from __future__ import annotations

from typing import Any

from app.analysis.state import PipelineState
from app.domain.models import AnalysisOperation
from app.rules.engine import format_threshold, trend_stats


def run(state: PipelineState, op: AnalysisOperation) -> PipelineState:
    """计算趋势方向、斜率、峰值与持续风险。"""
    records: list[dict[str, Any]] = []
    for series in state.series:
        definition = state.definitions.get(series.metric_id)
        if definition is None:
            continue
        stats = trend_stats(series, definition, state.policies.trend)
        records.append(
            {
                "kind": "trend",
                "resource_id": series.resource_id,
                "metric_id": series.metric_id,
                "display_name": series.display_name or definition.display_name,
                "unit": series.unit,
                "dimensions": dict(series.dimensions),
                "collection_status": series.collection_status,
                "threshold_warning": format_threshold(
                    definition.thresholds.get("warning"), definition.unit
                ),
                "severity": "warning" if stats.get("sustained_risk") else None,
                **stats,
            }
        )
    state.records = records
    return state


__all__ = ["run"]
