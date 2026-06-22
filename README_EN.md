# 🤖 RoboEval

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev)
[![Ray](https://img.shields.io/badge/Ray-2.52-blue.svg)](https://docs.ray.io)

**Distributed Robot Policy Evaluation Platform built on Isaac Lab + Ray**

[中文](README.md) · [Issues](https://github.com/lirixiang/robot-eval/issues)

![screenshot](docs/screenshot.png)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 📋 **Job Submission** | Visual form for environment, embodiment, policy config with live JSON preview |
| 📊 **Job Queue** | Real-time log streaming, cancel/retry, status tracking |
| 🏆 **Arena Leaderboard** | Glicko-2 Elo ranking with bootstrap CI significance testing |
| 🔬 **Result Analysis** | Multi-run comparison, trend charts, per-episode metrics |
| 🖥️ **Worker Management** | Ray cluster status, GPU utilization, node scale-out |
| 🔌 **External Model Integration** | HTTP Policy Server protocol for easy model submission |
| 🎥 **Live Preview** | Isaac Sim native WebRTC streaming, MJPEG fallback |

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│           Browser (React 18)            │
└────────────────┬────────────────────────┘
                 │ HTTP / SSE
┌────────────────▼────────────────────────┐
│         FastAPI Platform Service        │
│   JobScheduler · ArenaEngine · API      │
└──────┬──────────────────────┬───────────┘
       │ asyncpg              │ Ray Client
┌──────▼──────┐    ┌──────────▼───────────┐
│ PostgreSQL  │    │     Ray Cluster       │
│  (jobs /    │    │  ray-head + worker-* │
│  rankings)  │    │  IsaacLabArenaActor  │
└─────────────┘    └──────────────────────┘
```

**Tech Stack**

- Backend: FastAPI · asyncpg · structlog · Ray 2.52
- Frontend: React 18 · TypeScript · Vite · Tailwind CSS
- Simulation: Isaac Lab 3.0 / Isaac Sim 6.0 (NVIDIA NGC)
- Distributed: Ray Client mode, GPU workers scale horizontally

## 🚀 Quick Start

### Prerequisites

- Docker + Docker Compose
- NVIDIA GPU (required for Isaac Lab workers)
- `isaaclab_arena:latest` image (or build from `Dockerfile.worker`)

### 1. Clone

```bash
git clone https://github.com/lirixiang/robot-eval.git
cd robot-eval
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — update passwords and paths as needed
```

### 3. Set Isaac Sim cache paths

Edit `docker-compose.yml` and replace worker volume paths with your Isaac Sim installation:

```yaml
volumes:
  - /your/isaacsim/cache/ov:/root/.cache/ov
  - /your/isaacsim/cache/kit:/isaac-sim/kit/cache
  # ... other cache paths
```

### 4. Build and start

```bash
# Build frontend
cd frontend && npm install && npm run build && cd ..

# Start all services
docker compose up -d
```

Open **http://localhost:8000**

### 5. Add worker nodes

On additional GPU machines:

```bash
docker run -d --runtime=nvidia --network=host \
  --gpus='"device=0"' \
  -v /your/isaacsim:/your/isaacsim \
  isaaclab_arena:latest \
  bash -c "ray start --address=<head-node-ip>:6379 --num-gpus=1 --block"
```

## ⚙️ Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://eval:...@127.0.0.1:5432/robot_eval` | PostgreSQL connection string |
| `RAY_ADDRESS` | `ray://127.0.0.1:10001` | Ray Client address |
| `EVAL_ACTOR_MODULE` | `arena_actor` | Actor module name |
| `EVAL_ACTOR_CLASS` | `IsaacLabArenaActor` | Actor class name |
| `EVAL_PYTHONPATH` | `/workspaces/isaaclab_arena:...` | Isaac Lab Python path |

> **Custom eval backend**: Implement the same interface as `IsaacLabArenaActor` and set `EVAL_ACTOR_MODULE` / `EVAL_ACTOR_CLASS` / `EVAL_PYTHONPATH` to swap it in.

## 🔌 External Model Integration

Implement three endpoints to join the leaderboard:

```python
from policy_server import PolicyBase, serve

class MyPolicy(PolicyBase):
    info = {"model": "my-model", "submitter": "My Lab"}

    def reset(self, episode_id, env_info): ...

    def act(self, observations, episode_id, step):
        return [0.0] * observations["action_dim"]

serve(MyPolicy(), port=7860)
```

Select "外部模型" in the submission form and enter `http://<your-server>:7860`.

## 📁 Structure

```
robot-eval/
├── backend/
│   ├── api/          # FastAPI routers (jobs/workers/configs/arena)
│   ├── db/           # asyncpg database layer + schema
│   ├── engines/      # JobScheduler · ArenaEngine
│   ├── runners/      # BaseRunner + IsaacLabRunner plugin
│   ├── arena_actor.py        # Ray Actor (Isaac Sim wrapper)
│   └── main.py               # App entry + lifespan
├── frontend/
│   └── src/components/       # EvalView · JobsView · WorkersView · ...
├── isaac-sim/
│   └── streaming_local.kit   # Isaac Sim WebRTC stream config
├── docker-compose.yml
├── Dockerfile
└── Dockerfile.worker         # Build worker image without private registry
```

## 🤝 Contributing

PRs and issues are welcome. Please follow [Conventional Commits](https://www.conventionalcommits.org).

## ⚠️ Disclaimer

This project is for research and engineering evaluation only. Simulation results do not represent real-world physical performance.

## ⭐ Support

If this project helps you, please give it a star!

<div align="center">
  <img src="docs/alipay-qr.jpg" width="160" alt="Alipay" />
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="docs/wechat-qr.jpg" width="160" alt="WeChat" />
</div>
