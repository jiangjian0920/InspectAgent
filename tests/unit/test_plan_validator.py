from __future__ import annotations

import pytest

from app.analysis.validator import validate_operations
from app.core.errors import PlanValidationError, TargetNotFoundError
from app.domain.models import AnalysisOperation, MetricDefinition, ThresholdRule


def _definition(metric_id: str, ops: list[str]) -> MetricDefinition:
    return MetricDefinition(
        metric_id=metric_id,
        display_name=metric_id,
        unit="percent",
        template_id="cpu_usage",
        supported_operations=ops,
        thresholds={"warning": ThresholdRule(comparison="gt", value=85)},
    )


def test_unknown_operator_rejected():
    with pytest.raises(PlanValidationError):
        validate_operations([AnalysisOperation(type="hack")], ["cpu"], {"cpu": _definition("cpu", ["hack"])})


def test_limit_before_sort_rejected():
    ops = [AnalysisOperation(type="aggregate"), AnalysisOperation(type="limit", count=3)]
    with pytest.raises(PlanValidationError):
        validate_operations(ops, ["cpu"], {"cpu": _definition("cpu", ["aggregate", "limit"])})


def test_unsupported_operator_for_metric_rejected():
    ops = [AnalysisOperation(type="aggregate"), AnalysisOperation(type="trend")]
    definitions = {"cpu": _definition("cpu", ["aggregate"])}
    with pytest.raises(PlanValidationError):
        validate_operations(ops, ["cpu"], definitions)


def test_summarize_must_be_last():
    ops = [
        AnalysisOperation(type="aggregate"),
        AnalysisOperation(type="summarize"),
        AnalysisOperation(type="filter"),
    ]
    definitions = {"cpu": _definition("cpu", ["aggregate", "summarize", "filter"])}
    with pytest.raises(PlanValidationError):
        validate_operations(ops, ["cpu"], definitions)


def test_unknown_instance_raises_before_query(settings, catalog, agent_factory):
    from tests.fakes import FakePrometheusClient

    client = FakePrometheusClient()
    agent = agent_factory(client)
    report = agent.run("查询服务器 192.168.59.131 的 CPU")
    assert report.query_status == "not_found"
    assert client.queries == []
