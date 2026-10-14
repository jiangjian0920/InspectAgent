from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urljoin

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.logging import get_logger


class RawSeries(BaseModel):
    metric: dict[str, str] = Field(default_factory=dict)
    timestamps: list[datetime] = Field(default_factory=list)
    values: list[float | None] = Field(default_factory=list)


class RangeQueryResult(BaseModel):
    ok: bool
    promql: str = ""
    error: str | None = None
    result_type: str = "matrix"
    series: list[RawSeries] = Field(default_factory=list)

    @property
    def series_count(self) -> int:
        return len(self.series)


class PrometheusQueryClient(Protocol):
    """查询客户端协议，便于在测试中注入模拟实现。"""

    def query_range(
        self,
        promql: str,
        start: datetime,
        end: datetime,
        step_seconds: int,
    ) -> RangeQueryResult:  # pragma: no cover - 协议声明
        ...


def _to_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _parse_series(result: list[dict[str, Any]]) -> list[RawSeries]:
    series: list[RawSeries] = []
    for item in result:
        if not isinstance(item, dict):
            continue
        metric = {str(k): str(v) for k, v in (item.get("metric") or {}).items()}
        timestamps: list[datetime] = []
        values: list[float | None] = []
        raw_values = item.get("values")
        if raw_values is None and "value" in item:
            raw_values = [item.get("value")]
        for pair in raw_values or []:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            try:
                timestamps.append(datetime.fromtimestamp(float(pair[0]), tz=timezone.utc))
            except (TypeError, ValueError):
                continue
            values.append(_to_float(pair[1]))
        series.append(RawSeries(metric=metric, timestamps=timestamps, values=values))
    return series


class HttpPrometheusClient:
    """基于 requests 的 Prometheus HTTP 查询客户端。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = get_logger("prometheus")

    def query_range(
        self,
        promql: str,
        start: datetime,
        end: datetime,
        step_seconds: int,
    ) -> RangeQueryResult:
        query = (promql or "").strip()
        if not query:
            return RangeQueryResult(ok=False, promql=query, error="PromQL 不能为空")
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - 运行期依赖
            return RangeQueryResult(
                ok=False,
                promql=query,
                error=f"未安装 requests: {exc}",
            )

        url = urljoin(self.settings.prometheus_url + "/", "api/v1/query_range")
        params = {
            "query": query,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step_seconds,
        }
        self.logger.info(
            "query_range url=%s start=%s end=%s step=%s promql=%s",
            url,
            start.isoformat(),
            end.isoformat(),
            step_seconds,
            query,
        )
        try:
            response = requests.get(
                url, params=params, timeout=self.settings.prometheus_timeout_seconds
            )
        except requests.Timeout:
            return RangeQueryResult(
                ok=False,
                promql=query,
                error=f"Prometheus 查询超时（{self.settings.prometheus_timeout_seconds}s）",
            )
        except requests.RequestException as exc:
            return RangeQueryResult(ok=False, promql=query, error=f"Prometheus 网络请求失败: {exc}")

        if response.status_code != 200:
            return RangeQueryResult(
                ok=False,
                promql=query,
                error=f"Prometheus HTTP {response.status_code}: {response.text[:500]}",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            return RangeQueryResult(ok=False, promql=query, error=f"Prometheus 返回非 JSON: {exc}")
        if payload.get("status") != "success":
            error_type = payload.get("errorType", "unknown")
            error = payload.get("error", "查询失败")
            return RangeQueryResult(
                ok=False, promql=query, error=f"Prometheus [{error_type}]: {error}"
            )
        data = payload.get("data") or {}
        result_type = str(data.get("resultType") or "matrix")
        result = data.get("result") or []
        if not isinstance(result, list):
            return RangeQueryResult(ok=False, promql=query, error="Prometheus 结果格式错误")
        if len(result) > self.settings.max_series:
            result = result[: self.settings.max_series]
        return RangeQueryResult(
            ok=True,
            promql=query,
            result_type=result_type,
            series=_parse_series(result),
        )


__all__ = [
    "RawSeries",
    "RangeQueryResult",
    "PrometheusQueryClient",
    "HttpPrometheusClient",
]
