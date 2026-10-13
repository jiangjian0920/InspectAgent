from __future__ import annotations

import re
from typing import Any

from agent.config import Thresholds
from agent.inspection.models import Finding
from agent.utils import safe_float


def normalize_promql(promql: str) -> str:
    return re.sub(r"\s+", " ", (promql or "").strip())


def resolve_metric_key(promql: str, catalog: list[dict[str, Any]], metric_key: str | None = None) -> str | None:
    if metric_key:
        return metric_key
    normalized = normalize_promql(promql)
    for item in catalog:
        if normalize_promql(item.get("promql", "")) == normalized:
            return str(item["key"])
        for follow in item.get("followups") or []:
            if normalize_promql(follow.get("promql", "")) == normalized:
                return str(follow["key"])
    return _heuristic_key(normalized)


def _heuristic_key(query: str) -> str | None:
    rules: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
        ("cpu", ("node_cpu_seconds_total", "idle", "100 -"), ()),
        ("cpu_iowait", ("node_cpu_seconds_total", "iowait"), ()),
        ("memory", ("node_memory_MemAvailable_bytes", "MemTotal"), ()),
        ("disk", ("node_filesystem_avail_bytes",), ()),
        ("disk_io", ("node_disk_io_time_seconds_total",), ()),
        ("load", ("node_load1",), ("node_load5", "node_load15")),
        ("network_rx", ("node_network_receive_bytes_total",), ()),
        ("network_tx", ("node_network_transmit_bytes_total",), ()),
    ]
    for key, must, must_not in rules:
        if all(token in query for token in must) and not any(token in query for token in must_not):
            return key
    return None


def _label_text(metric: dict[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for name in ("instance", "job", "device", "mountpoint", "fstype", "pod", "namespace", "container", "name"):
        value = metric.get(name)
        if value:
            labels[name] = str(value)
    return labels


def evaluate_result(
    metric_def: dict[str, Any],
    result: dict[str, Any],
    thresholds: Thresholds,
    purpose: str = "primary",
) -> list[Finding]:
    """拿一条 Prometheus 结果对照阈值，生成 Finding 列表。"""
    findings: list[Finding] = []
    warning = _threshold(thresholds, metric_def.get("warning_attr"))
    critical = _threshold(thresholds, metric_def.get("critical_attr"))
    compare = str(metric_def.get("compare") or "gte")
    common = {
        "metric_key": str(metric_def["key"]),
        "metric_name": str(metric_def["name"]),
        "meaning": str(metric_def.get("meaning") or ""),
        "unit": str(metric_def.get("unit") or ""),
        "source_promql": str(result.get("promql") or metric_def.get("promql") or ""),
        "warning": warning,
        "critical": critical,
        "purpose": purpose,
    }
    if not result.get("ok"):
        findings.append(
            Finding(
                labels={},
                latest=None,
                max_value=None,
                avg_value=None,
                severity="error",
                error=str(result.get("error") or "Prometheus 查询失败"),
                **common,
            )
        )
        return findings

    series = result.get("series") or []
    usable = [item for item in series if not (item.get("metric") or {}).get("_note")]
    if not usable:
        findings.append(
            Finding(
                labels={},
                latest=None,
                max_value=None,
                avg_value=None,
                severity="unknown",
                error="查询成功但没有可用时序数据，未编造数值",
                **common,
            )
        )
        return findings

    for item in usable:
        latest = safe_float(item.get("latest"))
        max_value = safe_float(item.get("max"))
        avg_value = safe_float(item.get("avg"))
        peak = max_value if max_value is not None else latest
        severity = _severity(peak, warning, critical, purpose, compare)
        findings.append(
            Finding(
                labels=_label_text(item.get("metric") or {}),
                latest=latest,
                max_value=max_value,
                avg_value=avg_value,
                severity=severity,
                error=None,
                **common,
            )
        )
    return findings


def _threshold(thresholds: Thresholds, attr: str | None) -> float | None:
    if not attr:
        return None
    return float(getattr(thresholds, attr))


def _severity(
    value: float | None,
    warning: float | None,
    critical: float | None,
    purpose: str,
    compare: str = "gte",
) -> str:
    if purpose != "primary" or warning is None or critical is None:
        return "info"
    if value is None:
        return "unknown"
    if compare == "lte":
        if value <= critical:
            return "critical"
        if value <= warning:
            return "warning"
        return "ok"
    if value >= critical:
        return "critical"
    if value >= warning:
        return "warning"
    return "ok"
