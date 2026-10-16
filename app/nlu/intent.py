from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from app.core.config import Settings
from app.core.errors import IntentError
from app.core.logging import get_logger
from app.core.timeparse import resolve_named_period, resolve_relative_range
from app.domain.enums import TaskType
from app.domain.models import InspectionIntent, NamedTimeRange
from app.nlu import fallback
from app.nlu.client import GLMClient
from app.nlu.schema import ModelIntent


_SYSTEM_PROMPT = (
    "你是服务器巡检意图解析器。只把用户的自然语言请求转换为 JSON，不生成 PromQL，"
    "不访问任何监控系统，不编造监控数据。只输出一个 JSON 对象，不要输出解释或 Markdown。"
)

_REPAIR_SYSTEM_PROMPT = (
    "你是服务器巡检计划修正器。上一次计划未通过校验，请按错误提示和允许列表修正，"
    "只输出一个 JSON 对象，不生成 PromQL，不访问监控系统，不编造数据，不输出解释或 Markdown。"
)

_ALLOWED_TASKS = [
    "instant_inspection",
    "historical_anomaly_summary",
    "period_comparison",
    "trend_analysis",
    "ranking_query",
    "threshold_filter",
]
_ALLOWED_METRICS = ["cpu", "memory", "disk", "availability"]

# 计划校验失败后允许的 LLM 纠错次数上限。
MAX_REPAIR_ATTEMPTS = 1


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise IntentError("模型没有返回 JSON 对象")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise IntentError(f"模型返回的 JSON 无法解析: {exc}") from exc


def _describe_error(exc: Exception) -> str:
    """把 pydantic 校验错误展开成单行详情，便于定位失败的字段。"""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            details = errors()
        except Exception:  # pragma: no cover - 防御性
            details = []
        if details:
            parts = []
            for detail in details:
                loc = ".".join(str(item) for item in detail.get("loc", ())) or "<root>"
                parts.append(f"{loc}: {detail.get('msg')}（输入={detail.get('input')!r}）")
            return "; ".join(parts)
    return str(exc).replace("\n", " ").strip()


class IntentService:
    """把自然语言转换为受控的 InspectionIntent。"""

    def __init__(self, settings: Settings, llm: GLMClient | None = None) -> None:
        self.settings = settings
        self.llm = llm
        self.logger = get_logger("intent")

    def parse(self, instruction: str) -> InspectionIntent:
        draft: ModelIntent
        source = "fallback"
        if self.llm is not None:
            try:
                raw = self.llm.complete(
                    [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": self._build_prompt(instruction)},
                    ]
                )
                draft = ModelIntent.model_validate(_extract_json(raw))
                source = "llm"
            except Exception as exc:  # 模型失败时回退，不影响可用性
                self.logger.warning("GLM 意图解析失败，改用规则回退: %s", _describe_error(exc))
                draft = fallback.parse(instruction)
        else:
            draft = fallback.parse(instruction)
        return self._normalize(draft, instruction, source)

    def can_repair(self) -> bool:
        """只有启用 GLM 时才具备纠错能力。"""
        return self.llm is not None

    def repair(
        self,
        instruction: str,
        intent: InspectionIntent,
        error: str,
        *,
        allowed_metrics: list[str] | None = None,
        allowed_operators: list[str] | None = None,
    ) -> InspectionIntent | None:
        """计划校验失败后，把错误与合法列表回传 GLM 请求一次修正。

        最多调用一次。任何失败都返回 None，由调用方给出原始报错。
        """
        if self.llm is None:
            return None
        metrics = allowed_metrics or _ALLOWED_METRICS
        operators = allowed_operators or []
        try:
            raw = self.llm.complete(
                [
                    {"role": "system", "content": _REPAIR_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": self._build_repair_prompt(
                            instruction, intent, error, metrics, operators
                        ),
                    },
                ]
            )
            draft = ModelIntent.model_validate(_extract_json(raw))
            repaired = self._normalize(draft, instruction, "llm_repair")
        except Exception as exc:  # 纠错失败不影响最终报错
            self.logger.warning("GLM 纠错失败: %s", _describe_error(exc))
            return None
        self.logger.info("GLM 纠错已生成新意图: task=%s metrics=%s", repaired.task_type, repaired.metrics)
        return repaired

    def _build_repair_prompt(
        self,
        instruction: str,
        intent: InspectionIntent,
        error: str,
        allowed_metrics: list[str],
        allowed_operators: list[str],
    ) -> str:
        now = datetime.now(timezone.utc).isoformat()
        previous = json.dumps(
            {
                "task_type": intent.task_type,
                "target": {"type": intent.target_type, "instance": intent.instance, "scope": intent.scope},
                "metrics": intent.metrics,
                "operations": [op.model_dump(exclude_defaults=True) for op in intent.operations],
                "periods": [p.model_dump() for p in intent.periods],
            },
            ensure_ascii=False,
        )
        return (
            "上一次生成的计划未通过校验，请修正后重新输出完整 JSON。\n"
            f"当前时间(UTC): {now}\n"
            f"校验错误: {error}\n"
            f"允许的 task_type: {_ALLOWED_TASKS}\n"
            f"允许的 metrics: {allowed_metrics}\n"
            f"允许的算子: {allowed_operators}\n"
            "约束：\n"
            "- metrics 必须是允许列表中的英文标识，把口语化或错别字的指标名映射到最接近的合法指标。\n"
            "- operations 元素必须是对象；limit 必须出现在 sort 之后；summarize 必须是最后一个算子。\n"
            "- period_comparison 必须提供两个不重叠且长度相近的时间段。\n"
            f"上一次输出: {previous}\n"
            f"用户请求: {instruction}\n"
            "只输出修正后的 JSON。"
        )

    def _build_prompt(self, instruction: str) -> str:
        now = datetime.now(timezone.utc).isoformat()
        return (
            f"当前时间(UTC): {now}\n"
            f"允许的 task_type: {_ALLOWED_TASKS}\n"
            f"允许的 metrics: {_ALLOWED_METRICS}\n"
            f"最大时间范围（天）: {self.settings.max_time_range_days}\n"
            "task_type 取值说明：\n"
            "- instant_inspection: 单实例当前状态或指标\n"
            "- historical_anomaly_summary: 最近 N 天异常清单\n"
            "- period_comparison: 两个时间段对比（需 periods）\n"
            "- trend_analysis: 一段时间趋势\n"
            "- ranking_query: 排序 Top N（授权范围全部实例）\n"
            "- threshold_filter: 阈值筛选（授权范围全部实例）\n"
            "可选的 operations 使用受控 DSL，元素必须是对象，算子仅限："
            "aggregate/group_by/filter/sort/limit/compare/trend/detect_anomaly/summarize。\n"
            'operations 示例：[{"type":"aggregate","function":"avg","group_by":["instance"]},'
            '{"type":"sort","field":"value","direction":"desc"},{"type":"limit","count":10},'
            '{"type":"summarize"}]。不要输出字符串算子。\n'
            '示例：{"task_type":"period_comparison","target":{"type":"server",'
            '"instance":"192.168.59.130"},"metrics":["cpu","memory"],'
            '"periods":[{"name":"today","start":"today 00:00","end":"now"},'
            '{"name":"yesterday","start":"yesterday 00:00","end":"yesterday 23:59:59"}]}\n'
            f"用户请求: {instruction}\n"
            "只输出 JSON。"
        )

    def _normalize(self, draft: ModelIntent, instruction: str, source: str) -> InspectionIntent:
        now = datetime.now(timezone.utc)
        task: TaskType = draft.task_type
        if task not in _ALLOWED_TASKS:
            raise IntentError(f"不支持的任务类型: {task}")

        # 只做轻量规范化，不在此过滤未知指标；允许列表由计划校验器统一把关，
        # 未知指标会在计划校验阶段触发一次 LLM 纠错。
        metrics: list[str] = []
        for raw_metric in draft.metrics:
            key = str(raw_metric).strip().lower()
            if key and key not in metrics:
                metrics.append(key)

        target = draft.target
        instance = (target.instance or "").strip() or None
        scope = target.scope or ("all" if instance is None and task in {
            "ranking_query",
            "threshold_filter",
            "historical_anomaly_summary",
        } else "instance")
        if task in {"ranking_query", "threshold_filter"}:
            scope = "all"

        base_step = self.settings.default_step_seconds
        time_range = None
        periods: list[NamedTimeRange] = []

        if task == "period_comparison":
            raw_periods = draft.periods or [
                _default_period("today"),
                _default_period("yesterday"),
            ]
            for period in raw_periods[:2]:
                resolve_named_period(
                    NamedTimeRange(name=period.name, start=period.start, end=period.end),
                    now,
                    base_step,
                )
            periods = [
                NamedTimeRange(name=p.name, start=p.start, end=p.end) for p in raw_periods[:2]
            ]
            if len(periods) < 2:
                raise IntentError("时段对比需要两个时间段")
        elif task in {"historical_anomaly_summary", "trend_analysis"}:
            expr = (draft.time_range.value if draft.time_range else "") or self.settings.default_time_range
            time_range, _ = resolve_relative_range(
                expr,
                now,
                _default_window_seconds(self.settings.default_time_range),
                base_step,
            )
        else:
            time_range, _ = resolve_relative_range(
                self.settings.default_time_range,
                now,
                _default_window_seconds(self.settings.default_time_range),
                base_step,
            )

        return InspectionIntent(
            task_type=task,
            target_type="server",
            instance=instance,
            scope=scope,  # type: ignore[arg-type]
            metrics=metrics,
            time_range=time_range,
            periods=periods,
            operations=list(draft.operations),
            limit=draft.limit,
            raw_request=instruction,
            source=source,
        )


def _default_period(name: str):
    from app.nlu.schema import ModelPeriod

    if name == "today":
        return ModelPeriod(name="today", start="today 00:00", end="now")
    return ModelPeriod(name="yesterday", start="yesterday 00:00", end="yesterday 23:59:59")


def _default_window_seconds(default_time_range: str) -> float:
    from app.core.timeparse import duration_seconds

    parsed = duration_seconds(default_time_range)
    return parsed if parsed is not None else 7200.0


__all__ = ["IntentService"]
