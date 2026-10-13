from __future__ import annotations

from typing import Any

from agent.inspection.host_metrics import HOST_METRICS


# 主机指标目录来自 host_metrics；下面是 Redis / Kafka / K8s 各自的指标定义。
SERVER_METRICS = HOST_METRICS

REDIS_METRICS: list[dict[str, Any]] = [
    {
        "key": "up",
        "name": "Redis存活",
        "meaning": "redis_exporter 探活，0 表示实例不可用",
        "promql": "redis_up",
        "unit": "",
        "warning_attr": "redis_up_warning",
        "critical_attr": "redis_up_critical",
        "compare": "lte",
        "business_impact": "Redis 宕机会导致缓存穿透、会话丢失和依赖该实例的服务不可用。",
    },
    {
        "key": "memory",
        "name": "Redis内存使用率",
        "meaning": "used_memory / maxmemory，maxmemory 为 0 时无法计算上限",
        "promql": "(redis_memory_used_bytes / clamp_min(redis_memory_max_bytes, 1)) * 100",
        "unit": "%",
        "warning_attr": "redis_memory_warning",
        "critical_attr": "redis_memory_critical",
        "business_impact": "内存打满会触发逐出或 OOM，造成缓存雪崩。",
    },
    {
        "key": "clients",
        "name": "Redis已连接客户端",
        "meaning": "当前客户端连接数",
        "promql": "redis_connected_clients",
        "unit": "",
        "warning_attr": "redis_clients_warning",
        "critical_attr": "redis_clients_critical",
        "business_impact": "连接数过高可能耗尽文件句柄，新请求无法接入。",
    },
    {
        "key": "blocked",
        "name": "Redis阻塞客户端",
        "meaning": "因 BLPOP 等命令阻塞的客户端数量",
        "promql": "redis_blocked_clients",
        "unit": "",
        "warning_attr": "redis_blocked_warning",
        "critical_attr": "redis_blocked_critical",
        "business_impact": "阻塞客户端堆积通常意味着消费端卡住或慢查询。",
    },
    {
        "key": "rejected",
        "name": "Redis拒绝连接速率",
        "meaning": "因 maxclients 被拒绝的连接速率",
        "promql": "rate(redis_rejected_connections_total[5m])",
        "unit": "conn/s",
        "warning_attr": "redis_rejected_warning",
        "critical_attr": "redis_rejected_critical",
        "business_impact": "持续拒绝连接说明连接池打满，业务会报错。",
    },
    {
        "key": "ops",
        "name": "Redis每秒命令数",
        "meaning": "instantaneous_ops_per_sec，反映 QPS 压力",
        "promql": "redis_instantaneous_ops_per_sec",
        "unit": "ops/s",
        "warning_attr": "redis_ops_warning",
        "critical_attr": "redis_ops_critical",
        "business_impact": "QPS 持续超阈值会导致延迟升高和 CPU 打满。",
    },
]

KAFKA_METRICS: list[dict[str, Any]] = [
    {
        "key": "brokers",
        "name": "Kafka Broker数量",
        "meaning": "当前可见 broker 数，过低表示集群不完整",
        "promql": "kafka_brokers",
        "unit": "",
        "warning_attr": "kafka_brokers_warning",
        "critical_attr": "kafka_brokers_critical",
        "compare": "lte",
        "business_impact": "Broker 减少会导致分区无法选举、生产消费中断。",
    },
    {
        "key": "under_replicated",
        "name": "Kafka未充分副本分区",
        "meaning": "under-replicated partitions，大于 0 即副本落后",
        "promql": "sum(kafka_topic_partition_under_replicated_partition) or vector(0)",
        "unit": "",
        "warning_attr": "kafka_under_replicated_warning",
        "critical_attr": "kafka_under_replicated_critical",
        "business_impact": "副本不足时再丢一台 broker 会丢数据或不可用。",
    },
    {
        "key": "offline",
        "name": "Kafka离线分区",
        "meaning": "没有 leader 的分区数量",
        "promql": "sum(kafka_controller_kafkacontroller_offlinepartitionscount) or vector(0)",
        "unit": "",
        "warning_attr": "kafka_offline_warning",
        "critical_attr": "kafka_offline_critical",
        "business_impact": "离线分区无法读写，对应 Topic 业务中断。",
    },
    {
        "key": "lag",
        "name": "Kafka消费组Lag",
        "meaning": "消费滞后消息数",
        "promql": "sum by(consumergroup, topic) (kafka_consumergroup_lag)",
        "unit": "",
        "warning_attr": "kafka_lag_warning",
        "critical_attr": "kafka_lag_critical",
        "business_impact": "Lag 持续升高意味着消费跟不上，数据积压和延迟增大。",
    },
]

K8S_METRICS: list[dict[str, Any]] = [
    {
        "key": "restarts",
        "name": "Pod容器重启次数",
        "meaning": "容器累计重启次数，升高通常伴随 CrashLoop",
        "promql": "sum by(namespace, pod, container) (kube_pod_container_status_restarts_total)",
        "unit": "",
        "warning_attr": "k8s_restarts_warning",
        "critical_attr": "k8s_restarts_critical",
        "business_impact": "频繁重启会导致服务抖动、就绪探针失败和流量丢失。",
    },
    {
        "key": "cpu",
        "name": "容器CPU使用率",
        "meaning": "相对 requests 的 CPU 使用百分比",
        "promql": '(sum by(namespace, pod, container) (rate(container_cpu_usage_seconds_total{container!="",container!="POD"}[5m])) / clamp_min(sum by(namespace, pod, container) (kube_pod_container_resource_requests{resource="cpu"}), 0.001)) * 100',
        "unit": "%",
        "warning_attr": "k8s_cpu_warning",
        "critical_attr": "k8s_cpu_critical",
        "business_impact": "CPU 打满会导致限流、延迟升高和 Pod 被节流。",
    },
    {
        "key": "memory",
        "name": "容器内存使用率",
        "meaning": "working_set / limits，接近 100% 可能 OOMKilled",
        "promql": '(sum by(namespace, pod, container) (container_memory_working_set_bytes{container!="",container!="POD"}) / clamp_min(sum by(namespace, pod, container) (kube_pod_container_resource_limits{resource="memory"}), 1)) * 100',
        "unit": "%",
        "warning_attr": "k8s_memory_warning",
        "critical_attr": "k8s_memory_critical",
        "business_impact": "内存触顶会触发 OOMKilled，业务中断。",
    },
    {
        "key": "not_ready",
        "name": "未就绪Pod",
        "meaning": "Ready=false 的 Pod 数量",
        "promql": 'sum by(namespace, pod) (kube_pod_status_ready{condition="false"})',
        "unit": "",
        "warning_attr": "k8s_not_ready_warning",
        "critical_attr": "k8s_not_ready_critical",
        "business_impact": "未就绪 Pod 不会承接流量，副本不足时服务降级。",
    },
]


def catalog_for(target_type: str) -> list[dict[str, Any]]:
    """按对象类型返回对应的指标目录。"""
    mapping = {
        "server": SERVER_METRICS,
        "redis": REDIS_METRICS,
        "kafka": KAFKA_METRICS,
        "k8s": K8S_METRICS,
    }
    return list(mapping.get(target_type, []))
