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


db = Database()

async def init_db(url: str) -> None:
    await db.init(url)
