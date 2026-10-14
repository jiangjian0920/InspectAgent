from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.core.errors import ProviderNotFoundError
from app.domain.models import (
    MetricDefinition,
    MetricQueryPlan,
    MetricSeries,
    ResolvedTarget,
    ServerTarget,
    TimeRange,
)
from app.prometheus.gateway import QueryBudget


class MetricCollectionRequest(BaseModel):
    """专项 Skill 采集请求。包含完整查询计划，Skill 不自行生成 PromQL。"""

    resource_id: str
    target: ServerTarget
    metric_ids: list[str] = Field(default_factory=list)
    queries: list[MetricQueryPlan] = Field(default_factory=list)
    time_range: TimeRange
    period: str | None = None


@runtime_checkable
class MetricProviderSkill(Protocol):
    """专项指标 Skill 协议。未来的 Redis / Kafka / MySQL 实现同一接口。"""

    resource_type: str

    def resolve_target(self, reference: str) -> ResolvedTarget | None:  # pragma: no cover
        ...

    def supported_metrics(self) -> list[MetricDefinition]:  # pragma: no cover
        ...

    def collect(self, request: MetricCollectionRequest) -> list[MetricSeries]:  # pragma: no cover
        ...


class BaseMetricProvider(ABC):
    """专项 Skill 基类，提供注册名与指标查表的通用实现。"""

    resource_type: str = "server"
    name: str = ""

    @abstractmethod
    def resolve_target(self, reference: str) -> ResolvedTarget | None:
        raise NotImplementedError

    @abstractmethod
    def supported_metrics(self) -> list[MetricDefinition]:
        raise NotImplementedError

    @abstractmethod
    def collect(self, request: MetricCollectionRequest) -> list[MetricSeries]:
        raise NotImplementedError

    def metric_by_id(self, metric_id: str) -> MetricDefinition | None:
        for definition in self.supported_metrics():
            if definition.metric_id == metric_id:
                return definition
        return None

    def plan_queries(
        self,
        target: ServerTarget,
        metric_ids: list[str],
        time_range: TimeRange,
        *,
        scope: str = "instance",
        period: str | None = None,
    ) -> list[MetricQueryPlan]:
        queries: list[MetricQueryPlan] = []
        for metric_id in metric_ids:
            definition = self.metric_by_id(metric_id)
            if definition is None:
                continue
            queries.append(
                MetricQueryPlan(
                    metric_id=metric_id,
                    template_id=definition.template_id,
                    scope=scope,  # type: ignore[arg-type]
                    instance=target.prometheus_instance,
                    time_range=time_range,
                    aggregation=definition.aggregation,
                    period=period,
                )
            )
        return queries


class ProviderRegistry:
    """按 resource_type 存放专项 Skill。"""

    def __init__(self) -> None:
        self._providers: dict[str, BaseMetricProvider] = {}

    def register(self, provider: BaseMetricProvider) -> None:
        self._providers[provider.resource_type] = provider

    def get(self, resource_type: str) -> BaseMetricProvider:
        provider = self._providers.get(resource_type)
        if provider is None:
            available = ", ".join(sorted(self._providers)) or "<empty>"
            raise ProviderNotFoundError(
                f"未注册的 resource_type: {resource_type}，当前可用: {available}"
            )
        return provider

    def has(self, resource_type: str) -> bool:
        return resource_type in self._providers

    def resource_types(self) -> list[str]:
        return list(self._providers.keys())

    def all_providers(self) -> list[BaseMetricProvider]:
        return list(self._providers.values())


__all__ = [
    "MetricCollectionRequest",
    "MetricProviderSkill",
    "BaseMetricProvider",
    "ProviderRegistry",
    "QueryBudget",
]
