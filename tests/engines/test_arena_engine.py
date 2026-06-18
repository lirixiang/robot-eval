from __future__ import annotations
import asyncio, os, pytest, asyncpg, uuid
from unittest.mock import AsyncMock, MagicMock
from backend.db.schema import create_tables
from backend.engines.arena_engine import _judge, ArenaEngine

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

def test_judge_a_wins():
    assert _judge({"success_rate": 0.8}, {"success_rate": 0.5}, {
        "metric": "success_rate", "min_diff": 0.02
    }) == "a"

def test_judge_b_wins():
    assert _judge({"success_rate": 0.3}, {"success_rate": 0.7}, {
        "metric": "success_rate", "min_diff": 0.02
    }) == "b"

def test_judge_draw():
    assert _judge({"success_rate": 0.80}, {"success_rate": 0.81}, {
        "metric": "success_rate", "min_diff": 0.02
    }) == "draw"

def test_judge_missing_metric_draws():
    assert _judge({}, {}, {
        "metric": "success_rate", "min_diff": 0.02
    }) == "draw"

@pytest.mark.asyncio(loop_scope="module")
async def test_create_match_persisted(pool):
    mock_engine = MagicMock()
    mock_engine.create_job = AsyncMock(return_value={"id": uuid.uuid4().hex[:8], "status": "pending"})
    engine = ArenaEngine(pool, mock_engine)
    match = await engine.create_match(
        env_name="lift_object",
        model_a="pi0", model_b="zero_action",
        mode="direct", is_blind=False,
    )
    assert match["model_a"] == "pi0"
    assert match["model_b"] == "zero_action"
    assert match["status"] == "running"

@pytest.mark.asyncio(loop_scope="module")
async def test_leaderboard_returns_list(pool):
    mock_engine = MagicMock()
    engine = ArenaEngine(pool, mock_engine)
    lb = await engine.get_leaderboard("lift_object")
    assert isinstance(lb, list)
