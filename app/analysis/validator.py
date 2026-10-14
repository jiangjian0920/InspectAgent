from __future__ import annotations

from app.analysis.registry import RECORD_OPERATORS, SERIES_OPERATORS, is_registered
from app.core.errors import PlanValidationError
from app.domain.models import AnalysisOperation, MetricDefinition


def validate_operations(
    operations: list[AnalysisOperation],
    metric_ids: list[str],
    definitions: dict[str, MetricDefinition],
) -> None:
    """校验分析 DSL：算子白名单、指标支持、顺序有效。"""
    if not operations:
        raise PlanValidationError("执行计划没有任何分析算子")

    first_series_level = False
    seen_sort = False
    summarize_index: int | None = None

    for index, op in enumerate(operations):
        if not is_registered(op.type):
            raise PlanValidationError(
                f"未注册的分析算子: {op.type}，可用算子: {sorted(SERIES_OPERATORS | RECORD_OPERATORS)}"
            )
        if op.type in SERIES_OPERATORS:
            first_series_level = True
        if op.type == "limit" and not seen_sort:
            raise PlanValidationError("limit 必须出现在 sort 之后")
        if op.type == "sort":
            seen_sort = True
        if op.type == "summarize":
            summarize_index = index

        for metric_id in metric_ids:
            definition = definitions.get(metric_id)
            if definition is None:
                raise PlanValidationError(f"未声明支持的指标: {metric_id}")
            if not definition.allows_operation(op.type):
                raise PlanValidationError(
                    f"指标 {metric_id} 不支持算子 {op.type}，允许: {definition.supported_operations}"
                )

    if not first_series_level:
        raise PlanValidationError("执行计划缺少取数算子（aggregate / trend / detect_anomaly / compare）")
    if summarize_index is not None and summarize_index != len(operations) - 1:
        raise PlanValidationError("summarize 必须是最后一个算子")


__all__ = ["validate_operations"]
