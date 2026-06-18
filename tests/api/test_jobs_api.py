# tests/api/test_jobs_api.py
import asyncio, os, pytest, asyncpg, uuid
import sys; sys.path.insert(0, ".")
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

TEST_DB = os.environ.get("TEST_DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test")

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop(); yield loop; loop.close()

@pytest.fixture(scope="module")
async def app_client():
    os.environ["DATABASE_URL"] = TEST_DB
    os.environ["RAY_ADDRESS"]  = "ray://127.0.0.1:10001"

    from backend.db.schema import create_tables
    import asyncpg
    pool = await asyncpg.create_pool(TEST_DB)
    await create_tables(pool)
    await pool.close()

    # Initialize the db singleton directly — ASGITransport does not trigger
    # the ASGI lifespan event, so we prime it manually here.
    from backend.db import init_db, db
    await init_db(TEST_DB)

    mock_engine = MagicMock()
    mock_engine.create_job = AsyncMock(return_value={
        "id": "abc12345", "name": "test", "status": "pending",
        "model_name": "pi0", "submitter": "alice",
        "policy_config": {}, "retry_count": 0,
        "created_at": 0.0, "updated_at": 0.0,
    })
    mock_engine.cancel_job = AsyncMock()
    mock_engine.reproduce_job = AsyncMock(return_value={
        "id": "def67890", "name": "test_repro", "status": "pending",
        "model_name": "pi0", "submitter": "alice",
        "policy_config": {}, "retry_count": 0,
        "created_at": 0.0, "updated_at": 0.0,
    })

    with patch("backend.engines.job_engine.job_engine", mock_engine), \
         patch("backend.main._create_actors", new=AsyncMock()), \
         patch("backend.api.jobs.jq.append_log", new=AsyncMock()), \
         patch("ray.init"):
        from backend.main import app
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as client:
            yield client
    await db.close()

@pytest.mark.asyncio(loop_scope="module")
async def test_submit_job(app_client):
    resp = await app_client.post("/api/jobs", json={
        "name": "test_job",
        "arena_env_args": {"environment": "lift_object"},
        "model_name": "pi0",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"

@pytest.mark.asyncio(loop_scope="module")
async def test_list_jobs(app_client):
    resp = await app_client.get("/api/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

@pytest.mark.asyncio(loop_scope="module")
async def test_health(app_client):
    resp = await app_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["db"] is True
