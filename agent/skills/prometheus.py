from __future__ import annotations

from agent.prometheus_client import PrometheusClient

# 旧的 prometheus_query LLM 工具已下线。PromQL 查询改由各巡检 Skill 内部调用 PrometheusClient。
PrometheusQuerySkill = PrometheusClient
