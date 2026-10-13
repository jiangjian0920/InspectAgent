# 模块：LangGraph 编排

路径：`agent/graph.py`

状态：`user_input, intent, results(reducer 追加), extra_suggestions, report`。

节点：`parse_intent` -> `Send` 到各 Skill -> `suggest` -> `report`。Skill 节点由 `agent.skills.all_skills()` 动态创建。
