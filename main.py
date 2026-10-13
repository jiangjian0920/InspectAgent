#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from agent.agent import InspectionAgent
from agent.config import load_settings
from agent.config_check import check_settings, format_check_report
from agent.logger import setup_logger
from agent.planner import build_inspection_plan


BANNER = """Prometheus 巡检 Agent
底层模型：智谱 GLM-5.3
架构：LangGraph 编排 + 可插拔 Skill（server_inspect / redis_inspect / kafka_inspect / k8s_inspect）
输入自然语言指令开始巡检，输入 quit / exit 退出。
示例：
  巡检 redis6404
  查询服务器 192.168.59.130 的 cpu
  全集群巡检
  做一个全面巡检
"""


def interactive_loop(agent: InspectionAgent) -> int:
    """交互模式：循环读取巡检指令并打印报告。"""
    print(BANNER)
    while True:
        try:
            user_input = input("巡检指令> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            return 0
        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "q"}:
            print("已退出。")
            return 0
        report = agent.run(user_input)
        print("\n===== 巡检报告 =====")
        print(report)
        print("===== 报告结束 =====\n")


def main() -> int:
    """命令行入口，按参数走自测、规划、诊断或真正巡检。"""
    parser = argparse.ArgumentParser(description="AI Prometheus 巡检 Agent")
    parser.add_argument("--selftest", action="store_true", help="运行离线自测，不调用智谱 API 和 Prometheus")
    parser.add_argument("--check-config", action="store_true", help="检查 .env 配置，不调用外部接口")
    parser.add_argument("--plan", action="store_true", help="只输出巡检规划，不调用智谱 API 和 Prometheus")
    parser.add_argument("--doctor", action="store_true", help="诊断 Python 环境和依赖，不调用外部接口")
    parser.add_argument(
        "instruction",
        nargs="*",
        help="直接传入巡检指令；不传则进入命令行交互模式",
    )
    args = parser.parse_args()
    if args.selftest:
        from tests.selftest import main as selftest_main

        return selftest_main()
    if args.doctor:
        from agent.doctor import collect_doctor_report

        print(collect_doctor_report())
        return 0
    try:
        settings = load_settings()
    except Exception as exc:
        print(f"配置加载失败: {exc}", file=sys.stderr)
        return 1
    if args.check_config:
        print(format_check_report(settings, check_settings(settings)))
        return 0
    if args.plan:
        instruction = " ".join(args.instruction) or "查询服务器 192.168.59.130 的 cpu"
        print(build_inspection_plan(instruction, settings))
        return 0
    try:
        setup_logger()
        from agent.llm.client import ZhipuLLMClient

        llm = ZhipuLLMClient(settings) if settings.zhipu_api_key else None
        agent = InspectionAgent(settings, llm_client=llm)
    except Exception as exc:
        print(f"启动失败: {exc}", file=sys.stderr)
        return 1
    if args.instruction:
        print(agent.run(" ".join(args.instruction)))
        return 0
    return interactive_loop(agent)


if __name__ == "__main__":
    sys.exit(main())
