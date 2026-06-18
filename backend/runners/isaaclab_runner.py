from __future__ import annotations
import time
import structlog
from backend.runners.base import BaseRunner, RunResult, EpisodeResult

logger = structlog.get_logger(__name__)

class IsaacLabRunner(BaseRunner):
    """Dispatches a run_job call to a Ray Actor (IsaacLabArenaActor)."""

    def __init__(self, config: dict):
        self.actor_name = config.get("actor_name", "arena-worker-0")
        self.namespace  = config.get("namespace", "robot-eval")
        self._timeout   = config.get("timeout_s", 3600)

    def health_check(self) -> bool:
        try:
            import ray
            actor = ray.get_actor(self.actor_name, namespace=self.namespace)
            status = ray.get(actor.status.remote(), timeout=3)
            return not status.get("busy", True)
        except Exception:
            return False

    async def run(self, config: dict, seed: int) -> RunResult:
        import ray, asyncio
        t0 = time.time()

        actor = ray.get_actor(self.actor_name, namespace=self.namespace)
        job_dict = {**config, "seed": seed}
        ref = actor.run_job.remote(job_dict)

        loop = asyncio.get_event_loop()
        raw: dict = await loop.run_in_executor(None, ray.get, ref)

        elapsed = time.time() - t0
        episodes = _extract_episodes(raw)
        metrics  = {k: v for k, v in raw.items() if k != "episodes"}

        return RunResult(
            metrics=metrics,
            episodes=episodes,
            elapsed_s=round(elapsed, 3),
            seed=seed,
            raw_output=str(raw),
        )

def _extract_episodes(raw: dict) -> list[EpisodeResult]:
    """Convert actor-returned episode list (if any) to EpisodeResult list."""
    eps = raw.get("episodes", [])
    if not eps:
        # Build synthetic episodes from aggregate metrics
        n = raw.get("num_episodes") or raw.get("total_episodes", 0)
        sr = raw.get("success_rate", 0.0)
        return [
            EpisodeResult(
                index=i, success=(i < round(n * sr)),
                reward_total=0.0, steps=0,
                termination_reason="success" if i < round(n * sr) else "timeout",
            )
            for i in range(n)
        ]
    return [
        EpisodeResult(
            index=ep.get("episode_index", i),
            success=ep.get("success", False),
            reward_total=ep.get("reward_total", 0.0),
            steps=ep.get("steps", 0),
            termination_reason=ep.get("termination_reason", ""),
            metadata=ep.get("metadata", {}),
        )
        for i, ep in enumerate(eps)
    ]
