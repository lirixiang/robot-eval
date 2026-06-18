from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.db import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/arena", tags=["arena"])

class CreateMatchRequest(BaseModel):
    env_name:            str
    model_a:             str
    model_b:             str
    template_id:         int | None = None
    mode:                str        = "direct"   # direct|swiss|round_robin
    is_blind:            bool       = False
    judge_config:        dict       = {}
    seed:                int | None = None
    arena_env_args:      dict       = {}
    num_episodes:        int        = 10
    policy_server_url_a: str        = ""
    policy_server_url_b: str        = ""

def _mask_blind(match: dict) -> dict:
    """Hide model_b if match is blind and not yet done."""
    if match.get("is_blind") and match.get("status") != "done":
        return {**match, "model_b": "?"}
    return match

def _require_pool():
    if db.pool is None:
        raise HTTPException(503, "Database not ready")
    return db.pool

def _get_engine():
    from backend.engines.arena_engine import arena_engine
    if arena_engine is None:
        raise HTTPException(503, "Arena engine not ready")
    return arena_engine

@router.post("/matches")
async def create_match(req: CreateMatchRequest):
    engine = _get_engine()
    match = await engine.create_match(
        env_name=req.env_name, model_a=req.model_a, model_b=req.model_b,
        template_id=req.template_id, mode=req.mode, is_blind=req.is_blind,
        judge_config=req.judge_config or None, seed=req.seed,
        arena_env_args=req.arena_env_args or None,
        num_episodes=req.num_episodes,
        policy_server_url_a=req.policy_server_url_a,
        policy_server_url_b=req.policy_server_url_b,
    )
    return _mask_blind(match)

@router.get("/matches")
async def list_matches(
    status:   str | None = None,
    env_name: str | None = None,
):
    from backend.db.queries import matches as mq
    matches = await mq.list_matches(_require_pool(), status=status, env_name=env_name)
    return [_mask_blind(m) for m in matches]

@router.get("/matches/{match_id}")
async def get_match(match_id: str):
    from backend.db.queries import matches as mq
    match = await mq.get_match(_require_pool(), match_id)
    if not match:
        raise HTTPException(404, f"Match {match_id} not found")
    return _mask_blind(match)

@router.get("/leaderboard")
async def get_leaderboard(env: str = Query(..., description="Environment name")):
    engine = _get_engine()
    return await engine.get_leaderboard(env)

@router.get("/envs")
async def list_envs():
    from backend.db.queries import elo as elq
    return await elq.list_envs(_require_pool())

@router.get("/models/{model_name}")
async def get_model_profile(model_name: str, env: str = Query(...)):
    engine = _get_engine()
    return await engine.get_model_profile(model_name, env)

@router.get("/matrix")
async def get_win_matrix(env: str = Query(..., description="Environment name")):
    engine = _get_engine()
    return await engine.get_win_matrix(env)
