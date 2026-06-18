# tests/api/test_arena_api.py
from __future__ import annotations
import asyncio, os, pytest, asyncpg
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from backend.db.schema import create_tables
from backend.db import init_db

TEST_DB = os.environ.get("TEST_DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test")

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop(); yield loop; loop.close()

@pytest.fixture(scope="module")
async def client():
    os.environ["DATABASE_URL"] = TEST_DB
    p = await asyncpg.create_pool(TEST_DB)
    await create_tables(p)
    await p.close()

    # Initialize db singleton (lifespan doesn't fire in ASGI transport tests)
    from backend.db import init_db, db
    await init_db(TEST_DB)

    # Wire arena_engine singleton (lifespan doesn't fire in ASGI transport)
    from backend.engines.job_engine import JobEngine
    from backend.engines.arena_engine import ArenaEngine
    import backend.engines.arena_engine as ae_mod
    import backend.engines.job_engine as je_mod
    mock_scheduler = MagicMock()
    je_mod.job_engine = JobEngine(db.pool, mock_scheduler)
    ae_mod.arena_engine = ArenaEngine(db.pool, je_mod.job_engine)

    with patch("backend.main._create_actors", new=AsyncMock()), \
         patch("ray.init"):
        from backend.main import app
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            yield c
    await db.close()

@pytest.mark.asyncio(loop_scope="module")
async def test_list_matches_empty(client):
    r = await client.get("/api/arena/matches")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

@pytest.mark.asyncio(loop_scope="module")
async def test_get_nonexistent_match(client):
    r = await client.get("/api/arena/matches/nosuchid")
    assert r.status_code == 404

@pytest.mark.asyncio(loop_scope="module")
async def test_leaderboard_no_env(client):
    r = await client.get("/api/arena/leaderboard")
    # Missing required 'env' query param → 422
    assert r.status_code == 422

@pytest.mark.asyncio(loop_scope="module")
async def test_leaderboard_empty_env(client):
    r = await client.get("/api/arena/leaderboard?env=nonexistent_env")
    assert r.status_code == 200
    assert r.json() == []

@pytest.mark.asyncio(loop_scope="module")
async def test_list_envs(client):
    r = await client.get("/api/arena/envs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

@pytest.mark.asyncio(loop_scope="module")
async def test_win_matrix_empty(client):
    r = await client.get("/api/arena/matrix?env=lift_object")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
