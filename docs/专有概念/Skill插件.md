# Skill 插件

Skill 是一类巡检能力的 Python 类。框架底座只认注册表里的 `name`，用 LangGraph 节点去调 `execute()`。

## 三层关系

1. 框架底座：`InspectionAgent`、`build_inspection_graph`、`SkillRegistry`
2. 公共工具：`agent/skills/common.py`、`PrometheusClient`、`evaluate_result`
3. 可插拔插件：`server_inspect` / `redis_inspect` / `kafka_inspect` / `k8s_inspect`

## 注册、发现、调用

1. 注册：`build_default_skills()` 实例化四个 Skill，写入 `SkillRegistry`
2. 发现：编译图时 `agent.skills.all_skills()` 按 `skill.name` 加成节点
3. 调用：意图节点产出 `targets[].skill`，`route_skills` 用 `Send(name, {instance, metrics, time_range})` 投递；节点内 `agent._run_one()` -> `skill.execute()`

## 探活与按需查询

`execute()` 固定顺序：规范化指标 -> `probe_instance` -> 失败则 `instance_found=false` -> 成功则 `run_metric_queries` 只查本次 `metrics`。

点名指标来自意图解析；空列表表示该组件基础健康集（`default_metrics()`）。

完整说明见 当前工作区 内的 `/.monkeycode/docs/HANDBOOK.md` 第 4、6 章。
