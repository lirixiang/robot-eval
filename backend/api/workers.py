from __future__ import annotations
import asyncio
import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["workers"])
logger = structlog.get_logger(__name__)


def _get_queue_depth() -> int:
    try:
        from backend.engines.job_engine import job_engine
        if job_engine and job_engine._scheduler:
            return job_engine._scheduler.queue_depth()
    except Exception:
        pass
    return 0

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
            "queue_depth":  _get_queue_depth(),
        }
    except Exception as exc:
        logger.warning("ray.status_error", error=str(exc))
        return {"online": False, "nodes": 0, "cpu_total": 0, "cpu_used": 0,
                "gpu_total": 0, "gpu_used": 0, "mem_total_gb": 0, "queue_depth": 0}

@router.get("/api/workers/{worker_id}/stream")
async def worker_stream_info(worker_id: int):
    """Return WebRTC stream info for a worker — derived from Ray node list."""
    import ray
    try:
        nodes = ray.nodes()
        alive_gpu = [n for n in nodes if n.get("Alive") and n.get("Resources", {}).get("GPU", 0) >= 1]
    except Exception:
        alive_gpu = []
    if worker_id >= len(alive_gpu):
        raise HTTPException(404, f"Worker {worker_id} not found")
    node = alive_gpu[worker_id]
    host = node.get("NodeManagerAddress", "127.0.0.1")
    return {
        "worker_id":       worker_id,
        "http_port":       8042 + worker_id,
        "livestream_port": 49200 + worker_id,
        "host":            host,
        "signaling_url":   f"ws://{host}:{49200 + worker_id}",
    }


@router.get("/api/workers/{worker_id}/mjpeg")
async def worker_mjpeg_stream(worker_id: int):
    """MJPEG stream from Isaac Sim viewport via Ray actor frame capture."""
    import ray

    actor_name = f"arena-worker-{worker_id}"
    try:
        actor = ray.get_actor(actor_name, namespace="robot-eval")
    except Exception:
        raise HTTPException(404, f"Worker {worker_id} actor not found")

    async def generate():
        while True:
            try:
                frame = await asyncio.wrap_future(actor.capture_frame.remote().future())
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
            except Exception:
                break
            await asyncio.sleep(0.066)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

