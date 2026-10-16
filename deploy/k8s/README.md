# Kubernetes 部署

面向新架构（`python -m app` + FastAPI）的清单。所有资源位于 `wanchi` 命名空间。

| 文件 | 资源 | 说明 |
| --- | --- | --- |
| `namespace.yaml` | Namespace | 命名空间 |
| `configmap-env.yaml` | ConfigMap `wanchi-env` | 环境变量：Prometheus、查询策略、GLM 模型 |
| `configmap-configs.yaml` | ConfigMap `wanchi-configs` | `assets.yaml` 与 `policies.yaml`，挂载到 `/app/configs` |
| `secret.yaml` | Secret `wanchi-secret` | `ZHIPU_API_KEY` |
| `deployment-api.yaml` | Deployment `wanchi-api` | FastAPI 服务，含 `/health` 探针 |
| `service.yaml` | Service `wanchi-api` | ClusterIP:8000 |
| `job.yaml` | Job `wanchi-once` | 一次性巡检，输出 JSON |
| `cronjob.yaml` | CronJob `wanchi-schedule` | 定时巡检，默认 `suspend: true` |
| `kustomization.yaml` | Kustomization | 统一编排与镜像标签 |

## 前置

构建并推送镜像，或在集群节点上加载本地镜像：

```bash
# 构建镜像
docker build -t wanchi:v1 .

# 推送到镜像仓库后，用 kustomize 覆盖镜像地址
cd deploy/k8s
kustomize edit set image wanchi=registry.example.com/wanchi:v1
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
kubectl -n wanchi get pods,svc
kubectl -n wanchi rollout status deploy/wanchi-api
```

## 校验与调用

```bash
# 配置检查
kubectl -n wanchi exec deploy/wanchi-api -- python -m app --check-config

# 只输出执行计划，不访问 Prometheus
kubectl -n wanchi exec deploy/wanchi-api -- python -m app --plan "查看 CPU 使用率最高的机器"

# 通过 Service 调用 API
kubectl -n wanchi port-forward svc/wanchi-api 8000:8000
curl -s localhost:8000/health
curl -s localhost:8000/capabilities
curl -s -X POST localhost:8000/inspect \
  -H 'Content-Type: application/json' \
  -d '{"instruction": "查询服务器 192.168.59.130 的 CPU"}'
```

## 一次性巡检

```bash
# 修改指令
kubectl -n wanchi patch configmap wanchi-env \
  --type merge -p '{"data":{"INSPECTION_INSTRUCTION":"查询最近 4 天的服务器异常清单"}}'

# 重新触发 Job
kubectl -n wanchi delete job wanchi-once
kubectl apply -f deploy/k8s/job.yaml

# 查看结果
kubectl -n wanchi logs job/wanchi-once
```

## 定时巡检

`cronjob.yaml` 默认 `suspend: true`，确认调度周期与影响后启用：

```bash
kubectl -n wanchi patch cronjob wanchi-schedule \
  -p '{"spec":{"suspend":false}}'
```

## 安全基线

- 全部容器 `runAsNonRoot`、`readOnlyRootFilesystem: true`、drop 全部 capability。
- `assets.yaml`、`policies.yaml` 只读挂载。
- 模型只接收用户请求与受控配置，不接触 Prometheus 与 API Key。
