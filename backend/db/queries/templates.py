from __future__ import annotations
import asyncpg

async def create_template(
    pool: asyncpg.Pool, *, name: str, version: str = "1.0",
    runner_type: str, config_yaml: str, description: str | None = None,
) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO templates(name,version,runner_type,config_yaml,description)
               VALUES($1,$2,$3,$4,$5) RETURNING *""",
            name, version, runner_type, config_yaml, description,
        )
    return dict(row)

async def get_template(pool: asyncpg.Pool, template_id: int) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM templates WHERE id=$1", template_id
        )
    return dict(row) if row else None

async def list_templates(pool: asyncpg.Pool) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM templates ORDER BY name, version"
        )
    return [dict(r) for r in rows]

async def delete_template(pool: asyncpg.Pool, template_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM templates WHERE id=$1", template_id)
