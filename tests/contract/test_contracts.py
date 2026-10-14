from __future__ import annotations

import json

from app.analysis.validator import validate_operations
from app.domain.models import AnalysisOperation, MetricSeries
from app.prometheus.gateway import QueryGateway, QueryBudget
from app.rules.loader import load_metric_catalog, load_query_templates, load_policies


DSL_SAMPLE = """
{
  "resource_type": "server",
  "target_scope": "all_authorized_instances",
  "metrics": ["cpu"],
  "time_range": {"type": "relative", "value": "5m"},
  "operations": [
    {"type": "aggregate", "function": "avg", "group_by": ["instance"]},
    {"type": "sort", "field": "value", "direction": "desc"},
    {"type": "limit", "count": 10},
    {"type": "summarize"}
  ]
}
"""


def test_doc_dsl_validates(settings):
    payload = json.loads(DSL_SAMPLE)
    operations = [AnalysisOperation.model_validate(op) for op in payload["operations"]]
    definitions = load_metric_catalog(settings.resolved_server_skill_dir() / "metric_catalog.yaml")
    validate_operations(operations, payload["metrics"], definitions)


def test_metric_series_contract(settings):
    fields = set(MetricSeries.model_fields)
    for required in {
        "resource_id",
        "resource_type",
        "metric_id",
        "display_name",
        "unit",
        "timestamps",
        "values",
        "dimensions",
        "collection_status",
        "source_time_range",
    }:
        assert required in fields


def test_gateway_binds_instance_safely(settings, catalog):
    gateway = QueryGateway(
        settings,
        client=None,  # 不执行查询
        templates=load_query_templates(settings.resolved_server_skill_dir() / "queries.yaml"),
        catalog=catalog,
    )
    from app.domain.models import ServerTarget

    target = ServerTarget(
        scope="instance",
        resource_id="server-prod-130",
        prometheus_instance="192.168.59.130:9100",
        labels={"job": "node-exporter"},
    )
    from app.domain.models import MetricQueryPlan, TimeRange
    from datetime import datetime, timezone

    window = TimeRange(
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
        step_seconds=60,
    )
    query = MetricQueryPlan(
        template_id="cpu_usage", metric_id="cpu", scope="instance", time_range=window
    )
    values = gateway._binding_values(target, query)
    assert values["instance"] == "192[.]168[.]59[.]130:9100"
    promql = gateway.build_promql("cpu_usage", values)
    assert "node_cpu_seconds_total" in promql
    assert "$" not in promql


def test_policies_loaded(settings):
    policies = load_policies(settings)
    assert policies.anomaly.min_consecutive_samples >= 1
    assert policies.max_query_count == settings.max_query_count
