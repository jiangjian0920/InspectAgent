from __future__ import annotations

from datetime import datetime
from typing import Any

from agent.intent import InspectionIntent


_SEVERITY_TEXT = {
    "critical": "严重",
    "warning": "警告",
    "error": "采集失败",
    "ok": "正常",
    "unknown": "未知",
}

_TARGET_TEXT = {
    "server": "服务器主机",
    "redis": "Redis",
    "kafka": "Kafka",
    "k8s": "Kubernetes",
}


def build_inspection_report(
    intent: InspectionIntent,
    results: list[dict[str, Any]],
    extra_suggestions: str = "",
) -> str:
    """把意图和 Skill 结果拼成给人看的巡检报告。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "巡检报告",
        f"- 用户指令：{intent.user_input}",
        f"- 时间范围：{intent.time_range}",
        f"- 巡检范围：{_scope_text(intent)}",
        f"- 生成时间：{now}",
        "",
    ]

    if not results:
        lines.append("未找到对应实例")
        return "\n".join(lines)

    missing = [item for item in results if not item.get("instance_found")]
    found = [item for item in results if item.get("instance_found")]

    for item in missing:
        instance = item.get("instance") or "未指定实例"
        target = _TARGET_TEXT.get(str(item.get("target_type") or ""), item.get("skill") or "巡检对象")
        lines.append(f"未找到对应实例：{target} / {instance}")
        if item.get("error") and "未找到对应实例" not in str(item.get("error")):
            lines.append(f"- 详情：{item.get('error')}")

    for item in found:
        lines.extend(_render_checked(item))

    if extra_suggestions.strip():
        lines.append("")
        lines.append("补充建议：")
        for raw in extra_suggestions.strip().splitlines():
            text = raw.strip()
            if text:
                lines.append(f"- {text}")
    lines.append("- Agent 只做查询分析，不会自动修改服务器或集群。变更操作需要人工确认后执行。")
    return "\n".join(lines)


def _scope_text(intent: InspectionIntent) -> str:
    """生成报告头部的巡检范围文案。"""
    parts: list[str] = []
    for item in intent.targets:
        target = _TARGET_TEXT.get(str(item.get("target_type") or ""), str(item.get("skill")))
        instance = item.get("instance") or "未指定实例"
        metrics = item.get("metrics") or []
        metric_text = "、".join(str(key) for key in metrics) if metrics else "基础健康巡检"
        parts.append(f"{target}/{instance}/{metric_text}")
    return "；".join(parts) or "未解析到巡检对象"


def _render_checked(item: dict[str, Any]) -> list[str]:
    """列出已检查指标的当前值、均值、峰值和阈值，方便对照。"""
    instance = item.get("instance") or "未指定实例"
    target = _TARGET_TEXT.get(str(item.get("target_type") or ""), item.get("skill") or "巡检对象")
    scope = "、".join(item.get("scope") or []) or "基础健康巡检"
    status = "健康" if item.get("healthy") else "存在异常"
    lines = [f"{target} 实例 {instance}，巡检范围：{scope}，结论：{status}"]
    rows = item.get("checked") or item.get("anomalies") or []
    if not rows:
        lines.append("- 未采集到可对照的指标数值。")
        return lines
    for row in rows:
        lines.append(_render_metric_line(row))
    return lines


def _render_metric_line(row: dict[str, Any]) -> str:
    """单条指标：当前值对照警告/严重阈值。"""
    severity_key = str(row.get("severity") or "ok")
    if severity_key not in {"warning", "critical", "error", "unknown"}:
        severity_key = "ok"
    severity = _SEVERITY_TEXT.get(severity_key, severity_key)
    metric = row.get("metric") or row.get("metric_key")
    unit = row.get("unit") or ""
    if row.get("severity") == "error":
        return f"- [{severity}] {metric}：{row.get('error') or '查询失败'}。未编造该指标数值。"
    current = _fmt(row.get("current"), unit)
    latest = _fmt(row.get("latest"), unit)
    avg = _fmt(row.get("avg"), unit)
    peak = _fmt(row.get("max"), unit)
    warning = _fmt(row.get("threshold_warning"), unit)
    critical = _fmt(row.get("threshold_critical"), unit)
    line = (
        f"- [{severity}] {metric}：当前 {current}，最新 {latest}，均值 {avg}，峰值 {peak}"
        f"；警告阈值 {warning}，严重阈值 {critical}"
    )
    if severity_key in {"warning", "critical"}:
        risk = row.get("risk") or "存在风险"
        line += f"。风险：{risk}"
    return line


def _fmt(value: Any, unit: str) -> str:
    if value is None:
        return "无"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    rendered = f"{number:.2f}".rstrip("0").rstrip(".")
    return f"{rendered}{unit}"
