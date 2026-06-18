"""
arena_actor.py — Reference EvalActor implementation using isaaclab_arena
...
Actor 名称：'arena-worker-{worker_id}'，namespace='robot-eval'
"""
from __future__ import annotations
import json
import os
import sys
import time
import traceback

# ── Isaac Sim Python 路径（模块加载时立即设置，__init__ 之前）─────────────────
# Ray worker 进程使用 Isaac Lab 的 Python，但不自动 source setup_python_env.sh
_ISAAC = "/workspaces/isaaclab_arena/submodules/IsaacLab/_isaac_sim"
_ISAAC_PATHS = [
    "/workspaces/isaaclab_arena",
    "/workspaces/isaaclab_arena/isaaclab_arena_environments",
    f"{_ISAAC}/kit/python/lib/python3.12",
    f"{_ISAAC}/kit/python/lib/python3.12/site-packages",
    f"{_ISAAC}/python_packages",
    f"{_ISAAC}/exts/isaacsim.simulation_app",
    f"{_ISAAC}/kit/kernel/py",
    f"{_ISAAC}/kit/plugins/bindings-python",
    f"{_ISAAC}/exts/isaacsim.robot_motion.lula/pip_prebundle",
    f"{_ISAAC}/exts/isaacsim.robot_motion.cumotion/pip_prebundle",
    f"{_ISAAC}/exts/isaacsim.asset.exporter.urdf/pip_prebundle",
    f"{_ISAAC}/exts/omni.isaac.core_archive/pip_prebundle",
    f"{_ISAAC}/exts/omni.isaac.ml_archive/pip_prebundle",
    f"{_ISAAC}/exts/omni.pip.compute/pip_prebundle",
    f"{_ISAAC}/exts/omni.pip.cloud/pip_prebundle",
]
import glob as _glob
for _p in _glob.glob(f"{_ISAAC}/extscache/omni.kit.pip_archive-*/pip_prebundle"):
    _ISAAC_PATHS.append(_p)
for _p in _ISAAC_PATHS:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Isaac Sim 动态库和环境变量
os.environ.setdefault("CARB_APP_PATH", f"{_ISAAC}/kit")
os.environ.setdefault("ISAAC_PATH",    _ISAAC)
os.environ.setdefault("EXP_PATH",      f"{_ISAAC}/apps")
os.environ.setdefault("RESOURCE_NAME", "IsaacSim")
_ld_extra = ":".join([_ISAAC, f"{_ISAAC}/kit", f"{_ISAAC}/kit/kernel/plugins",
                      f"{_ISAAC}/kit/plugins", f"{_ISAAC}/kit/plugins/carb_gfx",
                      f"{_ISAAC}/kit/plugins/gpu.foundation"])
os.environ["LD_LIBRARY_PATH"] = _ld_extra + ":" + os.environ.get("LD_LIBRARY_PATH", "")

import ray


@ray.remote(num_gpus=1)
class IsaacLabArenaActor:
    """
    持久化 Ray Actor：Isaac Sim 启动一次，串行处理多个 eval job。
    Native WebRTC streaming via isaacsim.exp.full.streaming kit.
    """

    def __init__(self, worker_id: int, http_port: int = 8042, livestream_port: int = 49200):
        self.worker_id       = worker_id
        self.http_port       = http_port
        self.livestream_port = livestream_port
        self._busy           = False

        # ── Isaac Sim 所需的 Python 路径（必须在任何 Isaac 相关 import 前）───
        import os, sys
        _ISAAC = "/workspaces/isaaclab_arena/submodules/IsaacLab/_isaac_sim"
        _extra_paths = [
            "/workspaces/isaaclab_arena",
            "/workspaces/isaaclab_arena/isaaclab_arena_environments",
            f"{_ISAAC}/kit/python/lib/python3.12",
            f"{_ISAAC}/kit/python/lib/python3.12/site-packages",
            f"{_ISAAC}/python_packages",
            f"{_ISAAC}/exts/isaacsim.simulation_app",
            f"{_ISAAC}/kit/kernel/py",
            f"{_ISAAC}/kit/plugins/bindings-python",
            f"{_ISAAC}/exts/isaacsim.robot_motion.lula/pip_prebundle",
            f"{_ISAAC}/exts/isaacsim.robot_motion.cumotion/pip_prebundle",
            f"{_ISAAC}/exts/isaacsim.asset.exporter.urdf/pip_prebundle",
            f"{_ISAAC}/exts/omni.isaac.core_archive/pip_prebundle",
            f"{_ISAAC}/exts/omni.isaac.ml_archive/pip_prebundle",
            f"{_ISAAC}/exts/omni.pip.compute/pip_prebundle",
            f"{_ISAAC}/exts/omni.pip.cloud/pip_prebundle",
        ]
        import glob
        for p in glob.glob(f"{_ISAAC}/extscache/omni.kit.pip_archive-*/pip_prebundle"):
            _extra_paths.append(p)
        for p in _extra_paths:
            if p not in sys.path:
                sys.path.insert(0, p)
        os.environ.setdefault("CARB_APP_PATH", f"{_ISAAC}/kit")
        os.environ.setdefault("ISAAC_PATH",    _ISAAC)
        os.environ.setdefault("EXP_PATH",      f"{_ISAAC}/apps")
        os.environ.setdefault("RESOURCE_NAME", "IsaacSim")
        _ld = ":".join([_ISAAC, f"{_ISAAC}/kit", f"{_ISAAC}/kit/kernel/plugins",
                        f"{_ISAAC}/kit/plugins", f"{_ISAAC}/kit/plugins/carb_gfx",
                        f"{_ISAAC}/kit/plugins/gpu.foundation"])
        os.environ["LD_LIBRARY_PATH"] = _ld + ":" + os.environ.get("LD_LIBRARY_PATH", "")

        # ── 注入 per-worker 端口作为 Kit CLI 覆盖参数 ──────────────────────────
        # AppLauncher 解析 sys.argv；在它之前插入 kit 设置覆盖
        _kit_overrides = [
            f"--/app/livestream/port={self.livestream_port}",
            f"--/exts/omni.services.transport.server.http/port={self.http_port}",
            "--/exts/omni.services.transport.server.http/allow_port_range=false",
            f"--/app/livestream/url=ws://0.0.0.0:{self.livestream_port}",
            "--experience", "/workspace/robot-eval/isaac-sim/streaming_local.kit",
        ]
        sys.argv = sys.argv[:1] + _kit_overrides + sys.argv[1:]

        # ── 用 AppLauncher 启动（正确初始化 GPU/PhysX + 原生 WebRTC 流）─────
        import argparse
        from isaaclab.app import AppLauncher

        parser = argparse.ArgumentParser()
        AppLauncher.add_app_launcher_args(parser)
        launcher_args = parser.parse_args(["--headless", "--device", "cuda:0", "--livestream", "2"])
        self._app_launcher = AppLauncher(launcher_args)
        self._sim_app      = self._app_launcher.app

        print(f"[arena-worker-{worker_id}] Isaac Sim ready "
              f"(HTTP :{self.http_port}, WebRTC :{self.livestream_port})", flush=True)

    # ── 视口帧捕获（MJPEG 流）────────────────────────────────────────────

    def capture_frame(self, quality: int = 75) -> bytes:
        """Capture current viewport as JPEG bytes for MJPEG streaming."""
        import io
        try:
            import omni.kit.viewport.utility as vp_util
            from PIL import Image
            import numpy as np

            vp = vp_util.get_active_viewport()
            frame = vp_util.capture_viewport_to_buffer(vp)
            if frame is not None:
                img = Image.fromarray(np.asarray(frame)[:, :, :3])
            else:
                img = Image.new("RGB", (320, 240), (10, 12, 20))
        except Exception:
            from PIL import Image
            img = Image.new("RGB", (320, 240), (10, 12, 20))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    # ── 健康检查 ──────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "worker_id":       self.worker_id,
            "status":          "ready",
            "busy":            self._busy,
            "http_port":       self.http_port,
            "livestream_port": self.livestream_port,
        }

    # ── 核心：运行一个 eval job ───────────────────────────────────────────

    @staticmethod
    def _to_python(obj):
        """Recursively convert numpy scalars/arrays to Python builtins for safe serialization."""
        try:
            import numpy as np
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        if isinstance(obj, dict):
            return {k: IsaacLabArenaActor._to_python(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return type(obj)(IsaacLabArenaActor._to_python(v) for v in obj)
        return obj

    def run_job(self, job_dict: dict) -> dict:
        """
        job_dict 格式：
        {
            "name": "my_job",
            "arena_env_args": { "environment": "lift_object", "embodiment": "franka" },
            "num_envs":     1,
            "num_episodes": 10,
            "num_steps":    None,
            "policy_type":  "zero_action",     # ignored when policy_server_url is set
            "policy_config_dict": {},
            # Optional: call external policy server instead of built-in policy
            "policy_server_url": "http://192.168.1.100:7860",
        }
        Returns metrics dict (all values converted to Python builtins).
        """
        self._busy = True
        try:
            policy_server_url = job_dict.get("policy_server_url", "").strip()
            if policy_server_url:
                result = self._run_job_remote_policy(job_dict, policy_server_url)
            else:
                result = self._run_job_builtin_policy(job_dict)
            return IsaacLabArenaActor._to_python(result)
        except Exception as e:
            traceback.print_exc()
            raise
        finally:
            self._busy = False

    def _run_job_builtin_policy(self, job_dict: dict) -> dict:
        """Run eval with built-in isaaclab_arena policy (original behavior)."""
        from isaaclab_arena.evaluation.eval_runner import load_env, get_policy_from_job
        from isaaclab_arena.evaluation.policy_runner import rollout_policy
        from isaaclab_arena.evaluation.job_manager import Job

        job = Job.from_dict(job_dict)
        print(f"[arena-worker-{self.worker_id}] builtin job '{job.name}'", flush=True)

        env    = load_env(job.arena_env_args, job.name)
        policy = get_policy_from_job(job)
        metrics = rollout_policy(
            env, policy,
            num_steps=job.num_steps,
            num_episodes=job.num_episodes,
            language_instruction=job.language_instruction,
        )
        env.close()

        # Build episode list from aggregate metrics (best effort)
        result = metrics if metrics is not None else {}
        result["episodes"] = _build_episode_list(result)
        print(f"[arena-worker-{self.worker_id}] builtin job done", flush=True)
        return result

    def _run_job_remote_policy(self, job_dict: dict, policy_url: str) -> dict:
        """
        Run eval where actions come from an external HTTP policy server.

        The rollout loop:
          1. env.reset() → obs
          2. POST /reset on policy server
          3. Loop: POST /act → actions → env.step(actions) → obs
          4. Collect metrics
        """
        import requests
        from isaaclab_arena.evaluation.eval_runner import load_env
        from isaaclab_arena.evaluation.job_manager import Job

        job = Job.from_dict(job_dict)
        print(f"[arena-worker-{self.worker_id}] remote-policy job '{job.name}' → {policy_url}", flush=True)

        # Verify policy server is reachable
        try:
            info_resp = requests.get(f"{policy_url}/info", timeout=5)
            policy_info = info_resp.json()
            print(f"[arena-worker-{self.worker_id}] policy: {policy_info.get('model','?')} by {policy_info.get('submitter','?')}", flush=True)
        except Exception as e:
            raise RuntimeError(f"Cannot reach policy server at {policy_url}: {e}")

        env = load_env(job.arena_env_args, job.name)
        action_dim = env.action_space.shape[-1] if hasattr(env.action_space, "shape") else 8

        success_count  = 0
        total_episodes = job.num_episodes or 10
        cycle_times    = []

        for ep in range(total_episodes):
            episode_id = f"{job.name}_ep{ep}"
            obs, _ = env.reset()
            obs_dict = self._obs_to_dict(obs, action_dim)

            # Notify policy server: new episode
            requests.post(f"{policy_url}/reset", json={
                "episode_id": episode_id,
                "env_info": {"action_dim": action_dim, "environment": job_dict["arena_env_args"].get("environment", "")},
            }, timeout=5)

            done       = False
            step       = 0
            ep_start   = time.time()
            max_steps  = job.num_steps or 500

            while not done and step < max_steps:
                t0 = time.time()

                # Get action from policy server
                act_resp = requests.post(f"{policy_url}/act", json={
                    "observations": obs_dict,
                    "episode_id":   episode_id,
                    "step":         step,
                }, timeout=10)
                actions = act_resp.json()["actions"]

                # Step environment
                import numpy as np
                obs, reward, terminated, truncated, info = env.step(np.array(actions))
                obs_dict = self._obs_to_dict(obs, action_dim)

                done  = terminated or truncated
                step += 1

            ep_time = time.time() - ep_start
            cycle_times.append(ep_time)

            # Check success from env info
            if info.get("success", False) or info.get("is_success", False):
                success_count += 1

            print(f"[arena-worker-{self.worker_id}] ep {ep+1}/{total_episodes} "
                  f"{'✓' if info.get('success') else '✗'} {ep_time:.1f}s", flush=True)

        env.close()

        avg_cycle_s = sum(cycle_times) / len(cycle_times) if cycle_times else 0
        uph         = 3600 / avg_cycle_s if avg_cycle_s > 0 else 0
        metrics = {
            "success_rate":        success_count / total_episodes,
            "success_count":       success_count,
            "total_episodes":      total_episodes,
            "avg_cycle_s":         round(avg_cycle_s, 3),
            "uph":                 round(uph, 2),
            "theoretical_max_uph": round(uph, 2),
            "policy_model":        policy_info.get("model", "unknown"),
            "policy_submitter":    policy_info.get("submitter", "unknown"),
        }
        print(f"[arena-worker-{self.worker_id}] remote-policy job done: {metrics}", flush=True)
        return metrics

    def _obs_to_dict(self, obs, action_dim: int) -> dict:
        """Convert isaaclab obs tensor/dict to JSON-serializable dict for policy server."""
        import numpy as np

        def to_list(x):
            if hasattr(x, "cpu"):     # torch tensor
                return x.cpu().numpy().tolist()
            if isinstance(x, np.ndarray):
                return x.tolist()
            return x

        result = {k: to_list(v) for k, v in obs.items()} if isinstance(obs, dict) else {"obs": to_list(obs)}
        result["action_dim"] = action_dim
        return result


def _build_episode_list(metrics: dict) -> list[dict]:
    """Build synthetic episode list from aggregate metrics when per-episode data unavailable."""
    n  = int(metrics.get("num_episodes") or metrics.get("total_episodes") or 0)
    sr = float(metrics.get("success_rate") or 0.0)
    successes = int(round(n * sr))
    return [
        {
            "episode_index":      i,
            "success":            i < successes,
            "reward_total":       0.0,
            "steps":              0,
            "termination_reason": "success" if i < successes else "timeout",
            "metadata":           {},
        }
        for i in range(n)
    ]
