from __future__ import annotations
import json, time
import asyncpg

async def create_job(
    pool: asyncpg.Pool, *, id: str, name: str,
    template_id: int | None = None, model_name: str | None = None,
    submitter: str | None = None, policy_config: dict | None = None,
    policy_server_url: str = "", max_retries: int = 3,
    timeout_s: int = 3600, description: str | None = None,
) -> dict:
    now = time.time()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO jobs
               (id,name,template_id,model_name,submitter,policy_config,
                policy_server_url,max_retries,timeout_s,description,
                status,created_at,updated_at)
               VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'pending',$11,$11)
               RETURNING *""",
            id, name, template_id, model_name, submitter,
            json.dumps(policy_config or {}), policy_server_url,
            max_retries, timeout_s, description, now,
        )
    return _row(row)

async def get_job(pool: asyncpg.Pool, job_id: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM jobs WHERE id=$1", job_id)
    return _row(row) if row else None

async def list_jobs(
    pool: asyncpg.Pool, *,
    status: str | None = None,
    model_name: str | None = None,
    submitter: str | None = None,
) -> list[dict]:
    clauses, params = [], []
    for col, val in [("status", status), ("model_name", model_name),
                     ("submitter", submitter)]:
        if val is not None:
            params.append(val)
            clauses.append(f"{col}=${len(params)}")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM jobs {where} ORDER BY created_at DESC", *params
        )
    return [_row(r) for r in rows]

async def update_job_status(pool: asyncpg.Pool, job_id: str, status: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE jobs SET status=$1, updated_at=$2 WHERE id=$3",
            status, time.time(), job_id,
        )

async def increment_retry(pool: asyncpg.Pool, job_id: str) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE jobs SET retry_count=retry_count+1, updated_at=$1 "
            "WHERE id=$2 RETURNING retry_count",
            time.time(), job_id,
        )
    return row["retry_count"]

async def set_baseline_run(pool: asyncpg.Pool, job_id: str, run_id: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE jobs SET baseline_run_id=$1, updated_at=$2 WHERE id=$3",
            run_id, time.time(), job_id,
        )

async def append_log(pool: asyncpg.Pool, job_id: str, line: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO logs(job_id,line,ts) VALUES($1,$2,$3)",
            job_id, line, time.time(),
        )

async def get_logs(pool: asyncpg.Pool, job_id: str) -> list[str]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT line FROM logs WHERE job_id=$1 ORDER BY id", job_id
        )
    return [r["line"] for r in rows]

def _row(row) -> dict:
    d = dict(row)
    if isinstance(d.get("policy_config"), str):
        d["policy_config"] = json.loads(d["policy_config"])
    return d
