import pytest
from backend.db.schema import create_tables


@pytest.mark.asyncio(loop_scope="module")
async def test_tables_exist(pool):
    tables = await pool.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    )
    names = {r["tablename"] for r in tables}
    for t in ("templates", "jobs", "runs", "episodes", "matches", "match_runs",
              "elo_ratings", "elo_history", "hosts", "remote_workers", "logs"):
        assert t in names, f"Missing table: {t}"
