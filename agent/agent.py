from __future__ import annotations

import json
from typing import Any

from agent.config import Settings
from agent.graph import build_inspection_graph
from agent.intent import InspectionIntent
from agent.llm.client import LLMTimeoutError, ZhipuLLMClient
from agent.logger import get_logger
from agent.skills import build_default_skills
from agent.skills.base import SkillRegistry
from agent.utils import dumps_compact


class InspectionAgent:
    """巡检 Agent：编译 LangGraph，按用户指令跑一遍图，返回报告文本。"""

    def __init__(
        self,
        settings: Settings,
        skill_registry: SkillRegistry | None = None,
        llm_client: ZhipuLLMClient | None = None,
    ) -> None:
        self.settings = settings
        self.logger = get_logger()
        # 测试可以传入自定义注册表；线上用默认四个 Skill。
        self.skills = skill_registry or build_default_skills(settings)
        self.llm = llm_client
        self._graph = None

    def graph(self):
        """第一次调用时编译图，之后复用。"""
        if self._graph is None:
            self._graph = build_inspection_graph(self)
        return self._graph

    def run(self, user_input: str) -> str:
        """接收一条自然语言指令，返回巡检报告。"""
        instruction = (user_input or "").strip()
        if not instruction:
            return "请输入巡检指令，例如：查询服务器 192.168.59.130 的 cpu。"
        # results 初始成空列表，后面 Skill 节点往里面追加。
        final = self.graph().invoke({"user_input": instruction, "results": []})
        return str(final.get("report") or "")

    def _need_llm(self) -> bool:
        """判断这次巡检要不要调智谱补建议。"""
        if self.llm is not None:
            return True
        return bool(self.settings.zhipu_api_key)

    def _llm(self) -> ZhipuLLMClient:
        if self.llm is None:
            self.llm = ZhipuLLMClient(self.settings)
        return self.llm

    def _run_one(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """按名字取出 Skill 并执行；出错时返回一份失败结果。"""
        self.logger.info("调用 Skill name=%s arguments=%s", name, dumps_compact(arguments, 1000))
        try:
            skill = self.skills.get(name)
            result = skill.execute(**arguments)
        except Exception as exc:
            self.logger.exception("Skill 执行失败 name=%s error=%s", name, exc)
            result = {
                "ok": False,
                "skill": name,
                "instance": arguments.get("instance") or "",
                "scope": arguments.get("metrics") or [],
                "time_range": arguments.get("time_range"),
                "instance_found": False,
                "message": "未找到对应实例" if "未找到" in str(exc) else "",
                "anomalies": [],
                "checked": [],
                "checked_count": 0,
                "healthy": False,
                "error": f"Skill 执行异常: {exc}",
            }
        self.logger.info("Skill 返回 name=%s result=%s", name, dumps_compact(result, 2000))
        return result

    def _ask_llm(self, instruction: str, intent: InspectionIntent, results: list[dict[str, Any]]) -> str:
        """把意图和 Skill 结果发给模型，拿回补充建议文本。"""
        payload = {
            "instruction": instruction,
            "intent": {
                "cluster_wide": intent.cluster_wide,
                "time_range": intent.time_range,
                "targets": intent.targets,
            },
            "skill_results": results,
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Prometheus 巡检助手。阈值判断和指标查询已由 Skill 完成。"
                    "你只能基于给定的真实结果用一两句话补充运维建议。"
                    "禁止编造数值，禁止要求再次调用工具，禁止建议自动变更。"
                    "变更类建议必须标注：需要人工确认后执行。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "以下是意图解析和 Skill 返回的真实结果，请补充简短建议，不要重复罗列全部字段：\n"
                    + json.dumps(payload, ensure_ascii=False)
                ),
            },
        ]
        try:
            response = self._llm().chat(messages=messages, tools=None, round_index=1)
            message = response.choices[0].message
            return (getattr(message, "content", None) or "").strip()
        except LLMTimeoutError as exc:
            self.logger.warning("LLM 超时，仅输出 Skill 结果 error=%s", exc)
            return f"模型超时，报告仅基于 Skill 真实结果。{exc}"
        except Exception as exc:
            self.logger.warning("LLM 补充建议失败，仅输出 Skill 结果 error=%s", exc)
            return ""
