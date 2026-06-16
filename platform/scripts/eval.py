"""
lw_benchhub 评测调用示例
用法：在 lw_benchhub 容器内执行

先启动 env_server（另一个终端）：
    docker exec -it lw_benchhub bash
    cd /workspace/lw_benchhub
    bash env_server.sh

再运行本脚本：
    docker exec -it lw_benchhub bash
    cd /workspace/lw_benchhub
    python /path/to/isaaclab_eval.py --task LiftObj --layout robocasakitchen --test_num 20

指标说明：
    success_rate  = 成功次数 / 总测试次数
    UPH           = 成功次数 / 总耗时(小时)  ← Units Per Hour，机器人每小时完成任务数
    avg_cycle_s   = 每轮平均耗时（秒）
    theoretical_max_uph = 假设100%成功时的最大UPH
"""

import argparse
import json
import time
from pathlib import Path

# ─── CLI ─────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="lw_benchhub 评测 + UPH 计算")
parser.add_argument("--task",        type=str, default="LiftObj",           help="任务名称")
parser.add_argument("--layout",      type=str, default="robocasakitchen",   help="场景布局")
parser.add_argument("--robot",       type=str, default="LeRobot-RL",         help="机器人配置名 (e.g. LeRobot-RL, LeRobot-AbsJointGripper-RL)")
parser.add_argument("--test_num",    type=int, default=10,                  help="测试轮数")
parser.add_argument("--time_limit",  type=float, default=60.0,              help="每轮超时秒数")
parser.add_argument("--ipc_host",    type=str, default="127.0.0.1",         help="env_server 地址")
parser.add_argument("--ipc_port",    type=int, default=50000,               help="env_server 端口")
parser.add_argument("--output",      type=str, default="eval_result.json",  help="结果输出文件")
parser.add_argument("--headless",    action="store_true", default=True,     help="无头模式")
parser.add_argument("--save_video",  action="store_true", default=False,    help="保存每轮视频到 eval_videos/")
args = parser.parse_args()


# ─── 连接 env_server ──────────────────────────────────────────────────────────
def connect_env():
    """连接到已在容器内运行的 env_server，返回 RemoteEnv 代理对象"""
    import sys
    sys.path.insert(0, "/workspace/lw_benchhub")

    from lw_benchhub.distributed.proxy import RemoteEnv
    from lw_benchhub.distributed.restful import DotDict

    print(f"[连接] {args.ipc_host}:{args.ipc_port} ...")
    env = RemoteEnv.make(
        address=(args.ipc_host, args.ipc_port),
        authkey=b"lightwheel",
    )

    # 配置环境参数（对应 env_server_base.yml 的字段）
    env_cfg = DotDict({
        "task":              args.task,
        "layout":            args.layout,
        "robot":             args.robot,
        "scene_backend":     "robocasa",
        "task_backend":      "robocasa",
        "device":            "cuda:0",
        "num_envs":          1,
        "robot_scale":       1.0,
        "first_person_view": False,
        "disable_fabric":    False,
        "usd_simplify":      False,
        "video":             False,
        "for_rl":            False,
        "concatenate_terms": False,
        "distributed":       False,
        "seed":              42,
        "sources":           ["objaverse", "lightwheel"],
        "object_projects":   [],
        "execute_mode":      "eval",
        "replay_cfgs":       {"add_camera_to_observation": args.save_video},
    })
    env.attach(env_cfg)
    print("[连接] 环境就绪")
    return env


# ─── 随机策略（占位，替换成你的真实策略）─────────────────────────────────────
class RandomPolicy:
    """示例：随机动作策略。替换 get_action() 接入你的模型。"""
    def __init__(self, action_dim: int):
        import numpy as np
        self.action_dim = action_dim
        self.np = np

    def reset(self):
        pass

    def get_action(self, obs):
        return self.np.random.uniform(-1, 1, (1, self.action_dim)).astype("float32")


# ─── 单轮评测 ─────────────────────────────────────────────────────────────────
def run_one_episode(env, policy, time_limit: float, video_path=None):
    """
    执行一个 episode，返回 (success: bool, duration_seconds: float)
    """
    import torch
    import numpy as np

    obs, _ = env.reset()
    policy.reset()

    frames = [] if video_path else None
    t0 = time.perf_counter()
    success = False

    while True:
        elapsed = time.perf_counter() - t0
        if elapsed >= time_limit:
            break

        action = policy.get_action(obs)
        action_tensor = torch.from_numpy(action).float().cuda()

        obs, _reward, terminated, _truncated, extras = env.step(action_tensor)
        terminated = bool(torch.as_tensor(terminated).any().item())

        # 采集相机帧
        if frames is not None:
            try:
                cam_keys = [k for k in obs['policy'].keys() if 'rgb' in k.lower() or 'image' in k.lower() or 'camera' in k.lower()]
                if cam_keys:
                    img = obs['policy'][cam_keys[0]].cpu().numpy()[0]
                    if img.dtype != np.uint8:
                        img = (img * 255).clip(0, 255).astype(np.uint8)
                    frames.append(img)
            except Exception:
                pass

        if terminated:
            success = bool(extras.get("success", extras.get("is_success", False)))
            break

    duration = time.perf_counter() - t0

    # 保存视频
    if video_path and frames:
        try:
            import mediapy
            Path(video_path).parent.mkdir(parents=True, exist_ok=True)
            mediapy.write_video(str(video_path), frames, fps=30)
            print(f"    视频保存: {video_path} ({len(frames)} 帧)")
        except Exception as e:
            print(f"    [警告] 视频保存失败: {e}")

    return success, duration


# ─── 计算 UPH ─────────────────────────────────────────────────────────────────
def compute_uph(success_count: int, total_seconds: float) -> float:
    """
    UPH (Units Per Hour) = 成功完成的任务数 / 总运行时间(小时)

    这是衡量机器人实际生产效率的核心指标：
      - 如果每次任务耗时 30s，成功率 80%，则 UPH ≈ (3600/30) * 0.8 = 96
      - 如果每次任务耗时 45s，成功率 60%，则 UPH ≈ (3600/45) * 0.6 = 48
    """
    if total_seconds <= 0:
        return 0.0
    return success_count / (total_seconds / 3600.0)


# ─── 主流程 ───────────────────────────────────────────────────────────────────
def main():
    env = connect_env()

    action_dim = env.action_space.shape[1]
    policy = RandomPolicy(action_dim=action_dim)

    print(f"\n{'='*50}")
    print(f"任务: {args.task}  |  布局: {args.layout}  |  共 {args.test_num} 轮")
    print(f"{'='*50}\n")

    success_count = 0
    durations = []
    wall_start = time.perf_counter()

    for i in range(args.test_num):
        video_path = Path(f"eval_videos/test_{i+1}.mp4") if args.save_video else None
        success, dur = run_one_episode(env, policy, time_limit=args.time_limit, video_path=video_path)
        if success:
            success_count += 1
        durations.append(dur)
        print(f"  轮次 {i+1:>3}/{args.test_num}  {'✓ 成功' if success else '✗ 失败'}  耗时 {dur:.1f}s"
              f"  累计 {success_count}/{i+1}")

    wall_total = time.perf_counter() - wall_start

    # ── 指标汇总 ──
    success_rate       = success_count / args.test_num
    avg_cycle_s        = sum(durations) / len(durations)
    uph                = compute_uph(success_count, wall_total)
    theoretical_max_uph = 3600.0 / avg_cycle_s  # 假设100%成功

    results = {
        "task":                  args.task,
        "layout":                args.layout,
        "test_num":              args.test_num,
        "success_count":         success_count,
        "success_rate":          round(success_rate, 4),
        "avg_cycle_seconds":     round(avg_cycle_s, 2),
        "total_wall_seconds":    round(wall_total, 2),
        "uph":                   round(uph, 2),
        "theoretical_max_uph":   round(theoretical_max_uph, 2),
    }

    print(f"\n{'='*50}")
    print(f"  成功率:           {success_rate:.1%}  ({success_count}/{args.test_num})")
    print(f"  平均单轮耗时:     {avg_cycle_s:.1f} 秒")
    print(f"  总耗时:           {wall_total:.1f} 秒")
    print(f"  UPH:              {uph:.1f}  (每小时实际完成任务数)")
    print(f"  理论最大 UPH:     {theoretical_max_uph:.1f}  (100% 成功率时)")
    print(f"{'='*50}\n")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    print(f"结果已保存: {output_path}")

    env.close_connection()


if __name__ == "__main__":
    main()
