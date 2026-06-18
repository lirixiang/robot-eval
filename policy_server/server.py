"""
Policy Server — wraps PolicyBase as a FastAPI HTTP service.

Usage:
    from policy_server import serve
    serve(MyPolicy(), host="0.0.0.0", port=7860)

Endpoints consumed by the eval platform:
    GET  /info
    POST /reset   { episode_id, env_info }
    POST /act     { observations, episode_id, step }
"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any

from .base_policy import PolicyBase


class ResetRequest(BaseModel):
    episode_id: str
    env_info:   dict[str, Any] = {}


class ActRequest(BaseModel):
    observations: dict[str, Any]
    episode_id:   str
    step:         int = 0


def serve(policy: PolicyBase, host: str = "0.0.0.0", port: int = 7860):
    """Start the policy HTTP server. Blocks until interrupted."""
    app = FastAPI(title="RoboEval Policy Server")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/info")
    def info():
        return policy.info

    @app.post("/reset")
    def reset(req: ResetRequest):
        policy.reset(req.episode_id, req.env_info)
        return {"ok": True}

    @app.post("/act")
    def act(req: ActRequest):
        actions = policy.act(req.observations, req.episode_id, req.step)
        return {"actions": actions}

    @app.get("/health")
    def health():
        return {"status": "ok", "model": policy.info.get("model", "unknown")}

    print(f"[policy-server] starting {policy.info.get('model', 'policy')} on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
