from __future__ import annotations

from app.core.config import Settings
from app.domain.models import InspectionIntent, NamedTimeRange
from app.inventory.catalog import AssetCatalog
from app.planner.planner import InspectionPlanner
from app.rules.loader import load_policies
from app.skills.providers.server.skill import ServerMetricSkill
from tests.fakes import FakePrometheusClient


def _planner(settings: Settings) -> InspectionPlanner:
    catalog = AssetCatalog.from_yaml(settings.resolved_assets_path())
    provider = ServerMetricSkill(settings, client=FakePrometheusClient(), catalog=catalog)
    return InspectionPlanner(settings, provider, load_policies(settings))


def _intent(operations, task_type="period_comparison"):
    from app.domain.models import TimeRange
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return InspectionIntent(
        task_type=task_type,
        instance="192.168.59.130",
        metrics=["cpu"],
        periods=[
            NamedTimeRange(name="today", start="today 00:00", end="now"),
            NamedTimeRange(name="yesterday", start="yesterday 00:00", end="yesterday 23:59:59"),
        ],
        time_range=TimeRange(start=now, end=now, step_seconds=60),
        operations=operations,
    )


def test_model_operations_are_completed_with_summarize(settings):
    from app.domain.models import AnalysisOperation

    planner = _planner(settings)
    plan = planner.build(_intent([AnalysisOperation(type="compare")]))
    types = [op.type for op in plan.operations]
    assert "compare" in types
    assert types[-1] == "summarize"


def test_operations_without_series_stage_fall_back_to_default(settings):
    from app.domain.models import AnalysisOperation

    planner = _planner(settings)
    plan = planner.build(_intent([AnalysisOperation(type="sort"), AnalysisOperation(type="summarize")]))
    types = [op.type for op in plan.operations]
    # 默认时段对比组合包含 compare。
    assert "compare" in types
