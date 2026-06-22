# 🤖 RoboEval

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev)
[![Ray](https://img.shields.io/badge/Ray-2.52-blue.svg)](https://docs.ray.io)

**基于 Isaac Lab + Ray 的分布式机器人策略评测平台**

[English](README_EN.md) · [问题反馈](https://github.com/lirixiang/robot-eval/issues)

![screenshot](docs/screenshot.png)

---

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 📋 **任务提交** | 可视化表单配置环境、机器人本体、策略类型，实时 JSON 预览 |
| 📊 **任务队列** | 实时日志流、取消/重试、状态追踪 |
| 🏆 **竞技榜单** | Glicko-2 Elo 排名，bootstrap 置信区间显著性检验 |
| 🔬 **结果分析** | 多轮次对比、趋势图、逐 episode 指标 |
| 🖥️ **Worker 管理** | Ray 集群实时状态，GPU 利用率，节点扩缩容 |
| 🔌 **外部模型接入** | HTTP Policy Server 协议，标准接口快速接入 |
| 🎥 **实时预览** | Isaac Sim WebRTC 原生推流，MJPEG 备用 |

## 🏗️ 架构

```
┌─────────────────────────────────────────┐
│           浏览器 (React 18)              │
└────────────────┬────────────────────────┘
                 │ HTTP / SSE
┌────────────────▼────────────────────────┐
│        FastAPI 平台服务                  │
│   JobScheduler · ArenaEngine · API      │
└──────┬──────────────────────┬───────────┘
       │ asyncpg              │ Ray Client
┌──────▼──────┐    ┌──────────▼───────────┐
│ PostgreSQL  │    │     Ray 集群          │
│   (任务/    │    │  ray-head + worker-* │
│    榜单)    │    │  IsaacLabArenaActor  │
└─────────────┘    └──────────────────────┘
```

**技术栈**

- 后端：FastAPI · asyncpg · structlog · Ray 2.52
- 前端：React 18 · TypeScript · Vite · Tailwind CSS
- 仿真：Isaac Lab 3.0 / Isaac Sim 6.0（NVIDIA NGC）
- 分布式：Ray Client 模式，GPU worker 按需扩展

## 🚀 快速开始

### 前置条件

- Docker + Docker Compose
- NVIDIA GPU（Isaac Lab worker 需要）
- `isaaclab_arena:latest` 镜像（或自行从 Dockerfile.worker 构建）

### 1. 克隆仓库

```bash
git clone https://github.com/lirixiang/robot-eval.git
cd robot-eval
```

### 2. 配置环境

```bash
cp .env.example .env
# 编辑 .env，按需修改密码和路径
```

### 3. 修改 Isaac Sim 缓存路径

编辑 `docker-compose.yml`，将 worker 的 volume 路径替换为你的 Isaac Sim 安装目录：

```yaml
volumes:
  - /your/isaacsim/cache/ov:/root/.cache/ov
  - /your/isaacsim/cache/kit:/isaac-sim/kit/cache
  # ... 其余缓存路径
```

### 4. 构建并启动

```bash
# 构建前端
cd frontend && npm install && npm run build && cd ..

# 启动所有服务
docker compose up -d
```

访问 **http://localhost:8000**

### 5. 扩展 Worker 节点

在其他 GPU 机器上执行：

```bash
docker run -d --runtime=nvidia --network=host \
  --gpus='"device=0"' \
  -v /your/isaacsim:/your/isaacsim \
  isaaclab_arena:latest \
  bash -c "ray start --address=<主节点IP>:6379 --num-gpus=1 --block"
```

## ⚙️ 配置说明

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `DATABASE_URL` | `postgresql://eval:...@127.0.0.1:5432/robot_eval` | PostgreSQL 连接串 |
| `RAY_ADDRESS` | `ray://127.0.0.1:10001` | Ray Client 连接地址 |
| `EVAL_ACTOR_MODULE` | `arena_actor` | Actor 模块名 |
| `EVAL_ACTOR_CLASS` | `IsaacLabArenaActor` | Actor 类名 |
| `EVAL_PYTHONPATH` | `/workspaces/isaaclab_arena:...` | Isaac Lab Python 路径 |

> 自定义 eval 后端：实现与 `IsaacLabArenaActor` 相同接口的类，设置 `EVAL_ACTOR_MODULE` / `EVAL_ACTOR_CLASS` / `EVAL_PYTHONPATH` 即可替换。

## 🔌 外部模型接入

实现以下三个接口即可接入榜单：

```python
from policy_server import PolicyBase, serve

class MyPolicy(PolicyBase):
    info = {"model": "my-model", "submitter": "My Lab"}

    def reset(self, episode_id, env_info): ...

    def act(self, observations, episode_id, step):
        return [0.0] * observations["action_dim"]

serve(MyPolicy(), port=7860)
```

在评测表单选择「外部模型」，填入 `http://<your-server>:7860` 即可。

## 📁 项目结构

```
robot-eval/
├── backend/
│   ├── api/          # FastAPI 路由（jobs/workers/configs/arena）
│   ├── db/           # asyncpg 数据库层 + schema
│   ├── engines/      # JobScheduler · ArenaEngine
│   ├── runners/      # BaseRunner + IsaacLabRunner 插件
│   ├── arena_actor.py        # Ray Actor（Isaac Sim 封装）
│   └── main.py               # 应用入口 + lifespan
├── frontend/
│   └── src/
│       └── components/       # EvalView · JobsView · WorkersView · ...
├── isaac-sim/
│   └── streaming_local.kit   # Isaac Sim WebRTC 流配置
├── docker-compose.yml
├── Dockerfile
└── Dockerfile.worker         # 无私有镜像时自行构建
```

## 🤝 贡献

欢迎 PR 和 Issue。提交规范参考 [Conventional Commits](https://www.conventionalcommits.org)。

## ⚠️ 免责声明

本项目仅用于科研与工程评测，仿真结果不代表真实物理环境性能。

## 📬 联系作者

如有问题或合作意向，欢迎通过 GitHub Issues 联系。

**如果这个项目对你有帮助，欢迎 Star ⭐**

<div align="center">
  <img src="docs/alipay-qr.jpg" width="160" alt="支付宝" />
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="docs/wechat-qr.jpg" width="160" alt="微信" />
</div>
