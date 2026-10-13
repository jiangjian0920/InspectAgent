from __future__ import annotations

from typing import Any

from agent.skills.base import Skill
from agent.skills.catalogs import K8S_METRICS
from agent.skills.common import inspect_schema, normalize_metrics, probe_instance, run_metric_queries, skill_payload


class K8sInspectSkill(Skill):
    """Kubernetes 巡检。先确认 Pod/Node 时序存在，再查重启、CPU、内存、就绪状态。"""

    name = "k8s_inspect"
    target_type = "k8s"
    description = (
        "巡检 Kubernetes Pod / Node（kube-state-metrics / cAdvisor）。"
        "入参 instance 为 Pod 名、Node 名或命名空间，metrics 可选 restarts/cpu/memory/not_ready。"
        "未指定 metrics 时做 K8s 基础健康巡检。实例不存在则直接返回未找到对应实例。"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return inspect_schema("K8s", "可选：restarts、cpu、memory、not_ready。")

    def default_metrics(self) -> list[str]:
        return [item["key"] for item in K8S_METRICS]

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        instance = str(kwargs.get("instance") or "").strip() or None
        time_range = str(kwargs.get("time_range") or self.settings.default_time_range).strip()
        metrics = normalize_metrics(kwargs.get("metrics"), K8S_METRICS, self.default_metrics())
        probe = probe_instance(
            self.prometheus,
            ["kube_pod_info", "kube_node_info", "kube_pod_status_phase"],
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
            K8S_METRICS,
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
