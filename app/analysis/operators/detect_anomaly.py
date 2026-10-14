from __future__ import annotations

from typing import Any

from app.analysis.state import PipelineState
from app.domain.models import AnalysisOperation
from app.rules.engine import detect_events


def run(state: PipelineState, op: AnalysisOperation) -> PipelineState:
    """把越阈值序列合并为异常事件。"""
    records: list[dict[str, Any]] = []
    for series in state.series:
        definition = state.definitions.get(series.metric_id)
        if definition is None:
            continue
        for event in detect_events(series, definition, state.policies.anomaly):
            event["kind"] = "anomaly_event"
            records.append(event)
    state.records = records
    return state


__all__ = ["run"]
