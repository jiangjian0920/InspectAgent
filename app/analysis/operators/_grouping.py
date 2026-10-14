from __future__ import annotations

from collections import OrderedDict
from typing import Any

from app.analysis.stats import percentile, summarize_values


def group_key(record: dict[str, Any], keys: list[str]) -> tuple[str, ...]:
    values: list[str] = []
    for key in keys:
        if key in {"instance", "resource_id", "resource"}:
            values.append(str(record.get("resource_id") or ""))
        else:
            values.append(str((record.get("dimensions") or {}).get(key, "")))
    return tuple(values)


def merge_values(values: list[Any], function: str) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    if not nums:
        return None
    if function == "sum":
        return round(sum(nums), 4)
    if function == "max":
        return max(nums)
    if function == "min":
        return min(nums)
    if function == "latest":
        return nums[-1]
    if function == "count":
        return float(len(nums))
    if function == "p95":
        return percentile(nums, 95)
    return round(sum(nums) / len(nums), 4)


def group_records(
    records: list[dict[str, Any]],
    keys: list[str],
    function: str,
) -> list[dict[str, Any]]:
    if not keys:
        return records
    grouped: OrderedDict[tuple[str, ...], list[dict[str, Any]]] = OrderedDict()
    for record in records:
        grouped.setdefault(group_key(record, keys), []).append(record)

    merged: list[dict[str, Any]] = []
    for key, items in grouped.items():
        values = [item.get("value") for item in items]
        numeric = [v for v in values if isinstance(v, (int, float))]
        dimensions: dict[str, str] = {}
        for item in items:
            dimensions.update(item.get("dimensions") or {})
        for name, value in zip(keys, key):
            if value:
                dimensions[name] = value
        status = "ok" if any(item.get("collection_status") == "ok" for item in items) else items[0].get(
            "collection_status", "ok"
        )
        merged.append(
            {
                "kind": items[0].get("kind", "metric"),
                "resource_id": items[0].get("resource_id", ""),
                "metric_id": items[0].get("metric_id", ""),
                "display_name": items[0].get("display_name", ""),
                "unit": items[0].get("unit", "ratio"),
                "dimensions": dimensions,
                "stats": summarize_values(numeric),
                "value": merge_values(values, function),
                "collection_status": status,
                "severity": None,
                "group_size": len(items),
                "period": items[0].get("period"),
            }
        )
    return merged


__all__ = ["group_key", "merge_values", "group_records"]
