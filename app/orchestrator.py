from __future__ import annotations

from app.analysis.executor import execute_plan
from app.analysis.registry import registered_names
from app.core.config import Settings
from app.core.context import request_context
from app.core.errors import InspectionError, PlanValidationError, QueryError, TargetNotFoundError
from app.core.logging import get_logger, setup_logging
from app.domain.models import InspectionIntent, InspectionPlan, InspectionReport
from app.nlu.client import GLMClient
from app.nlu.intent import IntentService
from app.planner.planner import InspectionPlanner
from app.reporting.builder import (
    build_error_report,
    build_not_found_report,
    build_report,
    target_label,
)
from app.rules.loader import load_policies
from app.skills.base import BaseMetricProvider, MetricCollectionRequest
from app.skills.providers.server.skill import ServerMetricSkill


class InspectionAgent:
    """单轮执行编排器：意图 → 计划 → 校验 → 采集 → 分析 → 报告。"""

    def __init__(
        self,
        settings: Settings,
        provider: BaseMetricProvider | None = None,
        llm: GLMClient | None = None,
    ) -> None:
        self.settings = settings
        setup_logging(settings.log_level)
        self.logger = get_logger("agent")
        self.policies = load_policies(settings)
        self.provider = provider or ServerMetricSkill(settings)
        self.llm = llm
        self.intent_service = IntentService(settings, llm)
        self.planner = InspectionPlanner(settings, self.provider, self.policies)

    def run(self, instruction: str) -> InspectionReport:
        with request_context() as request_id:
            return self._run(instruction, request_id)

    def _run(self, instruction: str, request_id: str) -> InspectionReport:
        intent = self.intent_service.parse(instruction)
        self.logger.info(
            "request_id=%s task=%s scope=%s instance=%s metrics=%s source=%s",
            request_id,
            intent.task_type,
            intent.scope,
            intent.instance,
            intent.metrics,
            intent.source,
        )
        try:
            plan = self.planner.build(intent)
        except TargetNotFoundError as exc:
            self.logger.info("request_id=%s 实例未命中资产目录: %s", request_id, exc)
            target = intent.instance or "未知实例"
            return build_not_found_report(request_id, intent.task_type, target, str(exc))
        except PlanValidationError as exc:
            self.logger.warning("request_id=%s 计划校验失败: %s", request_id, exc)
            plan = self._repair_plan(instruction, intent, str(exc), request_id)
            if plan is None:
                return build_error_report(
                    request_id,
                    intent.task_type,
                    intent.instance or "全部授权实例",
                    str(exc),
                    status="no_capability",
                    scope=intent.metrics,
                )

        self.logger.info(
            "request_id=%s 计划已生成 queries=%d operations=%s",
            request_id,
            len(plan.queries),
            [op.type for op in plan.operations],
        )

        try:
            series = self._collect(plan)
        except QueryError as exc:
            self.logger.error("request_id=%s 查询预算/查询失败: %s", request_id, exc)
            return build_error_report(
                request_id,
                intent.task_type,
                target_label(plan),
                str(exc),
                status="data_source_error",
                scope=plan.metrics,
            )
        except InspectionError as exc:
            self.logger.error("request_id=%s 采集失败: %s", request_id, exc)
            return build_error_report(
                request_id,
                intent.task_type,
                target_label(plan),
                str(exc),
                status="data_source_error",
                scope=plan.metrics,
            )

        definitions = {d.metric_id: d for d in self.provider.supported_metrics()}
        state = execute_plan(
            plan,
            series,
            definitions,
            self.policies,
            target_label=target_label(plan),
            time_range_label=self._time_label(plan),
        )
        report = build_report(plan, series, state)
        report = self._maybe_summarize(plan, report)
        return report

    def _repair_plan(
        self,
        instruction: str,
        intent: InspectionIntent,
        error: str,
        request_id: str,
    ) -> InspectionPlan | None:
        """计划校验失败后给 GLM 一次纠错机会；不成功返回 None。"""
        if not self.intent_service.can_repair():
            return None
        repaired_intent = self.intent_service.repair(
            instruction,
            intent,
            error,
            allowed_metrics=[d.metric_id for d in self.provider.supported_metrics()],
            allowed_operators=registered_names(),
        )
        if repaired_intent is None:
            self.logger.info("request_id=%s 未获得有效的纠错结果", request_id)
            return None
        try:
            plan = self.planner.build(repaired_intent)
        except (PlanValidationError, TargetNotFoundError) as exc:
            self.logger.warning("request_id=%s 纠错后仍未通过校验: %s", request_id, exc)
            return None
        self.logger.info("request_id=%s 纠错后计划已生成", request_id)
        return plan

    def _collect(self, plan: InspectionPlan):
        resource_id = plan.target.resource_id or plan.target.reference or "all"
        time_range = plan.queries[0].time_range if plan.queries else plan.created_at
        request = MetricCollectionRequest(
            resource_id=resource_id,
            target=plan.target,
            metric_ids=plan.metrics,
            queries=plan.queries,
            time_range=time_range,
            period=plan.queries[0].period if plan.queries else None,
        )
        return self.provider.collect(request)

    @staticmethod
    def _time_label(plan: InspectionPlan) -> str:
        periods = sorted({q.period for q in plan.queries if q.period})
        if periods:
            return " / ".join(periods)
        if plan.queries:
            window = plan.queries[0].time_range
            return f"{window.start:%Y-%m-%d %H:%M} ~ {window.end:%Y-%m-%d %H:%M}"
        return ""

    def _maybe_summarize(self, plan: InspectionPlan, report: InspectionReport) -> InspectionReport:
        if plan.report_mode != "llm_summary" or self.llm is None:
            return report
        facts = report.model_dump(mode="json")
        try:
            text = self.llm.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是巡检报告摘要器。只根据提供的结构化事实改写为自然语言，"
                            "不补充原因、不预测、不编造指标；数据缺失或查询失败必须说明无法判断。"
                        ),
                    },
                    {"role": "user", "content": str(facts)},
                ]
            )
        except Exception as exc:  # 摘要失败不影响模板报告
            self.logger.warning("报告摘要失败，保留模板报告: %s", exc)
            return report
        if text.strip():
            return report.model_copy(update={"summary": text.strip()})
        return report


__all__ = ["InspectionAgent"]
