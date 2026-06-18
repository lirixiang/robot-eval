import os
import pytest_asyncio
import asyncpg
from backend.db.schema import create_tables

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test",
)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    p = await asyncpg.create_pool(TEST_DB)
    await create_tables(p)
    yield p
    await p.close()
