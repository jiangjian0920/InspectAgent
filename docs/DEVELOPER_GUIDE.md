# 开发者指南

扩展步骤与示例见 当前工作区 内的 `/.monkeycode/docs/HANDBOOK.md` 第 6、8 章。

## 本地

```bash
pip install -r requirements.txt
cp .env.example .env
python3 main.py --selftest
python3 main.py --plan 做一个全面巡检
```

只装 `zai-sdk==0.2.3`，不要并行安装 `zhipuai`。

## 新增 Skill

1. `Thresholds` + env + ConfigMap
2. `catalogs.py` 指标目录
3. `agent/skills/xxx_inspect.py` 继承 `Skill`，探活后 `run_metric_queries`
4. `build_default_skills()` register
5. `intent.py` 关键词与实例解析
6. `tests/selftest.py`

图会按注册表自动加成节点。意图不加关键词时仍默认 `server`。

## 新增指标

改对应 catalog（主机改 `host_metrics.py`），补阈值与意图关键词，更新 FakePrometheus。

## 约束

- 指定实例必须过滤 + 绑定，找不到就停
- 禁止编造数据、禁止未点名扩查其它组件
- 变更建议标注需要人工确认后执行
- `invoke` 时 `results` 初始为 `[]`
