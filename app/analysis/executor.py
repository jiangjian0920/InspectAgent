from __future__ import annotations

from app.analysis.registry import get_operator
from app.analysis.state import PipelineState
from app.domain.models import MetricDefinition, MetricSeries, InspectionPlan
from app.rules.loader import Policies


def execute_plan(
    plan: InspectionPlan,
    series: list[MetricSeries],
    definitions: dict[str, MetricDefinition],
    policies: Policies,
    *,
    target_label: str,
    time_range_label: str,
) -> PipelineState:
    """单轮执行：按计划顺序运行分析算子，返回最终状态。"""
    state = PipelineState(
        series=series,
        definitions=definitions,
        policies=policies,
        task_type=plan.task_type,
        target_label=target_label,
        time_range_label=time_range_label,
        limit_default=policies.default_limit,
    )
    for operation in plan.operations:
        state = get_operator(operation.type)(state, operation)
    return state


__all__ = ["execute_plan"]
