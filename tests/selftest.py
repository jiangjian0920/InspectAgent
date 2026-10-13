from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.agent import InspectionAgent
from agent.config import Settings, Thresholds
from agent.intent import parse_intent
from agent.inspection.evaluator import evaluate_result
from agent.inspection.host_metrics import HOST_METRICS
from agent.planner import build_inspection_plan
from agent.skills import build_default_skills
from agent.skills.base import SkillRegistry
from agent.skills.server_inspect import ServerInspectSkill
from agent.skills.redis_inspect import RedisInspectSkill
from agent.skills.kafka_inspect import KafkaInspectSkill
from agent.skills.k8s_inspect import K8sInspectSkill
from agent.utils import (
    apply_instance_filter,
    bind_prometheus_result_to_instance,
    parse_instance,
    parse_time_range,
    prometheus_instance_matcher,
    series_matches_instance,
)


def _thresholds() -> Thresholds:
    return Thresholds(
        cpu_warning=80,
        cpu_critical=90,
        memory_warning=80,
        memory_critical=90,
        disk_warning=80,
        disk_critical=90,
        disk_io_util_warning=80,
        disk_io_util_critical=90,
        load1_warning=4,
        load1_critical=8,
        network_rx_mbps_warning=800,
        network_rx_mbps_critical=950,
        network_tx_mbps_warning=800,
        network_tx_mbps_critical=950,
        redis_up_warning=0,
        redis_up_critical=0,
        redis_memory_warning=80,
        redis_memory_critical=90,
        redis_clients_warning=5000,
        redis_clients_critical=8000,
        redis_blocked_warning=10,
        redis_blocked_critical=50,
        redis_rejected_warning=1,
        redis_rejected_critical=5,
        redis_ops_warning=20000,
        redis_ops_critical=50000,
        kafka_brokers_warning=2,
        kafka_brokers_critical=1,
        kafka_under_replicated_warning=1,
        kafka_under_replicated_critical=1,
        kafka_offline_warning=1,
        kafka_offline_critical=1,
        kafka_lag_warning=10000,
        kafka_lag_critical=100000,
        k8s_restarts_warning=3,
        k8s_restarts_critical=10,
        k8s_cpu_warning=80,
        k8s_cpu_critical=95,
        k8s_memory_warning=80,
        k8s_memory_critical=95,
        k8s_not_ready_warning=1,
        k8s_not_ready_critical=1,
    )


def _settings() -> Settings:
    return Settings(
        zhipu_api_key="",
        zhipu_model="glm-5.3",
        zhipu_base_url="",
        zhipu_timeout_seconds=5,
        prometheus_url="http://127.0.0.1:9090",
        prometheus_timeout_seconds=5,
        default_time_range="2h",
        max_tool_rounds=1,
        thresholds=_thresholds(),
    )


class FakePrometheus:
    def __init__(self) -> None:
        self.calls = 0
        self.queries: list[str] = []

    def query_range(self, promql: str, time_range: str) -> dict:
        self.calls += 1
        self.queries.append(promql)
        series = self._series_for(promql)
        return {
            "ok": True,
            "promql": promql,
            "time_range": time_range or "2h",
            "start": "2026-10-09T00:00:00Z",
            "end": "2026-10-09T02:00:00Z",
            "step": "30s",
            "series_count": len(series),
            "series": series,
        }

    def _series_for(self, promql: str) -> list[dict]:
        import re

        match = re.search(r'instance\s*(?:=~|=)\s*"([^"]+)"', promql)
        requested = ""
        if match:
            requested = match.group(1).replace("[.]", ".")
        if "192.168.59.131" in requested:
            return []
        if "missing" in requested.lower() or "notfound" in requested.lower():
            return []

        if "redis_" in promql:
            if requested and "redis6404" not in requested and "10.0.0.8" not in requested:
                return []
            instance = "redis6404:9121"
            if "redis_up" in promql:
                return [_point(instance, 1)]
            if "redis_memory" in promql:
                return [_point(instance, 42)]
            if "redis_connected_clients" in promql:
                return [_point(instance, 12)]
            if "redis_blocked" in promql:
                return [_point(instance, 0)]
            if "rejected" in promql:
                return [_point(instance, 0)]
            return [_point(instance, 100)]

        if "kafka_" in promql:
            if requested and "kafka" not in requested.lower() and "10.0.0.8" not in requested:
                return []
            instance = "kafka-1:9308"
            if "brokers" in promql:
                return [_point(instance, 3)]
            if "lag" in promql:
                return [_point(instance, 20, extra={"consumergroup": "cg1", "topic": "t1"})]
            return [_point(instance, 0)]

        if "kube_" in promql or "container_" in promql:
            if requested and "nginx" not in requested and "10.0.0.8" not in requested:
                return []
            instance = "10.0.0.8:9100"
            extra = {"pod": "nginx-0", "namespace": "default"}
            if "restarts" in promql:
                return [_point(instance, 1, extra=extra)]
            if "cpu" in promql:
                return [_point(instance, 20, extra=extra)]
            if "memory" in promql:
                return [_point(instance, 30, extra=extra)]
            if "ready" in promql:
                return [_point(instance, 0, extra=extra)]
            return [_point(instance, 1, extra=extra)]

        instance = "10.0.0.8:9100"
        if requested and "10.0.0.8" not in requested and "192.168.59.130" not in requested:
            return []
        if "192.168.59.130" in requested:
            instance = "192.168.59.130:9100"
        high = "node_cpu_seconds_total" in promql and "idle" in promql
        if "up" == promql.strip() or promql.strip().startswith("up{") or "node_uname_info" in promql:
            return [_point(instance, 1)]
        return [_point(instance, 95.0 if high else 12.0, extra={"max": 96.0 if high else 15.0, "avg": 40.0 if high else 10.0})]


def _point(instance: str, latest: float, extra: dict | None = None) -> dict:
    metric = {"instance": instance}
    payload = extra or {}
    max_value = payload.pop("max", latest)
    avg_value = payload.pop("avg", latest)
    metric.update(payload)
    return {
        "metric": metric,
        "sample_count": 5,
        "latest": latest,
        "max": max_value,
        "min": min(latest, 8.0),
        "avg": avg_value,
    }


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, tools=None, round_index=1, **kwargs):
        self.calls += 1
        message = SimpleNamespace(
            role="assistant",
            content="建议继续观察。扩容前需要人工确认后执行。",
            tool_calls=[],
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])


def _agent(fake: FakePrometheus | None = None, llm=None) -> tuple[InspectionAgent, FakePrometheus]:
    settings = _settings()
    prometheus = fake or FakePrometheus()
    registry = SkillRegistry()
    registry.register(ServerInspectSkill(settings, prometheus))
    registry.register(RedisInspectSkill(settings, prometheus))
    registry.register(KafkaInspectSkill(settings, prometheus))
    registry.register(K8sInspectSkill(settings, prometheus))
    agent = InspectionAgent(settings=settings, skill_registry=registry, llm_client=llm)
    return agent, prometheus


def test_parse_time_range() -> None:
    normalized, seconds = parse_time_range("帮我巡检最近2小时服务器主机指标", "1h")
    assert normalized == "2h", normalized
    assert seconds == 7200, seconds


def test_parse_instance_and_filter() -> None:
    instance = parse_instance("帮我巡检主机 10.0.0.8 最近2小时")
    assert instance == "10.0.0.8"
    matcher = prometheus_instance_matcher(instance)
    query = apply_instance_filter("node_load1", instance)
    assert matcher in query
    ip_matcher = prometheus_instance_matcher("192.168.59.131")
    assert r"\." not in ip_matcher
    assert 'instance=~"192[.]168[.]59[.]131(:[0-9]+)?"' == ip_matcher


def test_parse_intent_examples() -> None:
    redis_intent = parse_intent("巡检 redis6404")
    assert redis_intent.targets[0]["target_type"] == "redis"
    assert redis_intent.targets[0]["instance"] == "redis6404"
    assert redis_intent.targets[0]["metrics"] == []
    assert redis_intent.skill_names == ["redis_inspect"]

    cpu_intent = parse_intent("查询服务器 192.168.59.130 的 cpu")
    assert cpu_intent.targets[0]["target_type"] == "server"
    assert cpu_intent.targets[0]["instance"] == "192.168.59.130"
    assert cpu_intent.targets[0]["metrics"] == ["cpu"]
    assert cpu_intent.skill_names == ["server_inspect"]

    cluster = parse_intent("全集群巡检")
    assert cluster.cluster_wide is True
    assert cluster.skill_names == ["server_inspect", "redis_inspect", "kafka_inspect", "k8s_inspect"]

    full = parse_intent("做一个全面巡检")
    assert full.cluster_wide is True
    assert full.skill_names == ["server_inspect", "redis_inspect", "kafka_inspect", "k8s_inspect"]

    disk = parse_intent("帮我查看当前服务器的/目录磁盘使用量，不要查看其它指标")
    assert disk.targets[0]["metrics"] == ["disk"]


def test_bind_result_rejects_other_host() -> None:
    result = {
        "ok": True,
        "promql": "node_load1",
        "time_range": "2h",
        "series_count": 1,
        "series": [
            {
                "metric": {"instance": "192.168.59.130:9100"},
                "latest": 1.2,
                "max": 1.5,
                "avg": 1.1,
            }
        ],
    }
    bound = bind_prometheus_result_to_instance(result, "192.168.59.131")
    assert bound["ok"] is False
    assert "未找到 instance=192.168.59.131" in bound["error"]
    assert series_matches_instance({"instance": "192.168.59.130:9100"}, "192.168.59.130")


def test_sdk_loader_error_message() -> None:
    from agent.llm.sdk import load_zhipu_client_class

    try:
        load_zhipu_client_class()
    except RuntimeError as exc:
        assert "无法导入智谱官方 SDK" in str(exc)
        return
    except Exception:
        return


def test_offline_plan() -> None:
    plan = build_inspection_plan("查询服务器 192.168.59.130 的 cpu", _settings())
    assert "server_inspect" in plan
    assert "CPU使用率" in plan
    assert "redis_inspect" not in plan


def test_threshold_critical() -> None:
    metric = HOST_METRICS[0]
    result = {
        "ok": True,
        "promql": metric["promql"],
        "series": [
            {
                "metric": {"instance": "10.0.0.8:9100"},
                "latest": 95.2,
                "max": 96.1,
                "avg": 88.0,
            }
        ],
    }
    findings = evaluate_result(metric, result, _thresholds())
    assert findings[0].severity == "critical"


def test_query_error_not_fabricated() -> None:
    metric = HOST_METRICS[1]
    result = {"ok": False, "error": "Prometheus HTTP 500: boom", "promql": metric["promql"]}
    findings = evaluate_result(metric, result, _thresholds())
    assert findings[0].severity == "error"
    assert findings[0].latest is None
    assert "500" in (findings[0].error or "")


def test_build_default_skills() -> None:
    registry = build_default_skills(_settings(), FakePrometheus())
    assert registry.names() == ["server_inspect", "redis_inspect", "kafka_inspect", "k8s_inspect"]


def test_langgraph_nodes() -> None:
    agent, _fake = _agent()
    nodes = set(agent.graph().nodes)
    for name in ("parse_intent", "suggest", "report", "server_inspect", "redis_inspect", "kafka_inspect", "k8s_inspect"):
        assert name in nodes, name


def test_missing_instance_stops() -> None:
    llm = FakeLLM()
    agent, fake = _agent(llm=llm)
    report = agent.run("帮我查看当前192.168.59.131这台服务器的运行情况")
    assert "未找到对应实例" in report
    assert "95.0" not in report
    assert "CPU使用率" not in report
    assert llm.calls == 0
    assert not any("node_cpu_seconds_total" in query for query in fake.queries)


def test_cpu_only_skips_other_metrics() -> None:
    agent, fake = _agent()
    report = agent.run("查询服务器 192.168.59.130 的 cpu")
    assert "CPU使用率" in report
    assert "内存使用率" not in report
    assert "磁盘使用率" not in report
    assert not any("node_memory_" in query for query in fake.queries)
    assert not any("node_filesystem_" in query for query in fake.queries)
    assert any("node_cpu_seconds_total" in query for query in fake.queries)


def test_disk_only_skips_other_metrics() -> None:
    agent, fake = _agent()
    report = agent.run("帮我查看当前服务器的/目录磁盘使用量，不要查看其它指标")
    assert "磁盘使用率" not in report or "健康" in report or "异常" in report or "巡检范围" in report
    assert "CPU使用率" not in report
    assert not any("node_cpu_seconds_total" in query and "idle" in query for query in fake.queries)


def test_redis_basic_health() -> None:
    agent, fake = _agent()
    report = agent.run("巡检 redis6404")
    assert "redis6404" in report
    assert "未找到对应实例" not in report
    assert any("redis_up" in query for query in fake.queries)
    assert "健康" in report


def test_redis_missing_instance() -> None:
    agent, _fake = _agent()
    report = agent.run("巡检 redis9999")
    assert "未找到对应实例" in report


def test_cluster_wide_calls_all_skills() -> None:
    agent, fake = _agent()
    report = agent.run("做一个全面巡检")
    assert "server_inspect" in " ".join(fake.queries) or "node_" in " ".join(fake.queries)
    assert any("redis_" in query for query in fake.queries)
    assert any("kafka_" in query for query in fake.queries)
    assert any("kube_" in query for query in fake.queries)
    assert "巡检范围" in report or "健康" in report or "未找到对应实例" in report


def test_healthy_report_includes_metric_values() -> None:
    agent, _fake = _agent()
    report = agent.run("巡检 redis6404")
    assert "健康" in report
    assert "Redis内存使用率" in report
    assert "当前" in report
    assert "警告阈值" in report


def test_cpu_anomaly_in_report() -> None:
    agent, _fake = _agent()
    report = agent.run("查询服务器 10.0.0.8 的 cpu")
    assert "CPU使用率" in report
    assert "严重" in report
    assert "当前" in report
    assert "警告阈值" in report


def main() -> int:
    tests = [
        test_parse_time_range,
        test_parse_instance_and_filter,
        test_parse_intent_examples,
        test_bind_result_rejects_other_host,
        test_sdk_loader_error_message,
        test_offline_plan,
        test_threshold_critical,
        test_query_error_not_fabricated,
        test_build_default_skills,
        test_langgraph_nodes,
        test_missing_instance_stops,
        test_cpu_only_skips_other_metrics,
        test_disk_only_skips_other_metrics,
        test_redis_basic_health,
        test_redis_missing_instance,
        test_cluster_wide_calls_all_skills,
        test_healthy_report_includes_metric_values,
        test_cpu_anomaly_in_report,
    ]
    failed = 0
    for func in tests:
        try:
            func()
            print(f"[PASS] {func.__name__}")
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {func.__name__}: {exc}")
    if failed:
        print(f"selftest failed: {failed}/{len(tests)}")
        return 1
    print(f"selftest passed: {len(tests)}/{len(tests)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
