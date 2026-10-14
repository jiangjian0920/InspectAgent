from __future__ import annotations

from typing import Literal


# 逻辑指标单位。
Unit = Literal["percent", "bytes", "count", "seconds", "ratio"]

# 数据采集状态。missing 与 error 必须原样进入报告，不得转成健康结论。
CollectionStatus = Literal["ok", "missing", "partial", "error"]

# 异常严重级别。
Severity = Literal["warning", "critical"]

# 单条发现的状态。
FindingStatus = Literal["active", "recovered", "unknown"]

# 报告整体查询状态。
QueryStatus = Literal[
    "healthy",
    "not_found",
    "metric_missing",
    "data_source_error",
    "partial_data",
    "no_capability",
]

# 任务类型。前四项来自设计文档，后两项对应排行与阈值筛选组合。
TaskType = Literal[
    "instant_inspection",
    "historical_anomaly_summary",
    "period_comparison",
    "trend_analysis",
    "ranking_query",
    "threshold_filter",
]

# 资源类型。第一阶段只有 server。
ResourceType = Literal["server"]

TargetScope = Literal["instance", "all"]

ReportMode = Literal["template", "llm_summary"]

ComparisonOp = Literal["gt", "lt", "ge", "le"]

AggregationFunction = Literal["avg", "max", "min", "p95", "sum", "latest", "count"]

__all__ = [
    "Unit",
    "CollectionStatus",
    "Severity",
    "FindingStatus",
    "QueryStatus",
    "TaskType",
    "ResourceType",
    "TargetScope",
    "ReportMode",
    "ComparisonOp",
    "AggregationFunction",
]
