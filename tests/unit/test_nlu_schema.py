from __future__ import annotations

from app.domain.models import AnalysisOperation
from app.nlu.schema import ModelIntent


def test_operations_as_strings_are_coerced():
    model = ModelIntent.model_validate(
        {
            "task_type": "period_comparison",
            "target": {"type": "server", "instance": "192.168.59.130"},
            "metrics": ["cpu"],
            "operations": ["aggregate", {"type": "compare"}, "summarize"],
        }
    )
    assert [op.type for op in model.operations] == ["aggregate", "compare", "summarize"]


def test_operations_as_single_string_and_none():
    assert ModelIntent.model_validate(
        {"task_type": "instant_inspection", "operations": "aggregate"}
    ).operations == [AnalysisOperation(type="aggregate")]
    assert ModelIntent.model_validate(
        {"task_type": "instant_inspection", "operations": None}
    ).operations == []


def test_periods_as_strings_and_dicts():
    model = ModelIntent.model_validate(
        {"task_type": "period_comparison", "periods": ["today", {"start": "2026-01-01"}]}
    )
    assert model.periods[0].name == "today"
    assert model.periods[0].end == "now"
    assert model.periods[1].name == "2026-01-01"


def test_target_string_and_metrics_string():
    model = ModelIntent.model_validate(
        {"task_type": "instant_inspection", "target": "192.168.59.130", "metrics": "cpu，memory"}
    )
    assert model.target.instance == "192.168.59.130"
    assert model.metrics == ["cpu", "memory"]


def test_task_type_accepts_chinese_and_camel_case():
    assert ModelIntent.model_validate({"task_type": "排名查询"}).task_type == "ranking_query"
    assert ModelIntent.model_validate({"task_type": "InstantInspection"}).task_type == "instant_inspection"
    assert ModelIntent.model_validate({"task_type": "趋势分析"}).task_type == "trend_analysis"


def test_operations_infer_type_from_fields():
    model = ModelIntent.model_validate(
        {
            "task_type": "threshold_filter",
            "operations": [
                {"function": "avg", "group_by": ["instance"]},
                {"field": "value", "comparison": "gt", "threshold": 80},
                {"operator": "sort", "field": "value", "direction": "desc"},
            ],
        }
    )
    assert [op.type for op in model.operations] == ["aggregate", "filter", "sort"]


def test_metric_objects_and_chinese_scope():
    model = ModelIntent.model_validate(
        {
            "task_type": "ranking_query",
            "target": {"scope": "全部"},
            "metrics": [{"metric": "cpu"}],
        }
    )
    assert model.metrics == ["cpu"]
    assert model.target.scope == "all"
