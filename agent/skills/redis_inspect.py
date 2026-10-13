from __future__ import annotations

from typing import Any

from agent.skills.base import Skill
from agent.skills.catalogs import REDIS_METRICS
from agent.skills.common import inspect_schema, normalize_metrics, probe_instance, run_metric_queries, skill_payload


class RedisInspectSkill(Skill):
    """Redis 巡检。先确认 redis 实例是否接入 Prometheus，再查健康指标。"""

    name = "redis_inspect"
    target_type = "redis"
    description = (
        "巡检 Redis 实例（redis_exporter）。"
        "入参 instance 如 redis6404，metrics 可选 up/memory/clients/blocked/rejected/ops。"
        "未指定 metrics 时做 Redis 基础健康巡检。实例不存在则直接返回未找到对应实例。"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return inspect_schema("Redis", "可选：up、memory、clients、blocked、rejected、ops。")

    def default_metrics(self) -> list[str]:
        return [item["key"] for item in REDIS_METRICS]

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        instance = str(kwargs.get("instance") or "").strip() or None
        time_range = str(kwargs.get("time_range") or self.settings.default_time_range).strip()
        metrics = normalize_metrics(kwargs.get("metrics"), REDIS_METRICS, self.default_metrics())
        probe = probe_instance(
            self.prometheus,
            ["redis_up", "redis_connected_clients", "redis_memory_used_bytes"],
            instance,
            time_range,
        )
        if not probe["found"]:
            error = str((probe.get("result") or {}).get("error") or "")
            return skill_payload(
                self.name,
                self.target_type,
                instance,
                metrics,
                time_range,
                instance_found=False,
                error=error or "未找到对应实例",
            )
        checked, anomalies = run_metric_queries(
            self.prometheus,
            REDIS_METRICS,
            metrics,
            instance,
            time_range,
            self.settings.thresholds,
        )
        return skill_payload(
            self.name,
            self.target_type,
            instance,
            metrics,
            time_range,
            instance_found=True,
            anomalies=anomalies,
            checked=checked,
            checked_count=len(metrics),
        )
