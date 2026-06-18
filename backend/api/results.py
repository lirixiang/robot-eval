"""GET /api/results — returns completed jobs with their latest run metrics,
shaped as JobResult for the frontend ResultsView."""
from __future__ import annotations
from fastapi import APIRouter
from backend.db import db

router = APIRouter(prefix="/api/results", tags=["results"])


@router.get("")
async def list_results():
    """Return completed jobs as a list of JobResult objects (with run_id)."""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                j.id          AS job_id,
                r.id          AS run_id,
                j.submitter   AS actor,
                j.config      AS job,
                r.metrics     AS metrics,
                r.elapsed_s   AS elapsed_s,
                r.finished_at AS timestamp
            FROM jobs j
            JOIN runs r ON r.id = (
                SELECT id FROM runs
                WHERE job_id = j.id AND status = 'done'
                ORDER BY attempt DESC
                LIMIT 1
            )
            WHERE j.status = 'done'
            ORDER BY r.finished_at DESC
            """
        )
    import json

    results = []
    for row in rows:
        job_config = row["job"]
        if isinstance(job_config, str):
            job_config = json.loads(job_config)
        metrics = row["metrics"]
        if isinstance(metrics, str):
            metrics = json.loads(metrics)

        results.append({
            "job_id":    row["job_id"],
            "run_id":    row["run_id"],
            "actor":     row["actor"] or "",
            "job":       job_config or {},
            "metrics":   metrics or {},
            "elapsed_s": row["elapsed_s"] or 0.0,
            "timestamp": row["timestamp"] or 0.0,
        })
    return results
