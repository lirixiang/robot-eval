"""
Robot Eval Platform — FastAPI backend（Ray + pluggable EvalActor）

Eval backend is configurable via environment variables:
  EVAL_ACTOR_MODULE   Python module containing the actor class (default: arena_actor)
  EVAL_ACTOR_CLASS    Class name inside that module          (default: IsaacLabArenaActor)
  EVAL_PYTHONPATH     Extra paths added to PYTHONPATH in worker runtime_env
"""
import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import ray
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.db import db
from backend.base_actor import load_actor_class
import backend.host_manager as hm

ROOT        = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "results"
STATIC      = Path(__file__).parent.parent / "frontend" / "dist"

_ACTOR_MODULE    = os.environ.get("EVAL_ACTOR_MODULE", "arena_actor")
_ACTOR_CLASS     = os.environ.get("EVAL_ACTOR_CLASS",  "IsaacLabArenaActor")
_EVAL_PYTHONPATH = os.environ.get(
    "EVAL_PYTHONPATH",
    "/workspaces/isaaclab_arena:/workspaces/isaaclab_arena/isaaclab_arena_environments",
)
_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    await db.init(_DATABASE_URL)
    ray_addr = os.environ.get("RAY_ADDRESS", "ray://127.0.0.1:10001")
    try:
        ray.init(address=ray_addr, ignore_reinit_error=True, log_to_driver=False)
        asyncio.create_task(_create_actors())
    except Exception as e:
        print(f"[platform] Ray not ready ({e}), will retry on job submit", flush=True)
    yield
    await db.close()


app = FastAPI(title="Robot Eval Platform", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Models ────────────────────────────────────────────────────────────────────

class SubmitRequest(BaseModel):
    """
    arena_env_args: isaaclab_arena 环境参数，与 eval_jobs_config.json 格式相同
    例：{"environment": "lift_object", "embodiment": "franka", "num_envs": 1}

    policy_server_url: 外部 Policy Server 地址（实现 RoboEval Policy Server API）。
    留空则使用内置 policy_type。
    """
    name:               str        = "eval_job"
    arena_env_args:     dict[str, Any]
    num_envs:           int        = 1
    num_episodes:       int | None = 10
    num_steps:          int | None = None
    policy_type:        str        = "zero_action"
    policy_config:      dict       = {}
    # Remote policy fields (for external model providers)
    policy_server_url:  str        = ""   # e.g. "http://192.168.1.100:7860"
    model_name:         str        = ""   # e.g. "pi0.5"
    submitter:          str        = ""   # team / person name
    description:        str        = ""

class AddHostRequest(BaseModel):
    label:    str
    host:     str
    port:     int = 22
    username: str
    password: str

# ── Ray 初始化 ─────────────────────────────────────────────────────────────────

async def _create_actors():
    """Create Ray EvalActors for all running remote_workers rows."""
    ActorClass = load_actor_class(_ACTOR_MODULE, _ACTOR_CLASS)

    _ISAAC_SIM = "/workspaces/isaaclab_arena/submodules/IsaacLab/_isaac_sim"
    isaac_ldpath = ":".join([
        _ISAAC_SIM, f"{_ISAAC_SIM}/kit", f"{_ISAAC_SIM}/kit/kernel/plugins",
        f"{_ISAAC_SIM}/kit/libs/iray", f"{_ISAAC_SIM}/kit/plugins",
        f"{_ISAAC_SIM}/kit/plugins/bindings-python",
        f"{_ISAAC_SIM}/kit/plugins/carb_gfx", f"{_ISAAC_SIM}/kit/plugins/rtx",
        f"{_ISAAC_SIM}/kit/plugins/gpu.foundation",
    ])
    worker_runtime_env = {
        "env_vars": {
            "LD_LIBRARY_PATH": isaac_ldpath,
            "CARB_APP_PATH":   f"{_ISAAC_SIM}/kit",
            "ISAAC_PATH":      _ISAAC_SIM,
            "EXP_PATH":        f"{_ISAAC_SIM}/apps",
            "RESOURCE_NAME":   "IsaacSim",
            "LD_PRELOAD":      f"{_ISAAC_SIM}/kit/libcarb.so",
        }
    }

    workers = await db.list_remote_workers(status="running")
    for w in workers:
        actor_name = f"arena-worker-{w['worker_id']}"
        try:
            ray.get_actor(actor_name, namespace="robot-eval")
        except Exception:
            ActorClass.options(
                name=actor_name,
                namespace="robot-eval",
                lifetime="detached",
                num_gpus=1,
                runtime_env=worker_runtime_env,
            ).remote(w["worker_id"], w["http_port"], w["livestream_port"])

# ── Workers API ───────────────────────────────────────────────────────────────

@app.get("/api/workers")
async def get_workers():
    workers = await db.list_remote_workers(status="running")
    results = []
    for w in workers:
        actor_name = f"arena-worker-{w['worker_id']}"
        host_row = await db.get_host(w["host_id"])
        try:
            actor  = ray.get_actor(actor_name, namespace="robot-eval")
            status = ray.get(actor.status.remote(), timeout=3)
            online = True
        except Exception:
            status = {}
            online = False
        results.append({
            "id":              w["worker_id"],
            "host":            host_row["host"] if host_row else "unknown",
            "http_port":       w["http_port"],
            "livestream_port": w["livestream_port"],
            "actor":           actor_name,
            "online":          online,
            "busy":            status.get("busy", False),
            "status":          status.get("status", ""),
            "worker_id":       w["worker_id"],
            "host_id":         w["host_id"],
        })
    return results

# ── Host management ───────────────────────────────────────────────────────────

@app.get("/api/hosts")
async def list_hosts():
    return await hm.list_hosts()

@app.post("/api/hosts", status_code=201)
async def add_host(req: AddHostRequest):
    return await hm.add_host(req.label, req.host, req.port, req.username, req.password)

@app.delete("/api/hosts/{host_id}", status_code=204)
async def delete_host(host_id: int):
    await hm.delete_host(host_id)

@app.post("/api/hosts/{host_id}/probe")
async def probe_host(host_id: int):
    return await hm.probe_host(host_id)

@app.post("/api/hosts/{host_id}/deploy", status_code=202)
async def deploy_worker(host_id: int):
    try:
        return await hm.deploy_worker(host_id)
    except RuntimeError as e:
        msg = str(e)
        if "No free GPU" in msg:
            raise HTTPException(409, detail=msg)
        raise HTTPException(500, detail=msg)

@app.delete("/api/hosts/{host_id}/workers/{worker_id}", status_code=204)
async def destroy_worker(host_id: int, worker_id: int):
    await hm.destroy_worker(host_id, worker_id)

# ── Isaac Sim 原生流媒体支持 ──────────────────────────────────────────────────

@app.get("/sim/health")
async def sim_health():
    workers = await db.list_remote_workers(status="running")
    if not workers:
        return {"status": "offline"}
    w = workers[0]
    host_row = await db.get_host(w["host_id"])
    host = host_row["host"] if host_row else "127.0.0.1"
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"http://{host}:{w['http_port']}/v1/streaming/ready")
            return r.json()
    except Exception:
        return {"status": "offline"}

@app.get("/api/workers/{worker_id}/stream")
async def worker_stream_info(worker_id: int):
    """返回该 worker 的 WebRTC 流接入信息，前端直连用。"""
    w = await db.get_remote_worker(worker_id)
    if not w:
        raise HTTPException(404, f"worker {worker_id} not found")
    host_row = await db.get_host(w["host_id"])
    host = host_row["host"] if host_row else "unknown"
    return {
        "worker_id":       worker_id,
        "http_port":       w["http_port"],
        "livestream_port": w["livestream_port"],
        "host":            host,
        "signaling_url":   f"ws://{host}:{w['livestream_port']}",
        "ready_url":       f"http://{host}:{w['http_port']}/v1/streaming/ready",
    }

@app.post("/api/workers/{worker_id}/stream/offer")
async def proxy_stream_offer(worker_id: int, request: Request):
    """将浏览器的 WebRTC SDP offer 转发给 Kit HTTP 服务（绕过浏览器跨域限制）。"""
    w = await db.get_remote_worker(worker_id)
    if not w:
        raise HTTPException(404, f"worker {worker_id} not found")
    host_row = await db.get_host(w["host_id"])
    host = host_row["host"] if host_row else "unknown"
    body = await request.json()
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"http://{host}:{w['http_port']}/v1/streaming/creds",
            json=body,
        )
    return r.json()

# ── Configs（从 isaaclab_arena 读取可用环境列表）─────────────────────────────

@app.get("/api/configs")
def get_configs():
    return {
        "environments": [
            "lift_object",
            "pick_and_place_maple_table",
            "kitchen_pick_and_place",
            "sorting",
            "press_button",
        ],
        "policy_types": ["zero_action", "rsl_rl", "replay_action"],
        "example_job": {
            "name": "lift_object_baseline",
            "arena_env_args": {
                "environment": "lift_object",
                "embodiment":  "franka_joint_pos",
            },
            "num_envs":     1,
            "num_episodes": 10,
            "policy_type":  "zero_action",
            "policy_config": {},
        },
    }

# ── Jobs ──────────────────────────────────────────────────────────────────────

@app.get("/api/jobs")
async def list_jobs():
    return await db.list_jobs()

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404)
    result_file = RESULTS_DIR / f"{job_id}.json"
    if result_file.exists():
        job["result"] = json.loads(result_file.read_text())
    return job

@app.post("/api/jobs")
async def submit_job(req: SubmitRequest):
    job_id = str(uuid.uuid4())[:8]
    job    = await db.create_job(job_id, req.model_dump())
    asyncio.create_task(_run_job(job_id, req))
    return job

@app.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str):
    await db.update_status(job_id, "cancelled")
    return {"ok": True}

# ── SSE log stream ────────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/logs")
async def stream_logs(job_id: str):
    async def generator() -> AsyncIterator[str]:
        sent = 0
        while True:
            lines = await db.get_logs(job_id)
            for line in lines[sent:]:
                yield f"data: {json.dumps(line)}\n\n"
                sent += 1
            job = await db.get_job(job_id)
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

# ── Leaderboard ───────────────────────────────────────────────────────────────

@app.get("/api/leaderboard")
def get_leaderboard(env: str | None = None):
    """
    返回按环境分组的榜单，每个（environment, model_name, submitter）组合取最佳成绩。
    可用 ?env=lift_object 过滤单个环境。
    """
    all_results = []
    for f in sorted(RESULTS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            r = json.loads(f.read_text())
            if r.get("metrics"):
                all_results.append(r)
        except Exception:
            pass

    # 过滤环境
    if env:
        all_results = [r for r in all_results
                       if r.get("job", {}).get("arena_env_args", {}).get("environment") == env]

    # 按 (environment, model_key) 分组取最佳
    best: dict[tuple, dict] = {}
    for r in all_results:
        environment  = r.get("job", {}).get("arena_env_args", {}).get("environment", "unknown")
        model_name   = (r.get("job", {}).get("model_name")
                        or r.get("metrics", {}).get("policy_model")
                        or r.get("job", {}).get("policy_type", "unknown"))
        submitter    = (r.get("job", {}).get("submitter")
                        or r.get("metrics", {}).get("policy_submitter", "–"))
        key = (environment, model_name, submitter)
        sr  = r.get("metrics", {}).get("success_rate", 0)
        if key not in best or sr > best[key]["metrics"].get("success_rate", 0):
            best[key] = {**r, "_model_name": model_name, "_submitter": submitter, "_environment": environment}

    # 构造榜单行，按成功率排序
    rows = []
    for (environment, model_name, submitter), r in best.items():
        m = r.get("metrics", {})
        rows.append({
            "rank":         0,                  # filled after sort
            "environment":  environment,
            "model_name":   model_name,
            "submitter":    submitter,
            "description":  r.get("job", {}).get("description", ""),
            "success_rate": m.get("success_rate", 0),
            "uph":          m.get("uph", 0),
            "avg_cycle_s":  m.get("avg_cycle_s", 0),
            "num_episodes": m.get("total_episodes") or r.get("job", {}).get("num_episodes", 0),
            "job_id":       r.get("job_id", ""),
            "timestamp":    r.get("timestamp", 0),
        })

    # Sort by environment then success_rate desc
    rows.sort(key=lambda x: (x["environment"], -x["success_rate"]))

    # Assign rank per environment
    env_rank: dict[str, int] = {}
    for row in rows:
        e = row["environment"]
        env_rank[e] = env_rank.get(e, 0) + 1
        row["rank"] = env_rank[e]

    # Group by environment
    groups: dict[str, list] = {}
    for row in rows:
        groups.setdefault(row["environment"], []).append(row)

    return {
        "groups":      [{"environment": e, "rows": rs} for e, rs in groups.items()],
        "total_submissions": len(all_results),
        "environments": list(groups.keys()),
    }

# ── Job runner ────────────────────────────────────────────────────────────────

async def _run_job(job_id: str, req: SubmitRequest):
    # 找可用 Actor
    actor_name = None
    for _ in range(60):
        workers = await db.list_remote_workers(status="running")
        for w in workers:
            name = f"arena-worker-{w['worker_id']}"
            try:
                a      = ray.get_actor(name, namespace="robot-eval")
                status = ray.get(a.status.remote(), timeout=3)
                if not status.get("busy", True):
                    actor_name = name
                    break
            except Exception:
                continue
        if actor_name:
            break
        await db.append_log(job_id, "等待空闲 Actor...")
        await asyncio.sleep(5)

    if not actor_name:
        await db.update_status(job_id, "failed")
        await db.append_log(job_id, "ERROR: 超时未找到空闲 Isaac Lab Actor")
        return

    await db.update_status(job_id, "running")
    await db.append_log(job_id, f"分配 {actor_name}")

    job_dict = {
        "name":               f"{req.name}_{job_id}",
        "arena_env_args":     {**req.arena_env_args, "num_envs": req.num_envs},
        "num_envs":           req.num_envs,
        "num_episodes":       req.num_episodes,
        "num_steps":          req.num_steps,
        "policy_type":        req.policy_type,
        "policy_config_dict": req.policy_config,
        "policy_server_url":  req.policy_server_url,
    }

    try:
        # 直接调用 Actor 方法（Ray Client 模式下不能用 ray.remote() 包装普通函数）
        actor      = ray.get_actor(actor_name, namespace="robot-eval")
        result_ref = actor.run_job.remote(job_dict)
        loop       = asyncio.get_event_loop()
        metrics    = await loop.run_in_executor(None, ray.get, result_ref)

        # 写结果文件
        output_file = RESULTS_DIR / f"{job_id}.json"
        result = {
            "job_id":    job_id,
            "actor":     actor_name,
            "job":       job_dict,
            "metrics":   metrics,
            "elapsed_s": 0,
            "timestamp": time.time(),
        }
        output_file.write_text(json.dumps(result, ensure_ascii=False, default=str))

        await db.update_status(job_id, "done")
        await db.append_log(job_id, f"完成 metrics={json.dumps(metrics, ensure_ascii=False)}")
    except Exception as e:
        await db.update_status(job_id, "failed")
        await db.append_log(job_id, f"ERROR: {e}")

# ── Serve React static build ─────────────────────────────────────────────────

if STATIC.exists():
    app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="static")
