from __future__ import annotations
import asyncio, json
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from backend.db import db
from backend.db.queries import jobs as jq, runs as rq

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

class SubmitRequest(BaseModel):
    name:             str         = "eval_job"
    model_name:       str         = ""
    submitter:        str         = ""
    description:      str         = ""
    template_id:      int | None  = None
    arena_env_args:   dict[str, Any] = {}
    num_envs:         int         = 1
    num_episodes:     int | None  = 10
    num_steps:        int | None  = None
    policy_type:      str         = "zero_action"
    policy_config:    dict        = {}
    policy_server_url: str        = ""
    max_retries:      int         = 3
    timeout_s:        int         = 3600

@router.post("")
async def submit_job(req: SubmitRequest):
    from backend.engines.job_engine import job_engine
    config = req.model_dump()
    job = await job_engine.create_job(
        name=req.name, model_name=req.model_name or None,
        submitter=req.submitter or None, policy_config=req.policy_config,
        policy_server_url=req.policy_server_url,
        template_id=req.template_id, max_retries=req.max_retries,
        timeout_s=req.timeout_s, description=req.description or None,
    )
    # Stash full config as first log entry for reproduce fidelity
    await jq.append_log(db.pool, job["id"], json.dumps(config))
    return job

@router.get("")
async def list_jobs(status: str | None = None,
                    model_name: str | None = None,
                    submitter: str | None = None):
    return await jq.list_jobs(db.pool, status=status,
                               model_name=model_name, submitter=submitter)

@router.get("/{job_id}")
async def get_job(job_id: str):
    job = await jq.get_job(db.pool, job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    run = await rq.latest_run_for_job(db.pool, job_id)
    return {**job, "latest_run": run}

@router.delete("/{job_id}")
async def cancel_job(job_id: str):
    from backend.engines.job_engine import job_engine
    await job_engine.cancel_job(job_id)
    return {"ok": True}

@router.post("/{job_id}/reproduce")
async def reproduce_job(job_id: str):
    from backend.engines.job_engine import job_engine
    clone = await job_engine.reproduce_job(job_id)
    return clone

@router.get("/{job_id}/regression")
async def get_regression(job_id: str):
    from backend.engines.job_engine import job_engine
    return await job_engine.get_regression(job_id)

@router.get("/{job_id}/logs")
async def stream_logs(job_id: str):
    job = await jq.get_job(db.pool, job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    async def generator():
        sent = 0
        while True:
            lines = await jq.get_logs(db.pool, job_id)
            for line in lines[sent:]:
                yield f"data: {json.dumps(line)}\n\n"
                sent += 1
            current_job = await jq.get_job(db.pool, job_id)
            if current_job and current_job["status"] in ("done", "failed_final", "cancelled"):
                yield "data: __END__\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
