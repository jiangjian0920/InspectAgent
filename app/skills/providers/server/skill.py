from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ConfigurationError
from app.core.logging import get_logger
from app.domain.models import (
    MetricDefinition,
    MetricSeries,
    ResolvedTarget,
    ServerTarget,
)
from app.inventory.catalog import AssetCatalog
from app.prometheus.client import HttpPrometheusClient, PrometheusQueryClient
from app.prometheus.gateway import QueryBudget, QueryGateway
from app.rules.loader import load_metric_catalog, load_query_templates
from app.skills.base import BaseMetricProvider, MetricCollectionRequest


_SKIP_DIMENSION_LABELS = {"__name__", "job", "aliases"}


class ServerMetricSkill(BaseMetricProvider):
    """服务器领域的唯一专项 Skill。

    只负责实例发现、标签映射、PromQL 模板与 MetricSeries 转换。
    """

    resource_type = "server"
    name = "server_metric"

    def __init__(
        self,
        settings: Settings,
        client: PrometheusQueryClient | None = None,
        catalog: AssetCatalog | None = None,
    ) -> None:
        self.settings = settings
        self.logger = get_logger("server_skill")
        skill_dir = settings.resolved_server_skill_dir()
        catalog_path = skill_dir / "metric_catalog.yaml"
        queries_path = skill_dir / "queries.yaml"
        if not catalog_path.exists() or not queries_path.exists():
            raise ConfigurationError(f"服务器指标配置缺失: {skill_dir}")
        self._definitions = load_metric_catalog(catalog_path)
        self._templates = load_query_templates(queries_path)
        self.catalog = catalog or AssetCatalog.from_yaml(settings.resolved_assets_path())
        self.client = client or HttpPrometheusClient(settings)
        self.gateway = QueryGateway(settings, self.client, self._templates, self.catalog)

    def resolve_target(self, reference: str) -> ResolvedTarget | None:
        return self.catalog.resolve(reference)

    def supported_metrics(self) -> list[MetricDefinition]:
        return list(self._definitions.values())

    def default_metric_ids(self) -> list[str]:
        return list(self._definitions.keys())

    def metric_by_id(self, metric_id: str) -> MetricDefinition | None:
        return self._definitions.get(metric_id)

    def all_targets(self) -> list[ResolvedTarget]:
        return self.catalog.all_targets()

    def _resource_id_for(self, instance_label: str, fallback: str) -> str:
        target = self.catalog.resolve(instance_label)
        if target is not None:
            return target.resource_id
        return instance_label or fallback

    def collect(self, request: MetricCollectionRequest) -> list[MetricSeries]:
        budget = QueryBudget(self.settings.max_query_count)
        series: list[MetricSeries] = []
        for query in request.queries:
            definition = self._definitions.get(query.metric_id)
            if definition is None:
                continue
            raw = self.gateway.collect_raw(request.target, query, budget)
            if not raw.ok:
                series.append(
                    MetricSeries(
                        resource_id=request.resource_id,
                        metric_id=query.metric_id,
                        display_name=definition.display_name,
                        unit=definition.unit,
                        collection_status="error",
                        source_time_range=query.time_range,
                        period=query.period,
                        error=raw.error,
                        dimensions={"instance": request.target.prometheus_instance or ""},
                    )
                )
                continue
            if not raw.series:
                series.append(
                    MetricSeries(
                        resource_id=request.resource_id,
                        metric_id=query.metric_id,
                        display_name=definition.display_name,
                        unit=definition.unit,
                        collection_status="missing",
                        source_time_range=query.time_range,
                        period=query.period,
                        dimensions={"instance": request.target.prometheus_instance or ""},
                    )
                )
                continue
            for item in raw.series:
                dimensions = {
                    key: value
                    for key, value in item.metric.items()
                    if key not in _SKIP_DIMENSION_LABELS
                }
                instance_label = item.metric.get("instance", "")
                resource_id = self._resource_id_for(instance_label, request.resource_id)
                status = "ok" if any(v is not None for v in item.values) else "missing"
                series.append(
                    MetricSeries(
                        resource_id=resource_id,
                        metric_id=query.metric_id,
                        display_name=definition.display_name,
                        unit=definition.unit,
                        timestamps=item.timestamps,
                        values=item.values,
                        dimensions=dimensions,
                        collection_status=status,  # type: ignore[arg-type]
                        source_time_range=query.time_range,
                        period=query.period,
                    )
                )
        return series


__all__ = ["ServerMetricSkill"]
