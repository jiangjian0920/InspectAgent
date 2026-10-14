from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.timeparse import (
    chinese_relative_days,
    duration_seconds,
    resolve_named_period,
    resolve_relative_range,
)
from app.domain.models import NamedTimeRange


def test_duration_seconds_units():
    assert duration_seconds("5m") == 300
    assert duration_seconds("2h") == 7200
    assert duration_seconds("1d") == 86400
    assert duration_seconds("30") is None


def test_chinese_relative_days():
    assert chinese_relative_days("最近4天") == 4 * 86400
    assert chinese_relative_days("近7天") == 7 * 86400
    assert chinese_relative_days("hello") is None


def test_resolve_relative_range_caps_step():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    window, label = resolve_relative_range("4天", now, 7200, 60)
    assert label == "4天"
    assert window.duration_seconds == 4 * 86400
    assert window.step_seconds > 60


def test_resolve_named_period_yesterday():
    now = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc).astimezone()
    period = NamedTimeRange(name="yesterday", start="yesterday 00:00", end="yesterday 23:59:59")
    window = resolve_named_period(period, now, 60)
    assert window.start < window.end
    assert window.duration_seconds == pytest.approx(86399, abs=5)
