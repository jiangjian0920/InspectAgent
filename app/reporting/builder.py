from __future__ import annotations

from typing import Any

from app.analysis.state import PipelineState
from app.domain.enums import QueryStatus
from app.domain.models import (
    Finding,
    InspectionPlan,
    InspectionReport,
    MetricRow,
    MetricSeries,
)

_STATUS_MESSAGES = {
    "healthy": "查询完成，数据正常。",
    "not_found": "未找到对应实例。",
    "metric_missing": "实例存在，但目标指标没有监控数据，无法判断。",
    "data_source_error": "Prometheus 查询失败，无法输出健康结论。",
    "partial_data": "部分指标缺失或查询失败，结论仅覆盖成功返回的数据。",
    "no_capability": "当前未配置该分析能力。",
}


def compute_query_status(series: list[MetricSeries]) -> QueryStatus:
    if not series:
        return "metric_missing"
    statuses = {s.collection_status for s in series}
    if "error" in statuses:
        return "data_source_error" if statuses <= {"error", "missing"} else "partial_data"
    if "missing" in statuses:
        return "metric_missing" if "ok" not in statuses else "partial_data"
    if "partial" in statuses:
        return "partial_data"
    return "healthy"


def target_label(plan: InspectionPlan) -> str:
    if plan.target.scope == "all":
        return "全部授权实例"
    return plan.target.resource_id or plan.target.reference or "未知实例"


def _time_label(plan: InspectionPlan) -> str:
    if plan.queries:
        starts = {q.time_range.start for q in plan.queries}
        ends = {q.time_range.end for q in plan.queries}
        if len(starts) == 1 and len(ends) == 1:
            start = next(iter(starts)).strftime("%Y-%m-%d %H:%M")
            end = next(iter(ends)).strftime("%Y-%m-%d %H:%M")
            return f"{start} ~ {end}"
        periods = sorted({q.period for q in plan.queries if q.period})
        if periods:
            return " / ".join(periods)
    return ""


def build_report(
    plan: InspectionPlan,
    series: list[MetricSeries],
    state: PipelineState,
    *,
    not_found: bool = False,
    status_override: QueryStatus | None = None,
    extra_message: str = "",
) -> InspectionReport:
    status: QueryStatus
    if not_found:
        status = "not_found"
    elif status_override is not None:
        status = status_override
    else:
        status = compute_query_status(series)

    report_data = state.report or {}
    findings = [Finding.model_validate(item) for item in report_data.get("findings", [])]
    rows = [MetricRow.model_validate(item) for item in report_data.get("rows", [])]

    summary = report_data.get("summary", "")
    messages = [_STATUS_MESSAGES.get(status, "")]
    if extra_message:
        messages.insert(0, extra_message)
    if status in {"data_source_error", "metric_missing", "partial_data", "not_found"}:
        summary = _STATUS_MESSAGES.get(status, summary)

    return InspectionReport(
        request_id=plan.request_id,
        task_type=plan.task_type,
        query_status=status,
        target=target_label(plan),
        scope=list(plan.metrics),
        time_range=_time_label(plan),
        metrics=rows,
        findings=findings,
        summary=summary,
        messages=[m for m in messages if m],
        sections=report_data.get("sections", []),
    )


def build_not_found_report(
    request_id: str,
    task_type: str,
    target: str,
    message: str,
) -> InspectionReport:
    return InspectionReport(
        request_id=request_id,
        task_type=task_type,  # type: ignore[arg-type]
        query_status="not_found",
        target=target,
        summary=message,
        messages=[_STATUS_MESSAGES["not_found"]],
    )


def build_error_report(
    request_id: str,
    task_type: str,
    target: str,
    message: str,
    status: QueryStatus = "no_capability",
    scope: list[str] | None = None,
) -> InspectionReport:
    return InspectionReport(
        request_id=request_id,
        task_type=task_type,  # type: ignore[arg-type]
        query_status=status,
        target=target,
        scope=scope or [],
        summary=message,
        messages=[_STATUS_MESSAGES.get(status, "")],
    )


__all__ = [
    "build_report",
    "build_not_found_report",
    "build_error_report",
    "compute_query_status",
    "target_label",
]
