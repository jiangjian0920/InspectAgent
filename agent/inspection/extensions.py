from __future__ import annotations

from agent.skills.kafka_inspect import KafkaInspectSkill
from agent.skills.k8s_inspect import K8sInspectSkill
from agent.skills.redis_inspect import RedisInspectSkill

# 旧的 Capability 预留入口已落地为独立 Skill。
RedisInspectionCapability = RedisInspectSkill
KafkaInspectionCapability = KafkaInspectSkill
K8sPodInspectionCapability = K8sInspectSkill
