import asyncio, os, pytest, asyncpg, uuid
import sys; sys.path.insert(0, ".")
from unittest.mock import AsyncMock, MagicMock, patch
from backend.db.schema import create_tables
from backend.db.queries import jobs as jq, runs as rq
from backend.engines.job_engine import JobEngine
from backend.runners.base import RunResult, EpisodeResult

TEST_DB = os.environ.get("TEST_DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test")

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop(); yield loop; loop.close()

@pytest.fixture(scope="module")
async def pool():
    p = await asyncpg.create_pool(TEST_DB)
    await create_tables(p)
    yield p
    await p.close()

@pytest.mark.asyncio(loop_scope="module")
async def test_create_job_persisted(pool):
    engine = JobEngine(pool, scheduler=MagicMock(enqueue=AsyncMock()))
    job = await engine.create_job(name="test", model_name="pi0",
                                   submitter="alice", policy_config={},
                                   policy_server_url="", max_retries=2)
    assert job["status"] == "pending"
    assert job["model_name"] == "pi0"
    persisted = await jq.get_job(pool, job["id"])
    assert persisted is not None

@pytest.mark.asyncio(loop_scope="module")
async def test_cancel_job(pool):
    engine = JobEngine(pool, scheduler=MagicMock(enqueue=AsyncMock()))
    job = await engine.create_job(name="cancel_me", model_name="x",
                                   submitter="", policy_config={},
                                   policy_server_url="")
    await engine.cancel_job(job["id"])
    updated = await jq.get_job(pool, job["id"])
    assert updated["status"] == "cancelled"

@pytest.mark.asyncio(loop_scope="module")
async def test_reproduce_job(pool):
    engine = JobEngine(pool, scheduler=MagicMock(enqueue=AsyncMock()))
    original = await engine.create_job(name="orig", model_name="pi0",
                                        submitter="bob", policy_config={"k": 1},
                                        policy_server_url="")
    clone = await engine.reproduce_job(original["id"])
    assert clone["id"] != original["id"]
    assert clone["model_name"] == original["model_name"]
    assert clone["policy_config"] == original["policy_config"]

@pytest.mark.asyncio(loop_scope="module")
async def test_get_regression_no_baseline(pool):
    engine = JobEngine(pool, scheduler=MagicMock(enqueue=AsyncMock()))
    job = await engine.create_job(name="regress_test", model_name="pi0",
                                   submitter="charlie", policy_config={},
                                   policy_server_url="")
    result = await engine.get_regression(job["id"])
    assert "error" in result

@pytest.mark.asyncio(loop_scope="module")
async def test_get_regression_with_baseline(pool):
    engine = JobEngine(pool, scheduler=MagicMock(enqueue=AsyncMock()))
    job = await engine.create_job(name="regress_with_baseline", model_name="pi0",
                                   submitter="dave", policy_config={},
                                   policy_server_url="")
    jid = job["id"]

    # Create baseline run
    baseline_rid = uuid.uuid4().hex[:8]
    await rq.create_run(pool, id=baseline_rid, job_id=jid, attempt=0, seed=1)
    await rq.update_run(pool, baseline_rid, status="done",
                         metrics={"success_rate": 0.7}, elapsed_s=10.0)
    await jq.set_baseline_run(pool, jid, baseline_rid)

    # Create current run
    current_rid = uuid.uuid4().hex[:8]
    await rq.create_run(pool, id=current_rid, job_id=jid, attempt=1, seed=2)
    await rq.update_run(pool, current_rid, status="done",
                         metrics={"success_rate": 0.8}, elapsed_s=9.0)

    result = await engine.get_regression(jid)
    assert "deltas" in result
    assert result["baseline_run_id"] == baseline_rid
    deltas = {d["metric"]: d for d in result["deltas"]}
    assert "success_rate" in deltas
    assert abs(deltas["success_rate"]["delta"] - 0.1) < 0.001
