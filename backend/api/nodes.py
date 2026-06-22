from __future__ import annotations
import structlog
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/nodes", tags=["nodes"])
logger = structlog.get_logger(__name__)


def _get_node_manager():
    from backend.engines.node_manager import node_manager
    if node_manager is None:
        raise HTTPException(503, "NodeManager not ready")
    return node_manager


@router.get("")
async def list_nodes():
    """Return all registered cluster nodes with GPU status."""
    nm = _get_node_manager()
    return await nm.get_all_nodes()


@router.post("/{node_id}/drain")
async def drain_node(node_id: str):
    """Mark a node as draining — scheduler won't assign new jobs to it."""
    nm = _get_node_manager()
    await nm.drain_node(node_id)
    return {"status": "draining", "node_id": node_id}


@router.post("/{node_id}/undrain")
async def undrain_node(node_id: str):
    """Restore a drained node back to healthy status."""
    nm = _get_node_manager()
    await nm.undrain_node(node_id)
    return {"status": "healthy", "node_id": node_id}


@router.post("/refresh")
async def refresh_nodes():
    """Force re-scan of Ray cluster nodes."""
    nm = _get_node_manager()
    await nm.refresh_from_ray()
    return await nm.get_all_nodes()
