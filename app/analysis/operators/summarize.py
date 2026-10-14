from __future__ import annotations

from typing import Any

from app.analysis.state import PipelineState
from app.domain.models import AnalysisOperation
from app.rules.engine import build_finding_from_event, risk_text


def _metric_finding(record: dict[str, Any]) -> dict[str, Any]:
    severity = record.get("severity") or "warning"
    return {
        "instance": record.get("resource_id", ""),
        "metric": record.get("metric_id", ""),
        "display_name": record.get("display_name", ""),
        "severity": severity,
        "value": record.get("value"),
        "unit": record.get("unit", "ratio"),
        "threshold": record.get("threshold_warning", ""),
        "observed_at": None,
        "started_at": None,
        "ended_at": None,
        "duration_seconds": None,
        "risk": risk_text(record.get("metric_id", ""), severity),
        "status": "active",
        "dimensions": record.get("dimensions", {}),
    }


def _metric_row(record: dict[str, Any]) -> dict[str, Any]:
    stats = record.get("stats") or {}
    return {
        "metric": record.get("metric_id", ""),
        "display_name": record.get("display_name", ""),
        "instance": record.get("resource_id", ""),
        "dimensions": record.get("dimensions", {}),
        "current": record.get("value"),
        "latest": stats.get("latest"),
        "avg": stats.get("avg"),
        "max": stats.get("max"),
        "p95": stats.get("p95"),
        "unit": record.get("unit", "ratio"),
        "threshold_warning": record.get("threshold_warning", ""),
        "threshold_critical": record.get("threshold_critical", ""),
        "severity": record.get("severity"),
        "risk": risk_text(record.get("metric_id", ""), record.get("severity") or "warning")
        if record.get("severity")
        else "",
        "status": record.get("collection_status", "ok"),
        "detail": record.get("error") or "",
    }


def _first_metric(records: list[dict[str, Any]]) -> str:
    for record in records:
        if record.get("metric_id"):
            return record["metric_id"]
    return ""


def run(state: PipelineState, op: AnalysisOperation) -> PipelineState:
    """把记录汇总为报告数据。"""
    records = state.records
    findings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    task = state.task_type

    if task in {"period_comparison"}:
        sections.append(
            {
                "title": "时段对比",
                "columns": ["实例", "指标", "时间段", "均值", "P95", "最大值", "变化", "结论"],
                "rows": [
                    [
                        record.get("resource_id", ""),
                        record.get("display_name") or record.get("metric_id", ""),
                        f"{record.get('before_period')} → {record.get('after_period')}",
                        _fmt(record.get("after", {}).get("avg")),
                        _fmt(record.get("after", {}).get("p95")),
                        _fmt(record.get("after", {}).get("max")),
                        _change(record.get("delta"), record.get("relative")),
                        record.get("verdict", ""),
                    ]
                    for record in records
                ],
            }
        )
        for record in records:
            if record.get("verdict") == "恶化":
                findings.append(
                    {
                        "instance": record.get("resource_id", ""),
                        "metric": record.get("metric_id", ""),
                        "display_name": record.get("display_name", ""),
                        "severity": "warning",
                        "value": record.get("delta"),
                        "unit": record.get("unit", "ratio"),
                        "threshold": "显著变化",
                        "observed_at": None,
                        "started_at": None,
                        "ended_at": None,
                        "duration_seconds": None,
                        "risk": risk_text(record.get("metric_id", ""), "warning"),
                        "status": "active",
                        "dimensions": record.get("dimensions", {}),
                    }
                )
        deteriorated = sum(1 for r in records if r.get("verdict") == "恶化")
        improved = sum(1 for r in records if r.get("verdict") == "改善")
        stable = sum(1 for r in records if r.get("verdict") == "稳定")
        summary = (
            f"{state.target_label} 时段对比：恶化 {deteriorated} 项，改善 {improved} 项，稳定 {stable} 项"
            if records
            else f"{state.target_label} 时段对比：数据不足，无法判断"
        )

    elif task == "trend_analysis":
        sections.append(
            {
                "title": "趋势分析",
                "columns": ["实例", "指标", "方向", "日均斜率", "增长率", "峰值", "持续风险"],
                "rows": [
                    [
                        record.get("resource_id", ""),
                        record.get("display_name") or record.get("metric_id", ""),
                        record.get("direction", ""),
                        _fmt(record.get("slope_per_day")),
                        _fmt(record.get("growth_rate")),
                        _fmt(record.get("peak")),
                        "是" if record.get("sustained_risk") else "否",
                    ]
                    for record in records
                ],
            }
        )
        for record in records:
            if record.get("sustained_risk"):
                findings.append(
                    {
                        "instance": record.get("resource_id", ""),
                        "metric": record.get("metric_id", ""),
                        "display_name": record.get("display_name", ""),
                        "severity": "warning",
                        "value": record.get("peak"),
                        "unit": record.get("unit", "ratio"),
                        "threshold": record.get("threshold_warning", ""),
                        "observed_at": None,
                        "started_at": None,
                        "ended_at": None,
                        "duration_seconds": None,
                        "risk": risk_text(record.get("metric_id", ""), "warning"),
                        "status": "active",
                        "dimensions": record.get("dimensions", {}),
                    }
                )
        summary = (
            f"{state.target_label} 趋势分析：{_trend_sentence(records)}"
            if records
            else f"{state.target_label} 趋势分析：数据不足，无法判断"
        )

    elif task == "historical_anomaly_summary":
        sections.append(
            {
                "title": "异常事件",
                "columns": ["实例", "指标", "峰值", "平均", "开始", "结束", "时长", "状态"],
                "rows": [
                    [
                        record.get("resource_id", ""),
                        record.get("display_name") or record.get("metric_id", ""),
                        _fmt(record.get("peak")),
                        _fmt(record.get("avg")),
                        _dt(record.get("started_at")),
                        _dt(record.get("ended_at")),
                        _duration(record.get("duration_seconds")),
                        record.get("status", ""),
                    ]
                    for record in records
                ],
            }
        )
        findings = [build_finding_from_event(record).model_dump() for record in records]
        active = sum(1 for r in records if r.get("status") == "active")
        recovered = sum(1 for r in records if r.get("status") == "recovered")
        unknown = sum(1 for r in records if r.get("status") == "unknown")
        summary = (
            f"{state.target_label} 异常清单：共 {len(records)} 个事件，进行中 {active}，已恢复 {recovered}，无法判断 {unknown}"
            if records
            else f"{state.target_label} 在 {state.time_range_label} 内未发现越阈值异常事件"
        )

    elif task == "ranking_query":
        rows = [_metric_row(record) for record in records]
        findings = [_metric_finding(r) for r in records if r.get("severity")]
        metric = _first_metric(records)
        summary = (
            f"{state.target_label} {metric} 排行：返回 {len(records)} 台机器"
            if records
            else f"{state.target_label} {metric} 排行：无数据"
        )

    else:  # instant_inspection / threshold_filter
        rows = [_metric_row(record) for record in records]
        findings = [_metric_finding(r) for r in records if r.get("severity")]
        if task == "threshold_filter":
            summary = (
                f"{state.target_label} 命中 {len(records)} 台机器"
                if records
                else f"{state.target_label} 没有命中的机器"
            )
        elif findings:
            summary = f"{state.target_label} 发现 {len(findings)} 项异常"
        elif records:
            summary = f"{state.target_label} 在已检查指标范围内健康"
        else:
            summary = f"{state.target_label} 缺少可比对数据，无法判断"

    state.report = {
        "task_type": task,
        "summary": summary,
        "findings": findings,
        "rows": rows,
        "sections": sections,
    }
    return state


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _dt(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except AttributeError:
        return str(value)


def _duration(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)):
        return "-"
    minutes = seconds / 60.0
    if minutes >= 60:
        return f"{minutes / 60:.1f}h"
    return f"{minutes:.1f}m"


def _change(delta: Any, relative: Any) -> str:
    if delta is None:
        return "-"
    text = f"{delta:+.4g}"
    if isinstance(relative, (int, float)):
        text += f" ({relative * 100:+.1f}%)"
    return text


def _trend_sentence(records: list[dict[str, Any]]) -> str:
    rising = sum(1 for r in records if r.get("direction") == "上升")
    falling = sum(1 for r in records if r.get("direction") == "下降")
    flat = sum(1 for r in records if r.get("direction") == "平稳")
    risks = [r for r in records if r.get("sustained_risk")]
    base = f"上升 {rising} 项，下降 {falling} 项，平稳 {flat} 项"
    if risks:
        base += f"，其中 {len(risks)} 项存在持续高负载风险"
    return base


__all__ = ["run"]
