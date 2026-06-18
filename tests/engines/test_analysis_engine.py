# tests/engines/test_analysis_engine.py
from __future__ import annotations
import asyncio, os, uuid, pytest, asyncpg
from backend.db.schema import create_tables
from backend.db.queries import jobs as jq, runs as rq, episodes as eq

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

async def _make_run(pool, success_rate: float, n_eps: int = 4,
                    model: str = "pi0", env: str = "lift_object") -> tuple[str, str]:
    jid = uuid.uuid4().hex[:8]
    rid = uuid.uuid4().hex[:8]
    import time
    await jq.create_job(pool, id=jid, name="analysis_test",
                         model_name=model,
                         config={"arena_env_args": {"environment": env},
                                 "num_episodes": n_eps})
    await rq.create_run(pool, id=rid, job_id=jid, attempt=0, seed=0)
    successes = int(n_eps * success_rate)
    await rq.update_run(pool, rid, status="done",
                         metrics={"success_rate": success_rate, "uph": 100.0},
                         finished_at=time.time())
    await eq.insert_episodes(pool, rid, [
        {"episode_index": i, "success": i < successes,
         "reward_total": 1.0 if i < successes else 0.0,
         "steps": 10, "termination_reason": "success" if i < successes else "timeout"}
        for i in range(n_eps)
    ])
    return jid, rid

@pytest.mark.asyncio(loop_scope="module")
async def test_compare_two_runs(pool):
    from backend.engines.analysis_engine import compare
    _, rid1 = await _make_run(pool, success_rate=0.75)
    _, rid2 = await _make_run(pool, success_rate=0.50)
    result = await compare(pool, [rid1, rid2])
    assert "runs" in result
    assert "metrics" in result
    sr = result["metrics"]["success_rate"]
    assert sr[rid1] == 0.75
    assert sr[rid2] == 0.50
    assert sr["best"] == rid1

@pytest.mark.asyncio(loop_scope="module")
async def test_compare_episode_matrix(pool):
    from backend.engines.analysis_engine import compare
    _, rid1 = await _make_run(pool, success_rate=1.0, n_eps=2)
    _, rid2 = await _make_run(pool, success_rate=0.0, n_eps=2)
    result = await compare(pool, [rid1, rid2])
    eps = result["episodes"]
    assert len(eps) == 2
    assert eps[0][rid1] is True
    assert eps[0][rid2] is False

@pytest.mark.asyncio(loop_scope="module")
async def test_trend(pool):
    from backend.engines.analysis_engine import trend
    _, _ = await _make_run(pool, success_rate=0.6, model="trend_model", env="lift_object")
    _, _ = await _make_run(pool, success_rate=0.8, model="trend_model", env="lift_object")
    result = await trend(pool, model_name="trend_model", env_name="lift_object", days=30)
    assert len(result) >= 2
    assert all("success_rate" in r for r in result)
    assert all("run_id" in r for r in result)
