from __future__ import annotations

from typing import Any

from app.analysis.state import PipelineState
from app.domain.models import AnalysisOperation
from app.rules.engine import format_threshold, severity_of


_OPERATORS = {
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
}


def _match(record: dict[str, Any], field: str, comparison: str, threshold: float) -> bool:
    value = record.get(field)
    if not isinstance(value, (int, float)):
        return False
    func = _OPERATORS.get(comparison or "gt")
    return bool(func(value, threshold)) if func else False


def run(state: PipelineState, op: AnalysisOperation) -> PipelineState:
    """按阈值、严重级别或维度过滤记录；默认保留异常项。"""
    field = op.field or "value"
    comparison = op.comparison
    threshold = op.threshold
    severity_filter = op.param("severity")
    dimension_filters = op.param("dimensions") or {}
    kept: list[dict[str, Any]] = []

    for record in state.records:
        definition = state.definitions.get(record.get("metric_id", ""))
        value = record.get("value")
        if definition is not None and field == "value" and isinstance(value, (int, float)):
            record["severity"] = severity_of(value, definition)
            record["threshold_warning"] = format_threshold(
                definition.thresholds.get("warning"), definition.unit
            )
            record["threshold_critical"] = format_threshold(
                definition.thresholds.get("critical"), definition.unit
            )
        dimensions = record.get("dimensions") or {}
        if any(str(dimensions.get(k, "")) != str(v) for k, v in dimension_filters.items()):
            continue
        if comparison and threshold is not None:
            if _match(record, field, comparison, float(threshold)):
                kept.append(record)
        elif severity_filter:
            if record.get("severity") == severity_filter:
                kept.append(record)
        elif record.get("severity") in {"warning", "critical"} or any(
            key in record for key in ("verdict", "direction", "status")
        ):
            # 事件、对比、趋势等结构化记录原样保留；指标记录只留异常项。
            kept.append(record)

    state.records = kept
    return state


__all__ = ["run"]
