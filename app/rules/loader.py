from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.errors import ConfigurationError
from app.domain.models import MetricDefinition, ThresholdRule


class AnomalyPolicy(BaseModel):
    min_consecutive_samples: int = 2
    max_gap_multiplier: float = 2.0
    recover_samples: int = 2


class SignificancePolicy(BaseModel):
    min_absolute_change: float = 5.0
    min_relative_change: float = 0.2


class TrendPolicy(BaseModel):
    sustained_ratio: float = 0.5
    slope_epsilon: float = 0.0


class Policies(BaseModel):
    anomaly: AnomalyPolicy = Field(default_factory=AnomalyPolicy)
    comparison_default: SignificancePolicy = Field(default_factory=SignificancePolicy)
    comparison_by_metric: dict[str, SignificancePolicy] = Field(default_factory=dict)
    trend: TrendPolicy = Field(default_factory=TrendPolicy)
    max_query_count: int = 40
    max_time_range_days: int = 30
    default_limit: int = 10
    max_series: int = 200

    def significance_for(self, metric_id: str) -> SignificancePolicy:
        return self.comparison_by_metric.get(metric_id, self.comparison_default)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigurationError(f"配置文件不存在: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"配置文件解析失败: {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigurationError(f"配置文件顶层必须是映射: {path}")
    return data


def load_policies(settings: Settings) -> Policies:
    """加载全局策略，并用 Settings 中的环境变量覆盖关键限制。"""
    path = settings.resolved_policies_path()
    data = load_yaml(path) if path.exists() else {}
    policies = Policies.model_validate(data)
    return policies.model_copy(
        update={
            "max_query_count": settings.max_query_count,
            "max_time_range_days": settings.max_time_range_days,
            "default_limit": settings.default_limit,
            "max_series": settings.max_series,
        }
    )


def load_metric_catalog(path: Path) -> dict[str, MetricDefinition]:
    """从 YAML 读取某个专项 Skill 的指标目录。"""
    data = load_yaml(path)
    raw_metrics = data.get("metrics")
    if not isinstance(raw_metrics, dict) or not raw_metrics:
        raise ConfigurationError(f"指标目录为空或格式错误: {path}")
    definitions: dict[str, MetricDefinition] = {}
    for metric_id, raw in raw_metrics.items():
        if not isinstance(raw, dict):
            raise ConfigurationError(f"指标定义必须是映射: {path} -> {metric_id}")
        payload = dict(raw)
        payload.setdefault("metric_id", metric_id)
        if "template" in payload and "template_id" not in payload:
            payload["template_id"] = payload.pop("template")
        thresholds_raw = payload.get("thresholds") or {}
        thresholds: dict[str, ThresholdRule] = {}
        for level, spec in thresholds_raw.items():
            thresholds[level] = ThresholdRule.model_validate(spec)
        payload["thresholds"] = thresholds
        definitions[metric_id] = MetricDefinition.model_validate(payload)
    return definitions


def load_query_templates(path: Path) -> dict[str, dict[str, Any]]:
    data = load_yaml(path)
    templates = data.get("templates")
    if not isinstance(templates, dict) or not templates:
        raise ConfigurationError(f"查询模板为空或格式错误: {path}")
    return templates


__all__ = [
    "AnomalyPolicy",
    "SignificancePolicy",
    "TrendPolicy",
    "Policies",
    "load_yaml",
    "load_policies",
    "load_metric_catalog",
    "load_query_templates",
]
