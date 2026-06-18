from __future__ import annotations
import structlog
import asyncpg

logger = structlog.get_logger(__name__)

async def compare(pool: asyncpg.Pool, run_ids: list[str]) -> dict:
    """Multi-run metric comparison with episode-level matrix."""
    from backend.db.queries import runs as rq, episodes as eq

    if not run_ids:
        return {"runs": [], "metrics": {}, "episodes": []}

    # Fetch runs
    runs = []
    for rid in run_ids:
        run = await rq.get_run(pool, rid)
        if run:
            runs.append(run)

    if not runs:
        return {"runs": [], "metrics": {}, "episodes": []}

    # Build metric comparison
    all_metric_keys: set[str] = set()
    for r in runs:
        all_metric_keys.update(
            k for k, v in (r.get("metrics") or {}).items()
            if isinstance(v, (int, float))
        )

    metrics_out: dict[str, dict] = {}
    for key in sorted(all_metric_keys):
        row: dict[str, float | str] = {}
        best_id, best_val = None, None
        for r in runs:
            val = (r.get("metrics") or {}).get(key)
            if val is not None:
                row[r["id"]] = float(val)
                if best_val is None or float(val) > best_val:
                    best_val = float(val)
                    best_id = r["id"]
        if best_id:
            row["best"] = best_id
        metrics_out[key] = row

    # Build episode matrix (align by index)
    eps_by_run: dict[str, list[dict]] = {}
    for r in runs:
        eps_by_run[r["id"]] = await eq.get_episodes(pool, r["id"])

    max_eps = max((len(v) for v in eps_by_run.values()), default=0)
    episode_matrix = []
    for i in range(max_eps):
        row: dict = {"index": i}
        for r in runs:
            eps = eps_by_run.get(r["id"], [])
            if i < len(eps):
                row[r["id"]] = bool(eps[i].get("success", False))
        episode_matrix.append(row)

    return {
        "runs": [
            {
                "id":          r["id"],
                "job_id":      r["job_id"],
                "metrics":     r.get("metrics") or {},
                "finished_at": r.get("finished_at"),
                "elapsed_s":   r.get("elapsed_s"),
            }
            for r in runs
        ],
        "metrics":  metrics_out,
        "episodes": episode_matrix,
    }


async def trend(
    pool: asyncpg.Pool,
    model_name: str,
    env_name: str,
    days: int = 30,
) -> list[dict]:
    """Return time-series of success_rate for a model+env combination."""
    import time
    from backend.db.queries import jobs as jq, runs as rq

    cutoff = time.time() - days * 86400

    # Find all jobs for this model targeting this env
    all_jobs = await jq.list_jobs(pool, model_name=model_name)
    env_jobs = [
        j for j in all_jobs
        if (j.get("config") or {}).get("arena_env_args", {}).get("environment") == env_name
    ]

    points = []
    for job in env_jobs:
        runs = await rq.list_runs_for_job(pool, job["id"])
        for run in runs:
            if run.get("status") != "done":
                continue
            finished = run.get("finished_at") or 0
            if finished < cutoff:
                continue
            m = run.get("metrics") or {}
            if "success_rate" not in m:
                continue
            points.append({
                "run_id":       run["id"],
                "job_id":       job["id"],
                "finished_at":  finished,
                "success_rate": float(m["success_rate"]),
                "uph":          float(m.get("uph") or 0),
                "model_name":   model_name,
                "env_name":     env_name,
            })

    points.sort(key=lambda x: x["finished_at"])
    return points
