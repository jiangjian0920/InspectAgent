from __future__ import annotations

from datetime import timedelta

from app.core.config import Settings
from app.core.errors import PlanValidationError
from app.domain.models import NamedTimeRange, TimeRange
from app.core.timeparse import resolve_named_period


_COMPARABLE_TOLERANCE = 0.05


def _trim_to_length(window: TimeRange, length_seconds: float) -> TimeRange:
    new_start = window.end - timedelta(seconds=length_seconds)
    if new_start < window.start:
        new_start = window.start
    return window.model_copy(update={"start": new_start})


def resolve_periods(
    periods: list[NamedTimeRange],
    settings: Settings,
    now,
) -> list[tuple[str, TimeRange]]:
    """解析并校验两个时间段：不重叠、同口径（截断到等长）、不超最大范围。"""
    if len(periods) != 2:
        raise PlanValidationError("时段对比需要两个时间段")
    resolved: list[tuple[str, TimeRange]] = []
    for period in periods:
        window = resolve_named_period(period, now, settings.default_step_seconds)
        _check_max_range(window, settings, period.name)
        resolved.append((period.name, window))

    (first_name, first), (second_name, second) = resolved
    shorter = min(first.duration_seconds, second.duration_seconds)
    longer = max(first.duration_seconds, second.duration_seconds)
    if shorter <= 0:
        raise PlanValidationError("时间段长度必须大于 0")
    # 长度不一致时截断到较短窗口，保证同口径比较。
    if longer - shorter > longer * _COMPARABLE_TOLERANCE:
        first = _trim_to_length(first, shorter)
        second = _trim_to_length(second, shorter)

    overlap = max(first.start, second.start) < min(first.end, second.end)
    if overlap:
        raise PlanValidationError("两个时间段不允许重叠")
    return [(first_name, first), (second_name, second)]


def check_range(range_: TimeRange, settings: Settings, label: str = "查询范围") -> None:
    _check_max_range(range_, settings, label)


def _check_max_range(range_: TimeRange, settings: Settings, label: str) -> None:
    max_seconds = settings.max_time_range_days * 86400
    if range_.duration_seconds > max_seconds:
        raise PlanValidationError(
            f"{label} 超过最大时间范围 {settings.max_time_range_days} 天"
        )
    if range_.duration_seconds <= 0:
        raise PlanValidationError(f"{label} 的时间窗口无效")


__all__ = ["resolve_periods", "check_range"]
