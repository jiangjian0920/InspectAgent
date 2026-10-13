from __future__ import annotations

from typing import Any


HOST_METRICS: list[dict[str, Any]] = [
    {
        "key": "cpu",
        "name": "CPU使用率",
        "meaning": "主机 CPU 非空闲时间占比，反映计算资源繁忙程度",
        "promql": '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
        "unit": "%",
        "warning_attr": "cpu_warning",
        "critical_attr": "cpu_critical",
        "business_impact": "CPU 持续高位会导致请求排队、接口超时、任务堆积。",
        "check_commands": [
            "top -bn1 | head -n 20",
            "pidstat -u 1 5",
            "uptime",
        ],
        "optimize_suggestions": [
            "定位占用 CPU 最高的进程，评估限流、扩容或优化热点代码。需要人工确认后执行。",
        ],
        "followups": [
            {
                "key": "cpu_iowait",
                "name": "CPU iowait占比",
                "meaning": "CPU 等待磁盘 IO 的时间占比，升高通常伴随磁盘瓶颈",
                "promql": 'avg by(instance) (rate(node_cpu_seconds_total{mode="iowait"}[5m])) * 100',
                "unit": "%",
            },
            {
                "key": "cpu_user",
                "name": "CPU user占比",
                "meaning": "用户态 CPU 占比，用于判断是否为计算型热点",
                "promql": 'avg by(instance) (rate(node_cpu_seconds_total{mode="user"}[5m])) * 100',
                "unit": "%",
            },
            {
                "key": "cpu_cores",
                "name": "CPU逻辑核数",
                "meaning": "用于把系统负载换算成相对核数的压力",
                "promql": 'count by(instance) (node_cpu_seconds_total{mode="idle"})',
                "unit": "核",
            },
        ],
    },
    {
        "key": "memory",
        "name": "内存使用率",
        "meaning": "已用内存占物理内存比例，基于 MemAvailable 计算真实可用压力",
        "promql": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100",
        "unit": "%",
        "warning_attr": "memory_warning",
        "critical_attr": "memory_critical",
        "business_impact": "内存不足会触发回收、Swap 抖动甚至 OOM，造成进程被杀和服务中断。",
        "check_commands": [
            "free -h",
            "ps aux --sort=-%mem | head -n 20",
            "dmesg | grep -i 'out of memory'",
        ],
        "optimize_suggestions": [
            "确认是否存在内存泄漏或缓存过大，评估扩容或限制进程内存。需要人工确认后执行。",
        ],
        "followups": [
            {
                "key": "memory_available",
                "name": "内存Available",
                "meaning": "系统估算的可回收后仍可用内存",
                "promql": "node_memory_MemAvailable_bytes",
                "unit": "bytes",
            },
            {
                "key": "swap_used",
                "name": "Swap使用率",
                "meaning": "Swap 占用升高说明物理内存已经不够用",
                "promql": "(1 - (node_memory_SwapFree_bytes / clamp_min(node_memory_SwapTotal_bytes, 1))) * 100",
                "unit": "%",
            },
        ],
    },
    {
        "key": "disk",
        "name": "磁盘使用率",
        "meaning": "文件系统已用空间占比，接近满盘会导致写入失败",
        "promql": '(1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"})) * 100',
        "unit": "%",
        "warning_attr": "disk_warning",
        "critical_attr": "disk_critical",
        "business_impact": "磁盘空间耗尽会导致日志、数据库、容器写入失败，服务不可用。",
        "check_commands": [
            "df -hT",
            "du -xh --max-depth=1 / | sort -h | tail -n 20",
        ],
        "optimize_suggestions": [
            "清理过期日志和临时文件，或扩容磁盘。需要人工确认后执行。",
        ],
        "followups": [
            {
                "key": "disk_inode",
                "name": "磁盘inode使用率",
                "meaning": "inode 耗尽时即使还有空间也无法创建新文件",
                "promql": '(1 - (node_filesystem_files_free{fstype!~"tmpfs|overlay|squashfs"} / clamp_min(node_filesystem_files{fstype!~"tmpfs|overlay|squashfs"}, 1))) * 100',
                "unit": "%",
            },
        ],
    },
    {
        "key": "disk_io",
        "name": "磁盘IO利用率",
        "meaning": "磁盘设备忙碌时间占比，持续高位表示 IO 瓶颈",
        "promql": "rate(node_disk_io_time_seconds_total[5m]) * 100",
        "unit": "%",
        "warning_attr": "disk_io_util_warning",
        "critical_attr": "disk_io_util_critical",
        "business_impact": "磁盘 IO 打满会导致应用卡顿、数据库慢查询和 CPU iowait 升高。",
        "check_commands": [
            "iostat -xz 1 5",
            "iotop -oP",
        ],
        "optimize_suggestions": [
            "识别热点磁盘与进程，评估隔离 IO、换高速盘或优化查询。需要人工确认后执行。",
        ],
        "followups": [
            {
                "key": "disk_read",
                "name": "磁盘读取速率",
                "meaning": "磁盘读带宽，用于判断读放大",
                "promql": "rate(node_disk_read_bytes_total[5m])",
                "unit": "B/s",
            },
            {
                "key": "disk_write",
                "name": "磁盘写入速率",
                "meaning": "磁盘写带宽，用于判断写放大",
                "promql": "rate(node_disk_written_bytes_total[5m])",
                "unit": "B/s",
            },
        ],
    },
    {
        "key": "load",
        "name": "系统负载",
        "meaning": "1 分钟平均负载，相对 CPU 核数偏高表示进程排队",
        "promql": "node_load1",
        "unit": "",
        "warning_attr": "load1_warning",
        "critical_attr": "load1_critical",
        "business_impact": "负载长期高于核数意味着调度排队，业务响应会变慢。",
        "check_commands": [
            "uptime",
            "nproc",
            "ps -eo pid,stat,pcpu,pmem,cmd --sort=-pcpu | head -n 20",
        ],
        "optimize_suggestions": [
            "对照 CPU 核数判断是否计算或 IO 卡住，再决定限流或扩容。需要人工确认后执行。",
        ],
        "followups": [
            {
                "key": "load5",
                "name": "系统5分钟负载",
                "meaning": "观察负载是否持续，而不是瞬时尖峰",
                "promql": "node_load5",
                "unit": "",
            },
            {
                "key": "load15",
                "name": "系统15分钟负载",
                "meaning": "更长周期的负载趋势",
                "promql": "node_load15",
                "unit": "",
            },
        ],
    },
    {
        "key": "network_rx",
        "name": "网络接收带宽",
        "meaning": "网卡入站流量，排除 lo，单位 Mbps",
        "promql": 'sum by(instance) (rate(node_network_receive_bytes_total{device!="lo"}[5m])) * 8 / 1000000',
        "unit": "Mbps",
        "warning_attr": "network_rx_mbps_warning",
        "critical_attr": "network_rx_mbps_critical",
        "business_impact": "入站带宽打满会导致请求丢失、超时和对外服务不可达。",
        "check_commands": [
            "sar -n DEV 1 5",
            "ss -ant | head",
        ],
        "optimize_suggestions": [
            "按网卡拆分流量，评估限流、扩容带宽或排查异常连接。需要人工确认后执行。",
        ],
        "followups": [
            {
                "key": "network_rx_err",
                "name": "网卡接收错误包速率",
                "meaning": "错误包升高说明链路或驱动异常",
                "promql": 'sum by(instance) (rate(node_network_receive_errs_total{device!="lo"}[5m]))',
                "unit": "pps",
            },
            {
                "key": "network_rx_drop",
                "name": "网卡接收丢包速率",
                "meaning": "丢包升高会直接损伤业务成功率",
                "promql": 'sum by(instance) (rate(node_network_receive_drop_total{device!="lo"}[5m]))',
                "unit": "pps",
            },
        ],
    },
    {
        "key": "network_tx",
        "name": "网络发送带宽",
        "meaning": "网卡出站流量，排除 lo，单位 Mbps",
        "promql": 'sum by(instance) (rate(node_network_transmit_bytes_total{device!="lo"}[5m])) * 8 / 1000000',
        "unit": "Mbps",
        "warning_attr": "network_tx_mbps_warning",
        "critical_attr": "network_tx_mbps_critical",
        "business_impact": "出站带宽打满会导致响应变慢、推送失败和超时。",
        "check_commands": [
            "sar -n DEV 1 5",
            "iftop -nP",
        ],
        "optimize_suggestions": [
            "排查大流量进程，评估压缩、限流或扩容出口带宽。需要人工确认后执行。",
        ],
        "followups": [
            {
                "key": "network_tx_err",
                "name": "网卡发送错误包速率",
                "meaning": "发送错误升高说明网卡或对端异常",
                "promql": 'sum by(instance) (rate(node_network_transmit_errs_total{device!="lo"}[5m]))',
                "unit": "pps",
            },
            {
                "key": "network_tx_drop",
                "name": "网卡发送丢包速率",
                "meaning": "发送丢包会表现为对端超时",
                "promql": 'sum by(instance) (rate(node_network_transmit_drop_total{device!="lo"}[5m]))',
                "unit": "pps",
            },
        ],
    },
]


def metric_by_key(key: str) -> dict[str, Any] | None:
    for item in HOST_METRICS:
        if item["key"] == key:
            return item
        for follow in item.get("followups") or []:
            if follow["key"] == key:
                return {
                    **follow,
                    "parent_key": item["key"],
                    "warning_attr": None,
                    "critical_attr": None,
                }
    return None
