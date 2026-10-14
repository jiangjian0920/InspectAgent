from __future__ import annotations

import re
from pathlib import Path

from app.core.errors import ConfigurationError
from app.domain.models import ResolvedTarget
from app.rules.loader import load_yaml


_REGEX_SPECIAL = re.compile(r"([\\.^$*+?()\[\]{}|])")


def escape_promql_regex(value: str) -> str:
    """转义为 PromQL 正则安全的字面量；点号转成字符类，避免匹配任意字符。"""
    escaped = _REGEX_SPECIAL.sub(r"\\\1", value)
    return escaped.replace(r"\.", "[.]")


class AssetCatalog:
    """从静态 YAML 加载服务器资产，支持别名映射。"""

    def __init__(self, targets: list[ResolvedTarget]) -> None:
        self._targets = targets
        self._index: dict[str, ResolvedTarget] = {}
        for target in targets:
            for key in self._keys_for(target):
                self._index.setdefault(key, target)

    @staticmethod
    def _keys_for(target: ResolvedTarget) -> set[str]:
        keys = {
            target.resource_id.lower(),
            target.prometheus_instance.lower(),
            target.reference.lower(),
        }
        for alias in target.labels.get("aliases", "").split(","):
            alias = alias.strip()
            if alias:
                keys.add(alias.lower())
        # 主机名（去掉端口）也作为可解析键。
        host = target.prometheus_instance.split(":")[0]
        if host:
            keys.add(host.lower())
        return keys

    @classmethod
    def from_yaml(cls, path: Path) -> "AssetCatalog":
        if not path.exists():
            raise ConfigurationError(f"资产目录不存在: {path}")
        data = load_yaml(path)
        raw_servers = data.get("servers") or []
        if not isinstance(raw_servers, list) or not raw_servers:
            raise ConfigurationError(f"资产目录中没有服务器定义: {path}")
        targets: list[ResolvedTarget] = []
        for raw in raw_servers:
            if not isinstance(raw, dict):
                raise ConfigurationError(f"服务器资产必须是映射: {path}")
            resource_id = str(raw.get("id") or "").strip()
            prometheus_instance = str(raw.get("prometheus_instance") or "").strip()
            if not resource_id or not prometheus_instance:
                raise ConfigurationError(f"服务器资产缺少 id 或 prometheus_instance: {raw}")
            aliases = raw.get("aliases") or []
            if not isinstance(aliases, list):
                raise ConfigurationError(f"aliases 必须是列表: {resource_id}")
            labels = {
                "aliases": ",".join(str(a) for a in aliases),
                "environment": str(raw.get("environment") or ""),
                "job": str(raw.get("prometheus_job") or "node-exporter"),
            }
            targets.append(
                ResolvedTarget(
                    resource_id=resource_id,
                    resource_type="server",
                    reference=str(aliases[0]) if aliases else prometheus_instance,
                    prometheus_instance=prometheus_instance,
                    environment=labels["environment"],
                    labels=labels,
                )
            )
        if not targets:
            raise ConfigurationError(f"资产目录为空: {path}")
        return cls(targets)

    def resolve(self, reference: str | None) -> ResolvedTarget | None:
        if not reference:
            return None
        return self._index.get(reference.strip().lower())

    def all_targets(self) -> list[ResolvedTarget]:
        return list(self._targets)

    def instance_regex(self) -> str:
        """全部授权实例的 PromQL 正则，用于 scope=all 的查询。"""
        return "|".join(escape_promql_regex(t.prometheus_instance) for t in self._targets)

    def job_regex(self) -> str:
        """全部授权实例 job 标签的正则。"""
        jobs = sorted({t.labels.get("job", "") for t in self._targets if t.labels.get("job")})
        if not jobs:
            return ".*"
        return "|".join(escape_promql_regex(job) for job in jobs)

    def __len__(self) -> int:
        return len(self._targets)


__all__ = ["AssetCatalog", "escape_promql_regex"]
