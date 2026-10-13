from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Thresholds:
    """各监控项的警告阈值和严重阈值。"""
    cpu_warning: float
    cpu_critical: float
    memory_warning: float
    memory_critical: float
    disk_warning: float
    disk_critical: float
    disk_io_util_warning: float
    disk_io_util_critical: float
    load1_warning: float
    load1_critical: float
    network_rx_mbps_warning: float
    network_rx_mbps_critical: float
    network_tx_mbps_warning: float
    network_tx_mbps_critical: float
    redis_up_warning: float
    redis_up_critical: float
    redis_memory_warning: float
    redis_memory_critical: float
    redis_clients_warning: float
    redis_clients_critical: float
    redis_blocked_warning: float
    redis_blocked_critical: float
    redis_rejected_warning: float
    redis_rejected_critical: float
    redis_ops_warning: float
    redis_ops_critical: float
    kafka_brokers_warning: float
    kafka_brokers_critical: float
    kafka_under_replicated_warning: float
    kafka_under_replicated_critical: float
    kafka_offline_warning: float
    kafka_offline_critical: float
    kafka_lag_warning: float
    kafka_lag_critical: float
    k8s_restarts_warning: float
    k8s_restarts_critical: float
    k8s_cpu_warning: float
    k8s_cpu_critical: float
    k8s_memory_warning: float
    k8s_memory_critical: float
    k8s_not_ready_warning: float
    k8s_not_ready_critical: float


@dataclass(frozen=True)
class Settings:
    """Agent 运行所需的配置项。"""
    zhipu_api_key: str
    zhipu_model: str
    zhipu_base_url: str
    zhipu_timeout_seconds: float
    prometheus_url: str
    prometheus_timeout_seconds: float
    default_time_range: str
    max_tool_rounds: int
    thresholds: Thresholds


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须是数字，当前值: {raw}") from exc


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须是整数，当前值: {raw}") from exc


def load_settings(dotenv_path: str | None = None) -> Settings:
    """从环境变量读取配置并构造 Settings。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    if load_dotenv is not None:
        load_dotenv(dotenv_path=dotenv_path, override=False)
    prometheus_url = os.getenv("PROMETHEUS_URL", "http://127.0.0.1:9090").rstrip("/")
    thresholds = Thresholds(
        cpu_warning=_float_env("THRESHOLD_CPU_WARNING", 80),
        cpu_critical=_float_env("THRESHOLD_CPU_CRITICAL", 90),
        memory_warning=_float_env("THRESHOLD_MEMORY_WARNING", 80),
        memory_critical=_float_env("THRESHOLD_MEMORY_CRITICAL", 90),
        disk_warning=_float_env("THRESHOLD_DISK_WARNING", 80),
        disk_critical=_float_env("THRESHOLD_DISK_CRITICAL", 90),
        disk_io_util_warning=_float_env("THRESHOLD_DISK_IO_UTIL_WARNING", 80),
        disk_io_util_critical=_float_env("THRESHOLD_DISK_IO_UTIL_CRITICAL", 90),
        load1_warning=_float_env("THRESHOLD_LOAD1_WARNING", 4),
        load1_critical=_float_env("THRESHOLD_LOAD1_CRITICAL", 8),
        network_rx_mbps_warning=_float_env("THRESHOLD_NETWORK_RX_MBPS_WARNING", 800),
        network_rx_mbps_critical=_float_env("THRESHOLD_NETWORK_RX_MBPS_CRITICAL", 950),
        network_tx_mbps_warning=_float_env("THRESHOLD_NETWORK_TX_MBPS_WARNING", 800),
        network_tx_mbps_critical=_float_env("THRESHOLD_NETWORK_TX_MBPS_CRITICAL", 950),
        redis_up_warning=_float_env("THRESHOLD_REDIS_UP_WARNING", 0),
        redis_up_critical=_float_env("THRESHOLD_REDIS_UP_CRITICAL", 0),
        redis_memory_warning=_float_env("THRESHOLD_REDIS_MEMORY_WARNING", 80),
        redis_memory_critical=_float_env("THRESHOLD_REDIS_MEMORY_CRITICAL", 90),
        redis_clients_warning=_float_env("THRESHOLD_REDIS_CLIENTS_WARNING", 5000),
        redis_clients_critical=_float_env("THRESHOLD_REDIS_CLIENTS_CRITICAL", 8000),
        redis_blocked_warning=_float_env("THRESHOLD_REDIS_BLOCKED_WARNING", 10),
        redis_blocked_critical=_float_env("THRESHOLD_REDIS_BLOCKED_CRITICAL", 50),
        redis_rejected_warning=_float_env("THRESHOLD_REDIS_REJECTED_WARNING", 1),
        redis_rejected_critical=_float_env("THRESHOLD_REDIS_REJECTED_CRITICAL", 5),
        redis_ops_warning=_float_env("THRESHOLD_REDIS_OPS_WARNING", 20000),
        redis_ops_critical=_float_env("THRESHOLD_REDIS_OPS_CRITICAL", 50000),
        kafka_brokers_warning=_float_env("THRESHOLD_KAFKA_BROKERS_WARNING", 2),
        kafka_brokers_critical=_float_env("THRESHOLD_KAFKA_BROKERS_CRITICAL", 1),
        kafka_under_replicated_warning=_float_env("THRESHOLD_KAFKA_UNDER_REPLICATED_WARNING", 1),
        kafka_under_replicated_critical=_float_env("THRESHOLD_KAFKA_UNDER_REPLICATED_CRITICAL", 1),
        kafka_offline_warning=_float_env("THRESHOLD_KAFKA_OFFLINE_WARNING", 1),
        kafka_offline_critical=_float_env("THRESHOLD_KAFKA_OFFLINE_CRITICAL", 1),
        kafka_lag_warning=_float_env("THRESHOLD_KAFKA_LAG_WARNING", 10000),
        kafka_lag_critical=_float_env("THRESHOLD_KAFKA_LAG_CRITICAL", 100000),
        k8s_restarts_warning=_float_env("THRESHOLD_K8S_RESTARTS_WARNING", 3),
        k8s_restarts_critical=_float_env("THRESHOLD_K8S_RESTARTS_CRITICAL", 10),
        k8s_cpu_warning=_float_env("THRESHOLD_K8S_CPU_WARNING", 80),
        k8s_cpu_critical=_float_env("THRESHOLD_K8S_CPU_CRITICAL", 95),
        k8s_memory_warning=_float_env("THRESHOLD_K8S_MEMORY_WARNING", 80),
        k8s_memory_critical=_float_env("THRESHOLD_K8S_MEMORY_CRITICAL", 95),
        k8s_not_ready_warning=_float_env("THRESHOLD_K8S_NOT_READY_WARNING", 1),
        k8s_not_ready_critical=_float_env("THRESHOLD_K8S_NOT_READY_CRITICAL", 1),
    )
    return Settings(
        zhipu_api_key=os.getenv("ZHIPU_API_KEY", "").strip(),
        zhipu_model=os.getenv("ZHIPU_MODEL", "glm-5.3").strip() or "glm-5.3",
        zhipu_base_url=os.getenv("ZHIPU_BASE_URL", "").strip(),
        zhipu_timeout_seconds=_float_env("ZHIPU_TIMEOUT_SECONDS", 180),
        prometheus_url=prometheus_url,
        prometheus_timeout_seconds=_float_env("PROMETHEUS_TIMEOUT_SECONDS", 30),
        default_time_range=os.getenv("DEFAULT_TIME_RANGE", "2h").strip() or "2h",
        max_tool_rounds=_int_env("MAX_TOOL_ROUNDS", 1),
        thresholds=thresholds,
    )
