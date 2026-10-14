from __future__ import annotations

import pytest

from app.core.config import Settings
from app.inventory.catalog import AssetCatalog
from app.orchestrator import InspectionAgent
from app.skills.providers.server.skill import ServerMetricSkill
from tests.fakes import FakePrometheusClient


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def catalog(settings: Settings) -> AssetCatalog:
    return AssetCatalog.from_yaml(settings.resolved_assets_path())


def build_agent(
    settings: Settings,
    client: FakePrometheusClient,
    catalog: AssetCatalog | None = None,
) -> InspectionAgent:
    provider = ServerMetricSkill(settings, client=client, catalog=catalog)
    return InspectionAgent(settings, provider=provider, llm=None)


@pytest.fixture
def agent_factory(settings, catalog):
    def _factory(client: FakePrometheusClient) -> InspectionAgent:
        return build_agent(settings, client, catalog)

    return _factory
