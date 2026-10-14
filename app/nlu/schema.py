from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.enums import ResourceType, TargetScope, TaskType
from app.domain.models import AnalysisOperation


class ModelTimeRange(BaseModel):
    type: str = "relative"
    value: str = ""


class ModelPeriod(BaseModel):
    name: str
    start: str
    end: str

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        # 模型可能把时间段写成字符串，例如 "today" / "yesterday"。
        if isinstance(value, str):
            name = value.strip().lower()
            if name in {"today", "今天", "今日"}:
                return {"name": "today", "start": "today 00:00", "end": "now"}
            if name in {"yesterday", "昨天", "昨日"}:
                return {
                    "name": "yesterday",
                    "start": "yesterday 00:00",
                    "end": "yesterday 23:59:59",
                }
            return {"name": name, "start": name, "end": name}
        if isinstance(value, dict) and "name" not in value:
            start = value.get("start") or "now"
            name = str(value.get("start") or "period")
            value = {
                "name": name,
                "start": start,
                "end": value.get("end") or "now",
            }
        return value


class ModelTarget(BaseModel):
    type: ResourceType = "server"
    instance: str | None = None
    scope: TargetScope | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        # 模型可能只给出实例字符串。
        if isinstance(value, str):
            return {"type": "server", "instance": value or None}
        return value


class ModelIntent(BaseModel):
    """GLM 输出的意图草稿。可包含高层意图，也可直接给出受控 DSL。"""

    task_type: TaskType
    target: ModelTarget = Field(default_factory=ModelTarget)
    metrics: list[str] = Field(default_factory=list)
    time_range: ModelTimeRange | None = None
    periods: list[ModelPeriod] = Field(default_factory=list)
    operations: list[AnalysisOperation] = Field(default_factory=list)
    limit: int | None = None

    @field_validator("metrics", mode="before")
    @classmethod
    def _coerce_metrics(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.replace("，", ",").split(",") if part.strip()]
        return value

    @field_validator("operations", mode="before")
    @classmethod
    def _coerce_operations(cls, value: Any) -> Any:
        # 模型可能返回字符串算子名，或 {"type": ...} 与纯字典混合。
        if value is None:
            return []
        if isinstance(value, (str, dict)):
            value = [value]
        if not isinstance(value, list):
            return []
        normalized: list[Any] = []
        for item in value:
            if isinstance(item, str):
                normalized.append({"type": item})
            else:
                normalized.append(item)
        return normalized

    @field_validator("time_range", mode="before")
    @classmethod
    def _coerce_time_range(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"type": "relative", "value": value}
        return value

    @field_validator("periods", mode="before")
    @classmethod
    def _coerce_periods(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, (str, dict)):
            value = [value]
        return value


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
