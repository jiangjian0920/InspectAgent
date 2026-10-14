from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    AggregationFunction,
    CollectionStatus,
    ComparisonOp,
    FindingStatus,
    QueryStatus,
    ReportMode,
    ResourceType,
    Severity,
    TargetScope,
    TaskType,
    Unit,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimeRange(BaseModel):
    """已解析的绝对时间窗口。"""

    start: datetime
    end: datetime
    step_seconds: int = 60

    @property
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()


class NamedTimeRange(BaseModel):
    """模型给出的命名时间段，start/end 为表达式，规划阶段解析为绝对时间。"""

    name: str
    start: str
    end: str


class ThresholdRule(BaseModel):
    comparison: ComparisonOp
    value: float

    def violated(self, value: float | None) -> bool:
        if value is None:
            return False
        if self.comparison == "gt":
            return value > self.value
        if self.comparison == "lt":
            return value < self.value
        if self.comparison == "ge":
            return value >= self.value
        return value <= self.value


class MetricDefinition(BaseModel):
    """专项 Skill 声明的逻辑指标契约。"""

    metric_id: str
    display_name: str
    unit: Unit
    template_id: str
    aggregation: AggregationFunction = "avg"
    is_counter: bool = False
    supported_operations: list[str] = Field(default_factory=list)
    thresholds: dict[Severity, ThresholdRule] = Field(default_factory=dict)
    dimensions: list[str] = Field(default_factory=list)
    description: str = ""

    def allows_operation(self, operation: str) -> bool:
        return operation in self.supported_operations

    def threshold_violations(self, value: float | None) -> list[Severity]:
        hits: list[Severity] = []
        critical = self.thresholds.get("critical")
        warning = self.thresholds.get("warning")
        if critical is not None and critical.violated(value):
            hits.append("critical")
        if warning is not None and warning.violated(value):
            hits.append("warning")
        return hits


class ResolvedTarget(BaseModel):
    """资产目录解析结果。"""

    resource_id: str
    resource_type: ResourceType = "server"
    reference: str
    prometheus_instance: str
    environment: str = ""
    labels: dict[str, str] = Field(default_factory=dict)


class ServerTarget(BaseModel):
    """计划中的服务器目标。scope=all 表示授权范围内全部实例。"""

    scope: TargetScope = "instance"
    reference: str | None = None
    resource_id: str | None = None
    prometheus_instance: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    resource_type: ResourceType = "server"


class AnalysisOperation(BaseModel):
    """受控分析 DSL 中的单个算子声明。"""

    model_config = ConfigDict(extra="allow")

    type: str
    function: str | None = None
    group_by: list[str] = Field(default_factory=list)
    by: list[str] = Field(default_factory=list)
    field: str | None = None
    comparison: str | None = None
    threshold: float | None = None
    direction: str | None = None
    count: int | None = None
    period: str | None = None
    periods: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)

    def param(self, name: str, default: Any = None) -> Any:
        if name in self.params:
            return self.params[name]
        value = getattr(self, name, None)
        return value if value is not None else default


class MetricQueryPlan(BaseModel):
    """只包含来自受信任配置的信息，不接受模型原始 PromQL。"""

    template_id: str
    metric_id: str
    scope: TargetScope = "instance"
    instance: str | None = None
    time_range: TimeRange
    aggregation: AggregationFunction | None = None
    period: str | None = None
    params: dict[str, str] = Field(default_factory=dict)


class InspectionIntent(BaseModel):
    """模型输出经校验后的意图。"""

    task_type: TaskType
    target_type: ResourceType = "server"
    instance: str | None = None
    scope: TargetScope = "instance"
    metrics: list[str] = Field(default_factory=list)
    time_range: TimeRange | None = None
    periods: list[NamedTimeRange] = Field(default_factory=list)
    operations: list[AnalysisOperation] = Field(default_factory=list)
    limit: int | None = None
    raw_request: str = ""
    source: str = "llm"


class InspectionPlan(BaseModel):
    """策略层生成的不可变执行计划，是 Skill 唯一允许执行的指令来源。"""

    model_config = ConfigDict(frozen=False)

    request_id: str
    task_type: TaskType
    provider_skill: str
    target: ServerTarget
    metrics: list[str] = Field(default_factory=list)
    operations: list[AnalysisOperation] = Field(default_factory=list)
    queries: list[MetricQueryPlan] = Field(default_factory=list)
    max_query_count: int = 40
    timeout_seconds: int = 60
    report_mode: ReportMode = "template"
    created_at: datetime = Field(default_factory=utcnow)


class MetricSeries(BaseModel):
    """标准化指标契约。公共分析层只处理该类型。"""

    resource_id: str
    resource_type: ResourceType = "server"
    metric_id: str
    display_name: str = ""
    unit: Unit = "ratio"
    timestamps: list[datetime] = Field(default_factory=list)
    values: list[float | None] = Field(default_factory=list)
    dimensions: dict[str, str] = Field(default_factory=dict)
    collection_status: CollectionStatus = "ok"
    source_time_range: TimeRange
    period: str | None = None
    error: str | None = None

    def numeric_values(self) -> list[float]:
        return [v for v in self.values if isinstance(v, (int, float))]

    @property
    def sample_count(self) -> int:
        return len(self.numeric_values())


class Finding(BaseModel):
    instance: str
    metric: str
    severity: Severity
    value: float | None = None
    unit: Unit = "ratio"
    threshold: str = ""
    observed_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: float | None = None
    risk: str = ""
    status: FindingStatus = "active"
    dimensions: dict[str, str] = Field(default_factory=dict)
    display_name: str = ""


class MetricRow(BaseModel):
    """报告中的指标对照行。"""

    metric: str
    display_name: str = ""
    instance: str = ""
    dimensions: dict[str, str] = Field(default_factory=dict)
    current: float | None = None
    latest: float | None = None
    avg: float | None = None
    max: float | None = None
    p95: float | None = None
    unit: Unit = "ratio"
    threshold_warning: str = ""
    threshold_critical: str = ""
    severity: Severity | None = None
    risk: str = ""
    status: CollectionStatus = "ok"
    detail: str = ""


class InspectionReport(BaseModel):
    request_id: str
    task_type: TaskType
    query_status: QueryStatus
    target: str = ""
    scope: list[str] = Field(default_factory=list)
    time_range: str = ""
    metrics: list[MetricRow] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    summary: str = ""
    messages: list[str] = Field(default_factory=list)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utcnow)


__all__ = [
    "utcnow",
    "TimeRange",
    "NamedTimeRange",
    "ThresholdRule",
    "MetricDefinition",
    "ResolvedTarget",
    "ServerTarget",
    "AnalysisOperation",
    "MetricQueryPlan",
    "InspectionIntent",
    "InspectionPlan",
    "MetricSeries",
    "Finding",
    "MetricRow",
    "InspectionReport",
]
