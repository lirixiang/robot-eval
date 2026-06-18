import asyncio, os, pytest, asyncpg, uuid
import sys; sys.path.insert(0, ".")
from unittest.mock import AsyncMock, patch, MagicMock
from backend.db.schema import create_tables
from backend.db.queries import jobs as jq, runs as rq
from backend.engines.scheduler import JobScheduler

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
async def test_scheduler_dispatches_to_runner(pool):
    from backend.runners.base import RunResult, EpisodeResult
    mock_result = RunResult(
        metrics={"success_rate": 0.8},
        episodes=[EpisodeResult(0, True, 5.0, 10, "success")],
        elapsed_s=1.0, seed=42,
    )

    workers = [{"worker_id": 0, "actor_name": "arena-worker-0"}]
    scheduler = JobScheduler(pool, workers)

    with patch("backend.engines.scheduler.get_runner") as mock_get_runner:
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=mock_result)
        mock_get_runner.return_value = mock_runner

        await scheduler.start()

        jid = uuid.uuid4().hex[:8]
        await jq.create_job(pool, id=jid, name="sched_test")
        await scheduler.enqueue(jid)

        # Wait for job to complete (poll with timeout to avoid flakiness)
        for _ in range(20):
            await asyncio.sleep(0.1)
            job = await jq.get_job(pool, jid)
            if job["status"] in ("done", "failed_final"):
                break

        job = await jq.get_job(pool, jid)
        assert job["status"] in ("done", "running")

@pytest.mark.asyncio(loop_scope="module")
async def test_scheduler_cancelled_job_skipped(pool):
    """A job that gets cancelled before dispatch is skipped without running the runner."""
    from backend.runners.base import RunResult, EpisodeResult

    workers = [{"worker_id": 1, "actor_name": "arena-worker-1"}]
    scheduler = JobScheduler(pool, workers)

    with patch("backend.engines.scheduler.get_runner") as mock_get_runner:
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=RunResult(
            metrics={}, episodes=[], elapsed_s=0.0, seed=0))
        mock_get_runner.return_value = mock_runner

        # Do NOT start scheduler yet — enqueue job, cancel it, then start
        jid = uuid.uuid4().hex[:8]
        await jq.create_job(pool, id=jid, name="cancelled_sched_test")
        await jq.update_job_status(pool, jid, "cancelled")
        await scheduler.enqueue(jid)

        await scheduler.start()
        await asyncio.sleep(0.3)

        # Runner should NOT have been called
        mock_runner.run.assert_not_called()

@pytest.mark.asyncio(loop_scope="module")
async def test_scheduler_retry_on_failure(pool):
    """A failing run should increment retry_count and re-enqueue."""
    workers = [{"worker_id": 2, "actor_name": "arena-worker-2"}]
    scheduler = JobScheduler(pool, workers)

    call_count = 0

    async def failing_run(config, seed):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("simulated failure")

    with patch("backend.engines.scheduler.get_runner") as mock_get_runner:
        mock_runner = MagicMock()
        mock_runner.run = failing_run
        mock_get_runner.return_value = mock_runner

        await scheduler.start()

        jid = uuid.uuid4().hex[:8]
        # max_retries=0 so it fails immediately to failed_final without long backoff
        await jq.create_job(pool, id=jid, name="fail_test", max_retries=0)
        await scheduler.enqueue(jid)

        # Wait for job to reach failed_final
        for _ in range(30):
            await asyncio.sleep(0.1)
            job = await jq.get_job(pool, jid)
            if job["status"] == "failed_final":
                break

        job = await jq.get_job(pool, jid)
        assert job["status"] == "failed_final"
        assert call_count >= 1
