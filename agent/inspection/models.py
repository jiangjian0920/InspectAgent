from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryRecord:
    promql: str
    time_range: str
    metric_key: str | None
    result: dict[str, Any]
    purpose: str = "primary"


@dataclass
class Finding:
    metric_key: str
    metric_name: str
    meaning: str
    unit: str
    labels: dict[str, str]
    latest: float | None
    max_value: float | None
    avg_value: float | None
    warning: float | None
    critical: float | None
    severity: str
    source_promql: str
    error: str | None = None
    purpose: str = "primary"


@dataclass
class InspectionContext:
    user_input: str
    time_range: str
    instance: str | None = None
    start: str | None = None
    end: str | None = None
    requested_metric_keys: list[str] = field(default_factory=list)
    instance_unavailable: bool = False
    stop_reason: str = ""
    data_complete: bool = False
    queries: list[QueryRecord] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def has_metric(self, metric_key: str) -> bool:
        return any(item.metric_key == metric_key for item in self.queries)

    def has_followup(self, metric_key: str, followup_key: str | None = None) -> bool:
        if followup_key:
            target = f"{metric_key}:{followup_key}"
            return any(item.metric_key == target and item.purpose == "followup" for item in self.queries)
        prefix = f"{metric_key}:"
        return any(
            (item.metric_key or "").startswith(prefix) and item.purpose == "followup"
            for item in self.queries
        )

    def add_query(self, record: QueryRecord) -> None:
        self.queries.append(record)
        if record.result.get("ok") and record.result.get("start"):
            self.start = record.result.get("start")
            self.end = record.result.get("end")
