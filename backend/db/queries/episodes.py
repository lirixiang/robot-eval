from __future__ import annotations
import json
import asyncpg

async def insert_episodes(
    pool: asyncpg.Pool, run_id: str, episodes: list[dict]
) -> None:
    """episodes: list of dicts with keys matching episodes table columns."""
    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO episodes
               (run_id,episode_index,success,reward_total,steps,
                termination_reason,metadata)
               VALUES($1,$2,$3,$4,$5,$6,$7)""",
            [
                (
                    run_id,
                    ep.get("episode_index", i),
                    ep.get("success", False),
                    ep.get("reward_total", 0.0),
                    ep.get("steps", 0),
                    ep.get("termination_reason", ""),
                    json.dumps(ep.get("metadata", {})),
                )
                for i, ep in enumerate(episodes)
            ],
        )

async def get_episodes(pool: asyncpg.Pool, run_id: str) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM episodes WHERE run_id=$1 ORDER BY episode_index",
            run_id,
        )
    return [dict(r) for r in rows]
