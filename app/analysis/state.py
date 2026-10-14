from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.models import MetricDefinition, MetricSeries
from app.rules.loader import Policies


@dataclass
class PipelineState:
    """分析流水线的可变状态。算子按顺序读写它。"""

    series: list[MetricSeries]
    definitions: dict[str, MetricDefinition]
    policies: Policies
    task_type: str = ""
    target_label: str = ""
    time_range_label: str = ""
    limit_default: int = 10
    records: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)


__all__ = ["PipelineState"]
