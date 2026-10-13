# 系统架构

完整 8 章手册：当前工作区 内的 `/.monkeycode/docs/HANDBOOK.md`

## 概述

Prometheus 巡检 Agent 是命令行只读分析系统。运维用自然语言下达巡检指令，LangGraph 先解析意图，再用 `Send` 把目标投递到可插拔 Skill。Skill 内部查询 Prometheus、对照阈值，报告层输出带当前/均值/峰值与阈值对照的中文文本。

无 Web、无自动变更、无消息推送。智谱 GLM-5.3 仅在实例找得到时补一两句建议。

## 技术栈

- Python >= 3.10，镜像 python:3.11-slim
- LangGraph >= 0.2.45
- zai-sdk==0.2.3（`from zai import ZhipuAiClient`）
- requests、python-dotenv
- Prometheus query_range；依赖 node_exporter / redis_exporter / kafka_exporter / kube-state-metrics

## 分层

1. 框架底座：`main.py`、`InspectionAgent`、`graph.py`、`report/builder.py`、`config.py`
2. 公共工具：`intent.py`、`prometheus_client.py`、`utils.py`、`evaluator.py`、`skills/common.py`
3. 可插拔 Skill：`server_inspect` / `redis_inspect` / `kafka_inspect` / `k8s_inspect`

## 请求路径

```text
用户指令 -> parse_intent -> Send(Skill) -> 探活 -> 按需 PromQL -> 阈值
        -> suggest(可选 LLM) -> build_inspection_report
```

Skill 注册：`build_default_skills()` -> 图编译 `all_skills()` 加成节点 -> 运行期按 `targets[].skill` 调用。

指定实例：PromQL 加 `192[.]168[.]59[.]131(:[0-9]+)?` 过滤，结果序列必须属于该实例，禁止回退其它主机。

## 部署

镜像 `inspect-agent:v1`，`imagePullPolicy: IfNotPresent`。Deployment 为 `sleep infinity` 后 exec；Job 跑 `python main.py "$INSPECTION_INSTRUCTION"`；CronJob 默认暂停。
