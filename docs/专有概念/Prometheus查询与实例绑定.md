# Prometheus 查询与实例绑定

Skill 内部通过 `PrometheusClient.query_range` 调 `/api/v1/query_range`。LLM 不再持有查询工具。

指定实例时：

1. `apply_instance_filter` 把 `instance=~"192[.]168[.]59[.]131(:[0-9]+)?"` 写入 PromQL（点号用字符类，避免正则误匹配）
2. `bind_result` / `bind_prometheus_result_to_instance` 只保留标签属于该实例的序列
3. 一条都对不上 -> `ok=false`，错误里写明本次实际返回的 instance，禁止改用其他主机数据

矩阵最多摘要 20 条序列，超出部分带 `_note`。评估时 `_note` 序列会被丢掉。

详见 当前工作区 内的 `/.monkeycode/docs/HANDBOOK.md` 第 5、7 章。
