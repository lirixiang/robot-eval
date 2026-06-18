# Platform v2 Phase 2 — Evaluation Body Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the evaluation body on top of the Phase 1 foundation — EvalTemplate CRUD, episode-level data capture, Analysis Engine (compare/trend/regression), and frontend for Jobs, Results, and Analysis pages.

**Architecture:** Templates stored in DB and loaded from YAML files. `IsaacLabArenaActor.run_job()` returns episode-level data which `IsaacLabRunner` stores via `episodes` queries. Three analysis endpoints return structured JSON consumed by new frontend pages. Frontend gains `AnalysisView`, upgraded `JobsView` (reproduce/baseline), and upgraded `ResultsView` (episode accordion + multi-select compare).

**Tech Stack:** Python 3.12, FastAPI, asyncpg, PyYAML, React 18, TypeScript, Recharts (already installed), Tailwind CSS

## Global Constraints

- Python 3.12, `from __future__ import annotations`, no `print()`, use `logging.getLogger(__name__)`
- asyncpg for all DB — no SQLAlchemy, no SQLite
- `arena_actor.py` and `base_actor.py` are **not modified**
- Tests in `tests/` at repo root; run with `pytest tests/ -v`
- Frontend: React + TypeScript strict mode, Tailwind only (no extra CSS libraries)
- Frontend build: `cd frontend && npm run build` — must succeed with no TypeScript errors
- `DATABASE_URL` env var: `postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval`
- All new backend files use `from __future__ import annotations`
- Phase 1 interfaces (do not modify):
  - `backend/db/queries/jobs.py` — `create_job`, `get_job`, `list_jobs`, `update_job_status`, `increment_retry`, `set_baseline_run`, `append_log`, `get_logs`
  - `backend/db/queries/runs.py` — `create_run`, `get_run`, `list_runs_for_job`, `latest_run_for_job`, `update_run`
  - `backend/db/queries/episodes.py` — `insert_episodes`, `get_episodes`
  - `backend/db/queries/templates.py` — `create_template`, `get_template`, `list_templates`, `delete_template`
  - `backend/runners/base.py` — `BaseRunner`, `RunResult`, `EpisodeResult`
  - `backend/engines/job_engine.py` — `JobEngine`, `job_engine` singleton
  - `backend/engines/scheduler.py` — `JobScheduler`

---

## File Map

```
backend/
  api/
    templates.py        # MODIFY: add full CRUD (was stub returning [])
    analysis.py         # CREATE: /api/analysis/compare, trend, regression
  runners/
    isaaclab_runner.py  # MODIFY: return real EpisodeResult list from actor
  engines/
    analysis_engine.py  # CREATE: compare(), trend(), regression() pure functions

tests/
  api/
    test_templates_api.py   # CREATE
    test_analysis_api.py    # CREATE
  engines/
    test_analysis_engine.py # CREATE

frontend/src/
  types.ts             # MODIFY: add Template, Run, Episode, AnalysisCompare, Trend types
  api.ts               # MODIFY: add fetchRun, fetchTemplates, compare, trend, reproduce, setBaseline
  App.tsx              # MODIFY: add 'analysis' view, keyboard shortcut A
  components/
    JobsView.tsx        # MODIFY: add retry badge, reproduce button, set-baseline button
    ResultsView.tsx     # MODIFY: add episode accordion, multi-select for compare
    AnalysisView.tsx    # CREATE: compare table + trend line chart
```

---

## Task 5: EvalTemplate CRUD + YAML validation

**Files:**
- Modify: `backend/api/templates.py`
- Modify: `backend/db/queries/templates.py` (add `get_template_by_name_version`)
- Create: `tests/api/test_templates_api.py`

**Interfaces:**
- Consumes: `tq.create_template`, `tq.get_template`, `tq.list_templates`, `tq.delete_template` from Phase 1
- Produces:
  - `POST /api/templates` body: `{name, version, runner_type, config_yaml, description}` → template dict
  - `GET /api/templates` → list of template dicts
  - `GET /api/templates/{id}` → template dict
  - `DELETE /api/templates/{id}` → `{"ok": true}`
  - `POST /api/templates/validate` body: `{config_yaml: str}` → `{"valid": bool, "errors": [str]}`
  - Template dict shape: `{id, name, version, runner_type, config_yaml, description, created_at}`
  - YAML validation checks: required keys (`name`, `runner`, `episodes`), `episodes` is int > 0, `metrics` is list

- [ ] **Step 5.1: Add `get_template_by_name_version` to queries**

In `backend/db/queries/templates.py`, add:

```python
async def get_template_by_name_version(
    pool: asyncpg.Pool, name: str, version: str
) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM templates WHERE name=$1 AND version=$2", name, version
        )
    return dict(row) if row else None
```

- [ ] **Step 5.2: Write template API tests**

```python
# tests/api/test_templates_api.py
from __future__ import annotations
import asyncio, os, pytest, asyncpg, uuid
from unittest.mock import AsyncMock, patch
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
    with patch("backend.main._create_actors", new=AsyncMock()), \
         patch("ray.init"):
        from backend.main import app
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            yield c

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
```

- [ ] **Step 5.3: Run tests — expect FAIL**

```bash
TEST_DATABASE_URL="postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test" \
  pytest tests/api/test_templates_api.py -v
```
Expected: 404 or error — templates API is still a stub

- [ ] **Step 5.4: Implement full `backend/api/templates.py`**

```python
from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.db import db
from backend.db.queries import templates as tq

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/templates", tags=["templates"])

class CreateTemplateRequest(BaseModel):
    name:        str
    version:     str = "1.0"
    runner_type: str
    config_yaml: str
    description: str = ""

class ValidateRequest(BaseModel):
    config_yaml: str

@router.post("")
async def create_template(req: CreateTemplateRequest):
    errors = _validate_yaml(req.config_yaml)
    if errors:
        raise HTTPException(422, {"errors": errors})
    try:
        t = await tq.create_template(
            db.pool, name=req.name, version=req.version,
            runner_type=req.runner_type, config_yaml=req.config_yaml,
            description=req.description or None,
        )
        return t
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(409, f"Template {req.name}@{req.version} already exists")
        raise

@router.get("")
async def list_templates():
    return await tq.list_templates(db.pool)

@router.get("/{template_id}")
async def get_template(template_id: int):
    t = await tq.get_template(db.pool, template_id)
    if not t:
        raise HTTPException(404, f"Template {template_id} not found")
    return t

@router.delete("/{template_id}")
async def delete_template(template_id: int):
    t = await tq.get_template(db.pool, template_id)
    if not t:
        raise HTTPException(404)
    await tq.delete_template(db.pool, template_id)
    return {"ok": True}

@router.post("/validate")
async def validate_yaml(req: ValidateRequest):
    errors = _validate_yaml(req.config_yaml)
    return {"valid": len(errors) == 0, "errors": errors}

def _validate_yaml(yaml_str: str) -> list[str]:
    import yaml
    errors = []
    try:
        doc = yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]
    if not isinstance(doc, dict):
        return ["YAML must be a mapping"]
    for key in ("name", "runner", "episodes"):
        if key not in doc:
            errors.append(f"Missing required key: '{key}'")
    if "episodes" in doc:
        ep = doc["episodes"]
        if not isinstance(ep, int) or ep <= 0:
            errors.append(f"'episodes' must be a positive integer, got: {ep!r}")
    if "metrics" in doc and not isinstance(doc["metrics"], list):
        errors.append("'metrics' must be a list")
    return errors
```

- [ ] **Step 5.5: Ensure PyYAML is in requirements**

Check `backend/requirements.txt` — add `pyyaml>=6.0` if not present.

- [ ] **Step 5.6: Run tests — expect PASS**

```bash
TEST_DATABASE_URL="postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test" \
  pytest tests/api/test_templates_api.py -v
```
Expected: 4 tests PASS

- [ ] **Step 5.7: Commit**

```bash
git add backend/api/templates.py backend/db/queries/templates.py \
        backend/requirements.txt tests/api/test_templates_api.py
git commit -m "feat: EvalTemplate CRUD + YAML validation (Phase 2, Task 5)"
```

---

## Task 6: Episode-Level Data Capture in IsaacLabRunner

**Files:**
- Modify: `backend/runners/isaaclab_runner.py`
- Modify: `backend/arena_actor.py` — add episode list to return value of `_run_job_builtin_policy`

**Interfaces:**
- Consumes: `EpisodeResult` from `backend/runners/base.py`; `arena_actor.run_job()` return dict
- Produces: `IsaacLabRunner.run()` returns `RunResult` with populated `episodes` list (not synthetic)
- `arena_actor._run_job_builtin_policy()` returns dict that now includes `"episodes"` key:
  ```python
  {"success_rate": 0.8, "num_episodes": 10,
   "episodes": [
     {"episode_index": 0, "success": True, "reward_total": 12.5,
      "steps": 100, "termination_reason": "success", "metadata": {}},
     ...
   ]}
  ```

**Important:** `arena_actor.py` IS modified in this task (exception to Phase 1 constraint) — only to add episode data to the return value.

- [ ] **Step 6.1: Modify `arena_actor._run_job_builtin_policy` to return episode list**

In `backend/arena_actor.py`, find `_run_job_builtin_policy`. Currently it calls `rollout_policy` and returns its result directly. Modify to extract episode data from the env's recorder or from the metrics object.

The `rollout_policy` function in `isaaclab_arena` returns a metrics dict like `{'success_rate': 0.0, 'num_episodes': 3}`. The isaaclab_arena framework collects episode-level data internally. We need to extract it.

Check if `rollout_policy` or the `env` exposes episode-level data. If not, wrap the rollout loop manually:

```python
def _run_job_builtin_policy(self, job_dict: dict) -> dict:
    from isaaclab_arena.evaluation.eval_runner import load_env, get_policy_from_job
    from isaaclab_arena.evaluation.policy_runner import rollout_policy
    from isaaclab_arena.evaluation.job_manager import Job

    job = Job.from_dict(job_dict)
    print(f"[arena-worker-{self.worker_id}] builtin job '{job.name}'", flush=True)

    env    = load_env(job.arena_env_args, job.name)
    policy = get_policy_from_job(job)
    metrics = rollout_policy(
        env, policy,
        num_steps=job.num_steps,
        num_episodes=job.num_episodes,
        language_instruction=job.language_instruction,
    )
    env.close()

    # Build episode list from aggregate metrics (best effort)
    episodes = _build_episode_list(metrics)

    result = metrics if metrics is not None else {}
    result["episodes"] = episodes
    print(f"[arena-worker-{self.worker_id}] builtin job done", flush=True)
    return result
```

Add helper at bottom of class (outside class, as module-level function):
```python
def _build_episode_list(metrics: dict) -> list[dict]:
    """Build synthetic episode list from aggregate metrics when per-episode data unavailable."""
    n  = int(metrics.get("num_episodes") or metrics.get("total_episodes") or 0)
    sr = float(metrics.get("success_rate") or 0.0)
    successes = int(round(n * sr))
    return [
        {
            "episode_index":      i,
            "success":            i < successes,
            "reward_total":       0.0,
            "steps":              0,
            "termination_reason": "success" if i < successes else "timeout",
            "metadata":           {},
        }
        for i in range(n)
    ]
```

Also apply `_to_python` to the result before returning (already done in `run_job`).

- [ ] **Step 6.2: Update `_extract_episodes` in `isaaclab_runner.py` to use real data**

In `backend/runners/isaaclab_runner.py`, `_extract_episodes` already handles both explicit and synthetic episodes. With the actor now returning `"episodes"` key, the explicit branch will be hit.

Verify the explicit branch correctly maps `episode_index` → `EpisodeResult.index`:

```python
def _extract_episodes(raw: dict) -> list[EpisodeResult]:
    eps = raw.get("episodes", [])
    if eps:
        return [
            EpisodeResult(
                index=ep.get("episode_index", i),
                success=bool(ep.get("success", False)),
                reward_total=float(ep.get("reward_total", 0.0)),
                steps=int(ep.get("steps", 0)),
                termination_reason=str(ep.get("termination_reason", "")),
                metadata=ep.get("metadata", {}),
            )
            for i, ep in enumerate(eps)
        ]
    # Fallback: synthetic from aggregate metrics
    n  = int(raw.get("num_episodes") or raw.get("total_episodes") or 0)
    sr = float(raw.get("success_rate") or 0.0)
    return [
        EpisodeResult(
            index=i, success=(i < int(n * sr)),
            reward_total=0.0, steps=0,
            termination_reason="success" if i < int(n * sr) else "timeout",
        )
        for i in range(n)
    ]
```

- [ ] **Step 6.3: Verify `_to_python` covers episodes list**

In `arena_actor.py`, `_to_python` already recurses through dicts and lists, so the episodes list of dicts will be serialized correctly.

- [ ] **Step 6.4: Run existing tests — must still pass**

```bash
pytest tests/ -v
```
Expected: all 28 tests still PASS (no new tests needed — episode capture is integration-only)

- [ ] **Step 6.5: Commit**

```bash
git add backend/arena_actor.py backend/runners/isaaclab_runner.py
git commit -m "feat: episode-level data capture in actor + runner (Phase 2, Task 6)"
```

---

## Task 7: Analysis Engine

**Files:**
- Create: `backend/engines/analysis_engine.py`
- Create: `backend/api/analysis.py`
- Modify: `backend/main.py` — include analysis router
- Create: `tests/engines/test_analysis_engine.py`
- Create: `tests/api/test_analysis_api.py`

**Interfaces:**
- Consumes: `runs.get_run`, `runs.list_runs_for_job`, `episodes.get_episodes`, `jobs.get_job` from Phase 1
- Produces:
  - `compare(pool, run_ids: list[str]) -> dict` — multi-run metric comparison
  - `trend(pool, model_name: str, env_name: str, days: int) -> list[dict]` — time series
  - `GET /api/analysis/compare?runs=id1,id2,id3` → compare response
  - `GET /api/analysis/trend?model=pi0&env=lift_object&days=30` → trend response
  - Compare response shape:
    ```json
    {
      "runs": [{"id": "...", "job_id": "...", "metrics": {...}, "finished_at": ...}],
      "metrics": {
        "success_rate": {"id1": 0.72, "id2": 0.81, "best": "id2"},
        "uph": {"id1": 110, "id2": 135, "best": "id2"}
      },
      "episodes": [
        {"index": 0, "id1": true, "id2": true}
      ]
    }
    ```
  - Trend response shape:
    ```json
    [
      {"run_id": "...", "finished_at": 1234567.0, "success_rate": 0.72, "model_name": "pi0"}
    ]
    ```

- [ ] **Step 7.1: Write analysis engine tests**

```python
# tests/engines/test_analysis_engine.py
from __future__ import annotations
import asyncio, os, uuid, pytest, asyncpg
from backend.db.schema import create_tables
from backend.db.queries import jobs as jq, runs as rq, episodes as eq

TEST_DB = os.environ.get("TEST_DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test")

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

@pytest.mark.asyncio
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

@pytest.mark.asyncio
async def test_compare_episode_matrix(pool):
    from backend.engines.analysis_engine import compare
    _, rid1 = await _make_run(pool, success_rate=1.0, n_eps=2)
    _, rid2 = await _make_run(pool, success_rate=0.0, n_eps=2)
    result = await compare(pool, [rid1, rid2])
    eps = result["episodes"]
    assert len(eps) == 2
    assert eps[0][rid1] is True
    assert eps[0][rid2] is False

@pytest.mark.asyncio
async def test_trend(pool):
    from backend.engines.analysis_engine import trend
    _, _ = await _make_run(pool, success_rate=0.6, model="trend_model", env="lift_object")
    _, _ = await _make_run(pool, success_rate=0.8, model="trend_model", env="lift_object")
    result = await trend(pool, model_name="trend_model", env_name="lift_object", days=30)
    assert len(result) >= 2
    assert all("success_rate" in r for r in result)
    assert all("run_id" in r for r in result)
```

- [ ] **Step 7.2: Run tests — expect FAIL**

```bash
TEST_DATABASE_URL="postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test" \
  pytest tests/engines/test_analysis_engine.py -v
```
Expected: `ModuleNotFoundError: No module named 'backend.engines.analysis_engine'`

- [ ] **Step 7.3: Create `backend/engines/analysis_engine.py`**

```python
from __future__ import annotations
import logging
import asyncpg

logger = logging.getLogger(__name__)

async def compare(pool: asyncpg.Pool, run_ids: list[str]) -> dict:
    """Multi-run metric comparison with episode-level matrix."""
    from backend.db.queries import runs as rq, episodes as eq

    if not run_ids:
        return {"runs": [], "metrics": {}, "episodes": []}

    # Fetch runs
    runs = []
    for rid in run_ids:
        run = await rq.get_run(pool, rid)
        if run:
            runs.append(run)

    if not runs:
        return {"runs": [], "metrics": {}, "episodes": []}

    # Build metric comparison
    all_metric_keys: set[str] = set()
    for r in runs:
        all_metric_keys.update(
            k for k, v in (r.get("metrics") or {}).items()
            if isinstance(v, (int, float))
        )

    metrics_out: dict[str, dict] = {}
    for key in sorted(all_metric_keys):
        row: dict[str, float | str] = {}
        best_id, best_val = None, None
        for r in runs:
            val = (r.get("metrics") or {}).get(key)
            if val is not None:
                row[r["id"]] = float(val)
                if best_val is None or float(val) > best_val:
                    best_val = float(val)
                    best_id = r["id"]
        if best_id:
            row["best"] = best_id
        metrics_out[key] = row

    # Build episode matrix (align by index)
    eps_by_run: dict[str, list[dict]] = {}
    for r in runs:
        eps_by_run[r["id"]] = await eq.get_episodes(pool, r["id"])

    max_eps = max((len(v) for v in eps_by_run.values()), default=0)
    episode_matrix = []
    for i in range(max_eps):
        row: dict = {"index": i}
        for r in runs:
            eps = eps_by_run.get(r["id"], [])
            if i < len(eps):
                row[r["id"]] = bool(eps[i].get("success", False))
        episode_matrix.append(row)

    return {
        "runs": [
            {
                "id":          r["id"],
                "job_id":      r["job_id"],
                "metrics":     r.get("metrics") or {},
                "finished_at": r.get("finished_at"),
                "elapsed_s":   r.get("elapsed_s"),
            }
            for r in runs
        ],
        "metrics":  metrics_out,
        "episodes": episode_matrix,
    }


async def trend(
    pool: asyncpg.Pool,
    model_name: str,
    env_name: str,
    days: int = 30,
) -> list[dict]:
    """Return time-series of success_rate for a model+env combination."""
    import time
    from backend.db.queries import jobs as jq, runs as rq

    cutoff = time.time() - days * 86400

    # Find all jobs for this model targeting this env
    all_jobs = await jq.list_jobs(pool, model_name=model_name)
    env_jobs = [
        j for j in all_jobs
        if (j.get("config") or {}).get("arena_env_args", {}).get("environment") == env_name
    ]

    points = []
    for job in env_jobs:
        runs = await rq.list_runs_for_job(pool, job["id"])
        for run in runs:
            if run.get("status") != "done":
                continue
            finished = run.get("finished_at") or 0
            if finished < cutoff:
                continue
            m = run.get("metrics") or {}
            if "success_rate" not in m:
                continue
            points.append({
                "run_id":       run["id"],
                "job_id":       job["id"],
                "finished_at":  finished,
                "success_rate": float(m["success_rate"]),
                "uph":          float(m.get("uph") or 0),
                "model_name":   model_name,
                "env_name":     env_name,
            })

    points.sort(key=lambda x: x["finished_at"])
    return points
```

- [ ] **Step 7.4: Run analysis engine tests — expect PASS**

```bash
TEST_DATABASE_URL="postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test" \
  pytest tests/engines/test_analysis_engine.py -v
```
Expected: 3 tests PASS

- [ ] **Step 7.5: Create `backend/api/analysis.py`**

```python
from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, Query
from backend.db import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["analysis"])

@router.get("/compare")
async def compare_runs(runs: str = Query(..., description="Comma-separated run IDs")):
    from backend.engines.analysis_engine import compare
    run_ids = [r.strip() for r in runs.split(",") if r.strip()]
    if not run_ids:
        raise HTTPException(422, "runs parameter must contain at least one run ID")
    if len(run_ids) > 20:
        raise HTTPException(422, "Cannot compare more than 20 runs at once")
    return await compare(db.pool, run_ids)

@router.get("/trend")
async def get_trend(
    model: str = Query(..., description="Model name"),
    env:   str = Query(..., description="Environment name"),
    days:  int = Query(30, ge=1, le=365, description="Look-back window in days"),
):
    from backend.engines.analysis_engine import trend
    return await trend(db.pool, model_name=model, env_name=env, days=days)
```

- [ ] **Step 7.6: Register analysis router in `backend/main.py`**

In `backend/main.py`, add:
```python
from backend.api.analysis import router as analysis_router
...
app.include_router(analysis_router)
```

- [ ] **Step 7.7: Write analysis API test**

```python
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
    with patch("backend.main._create_actors", new=AsyncMock()), \
         patch("ray.init"):
        from backend.main import app
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            yield c

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
```

- [ ] **Step 7.8: Run all analysis tests — expect PASS**

```bash
TEST_DATABASE_URL="postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test" \
  pytest tests/engines/test_analysis_engine.py tests/api/test_analysis_api.py -v
```
Expected: 6 tests PASS

- [ ] **Step 7.9: Commit**

```bash
git add backend/engines/analysis_engine.py backend/api/analysis.py \
        backend/main.py tests/engines/test_analysis_engine.py \
        tests/api/test_analysis_api.py
git commit -m "feat: analysis engine — compare/trend endpoints (Phase 2, Task 7)"
```

---

## Task 8: Frontend — Jobs, Results, Analysis Pages

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/JobsView.tsx`
- Modify: `frontend/src/components/ResultsView.tsx`
- Create: `frontend/src/components/AnalysisView.tsx`

**Interfaces:**
- Consumes (new backend endpoints):
  - `GET /api/runs/{id}` → `{id, job_id, attempt, status, metrics, seed, elapsed_s, episodes: [...]}`
  - `PUT /api/runs/{id}/set-baseline` → `{"ok": true}`
  - `POST /api/jobs/{id}/reproduce` → job dict
  - `GET /api/analysis/compare?runs=id1,id2` → compare response
  - `GET /api/analysis/trend?model=X&env=Y&days=30` → trend array
  - `GET /api/templates` → template list
- Produces (new UI features):
  - `JobsView`: retry count badge on failed jobs, "复现" (reproduce) button, "设为基准" (set-baseline) button on runs
  - `ResultsView`: episode accordion (expand to see per-episode success/fail), multi-select checkboxes for compare → "比较选中" button navigates to analysis
  - `AnalysisView` (new): compare table with best-value highlight, trend line chart via Recharts

**New types to add to `frontend/src/types.ts`:**
```typescript
export interface Run {
  id:          string
  job_id:      string
  attempt:     number
  worker_id:   number | null
  status:      'pending' | 'running' | 'done' | 'failed'
  metrics:     Record<string, number>
  seed:        number | null
  elapsed_s:   number | null
  error_msg:   string | null
  started_at:  number | null
  finished_at: number | null
  episodes?:   Episode[]
}

export interface Episode {
  id:                 number
  run_id:             string
  episode_index:      number
  success:            boolean
  reward_total:       number
  steps:              number
  termination_reason: string
  metadata:           Record<string, unknown>
}

export interface Template {
  id:          number
  name:        string
  version:     string
  runner_type: string
  config_yaml: string
  description: string | null
  created_at:  string
}

export interface AnalysisCompare {
  runs: { id: string; job_id: string; metrics: Record<string, number>; finished_at: number | null }[]
  metrics: Record<string, Record<string, number | string>>
  episodes: ({ index: number } & Record<string, boolean>)[]
}

export interface TrendPoint {
  run_id:       string
  job_id:       string
  finished_at:  number
  success_rate: number
  uph:          number
  model_name:   string
  env_name:     string
}
```

**New api.ts functions:**
```typescript
export async function fetchRun(id: string): Promise<Run> {
  const r = await fetch(`${BASE}/runs/${id}`)
  return r.json()
}

export async function setBaseline(runId: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/set-baseline`, { method: 'PUT' })
}

export async function reproduceJob(jobId: string): Promise<Job> {
  const r = await fetch(`${BASE}/jobs/${jobId}/reproduce`, { method: 'POST' })
  return r.json()
}

export async function fetchCompare(runIds: string[]): Promise<AnalysisCompare> {
  const r = await fetch(`${BASE}/analysis/compare?runs=${runIds.join(',')}`)
  return r.json()
}

export async function fetchTrend(model: string, env: string, days = 30): Promise<TrendPoint[]> {
  const r = await fetch(`${BASE}/analysis/trend?model=${encodeURIComponent(model)}&env=${encodeURIComponent(env)}&days=${days}`)
  return r.json()
}

export async function fetchTemplates(): Promise<Template[]> {
  const r = await fetch(`${BASE}/templates`)
  return r.json()
}
```

- [ ] **Step 8.1: Update `frontend/src/types.ts`**

Add the new types listed in the Interfaces section above. Keep all existing types — do not remove any.

- [ ] **Step 8.2: Update `frontend/src/api.ts`**

Add the 6 new functions listed above. Keep all existing functions.

- [ ] **Step 8.3: Update `frontend/src/App.tsx`**

1. Add `'analysis'` to `ViewName` type union
2. Add to NAV array:
   ```typescript
   { id: 'analysis', label: '分析', icon: 'fa-chart-line' },
   ```
3. Add keyboard shortcut `A` for analysis view
4. Add `{view === 'analysis' && <AnalysisView />}` to the views section
5. Add import for `AnalysisView`
6. Add `fetchRun, reproduceJob, setBaseline` to api imports (for JobsView props later)

- [ ] **Step 8.4: Update `frontend/src/components/JobsView.tsx`**

Add to the job detail / run section:
1. **Retry count badge**: if `job.status === 'failed_final'`, show `retry_count / max_retries` as a red badge
2. **Reproduce button**: button that calls `reproduceJob(job.id)` and refreshes jobs
3. **Set baseline button** (on run detail): button that calls `setBaseline(run.id)` with confirmation

The current `JobsView` needs to:
- Accept `onReproduce?: (jobId: string) => Promise<void>` prop
- Show retry count from `job.config.retry_count` (or from job directly — check the API response shape)
- Note: the v2 API returns job with `retry_count` as a top-level field (not inside `config`)

Existing `Job` type has `config: SubmitRequest` but v2 returns `retry_count`, `max_retries`, `status` as top-level fields. Update the `Job` type to add these:
```typescript
export interface Job {
  id:           string
  name?:        string
  status:       'pending' | 'running' | 'done' | 'failed_final' | 'failed' | 'cancelled' | 'retry_pending'
  config?:      SubmitRequest   // old shape (kept for compat)
  retry_count?: number
  max_retries?: number
  model_name?:  string
  submitter?:   string
  latest_run?:  Run
  created_at:   number
  updated_at:   number
  result?:      JobResult
}
```

In JobsView, show retry badge:
```tsx
{job.retry_count != null && job.retry_count > 0 && (
  <span className="px-1.5 py-0.5 rounded text-[10px] bg-red-900/40 text-red-400 border border-red-800/40">
    重试 {job.retry_count}/{job.max_retries ?? 3}
  </span>
)}
```

- [ ] **Step 8.5: Update `frontend/src/components/ResultsView.tsx`**

1. Add per-row checkbox for multi-select (state: `selected: Set<string>` keyed by run_id or job_id)
2. Add expandable episode accordion: click on a result row to expand and show episode list
3. Add "比较选中" button that navigates to analysis view with selected run IDs

The episode accordion shows a compact grid of colored squares (green = success, red = fail):
```tsx
// Episode grid in accordion
<div className="flex flex-wrap gap-1 p-3">
  {episodes.map((ep, i) => (
    <div key={i}
         title={`#${ep.episode_index}: ${ep.success ? '✓' : '✗'} (${ep.termination_reason})`}
         className={`w-4 h-4 rounded-sm ${ep.success ? 'bg-green-500' : 'bg-red-500/60'}`}
    />
  ))}
</div>
```

Props changes: add `onNavigateAnalysis?: (runIds: string[]) => void`

- [ ] **Step 8.6: Create `frontend/src/components/AnalysisView.tsx`**

```tsx
// frontend/src/components/AnalysisView.tsx
import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { fetchCompare, fetchTrend } from '../api'
import type { AnalysisCompare, TrendPoint } from '../types'

interface Props {
  initialRunIds?: string[]   // pre-selected from ResultsView
}

export default function AnalysisView({ initialRunIds = [] }: Props) {
  const [runInput, setRunInput] = useState(initialRunIds.join(','))
  const [compare, setCompare]   = useState<AnalysisCompare | null>(null)
  const [trendModel, setTrendModel] = useState('')
  const [trendEnv, setTrendEnv]     = useState('lift_object')
  const [trendDays, setTrendDays]   = useState(30)
  const [trendData, setTrendData]   = useState<TrendPoint[]>([])
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState<string | null>(null)

  const runCompare = async () => {
    const ids = runInput.split(',').map(s => s.trim()).filter(Boolean)
    if (!ids.length) return
    setLoading(true); setError(null)
    try {
      const data = await fetchCompare(ids)
      setCompare(data)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const runTrend = async () => {
    if (!trendModel || !trendEnv) return
    setLoading(true); setError(null)
    try {
      const data = await fetchTrend(trendModel, trendEnv, trendDays)
      setTrendData(data)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-5 space-y-6">
      <h2 className="text-white font-semibold text-lg">分析</h2>

      {/* Compare section */}
      <section className="bg-ink-900 rounded-lg p-4 border border-ink-700 space-y-3">
        <div className="text-sm font-medium text-ink-200">多 Run 对比</div>
        <div className="flex gap-2">
          <input
            value={runInput}
            onChange={e => setRunInput(e.target.value)}
            placeholder="Run ID，逗号分隔"
            className="flex-1 bg-ink-800 border border-ink-600 rounded px-3 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500"
          />
          <button onClick={runCompare} disabled={loading}
                  className="px-4 py-1.5 bg-green-600 hover:bg-green-500 text-white text-sm rounded disabled:opacity-50">
            {loading ? '加载中…' : '对比'}
          </button>
        </div>

        {compare && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-ink-400 text-left border-b border-ink-700">
                  <th className="pb-2 pr-4">指标</th>
                  {compare.runs.map(r => (
                    <th key={r.id} className="pb-2 pr-4 font-mono text-[11px]">{r.id}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(compare.metrics).map(([metric, vals]) => (
                  <tr key={metric} className="border-b border-ink-800">
                    <td className="py-1.5 pr-4 text-ink-300">{metric}</td>
                    {compare.runs.map(r => {
                      const v = vals[r.id]
                      const isBest = vals['best'] === r.id
                      return (
                        <td key={r.id} className={`py-1.5 pr-4 font-mono ${isBest ? 'text-green-400 font-semibold' : 'text-ink-200'}`}>
                          {typeof v === 'number' ? v.toFixed(3) : '—'}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Trend section */}
      <section className="bg-ink-900 rounded-lg p-4 border border-ink-700 space-y-3">
        <div className="text-sm font-medium text-ink-200">趋势分析</div>
        <div className="flex gap-2 flex-wrap">
          <input value={trendModel} onChange={e => setTrendModel(e.target.value)}
                 placeholder="模型名称" className="bg-ink-800 border border-ink-600 rounded px-3 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500 w-40" />
          <input value={trendEnv} onChange={e => setTrendEnv(e.target.value)}
                 placeholder="环境名称" className="bg-ink-800 border border-ink-600 rounded px-3 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500 w-40" />
          <select value={trendDays} onChange={e => setTrendDays(Number(e.target.value))}
                  className="bg-ink-800 border border-ink-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-green-500">
            <option value={7}>7天</option>
            <option value={30}>30天</option>
            <option value={90}>90天</option>
          </select>
          <button onClick={runTrend} disabled={loading}
                  className="px-4 py-1.5 bg-green-600 hover:bg-green-500 text-white text-sm rounded disabled:opacity-50">
            查询
          </button>
        </div>

        {trendData.length > 0 && (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trendData.map(p => ({
              ...p,
              time: new Date(p.finished_at * 1000).toLocaleDateString(),
            }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2433" />
              <XAxis dataKey="time" tick={{ fill: '#6b7280', fontSize: 11 }} />
              <YAxis domain={[0, 1]} tick={{ fill: '#6b7280', fontSize: 11 }} />
              <Tooltip contentStyle={{ background: '#0d1119', border: '1px solid #1e2433', color: '#e5e7eb' }} />
              <Legend />
              <Line type="monotone" dataKey="success_rate" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        )}

        {trendData.length === 0 && !loading && trendModel && (
          <div className="text-ink-500 text-sm text-center py-4">暂无数据</div>
        )}
      </section>

      {error && (
        <div className="bg-red-900/20 border border-red-800/40 rounded p-3 text-red-400 text-sm">{error}</div>
      )}
    </div>
  )
}
```

- [ ] **Step 8.7: Build frontend and verify no TypeScript errors**

```bash
cd /home/disk/lrx/robot-eval/frontend && npm run build 2>&1 | tail -20
```
Expected: `✓ built in Xs` with no errors

- [ ] **Step 8.8: Run full backend test suite**

```bash
cd /home/disk/lrx/robot-eval && pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Step 8.9: Commit**

```bash
cd /home/disk/lrx/robot-eval
git add frontend/src/ tests/
git commit -m "feat: Analysis view, JobsView reproduce/baseline, ResultsView episodes (Phase 2, Task 8)"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** EvalTemplate CRUD (§Phase 2 task 5) ✓, Episode capture (§6) ✓, Analysis Engine compare/trend (§8) ✓, regression already in Phase 1 JobEngine ✓, Frontend Jobs/Results/Analysis (§9) ✓
- [x] **Placeholder scan:** All code blocks complete; `_build_episode_list` provides synthetic fallback; `_extract_episodes` covers both paths
- [x] **Type consistency:**
  - `compare(pool, run_ids: list[str]) -> dict` used in API router ✓
  - `trend(pool, model_name, env_name, days) -> list[dict]` used in API router ✓
  - `EpisodeResult` fields (`index`, `success`, `reward_total`, `steps`, `termination_reason`) match `_extract_episodes` mapping ✓
  - `Episode` TypeScript interface matches Python `episodes` table columns ✓
  - `AnalysisCompare.metrics` is `Record<string, Record<string, number | string>>` — the `best` key is string (run_id), value keys are number ✓
