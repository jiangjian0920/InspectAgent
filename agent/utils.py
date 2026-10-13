from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone


_RANGE_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ms|s|m|h|d|秒|分钟|分|小时|时|天)",
    re.IGNORECASE,
)

_INSTANCE_RE = re.compile(
    r"(?:instance\s*=\s*|主机\s*|服务器\s*|实例\s*)([A-Za-z0-9_.:\-]+)",
    re.IGNORECASE,
)

_IP_RE = re.compile(r"(?<![\dA-Za-z])(\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?)(?![\dA-Za-z])")

_METRIC_TOKEN_RE = re.compile(r"(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?P<sel>\{[^{}]*\})?")

_PROMQL_KEYWORDS = {
    "by",
    "without",
    "on",
    "ignoring",
    "group_left",
    "group_right",
    "rate",
    "irate",
    "sum",
    "avg",
    "max",
    "min",
    "count",
    "clamp_min",
    "clamp_max",
    "and",
    "or",
    "unless",
    "bool",
}

_UNIT_SECONDS = {
    "ms": 0.001,
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "秒": 1,
    "分钟": 60,
    "分": 60,
    "小时": 3600,
    "时": 3600,
    "天": 86400,
}


def parse_time_range(raw: str, default: str = "2h") -> tuple[str, int]:
    """解析时间范围，返回规范化字符串和对应秒数。"""
    text = (raw or "").strip()
    if not text:
        text = default
    match = _RANGE_RE.search(text)
    if match is None:
        match = _RANGE_RE.search(default)
        if match is None:
            raise ValueError(f"无法解析时间范围: {raw!r}")
        text = default
    value = float(match.group("value"))
    unit = match.group("unit").lower()
    seconds = int(value * _UNIT_SECONDS[unit])
    if seconds <= 0:
        raise ValueError(f"时间范围必须大于 0: {raw!r}")
    if unit in {"秒"}:
        normalized = f"{int(value)}s"
    elif unit in {"分钟", "分"}:
        normalized = f"{int(value)}m"
    elif unit in {"小时", "时"}:
        normalized = f"{int(value)}h"
    elif unit in {"天"}:
        normalized = f"{int(value)}d"
    else:
        normalized = f"{int(value) if value.is_integer() else value}{unit}"
    return normalized, seconds


def step_for_range(seconds: int) -> str:
    if seconds <= 15 * 60:
        return "15s"
    if seconds <= 60 * 60:
        return "15s"
    if seconds <= 6 * 60 * 60:
        return "30s"
    if seconds <= 24 * 60 * 60:
        return "1m"
    return "5m"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def range_window(seconds: int, end: datetime | None = None) -> tuple[datetime, datetime]:
    finish = end or utc_now()
    start = finish - timedelta(seconds=seconds)
    return start, finish


def to_rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def truncate_text(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"...(truncated, total={len(text)})"


def dumps_compact(data: object, limit: int = 4000) -> str:
    try:
        text = json.dumps(data, ensure_ascii=False, default=str)
    except TypeError:
        text = str(data)
    return truncate_text(text, limit)


def safe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_INSTANCE_MATCHER_RE = re.compile(r'\binstance\s*(=~|=|!=|!~)\s*"[^"]*"')


def parse_instance(raw: str) -> str | None:
    """从文本里提取主机名或 IP 作为实例标识。"""
    text = (raw or "").strip()
    if not text:
        return None
    match = _INSTANCE_RE.search(text)
    if match:
        return match.group(1)
    match = _IP_RE.search(text)
    if match:
        return match.group(1)
    return None


def instance_host(value: str) -> str:
    text = (value or "").strip()
    if re.search(r":\d+$", text):
        return text.rsplit(":", 1)[0]
    return text


def series_matches_instance(metric: dict | None, instance: str | None) -> bool:
    """判断时序的 instance 标签是否等于指定实例（端口可以不同）。"""
    target = (instance or "").strip()
    if not target:
        return True
    raw = str((metric or {}).get("instance") or "").strip()
    if not raw:
        return False
    if raw.lower() == target.lower():
        return True
    return instance_host(raw).lower() == instance_host(target).lower()


def _promql_regex_literal(text: str) -> str:
    chars: list[str] = []
    for ch in text:
        if ch in r".*+?^${}()|[]\\":
            chars.append(f"[{ch}]")
        else:
            chars.append(ch)
    return "".join(chars)


def prometheus_instance_matcher(instance: str) -> str:
    """生成 PromQL 里的 instance 匹配器，IP 会写成字符类以免被当成正则点号。"""
    target = instance.replace('"', "").strip()
    if re.search(r":\d+$", target):
        return f'instance="{target}"'
    pattern = _promql_regex_literal(target)
    return f'instance=~"{pattern}(:[0-9]+)?"'


def apply_instance_filter(promql: str, instance: str | None) -> str:
    """给 PromQL 的指标选择器加上或替换 instance 过滤条件。"""
    query = (promql or "").strip()
    target = (instance or "").strip()
    if not query or not target:
        return query
    matcher = prometheus_instance_matcher(target)
    if _INSTANCE_MATCHER_RE.search(query):
        return _INSTANCE_MATCHER_RE.sub(matcher, query)

    def replacer(match: re.Match[str]) -> str:
        name = match.group("name")
        if name in _PROMQL_KEYWORDS or ("_" not in name and name != "up"):
            return match.group(0)
        selector = match.group("sel")
        if selector:
            inner = selector[1:-1].strip()
            if inner:
                return f"{name}{{{matcher},{inner}}}"
            return f"{name}{{{matcher}}}"
        return f"{name}{{{matcher}}}"

    return _METRIC_TOKEN_RE.sub(replacer, query)


def bind_prometheus_result_to_instance(result: dict, instance: str | None) -> dict:
    """留下属于指定实例的序列；一条都对不上就把结果标成失败。"""
    target = (instance or "").strip()
    if not target or not isinstance(result, dict):
        return result
    if not result.get("ok"):
        copied = dict(result)
        copied["requested_instance"] = target
        return copied
    series = list(result.get("series") or [])
    matched: list[dict] = []
    dropped: list[str] = []
    notes: list[dict] = []
    for item in series:
        labels = item.get("metric") or {}
        if labels.get("_note"):
            notes.append(item)
            continue
        raw = str(labels.get("instance") or "").strip()
        if series_matches_instance(labels, target):
            matched.append(item)
        elif raw:
            dropped.append(raw)
    if matched:
        copied = dict(result)
        copied["series"] = matched + notes
        copied["series_count"] = len(matched)
        copied["requested_instance"] = target
        if dropped:
            copied["dropped_instances"] = sorted(set(dropped))
        return copied
    found = sorted(set(dropped))
    found_text = "、".join(found) if found else "无"
    return {
        "ok": False,
        "error": (
            f"Prometheus 中未找到 instance={target} 的时序。"
            "禁止使用其他主机数据。"
            f"本次查询实际返回的 instance：{found_text}。"
        ),
        "promql": result.get("promql"),
        "time_range": result.get("time_range"),
        "requested_instance": target,
        "returned_instances": found,
        "series": [],
        "series_count": 0,
    }
