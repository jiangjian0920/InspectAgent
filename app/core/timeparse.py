from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.domain.models import NamedTimeRange, TimeRange


_DURATION_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds|秒|m|min|mins|minute|minutes|分钟|分|"
    r"h|hr|hrs|hour|hours|小时|时|d|day|days|天|w|week|weeks|周)\s*$",
    re.IGNORECASE,
)

_UNIT_SECONDS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "秒": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60, "分钟": 60, "分": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600, "小时": 3600, "时": 3600,
    "d": 86400, "day": 86400, "days": 86400, "天": 86400,
    "w": 604800, "week": 604800, "weeks": 604800, "周": 604800,
}

_CHINESE_RELATIVE_RE = re.compile(r"^(?:最近|近|过去|前)\s*(\d+)\s*(天|日|小时|分钟|周)$")


def duration_seconds(text: str) -> float | None:
    match = _DURATION_RE.match(text or "")
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    return value * _UNIT_SECONDS.get(unit, 60)


def chinese_relative_days(text: str) -> float | None:
    match = _CHINESE_RELATIVE_RE.match((text or "").strip())
    if not match:
        return None
    value = float(match.group(1))
    return value * _UNIT_SECONDS.get(match.group(2), 86400)


def local_midnight(moment: datetime) -> datetime:
    local = moment.astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def clamp_step(duration: float, base_step: int, max_points: int = 200) -> int:
    if duration <= 0:
        return max(1, base_step)
    return max(1, base_step, int(duration / max_points))


def _endpoint(expr: str, now: datetime) -> datetime:
    text = (expr or "").strip().lower()
    if text in {"", "now"}:
        return now
    if text in {"today", "今日", "今天", "today 00:00", "today 0:00"}:
        return local_midnight(now)
    if text in {"yesterday", "昨日", "昨天", "yesterday 00:00"}:
        return local_midnight(now) - timedelta(days=1)
    if text in {"yesterday 23:59:59", "yesterday 23:59"}:
        return local_midnight(now) - timedelta(seconds=1)
    if text in {"today 23:59:59", "today 23:59"}:
        return local_midnight(now) + timedelta(days=1) - timedelta(seconds=1)
    seconds = duration_seconds(text)
    if seconds is not None:
        return now - timedelta(seconds=seconds)
    days = chinese_relative_days(text)
    if days is not None:
        return now - timedelta(seconds=days)
    try:
        parsed = datetime.fromisoformat((expr or "").strip())
    except ValueError as exc:
        raise ValueError(f"无法解析时间表达式: {expr}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def resolve_relative_range(
    expr: str,
    now: datetime,
    default_seconds: float,
    base_step: int,
) -> tuple[TimeRange, str]:
    """把单个相对时间描述解析为绝对时间窗口。"""
    text = (expr or "").strip()
    if not text:
        seconds = default_seconds
        label = f"{int(default_seconds)}s"
    else:
        days = chinese_relative_days(text)
        if days is not None:
            seconds = days
            label = text
        else:
            parsed = duration_seconds(text)
            if parsed is None:
                raise ValueError(f"无法解析时间范围: {expr}")
            seconds = parsed
            label = text
    end = now
    start = now - timedelta(seconds=seconds)
    step = clamp_step((end - start).total_seconds(), base_step)
    return TimeRange(start=start, end=end, step_seconds=step), label


def resolve_named_period(
    period: NamedTimeRange,
    now: datetime,
    base_step: int,
) -> TimeRange:
    """解析命名时间段，start/end 支持 now/today/yesterday/相对/ISO。"""
    start = _endpoint(period.start, now)
    end = _endpoint(period.end, now)
    if end <= start:
        raise ValueError(f"时间段 {period.name} 的结束时间必须晚于开始时间")
    step = clamp_step((end - start).total_seconds(), base_step)
    return TimeRange(start=start, end=end, step_seconds=step)


__all__ = [
    "duration_seconds",
    "chinese_relative_days",
    "local_midnight",
    "clamp_step",
    "resolve_relative_range",
    "resolve_named_period",
]
