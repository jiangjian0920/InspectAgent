from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.analysis.executor import execute_plan
from app.domain.models import (
    AnalysisOperation,
    InspectionPlan,
    MetricSeries,
    ServerTarget,
    TimeRange,
)
from app.rules.loader import load_metric_catalog, load_policies


def _series(metric_id, resource_id, values, *, step=60, period=None, dimensions=None, unit="percent"):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timestamps = [start + timedelta(seconds=step * i) for i in range(len(values))]
    return MetricSeries(
        resource_id=resource_id,
        metric_id=metric_id,
        display_name=metric_id,
        unit=unit,
        timestamps=timestamps,
        values=values,
        dimensions=dimensions or {"instance": resource_id},
        source_time_range=TimeRange(start=timestamps[0], end=timestamps[-1], step_seconds=step),
        period=period,
    )


def _definitions(settings):
    return load_metric_catalog(settings.resolved_server_skill_dir() / "metric_catalog.yaml")


def _plan(ops, metrics):
    return InspectionPlan(
        request_id="test",
        task_type="instant_inspection",
        provider_skill="server_metric",
        target=ServerTarget(scope="all"),
        metrics=metrics,
        operations=ops,
        queries=[],
    )


def _run(settings, series, ops, metrics):
    policies = load_policies(settings)
    state = execute_plan(
        _plan(ops, metrics),
        series,
        _definitions(settings),
        policies,
        target_label="test",
        time_range_label="test",
    )
    return state


def test_aggregate_average(settings):
    series = [_series("cpu", "s1", [80, 90, 100])]
    state = _run(settings, series, [AnalysisOperation(type="aggregate", function="avg")], ["cpu"])
    assert state.records[0]["value"] == 90


def test_filter_keeps_only_anomalies(settings):
    series = [
        _series("cpu", "s1", [99, 99]),
        _series("cpu", "s2", [10, 20]),
    ]
    state = _run(
        settings,
        series,
        [AnalysisOperation(type="aggregate", function="avg"), AnalysisOperation(type="filter")],
        ["cpu"],
    )
    assert len(state.records) == 1
    assert state.records[0]["resource_id"] == "s1"
    assert state.records[0]["severity"] == "critical"


def test_sort_and_limit(settings):
    series = [
        _series("cpu", "s1", [50]),
        _series("cpu", "s2", [90]),
        _series("cpu", "s3", [70]),
    ]
    state = _run(
        settings,
        series,
        [
            AnalysisOperation(type="aggregate", function="avg", group_by=["instance"]),
            AnalysisOperation(type="sort", field="value", direction="desc"),
            AnalysisOperation(type="limit", count=2),
        ],
        ["cpu"],
    )
    assert [r["resource_id"] for r in state.records] == ["s2", "s3"]


def test_detect_anomaly_merges_and_recovers(settings):
    series = [_series("cpu", "s1", [10, 99, 99, 10, 10, 10])]
    state = _run(settings, series, [AnalysisOperation(type="detect_anomaly")], ["cpu"])
    assert len(state.records) == 1
    event = state.records[0]
    assert event["kind"] == "anomaly_event"
    assert event["status"] == "recovered"
    assert event["peak"] == 99
    assert event["sample_count"] == 2


def test_compare_detects_deterioration(settings):
    series = [
        _series("cpu", "s1", [50] * 5, period="yesterday"),
        _series("cpu", "s1", [90] * 5, period="today"),
    ]
    state = _run(settings, series, [AnalysisOperation(type="compare")], ["cpu"])
    record = state.records[0]
    assert record["kind"] == "comparison"
    assert record["before_period"] == "yesterday"
    assert record["after_period"] == "today"
    assert record["verdict"] == "恶化"
    assert record["delta"] == 40


def test_trend_rising(settings):
    values = [float(v) for v in range(50, 100)]
    series = [_series("cpu", "s1", values)]
    state = _run(settings, series, [AnalysisOperation(type="trend")], ["cpu"])
    record = state.records[0]
    assert record["kind"] == "trend"
    assert record["direction"] == "上升"
    assert record["slope_per_day"] > 0


def test_summarize_instant_findings(settings):
    series = [_series("cpu", "s1", [99, 99])]
    ops = [
        AnalysisOperation(type="aggregate", function="avg"),
        AnalysisOperation(type="filter"),
        AnalysisOperation(type="summarize"),
    ]
    state = _run(settings, series, ops, ["cpu"])
    assert state.report["findings"]
    assert state.report["findings"][0]["severity"] == "critical"
