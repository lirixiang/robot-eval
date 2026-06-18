import os, pytest, pytest_asyncio, asyncpg
import sys; sys.path.insert(0, ".")
from backend.db.schema import create_tables

TEST_DB = os.environ.get("TEST_DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test")

@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    p = await asyncpg.create_pool(TEST_DB)
    await create_tables(p)
    yield p
    await p.close()

@pytest.mark.asyncio(loop_scope="module")
async def test_tables_exist(pool):
    tables = await pool.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    )
    names = {r["tablename"] for r in tables}
    for t in ("templates","jobs","runs","episodes","matches","match_runs",
              "elo_ratings","elo_history","hosts","remote_workers"):
        assert t in names, f"Missing table: {t}"
