from __future__ import annotations

import json
from typing import Any

from app.domain.models import InspectionReport, MetricRow


_UNIT_SUFFIX = {
    "percent": "%",
    "seconds": "s",
    "bytes": "B",
    "count": "",
    "ratio": "",
}


def _fmt(value: Any, unit: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        text = f"{value:.4g}"
    else:
        text = str(value)
    suffix = _UNIT_SUFFIX.get(unit, "")
    return f"{text}{suffix}" if suffix else text


def _row_line(row: MetricRow) -> str:
    dims = ",".join(f"{k}={v}" for k, v in row.dimensions.items() if k not in {"instance"})
    parts = [
        f"{row.display_name or row.metric}",
        f"当前 {_fmt(row.current, row.unit)}",
        f"均值 {_fmt(row.avg, row.unit)}",
        f"峰值 {_fmt(row.max, row.unit)}",
    ]
    if row.threshold_warning:
        parts.append(f"阈值 {row.threshold_warning}")
    if row.severity:
        parts.append(f"级别 {row.severity}")
    if row.status != "ok":
        parts.append(f"状态 {row.status}")
    if dims:
        parts.append(dims)
    return f"{row.instance} " + "，".join(parts)


def render_text(report: InspectionReport) -> str:
    lines: list[str] = []
    lines.append("===== 巡检报告 =====")
    lines.append(f"任务类型: {report.task_type}")
    lines.append(f"查询状态: {report.query_status}")
    lines.append(f"目标: {report.target}")
    if report.time_range:
        lines.append(f"时间范围: {report.time_range}")
    if report.scope:
        lines.append(f"指标范围: {', '.join(report.scope)}")
    lines.append(f"摘要: {report.summary}")
    lines.append("")

    if report.findings:
        lines.append("发现的问题:")
        for finding in report.findings:
            value = _fmt(finding.value, finding.unit)
            threshold = f"（阈值 {finding.threshold}）" if finding.threshold else ""
            span = ""
            if finding.started_at and finding.ended_at:
                span = f" [{finding.started_at:%Y-%m-%d %H:%M} ~ {finding.ended_at:%Y-%m-%d %H:%M}]"
            lines.append(
                f"- [{finding.severity}] {finding.instance} {finding.display_name or finding.metric}："
                f"值 {value}{threshold}{span} {finding.risk}"
            )
        lines.append("")

    if report.metrics:
        lines.append("指标对照:")
        for row in report.metrics:
            lines.append("- " + _row_line(row))
        lines.append("")

    for section in report.sections:
        title = section.get("title", "")
        columns = section.get("columns", [])
        rows = section.get("rows", [])
        if not rows:
            continue
        lines.append(f"{title}:")
        widths = _column_widths(columns, rows)
        lines.append("  " + " | ".join(_pad(str(col), widths[i]) for i, col in enumerate(columns)))
        lines.append("  " + "-+-".join("-" * w for w in widths))
        for row in rows:
            lines.append(
                "  "
                + " | ".join(
                    _pad(str(cell), widths[i]) for i, cell in enumerate(row[: len(columns)])
                )
            )
        lines.append("")

    if report.messages:
        lines.append("说明:")
        for message in report.messages:
            lines.append(f"- {message}")

    lines.append("===== 报告结束 =====")
    return "\n".join(lines)


def _column_widths(columns: list[str], rows: list[list[Any]]) -> list[int]:
    widths = [len(str(col)) for col in columns]
    for row in rows:
        for index in range(len(columns)):
            cell = str(row[index]) if index < len(row) else ""
            widths[index] = max(widths[index], len(cell))
    return widths


def _pad(text: str, width: int) -> str:
    # 中文按全角宽度粗略对齐。
    display = sum(2 if ord(c) > 0x2E80 else 1 for c in text)
    padding = max(0, width - display)
    return text + " " * padding


def render_markdown(report: InspectionReport) -> str:
    lines: list[str] = []
    lines.append(f"# 巡检报告：{report.target}")
    lines.append("")
    lines.append(f"- 任务类型：{report.task_type}")
    lines.append(f"- 查询状态：{report.query_status}")
    if report.time_range:
        lines.append(f"- 时间范围：{report.time_range}")
    lines.append(f"- 摘要：{report.summary}")
    lines.append("")
    if report.findings:
        lines.append("## 发现的问题")
        for finding in report.findings:
            lines.append(
                f"- **{finding.severity}** {finding.instance} "
                f"{finding.display_name or finding.metric}：{_fmt(finding.value, finding.unit)} "
                f"（阈值 {finding.threshold}）"
            )
        lines.append("")
    if report.metrics:
        lines.append("## 指标对照")
        lines.append("| 实例 | 指标 | 当前 | 均值 | 峰值 | 阈值 | 级别 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for row in report.metrics:
            lines.append(
                f"| {row.instance} | {row.display_name or row.metric} | "
                f"{_fmt(row.current, row.unit)} | {_fmt(row.avg, row.unit)} | "
                f"{_fmt(row.max, row.unit)} | {row.threshold_warning} | {row.severity or ''} |"
            )
        lines.append("")
    for section in report.sections:
        if not section.get("rows"):
            continue
        lines.append(f"## {section.get('title', '')}")
        columns = section.get("columns", [])
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("| " + " | ".join("---" for _ in columns) + " |")
        for row in section.get("rows", []):
            lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
        lines.append("")
    return "\n".join(lines)


def to_json(report: InspectionReport) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)


__all__ = ["render_text", "render_markdown", "to_json"]
