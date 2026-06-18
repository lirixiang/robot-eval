from __future__ import annotations
from typing import Optional
import asyncpg
from backend.db.schema import create_tables

class Database:
    pool: asyncpg.Pool | None = None

    async def init(self, url: str) -> None:
        self.pool = await asyncpg.create_pool(url, min_size=2, max_size=10)
        await create_tables(self.pool)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    # ── Hosts ─────────────────────────────────────────────────────────────────

    async def list_hosts(self) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM hosts ORDER BY id")
        return [dict(r) for r in rows]

    async def get_host(self, host_id: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM hosts WHERE id=$1", host_id)
        return dict(row) if row else None

    async def insert_host(self, label: str, host: str, port: int,
                          username: str, password_enc: str) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO hosts (label, host, port, username, password_enc)
                   VALUES ($1,$2,$3,$4,$5) RETURNING *""",
                label, host, port, username, password_enc,
            )
        return dict(row)

    # ── Remote workers ────────────────────────────────────────────────────────

    async def list_remote_workers(self, host_id: Optional[int] = None,
                                  status: Optional[str] = None) -> list[dict]:
        conditions, params = [], []
        if host_id is not None:
            params.append(host_id)
            conditions.append(f"host_id=${len(params)}")
        if status is not None:
            params.append(status)
            conditions.append(f"status=${len(params)}")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM remote_workers {where} ORDER BY worker_id", *params
            )
        return [dict(r) for r in rows]

    async def get_remote_worker(self, worker_id: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM remote_workers WHERE worker_id=$1", worker_id
            )
        return dict(row) if row else None

    async def insert_remote_worker(self, host_id: int, worker_id: int,
                                   gpu_index: int, http_port: int,
                                   livestream_port: int,
                                   container_name: str) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO remote_workers
                   (host_id, worker_id, gpu_index, http_port, livestream_port, container_name)
                   VALUES ($1,$2,$3,$4,$5,$6) RETURNING *""",
                host_id, worker_id, gpu_index, http_port, livestream_port, container_name,
            )
        return dict(row)

    async def update_worker_status(self, worker_id: int, status: str) -> None:
        async with self.pool.acquire() as conn:
            if status == "stopped":
                await conn.execute(
                    "UPDATE remote_workers SET status=$1, stopped_at=now() WHERE worker_id=$2",
                    status, worker_id,
                )
            else:
                await conn.execute(
                    "UPDATE remote_workers SET status=$1 WHERE worker_id=$2",
                    status, worker_id,
                )


db = Database()

async def init_db(url: str) -> None:
    await db.init(url)
