from __future__ import annotations
import structlog
from fastapi import APIRouter, HTTPException
from backend.db import db

router = APIRouter(prefix="/api/workers", tags=["workers"])
logger = structlog.get_logger(__name__)

@router.get("")
async def get_workers():
    import ray
    from backend.db.queries import jobs as jq
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
        })
    return results

@router.get("/{worker_id}/stream")
async def worker_stream_info(worker_id: int):
    w = await db.get_remote_worker(worker_id)
    if not w:
        raise HTTPException(404)
    host_row = await db.get_host(w["host_id"])
    host = host_row["host"] if host_row else "unknown"
    return {
        "worker_id":       worker_id,
        "http_port":       w["http_port"],
        "livestream_port": w["livestream_port"],
        "host":            host,
        "signaling_url":   f"ws://{host}:{w['livestream_port']}",
    }
