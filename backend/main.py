"""Robot Eval Platform v2 — FastAPI entry point."""
from __future__ import annotations
import asyncio, os
from contextlib import asynccontextmanager
from pathlib import Path

import ray
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.db import db, init_db
from backend.base_actor import load_actor_class
from backend.engines.arena_engine import ArenaEngine
from backend.logging_config import configure_logging

logger = structlog.get_logger(__name__)

# Configure logging at import time so all modules get JSON formatting.
# Skip in test environments to avoid clobbering structlog's default PrintLogger.
if not os.environ.get("PYTEST_CURRENT_TEST"):
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))

_DATABASE_URL    = os.environ.get("DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval")
_RAY_ADDRESS     = os.environ.get("RAY_ADDRESS", "ray://127.0.0.1:10001")
_ACTOR_MODULE    = os.environ.get("EVAL_ACTOR_MODULE", "arena_actor")
_ACTOR_CLASS     = os.environ.get("EVAL_ACTOR_CLASS",  "IsaacLabArenaActor")
_STATIC          = Path(__file__).parent.parent / "frontend" / "dist"

_ISAAC_SIM = "/workspaces/isaaclab_arena/submodules/IsaacLab/_isaac_sim"
_ISAAC_LD  = ":".join([
    _ISAAC_SIM, f"{_ISAAC_SIM}/kit", f"{_ISAAC_SIM}/kit/kernel/plugins",
    f"{_ISAAC_SIM}/kit/libs/iray", f"{_ISAAC_SIM}/kit/plugins",
    f"{_ISAAC_SIM}/kit/plugins/bindings-python",
    f"{_ISAAC_SIM}/kit/plugins/carb_gfx", f"{_ISAAC_SIM}/kit/plugins/rtx",
    f"{_ISAAC_SIM}/kit/plugins/gpu.foundation",
])

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(_DATABASE_URL)

    # Init Ray
    try:
        ray.init(address=_RAY_ADDRESS, ignore_reinit_error=True,
                 log_to_driver=False,
                 runtime_env={"working_dir": "/app/backend"})
        logger.info("ray.connected", address=_RAY_ADDRESS)
    except Exception as exc:
        logger.warning("ray.unavailable", error=str(exc))

    # Start scheduler
    from backend.engines.scheduler import JobScheduler
    from backend.engines.job_engine import JobEngine

    workers = await _get_workers_meta()
    scheduler = JobScheduler(db.pool, workers)
    await scheduler.start()

    # Wire singletons so routers can import them
    import backend.engines.job_engine as je_mod
    je_mod.job_engine = JobEngine(db.pool, scheduler)

    import backend.engines.arena_engine as ae_mod
    ae_mod.arena_engine = ArenaEngine(db.pool, je_mod.job_engine)

    # Create Ray actors for running workers
    asyncio.create_task(_create_actors())

    yield
    await db.close()


async def _get_workers_meta() -> list[dict]:
    try:
        rows = await db.list_remote_workers(status="running")
        return [
            {
                "worker_id":       r["worker_id"],
                "actor_name":      f"arena-worker-{r['worker_id']}",
                "http_port":       r["http_port"],
                "livestream_port": r["livestream_port"],
            }
            for r in rows
        ]
    except Exception:
        # Fallback for first-run before any workers are registered
        return [{"worker_id": 0, "actor_name": "arena-worker-0",
                 "http_port": 8042, "livestream_port": 49200}]


async def _create_actors():
    ActorClass = load_actor_class(_ACTOR_MODULE, _ACTOR_CLASS)
    runtime_env = {"env_vars": {
        "LD_LIBRARY_PATH": _ISAAC_LD,
        "CARB_APP_PATH":   f"{_ISAAC_SIM}/kit",
        "ISAAC_PATH":      _ISAAC_SIM,
        "EXP_PATH":        f"{_ISAAC_SIM}/apps",
        "RESOURCE_NAME":   "IsaacSim",
        "LD_PRELOAD":      f"{_ISAAC_SIM}/kit/libcarb.so",
    }}
    try:
        workers = await _get_workers_meta()
    except Exception:
        workers = [{"worker_id": 0, "actor_name": "arena-worker-0",
                    "http_port": 8042, "livestream_port": 49200}]

    for w in workers:
        name = w["actor_name"]
        try:
            ray.get_actor(name, namespace="robot-eval")
            logger.info("actor.exists", name=name)
        except Exception:
            logger.info("actor.creating", name=name)
            ActorClass.options(
                name=name, namespace="robot-eval",
                lifetime="detached", num_gpus=1,
                runtime_env=runtime_env,
            ).remote(w["worker_id"], w.get("http_port", 8042), w.get("livestream_port", 49200))


app = FastAPI(title="Robot Eval Platform v2", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

from backend.api.jobs      import router as jobs_router
from backend.api.runs      import router as runs_router
from backend.api.workers   import router as workers_router
from backend.api.templates import router as templates_router
from backend.api.analysis  import router as analysis_router
from backend.api.results   import router as results_router
from backend.api.arena     import router as arena_router
from backend.api.configs   import router as configs_router

app.include_router(jobs_router)
app.include_router(runs_router)
app.include_router(workers_router)
app.include_router(templates_router)
app.include_router(analysis_router)
app.include_router(results_router)
app.include_router(arena_router)
app.include_router(configs_router)

@app.get("/api/health")
async def health():
    try:
        await db.pool.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    ray_ok = False
    try:
        import ray
        if ray.is_initialized():
            ray_ok = True
    except Exception:
        pass

    status = "ok" if (db_ok and ray_ok) else "degraded"
    return {"status": status, "db": db_ok, "ray": ray_ok}

if _STATIC.exists():
    from fastapi.responses import FileResponse
    # Serve static assets under /assets directly
    app.mount("/assets", StaticFiles(directory=str(_STATIC / "assets")), name="assets")

    # Catch-all: return index.html for all non-API paths (SPA client-side routing)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        return FileResponse(str(_STATIC / "index.html"))
