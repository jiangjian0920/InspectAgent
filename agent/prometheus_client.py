from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from agent.config import Settings
from agent.logger import get_logger
from agent.utils import dumps_compact, parse_time_range, range_window, step_for_range, to_rfc3339


class PrometheusClient:
    """Prometheus HTTP 查询客户端。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = get_logger()

    def query_range(self, promql: str, time_range: str) -> dict[str, Any]:
        """调用 /api/v1/query_range，把矩阵结果收成 latest/max/avg。"""
        query = (promql or "").strip()
        window = (time_range or self.settings.default_time_range).strip()
        if not query:
            return {"ok": False, "error": "promql 不能为空", "promql": query, "time_range": window}

        try:
            normalized_range, seconds = parse_time_range(window, self.settings.default_time_range)
            start, end = range_window(seconds)
            step = step_for_range(seconds)
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "promql": query, "time_range": window}

        url = urljoin(self.settings.prometheus_url + "/", "api/v1/query_range")
        params = {
            "query": query,
            "start": to_rfc3339(start),
            "end": to_rfc3339(end),
            "step": step,
        }
        self.logger.info(
            "Prometheus query_range url=%s promql=%s start=%s end=%s step=%s",
            url,
            query,
            params["start"],
            params["end"],
            step,
        )

        try:
            import requests
        except ImportError as exc:
            return {
                "ok": False,
                "error": f"未安装 requests，请先执行 pip install -r requirements.txt: {exc}",
                "promql": query,
                "time_range": window,
            }

        try:
            response = requests.get(
                url,
                params=params,
                timeout=self.settings.prometheus_timeout_seconds,
            )
        except requests.Timeout as exc:
            return {
                "ok": False,
                "error": f"Prometheus 查询超时（{self.settings.prometheus_timeout_seconds}s）: {exc}",
                "promql": query,
                "time_range": window,
            }
        except requests.RequestException as exc:
            return {
                "ok": False,
                "error": f"Prometheus 网络请求失败: {exc}",
                "promql": query,
                "time_range": window,
            }

        if response.status_code != 200:
            body = dumps_compact(response.text, 1500)
            return {
                "ok": False,
                "error": f"Prometheus HTTP {response.status_code}: {body}",
                "promql": query,
                "time_range": window,
            }

        try:
            payload = response.json()
        except ValueError as exc:
            return {
                "ok": False,
                "error": f"Prometheus 返回非 JSON 响应: {exc}",
                "promql": query,
                "time_range": window,
            }

        if payload.get("status") != "success":
            error_type = payload.get("errorType", "unknown")
            error = payload.get("error", "Prometheus 查询失败")
            return {
                "ok": False,
                "error": f"Prometheus 查询失败 [{error_type}]: {error}",
                "promql": query,
                "time_range": window,
            }

        result = payload.get("data", {}).get("result", [])
        return {
            "ok": True,
            "promql": query,
            "time_range": normalized_range,
            "start": to_rfc3339(start),
            "end": to_rfc3339(end),
            "step": step,
            "result_type": payload.get("data", {}).get("resultType"),
            "series_count": len(result),
            "series": _summarize_matrix(result),
        }


def _summarize_matrix(result: list[dict[str, Any]], max_series: int = 20) -> list[dict[str, Any]]:
    """把 Prometheus 矩阵压缩成每条序列的 latest/max/min/avg。"""
    series: list[dict[str, Any]] = []
    for item in result[:max_series]:
        points: list[float] = []
        for pair in item.get("values") or []:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            try:
                points.append(float(pair[1]))
            except (TypeError, ValueError):
                continue
        series.append(
            {
                "metric": item.get("metric") or {},
                "sample_count": len(points),
                "latest": points[-1] if points else None,
                "max": max(points) if points else None,
                "min": min(points) if points else None,
                "avg": round(sum(points) / len(points), 4) if points else None,
            }
        )
    if len(result) > max_series:
        series.append(
            {
                "metric": {"_note": f"仅返回前 {max_series} 条序列，原始共 {len(result)} 条"},
                "sample_count": 0,
                "latest": None,
                "max": None,
                "min": None,
                "avg": None,
            }
        )
    return series
