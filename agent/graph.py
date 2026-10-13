from __future__ import annotations

import os
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

try:
    from langgraph.types import Send
except ImportError:
    from langgraph.constants import Send

from agent.intent import InspectionIntent, parse_intent
from agent.report.builder import build_inspection_report

# 默认关掉 LangSmith 追踪。
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("LANGSMITH_TRACING", "false")


def _append_results(
    left: list[dict[str, Any]] | None,
    right: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """把多个 Skill 节点返回的 results 拼成一份列表。"""
    return list(left or []) + list(right or [])


class InspectionState(TypedDict, total=False):
    """巡检图在节点之间传递的状态。"""

    user_input: str
    intent: dict[str, Any]
    results: Annotated[list[dict[str, Any]], _append_results]
    extra_suggestions: str
    report: str


def intent_to_dict(intent: InspectionIntent) -> dict[str, Any]:
    """把 InspectionIntent 转成字典，写入图状态。"""
    return {
        "user_input": intent.user_input,
        "time_range": intent.time_range,
        "cluster_wide": intent.cluster_wide,
        "targets": list(intent.targets),
    }


def intent_from_state(state: InspectionState, default_time_range: str) -> InspectionIntent:
    """从图状态里把意图再组装回 InspectionIntent。"""
    data = state.get("intent") or {}
    return InspectionIntent(
        user_input=str(data.get("user_input") or state.get("user_input") or ""),
        time_range=str(data.get("time_range") or default_time_range),
        cluster_wide=bool(data.get("cluster_wide")),
        targets=list(data.get("targets") or []),
    )


def build_inspection_graph(agent: Any):
    """组装巡检图：解析意图、按目标调用 Skill、补建议、生成报告。"""

    def parse_intent_node(state: InspectionState) -> dict[str, Any]:
        # 从用户输入里解析出要查哪些对象、实例和指标。
        intent = parse_intent(state.get("user_input") or "", agent.settings.default_time_range)
        agent.logger.info(
            "意图解析 cluster_wide=%s time_range=%s targets=%s",
            intent.cluster_wide,
            intent.time_range,
            intent.targets,
        )
        return {"intent": intent_to_dict(intent)}

    def route_skills(state: InspectionState):
        """根据意图里的 targets，把任务分发给对应的 Skill 节点。"""
        intent = state.get("intent") or {}
        registered = set(agent.skills.names())
        sends = []
        for target in intent.get("targets") or []:
            name = str(target.get("skill") or "")
            if name not in registered:
                continue
            sends.append(
                Send(
                    name,
                    {
                        "instance": target.get("instance") or "",
                        "metrics": list(target.get("metrics") or []),
                        "time_range": intent.get("time_range") or agent.settings.default_time_range,
                    },
                )
            )
        # 没有可调用的 Skill 时，跳到建议节点。
        return sends or "suggest"

    def make_skill_node(skill_name: str):
        """生成名为 skill_name 的节点函数，执行对应 Skill。"""

        def skill_node(state: dict[str, Any]) -> dict[str, Any]:
            arguments = {
                "instance": state.get("instance") or "",
                "metrics": list(state.get("metrics") or []),
                "time_range": state.get("time_range") or agent.settings.default_time_range,
            }
            return {"results": [agent._run_one(skill_name, arguments)]}

        skill_node.__name__ = skill_name
        return skill_node

    def suggest_node(state: InspectionState) -> dict[str, Any]:
        # 有密钥、且至少找到过实例时，让模型根据 Skill 结果补几句建议。
        intent = intent_from_state(state, agent.settings.default_time_range)
        results = list(state.get("results") or [])
        extra = ""
        all_missing = bool(results) and all(not item.get("instance_found") for item in results)
        if agent._need_llm() and not all_missing:
            extra = agent._ask_llm(state.get("user_input") or intent.user_input, intent, results)
        return {"extra_suggestions": extra}

    def report_node(state: InspectionState) -> dict[str, Any]:
        # 并行 Skill 返回顺序不固定，这里按意图里的目标顺序排一下再出报告。
        intent = intent_from_state(state, agent.settings.default_time_range)
        results = list(state.get("results") or [])
        order = {str(item.get("skill")): index for index, item in enumerate(intent.targets)}
        results.sort(key=lambda item: order.get(str(item.get("skill") or ""), 999))
        return {
            "report": build_inspection_report(
                intent,
                results,
                str(state.get("extra_suggestions") or ""),
            )
        }

    builder = StateGraph(InspectionState)
    builder.add_node("parse_intent", parse_intent_node)
    for skill in agent.skills.all_skills():
        builder.add_node(skill.name, make_skill_node(skill.name))
    builder.add_node("suggest", suggest_node)
    builder.add_node("report", report_node)
    builder.add_edge(START, "parse_intent")
    builder.add_conditional_edges("parse_intent", route_skills)
    for skill in agent.skills.all_skills():
        builder.add_edge(skill.name, "suggest")
    builder.add_edge("suggest", "report")
    builder.add_edge("report", END)
    return builder.compile()
