from __future__ import annotations

from app.analysis.operators._grouping import group_records
from app.analysis.state import PipelineState
from app.domain.models import AnalysisOperation
from app.analysis.stats import pick_aggregate, summarize_values
from app.rules.engine import format_threshold, severity_of


def run(state: PipelineState, op: AnalysisOperation) -> PipelineState:
    """按函数对每条序列做时间聚合，再按 group_by 合并。"""
    function = op.function or "avg"
    group_by = op.group_by or op.by or []
    records: list[dict] = []
    for series in state.series:
        definition = state.definitions.get(series.metric_id)
        display = series.display_name or (definition.display_name if definition else series.metric_id)
        numeric = series.numeric_values()
        stats = summarize_values(numeric)
        value = pick_aggregate(stats, function) if series.collection_status == "ok" else None
        # 严重级别与阈值标签在取数阶段就标注，保证没有 filter 时报告也能给出级别。
        severity = severity_of(value, definition) if definition else None
        threshold_warning = (
            format_threshold(definition.thresholds.get("warning"), definition.unit)
            if definition
            else ""
        )
        threshold_critical = (
            format_threshold(definition.thresholds.get("critical"), definition.unit)
            if definition
            else ""
        )
        records.append(
            {
                "kind": "metric",
                "resource_id": series.resource_id,
                "metric_id": series.metric_id,
                "display_name": display,
                "unit": series.unit,
                "dimensions": dict(series.dimensions),
                "stats": stats,
                "value": value,
                "collection_status": series.collection_status,
                "error": series.error,
                "period": series.period,
                "severity": severity,
                "threshold_warning": threshold_warning,
                "threshold_critical": threshold_critical,
            }
        )
    state.records = group_records(records, group_by, function)
    return state


__all__ = ["run"]
