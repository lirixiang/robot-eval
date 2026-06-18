# tests/api/test_analysis_api.py
from __future__ import annotations
import asyncio, os, pytest, asyncpg, uuid, time
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from backend.db.schema import create_tables
from backend.db.queries import jobs as jq, runs as rq

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

    # Prime db singleton — ASGITransport does not trigger ASGI lifespan
    from backend.db import init_db, db
    await init_db(TEST_DB)

    with patch("backend.main._create_actors", new=AsyncMock()), \
         patch("ray.init"):
        from backend.main import app
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            yield c
    await db.close()

async def _seed_run(pool, sr: float = 0.8) -> str:
    jid = uuid.uuid4().hex[:8]
    rid = uuid.uuid4().hex[:8]
    await jq.create_job(pool, id=jid, name="analysis_api_test",
                         model_name="pi0",
                         config={"arena_env_args": {"environment": "lift_object"},
                                 "num_episodes": 5})
    await rq.create_run(pool, id=rid, job_id=jid, attempt=0, seed=42)
    await rq.update_run(pool, rid, status="done",
                         metrics={"success_rate": sr, "uph": 100.0},
                         finished_at=time.time())
    return rid

@pytest.mark.asyncio(loop_scope="module")
async def test_compare_endpoint(client):
    p = await asyncpg.create_pool(TEST_DB)
    rid1 = await _seed_run(p, 0.8)
    rid2 = await _seed_run(p, 0.6)
    await p.close()
    r = await client.get(f"/api/analysis/compare?runs={rid1},{rid2}")
    assert r.status_code == 200
    data = r.json()
    assert "metrics" in data
    assert "runs" in data

@pytest.mark.asyncio(loop_scope="module")
async def test_compare_empty_runs(client):
    r = await client.get("/api/analysis/compare?runs=")
    assert r.status_code == 422

@pytest.mark.asyncio(loop_scope="module")
async def test_trend_endpoint(client):
    r = await client.get("/api/analysis/trend?model=pi0&env=lift_object&days=30")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
