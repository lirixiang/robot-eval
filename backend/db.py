"""PostgreSQL-backed store using asyncpg."""
import json
import time
import asyncpg
from typing import Optional


class Database:
    def __init__(self):
        self._pool: asyncpg.Pool | None = None

    async def init(self, url: str) -> None:
        self._pool = await asyncpg.create_pool(url, min_size=2, max_size=10)
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    config TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at DOUBLE PRECISION,
                    updated_at DOUBLE PRECISION
                );
                CREATE TABLE IF NOT EXISTS logs (
                    id SERIAL PRIMARY KEY,
                    job_id TEXT,
                    line TEXT,
                    ts DOUBLE PRECISION
                );
                CREATE TABLE IF NOT EXISTS hosts (
                    id SERIAL PRIMARY KEY,
                    label TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER DEFAULT 22,
                    username TEXT NOT NULL,
                    password_enc TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS remote_workers (
                    id SERIAL PRIMARY KEY,
                    host_id INTEGER REFERENCES hosts(id) ON DELETE CASCADE,
                    worker_id INTEGER NOT NULL,
                    gpu_index INTEGER NOT NULL,
                    http_port INTEGER NOT NULL,
                    livestream_port INTEGER NOT NULL,
                    container_name TEXT NOT NULL,
                    status TEXT DEFAULT 'deploying',
                    deployed_at TIMESTAMPTZ DEFAULT now(),
                    stopped_at TIMESTAMPTZ
                );
            """)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    # ── Jobs ──────────────────────────────────────────────────────────────────

    async def create_job(self, job_id: str, config: dict) -> dict:
        now = time.time()
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO jobs VALUES ($1,$2,$3,$4,$5)",
                job_id, json.dumps(config), "pending", now, now,
            )
        return await self.get_job(job_id)

    async def get_job(self, job_id: str) -> Optional[dict]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM jobs WHERE id=$1", job_id)
        if not row:
            return None
        d = dict(row)
        d["config"] = json.loads(d["config"])
        return d

    async def list_jobs(self) -> list:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM jobs ORDER BY created_at DESC")
        result = []
        for row in rows:
            d = dict(row)
            d["config"] = json.loads(d["config"])
            result.append(d)
        return result

    async def update_status(self, job_id: str, status: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE jobs SET status=$1, updated_at=$2 WHERE id=$3",
                status, time.time(), job_id,
            )

    async def append_log(self, job_id: str, line: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO logs (job_id, line, ts) VALUES ($1,$2,$3)",
                job_id, line, time.time(),
            )

    async def get_logs(self, job_id: str) -> list[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT line FROM logs WHERE job_id=$1 ORDER BY id", job_id
            )
        return [r["line"] for r in rows]

    # ── Hosts ─────────────────────────────────────────────────────────────────

    async def insert_host(self, label: str, host: str, port: int,
                          username: str, password_enc: str) -> dict:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO hosts (label, host, port, username, password_enc)
                   VALUES ($1,$2,$3,$4,$5) RETURNING *""",
                label, host, port, username, password_enc,
            )
        return dict(row)

    async def list_hosts(self) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM hosts ORDER BY id")
        return [dict(r) for r in rows]

    async def get_host(self, host_id: int) -> Optional[dict]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM hosts WHERE id=$1", host_id)
        return dict(row) if row else None

    async def delete_host(self, host_id: int) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM hosts WHERE id=$1", host_id)

    # ── Remote workers ────────────────────────────────────────────────────────

    async def insert_remote_worker(self, host_id: int, worker_id: int,
                                   gpu_index: int, http_port: int,
                                   livestream_port: int,
                                   container_name: str) -> dict:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO remote_workers
                   (host_id, worker_id, gpu_index, http_port, livestream_port, container_name)
                   VALUES ($1,$2,$3,$4,$5,$6) RETURNING *""",
                host_id, worker_id, gpu_index, http_port, livestream_port, container_name,
            )
        return dict(row)

    async def update_worker_status(self, worker_id: int, status: str) -> None:
        async with self._pool.acquire() as conn:
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
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM remote_workers {where} ORDER BY worker_id", *params
            )
        return [dict(r) for r in rows]

    async def get_remote_worker(self, worker_id: int) -> Optional[dict]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM remote_workers WHERE worker_id=$1", worker_id
            )
        return dict(row) if row else None

    async def next_worker_id(self) -> int:
        """Return MAX(worker_id)+1 across all non-stopped workers, minimum 0."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT MAX(worker_id) AS m FROM remote_workers WHERE status != 'stopped'"
            )
        return (row["m"] or -1) + 1


db = Database()
