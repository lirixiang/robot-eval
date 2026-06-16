"""
eval_runner.py — 独立评测 runner，不依赖 lw_benchhub
直接在本项目 Isaac Sim 容器内运行评测任务

用法（由 platform backend 调用）：
    python eval_runner.py --job_id xxx --task LiftObj --layout robocasakitchen-9-8 \
                          --robot LeRobot-RL --test_num 10 --output results/xxx.json
"""
import argparse
import json
import time
import random
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--job_id",    type=str, required=True)
parser.add_argument("--task",      type=str, default="LiftObj")
parser.add_argument("--layout",    type=str, default="robocasakitchen-9-8")
parser.add_argument("--robot",     type=str, default="LeRobot-RL")
parser.add_argument("--test_num",  type=int, default=10)
parser.add_argument("--time_limit",type=float, default=60.0)
parser.add_argument("--output",    type=str, required=True)
args = parser.parse_args()

def log(msg: str):
    print(msg, flush=True)


def run_episode(idx: int) -> tuple[bool, float]:
    """
    TODO: 接入你的 Isaac Sim 评测逻辑
    当前为模拟实现：随机成功/失败 + 随机耗时
    替换此函数即可对接真实环境
    """
    t0 = time.perf_counter()
    # --- 模拟评测过程 ---
    cycle_time = random.uniform(8, args.time_limit * 0.8)
    time.sleep(min(cycle_time * 0.05, 2.0))  # 实际不等待，仅模拟进度
    success = random.random() < 0.65  # 65% 基准成功率
    duration = cycle_time
    # --- end ---
    return success, duration


def main():
    log(f"[{args.job_id}] 开始评测: task={args.task} layout={args.layout} robot={args.robot}")
    log(f"[{args.job_id}] 共 {args.test_num} 轮，单轮超时 {args.time_limit}s")

    success_count = 0
    durations = []
    wall_start = time.perf_counter()

    for i in range(args.test_num):
        success, dur = run_episode(i)
        if success:
            success_count += 1
        durations.append(dur)
        status = "✓ 成功" if success else "✗ 失败"
        log(f"[{args.job_id}] 轮次 {i+1:>3}/{args.test_num}  {status}  "
            f"耗时 {dur:.1f}s  累计 {success_count}/{i+1}")

    wall_total = time.perf_counter() - wall_start
    success_rate = success_count / args.test_num
    avg_cycle_s  = sum(durations) / len(durations)
    uph          = success_count / (wall_total / 3600) if wall_total > 0 else 0
    theoretical_max_uph = 3600 / avg_cycle_s

    result = {
        "job_id":               args.job_id,
        "task":                 args.task,
        "layout":               args.layout,
        "robot":                args.robot,
        "test_num":             args.test_num,
        "success_count":        success_count,
        "success_rate":         round(success_rate, 4),
        "avg_cycle_seconds":    round(avg_cycle_s, 2),
        "total_wall_seconds":   round(wall_total, 2),
        "uph":                  round(uph, 2),
        "theoretical_max_uph":  round(theoretical_max_uph, 2),
        "timestamp":            time.time(),
    }

    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    log(f"[{args.job_id}] 完成 | 成功率 {success_rate:.1%} | UPH {uph:.1f} | 结果 → {args.output}")


if __name__ == "__main__":
    main()
