from __future__ import annotations
import structlog
from fastapi import APIRouter, HTTPException, Query
from backend.db import db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["analysis"])

@router.get("/compare")
async def compare_runs(runs: str = Query(..., description="Comma-separated run IDs")):
    from backend.engines.analysis_engine import compare
    run_ids = [r.strip() for r in runs.split(",") if r.strip()]
    if not run_ids:
        raise HTTPException(422, "runs parameter must contain at least one run ID")
    if len(run_ids) > 20:
        raise HTTPException(422, "Cannot compare more than 20 runs at once")
    return await compare(db.pool, run_ids)

@router.get("/trend")
async def get_trend(
    model: str = Query(..., description="Model name"),
    env:   str = Query(..., description="Environment name"),
    days:  int = Query(30, ge=1, le=365, description="Look-back window in days"),
):
    from backend.engines.analysis_engine import trend
    return await trend(db.pool, model_name=model, env_name=env, days=days)
