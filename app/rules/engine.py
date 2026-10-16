from __future__ import annotations

from datetime import datetime
from typing import Any

from app.analysis.stats import linear_slope, percentile, summarize_values
from app.domain.models import Finding, MetricDefinition, MetricSeries, ThresholdRule
from app.rules.loader import AnomalyPolicy, Policies, TrendPolicy


_UNIT_SUFFIX = {
    "percent": "%",
    "seconds": "s",
    "bytes": "B",
    "count": "",
    "ratio": "",
}


def format_threshold(rule: ThresholdRule | None, unit: str) -> str:
    if rule is None:
        return ""
    symbol = {"gt": ">", "lt": "<", "ge": ">=", "le": "<="}[rule.comparison]
    return f"{symbol} {rule.value:g}{_UNIT_SUFFIX.get(unit, '')}"


def severity_of(value: float | None, definition: MetricDefinition) -> str | None:
    """返回 warning / critical，critical 优先。"""
    hits = definition.threshold_violations(value)
    if "critical" in hits:
        return "critical"
    if "warning" in hits:
        return "warning"
    return None


def _is_violating(value: float | None, definition: MetricDefinition) -> bool:
    warning = definition.thresholds.get("warning")
    if warning is None or value is None:
        return False
    return warning.violated(value)


def _gap_multiplier_seconds(series: MetricSeries, policy: AnomalyPolicy) -> float:
    step = series.source_time_range.step_seconds or 60
    return max(step * policy.max_gap_multiplier, step + 1)


def detect_events(
    series: MetricSeries,
    definition: MetricDefinition,
    policy: AnomalyPolicy,
) -> list[dict[str, Any]]:
    """把连续越阈值的样本合并为异常事件。数据缺口标记 unknown。"""
    points: list[tuple[datetime, float | None]] = list(zip(series.timestamps, series.values))
    if not points:
        return []
    gap_limit = _gap_multiplier_seconds(series, policy)
    warning = format_threshold(definition.thresholds.get("warning"), definition.unit)
    critical = format_threshold(definition.thresholds.get("critical"), definition.unit)

    events: list[dict[str, Any]] = []
    index = 0
    total = len(points)
    while index < total:
        if not _is_violating(points[index][1], definition):
            index += 1
            continue
        start_index = index
        last_violation = index
        recovered = True
        gap_seen = False
        recover_run = 0
        cursor = index
        while cursor < total:
            current_value = points[cursor][1]
            if cursor > start_index:
                delta = (points[cursor][0] - points[cursor - 1][0]).total_seconds()
                if delta > gap_limit:
                    gap_seen = True
            if _is_violating(current_value, definition):
                last_violation = cursor
                recover_run = 0
            else:
                recover_run += 1
                if recover_run >= max(1, policy.recover_samples):
                    recovered = True
                    break
            cursor += 1
        if cursor >= total:
            recovered = False

        segment = points[start_index : last_violation + 1]
        violating_values = [v for _, v in segment if v is not None]
        if len(violating_values) >= max(1, policy.min_consecutive_samples):
            stats = summarize_values(violating_values)
            started_at = segment[0][0]
            ended_at = segment[-1][0]
            duration = (ended_at - started_at).total_seconds()
            if gap_seen:
                status = "unknown"
            elif recovered:
                status = "recovered"
            else:
                status = "active"
            comparison = (
                definition.thresholds.get("warning").comparison
                if definition.thresholds.get("warning")
                else "gt"
            )
            peak = min(violating_values) if comparison == "lt" else max(violating_values)
            severity = "critical" if "critical" in definition.threshold_violations(peak) else "warning"
            events.append(
                {
                    "kind": "anomaly_event",
                    "metric_id": definition.metric_id,
                    "display_name": definition.display_name,
                    "unit": definition.unit,
                    "resource_id": series.resource_id,
                    "dimensions": dict(series.dimensions),
                    "peak": peak,
                    "avg": stats["avg"],
                    "p95": stats["p95"],
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "duration_seconds": duration,
                    "status": status,
                    "severity": severity,
                    "threshold_warning": warning,
                    "threshold_critical": critical,
                    "sample_count": len(violating_values),
                }
            )
        index = last_violation + 1
    return events


def significant_change(
    metric_id: str,
    before: float | None,
    after: float | None,
    policies: Policies,
) -> dict[str, Any]:
    """按绝对与相对双条件判定显著性。"""
    policy = policies.significance_for(metric_id)
    if before is None or after is None:
        return {
            "delta": None,
            "relative": None,
            "significant": False,
            "verdict": "无法判断",
        }
    delta = after - before
    relative = delta / abs(before) if before else None
    significant = abs(delta) >= policy.min_absolute_change and (
        relative is None or abs(relative) >= policy.min_relative_change
    )
    return {
        "delta": round(delta, 4),
        "relative": round(relative, 4) if relative is not None else None,
        "significant": significant,
        "verdict": "变化" if significant else "稳定",
    }


def verdict_label(metric_id: str, before: float | None, after: float | None, comparison: str, policies: Policies) -> str:
    change = significant_change(metric_id, before, after, policies)
    if not change["significant"]:
        return "稳定" if before is not None and after is not None else "无法判断"
    delta = change["delta"] or 0.0
    higher_is_worse = comparison == "gt"
    if higher_is_worse:
        return "恶化" if delta > 0 else "改善"
    return "改善" if delta > 0 else "恶化"


def trend_stats(
    series: MetricSeries,
    definition: MetricDefinition,
    policy: TrendPolicy,
) -> dict[str, Any]:
    """计算趋势方向、斜率、峰值和持续风险。"""
    numeric = [(t, v) for t, v in zip(series.timestamps, series.values) if isinstance(v, (int, float))]
    if len(numeric) < 2:
        return {
            "slope": 0.0,
            "slope_per_day": 0.0,
            "growth_rate": None,
            "peak": numeric[0][1] if numeric else None,
            "sustained_ratio": 0.0,
            "direction": "数据不足",
            "sustained_risk": False,
        }
    epochs = [t.timestamp() for t, _ in numeric]
    values = [float(v) for _, v in numeric]
    slope = linear_slope(epochs, values)
    first = values[0]
    growth = (values[-1] - first) / abs(first) if first else None
    warning = definition.thresholds.get("warning")
    if warning is not None:
        above = sum(1 for v in values if warning.violated(v))
        sustained_ratio = above / len(values)
    else:
        sustained_ratio = 0.0
    per_day = slope * 86400
    epsilon = policy.slope_epsilon
    if per_day > epsilon:
        direction = "上升"
    elif per_day < -epsilon:
        direction = "下降"
    else:
        direction = "平稳"
    return {
        "slope": round(slope, 8),
        "slope_per_day": round(per_day, 6),
        "growth_rate": round(growth, 4) if growth is not None else None,
        "peak": max(values),
        "sustained_ratio": round(sustained_ratio, 4),
        "direction": direction,
        "sustained_risk": sustained_ratio >= policy.sustained_ratio,
    }


def risk_text(metric_id: str, severity: str) -> str:
    mapping = {
        "cpu": "CPU 持续高负载可能影响业务响应时间",
        "memory": "内存使用率过高可能触发 OOM 或频繁换页",
        "disk": "磁盘使用率过高可能导致写入失败或服务不可用",
        "availability": "实例不可用，业务请求可能失败",
    }
    return mapping.get(metric_id, f"{metric_id} 指标超出阈值")


def build_finding_from_event(event: dict[str, Any]) -> Finding:
    return Finding(
        instance=event.get("resource_id", ""),
        metric=event.get("metric_id", ""),
        display_name=event.get("display_name", ""),
        severity=event.get("severity", "warning"),
        value=event.get("peak"),
        unit=event.get("unit", "ratio"),
        threshold=event.get("threshold_warning", ""),
        observed_at=event.get("ended_at"),
        started_at=event.get("started_at"),
        ended_at=event.get("ended_at"),
        duration_seconds=event.get("duration_seconds"),
        risk=risk_text(event.get("metric_id", ""), event.get("severity", "warning")),
        status=event.get("status", "unknown"),
        dimensions=event.get("dimensions", {}),
    )


__all__ = [
    "format_threshold",
    "severity_of",
    "detect_events",
    "significant_change",
    "verdict_label",
    "trend_stats",
    "risk_text",
    "build_finding_from_event",
]
