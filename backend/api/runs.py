from __future__ import annotations
from fastapi import APIRouter, HTTPException
from backend.db import db
from backend.db.queries import runs as rq, jobs as jq, episodes as eq

router = APIRouter(prefix="/api/runs", tags=["runs"])

@router.get("/{run_id}")
async def get_run(run_id: str):
    run = await rq.get_run(db.pool, run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    episodes = await eq.get_episodes(db.pool, run_id)
    return {**run, "episodes": episodes}

@router.put("/{run_id}/set-baseline")
async def set_baseline(run_id: str):
    run = await rq.get_run(db.pool, run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    await jq.set_baseline_run(db.pool, run["job_id"], run_id)
    return {"ok": True, "run_id": run_id, "job_id": run["job_id"]}
