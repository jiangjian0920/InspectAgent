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
