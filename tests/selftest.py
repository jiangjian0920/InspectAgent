from __future__ import annotations

from app.core.config import Settings
from app.inventory.catalog import AssetCatalog
from app.orchestrator import InspectionAgent
from app.skills.providers.server.skill import ServerMetricSkill
from tests.fakes import FakePrometheusClient


def _agent(client: FakePrometheusClient, settings: Settings) -> InspectionAgent:
    catalog = AssetCatalog.from_yaml(settings.resolved_assets_path())
    provider = ServerMetricSkill(settings, client=client, catalog=catalog)
    return InspectionAgent(settings, provider=provider, llm=None)


def _case_instant(settings) -> str:
    client = FakePrometheusClient({"cpu": [({"instance": "192.168.59.130:9100"}, 99)]})
    report = _agent(client, settings).run("查询服务器 192.168.59.130 的 CPU")
    assert len(client.queries) == 1, "只应查询 CPU"
    assert report.findings and report.findings[0].severity == "critical"
    return "instant_inspection"


def _case_not_found(settings) -> str:
    client = FakePrometheusClient()
    report = _agent(client, settings).run("查询服务器 192.168.59.131 的 CPU")
    assert report.query_status == "not_found"
    assert client.queries == []
    return "not_found"


def _case_anomaly(settings) -> str:
    client = FakePrometheusClient(
        {
            "cpu": [({"instance": "192.168.59.130:9100"}, lambda i, n: 99 if i < 5 else 10)],
            "memory": [({"instance": "192.168.59.130:9100"}, 30)],
            "disk": [({"instance": "192.168.59.130:9100"}, 40)],
            "availability": [({"instance": "192.168.59.130:9100"}, 1)],
        }
    )
    report = _agent(client, settings).run("查询最近 4 天的服务器异常清单")
    assert report.findings, "应识别到异常事件"
    assert report.findings[0].status == "recovered"
    return "historical_anomaly_summary"


def _case_error(settings) -> str:
    client = FakePrometheusClient(errors={"cpu"})
    report = _agent(client, settings).run("查询服务器 192.168.59.130 的 CPU")
    assert report.query_status == "data_source_error"
    return "data_source_error"


def main() -> int:
    settings = Settings()
    cases = [_case_instant, _case_not_found, _case_anomaly, _case_error]
    failures = 0
    print("== 离线自测 ==")
    for case in cases:
        try:
            name = case(settings)
            print(f"  PASS  {case.__name__} ({name})")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  FAIL  {case.__name__}: {exc}")
    print(f"共 {len(cases)} 项，失败 {failures} 项")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
