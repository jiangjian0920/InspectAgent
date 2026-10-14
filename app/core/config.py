from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from app.core.errors import ConfigurationError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "configs"


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"环境变量 {name} 必须是数字，当前值: {raw}") from exc


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"环境变量 {name} 必须是整数，当前值: {raw}") from exc


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LLMSettings:
    """GLM 调用配置。模型只负责意图与计划生成，以及可选的报告摘要。"""

    api_key: str = ""
    model: str = "glm-5.3"
    base_url: str = ""
    timeout_seconds: float = 180.0
    temperature: float = 0.1

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class Settings:
    """运行期配置。字段默认值让离线测试无需任何环境变量即可运行。"""

    prometheus_url: str = "http://127.0.0.1:9090"
    prometheus_timeout_seconds: float = 30.0
    default_time_range: str = "2h"
    default_step_seconds: int = 60
    max_time_range_days: int = 30
    max_query_count: int = 40
    max_series: int = 200
    default_limit: int = 10
    report_mode: str = "template"
    log_level: str = "INFO"
    config_dir: Path = field(default_factory=lambda: DEFAULT_CONFIG_DIR)
    assets_path: Path | None = None
    policies_path: Path | None = None
    server_skill_dir: Path | None = None
    llm: LLMSettings = field(default_factory=LLMSettings)

    def resolved_assets_path(self) -> Path:
        return self.assets_path or (self.config_dir / "assets.yaml")

    def resolved_policies_path(self) -> Path:
        return self.policies_path or (self.config_dir / "policies.yaml")

    def resolved_server_skill_dir(self) -> Path:
        if self.server_skill_dir:
            return self.server_skill_dir
        return PROJECT_ROOT / "app" / "skills" / "providers" / "server"


def load_settings(dotenv_path: str | None = None) -> Settings:
    """从环境变量读取配置。"""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv 是可选的
        load_dotenv = None
    if load_dotenv is not None:
        load_dotenv(dotenv_path=dotenv_path, override=False)

    config_dir_raw = os.getenv("CONFIG_DIR", "").strip()
    config_dir = Path(config_dir_raw).expanduser().resolve() if config_dir_raw else DEFAULT_CONFIG_DIR

    def _path(name: str) -> Path | None:
        raw = os.getenv(name, "").strip()
        return Path(raw).expanduser().resolve() if raw else None

    llm = LLMSettings(
        api_key=os.getenv("ZHIPU_API_KEY", "").strip(),
        model=os.getenv("ZHIPU_MODEL", "glm-5.3").strip() or "glm-5.3",
        base_url=os.getenv("ZHIPU_BASE_URL", "").strip(),
        timeout_seconds=_float_env("ZHIPU_TIMEOUT_SECONDS", 180),
        temperature=_float_env("ZHIPU_TEMPERATURE", 0.1),
    )
    report_mode = os.getenv("REPORT_MODE", "template").strip().lower() or "template"
    if report_mode not in {"template", "llm_summary"}:
        raise ConfigurationError("REPORT_MODE 只能是 template 或 llm_summary")
    if report_mode == "llm_summary" and not llm.enabled:
        raise ConfigurationError("REPORT_MODE=llm_summary 需要配置 ZHIPU_API_KEY")

    return Settings(
        prometheus_url=os.getenv("PROMETHEUS_URL", "http://127.0.0.1:9090").rstrip("/"),
        prometheus_timeout_seconds=_float_env("PROMETHEUS_TIMEOUT_SECONDS", 30),
        default_time_range=os.getenv("DEFAULT_TIME_RANGE", "2h").strip() or "2h",
        default_step_seconds=_int_env("DEFAULT_STEP_SECONDS", 60),
        max_time_range_days=_int_env("MAX_TIME_RANGE_DAYS", 30),
        max_query_count=_int_env("MAX_QUERY_COUNT", 40),
        max_series=_int_env("MAX_SERIES", 200),
        default_limit=_int_env("DEFAULT_LIMIT", 10),
        report_mode=report_mode,
        log_level=os.getenv("LOG_LEVEL", "INFO").strip() or "INFO",
        config_dir=config_dir,
        assets_path=_path("ASSETS_PATH"),
        policies_path=_path("POLICIES_PATH"),
        server_skill_dir=_path("SERVER_SKILL_DIR"),
        llm=llm,
    )


__all__ = ["Settings", "LLMSettings", "load_settings", "PROJECT_ROOT", "DEFAULT_CONFIG_DIR"]
