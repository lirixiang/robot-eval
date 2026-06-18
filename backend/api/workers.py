from __future__ import annotations
import structlog
from fastapi import APIRouter, HTTPException
from backend.db import db

router = APIRouter(tags=["workers"])
logger = structlog.get_logger(__name__)

@router.get("/api/workers")
async def get_workers():
    """Return worker list — reads GPU nodes directly from Ray, no DB."""
    import ray
    try:
        nodes = ray.nodes()
        alive_gpu = [n for n in nodes if n.get("Alive") and n.get("Resources", {}).get("GPU", 0) >= 1]
    except Exception:
        alive_gpu = []

    results = []
    for idx, node in enumerate(alive_gpu):
        actor_name = f"arena-worker-{idx}"
        try:
            actor  = ray.get_actor(actor_name, namespace="robot-eval")
            status = ray.get(actor.status.remote(), timeout=3)
            online = True
        except Exception:
            status = {}
            online = False
        results.append({
            "id":              idx,
            "host":            node.get("NodeManagerAddress", "127.0.0.1"),
            "http_port":       8042 + idx,
            "livestream_port": 49200 + idx,
            "actor":           actor_name,
            "online":          online,
            "busy":            status.get("busy", False),
            "status":          status.get("status", ""),
        })
    return results

@router.get("/api/ray/status")
async def ray_status():
    """Return Ray cluster resource summary for the WorkersView dashboard."""
    import ray
    try:
        if not ray.is_initialized():
            return {"online": False, "nodes": 0, "cpu_total": 0, "cpu_used": 0,
                    "gpu_total": 0, "gpu_used": 0, "mem_total_gb": 0}
        nodes = ray.nodes()
        alive = [n for n in nodes if n.get("Alive")]
        total = ray.cluster_resources()
        avail = ray.available_resources()
        cpu_total = int(total.get("CPU", 0))
        cpu_avail = int(avail.get("CPU", 0))
        gpu_total = int(total.get("GPU", 0))
        gpu_avail = int(avail.get("GPU", 0))
        mem_bytes = total.get("memory", 0)
        return {
            "online":       len(alive) > 0,
            "nodes":        len(alive),
            "cpu_total":    cpu_total,
            "cpu_used":     max(0, cpu_total - cpu_avail),
            "gpu_total":    gpu_total,
            "gpu_used":     max(0, gpu_total - gpu_avail),
            "mem_total_gb": round(mem_bytes / (1024**3), 1) if mem_bytes else 0,
        }
    except Exception as exc:
        logger.warning("ray.status_error", error=str(exc))
        return {"online": False, "nodes": 0, "cpu_total": 0, "cpu_used": 0,
                "gpu_total": 0, "gpu_used": 0, "mem_total_gb": 0}

@router.get("/api/workers/{worker_id}/stream")
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
