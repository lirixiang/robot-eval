# tests/api/test_templates_api.py
from __future__ import annotations
import asyncio, os, pytest, asyncpg, uuid
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

TEST_DB = os.environ.get("TEST_DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test")

VALID_YAML = """
name: lift_object
version: "1.0"
runner: isaaclab
runner_config:
  environment: lift_object
  embodiment: franka_joint_pos
metrics:
  - name: success_rate
    type: ratio
    higher_is_better: true
episodes: 50
timeout_s: 3600
""".strip()

INVALID_YAML = "name: test\nrunner: isaaclab\n# missing episodes"

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop(); yield loop; loop.close()

@pytest.fixture(scope="module")
async def client():
    os.environ["DATABASE_URL"] = TEST_DB

    from backend.db.schema import create_tables
    p = await asyncpg.create_pool(TEST_DB)
    await create_tables(p)
    await p.close()

    from backend.db import init_db, db
    await init_db(TEST_DB)

    with patch("backend.main._create_actors", new=AsyncMock()), \
         patch("ray.init"):
        from backend.main import app
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            yield c
    await db.close()

@pytest.mark.asyncio(loop_scope="module")
async def test_create_template(client):
    r = await client.post("/api/templates", json={
        "name": f"test_{uuid.uuid4().hex[:6]}", "version": "1.0",
        "runner_type": "isaaclab", "config_yaml": VALID_YAML,
        "description": "test template",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["name"].startswith("test_")
    assert data["runner_type"] == "isaaclab"

@pytest.mark.asyncio(loop_scope="module")
async def test_list_templates(client):
    r = await client.get("/api/templates")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

@pytest.mark.asyncio(loop_scope="module")
async def test_get_template(client):
    # Create one first, then fetch by id
    name = f"test_{uuid.uuid4().hex[:6]}"
    r = await client.post("/api/templates", json={
        "name": name, "version": "2.0",
        "runner_type": "isaaclab", "config_yaml": VALID_YAML,
    })
    assert r.status_code == 200
    tid = r.json()["id"]

    r2 = await client.get(f"/api/templates/{tid}")
    assert r2.status_code == 200
    assert r2.json()["id"] == tid

@pytest.mark.asyncio(loop_scope="module")
async def test_get_template_not_found(client):
    r = await client.get("/api/templates/999999")
    assert r.status_code == 404

@pytest.mark.asyncio(loop_scope="module")
async def test_delete_template(client):
    name = f"test_{uuid.uuid4().hex[:6]}"
    r = await client.post("/api/templates", json={
        "name": name, "version": "1.0",
        "runner_type": "isaaclab", "config_yaml": VALID_YAML,
    })
    assert r.status_code == 200
    tid = r.json()["id"]

    r2 = await client.delete(f"/api/templates/{tid}")
    assert r2.status_code == 200
    assert r2.json() == {"ok": True}

    r3 = await client.get(f"/api/templates/{tid}")
    assert r3.status_code == 404

@pytest.mark.asyncio(loop_scope="module")
async def test_validate_valid_yaml(client):
    r = await client.post("/api/templates/validate",
                          json={"config_yaml": VALID_YAML})
    assert r.status_code == 200
    assert r.json()["valid"] is True
    assert r.json()["errors"] == []

@pytest.mark.asyncio(loop_scope="module")
async def test_validate_invalid_yaml(client):
    r = await client.post("/api/templates/validate",
                          json={"config_yaml": INVALID_YAML})
    assert r.status_code == 200
    assert r.json()["valid"] is False
    assert len(r.json()["errors"]) > 0

@pytest.mark.asyncio(loop_scope="module")
async def test_create_template_invalid_yaml(client):
    r = await client.post("/api/templates", json={
        "name": f"test_{uuid.uuid4().hex[:6]}", "version": "1.0",
        "runner_type": "isaaclab", "config_yaml": INVALID_YAML,
    })
    assert r.status_code == 422
