from __future__ import annotations


class InspectionError(Exception):
    """巡检 Agent 的基类异常。"""

    code = "inspection_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(InspectionError):
    """配置缺失或非法。"""

    code = "configuration_error"


class IntentError(InspectionError):
    """模型输出或规则解析无法得到合法意图。"""

    code = "intent_error"


class PlanValidationError(InspectionError):
    """计划校验失败。校验失败时不允许访问 Prometheus。"""

    code = "plan_validation_error"


class TargetNotFoundError(InspectionError):
    """资产目录中不存在目标实例，禁止访问 Prometheus。"""

    code = "not_found"


class ProviderNotFoundError(InspectionError):
    """没有为指定 resource_type 注册专项 Skill。"""

    code = "provider_not_found"


class QueryError(InspectionError):
    """Prometheus 查询失败。"""

    code = "query_error"


__all__ = [
    "InspectionError",
    "ConfigurationError",
    "IntentError",
    "PlanValidationError",
    "TargetNotFoundError",
    "ProviderNotFoundError",
    "QueryError",
]
