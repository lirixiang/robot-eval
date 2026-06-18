"""
eval_runner.py — Ray remote 函数，通过 IsaacLabArenaActor 执行评测

平台通过 ray.remote(run_eval).remote(...) 提交，
run_eval 内部找到 Actor 并调用 run_job。
"""
import json
import time
from pathlib import Path


def run_eval(
    job_id:      str,
    actor_name:  str,
    job_dict:    dict,
    output_path: str,
) -> dict:
    """
    在 Ray 集群上运行：找到 Actor → 提交 job → 收集 metrics → 写结果文件。

    job_dict 格式（与 isaaclab_arena eval_jobs_config.json 的 jobs[] 元素相同）：
    {
        "name": "...",
        "arena_env_args": {"environment": "lift_object", "embodiment": "franka", ...},
        "num_envs": 1,
        "num_episodes": 10,
        "policy_type": "zero_action",
        "policy_config_dict": {}
    }
    """
    import ray

    def log(msg):
        print(f"[{job_id}] {msg}", flush=True)

    log(f"分配 actor: {actor_name}")
    actor = ray.get_actor(actor_name, namespace="robot-eval")

    log(f"开始评测 job={job_dict.get('name')} env={job_dict.get('arena_env_args', {}).get('environment')}")
    t0 = time.perf_counter()

    metrics = ray.get(actor.run_job.remote(job_dict))

    elapsed = time.perf_counter() - t0
    log(f"完成，耗时 {elapsed:.1f}s，metrics={metrics}")

    result = {
        "job_id":    job_id,
        "actor":     actor_name,
        "job":       job_dict,
        "metrics":   metrics,
        "elapsed_s": round(elapsed, 2),
        "timestamp": time.time(),
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    log(f"结果写入 {output_path}")
    return result
