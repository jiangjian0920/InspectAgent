from __future__ import annotations

from typing import Any

from agent.skills.base import Skill
from agent.skills.catalogs import KAFKA_METRICS
from agent.skills.common import inspect_schema, normalize_metrics, probe_instance, run_metric_queries, skill_payload


class KafkaInspectSkill(Skill):
    """Kafka 巡检。先确认 broker/集群时序存在，再查副本与消费滞后。"""

    name = "kafka_inspect"
    target_type = "kafka"
    description = (
        "巡检 Kafka 集群或 Broker（kafka_exporter / JMX）。"
        "入参 instance 为 broker 或集群名，metrics 可选 brokers/under_replicated/offline/lag。"
        "未指定 metrics 时做 Kafka 基础健康巡检。实例不存在则直接返回未找到对应实例。"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return inspect_schema("Kafka", "可选：brokers、under_replicated、offline、lag。")

    def default_metrics(self) -> list[str]:
        return [item["key"] for item in KAFKA_METRICS]

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        instance = str(kwargs.get("instance") or "").strip() or None
        time_range = str(kwargs.get("time_range") or self.settings.default_time_range).strip()
        metrics = normalize_metrics(kwargs.get("metrics"), KAFKA_METRICS, self.default_metrics())
        probe = probe_instance(
            self.prometheus,
            [
                "kafka_brokers",
                "up",
                "kafka_server_brokertopicmetrics_messagesin_total",
            ],
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
            KAFKA_METRICS,
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
