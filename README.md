# AI Prometheus 巡检 Agent

基于智谱 GLM-5.3 与 LangGraph 的单 Agent + 可插拔 Skill 架构。图先解析意图，再用 `Send` 把目标路由到对应 Skill 节点。Skill 内部完成 Prometheus 查询和阈值判断，只把异常项交给报告层。

当前 Skill：`server_inspect`、`redis_inspect`、`kafka_inspect`、`k8s_inspect`。新增巡检类型时实现 Skill 并在 `build_default_skills()` 注册，图会自动把它加成节点。

Agent 只做查询分析，不会自动修改服务器或集群。变更建议标注：需要人工确认后执行。

## 功能

- 意图先行：先提取对象类型、实例标识、指标范围，再调用 Skill
- 可插拔 Skill：主机 / Redis / Kafka / Kubernetes
- 实例先校验：查不到实例直接返回「未找到对应实例」，不再查业务指标
- 指标收窄：`查询服务器 192.168.59.130 的 cpu` 只查 CPU
- 单轮调用：一次请求最多一轮 Skill；全集群才并行四个 Skill
- 只回异常：正常指标不进入报告，减少 token
- 禁止编造监控数据

## 环境准备

- Python >= 3.10
- 可访问的智谱开放平台 API Key
- 已接入对应 exporter 的 Prometheus

## 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

官方 Python SDK 使用 `zai-sdk==0.2.3`，导入 `from zai import ZhipuAiClient`。不要同时安装旧包 `zhipuai`。

编辑 `.env`，至少填写：

```bash
ZHIPU_API_KEY=你的智谱密钥
PROMETHEUS_URL=http://你的Prometheus地址:9090
ZHIPU_MODEL=glm-5.3
```

## 启动命令

交互模式：

```bash
python main.py
```

单次指令：

```bash
python main.py 查询服务器 192.168.59.130 的 cpu
python main.py 巡检 redis6404
python main.py 全集群巡检
```

离线自测：

```bash
python main.py --selftest
```

只看规划：

```bash
python main.py --plan 查询服务器 192.168.59.130 的 cpu
```

检查配置：

```bash
python main.py --check-config
```

## 测试调用示例

| 指令 | 解析结果 | 行为 |
| --- | --- | --- |
| `巡检 redis6404` | 对象 redis，实例 redis6404 | 调用 `redis_inspect`，基础健康巡检 |
| `查询服务器 192.168.59.130 的 cpu` | 对象 server，实例 192.168.59.130，指标 cpu | 只查 CPU，不查内存磁盘 |
| `帮我查看当前服务器的/目录磁盘使用量` | 对象 server，指标 disk | 只查磁盘 |
| `全集群巡检` / `做一个全面巡检` | 四个 Skill | 并行调用全部 Skill |
| `帮我查看 192.168.59.131 这台服务器` | 对象 server，实例 192.168.59.131 | 实例不存在则返回「未找到对应实例」 |

## 架构

```text
用户指令
  -> LangGraph 意图节点（对象 / 实例 / 指标）
  -> Send 到匹配 Skill 节点（全集群并行）
  -> Skill：校验实例 -> PromQL -> 阈值判断 -> 只返回异常
  -> 建议节点（可选 LLM）-> 报告节点
```

```text
main.py                         命令行入口
agent/agent.py                  InspectionAgent，编译并 invoke LangGraph
agent/graph.py                  StateGraph：意图 / Skill / 建议 / 报告
agent/intent.py                 自然语言意图解析
agent/skills/base.py            Skill 基类与注册表
agent/skills/server_inspect.py  主机巡检
agent/skills/redis_inspect.py   Redis 巡检
agent/skills/kafka_inspect.py   Kafka 巡检
agent/skills/k8s_inspect.py     Kubernetes 巡检
agent/prometheus_client.py      Prometheus HTTP 客户端（Skill 内部使用）
agent/report/builder.py         异常报告
tests/selftest.py               离线自测
```

后续新增巡检类型：新建 `agent/skills/xxx_inspect.py`，在 `agent/skills/__init__.py` 的 `build_default_skills()` 中 `register`。每人只维护自己的 Skill 文件。

## Skill 内置逻辑

1. 收到实例后先探活（如 `up` / `redis_up` / `kafka_brokers` / `kube_pod_info`）
2. 实例不存在：立即返回「未找到对应实例」
3. PromQL、阈值、数值比较都在 Skill 代码里完成，不交给 LLM
4. 返回已检查指标的当前值、均值、峰值和阈值；超阈值项同时放进 `anomalies`

## 工具调用约束

- 单次用户请求最多一轮 Skill 调用
- 未说全集群时，只调用匹配的 Skill
- 一个 Skill 一次执行完该对象的全部点名指标

## 报告规范

- 标注实例和巡检范围
- 已检查指标都列出：当前值、最新值、均值、峰值、警告/严重阈值
- 异常项额外标注风险说明
- 找不到实例：返回「未找到对应实例」

## Docker 与 Kubernetes

```bash
docker build -t inspect-agent:v1 .
```

部署前改 `deploy/k8s/secret.yaml` 的 `ZHIPU_API_KEY`，以及 `deploy/k8s/configmap.yaml` 的 `PROMETHEUS_URL`。

```bash
kubectl apply -k deploy/k8s
kubectl -n inspect-agent exec -it deploy/inspect-agent -- python main.py --doctor
kubectl -n inspect-agent exec -it deploy/inspect-agent -- python main.py 查询服务器 192.168.59.130 的 cpu
```

## 约束

- 所有指标必须来自 Prometheus，禁止编造
- 禁止主动查询用户没提到的组件和指标
- 禁止一次性拉取 Prometheus 全部指标
- 变更操作只作为建议，并标注需要人工确认后执行
