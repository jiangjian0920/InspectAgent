from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.enums import ResourceType, TargetScope, TaskType
from app.domain.models import AnalysisOperation


# 模型可能用近义词、中文或大小写变体表达 task_type。
_TASK_ALIASES = {
    "instant": "instant_inspection",
    "instant_inspection": "instant_inspection",
    "current": "instant_inspection",
    "snapshot": "instant_inspection",
    "status": "instant_inspection",
    "realtime": "instant_inspection",
    "即时": "instant_inspection",
    "即时巡检": "instant_inspection",
    "实时": "instant_inspection",
    "实时巡检": "instant_inspection",
    "当前状态": "instant_inspection",
    "现状巡检": "instant_inspection",
    "历史异常": "historical_anomaly_summary",
    "历史异常汇总": "historical_anomaly_summary",
    "historical_anomaly_summary": "historical_anomaly_summary",
    "anomaly": "historical_anomaly_summary",
    "anomalies": "historical_anomaly_summary",
    "anomaly_summary": "historical_anomaly_summary",
    "history_anomaly": "historical_anomaly_summary",
    "历史告警": "historical_anomaly_summary",
    "异常": "historical_anomaly_summary",
    "异常汇总": "historical_anomaly_summary",
    "异常清单": "historical_anomaly_summary",
    "period_comparison": "period_comparison",
    "comparison": "period_comparison",
    "compare": "period_comparison",
    "环比": "period_comparison",
    "对比": "period_comparison",
    "时段对比": "period_comparison",
    "同期对比": "period_comparison",
    "trend_analysis": "trend_analysis",
    "trend": "trend_analysis",
    "趋势": "trend_analysis",
    "趋势分析": "trend_analysis",
    "ranking_query": "ranking_query",
    "ranking": "ranking_query",
    "rank": "ranking_query",
    "top": "ranking_query",
    "topn": "ranking_query",
    "排行": "ranking_query",
    "排名": "ranking_query",
    "排序": "ranking_query",
    "最高": "ranking_query",
    "threshold_filter": "threshold_filter",
    "threshold": "threshold_filter",
    "filter": "threshold_filter",
    "阈值": "threshold_filter",
    "阈值筛选": "threshold_filter",
    "阈值过滤": "threshold_filter",
    "筛选": "threshold_filter",
}

_RESOURCE_TYPE_ALIASES = {
    "server": "server",
    "servers": "server",
    "host": "server",
    "node": "server",
    "machine": "server",
    "服务器": "server",
    "主机": "server",
    "节点": "server",
}

_SCOPE_ALIASES = {
    "instance": "instance",
    "single": "instance",
    "one": "instance",
    "实例": "instance",
    "单实例": "instance",
    "单个": "instance",
    "all": "all",
    "every": "all",
    "cluster": "all",
    "全部": "all",
    "所有": "all",
    "全量": "all",
    "全集群": "all",
    "整个集群": "all",
}

_OPERATION_TYPE_KEYS = ("type", "op", "operator", "action", "name")


def _normalize_token(value: str) -> str:
    text = value.strip()
    # camelCase / PascalCase 先拆成 snake_case。
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    return text.lower().replace(" ", "_").replace("-", "_")


def _normalize_task_type(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    token = _normalize_token(value)
    if token in _TASK_ALIASES:
        return _TASK_ALIASES[token]
    stripped = value.strip()
    if stripped in _TASK_ALIASES:
        return _TASK_ALIASES[stripped]
    # 中文近义表达做包含匹配，取最长的命中项。
    matches = [key for key in _TASK_ALIASES if key in token]
    if matches:
        return _TASK_ALIASES[max(matches, key=len)]
    return value


def _infer_operation_type(item: dict[str, Any]) -> str | None:
    """从算子字典的别名键或字段组合推断算子名。"""
    for key in _OPERATION_TYPE_KEYS:
        candidate = item.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    if "comparison" in item or "threshold" in item:
        return "filter"
    if "count" in item or "top" in item or "limit" in item:
        return "limit"
    if "direction" in item:
        return "sort"
    if "function" in item or "group_by" in item or "by" in item:
        return "aggregate"
    if "field" in item:
        return "sort"
    return None


class ModelTimeRange(BaseModel):
    type: str = "relative"
    value: str = ""

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        # 模型可能把时间范围写成纯字符串。
        if isinstance(value, (int, float)):
            return {"type": "relative", "value": str(value)}
        return value


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
            start = value.get("start") or value.get("start_time") or "now"
            name = str(start)
            value = {
                "name": name,
                "start": start,
                "end": value.get("end") or value.get("end_time") or "now",
            }
        return value


class ModelTarget(BaseModel):
    type: ResourceType = "server"
    instance: str | None = None
    scope: TargetScope | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        # 模型可能只给出实例字符串，或使用中文资源类型 / 范围。
        if isinstance(value, str):
            return {"type": "server", "instance": value or None}
        if isinstance(value, list):
            # 极端情况下模型给出实例列表，取第一个。
            first = value[0] if value else None
            return {"type": "server", "instance": str(first) if first else None}
        if isinstance(value, dict):
            normalized = dict(value)
            raw_type = normalized.get("type")
            if isinstance(raw_type, str):
                normalized["type"] = _RESOURCE_TYPE_ALIASES.get(
                    _normalize_token(raw_type), raw_type
                )
            raw_scope = normalized.get("scope")
            if isinstance(raw_scope, str):
                normalized["scope"] = _SCOPE_ALIASES.get(_normalize_token(raw_scope), raw_scope)
            raw_instance = normalized.get("instance")
            if isinstance(raw_instance, (int, float)):
                normalized["instance"] = str(raw_instance)
            return normalized
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

    @field_validator("task_type", mode="before")
    @classmethod
    def _coerce_task_type(cls, value: Any) -> Any:
        return _normalize_task_type(value)

    @field_validator("metrics", mode="before")
    @classmethod
    def _coerce_metrics(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, (str, dict)):
            value = [value]
        if not isinstance(value, list):
            return []
        normalized: list[Any] = []
        for item in value:
            if isinstance(item, str):
                normalized.append(item.strip())
            elif isinstance(item, dict):
                # 模型可能返回 [{"metric": "cpu"}] 之类的结构。
                for key in ("metric", "metric_id", "id", "name", "type"):
                    candidate = item.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        normalized.append(candidate.strip())
                        break
            elif isinstance(item, (int, float)):
                normalized.append(str(item))
        # 单个字符串里可能包含多个逗号分隔的指标。
        expanded: list[str] = []
        for item in normalized:
            expanded.extend(
                part.strip() for part in item.replace("，", ",").split(",") if part.strip()
            )
        return expanded

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
            elif isinstance(item, dict):
                entry = dict(item)
                if not isinstance(entry.get("type"), str) or not entry.get("type", "").strip():
                    inferred = _infer_operation_type(entry)
                    if inferred is not None:
                        entry["type"] = inferred
                normalized.append(entry)
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

    @field_validator("limit", mode="before")
    @classmethod
    def _coerce_limit(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            return int(text) if text.isdigit() else None
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
