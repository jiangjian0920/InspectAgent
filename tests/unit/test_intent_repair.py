from __future__ import annotations

from app.core.config import Settings
from app.domain.models import InspectionIntent
from app.inventory.catalog import AssetCatalog
from app.nlu.intent import IntentService
from app.orchestrator import InspectionAgent
from app.skills.providers.server.skill import ServerMetricSkill
from tests.fakes import FakePrometheusClient


class ScriptedLLM:
    """按顺序返回预设响应，并记录每次调用的 messages。"""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[list[dict]] = []

    def complete(self, messages, **kwargs) -> str:
        self.calls.append(messages)
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


def _agent(settings: Settings, llm, client=None) -> InspectionAgent:
    catalog = AssetCatalog.from_yaml(settings.resolved_assets_path())
    provider = ServerMetricSkill(settings, client=client or FakePrometheusClient(), catalog=catalog)
    return InspectionAgent(settings, provider=provider, llm=llm)


# 指标名口语化/未知，会触发计划校验失败。
BAD_INTENT = (
    '{"task_type":"instant_inspection","target":{"type":"server",'
    '"instance":"192.168.59.130"},"metrics":["内核使用率"],'
    '"operations":["aggregate","filter","summarize"]}'
)
GOOD_INTENT = (
    '{"task_type":"instant_inspection","target":{"type":"server",'
    '"instance":"192.168.59.130"},"metrics":["cpu"],'
    '"operations":["aggregate","filter","summarize"]}'
)
# 合法计划，但实例不存在于资产目录。
UNKNOWN_INSTANCE_INTENT = (
    '{"task_type":"instant_inspection","target":{"type":"server",'
    '"instance":"192.168.59.131"},"metrics":["cpu"],'
    '"operations":["aggregate","filter","summarize"]}'
)


def test_repair_triggered_on_unknown_metric(settings):
    llm = ScriptedLLM([BAD_INTENT, GOOD_INTENT])
    client = FakePrometheusClient({"cpu": [({"instance": "192.168.59.130:9100"}, 20)]})
    agent = _agent(settings, llm, client)
    report = agent.run("查一下 192.168.59.130 的内核使用率")

    assert len(llm.calls) == 2, "应触发一次纠错"
    assert report.query_status == "healthy"
    assert report.task_type == "instant_inspection"
    assert report.scope == ["cpu"], "纠错后应映射到合法指标 cpu"


def test_repair_gives_up_after_one_attempt(settings):
    llm = ScriptedLLM([BAD_INTENT, BAD_INTENT])
    agent = _agent(settings, llm)
    report = agent.run("查一下 192.168.59.130 的内核使用率")

    assert len(llm.calls) == 2, "最多纠错一次"
    assert report.query_status == "no_capability"


def test_repair_prompt_contains_error_and_allowlists(settings):
    llm = ScriptedLLM([BAD_INTENT, GOOD_INTENT])
    agent = _agent(settings, llm)
    agent.run("查一下 192.168.59.130 的内核使用率")

    repair_prompt = llm.calls[1][1]["content"]
    assert "校验错误" in repair_prompt
    assert "允许的 metrics" in repair_prompt
    assert "允许的算子" in repair_prompt
    assert "cpu" in repair_prompt
    assert "aggregate" in repair_prompt
    assert "promql" not in repair_prompt.lower()


def test_no_repair_when_llm_disabled(settings):
    agent = _agent(settings, None)
    # 无 LLM 时规则回退把“内核使用率”识别为空指标集，使用默认指标正常执行。
    report = agent.run("查一下 192.168.59.130 的内核使用率")
    assert report.query_status in {"healthy", "metric_missing", "data_source_error"}


def test_not_found_does_not_trigger_repair(settings):
    llm = ScriptedLLM([UNKNOWN_INSTANCE_INTENT, UNKNOWN_INSTANCE_INTENT])
    agent = _agent(settings, llm)
    report = agent.run("查询服务器 192.168.59.131 的 CPU")

    assert report.query_status == "not_found"
    assert len(llm.calls) == 1, "实例不存在不应触发纠错"


def test_repair_method_returns_none_without_llm(settings):
    service = IntentService(settings, None)
    intent = InspectionIntent(task_type="instant_inspection", metrics=["cpu"])
    assert service.can_repair() is False
    assert service.repair("x", intent, "err") is None
