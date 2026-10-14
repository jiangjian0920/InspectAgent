from __future__ import annotations

from app.analysis.state import PipelineState
from app.domain.models import AnalysisOperation


def run(state: PipelineState, op: AnalysisOperation) -> PipelineState:
    """截取前 N 条。"""
    count = op.count or op.param("count") or state.limit_default
    try:
        size = int(count)
    except (TypeError, ValueError):
        size = state.limit_default
    if size > 0:
        state.records = state.records[:size]
    return state


__all__ = ["run"]
