"""公共分析算子。"""

from __future__ import annotations

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

__all__ = [
    "aggregate",
    "compare",
    "detect_anomaly",
    "filter_op",
    "group_by",
    "limit",
    "sort",
    "summarize",
    "trend",
]
