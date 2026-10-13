from __future__ import annotations

from typing import Any

from agent.config import Thresholds
from agent.inspection.evaluator import evaluate_result
from agent.prometheus_client import PrometheusClient
from agent.utils import (
    apply_instance_filter,
    bind_prometheus_result_to_instance,
    instance_host,
    series_matches_instance,
)


def inspect_schema(target: str, metric_hint: str) -> dict[str, Any]:
    """生成 Skill 入参 JSON Schema，字段是 instance、metrics、time_range。"""
    return {
        "type": "object",
        "properties": {
            "instance": {
                "type": "string",
                "description": f"{target} 实例标识，例如主机 IP、redis6404、Pod 名。全集群巡检可为空。",
            },
            "metrics": {
                "type": "array",
                "items": {"type": "string"},
                "description": f"需要查询的指标 key 列表。{metric_hint} 为空则做该组件基础健康巡检。",
            },
            "time_range": {
                "type": "string",
                "description": "查询时间范围，例如 30m、1h、2h",
            },
        },
        "required": [],
    }


def labels_match_instance(metric: dict[str, Any] | None, instance: str | None) -> bool:
    """看这条时序的标签里有没有目标实例名。"""
    target = (instance or "").strip()
    if not target:
        return True
    labels = metric or {}
    if series_matches_instance(labels, target):
        return True
    needle = instance_host(target).lower()
    for key in ("instance", "pod", "pod_name", "service", "name", "addr", "job", "node", "container"):
        value = str(labels.get(key) or "").lower()
        if needle and needle in value:
            return True
    return False


def bind_result(result: dict[str, Any], instance: str | None) -> dict[str, Any]:
    """从查询结果里筛出属于指定实例的序列；筛不到就沿用 bind_prometheus_result_to_instance 的失败结果。"""
    target = (instance or "").strip()
    if not target:
        return result
    bound = bind_prometheus_result_to_instance(result, target)
    if bound.get("ok") and bound.get("series"):
        usable = [item for item in bound["series"] if not (item.get("metric") or {}).get("_note")]
        if usable:
            return bound
    series = [
        item
        for item in (result.get("series") or [])
        if labels_match_instance(item.get("metric"), target)
        and not (item.get("metric") or {}).get("_note")
    ]
    if series:
        copied = dict(result)
        copied["ok"] = True
        copied["series"] = series
        copied["series_count"] = len(series)
        copied["requested_instance"] = target
        copied.pop("error", None)
        return copied
    return bound


def _usable_series(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in (result.get("series") or [])
        if not (item.get("metric") or {}).get("_note")
    ]


def query_for_instance(
    prometheus: PrometheusClient,
    promql: str,
    instance: str | None,
    time_range: str,
) -> dict[str, Any]:
    """拼上 instance 过滤后查 Prometheus，再把结果绑回该实例。"""
    query = apply_instance_filter(promql, instance) if instance else promql
    return bind_result(prometheus.query_range(query, time_range), instance)


def probe_instance(
    prometheus: PrometheusClient,
    probes: list[str],
    instance: str | None,
    time_range: str,
) -> dict[str, Any]:
    """用一组探活 PromQL 确认实例在 Prometheus 里有没有数据。"""
    target = (instance or "").strip()
    if not target:
        return {"found": True, "result": None}
    last: dict[str, Any] = {}
    for promql in probes:
        result = query_for_instance(prometheus, promql, target, time_range)
        last = result
        if result.get("ok") and _usable_series(result):
            return {"found": True, "result": result}
    return {"found": False, "result": last}


def _metric_row(finding: Any, item: dict[str, Any], instance: str | None) -> dict[str, Any]:
    """把一条 Finding 收成报告对照用的指标行。"""
    labels = finding.labels or {}
    return {
        "metric_key": finding.metric_key,
        "metric": finding.metric_name,
        "instance": labels.get("instance") or labels.get("pod") or labels.get("name") or instance or "",
        "labels": labels,
        "current": finding.max_value if finding.max_value is not None else finding.latest,
        "latest": finding.latest,
        "avg": finding.avg_value,
        "max": finding.max_value,
        "unit": finding.unit,
        "threshold_warning": finding.warning,
        "threshold_critical": finding.critical,
        "severity": finding.severity,
        "risk": item.get("business_impact") or finding.error or "",
        "error": finding.error,
        "promql": finding.source_promql,
    }


def run_metric_queries(
    prometheus: PrometheusClient,
    catalog: list[dict[str, Any]],
    metric_keys: list[str],
    instance: str | None,
    time_range: str,
    thresholds: Thresholds,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按 metric_keys 查指标，返回已检查列表和超阈值异常列表。"""
    allowed = set(metric_keys)
    selected = [item for item in catalog if item["key"] in allowed]
    checked: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    for item in selected:
        result = query_for_instance(prometheus, item["promql"], instance, time_range)
        findings = evaluate_result(item, result, thresholds, purpose="primary")
        for finding in findings:
            row = _metric_row(finding, item, instance)
            checked.append(row)
            if finding.severity in {"warning", "critical", "error"}:
                anomalies.append(row)
    return checked, anomalies


def skill_payload(
    skill_name: str,
    target_type: str,
    instance: str | None,
    metrics: list[str],
    time_range: str,
    *,
    instance_found: bool,
    anomalies: list[dict[str, Any]] | None = None,
    checked: list[dict[str, Any]] | None = None,
    error: str | None = None,
    checked_count: int = 0,
) -> dict[str, Any]:
    """组装 Skill 的标准返回字典，报告层按这些字段渲染。"""
    target = (instance or "").strip()
    if not instance_found:
        return {
            "ok": False,
            "skill": skill_name,
            "target_type": target_type,
            "instance": target,
            "scope": metrics,
            "time_range": time_range,
            "instance_found": False,
            "message": "未找到对应实例",
            "anomalies": [],
            "checked": [],
            "checked_count": 0,
            "healthy": False,
            "error": error or f"未找到对应实例：{target or '<未指定>'}",
        }
    items = anomalies or []
    rows = checked or []
    return {
        "ok": error is None,
        "skill": skill_name,
        "target_type": target_type,
        "instance": target,
        "scope": metrics,
        "time_range": time_range,
        "instance_found": True,
        "message": "",
        "anomalies": items,
        "checked": rows,
        "checked_count": checked_count or len(rows),
        "healthy": error is None and not items,
        "error": error,
    }


def normalize_metrics(raw: Any, catalog: list[dict[str, Any]], fallback: list[str] | None = None) -> list[str]:
    """把传入的指标名对上 catalog 的 key；对不上或没传，就用 fallback。"""
    known = [item["key"] for item in catalog]
    if isinstance(raw, str):
        requested = [part.strip() for part in raw.replace("，", ",").split(",") if part.strip()]
    elif isinstance(raw, (list, tuple)):
        requested = [str(item).strip() for item in raw if str(item).strip()]
    else:
        requested = []
    unique: list[str] = []
    for key in requested:
        lowered = key.lower()
        matched = next((item for item in known if item == lowered or item == key), None)
        if matched and matched not in unique:
            unique.append(matched)
    if unique:
        return unique
    return list(fallback or known)
