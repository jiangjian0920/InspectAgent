from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from app.prometheus.client import RangeQueryResult
from tests.fakes import FakePrometheusClient, detect_metric, make_series


def _instance_spec(value):
    return [({"instance": "192.168.59.130:9100"}, value)]


def test_instant_inspection_only_queries_named_metric(settings, agent_factory):
    client = FakePrometheusClient({"cpu": _instance_spec(99)})
    agent = agent_factory(client)
    report = agent.run("查询服务器 192.168.59.130 的 CPU")

    assert len(client.queries) == 1
    assert "node_cpu_seconds_total" in client.queries[0]
    assert report.task_type == "instant_inspection"
    assert report.query_status == "healthy"
    assert report.findings and report.findings[0].severity == "critical"
    # 报告必须打印具体指标，而不是只给一句结论。
    assert len(report.metrics) == 1
    assert report.metrics[0].metric == "cpu"
    assert report.metrics[0].current == 99
    assert report.metrics[0].severity == "critical"


def test_basic_inspection_queries_all_metrics(settings, agent_factory):
    client = FakePrometheusClient(
        {
            "cpu": _instance_spec(20),
            "memory": _instance_spec(30),
            "disk": _instance_spec(40),
            "availability": _instance_spec(1),
        }
    )
    agent = agent_factory(client)
    report = agent.run("巡检服务器 192.168.59.130")

    assert len(client.queries) == 4
    assert report.query_status == "healthy"
    assert not report.findings
    # 健康实例同样要逐项列出指标数值。
    assert {row.metric for row in report.metrics} == {"cpu", "memory", "disk", "availability"}
    assert all(row.current is not None for row in report.metrics)


def test_metric_missing_is_not_healthy(settings, agent_factory):
    client = FakePrometheusClient({"cpu": []})
    agent = agent_factory(client)
    report = agent.run("查询服务器 192.168.59.130 的 CPU")

    assert report.query_status == "metric_missing"
    assert report.findings == []


def test_data_source_error(settings, agent_factory):
    client = FakePrometheusClient(errors={"cpu"})
    agent = agent_factory(client)
    report = agent.run("查询服务器 192.168.59.130 的 CPU")

    assert report.query_status == "data_source_error"
    assert report.findings == []


def test_historical_anomaly_summary(settings, agent_factory):
    client = FakePrometheusClient(
        {
            "cpu": [({"instance": "192.168.59.130:9100"}, lambda i, n: 99 if i < 5 else 10)],
            "memory": _instance_spec(30),
            "disk": _instance_spec(40),
            "availability": _instance_spec(1),
        }
    )
    agent = agent_factory(client)
    report = agent.run("查询最近 4 天的服务器异常清单")

    assert report.task_type == "historical_anomaly_summary"
    assert report.findings
    assert report.findings[0].status == "recovered"
    assert any(section["title"] == "异常事件" for section in report.sections)


def test_period_comparison(settings, agent_factory):
    def responder(promql, start, end, step):
        metric = detect_metric(promql)
        today = start.astimezone().date() == datetime.now().astimezone().date()
        if metric == "cpu":
            value = 90 if today else 50
        else:
            value = 1 if metric == "availability" else 40
        spec = [({"instance": "192.168.59.130:9100"}, value)]
        return RangeQueryResult(ok=True, promql=promql, series=make_series(promql, start, end, step, spec))

    client = FakePrometheusClient(responder=responder)
    agent = agent_factory(client)
    report = agent.run("对比 192.168.59.130 今天和昨天的运行情况")

    assert report.task_type == "period_comparison"
    assert any(section["title"] == "时段对比" for section in report.sections)
    assert report.findings
    assert report.findings[0].metric == "cpu"


def test_trend_analysis(settings, agent_factory):
    def responder(promql, start, end, step):
        metric = detect_metric(promql)
        if metric == "cpu":
            spec = [({"instance": "192.168.59.130:9100"}, lambda i, n: 50 + (i / max(1, n - 1)) * 40)]
        else:
            spec = [({"instance": "192.168.59.130:9100"}, 1 if metric == "availability" else 40)]
        return RangeQueryResult(ok=True, promql=promql, series=make_series(promql, start, end, step, spec))

    client = FakePrometheusClient(responder=responder)
    agent = agent_factory(client)
    report = agent.run("分析服务器 192.168.59.130 最近 7 天 CPU 趋势")

    assert report.task_type == "trend_analysis"
    section = next(s for s in report.sections if s["title"] == "趋势分析")
    cpu_row = next(row for row in section["rows"] if "cpu" in str(row[1]).lower())
    assert cpu_row[2] == "上升"


def test_ranking_query(settings, agent_factory):
    client = FakePrometheusClient(
        {
            "cpu": [
                ({"instance": "192.168.59.130:9100"}, 90),
                ({"instance": "192.168.59.132:9100"}, 70),
                ({"instance": "192.168.59.140:9100"}, 50),
            ]
        }
    )
    agent = agent_factory(client)
    report = agent.run("查看 CPU 使用率最高的机器")

    assert report.task_type == "ranking_query"
    assert len(report.metrics) == 3
    assert report.metrics[0].current == 90


def test_threshold_filter(settings, agent_factory):
    client = FakePrometheusClient(
        {
            "cpu": [
                ({"instance": "192.168.59.130:9100"}, 90),
                ({"instance": "192.168.59.132:9100"}, 70),
                ({"instance": "192.168.59.140:9100"}, 50),
            ]
        }
    )
    agent = agent_factory(client)
    report = agent.run("找出 CPU 超过 80% 的机器")

    assert report.task_type == "threshold_filter"
    assert len(report.metrics) == 1
    assert report.metrics[0].current == 90


def test_query_budget_blocks_plan_before_query(agent_factory, settings, catalog):
    from tests.conftest import build_agent

    client = FakePrometheusClient()
    budget_settings = replace(settings, max_query_count=1)
    agent = build_agent(budget_settings, client, catalog)
    report = agent.run("巡检服务器 192.168.59.130")

    assert report.query_status == "no_capability"
    assert client.queries == []
