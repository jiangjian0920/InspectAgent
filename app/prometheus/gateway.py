from __future__ import annotations

import re
from typing import Any

from app.core.config import Settings
from app.core.errors import QueryError
from app.core.logging import get_logger
from app.domain.models import MetricQueryPlan, ServerTarget, TimeRange
from app.inventory.catalog import AssetCatalog, escape_promql_regex
from app.prometheus.client import PrometheusQueryClient, RangeQueryResult


_PLACEHOLDER = re.compile(r"\$\{?(\w+)\}?")


class QueryBudget:
    """限制单个计划允许的查询次数，防止查询放大。"""

    def __init__(self, max_query_count: int) -> None:
        self.max_query_count = max(1, max_query_count)
        self.used = 0

    def consume(self, label: str) -> None:
        if self.used >= self.max_query_count:
            raise QueryError(
                f"查询次数超过预算（{self.max_query_count}），拒绝执行 {label}",
                details={"max_query_count": self.max_query_count},
            )
        self.used += 1


class QueryGateway:
    """受控 Prometheus 查询网关。

    只接受来自受信任配置的模板 ID 与参数，不执行模型输出的原始 PromQL。
    """

    def __init__(
        self,
        settings: Settings,
        client: PrometheusQueryClient,
        templates: dict[str, dict[str, Any]],
        catalog: AssetCatalog,
    ) -> None:
        self.settings = settings
        self.client = client
        self.templates = templates
        self.catalog = catalog
        self.logger = get_logger("gateway")

    def template_default_window(self, template_id: str) -> str:
        template = self.templates.get(template_id) or {}
        return str(template.get("default_window") or "5m")

    def build_promql(self, template_id: str, values: dict[str, str]) -> str:
        template = self.templates.get(template_id)
        if template is None:
            raise QueryError(f"未注册的查询模板: {template_id}")

        missing: list[str] = []

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in values:
                missing.append(key)
                return match.group(0)
            return values[key]

        rendered = _PLACEHOLDER.sub(repl, str(template.get("promql") or ""))
        if missing:
            raise QueryError(f"模板 {template_id} 缺少参数: {sorted(set(missing))}")
        return rendered

    def _binding_values(
        self,
        target: ServerTarget,
        plan: MetricQueryPlan,
    ) -> dict[str, str]:
        if plan.scope == "all" or target.scope == "all":
            instance = self.catalog.instance_regex()
            job = self.catalog.job_regex()
        else:
            instance_value = target.prometheus_instance or plan.instance or ""
            instance = escape_promql_regex(instance_value)
            job = escape_promql_regex(target.labels.get("job", "") or ".*")
        return {
            "instance": instance,
            "job": job,
            "window": plan.params.get("window") or self.template_default_window(plan.template_id),
        }

    def collect_raw(
        self,
        target: ServerTarget,
        plan: MetricQueryPlan,
        budget: QueryBudget,
    ) -> RangeQueryResult:
        """执行一次模板查询，返回原始矩阵。"""
        values = self._binding_values(target, plan)
        promql = self.build_promql(plan.template_id, values)
        budget.consume(f"{plan.metric_id}@{plan.template_id}")
        return self.client.query_range(
            promql,
            plan.time_range.start,
            plan.time_range.end,
            plan.time_range.step_seconds,
        )


__all__ = ["QueryGateway", "QueryBudget"]
