from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent.config import Settings
from agent.prometheus_client import PrometheusClient


class Skill(ABC):
    """一类巡检能力。子类实现 execute()，由注册表挂到 LangGraph 节点上。"""

    name: str
    description: str
    target_type: str

    def __init__(self, settings: Settings, prometheus: PrometheusClient | None = None) -> None:
        self.settings = settings
        # 每个 Skill 自己拿 Prometheus 客户端去查指标。
        self.prometheus = prometheus or PrometheusClient(settings)

    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """返回这个 Skill 的入参结构。"""
        raise NotImplementedError

    @abstractmethod
    def execute(self, **kwargs: Any) -> dict[str, Any]:
        """按 instance / metrics / time_range 跑巡检，返回结构化结果。"""
        raise NotImplementedError

    def default_metrics(self) -> list[str]:
        """没指定指标时，execute 会查这些默认项。"""
        return []

    def to_tool_spec(self) -> dict[str, Any]:
        """把 Skill 描述成 Function Calling 的工具格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema(),
            },
        }


class SkillRegistry:
    """按名字存放 Skill，图编译和运行时都从这里取。"""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill:
        if name not in self._skills:
            available = ", ".join(sorted(self._skills)) or "<empty>"
            raise KeyError(f"未注册的工具: {name}，当前可用: {available}")
        return self._skills[name]

    def by_target(self, target_type: str) -> Skill | None:
        for skill in self._skills.values():
            if skill.target_type == target_type:
                return skill
        return None

    def all_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def tool_specs(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        if names is None:
            return [skill.to_tool_spec() for skill in self._skills.values()]
        return [self.get(name).to_tool_spec() for name in names if name in self._skills]

    def names(self) -> list[str]:
        return list(self._skills.keys())
