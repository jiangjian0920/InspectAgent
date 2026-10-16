from __future__ import annotations

from datetime import datetime, timezone

from app.analysis.registry import SERIES_OPERATORS
from app.analysis.validator import validate_operations
from app.core.config import Settings
from app.core.context import current_request_id, new_request_id
from app.core.errors import PlanValidationError, TargetNotFoundError
from app.core.logging import get_logger
from app.domain.models import (
    AnalysisOperation,
    InspectionIntent,
    InspectionPlan,
    MetricQueryPlan,
    ServerTarget,
)
from app.planner.validator import check_range, resolve_periods
from app.rules.loader import Policies
from app.skills.base import BaseMetricProvider


_DEFAULT_METRICS = {
    "instant_inspection": ["cpu", "memory", "disk", "availability"],
    "historical_anomaly_summary": ["cpu", "memory", "disk", "availability"],
    "period_comparison": ["cpu", "memory", "disk", "availability"],
    "trend_analysis": ["cpu", "memory", "disk", "availability"],
    "ranking_query": ["cpu"],
    "threshold_filter": ["cpu"],
}


def default_operations(task_type: str, limit: int) -> list[AnalysisOperation]:
    if task_type == "historical_anomaly_summary":
        return [
            AnalysisOperation(type="detect_anomaly"),
            AnalysisOperation(type="group_by", group_by=["instance"]),
            AnalysisOperation(type="sort", field="severity", direction="desc"),
            AnalysisOperation(type="summarize"),
        ]
    if task_type == "period_comparison":
        return [
            AnalysisOperation(type="aggregate", function="avg"),
            AnalysisOperation(type="compare"),
            AnalysisOperation(type="filter"),
            AnalysisOperation(type="summarize"),
        ]
    if task_type == "trend_analysis":
        return [
            AnalysisOperation(type="trend"),
            AnalysisOperation(type="summarize"),
        ]
    if task_type == "ranking_query":
        return [
            AnalysisOperation(type="aggregate", function="avg", group_by=["instance"]),
            AnalysisOperation(type="sort", field="value", direction="desc"),
            AnalysisOperation(type="limit", count=limit),
            AnalysisOperation(type="summarize"),
        ]
    if task_type == "threshold_filter":
        return [
            AnalysisOperation(type="aggregate", function="avg", group_by=["instance"]),
            AnalysisOperation(type="filter"),
            AnalysisOperation(type="sort", field="value", direction="desc"),
            AnalysisOperation(type="summarize"),
        ]
    return [
        AnalysisOperation(type="aggregate", function="avg"),
        AnalysisOperation(type="summarize"),
    ]


class InspectionPlanner:
    """把 InspectionIntent 编译为不可变的 InspectionPlan。"""

    def __init__(
        self,
        settings: Settings,
        provider: BaseMetricProvider,
        policies: Policies,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.policies = policies
        self.logger = get_logger("planner")

    def build(self, intent: InspectionIntent) -> InspectionPlan:
        target = self._resolve_target(intent)
        metrics = self._select_metrics(intent)
        operations = self._normalize_operations(intent)
        definitions = {d.metric_id: d for d in self.provider.supported_metrics()}
        validate_operations(operations, metrics, definitions)
        queries = self._build_queries(intent, target, metrics)
        if len(queries) > self.settings.max_query_count:
            raise PlanValidationError(
                f"计划查询数 {len(queries)} 超过上限 {self.settings.max_query_count}"
            )
        return InspectionPlan(
            request_id=current_request_id() or new_request_id(),
            task_type=intent.task_type,
            provider_skill=getattr(self.provider, "name", "server_metric"),
            target=target,
            metrics=metrics,
            operations=operations,
            queries=queries,
            max_query_count=self.settings.max_query_count,
            timeout_seconds=int(self.settings.prometheus_timeout_seconds * 4),
            report_mode=self.settings.report_mode,  # type: ignore[arg-type]
        )

    def _normalize_operations(self, intent: InspectionIntent) -> list[AnalysisOperation]:
        """模型给出的算子可能不完整；补齐取数与汇总阶段，否则回退默认组合。"""
        limit = intent.limit or self.settings.default_limit
        defaults = default_operations(intent.task_type, limit)
        if not intent.operations:
            return defaults
        operations = list(intent.operations)
        # 缺少取数算子时，模型输出不可用，直接使用默认组合。
        if not any(op.type in SERIES_OPERATORS for op in operations):
            return defaults
        # 缺少汇总算子时补上，保证报告有结构化输出。
        if operations[-1].type != "summarize" and not any(
            op.type == "summarize" for op in operations
        ):
            operations.append(AnalysisOperation(type="summarize"))
        return operations

    def _resolve_target(self, intent: InspectionIntent) -> ServerTarget:
        if intent.scope == "all":
            if not self.provider.all_targets():
                raise TargetNotFoundError("资产目录为空，无法执行授权范围查询")
            return ServerTarget(scope="all", reference="全部授权实例", labels={})

        if not intent.instance:
            raise TargetNotFoundError("未指定实例")
        resolved = self.provider.resolve_target(intent.instance)
        if resolved is None:
            raise TargetNotFoundError(f"未找到对应实例：{intent.instance}")
        return ServerTarget(
            scope="instance",
            reference=intent.instance,
            resource_id=resolved.resource_id,
            prometheus_instance=resolved.prometheus_instance,
            labels=resolved.labels,
        )

    def _select_metrics(self, intent: InspectionIntent) -> list[str]:
        known = {d.metric_id for d in self.provider.supported_metrics()}
        requested = [m for m in intent.metrics if m in known]
        if requested:
            return requested
        # 用户点名了指标但都不在允许列表：交给上层触发一次 LLM 纠错，
        # 把口语化或错别字的指标名映射到最接近的合法指标。
        if intent.metrics:
            unknown = [m for m in intent.metrics if m not in known]
            raise PlanValidationError(
                f"未声明支持的指标: {unknown}，允许的指标: {sorted(known)}"
            )
        defaults = _DEFAULT_METRICS.get(intent.task_type, ["cpu"])
        return [m for m in defaults if m in known]

    def _build_queries(
        self,
        intent: InspectionIntent,
        target: ServerTarget,
        metrics: list[str],
    ) -> list[MetricQueryPlan]:
        now = datetime.now(timezone.utc)
        if intent.task_type == "period_comparison":
            queries: list[MetricQueryPlan] = []
            for name, window in resolve_periods(intent.periods, self.settings, now):
                queries.extend(
                    self.provider.plan_queries(
                        target, metrics, window, scope=target.scope, period=name
                    )
                )
            return queries

        if intent.time_range is None:
            raise PlanValidationError("执行计划缺少时间范围")
        if intent.task_type in {"historical_anomaly_summary", "trend_analysis"}:
            check_range(intent.time_range, self.settings, "历史查询范围")
        return self.provider.plan_queries(
            target, metrics, intent.time_range, scope=target.scope
        )


__all__ = ["InspectionPlanner", "default_operations"]
