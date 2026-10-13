from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent.config import Thresholds


class InspectionCapability(ABC):
    name: str
    target_type: str
    description: str

    @abstractmethod
    def metric_catalog(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def system_prompt(
        self,
        thresholds: Thresholds,
        default_time_range: str,
        metric_keys: list[str] | None = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def suggested_queries(
        self,
        time_range: str,
        instance: str | None = None,
        metric_keys: list[str] | None = None,
    ) -> list[dict[str, str]]:
        raise NotImplementedError

    def followup_queries(
        self,
        metric_key: str,
        time_range: str,
        instance: str | None = None,
    ) -> list[dict[str, str]]:
        return []
