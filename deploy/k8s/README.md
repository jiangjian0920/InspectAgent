# Kubernetes 部署

面向新架构（`python -m app` + FastAPI）的清单。所有资源位于 `inspect-agent` 命名空间。

| 文件 | 资源 | 说明 |
| --- | --- | --- |
| `namespace.yaml` | Namespace | 命名空间 |
| `configmap-env.yaml` | ConfigMap `inspect-agent-env` | 环境变量：Prometheus、查询策略、GLM 模型 |
| `configmap-configs.yaml` | ConfigMap `inspect-agent-configs` | `assets.yaml` 与 `policies.yaml`，挂载到 `/app/configs` |
| `secret.yaml` | Secret `inspect-agent-secret` | `ZHIPU_API_KEY` |
| `deployment-api.yaml` | Deployment `inspect-agent-api` | FastAPI 服务，含 `/health` 探针 |
| `service.yaml` | Service `inspect-agent-api` | ClusterIP:8000 |
| `job.yaml` | Job `inspect-agent-once` | 一次性巡检，输出 JSON |
| `cronjob.yaml` | CronJob `inspect-agent-schedule` | 定时巡检，默认 `suspend: true` |
| `kustomization.yaml` | Kustomization | 统一编排与镜像标签 |

## 前置

构建并推送镜像，或在集群节点上加载本地镜像：

```bash
# 构建镜像
docker build -t inspect-agent:v1 .

# 推送到镜像仓库后，用 kustomize 覆盖镜像地址
cd deploy/k8s
kustomize edit set image inspect-agent=registry.example.com/inspect-agent:v1
```

## 部署

部署前必须修改：

1. `deploy/k8s/secret.yaml` 的 `ZHIPU_API_KEY`（留空则使用规则回退解析）。
2. `deploy/k8s/configmap-env.yaml` 的 `PROMETHEUS_URL`。
3. `deploy/k8s/configmap-configs.yaml` 的 `assets.yaml`，把服务器资产替换为真实实例。

```bash
# 应用全部资源
kubectl apply -k deploy/k8s

# 查看状态
kubectl -n inspect-agent get pods,svc
kubectl -n inspect-agent rollout status deploy/inspect-agent-api
```

## 校验与调用

```bash
# 配置检查
kubectl -n inspect-agent exec deploy/inspect-agent-api -- python -m app --check-config

# 只输出执行计划，不访问 Prometheus
kubectl -n inspect-agent exec deploy/inspect-agent-api -- python -m app --plan "查看 CPU 使用率最高的机器"

# 通过 Service 调用 API
kubectl -n inspect-agent port-forward svc/inspect-agent-api 8000:8000
curl -s localhost:8000/health
curl -s localhost:8000/capabilities
curl -s -X POST localhost:8000/inspect \
  -H 'Content-Type: application/json' \
  -d '{"instruction": "查询服务器 192.168.59.130 的 CPU"}'
```

## 一次性巡检

```bash
# 修改指令
kubectl -n inspect-agent patch configmap inspect-agent-env \
  --type merge -p '{"data":{"INSPECTION_INSTRUCTION":"查询最近 4 天的服务器异常清单"}}'

# 重新触发 Job
kubectl -n inspect-agent delete job inspect-agent-once
kubectl apply -f deploy/k8s/job.yaml

# 查看结果
kubectl -n inspect-agent logs job/inspect-agent-once
```

## 定时巡检

`cronjob.yaml` 默认 `suspend: true`，确认调度周期与影响后启用：

```bash
kubectl -n inspect-agent patch cronjob inspect-agent-schedule \
  -p '{"spec":{"suspend":false}}'
```

## 安全基线

- 全部容器 `runAsNonRoot`、`readOnlyRootFilesystem: true`、drop 全部 capability。
- `assets.yaml`、`policies.yaml` 只读挂载。
- 模型只接收用户请求与受控配置，不接触 Prometheus 与 API Key。
