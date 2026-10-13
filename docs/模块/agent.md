# 模块：InspectionAgent

路径：`agent/agent.py`

门面：懒编译 LangGraph，`run()` invoke 后取 `report`。`_run_one` 按名从注册表取 Skill 并 `execute`。`_ask_llm` 只基于真实 Skill 结果补建议，`tools=None`。
