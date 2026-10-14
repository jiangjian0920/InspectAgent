from __future__ import annotations

from typing import Any

from app.analysis.state import PipelineState
from app.domain.models import AnalysisOperation


_SEVERITY_ORDER = {"critical": 2, "warning": 1}


def run(state: PipelineState, op: AnalysisOperation) -> PipelineState:
    """按数值或严重级别排序。"""
    field = op.field or "value"
    direction = (op.direction or "desc").lower()
    reverse = direction != "asc"

    def key(record: dict[str, Any]) -> float:
        if field == "severity":
            return float(_SEVERITY_ORDER.get(record.get("severity"), 0))
        value = record.get(field)
        if isinstance(value, (int, float)):
            return float(value)
        return float("-inf")

    state.records = sorted(state.records, key=key, reverse=reverse)
    return state


__all__ = ["run"]
