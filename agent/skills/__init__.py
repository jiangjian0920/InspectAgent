from __future__ import annotations

from agent.config import Settings
from agent.prometheus_client import PrometheusClient
from agent.skills.base import Skill, SkillRegistry
from agent.skills.kafka_inspect import KafkaInspectSkill
from agent.skills.k8s_inspect import K8sInspectSkill
from agent.skills.redis_inspect import RedisInspectSkill
from agent.skills.server_inspect import ServerInspectSkill


def build_default_skills(
    settings: Settings,
    prometheus: PrometheusClient | None = None,
) -> SkillRegistry:
    """创建默认 Skill 注册表：主机、Redis、Kafka、K8s 各一份。"""
    client = prometheus or PrometheusClient(settings)
    registry = SkillRegistry()
    for cls in (ServerInspectSkill, RedisInspectSkill, KafkaInspectSkill, K8sInspectSkill):
        registry.register(cls(settings, client))
    return registry


__all__ = ["Skill", "SkillRegistry", "build_default_skills"]
