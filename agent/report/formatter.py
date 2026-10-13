from __future__ import annotations

from datetime import datetime


def render_report(content: str) -> str:
    return (content or "").strip() or "未能生成报告。"


def format_fallback_report(user_input: str, error: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return (
        "巡检报告\n"
        f"- 用户指令：{user_input}\n"
        f"- 生成时间：{now}\n"
        f"- 未能完成巡检：{error}\n"
        "- 未编造监控数据。变更操作需要人工确认后执行。"
    )
