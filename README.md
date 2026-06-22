# Robot Eval Platform

分布式机器人仿真评测平台。基于 Ray + Isaac Sim，支持多模型评测、Elo 排行榜、GPU 调度。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户 / 浏览器                              │
│                    http://localhost:8000                          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  FastAPI 后端 (backend/main.py)                                   │
│                                                                   │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌─────────────┐  │
│  │ JobEngine │  │ Scheduler │  │NodeManager│  │ ArenaEngine │  │
│  │ 任务管理   │  │ GPU 调度   │  │ 节点管理   │  │ Elo 对战    │  │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └──────┬──────┘  │
│        │               │               │               │          │
│  ┌─────▼───────────────▼───────────────▼───────────────▼──────┐  │
│  │                    PostgreSQL                                │  │
│  │  jobs | runs | episodes | matches | elo_ratings | nodes     │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────┘
                               │ Ray API
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Worker 0    │     │  Worker 1    │     │  Worker N    │
│  Ray Actor   │     │  Ray Actor   │     │  Ray Actor   │
│  Isaac Sim   │     │  Isaac Sim   │     │  Isaac Sim   │
│  GPU 0       │     │  GPU 1       │     │  GPU N       │
└──────────────┘     └──────────────┘     └──────────────┘
```

## 核心功能

| 模块 | 功能 |
|------|------|
| **评测提交** | Web 表单 / API 提交评测任务，支持内置策略和远程 Policy Server |
| **GPU 调度** | 优先级堆 + Bin Packing，显存感知，GPU 型号亲和 |
| **节点管理** | 自动发现 Ray 节点，心跳检测，drain/undrain 操作 |
| **结果分析** | 成功率、UPH、cycle time 等指标，支持 baseline 对比 |
| **Elo 排行榜** | 模型对战 Arena，Glicko-2 评分，胜率矩阵 |
| **实时画面** | Isaac Sim 仿真画面 MJPEG 流 |

## 调度规则（当前）

```
Job 提交 → 进入优先级堆（priority 小=高优先）
              │
              ▼
       调度器取堆顶 Job
              │
              ▼
    遍历所有 Worker，过滤:
     ① busy=true → 跳过
     ② gpu_type 不匹配 → 跳过
     ③ gpu_count 不够 → 跳过
              │
              ▼
    剩余候选按"剩余显存升序"排序
    选最小的（Bin Packing）
              │
              ▼
     派发执行 actor.run_job()
              │
         ┌────┴────┐
         ▼         ▼
       成功       失败 → 2^n 秒退避重试（最多 max_retries 次）
         │
         ▼
    worker 标记空闲，唤醒调度器处理下一个
```

**当前限制**: 1 GPU = 1 Worker = 同时 1 Job（不支持 GPU 共享）

## 目录结构

```
robot-eval/
├── backend/
│   ├── main.py                 # FastAPI 入口，启动串联
│   ├── base_actor.py           # Actor 协议定义 + gpu_info() 实现
│   ├── arena_actor.py          # Isaac Lab Arena Actor 实现
│   ├── api/
│   │   ├── jobs.py             # POST /api/jobs 提交评测
│   │   ├── runs.py             # 运行记录查询
│   │   ├── workers.py          # Worker 状态 + Ray 集群信息
│   │   ├── nodes.py            # 节点管理（drain/undrain）
│   │   ├── arena.py            # Elo 对战 API
│   │   ├── analysis.py         # 结果分析 / baseline 对比
│   │   ├── templates.py        # 评测模板管理
│   │   ├── results.py          # 排行榜
│   │   └── configs.py          # 前端配置
│   ├── engines/
│   │   ├── scheduler.py        # GPU 调度器（RayScheduler + K8sScheduler）
│   │   ├── job_engine.py       # 任务创建 / 取消 / 复现
│   │   ├── arena_engine.py     # Elo 对战引擎
│   │   ├── analysis_engine.py  # 分析引擎
│   │   └── node_manager.py     # 节点心跳 / 健康检查
│   ├── db/
│   │   ├── schema.py           # 建表 + migration
│   │   └── queries/            # 每个实体一个模块（jobs/runs/episodes/nodes...）
│   ├── elo/
│   │   ├── calculator.py       # Glicko-2 算法
│   │   └── significance.py     # 统计显著性检验
│   └── runners/
│       ├── registry.py         # Runner 注册表
│       ├── isaaclab_runner.py   # Isaac Lab 仿真 Runner
│       ├── lmeval_runner.py    # LM-Eval Runner
│       └── remote_policy.py    # 远程 Policy Server 客户端
├── frontend/
│   └── src/
│       ├── App.tsx             # 路由
│       ├── api.ts              # 后端 API 客户端
│       ├── types.ts            # TypeScript 类型
│       └── components/
│           ├── SubmitView.tsx   # 任务提交表单（含 GPU 调度选项）
│           ├── JobsView.tsx     # 任务列表 + 日志
│           ├── WorkersView.tsx  # Worker 状态 + 集群面板
│           ├── ArenaView.tsx    # Elo 对战
│           ├── LeaderboardView.tsx
│           ├── ResultsView.tsx
│           └── ...
├── deploy/
│   ├── README.md              # 部署文档
│   └── k8s/                   # K8s 部署 yaml（KubeRay + Volcano）
├── tests/                     # 83 个测试（pytest）
├── docker-compose.yml         # 本地部署（Ray Head + Worker + Postgres + 平台）
├── Dockerfile                 # 平台镜像
└── Makefile                   # make up / down / build / fe / logs
```

## 快速启动

```bash
# 启动所有服务
make up

# 前端开发（热更新）
cd frontend && npm run dev

# 跑测试
python3.10 -m pytest tests/ -q

# 查看日志
make logs
```

## 数据流

```
1. 用户在 SubmitView 填表 → POST /api/jobs
2. JobEngine.create_job() → 写 DB + Scheduler.enqueue()
3. Scheduler 从优先级堆取 job → 匹配空闲 Worker
4. Worker (Ray Actor) 执行 Isaac Sim 仿真
5. 返回 metrics → 写 runs 表 + episodes 表
6. Worker 释放 → Scheduler 处理下一个 job
7. 前端轮询展示结果 / Leaderboard 更新
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval` | 数据库 |
| `RAY_ADDRESS` | `ray://127.0.0.1:10001` | Ray 集群地址 |
| `SCHEDULER_BACKEND` | `ray` | 调度后端：`ray`（本地）或 `k8s`（Volcano） |
| `EVAL_ACTOR_MODULE` | `arena_actor` | Actor 类所在模块 |
| `EVAL_ACTOR_CLASS` | `IsaacLabArenaActor` | Actor 类名 |
