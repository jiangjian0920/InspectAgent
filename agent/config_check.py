from __future__ import annotations

from pathlib import Path

from agent.config import Settings


PLACEHOLDER_KEYS = {"", "your-zhipu-api-key-here", "changeme", "your_api_key"}


def check_settings(settings: Settings, env_path: str = ".env") -> list[str]:
    issues: list[str] = []
    if settings.zhipu_api_key.strip() in PLACEHOLDER_KEYS:
        issues.append("ZHIPU_API_KEY 未配置，请复制 .env.example 为 .env 并填写智谱密钥。")
    if not settings.prometheus_url:
        issues.append("PROMETHEUS_URL 不能为空。")
    if settings.max_tool_rounds <= 0:
        issues.append("MAX_TOOL_ROUNDS 必须大于 0。")
    if settings.zhipu_timeout_seconds <= 0:
        issues.append("ZHIPU_TIMEOUT_SECONDS 必须大于 0。")
    if settings.prometheus_timeout_seconds <= 0:
        issues.append("PROMETHEUS_TIMEOUT_SECONDS 必须大于 0。")
    thresholds = settings.thresholds
    pairs = [
        ("CPU", thresholds.cpu_warning, thresholds.cpu_critical),
        ("内存", thresholds.memory_warning, thresholds.memory_critical),
        ("磁盘", thresholds.disk_warning, thresholds.disk_critical),
        ("磁盘IO", thresholds.disk_io_util_warning, thresholds.disk_io_util_critical),
        ("负载", thresholds.load1_warning, thresholds.load1_critical),
        ("网络接收", thresholds.network_rx_mbps_warning, thresholds.network_rx_mbps_critical),
        ("网络发送", thresholds.network_tx_mbps_warning, thresholds.network_tx_mbps_critical),
        ("Redis内存", thresholds.redis_memory_warning, thresholds.redis_memory_critical),
        ("Kafka Lag", thresholds.kafka_lag_warning, thresholds.kafka_lag_critical),
        ("K8s CPU", thresholds.k8s_cpu_warning, thresholds.k8s_cpu_critical),
        ("K8s 内存", thresholds.k8s_memory_warning, thresholds.k8s_memory_critical),
    ]
    for name, warning, critical in pairs:
        if warning > critical:
            issues.append(f"{name} 警告阈值 {warning} 大于严重阈值 {critical}。")
    if not Path(env_path).exists() and not Path(".env").exists():
        issues.append("未找到 .env，当前使用默认配置；联调前请复制 .env.example。")
    return issues


def format_check_report(settings: Settings, issues: list[str]) -> str:
    lines = [
        "配置检查（不调用外部接口）",
        f"- 模型：{settings.zhipu_model}",
        f"- Prometheus：{settings.prometheus_url}",
        f"- 默认时间范围：{settings.default_time_range}",
        f"- 最大工具轮次：{settings.max_tool_rounds}",
        f"- 已注册 Skill：server_inspect / redis_inspect / kafka_inspect / k8s_inspect",
        f"- API Key：{'已填写' if settings.zhipu_api_key.strip() not in PLACEHOLDER_KEYS else '未填写'}",
    ]
    if issues:
        lines.append("- 结果：存在配置问题")
        for item in issues:
            lines.append(f"  - {item}")
    else:
        lines.append("- 结果：配置检查通过")
    return "\n".join(lines)
