from __future__ import annotations
import json, time, uuid
import asyncpg

async def create_match(
    pool: asyncpg.Pool, *, id: str, env_name: str,
    template_id: int | None = None, seed: int | None = None,
    mode: str = "direct", model_a: str, model_b: str,
    is_blind: bool = False, judge_config: dict | None = None,
) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO matches
               (id,env_name,template_id,seed,mode,model_a,model_b,
                is_blind,judge_config,status)
               VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'pending')
               RETURNING *""",
            id, env_name, template_id, seed, mode, model_a, model_b,
            is_blind, json.dumps(judge_config or {}),
        )
    return _row(row)

async def get_match(pool: asyncpg.Pool, match_id: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM matches WHERE id=$1", match_id)
    return _row(row) if row else None

async def list_matches(
    pool: asyncpg.Pool, *,
    status: str | None = None,
    env_name: str | None = None,
) -> list[dict]:
    clauses, params = [], []
    for col, val in [("status", status), ("env_name", env_name)]:
        if val is not None:
            params.append(val); clauses.append(f"{col}=${len(params)}")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM matches {where} ORDER BY created_at DESC", *params
        )
    return [_row(r) for r in rows]

async def update_match(
    pool: asyncpg.Pool, match_id: str, *,
    status: str | None = None,
    winner: str | None = None,
    finished_at: float | None = None,
) -> None:
    sets, params = [], [match_id]
    for col, val in [("status", status), ("winner", winner)]:
        if val is not None:
            params.append(val); sets.append(f"{col}=${len(params)}")
    if finished_at is not None:
        params.append(finished_at)
        sets.append(f"finished_at=to_timestamp(${len(params)})")
    if not sets:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE matches SET {','.join(sets)} WHERE id=$1", *params
        )

async def set_match_run(
    pool: asyncpg.Pool, match_id: str, model: str, run_id: str
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO match_runs(match_id,model,run_id)
               VALUES($1,$2,$3) ON CONFLICT(match_id,model) DO UPDATE SET run_id=$3""",
            match_id, model, run_id,
        )

async def get_match_runs(pool: asyncpg.Pool, match_id: str) -> dict[str, str]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT model, run_id FROM match_runs WHERE match_id=$1", match_id
        )
    return {r["model"]: r["run_id"] for r in rows}

async def win_matrix(pool: asyncpg.Pool, env_name: str) -> list[dict]:
    """Return aggregated win/loss/draw counts for all model pairs in env."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT model_a, model_b,
                      SUM(CASE WHEN winner='a' THEN 1 ELSE 0 END) AS wins_a,
                      SUM(CASE WHEN winner='b' THEN 1 ELSE 0 END) AS wins_b,
                      SUM(CASE WHEN winner='draw' THEN 1 ELSE 0 END) AS draws
               FROM matches
               WHERE env_name=$1 AND status='done'
               GROUP BY model_a, model_b""",
            env_name,
        )
    return [dict(r) for r in rows]

def _row(row) -> dict:
    d = dict(row)
    if isinstance(d.get("judge_config"), str):
        d["judge_config"] = json.loads(d["judge_config"])
    return d
