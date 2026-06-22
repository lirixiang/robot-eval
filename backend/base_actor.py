"""
base_actor.py — Pluggable EvalActor protocol

To use your own simulator / eval framework instead of isaaclab_arena:

1. Create a class that implements the two methods below.
2. Decorate it with @ray.remote(num_gpus=1).
3. Set environment variables in docker-compose (or .env):
       EVAL_ACTOR_MODULE=my_package.my_actor
       EVAL_ACTOR_CLASS=MyActor
       EVAL_PYTHONPATH=/path/to/my_package   # added to PYTHONPATH in worker

Example minimal implementation
-------------------------------
import ray

@ray.remote(num_gpus=1)
class MyActor:
    def __init__(self, worker_id: int, frame_port: int = 8765):
        self.worker_id = worker_id
        self._busy = False
        # initialise your simulator here

    def status(self) -> dict:
        return {"worker_id": self.worker_id, "busy": self._busy, "status": "ready"}

    def run_job(self, job_dict: dict) -> dict:
        '''
        job_dict keys (all optional except env_args):
          name        : str   — human-readable job name
          env_args    : dict  — passed verbatim to your env constructor
          num_envs    : int
          num_episodes: int | None
          num_steps   : int | None
          policy_type : str
          policy_config: dict

        Returns a metrics dict, at minimum:
          {"success_rate": float,   # 0-1
           "uph":          float,   # units per hour
           "avg_cycle_s":  float}   # seconds per episode
        '''
        self._busy = True
        try:
            metrics = run_your_eval(job_dict)
            return metrics
        finally:
            self._busy = False

job_dict compatibility note
----------------------------
The platform passes job_dict straight through from the API request body.
For backward-compat with isaaclab_arena, the field "arena_env_args" is also
forwarded. New implementations should use "env_args".
"""

from __future__ import annotations
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EvalActorProtocol(Protocol):
    """
    Structural protocol — your Ray Actor just needs these two methods.
    No inheritance required.
    """

    def status(self) -> dict[str, Any]:
        """
        Returns at minimum: {"worker_id": int, "busy": bool, "status": str}
        May include extra keys (gpu_util, vram_used, etc.) — the platform
        forwards them to the /api/workers endpoint as-is.
        """
        ...

    def run_job(self, job_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Runs one eval job and returns a metrics dict.

        Recommended metric keys (used by the platform's dashboard & charts):
          success_rate  : float  — fraction of successful episodes (0–1)
          uph           : float  — units per hour (successes / total_hours)
          avg_cycle_s   : float  — mean seconds per episode
          total_episodes: int
          success_count : int

        Any extra keys are stored in the result JSON as-is.
        """
        ...

    def gpu_info(self) -> dict[str, Any]:
        """
        Returns GPU status for scheduling decisions.
        Keys: free_memory_mb, total_memory_mb, gpu_type, utilization_pct, temperature
        Default implementation uses nvidia-smi; override for custom behavior.
        """
        ...


def load_actor_class(module_name: str, class_name: str):
    """
    Dynamically import the actor class at worker startup.

    Called by platform/backend/main.py at startup:
        ActorClass = load_actor_class(
            os.environ["EVAL_ACTOR_MODULE"],
            os.environ["EVAL_ACTOR_CLASS"],
        )
    """
    import importlib
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    return cls


def query_gpu_info() -> dict[str, Any]:
    """
    Default gpu_info() implementation using nvidia-smi.
    Actor classes can call this directly or override with custom logic.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=memory.free,memory.total,name,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {"free_memory_mb": 0, "total_memory_mb": 0, "gpu_type": "",
                    "utilization_pct": 0, "temperature": 0}
        parts = [p.strip() for p in result.stdout.strip().split(",")]
        return {
            "free_memory_mb":  int(parts[0]) if parts[0].isdigit() else 0,
            "total_memory_mb": int(parts[1]) if parts[1].isdigit() else 0,
            "gpu_type":        parts[2] if len(parts) > 2 else "",
            "utilization_pct": int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0,
            "temperature":     int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0,
        }
    except Exception:
        return {"free_memory_mb": 0, "total_memory_mb": 0, "gpu_type": "",
                "utilization_pct": 0, "temperature": 0}
