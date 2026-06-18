import os, pytest, pytest_asyncio, asyncpg, uuid
import sys; sys.path.insert(0, ".")
from backend.db.schema import create_tables
from backend.db.queries import jobs as jq, runs as rq

TEST_DB = os.environ.get("TEST_DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test")

@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    p = await asyncpg.create_pool(TEST_DB)
    await create_tables(p)
    yield p
    await p.close()

@pytest.mark.asyncio(loop_scope="module")
async def test_create_and_get_job(pool):
    jid = uuid.uuid4().hex[:8]
    job = await jq.create_job(pool, id=jid, name="test_job")
    assert job["id"] == jid
    assert job["status"] == "pending"
    assert job["retry_count"] == 0
    fetched = await jq.get_job(pool, jid)
    assert fetched["id"] == jid

@pytest.mark.asyncio(loop_scope="module")
async def test_update_job_status(pool):
    jid = uuid.uuid4().hex[:8]
    await jq.create_job(pool, id=jid, name="status_test")
    await jq.update_job_status(pool, jid, "running")
    job = await jq.get_job(pool, jid)
    assert job["status"] == "running"

@pytest.mark.asyncio(loop_scope="module")
async def test_increment_retry(pool):
    jid = uuid.uuid4().hex[:8]
    await jq.create_job(pool, id=jid, name="retry_test")
    count = await jq.increment_retry(pool, jid)
    assert count == 1
    count = await jq.increment_retry(pool, jid)
    assert count == 2

@pytest.mark.asyncio(loop_scope="module")
async def test_create_run_and_update(pool):
    jid = uuid.uuid4().hex[:8]
    rid = uuid.uuid4().hex[:8]
    await jq.create_job(pool, id=jid, name="run_test")
    run = await rq.create_run(pool, id=rid, job_id=jid, attempt=0, seed=42)
    assert run["id"] == rid
    assert run["status"] == "pending"
    await rq.update_run(pool, rid, status="done", metrics={"success_rate": 0.8},
                        elapsed_s=12.5)
    updated = await rq.get_run(pool, rid)
    assert updated["status"] == "done"
    assert updated["metrics"]["success_rate"] == 0.8
    assert updated["elapsed_s"] == 12.5
