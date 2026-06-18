from __future__ import annotations
import json, time
import asyncpg

async def create_run(
    pool: asyncpg.Pool, *, id: str, job_id: str,
    attempt: int = 0, seed: int | None = None,
) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO runs(id,job_id,attempt,seed,status)
               VALUES($1,$2,$3,$4,'pending') RETURNING *""",
            id, job_id, attempt, seed,
        )
    return _row(row)

async def get_run(pool: asyncpg.Pool, run_id: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM runs WHERE id=$1", run_id)
    return _row(row) if row else None

async def list_runs_for_job(pool: asyncpg.Pool, job_id: str) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM runs WHERE job_id=$1 ORDER BY attempt", job_id
        )
    return [_row(r) for r in rows]

async def latest_run_for_job(pool: asyncpg.Pool, job_id: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM runs WHERE job_id=$1 ORDER BY attempt DESC LIMIT 1",
            job_id,
        )
    return _row(row) if row else None

async def update_run(
    pool: asyncpg.Pool, run_id: str, *,
    status: str | None = None, metrics: dict | None = None,
    elapsed_s: float | None = None, error_msg: str | None = None,
    worker_id: int | None = None, started_at: float | None = None,
    finished_at: float | None = None,
) -> None:
    """Update fields on a run row.

    If every optional argument is None this is a no-op (no SQL is executed).
    run_id is appended last so that SET placeholders start at $1.
    """
    sets, params = [], []
    for col, val in [("status", status), ("elapsed_s", elapsed_s),
                     ("error_msg", error_msg), ("worker_id", worker_id),
                     ("started_at", started_at), ("finished_at", finished_at)]:
        if val is not None:
            params.append(val)
            sets.append(f"{col}=${len(params)}")
    if metrics is not None:
        params.append(json.dumps(metrics))
        sets.append(f"metrics=${len(params)}")
    if not sets:
        return
    params.append(run_id)   # run_id goes LAST so SET clauses bind correctly
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE runs SET {','.join(sets)} WHERE id=${len(params)}", *params
        )

def _row(row) -> dict:
    d = dict(row)
    if isinstance(d.get("metrics"), str):
        d["metrics"] = json.loads(d["metrics"])
    return d
