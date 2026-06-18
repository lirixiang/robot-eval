from __future__ import annotations
import asyncio, os, pytest, asyncpg, uuid
from backend.db.schema import create_tables
from backend.db.queries import matches as mq, elo as elq
from backend.elo.calculator import GlickoPlayer

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
async def test_create_and_get_match(pool):
    mid = uuid.uuid4().hex[:8]
    m = await mq.create_match(pool, id=mid, env_name="lift_object",
                               model_a="pi0", model_b="zero")
    assert m["id"] == mid
    assert m["status"] == "pending"
    fetched = await mq.get_match(pool, mid)
    assert fetched["model_a"] == "pi0"

@pytest.mark.asyncio(loop_scope="module")
async def test_update_match_winner(pool):
    mid = uuid.uuid4().hex[:8]
    await mq.create_match(pool, id=mid, env_name="lift_object",
                           model_a="a", model_b="b")
    await mq.update_match(pool, mid, status="done", winner="a",
                           finished_at=1234567.0)
    m = await mq.get_match(pool, mid)
    assert m["status"] == "done"
    assert m["winner"] == "a"

@pytest.mark.asyncio(loop_scope="module")
async def test_elo_save_and_load(pool):
    p = GlickoPlayer(rating=1600, rd=200, volatility=0.05)
    mid = uuid.uuid4().hex[:8]
    await mq.create_match(pool, id=mid, env_name="test_env",
                           model_a="modelX", model_b="modelY")
    await elq.save(pool, "modelX", "test_env", p, mid)
    loaded = await elq.get_or_create(pool, "modelX", "test_env")
    assert abs(loaded.rating - 1600) < 0.01
    assert abs(loaded.rd - 200) < 0.01

@pytest.mark.asyncio(loop_scope="module")
async def test_list_matches_filter(pool):
    mid = uuid.uuid4().hex[:8]
    await mq.create_match(pool, id=mid, env_name="env_filter_test",
                           model_a="m1", model_b="m2")
    results = await mq.list_matches(pool, env_name="env_filter_test")
    assert any(r["id"] == mid for r in results)
    results_status = await mq.list_matches(pool, status="pending")
    assert any(r["id"] == mid for r in results_status)

@pytest.mark.asyncio(loop_scope="module")
async def test_get_match_returns_none_for_missing(pool):
    result = await mq.get_match(pool, "nonexistent_id_xyz")
    assert result is None

@pytest.mark.asyncio(loop_scope="module")
async def test_elo_get_or_create_default(pool):
    player = await elq.get_or_create(pool, "brand_new_model", "new_env")
    assert player.rating == 1500.0
    assert player.rd == 350.0
    assert player.volatility == 0.06
