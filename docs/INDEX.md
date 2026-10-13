# Prometheus 巡检 Agent 文档索引

面向开发人员与 SRE 的协作文档。正文以 8 章手册为准，架构/接口/开发指南为同一内容的拆分视图。

## 8 章手册（一次性全套）

完整正文：当前工作区 内的 `/.monkeycode/docs/HANDBOOK.md`

1. [项目总览](HANDBOOK.md#1-项目总览) — 业务目标、技术栈、设计原则、目录、整体架构
2. [模块划分与模块职责](HANDBOOK.md#2-模块划分与模块职责) — 文件职责与依赖
3. [核心类与核心函数](HANDBOOK.md#3-核心类与核心函数文档) — 入参、返回值
4. [业务时序](HANDBOOK.md#4-业务时序文档) — 一次巡检的端到端数据流
5. [核心数据结构](HANDBOOK.md#5-核心数据结构文档) — 指标元数据、Skill payload、工具入参
6. [扩展开发指南](HANDBOOK.md#6-扩展开发指南) — 新增 Skill / 新增指标
7. [设计取舍、风险与坑点](HANDBOOK.md#7-设计取舍潜在风险与坑点梳理)
8. [最小使用示例](HANDBOOK.md#8-最小使用示例) — 调用样例与 JSON

## Wiki 拆分视图

| 文档 | 覆盖章节 |
| --- | --- |
| 当前工作区 内的 `/.monkeycode/docs/ARCHITECTURE.md` | 第 1、2、4、7 章 |
| 当前工作区 内的 `/.monkeycode/docs/INTERFACES.md` | 第 3、5 章 |
| 当前工作区 内的 `/.monkeycode/docs/DEVELOPER_GUIDE.md` | 第 6、8 章 |

## 专有概念

- 当前工作区 内的 `/.monkeycode/docs/专有概念/Skill插件.md`
- 当前工作区 内的 `/.monkeycode/docs/专有概念/意图解析.md`
- 当前工作区 内的 `/.monkeycode/docs/专有概念/Prometheus查询与实例绑定.md`

## 模块

- 当前工作区 内的 `/.monkeycode/docs/模块/agent.md`
- 当前工作区 内的 `/.monkeycode/docs/模块/graph.md`
- 当前工作区 内的 `/.monkeycode/docs/模块/skills.md`
