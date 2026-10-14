from __future__ import annotations

from app.analysis.operators._grouping import group_records
from app.analysis.state import PipelineState
from app.domain.models import AnalysisOperation


def run(state: PipelineState, op: AnalysisOperation) -> PipelineState:
    """对指标记录按维度重新分组并聚合；结构化记录（事件/对比/趋势）原样保留。"""
    keys = op.group_by or op.by or []
    function = op.function or "avg"
    metric_records = [r for r in state.records if r.get("kind") == "metric"]
    others = [r for r in state.records if r.get("kind") != "metric"]
    if metric_records:
        state.records = group_records(metric_records, keys, function) + others
    return state


__all__ = ["run"]
