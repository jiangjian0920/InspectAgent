# 接口文档

字段级 schema 以 当前工作区 内的 `/.monkeycode/docs/HANDBOOK.md` 第 3、5 章为准。

## 对外入口

| 调用 | 行为 |
| --- | --- |
| `python main.py <指令>` | `InspectionAgent.run` 打印报告 |
| `python main.py` | 交互循环 |
| `--selftest` | 18 项离线自测 |
| `--plan` | 只打印将调用的 Skill |
| `--check-config` | 静态配置检查 |
| `--doctor` | 依赖与 SDK 诊断 |

`InspectionAgent.run(user_input: str) -> str`

## Skill.execute

入参：`instance: str`、`metrics: list[str]`、`time_range: str`。

返回 payload：`ok, skill, target_type, instance, scope, time_range, instance_found, message, anomalies, checked, checked_count, healthy, error`。

checked 行：`metric_key, metric, instance, labels, current, latest, avg, max, unit, threshold_warning, threshold_critical, severity, risk, error, promql`。

## 意图

`parse_intent(instruction, default_time_range="2h") -> InspectionIntent`

target：`{target_type, skill, instance, metrics}`。`metrics=[]` 表示组件基础健康集。

## PrometheusClient.query_range

入参 PromQL 与时间范围。成功含 `series[{metric, sample_count, latest, max, min, avg}]`。失败含真实 `error`。
