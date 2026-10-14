from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from app.prometheus.client import RangeQueryResult, RawSeries


METRIC_TOKENS = {
    "node_cpu_seconds_total": "cpu",
    "node_memory_MemAvailable": "memory",
    "node_filesystem_avail": "disk",
    "up{": "availability",
}

Responder = Callable[[str, datetime, datetime, int], RangeQueryResult]


def detect_metric(promql: str) -> str | None:
    for token, metric in METRIC_TOKENS.items():
        if token in promql:
            return metric
    if promql.strip().startswith("up"):
        return "availability"
    return None


def make_series(
    promql: str,
    start: datetime,
    end: datetime,
    step: int,
    spec: list[tuple[dict[str, str], object]],
) -> list[RawSeries]:
    """按 spec 生成矩阵。spec 的 value 可以是常量或 (index, count) -> float 的函数。"""
    count = max(1, int((end - start).total_seconds() // max(1, step)) + 1)
    timestamps = [start + timedelta(seconds=step * i) for i in range(count)]
    series: list[RawSeries] = []
    for labels, value in spec:
        if callable(value):
            values: list[float | None] = [float(value(i, count)) for i in range(count)]
        else:
            values = [float(value) for _ in range(count)]  # type: ignore[arg-type]
        series.append(RawSeries(metric=dict(labels), timestamps=list(timestamps), values=values))
    return series


class FakePrometheusClient:
    """模拟 Prometheus 查询客户端，记录所有收到的 PromQL。"""

    def __init__(self, specs: dict[str, list[tuple[dict[str, str], object]]] | None = None,
                 errors: set[str] | None = None,
                 responder: Responder | None = None) -> None:
        self.specs = specs or {}
        self.errors = errors or set()
        self.responder = responder
        self.queries: list[str] = []

    def query_range(self, promql: str, start: datetime, end: datetime, step: int) -> RangeQueryResult:
        self.queries.append(promql)
        if self.responder is not None:
            return self.responder(promql, start, end, step)
        metric = detect_metric(promql)
        if metric in self.errors:
            return RangeQueryResult(ok=False, promql=promql, error="simulated failure")
        spec = self.specs.get(metric or "", [])
        return RangeQueryResult(
            ok=True,
            promql=promql,
            series=make_series(promql, start, end, step, spec),
        )


__all__ = ["FakePrometheusClient", "make_series", "detect_metric", "METRIC_TOKENS"]
