from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import ResourceType, TargetScope, TaskType
from app.domain.models import AnalysisOperation


class ModelTimeRange(BaseModel):
    type: str = "relative"
    value: str = ""


class ModelPeriod(BaseModel):
    name: str
    start: str
    end: str


class ModelTarget(BaseModel):
    type: ResourceType = "server"
    instance: str | None = None
    scope: TargetScope | None = None


class ModelIntent(BaseModel):
    """GLM 输出的意图草稿。可包含高层意图，也可直接给出受控 DSL。"""

    task_type: TaskType
    target: ModelTarget = Field(default_factory=ModelTarget)
    metrics: list[str] = Field(default_factory=list)
    time_range: ModelTimeRange | None = None
    periods: list[ModelPeriod] = Field(default_factory=list)
    operations: list[AnalysisOperation] = Field(default_factory=list)
    limit: int | None = None


def intent_example() -> str:
    """给模型的 JSON 输出示例。"""
    return (
        '{"task_type": "period_comparison", "target": {"type": "server", '
        '"instance": "192.168.59.130"}, "metrics": ["cpu", "memory"], '
        '"periods": [{"name": "today", "start": "today 00:00", "end": "now"}, '
        '{"name": "yesterday", "start": "yesterday 00:00", "end": "yesterday 23:59:59"}]}'
    )


__all__ = [
    "ModelTimeRange",
    "ModelPeriod",
    "ModelTarget",
    "ModelIntent",
    "intent_example",
]
