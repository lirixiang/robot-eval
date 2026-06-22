from __future__ import annotations
import asyncio, time
import structlog
import asyncpg

from backend.db.queries import nodes as nq

logger = structlog.get_logger(__name__)

HEARTBEAT_TIMEOUT_S = 45
HEALTH_CHECK_INTERVAL_S = 15


class NodeManager:
    """Manages cluster nodes: registration, heartbeat, health checks."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool
        self._running = False
        self._nodes_cache: dict[str, dict] = {}

    async def start(self) -> None:
        self._running = True
        await self.refresh_from_ray()
        asyncio.create_task(self._health_check_loop())
        logger.info("node_manager.started")

    async def refresh_from_ray(self) -> None:
        """Sync nodes from Ray cluster into DB."""
        try:
            import ray
            if not ray.is_initialized():
                return
            nodes = ray.nodes()
            alive_gpu = [
                n for n in nodes
                if n.get("Alive") and n.get("Resources", {}).get("GPU", 0) >= 1
            ]
            for idx, node in enumerate(alive_gpu):
                node_id = node.get("NodeID", f"node-{idx}")[:16]
                host = node.get("NodeManagerAddress", "127.0.0.1")
                gpu_count = int(node.get("Resources", {}).get("GPU", 1))
                info = await nq.upsert_node(
                    self._pool, id=node_id, host=host,
                    gpu_count=gpu_count, status="healthy",
                )
                self._nodes_cache[node_id] = info
            logger.info("node_manager.refreshed", count=len(alive_gpu))
        except Exception as exc:
            logger.warning("node_manager.refresh_failed", error=str(exc))

    async def heartbeat(self, node_id: str, gpu_status: list[dict]) -> None:
        """Called by worker actors to report GPU state."""
        await nq.update_heartbeat(self._pool, node_id, gpu_status)
        if node_id in self._nodes_cache:
            self._nodes_cache[node_id]["gpu_status"] = gpu_status
            self._nodes_cache[node_id]["last_heartbeat"] = time.time()
            self._nodes_cache[node_id]["status"] = "healthy"

    async def drain_node(self, node_id: str) -> None:
        await nq.update_status(self._pool, node_id, "draining")
        if node_id in self._nodes_cache:
            self._nodes_cache[node_id]["status"] = "draining"
        logger.info("node_manager.drain", node_id=node_id)

    async def undrain_node(self, node_id: str) -> None:
        await nq.update_status(self._pool, node_id, "healthy")
        if node_id in self._nodes_cache:
            self._nodes_cache[node_id]["status"] = "healthy"
        logger.info("node_manager.undrain", node_id=node_id)

    def get_healthy_nodes(self) -> list[dict]:
        return [
            n for n in self._nodes_cache.values()
            if n.get("status") == "healthy"
        ]

    async def get_all_nodes(self) -> list[dict]:
        return await nq.list_nodes(self._pool)

    async def _health_check_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(HEALTH_CHECK_INTERVAL_S)
                now = time.time()
                for node_id, node in list(self._nodes_cache.items()):
                    hb = node.get("last_heartbeat", 0)
                    if node["status"] == "draining":
                        continue
                    if now - hb > HEARTBEAT_TIMEOUT_S:
                        node["status"] = "unhealthy"
                        await nq.update_status(self._pool, node_id, "unhealthy")
                        logger.warning("node_manager.unhealthy", node_id=node_id,
                                       last_hb=round(now - hb, 1))
        except asyncio.CancelledError:
            return


node_manager: NodeManager | None = None
