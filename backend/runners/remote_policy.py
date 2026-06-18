from __future__ import annotations
import time
import structlog
import httpx
from backend.runners.base import BaseRunner, RunResult, EpisodeResult

logger = structlog.get_logger(__name__)

class RemotePolicyRunner(BaseRunner):
    """Runs eval by sending observations to an external HTTP policy server."""

    def __init__(self, config: dict):
        self.endpoint = config["endpoint"].rstrip("/")
        self.timeout  = config.get("timeout_s", 30)

    def health_check(self) -> bool:
        try:
            r = httpx.get(f"{self.endpoint}/info", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    async def run(self, config: dict, seed: int) -> RunResult:
        # RemotePolicyRunner drives the env from inside the actor;
        # here we just forward the full job_dict to an actor that supports
        # policy_server_url, or raise NotImplementedError for headless use.
        raise NotImplementedError(
            "RemotePolicyRunner must be used via IsaacLabRunner with "
            "policy_server_url set in config"
        )
