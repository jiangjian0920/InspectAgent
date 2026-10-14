from __future__ import annotations

import re

from app.nlu.schema import ModelIntent, ModelPeriod, ModelTarget
from app.domain.models import AnalysisOperation


_IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?\b")
_NAMED_RE = re.compile(r"(?:巡检|查看|查询|检查)\s*([A-Za-z][A-Za-z0-9_.\-]{1,63})", re.IGNORECASE)

_METRIC_HINTS = {
    "cpu": ("cpu", "处理器", "cpu使用率"),
    "memory": ("内存", "memory", "mem"),
    "disk": ("磁盘", "硬盘", "文件系统", "磁盘使用", "disk"),
    "availability": ("可用性", "存活", "在线", "availability", "探活"),
}

_DUR_RE = re.compile(r"(\d+)\s*(天|日|小时|分钟|周)")


def _detect_metrics(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for metric, hints in _METRIC_HINTS.items():
        if any(hint in lowered or hint in text for hint in hints):
            if metric not in found:
                found.append(metric)
    return found


def _detect_instance(text: str) -> str | None:
    match = _IP_RE.search(text)
    if match:
        return match.group(1)
    named = _NAMED_RE.search(text)
    if named:
        token = named.group(1)
        if token.lower() not in {"redis", "kafka", "server", "host", "cpu", "memory"}:
            return token
    return None


def _threshold_operation(text: str) -> AnalysisOperation | None:
    match = re.search(r"(超过|大于|高于|高于|超过|高于|≥|>=|>)\s*(\d+(?:\.\d+)?)\s*%?", text)
    if match:
        return AnalysisOperation(
            type="filter", field="value", comparison="gt", threshold=float(match.group(2))
        )
    match = re.search(r"(小于|低于|少于|≤|<=|<)\s*(\d+(?:\.\d+)?)\s*%?", text)
    if match:
        return AnalysisOperation(
            type="filter", field="value", comparison="lt", threshold=float(match.group(2))
        )
    return None


def parse(instruction: str) -> ModelIntent:
    """无模型时的规则回退解析，输出与 GLM 相同的 ModelIntent。"""
    text = (instruction or "").strip()
    lowered = text.lower()
    instance = _detect_instance(text)
    metrics = _detect_metrics(text)
    scope = "instance" if instance else "instance"

    wants_all = any(k in text for k in ("全部", "所有", "全集群", "整个集群", "全量"))
    if wants_all:
        scope = "all"
        instance = None

    task = "instant_inspection"
    periods: list[ModelPeriod] = []
    operations: list[AnalysisOperation] = []
    time_range_value = ""

    comparison = any(k in text for k in ("对比", "比较", "compare", "环比"))
    if comparison:
        task = "period_comparison"
        periods = [
            ModelPeriod(name="today", start="today 00:00", end="now"),
            ModelPeriod(name="yesterday", start="yesterday 00:00", end="yesterday 23:59:59"),
        ]
        scope = "instance" if instance else "all"
    elif any(k in text for k in ("异常", "告警", "报警")):
        task = "historical_anomaly_summary"
        scope = "all" if (wants_all or not instance) else "instance"
    elif any(k in text for k in ("趋势", "trend")):
        task = "trend_analysis"
        scope = "instance" if instance else "all"
    elif any(k in text for k in ("最高", "top", "排行", "排序", "排名")):
        task = "ranking_query"
        scope = "all"
        operations = [
            AnalysisOperation(type="aggregate", function="avg", group_by=["instance"]),
            AnalysisOperation(type="sort", field="value", direction="desc"),
            AnalysisOperation(type="limit", count=10),
            AnalysisOperation(type="summarize"),
        ]
    else:
        threshold_op = _threshold_operation(text)
        if threshold_op is not None:
            task = "threshold_filter"
            scope = "all"
            operations = [
                AnalysisOperation(type="aggregate", function="avg", group_by=["instance"]),
                threshold_op,
                AnalysisOperation(type="sort", field="value", direction="desc"),
                AnalysisOperation(type="summarize"),
            ]

    if task in {"historical_anomaly_summary", "trend_analysis"}:
        match = _DUR_RE.search(text)
        if match:
            time_range_value = f"{match.group(1)}{match.group(2)}"

    return ModelIntent(
        task_type=task,  # type: ignore[arg-type]
        target=ModelTarget(type="server", instance=instance, scope=scope),  # type: ignore[arg-type]
        metrics=metrics,
        time_range={"type": "relative", "value": time_range_value} if time_range_value else None,
        periods=periods,
        operations=operations,
    )


__all__ = ["parse"]
