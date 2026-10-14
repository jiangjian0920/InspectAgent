from __future__ import annotations

from collections import OrderedDict
from typing import Any

from app.analysis.state import PipelineState
from app.domain.models import AnalysisOperation
from app.analysis.stats import summarize_values
from app.rules.engine import format_threshold, verdict_label


def _key(series) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    return (series.resource_id, series.metric_id, tuple(sorted((series.dimensions or {}).items())))


def run(state: PipelineState, op: AnalysisOperation) -> PipelineState:
    """同口径比较两个时间段，输出绝对与相对变化。"""
    groups: "OrderedDict[tuple, list]" = OrderedDict()
    for series in state.series:
        groups.setdefault(_key(series), []).append(series)

    records: list[dict[str, Any]] = []
    for series_list in groups.values():
        by_period: dict[str, dict[str, Any]] = {}
        period_order: dict[str, float] = {}
        for series in series_list:
            if not series.period:
                continue
            numeric = series.numeric_values()
            by_period[series.period] = summarize_values(numeric)
            start = series.source_time_range.start.timestamp()
            period_order[series.period] = min(period_order.get(series.period, start), start)

        if len(by_period) < 2:
            continue
        ordered = sorted(by_period.keys(), key=lambda name: period_order.get(name, 0.0))
        before_name, after_name = ordered[0], ordered[-1]
        before_stats, after_stats = by_period[before_name], by_period[after_name]
        # 用平均值作为比较口径。
        before_avg, after_avg = before_stats.get("avg"), after_stats.get("avg")

        definition = state.definitions.get(series_list[0].metric_id)
        comparison = (
            definition.thresholds.get("warning").comparison
            if definition and definition.thresholds.get("warning")
            else "gt"
        )
        verdict = verdict_label(
            series_list[0].metric_id, before_avg, after_avg, comparison, state.policies
        )
        delta = None
        relative = None
        if isinstance(before_avg, (int, float)) and isinstance(after_avg, (int, float)):
            delta = round(after_avg - before_avg, 4)
            relative = round(delta / abs(before_avg), 4) if before_avg else None

        records.append(
            {
                "kind": "comparison",
                "resource_id": series_list[0].resource_id,
                "metric_id": series_list[0].metric_id,
                "display_name": series_list[0].display_name,
                "unit": series_list[0].unit,
                "dimensions": dict(series_list[0].dimensions),
                "before_period": before_name,
                "after_period": after_name,
                "before": before_stats,
                "after": after_stats,
                "delta": delta,
                "relative": relative,
                "verdict": verdict,
                "severity": "warning" if verdict == "恶化" else None,
                "collection_status": series_list[0].collection_status,
                "threshold_warning": format_threshold(
                    definition.thresholds.get("warning"), definition.unit
                )
                if definition
                else "",
            }
        )
    state.records = records
    return state


__all__ = ["run"]
