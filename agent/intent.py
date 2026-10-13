from __future__ import annotations

from dataclasses import dataclass, field
import re

from agent.skills.catalogs import catalog_for
from agent.utils import parse_instance, parse_time_range


# 巡检对象类型对应的 Skill 名称。
SKILL_BY_TARGET = {
    "server": "server_inspect",
    "redis": "redis_inspect",
    "kafka": "kafka_inspect",
    "k8s": "k8s_inspect",
}

_FULL_CLUSTER_HINTS = (
    "全集群",
    "全面巡检",
    "全面检查",
    "完整巡检",
    "整体巡检",
    "全部巡检",
    "全部组件",
    "全部skill",
    "所有组件",
    "所有 skill",
    "所有服务",
    "全部服务",
    "整个集群",
    "整个系统",
    "全系统",
    "全量巡检",
    "巡检全部",
    "cluster wide",
    "all skills",
)

_REDIS_HINTS = ("redis",)
_KAFKA_HINTS = ("kafka",)
_K8S_HINTS = ("k8s", "kubernetes", "kube", "pod", "容器")
_SERVER_HINTS = ("服务器", "主机", "server", "host", "linux", "node_exporter")

_DISK_IO_HINTS = ("磁盘io", "磁盘 io", "disk io", "io利用率", "ioutil")
_DISK_HINTS = ("磁盘使用", "磁盘空间", "硬盘", "文件系统", "目录", "挂载", "disk usage")
_CPU_HINTS = ("cpu", "处理器")
_MEM_HINTS = ("内存", "memory")
_LOAD_HINTS = ("负载", "load average", "系统负载")
_NET_RX_HINTS = ("网络接收", "入站", "下行")
_NET_TX_HINTS = ("网络发送", "出站", "上行")
_NET_HINTS = ("网络", "网卡", "带宽")

_REDIS_METRIC_HINTS = {
    "up": ("存活", "探活", "是否在线", "是否挂了"),
    "memory": ("内存", "memory"),
    "clients": ("连接", "客户端", "clients"),
    "blocked": ("阻塞", "blocked"),
    "rejected": ("拒绝", "rejected"),
    "ops": ("qps", "ops", "命令数"),
}

_KAFKA_METRIC_HINTS = {
    "brokers": ("broker", "节点数"),
    "under_replicated": ("副本", "under.replicated", "isr"),
    "offline": ("离线分区", "offline"),
    "lag": ("lag", "积压", "消费滞后"),
}

_K8S_METRIC_HINTS = {
    "restarts": ("重启", "crash", "restart"),
    "cpu": ("cpu", "处理器"),
    "memory": ("内存", "memory"),
    "not_ready": ("未就绪", "not ready", "ready"),
}

_NAMED_INSTANCE_RE = re.compile(
    r"(?:巡检|查看|查询|检查)\s*([A-Za-z][A-Za-z0-9_.\-]{1,63})",
    re.IGNORECASE,
)


@dataclass
class InspectionIntent:
    """自然语言解析后的巡检意图。"""

    user_input: str
    time_range: str
    cluster_wide: bool = False
    targets: list[dict[str, object]] = field(default_factory=list)

    @property
    def skill_names(self) -> list[str]:
        names: list[str] = []
        for item in self.targets:
            name = str(item.get("skill") or "")
            if name and name not in names:
                names.append(name)
        return names


def _hit(text: str, lowered: str, hints: tuple[str, ...]) -> bool:
    return any(hint in lowered or hint in text for hint in hints)


def _pick_metrics(text: str, lowered: str, target_type: str) -> list[str]:
    """从用户话里找出要查的指标 key，没有点名则返回空列表。"""
    catalog = catalog_for(target_type)
    known = [item["key"] for item in catalog]
    selected: list[str] = []

    def add(key: str) -> None:
        if key in known and key not in selected:
            selected.append(key)

    if target_type == "server":
        if _hit(text, lowered, _DISK_IO_HINTS):
            add("disk_io")
        if _hit(text, lowered, _DISK_HINTS) or "/目录" in text or ("磁盘" in text and "io" not in lowered):
            add("disk")
        if "磁盘" in text and "disk_io" in selected and any(token in text for token in ("使用", "空间", "目录", "文件系统")):
            add("disk")
        if _hit(text, lowered, _CPU_HINTS):
            add("cpu")
        if _hit(text, lowered, _MEM_HINTS):
            add("memory")
        if _hit(text, lowered, _LOAD_HINTS):
            add("load")
        if _hit(text, lowered, _NET_RX_HINTS):
            add("network_rx")
        if _hit(text, lowered, _NET_TX_HINTS):
            add("network_tx")
        if _hit(text, lowered, _NET_HINTS) and "network_rx" not in selected and "network_tx" not in selected:
            add("network_rx")
            add("network_tx")
        return selected

    mapping = {
        "redis": _REDIS_METRIC_HINTS,
        "kafka": _KAFKA_METRIC_HINTS,
        "k8s": _K8S_METRIC_HINTS,
    }.get(target_type, {})
    for key, hints in mapping.items():
        if _hit(text, lowered, tuple(hints)):
            add(key)
    return selected


def _named_instance(text: str) -> str | None:
    """从「巡检 xxx」里取出实例名，类型词本身不算实例。"""
    match = _NAMED_INSTANCE_RE.search(text)
    if not match:
        return None
    token = match.group(1)
    lowered = token.lower()
    skip = {
        "redis",
        "kafka",
        "k8s",
        "kubernetes",
        "server",
        "host",
        "cpu",
        "memory",
        "pod",
        "node",
    }
    if lowered in skip:
        return None
    return token


def _detect_targets(text: str, lowered: str) -> list[str]:
    """根据关键字判断这次要巡检哪些组件。"""
    found: list[str] = []
    if _hit(text, lowered, _REDIS_HINTS):
        found.append("redis")
    if _hit(text, lowered, _KAFKA_HINTS):
        found.append("kafka")
    if _hit(text, lowered, _K8S_HINTS):
        found.append("k8s")
    if _hit(text, lowered, _SERVER_HINTS):
        found.append("server")
    if re.search(r"redis\d+", lowered):
        if "redis" not in found:
            found.append("redis")
    if parse_instance(text) and not found:
        found.append("server")
    return found


def _instance_for(target_type: str, text: str, lowered: str) -> str | None:
    """按组件类型从指令里取出实例标识。"""
    ip = parse_instance(text)
    named = _named_instance(text)
    if target_type == "server":
        return ip or named
    if target_type == "redis":
        match = re.search(r"(redis[A-Za-z0-9_.\-]*)", text, re.IGNORECASE)
        if match and match.group(1).lower() != "redis":
            return match.group(1)
        return named if named and "kafka" not in (named or "").lower() else None
    if target_type == "kafka":
        match = re.search(r"(kafka[A-Za-z0-9_.\-]*)", text, re.IGNORECASE)
        if match and match.group(1).lower() != "kafka":
            return match.group(1)
        return named
    if target_type == "k8s":
        match = re.search(
            r"(?:pod|节点|node|命名空间|ns)\s*[=:：]?\s*([A-Za-z0-9_.\-]+)",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
        return named
    return ip or named


def parse_intent(instruction: str, default_time_range: str = "2h") -> InspectionIntent:
    """把一条自然语言指令解析成 InspectionIntent。"""
    text = (instruction or "").strip()
    lowered = text.lower()
    try:
        time_range, _ = parse_time_range(text, default_time_range)
    except ValueError:
        time_range = default_time_range

    cluster_wide = _hit(text, lowered, _FULL_CLUSTER_HINTS)
    target_types = list(SKILL_BY_TARGET) if cluster_wide else _detect_targets(text, lowered)
    if not target_types:
        target_types = ["server"]

    targets: list[dict[str, object]] = []
    for target_type in target_types:
        metrics = _pick_metrics(text, lowered, target_type)
        targets.append(
            {
                "target_type": target_type,
                "skill": SKILL_BY_TARGET[target_type],
                "instance": _instance_for(target_type, text, lowered),
                "metrics": metrics,
            }
        )
    return InspectionIntent(
        user_input=text,
        time_range=time_range,
        cluster_wide=cluster_wide,
        targets=targets,
    )
