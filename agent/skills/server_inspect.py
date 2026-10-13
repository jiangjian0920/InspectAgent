from __future__ import annotations

from typing import Any

from agent.skills.base import Skill
from agent.skills.catalogs import SERVER_METRICS
from agent.skills.common import inspect_schema, normalize_metrics, probe_instance, run_metric_queries, skill_payload


class ServerInspectSkill(Skill):
    """Linux 主机巡检。先校验 instance 是否存在，再按点名指标查询。"""

    name = "server_inspect"
    target_type = "server"
    description = (
        "巡检 Linux 服务器主机（node_exporter）。"
        "入参 instance 为主机 IP 或 instance 标签，metrics 为 cpu/memory/disk/disk_io/load/network_rx/network_tx。"
        "未指定 metrics 时做主机基础健康巡检。实例不存在则返回未找到对应实例，不再查 Prometheus 业务指标。"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return inspect_schema("服务器", "可选：cpu、memory、disk、disk_io、load、network_rx、network_tx。")

    def default_metrics(self) -> list[str]:
        return [item["key"] for item in SERVER_METRICS]

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        instance = str(kwargs.get("instance") or "").strip() or None
        time_range = str(kwargs.get("time_range") or self.settings.default_time_range).strip()
        metrics = normalize_metrics(kwargs.get("metrics"), SERVER_METRICS, self.default_metrics())
        probe = probe_instance(
            self.prometheus,
            ["up", "node_uname_info"],
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
            SERVER_METRICS,
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
