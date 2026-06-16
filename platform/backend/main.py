"""
Robot Eval Platform — FastAPI backend
Serves REST API + React static build + Isaac Sim MJPEG proxy on port 8000
"""
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db import JobDB

ROOT        = Path(__file__).parent.parent   # /app  (parent of backend/)
RESULTS_DIR = ROOT / "results"
SCRIPTS_DIR = ROOT / "scripts"
ISAAC_BASE  = "http://127.0.0.1:8765"       # Isaac Sim frame_server

# Static: /app/frontend/dist (built React)
STATIC = Path(__file__).parent.parent / "frontend" / "dist"

app = FastAPI(title="Robot Eval Platform")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
db = JobDB()

# ── Models ────────────────────────────────────────────────────────────────────

class SubmitRequest(BaseModel):
    task: str = "LiftObj"
    layout: str = "robocasakitchen-9-8"
    robot: str = "LeRobot-RL"
    test_num: int = 10
    time_limit: float = 60.0

# ── Isaac Sim proxy ───────────────────────────────────────────────────────────

@app.get("/sim/health")
async def sim_health():
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"{ISAAC_BASE}/health")
            return r.json()
    except Exception:
        return {"status": "offline"}

@app.get("/sim/stream")
async def sim_stream(request: Request):
    async def generate():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=None)) as client:
                async with client.stream("GET", f"{ISAAC_BASE}/stream") as resp:
                    async for chunk in resp.aiter_bytes(chunk_size=4096):
                        if await request.is_disconnected():
                            break
                        yield chunk
        except Exception:
            # Isaac Sim offline — yield nothing, frontend will retry via /sim/health poll
            return
    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ── Configs ───────────────────────────────────────────────────────────────────

TASKS   = ["LiftObj"]
LAYOUTS = ["robocasakitchen-9-8"]
ROBOTS  = ["LeRobot-RL", "LeRobot-AbsJointGripper-RL"]

@app.get("/api/configs")
def get_configs():
    return {"tasks": TASKS, "layouts": LAYOUTS, "robots": ROBOTS}

# ── Jobs ──────────────────────────────────────────────────────────────────────

@app.get("/api/jobs")
def list_jobs():
    return db.list_jobs()

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404)
    result_file = RESULTS_DIR / f"{job_id}.json"
    if result_file.exists():
        job["result"] = json.loads(result_file.read_text())
    return job

@app.post("/api/jobs")
async def submit_job(req: SubmitRequest):
    job_id = str(uuid.uuid4())[:8]
    job = db.create_job(job_id, req.model_dump())
    asyncio.create_task(_run_job(job_id, req))
    return job

@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: str):
    db.update_status(job_id, "cancelled")
    return {"ok": True}

# ── SSE log stream ────────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/logs")
async def stream_logs(job_id: str):
    async def generator() -> AsyncIterator[str]:
        sent = 0
        while True:
            lines = db.get_logs(job_id)
            for line in lines[sent:]:
                yield f"data: {json.dumps(line)}\n\n"
                sent += 1
            job = db.get_job(job_id)
            if job and job["status"] in ("done", "failed", "cancelled"):
                yield "data: __END__\n\n"
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── Results ───────────────────────────────────────────────────────────────────

@app.get("/api/results")
def list_results():
    results = []
    for f in sorted(RESULTS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            results.append(json.loads(f.read_text()))
        except Exception:
            pass
    return results

# ── Runner ────────────────────────────────────────────────────────────────────

async def _run_job(job_id: str, req: SubmitRequest):
    db.update_status(job_id, "running")
    output_file = RESULTS_DIR / f"{job_id}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python", str(SCRIPTS_DIR / "eval_runner.py"),
        "--job_id",    job_id,
        "--task",      req.task,
        "--layout",    req.layout,
        "--robot",     req.robot,
        "--test_num",  str(req.test_num),
        "--time_limit", str(req.time_limit),
        "--output",    str(output_file),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async for raw in proc.stdout:
            line = raw.decode().rstrip()
            db.append_log(job_id, line)

        await proc.wait()
        status = "done" if proc.returncode == 0 else "failed"
    except Exception as e:
        db.append_log(job_id, f"ERROR: {e}")
        status = "failed"

    db.update_status(job_id, status)

# ── Startup hook: ensure loop is available ────────────────────────────────────

@app.on_event("startup")
async def startup():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Serve React static build ─────────────────────────────────────────────────

if STATIC.exists():
    app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="static")
