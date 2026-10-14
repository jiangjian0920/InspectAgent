from __future__ import annotations

from typing import Callable

from app.analysis.operators import (
    aggregate,
    compare,
    detect_anomaly,
    filter as filter_op,
    group_by,
    limit,
    sort,
    summarize,
    trend,
)
from app.analysis.state import PipelineState
from app.core.errors import PlanValidationError
from app.domain.models import AnalysisOperation

OperatorFn = Callable[[PipelineState, AnalysisOperation], PipelineState]

OPERATORS: dict[str, OperatorFn] = {
    "aggregate": aggregate.run,
    "group_by": group_by.run,
    "filter": filter_op.run,
    "sort": sort.run,
    "limit": limit.run,
    "compare": compare.run,
    "trend": trend.run,
    "detect_anomaly": detect_anomaly.run,
    "summarize": summarize.run,
}

# 直接消费 MetricSeries 的算子。
SERIES_OPERATORS = {"aggregate", "compare", "trend", "detect_anomaly"}
# 消费中间记录的算子。
RECORD_OPERATORS = {"group_by", "filter", "sort", "limit", "summarize"}


def is_registered(name: str) -> bool:
    return name in OPERATORS


def get_operator(name: str) -> OperatorFn:
    if name not in OPERATORS:
        raise PlanValidationError(f"未注册的分析算子: {name}")
    return OPERATORS[name]


def registered_names() -> list[str]:
    return list(OPERATORS.keys())


__all__ = [
    "OPERATORS",
    "SERIES_OPERATORS",
    "RECORD_OPERATORS",
    "is_registered",
    "get_operator",
    "registered_names",
]
