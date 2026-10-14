from __future__ import annotations

from math import ceil
from statistics import mean


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def summarize_values(values: list[float]) -> dict[str, float | None]:
    """对一组数值给出均值、最大值、最小值、P95、最新值、总和。"""
    if not values:
        return {"avg": None, "max": None, "min": None, "p95": None, "latest": None, "sum": None}
    return {
        "avg": round(mean(values), 4),
        "max": max(values),
        "min": min(values),
        "p95": round(percentile(values, 95) or max(values), 4),
        "latest": values[-1],
        "sum": round(sum(values), 4),
    }


def pick_aggregate(stats: dict[str, float | None], function: str) -> float | None:
    key = {
        "avg": "avg",
        "max": "max",
        "min": "min",
        "p95": "p95",
        "latest": "latest",
        "sum": "sum",
    }.get(function, "avg")
    return stats.get(key)


def linear_slope(timestamps: list[float], values: list[float]) -> float:
    """最小二乘斜率，单位 值/秒。"""
    n = min(len(timestamps), len(values))
    if n < 2:
        return 0.0
    xs = timestamps[:n]
    ys = values[:n]
    mx = mean(xs)
    my = mean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    numer = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return numer / denom


def count_above(values: list[float], threshold: float, comparison: str = "gt") -> int:
    if comparison == "gt":
        return sum(1 for v in values if v > threshold)
    if comparison == "lt":
        return sum(1 for v in values if v < threshold)
    if comparison == "ge":
        return sum(1 for v in values if v >= threshold)
    return sum(1 for v in values if v <= threshold)


def ceil_div(a: int, b: int) -> int:
    if b <= 0:
        return 0
    return ceil(a / b)


__all__ = [
    "percentile",
    "summarize_values",
    "pick_aggregate",
    "linear_slope",
    "count_above",
    "ceil_div",
]
