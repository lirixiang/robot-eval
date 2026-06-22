# GPU 调度与部署

## 架构概览

```
┌────────────────────────────────────────────────────────────────┐
│                    robot-eval 平台 (FastAPI)                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ SchedulerBackend (抽象接口)                                │  │
│  │   ├── RayScheduler   ← 优先级堆 + Bin Packing (默认)      │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ NodeManager — 节点注册 / 心跳 / 健康检查                    │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────┬───────────────────────────────────────┘
                         │ Ray API
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ Worker 0 │   │ Worker 1 │   │ Worker N │
   │ GPU ×1   │   │ GPU ×1   │   │ GPU ×1   │
   │ Isaac Sim│   │ Isaac Sim│   │ Isaac Sim│
   └──────────┘   └──────────┘   └──────────┘
```

## 部署方式

### 方式一：本地 docker-compose（开发/小规模）

```bash
docker-compose up -d
# 默认: SCHEDULER_BACKEND=ray
# 平台: http://localhost:8000
# Ray Dashboard: http://localhost:8265
```

扩容 GPU 节点：
```bash
# 在新机器上执行
docker run -d --runtime=nvidia --network=host \
  --gpus='"device=0"' \
  isaaclab_arena:latest \
  bash -c "ray start --address=<主节点IP>:6379 --num-gpus=1 --block"
```

### 方式二：K8s + KubeRay（推荐生产部署）

**适用场景**：多节点集群、需要弹性伸缩、多团队共享

```bash
# 1. 安装前置组件
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm install kuberay-operator kuberay/kuberay-operator

# 2. 部署
kubectl apply -f deploy/k8s/04-secrets.yaml
kubectl apply -f deploy/k8s/00-postgres.yaml
kubectl apply -f deploy/k8s/01-raycluster.yaml
kubectl apply -f deploy/k8s/02-platform.yaml
kubectl apply -f deploy/k8s/05-autoscaler.yaml   # 可选：自动伸缩

# 3. 验证
kubectl -n robot-eval get pods
kubectl -n robot-eval port-forward svc/robot-eval-svc 8000:8000
```

环境变量（在 `02-platform.yaml` 中配置）：
```
RAY_ADDRESS=ray://ray-head-svc.robot-eval.svc:10001
SCHEDULER_BACKEND=ray
```

### 方式三：K8s + Volcano（无 Ray，轻量任务）

**适用场景**：不需要长驻 Actor，每个评测任务起一个 Pod 跑完销毁

```bash
# 1. 安装 Volcano
helm repo add volcano https://volcano-sh.github.io/charts
helm install volcano volcano/volcano -n volcano-system --create-namespace

# 2. 部署 Volcano 配置
kubectl apply -f deploy/k8s/03-volcano.yaml

# 3. 平台配置
# 修改 02-platform.yaml 中的环境变量:
#   SCHEDULER_BACKEND=k8s
```

## 调度策略

### RayScheduler（SCHEDULER_BACKEND=ray）

| 策略 | 说明 |
|------|------|
| **优先级堆** | priority 字段（1=最高, 9=最低），低值优先出队 |
| **Bin Packing** | 选剩余资源最少但满足需求的 worker，减少碎片 |
| **GPU 型号亲和** | job 指定 gpu_type 时只调度到匹配的节点 |
| **显存感知** | 每 10s 通过 nvidia-smi 刷新 worker GPU 状态 |
| **指数退避重试** | 失败后 2^n 秒重试，最多 max_retries 次 |

### K8sScheduler（SCHEDULER_BACKEND=k8s）

| 策略 | 说明 |
|------|------|
| **Volcano Queue** | 按 submitter 分队列，权重分配 GPU 配额 |
| **PriorityClass** | priority 1-2→critical, 3-4→high, 5-7→normal, 8-9→low |
| **Gang Scheduling** | minAvailable=1，所有 Pod 资源满足才调度 |
| **Bin Packing** | nodeorder 插件 mostrequested.weight=10 |
| **Backfill** | 大任务排队时小任务可插空执行 |

## API 接口

### 任务提交（含 GPU 调度字段）

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "eval_pick_cube",
    "arena_env_args": {"environment": "PickAndPlace"},
    "num_episodes": 100,
    "policy_type": "remote",
    "policy_server_url": "http://model-server:7860",
    "model_name": "pi0.5",
    "submitter": "team-sim",
    "priority": 2,
    "num_gpus": 1,
    "gpu_type": "A100"
  }'
```

### 节点管理

```bash
# 查看所有节点
curl http://localhost:8000/api/nodes

# 下线节点（不再分配新任务）
curl -X POST http://localhost:8000/api/nodes/{node_id}/drain

# 恢复节点
curl -X POST http://localhost:8000/api/nodes/{node_id}/undrain

# 强制刷新 Ray 节点列表
curl -X POST http://localhost:8000/api/nodes/refresh
```

### 集群状态

```bash
# Ray 状态 + 队列深度
curl http://localhost:8000/api/ray/status
# → {"online":true, "nodes":3, "gpu_total":6, "gpu_used":2, "queue_depth":5}
```

## 文件结构

```
deploy/k8s/
├── 00-postgres.yaml      # PostgreSQL 数据库
├── 01-raycluster.yaml    # KubeRay 集群（Ray Head + GPU Workers）
├── 02-platform.yaml      # robot-eval 平台 Deployment + Service + Ingress
├── 03-volcano.yaml       # Volcano 配置（可选，仅 SCHEDULER_BACKEND=k8s 时需要）
├── 04-secrets.yaml       # 密钥
└── 05-autoscaler.yaml    # GPU Worker 自动伸缩（可选）

backend/engines/
├── scheduler.py          # SchedulerBackend 抽象 + RayScheduler + K8sScheduler
└── node_manager.py       # 节点管理（心跳/健康检查）
```

## 迁移指南

### docker-compose → K8s + KubeRay

1. **Python 代码不需要改**，只换部署层
2. 修改 `RAY_ADDRESS` 环境变量指向 K8s 内部 service
3. 删除 docker-compose.yml 中的 ray-head 和 worker 服务
4. `kubectl apply -f deploy/k8s/`

### 后续升级到 Volcano

1. 安装 Volcano helm chart
2. 应用 `03-volcano.yaml`（Queue + PriorityClass）
3. 修改平台环境变量 `SCHEDULER_BACKEND=k8s`
4. 重启平台 Pod

两种后端可以**共存**——通过环境变量随时切换，无需重新部署代码。
