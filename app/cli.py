from __future__ import annotations

import argparse
import sys

from app.core.config import load_settings
from app.core.errors import InspectionError
from app.core.logging import setup_logging
from app.nlu.client import GLMClient
from app.nlu.intent import IntentService
from app.orchestrator import InspectionAgent
from app.planner.planner import InspectionPlanner
from app.reporting.render import render_markdown, render_text, to_json
from app.rules.loader import load_policies
from app.skills.providers.server.skill import ServerMetricSkill


BANNER = """AI Prometheus 巡检 Agent（服务器专项 Skill）
输入自然语言指令开始巡检，输入 quit / exit 退出。
示例：
  查询服务器 192.168.59.130 的 CPU
  巡检服务器 192.168.59.130
  查询最近 4 天的服务器异常清单
  对比 192.168.59.130 今天和昨天的运行情况
  查看 CPU 使用率最高的机器
"""


def _build_agent():
    settings = load_settings()
    llm = GLMClient(settings.llm) if settings.llm.enabled else None
    return settings, InspectionAgent(settings, llm=llm)


def interactive_loop(agent: InspectionAgent) -> int:
    print(BANNER)
    while True:
        try:
            raw = input("巡检指令> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            return 0
        if not raw:
            continue
        if raw.lower() in {"quit", "exit", "q"}:
            print("已退出。")
            return 0
        try:
            report = agent.run(raw)
            print("\n" + render_text(report) + "\n")
        except InspectionError as exc:
            print(f"执行失败: {exc}", file=sys.stderr)


def _run_plan(instruction: str) -> int:
    settings, _ = load_settings(), None
    provider = ServerMetricSkill(settings)
    policies = load_policies(settings)
    intent_service = IntentService(settings, None)
    planner = InspectionPlanner(settings, provider, policies)
    intent = intent_service.parse(instruction)
    print(f"task_type: {intent.task_type}")
    print(f"target: scope={intent.scope} instance={intent.instance}")
    print(f"metrics: {intent.metrics or '<默认指标集>'}")
    try:
        plan = planner.build(intent)
    except InspectionError as exc:
        print(f"计划构建失败: {exc}")
        return 1
    print("operations:")
    for op in plan.operations:
        print(f"  - {op.type} {op.model_dump(exclude_defaults=True, exclude={'type'})}")
    print("queries:")
    for query in plan.queries:
        print(
            f"  - metric={query.metric_id} template={query.template_id} "
            f"scope={query.scope} period={query.period}"
        )
    return 0


def _check_config() -> int:
    settings = load_settings()
    print("== 配置检查 ==")
    print(f"PROMETHEUS_URL: {settings.prometheus_url}")
    print(f"默认时间范围: {settings.default_time_range}")
    print(f"默认步长: {settings.default_step_seconds}s")
    print(f"最大时间范围: {settings.max_time_range_days} 天")
    print(f"查询预算: {settings.max_query_count}")
    print(f"报告模式: {settings.report_mode}")
    print(f"GLM: {'已配置' if settings.llm.enabled else '未配置（使用规则回退）'}")
    for label, path in (
        ("资产目录", settings.resolved_assets_path()),
        ("策略配置", settings.resolved_policies_path()),
        ("服务器指标目录", settings.resolved_server_skill_dir() / "metric_catalog.yaml"),
        ("服务器查询模板", settings.resolved_server_skill_dir() / "queries.yaml"),
    ):
        print(f"{label}: {path} {'OK' if path.exists() else '缺失'}")
    return 0


def _doctor() -> int:
    import importlib

    print("== 环境诊断 ==")
    print(f"Python: {sys.version.split()[0]}")
    for module in ("pydantic", "yaml", "requests", "dotenv", "zai", "fastapi", "uvicorn"):
        try:
            importlib.import_module(module)
            print(f"  {module}: OK")
        except ImportError:
            print(f"  {module}: 缺失")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Prometheus 巡检 Agent")
    parser.add_argument("--selftest", action="store_true", help="运行离线自测")
    parser.add_argument("--plan", action="store_true", help="只输出执行计划，不访问 Prometheus")
    parser.add_argument("--check-config", action="store_true", help="检查配置")
    parser.add_argument("--doctor", action="store_true", help="环境与依赖诊断")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出报告")
    parser.add_argument("instruction", nargs="*", help="巡检指令；不传则进入交互模式")
    args = parser.parse_args(argv)

    if args.selftest:
        from tests.selftest import main as selftest_main

        return selftest_main()
    if args.check_config:
        return _check_config()
    if args.doctor:
        return _doctor()

    instruction = " ".join(args.instruction)
    if args.plan:
        return _run_plan(instruction or "查询服务器 192.168.59.130 的 CPU")

    try:
        settings, agent = _build_agent()
    except InspectionError as exc:
        print(f"启动失败: {exc}", file=sys.stderr)
        return 1
    setup_logging(settings.log_level)

    if instruction:
        try:
            report = agent.run(instruction)
        except InspectionError as exc:
            print(f"执行失败: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(to_json(report))
        else:
            print(render_text(report))
        return 0
    return interactive_loop(agent)


__all__ = ["main", "render_markdown"]
