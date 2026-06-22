from __future__ import annotations
import json, time
import asyncpg


async def upsert_node(
    pool: asyncpg.Pool, *, id: str, host: str,
    gpu_count: int = 1, gpu_type: str = "",
    total_memory_mb: int = 0, labels: dict | None = None,
    status: str = "healthy", gpu_status: list | None = None,
) -> dict:
    now = time.time()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO nodes (id,host,gpu_count,gpu_type,total_memory_mb,labels,status,last_heartbeat,gpu_status)
               VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
               ON CONFLICT(id) DO UPDATE SET
                 host=EXCLUDED.host, gpu_count=EXCLUDED.gpu_count,
                 gpu_type=EXCLUDED.gpu_type, total_memory_mb=EXCLUDED.total_memory_mb,
                 labels=EXCLUDED.labels, status=EXCLUDED.status,
                 last_heartbeat=EXCLUDED.last_heartbeat, gpu_status=EXCLUDED.gpu_status
               RETURNING *""",
            id, host, gpu_count, gpu_type, total_memory_mb,
            json.dumps(labels or {}), status, now, json.dumps(gpu_status or []),
        )
    return _row(row)


async def update_heartbeat(
    pool: asyncpg.Pool, node_id: str, gpu_status: list,
) -> None:
    now = time.time()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE nodes SET last_heartbeat=$1, gpu_status=$2, status='healthy'
               WHERE id=$3""",
            now, json.dumps(gpu_status), node_id,
        )


async def update_status(pool: asyncpg.Pool, node_id: str, status: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE nodes SET status=$1 WHERE id=$2", status, node_id,
        )


async def list_nodes(pool: asyncpg.Pool, status: str | None = None) -> list[dict]:
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch(
                "SELECT * FROM nodes WHERE status=$1 ORDER BY id", status)
        else:
            rows = await conn.fetch("SELECT * FROM nodes ORDER BY id")
    return [_row(r) for r in rows]


async def get_node(pool: asyncpg.Pool, node_id: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM nodes WHERE id=$1", node_id)
    return _row(row) if row else None


async def delete_node(pool: asyncpg.Pool, node_id: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM nodes WHERE id=$1", node_id)


def _row(row) -> dict:
    if not row:
        return {}
    d = dict(row)
    for k in ("labels", "gpu_status"):
        if k in d and isinstance(d[k], str):
            d[k] = json.loads(d[k])
    return d
