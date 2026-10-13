# 模块：Skill 插件

路径：`agent/skills/`

- `base.py`：抽象与注册表
- `common.py`：探活、查询、payload
- `catalogs.py`：指标目录
- 四个 `*_inspect.py`：组件插件

`execute` 固定：normalize -> probe -> query -> skill_payload。
