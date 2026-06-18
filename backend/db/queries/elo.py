from __future__ import annotations
import asyncpg
from backend.elo.calculator import GlickoPlayer

async def get_or_create(
    pool: asyncpg.Pool, model_name: str, env_name: str
) -> GlickoPlayer:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM elo_ratings WHERE model_name=$1 AND env_name=$2",
            model_name, env_name,
        )
    if row:
        return GlickoPlayer(
            rating=float(row["rating"]),
            rd=float(row["rd"]),
            volatility=float(row["volatility"]),
        )
    return GlickoPlayer()  # default 1500/350/0.06

async def save(
    pool: asyncpg.Pool,
    model_name: str, env_name: str,
    player: GlickoPlayer,
    match_id: str,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO elo_ratings(model_name, env_name, rating, rd, volatility, updated_at)
               VALUES($1,$2,$3,$4,$5,now())
               ON CONFLICT(model_name,env_name)
               DO UPDATE SET rating=$3, rd=$4, volatility=$5, updated_at=now()""",
            model_name, env_name, player.rating, player.rd, player.volatility,
        )
        await conn.execute(
            """INSERT INTO elo_history(model_name, env_name, rating, rd, match_id)
               VALUES($1,$2,$3,$4,$5)""",
            model_name, env_name, player.rating, player.rd, match_id,
        )

async def list_leaderboard(pool: asyncpg.Pool, env_name: str) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT model_name, env_name, rating, rd, volatility, updated_at
               FROM elo_ratings WHERE env_name=$1
               ORDER BY rating DESC""",
            env_name,
        )
    return [
        {
            "model_name":  r["model_name"],
            "env_name":    r["env_name"],
            "rating":      round(float(r["rating"]), 1),
            "rd":          round(float(r["rd"]), 1),
            "ci_low":      round(float(r["rating"]) - 2 * float(r["rd"]), 1),
            "ci_high":     round(float(r["rating"]) + 2 * float(r["rd"]), 1),
            "updated_at":  str(r["updated_at"]),
        }
        for r in rows
    ]

async def get_history(
    pool: asyncpg.Pool, model_name: str, env_name: str
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT rating, rd, match_id, recorded_at
               FROM elo_history
               WHERE model_name=$1 AND env_name=$2
               ORDER BY recorded_at ASC""",
            model_name, env_name,
        )
    return [
        {
            "rating":      round(float(r["rating"]), 1),
            "rd":          round(float(r["rd"]), 1),
            "match_id":    r["match_id"],
            "recorded_at": str(r["recorded_at"]),
        }
        for r in rows
    ]

async def list_envs(pool: asyncpg.Pool) -> list[str]:
    """List all envs that have at least one Elo rating."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT env_name FROM elo_ratings ORDER BY env_name"
        )
    return [r["env_name"] for r in rows]
