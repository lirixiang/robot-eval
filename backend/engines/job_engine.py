from __future__ import annotations
import uuid
import structlog
import asyncpg
from backend.db.queries import jobs as jq, runs as rq

logger = structlog.get_logger(__name__)

class JobEngine:
    def __init__(self, pool: asyncpg.Pool, scheduler):
        self._pool      = pool
        self._scheduler = scheduler  # JobScheduler instance

    async def create_job(
        self, *, name: str, model_name: str | None = None,
        submitter: str | None = None, policy_config: dict | None = None,
        policy_server_url: str = "", template_id: int | None = None,
        max_retries: int = 3, timeout_s: int = 3600,
        description: str | None = None,
        arena_env_args: dict | None = None,
        num_envs: int = 1,
        num_episodes: int | None = 10,
        num_steps: int | None = None,
        policy_type: str = "zero_action",
    ) -> dict:
        job_id = uuid.uuid4().hex[:8]
        config = {
            "arena_env_args": arena_env_args or {},
            "num_envs":       num_envs,
            "num_episodes":   num_episodes,
            "num_steps":      num_steps,
            "policy_type":    policy_type,
        }
        job = await jq.create_job(
            self._pool, id=job_id, name=name, template_id=template_id,
            model_name=model_name, submitter=submitter,
            policy_config=policy_config or {}, policy_server_url=policy_server_url,
            max_retries=max_retries, timeout_s=timeout_s, description=description,
            config=config,
        )
        await self._scheduler.enqueue(job_id)
        logger.info("job.created", job_id=job_id, model=model_name)
        return job

    async def cancel_job(self, job_id: str) -> None:
        await jq.update_job_status(self._pool, job_id, "cancelled")
        logger.info("job.cancelled", job_id=job_id)

    async def reproduce_job(self, job_id: str) -> dict:
        original = await jq.get_job(self._pool, job_id)
        if not original:
            raise ValueError(f"Job {job_id} not found")
        # Fix 4: Preserve seed from last run so reproduction is deterministic
        last_run = await rq.latest_run_for_job(self._pool, job_id)
        policy_config = dict(original.get("policy_config") or {})
        if last_run and last_run.get("seed") is not None:
            policy_config["_reproduce_seed"] = last_run["seed"]
        clone_id = uuid.uuid4().hex[:8]
        original_config = original.get("config") or {}
        clone = await jq.create_job(
            self._pool, id=clone_id,
            name=f"{original['name']}_repro",
            template_id=original.get("template_id"),
            model_name=original.get("model_name"),
            submitter=original.get("submitter"),
            policy_config=policy_config,
            policy_server_url=original.get("policy_server_url", ""),
            max_retries=original.get("max_retries", 3),
            timeout_s=original.get("timeout_s", 3600),
            description=f"Reproduced from {job_id}",
            config=original_config,   # preserve arena_env_args etc.
        )
        await self._scheduler.enqueue(clone["id"])
        return clone

    async def get_regression(self, job_id: str) -> dict:
        job = await jq.get_job(self._pool, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        baseline_run_id = job.get("baseline_run_id")
        if not baseline_run_id:
            return {"error": "no baseline set for this job"}
        current = await rq.latest_run_for_job(self._pool, job_id)
        baseline = await rq.get_run(self._pool, baseline_run_id)
        if not current or not baseline:
            return {"error": "missing run data"}
        return _compute_regression(baseline, current)

def _compute_regression(baseline: dict, current: dict) -> dict:
    b_metrics = baseline.get("metrics", {})
    c_metrics = current.get("metrics", {})
    deltas = []
    for key in b_metrics:
        if key in c_metrics and isinstance(b_metrics[key], (int, float)):
            bv = float(b_metrics[key])
            cv = float(c_metrics[key])
            delta = cv - bv
            deltas.append({
                "metric":    key,
                "baseline":  bv,
                "current":   cv,
                "delta":     round(delta, 4),
                "delta_pct": round((delta / bv * 100) if bv != 0 else 0, 2),
                "significant": abs(delta) > 0.02,  # simple threshold; Phase 3 adds bootstrap CI
            })
    return {
        "baseline_run_id": baseline["id"],
        "current_run_id":  current["id"],
        "deltas": deltas,
    }

# Module-level singleton — wired up by the lifespan in main.py
job_engine: JobEngine | None = None
