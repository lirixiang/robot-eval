import os, pytest, pytest_asyncio, asyncpg, uuid
import sys; sys.path.insert(0, ".")
from backend.db.schema import create_tables
from backend.db.queries import runs as rq, jobs as jq

TEST_DB = os.environ.get("TEST_DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test")

@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    p = await asyncpg.create_pool(TEST_DB)
    await create_tables(p)
    yield p
    await p.close()

@pytest.mark.asyncio(loop_scope="module")
async def test_list_runs_for_job(pool):
    jid = uuid.uuid4().hex[:8]
    await jq.create_job(pool, id=jid, name="list_runs_test")
    rid1 = uuid.uuid4().hex[:8]
    rid2 = uuid.uuid4().hex[:8]
    await rq.create_run(pool, id=rid1, job_id=jid, attempt=0)
    await rq.create_run(pool, id=rid2, job_id=jid, attempt=1)
    runs = await rq.list_runs_for_job(pool, jid)
    assert len(runs) == 2
    assert runs[0]["attempt"] == 0
    assert runs[1]["attempt"] == 1

@pytest.mark.asyncio(loop_scope="module")
async def test_latest_run_for_job(pool):
    jid = uuid.uuid4().hex[:8]
    await jq.create_job(pool, id=jid, name="latest_run_test")
    rid1 = uuid.uuid4().hex[:8]
    rid2 = uuid.uuid4().hex[:8]
    await rq.create_run(pool, id=rid1, job_id=jid, attempt=0)
    await rq.create_run(pool, id=rid2, job_id=jid, attempt=1)
    latest = await rq.latest_run_for_job(pool, jid)
    assert latest["id"] == rid2
    assert latest["attempt"] == 1

@pytest.mark.asyncio(loop_scope="module")
async def test_get_run_none(pool):
    result = await rq.get_run(pool, "nonexistent_id")
    assert result is None
