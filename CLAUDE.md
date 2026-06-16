# robot-eval

机器人训练与评测项目，基于 lw_benchhub + Isaac Sim 5.0。

## 环境

- 评测容器: `lw_benchhub`（host 网络）
- 仿真引擎: `isaac-sim5.0`（NVIDIA Isaac Sim 5.0）
- IPC 地址: `127.0.0.1:50000`（env_server）

## 快速开始

```bash
# 1. 启动 env_server（在 lw_benchhub 容器内）
docker exec -d lw_benchhub bash -c "
  source /opt/conda/etc/profile.d/conda.sh && conda activate lw_benchhub &&
  cd /workspace/lw_benchhub &&
  python lw_benchhub/scripts/env_server.py --headless > /tmp/env_server.log 2>&1"

# 2. 运行评测
docker exec lw_benchhub bash -c "
  source /opt/conda/etc/profile.d/conda.sh && conda activate lw_benchhub &&
  cd /workspace/lw_benchhub &&
  python /home/disk/lrx/robot-eval/scripts/eval.py \
    --task LiftObj --layout robocasakitchen-9-8 --robot LeRobot-RL"
```

## 目录结构

```
scripts/        评测/训练脚本
configs/        任务、场景、机器人配置
results/        评测结果（JSON + 视频）
notebooks/      分析用 Jupyter notebook
```

## 可用任务

| task | layout | robot |
|------|--------|-------|
| LiftObj | robocasakitchen-9-8 | LeRobot-RL |

## 指标说明

- `success_rate`: 成功次数 / 总测试次数
- `UPH`: 成功数 / 总耗时(小时)，Units Per Hour
- `avg_cycle_s`: 平均单轮耗时（秒）
- `theoretical_max_uph`: 3600 / avg_cycle_s（100% 成功率上限）
