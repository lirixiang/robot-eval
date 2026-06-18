# Platform v2 Phase 1 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the platform foundation — DB schema, Runner plugin layer, Job Engine with proper scheduling/retry, and clean API structure.

**Architecture:** PostgreSQL stores jobs/runs/episodes/templates. A `BaseRunner` ABC with `RunResult` dataclass decouples execution from orchestration. A `JobScheduler` replaces the 60×5s polling loop with asyncio queues. FastAPI routers are split into focused files under `backend/api/`.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, asyncio, PyYAML, Ray 2.52.1, pytest + pytest-asyncio

## Global Constraints

- Python 3.12 only (must match Ray worker Python version)
- asyncpg for all DB access — no SQLAlchemy, no SQLite
- `DATABASE_URL` env var: `postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval`
- `RAY_ADDRESS` env var: `ray://127.0.0.1:10001`
- `backend/` is uploaded to Ray GCS as `working_dir` — keep it importable (no relative imports beyond `backend/`)
- `arena_actor.py` and `base_actor.py` are **not modified** in Phase 1
- All new files use `from __future__ import annotations`
- No `print()` — use `import logging; logger = logging.getLogger(__name__)` for now (structlog in Phase 4)
- Tests go in `tests/` at repo root; run with `pytest tests/ -v`

---

## File Map

```
backend/
  db/
    __init__.py          # exports: db (Database singleton), init_db()
    schema.py            # create_tables() — all DDL
    queries/
      __init__.py
      jobs.py            # async CRUD for jobs table
      runs.py            # async CRUD for runs table
      episodes.py        # async CRUD for episodes table
      templates.py       # async CRUD for templates table
  runners/
    __init__.py
    base.py              # BaseRunner ABC, RunResult, EpisodeResult dataclasses
    registry.py          # _REGISTRY dict, get_runner(), register_runner()
    isaaclab_runner.py   # IsaacLabRunner — wraps Ray Actor call
    remote_policy.py     # RemotePolicyRunner — HTTP Policy Server
  engines/
    __init__.py
    job_engine.py        # JobEngine: create_job, enqueue, cancel, reproduce
    scheduler.py         # JobScheduler: asyncio queue-based dispatch loop
  api/
    __init__.py
    jobs.py              # /api/jobs router
    runs.py              # /api/runs router
    workers.py           # /api/workers router (moved from main.py)
    templates.py         # /api/templates router (stub for Phase 2)
  main.py                # FastAPI app + lifespan (slimmed down)
  base_actor.py          # UNCHANGED
  arena_actor.py         # UNCHANGED

tests/
  conftest.py            # pytest fixtures: test DB, mock runner
  db/
    test_schema.py
    test_jobs_queries.py
    test_runs_queries.py
  runners/
    test_base.py
    test_registry.py
    test_remote_policy.py
  engines/
    test_job_engine.py
    test_scheduler.py
  api/
    test_jobs_api.py
```

---

## Task 1: DB Schema Migration

**Files:**
- Create: `backend/db/__init__.py`
- Create: `backend/db/schema.py`
- Create: `backend/db/queries/__init__.py`
- Create: `backend/db/queries/jobs.py`
- Create: `backend/db/queries/runs.py`
- Create: `backend/db/queries/episodes.py`
- Create: `backend/db/queries/templates.py`
- Create: `tests/conftest.py`
- Create: `tests/db/test_schema.py`
- Create: `tests/db/test_jobs_queries.py`
- Create: `tests/db/test_runs_queries.py`

**Interfaces:**
- Produces:
  - `backend/db/__init__.py` exports `db: Database` singleton and `init_db(url: str) -> None`
  - `Database.pool: asyncpg.Pool`
  - `create_tables(pool: asyncpg.Pool) -> None`
  - `jobs.create_job(pool, id, name, template_id, model_name, submitter, policy_config, policy_server_url, max_retries, timeout_s, description) -> dict`
  - `jobs.get_job(pool, job_id: str) -> dict | None`
  - `jobs.list_jobs(pool, status=None, model_name=None, submitter=None) -> list[dict]`
  - `jobs.update_job_status(pool, job_id: str, status: str) -> None`
  - `jobs.increment_retry(pool, job_id: str) -> int` — returns new retry_count
  - `jobs.set_baseline_run(pool, job_id: str, run_id: str) -> None`
  - `runs.create_run(pool, id, job_id, attempt, seed) -> dict`
  - `runs.get_run(pool, run_id: str) -> dict | None`
  - `runs.list_runs_for_job(pool, job_id: str) -> list[dict]`
  - `runs.update_run(pool, run_id, status=None, metrics=None, elapsed_s=None, error_msg=None, worker_id=None, started_at=None, finished_at=None) -> None`
  - `runs.latest_run_for_job(pool, job_id: str) -> dict | None`
  - `episodes.insert_episodes(pool, run_id: str, episodes: list[dict]) -> None`
  - `episodes.get_episodes(pool, run_id: str) -> list[dict]`
  - `templates.create_template(pool, name, version, runner_type, config_yaml, description) -> dict`
  - `templates.get_template(pool, template_id: int) -> dict | None`
  - `templates.list_templates(pool) -> list[dict]`

- [ ] **Step 1.1: Write schema test**

```python
# tests/db/test_schema.py
import asyncio, os, pytest, asyncpg
import sys; sys.path.insert(0, ".")
from backend.db.schema import create_tables

TEST_DB = os.environ.get("TEST_DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test")

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="module")
async def pool():
    p = await asyncpg.create_pool(TEST_DB)
    await create_tables(p)
    yield p
    await p.close()

@pytest.mark.asyncio
async def test_tables_exist(pool):
    tables = await pool.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    )
    names = {r["tablename"] for r in tables}
    for t in ("templates","jobs","runs","episodes","matches","match_runs",
              "elo_ratings","elo_history","hosts","remote_workers"):
        assert t in names, f"Missing table: {t}"
```

- [ ] **Step 1.2: Run test — expect FAIL**

```bash
cd /home/disk/lrx/robot-eval
TEST_DATABASE_URL="postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test" \
  pytest tests/db/test_schema.py -v
```
Expected: `ModuleNotFoundError: No module named 'backend.db.schema'`

- [ ] **Step 1.3: Create `backend/db/__init__.py`**

```python
from __future__ import annotations
import asyncpg
from backend.db.schema import create_tables

class Database:
    pool: asyncpg.Pool | None = None

    async def init(self, url: str) -> None:
        self.pool = await asyncpg.create_pool(url, min_size=2, max_size=10)
        await create_tables(self.pool)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

db = Database()

async def init_db(url: str) -> None:
    await db.init(url)
```

- [ ] **Step 1.4: Create `backend/db/schema.py`**

```python
from __future__ import annotations
import asyncpg

async def create_tables(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            version     TEXT NOT NULL DEFAULT '1.0',
            runner_type TEXT NOT NULL,
            config_yaml TEXT NOT NULL,
            description TEXT,
            created_at  TIMESTAMPTZ DEFAULT now(),
            UNIQUE(name, version)
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id                TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            template_id       INTEGER REFERENCES templates(id),
            model_name        TEXT,
            submitter         TEXT,
            policy_config     JSONB DEFAULT '{}',
            policy_server_url TEXT DEFAULT '',
            status            TEXT DEFAULT 'pending',
            retry_count       INTEGER DEFAULT 0,
            max_retries       INTEGER DEFAULT 3,
            timeout_s         INTEGER DEFAULT 3600,
            baseline_run_id   TEXT,
            description       TEXT,
            created_at        DOUBLE PRECISION,
            updated_at        DOUBLE PRECISION
        );

        CREATE TABLE IF NOT EXISTS runs (
            id          TEXT PRIMARY KEY,
            job_id      TEXT REFERENCES jobs(id),
            attempt     INTEGER DEFAULT 0,
            worker_id   INTEGER,
            status      TEXT DEFAULT 'pending',
            metrics     JSONB DEFAULT '{}',
            seed        BIGINT,
            elapsed_s   DOUBLE PRECISION,
            error_msg   TEXT,
            started_at  DOUBLE PRECISION,
            finished_at DOUBLE PRECISION
        );

        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'jobs_baseline_run_id_fkey'
            ) THEN
                ALTER TABLE jobs
                    ADD CONSTRAINT jobs_baseline_run_id_fkey
                    FOREIGN KEY (baseline_run_id) REFERENCES runs(id);
            END IF;
        END $$;

        CREATE TABLE IF NOT EXISTS episodes (
            id                 SERIAL PRIMARY KEY,
            run_id             TEXT REFERENCES runs(id),
            episode_index      INTEGER,
            success            BOOLEAN,
            reward_total       DOUBLE PRECISION,
            steps              INTEGER,
            termination_reason TEXT,
            metadata           JSONB DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS matches (
            id           TEXT PRIMARY KEY,
            env_name     TEXT NOT NULL,
            template_id  INTEGER REFERENCES templates(id),
            seed         BIGINT,
            mode         TEXT DEFAULT 'direct',
            status       TEXT DEFAULT 'pending',
            model_a      TEXT NOT NULL,
            model_b      TEXT NOT NULL,
            winner       TEXT,
            is_blind     BOOLEAN DEFAULT false,
            judge_config JSONB DEFAULT '{}',
            created_at   TIMESTAMPTZ DEFAULT now(),
            finished_at  TIMESTAMPTZ
        );

        CREATE TABLE IF NOT EXISTS match_runs (
            match_id TEXT REFERENCES matches(id),
            model    TEXT,
            run_id   TEXT REFERENCES runs(id),
            PRIMARY KEY (match_id, model)
        );

        CREATE TABLE IF NOT EXISTS elo_ratings (
            id         SERIAL PRIMARY KEY,
            model_name TEXT NOT NULL,
            env_name   TEXT NOT NULL,
            rating     DOUBLE PRECISION DEFAULT 1500,
            rd         DOUBLE PRECISION DEFAULT 350,
            volatility DOUBLE PRECISION DEFAULT 0.06,
            updated_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(model_name, env_name)
        );

        CREATE TABLE IF NOT EXISTS elo_history (
            id          SERIAL PRIMARY KEY,
            model_name  TEXT NOT NULL,
            env_name    TEXT NOT NULL,
            rating      DOUBLE PRECISION,
            rd          DOUBLE PRECISION,
            match_id    TEXT REFERENCES matches(id),
            recorded_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS hosts (
            id           SERIAL PRIMARY KEY,
            label        TEXT NOT NULL,
            host         TEXT NOT NULL,
            port         INTEGER DEFAULT 22,
            username     TEXT NOT NULL,
            password_enc TEXT NOT NULL,
            created_at   TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS remote_workers (
            id               SERIAL PRIMARY KEY,
            host_id          INTEGER REFERENCES hosts(id) ON DELETE CASCADE,
            worker_id        INTEGER NOT NULL,
            gpu_index        INTEGER NOT NULL,
            http_port        INTEGER NOT NULL,
            livestream_port  INTEGER NOT NULL,
            container_name   TEXT NOT NULL,
            status           TEXT DEFAULT 'deploying',
            deployed_at      TIMESTAMPTZ DEFAULT now(),
            stopped_at       TIMESTAMPTZ
        );

        CREATE TABLE IF NOT EXISTS logs (
            id      SERIAL PRIMARY KEY,
            job_id  TEXT REFERENCES jobs(id),
            line    TEXT,
            ts      DOUBLE PRECISION
        );
        """)
```

- [ ] **Step 1.5: Create `backend/db/queries/__init__.py`**

```python
# empty
```

- [ ] **Step 1.6: Create `backend/db/queries/jobs.py`**

```python
from __future__ import annotations
import json, time
import asyncpg

async def create_job(
    pool: asyncpg.Pool, *, id: str, name: str,
    template_id: int | None = None, model_name: str | None = None,
    submitter: str | None = None, policy_config: dict | None = None,
    policy_server_url: str = "", max_retries: int = 3,
    timeout_s: int = 3600, description: str | None = None,
) -> dict:
    now = time.time()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO jobs
               (id,name,template_id,model_name,submitter,policy_config,
                policy_server_url,max_retries,timeout_s,description,
                status,created_at,updated_at)
               VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'pending',$11,$11)
               RETURNING *""",
            id, name, template_id, model_name, submitter,
            json.dumps(policy_config or {}), policy_server_url,
            max_retries, timeout_s, description, now,
        )
    return _row(row)

async def get_job(pool: asyncpg.Pool, job_id: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM jobs WHERE id=$1", job_id)
    return _row(row) if row else None

async def list_jobs(
    pool: asyncpg.Pool, *,
    status: str | None = None,
    model_name: str | None = None,
    submitter: str | None = None,
) -> list[dict]:
    clauses, params = [], []
    for col, val in [("status", status), ("model_name", model_name),
                     ("submitter", submitter)]:
        if val is not None:
            params.append(val)
            clauses.append(f"{col}=${len(params)}")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM jobs {where} ORDER BY created_at DESC", *params
        )
    return [_row(r) for r in rows]

async def update_job_status(pool: asyncpg.Pool, job_id: str, status: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE jobs SET status=$1, updated_at=$2 WHERE id=$3",
            status, time.time(), job_id,
        )

async def increment_retry(pool: asyncpg.Pool, job_id: str) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE jobs SET retry_count=retry_count+1, updated_at=$1 "
            "WHERE id=$2 RETURNING retry_count",
            time.time(), job_id,
        )
    return row["retry_count"]

async def set_baseline_run(pool: asyncpg.Pool, job_id: str, run_id: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE jobs SET baseline_run_id=$1, updated_at=$2 WHERE id=$3",
            run_id, time.time(), job_id,
        )

async def append_log(pool: asyncpg.Pool, job_id: str, line: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO logs(job_id,line,ts) VALUES($1,$2,$3)",
            job_id, line, time.time(),
        )

async def get_logs(pool: asyncpg.Pool, job_id: str) -> list[str]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT line FROM logs WHERE job_id=$1 ORDER BY id", job_id
        )
    return [r["line"] for r in rows]

def _row(row) -> dict:
    d = dict(row)
    if isinstance(d.get("policy_config"), str):
        d["policy_config"] = json.loads(d["policy_config"])
    return d
```

- [ ] **Step 1.7: Create `backend/db/queries/runs.py`**

```python
from __future__ import annotations
import json, time
import asyncpg

async def create_run(
    pool: asyncpg.Pool, *, id: str, job_id: str,
    attempt: int = 0, seed: int | None = None,
) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO runs(id,job_id,attempt,seed,status)
               VALUES($1,$2,$3,$4,'pending') RETURNING *""",
            id, job_id, attempt, seed,
        )
    return _row(row)

async def get_run(pool: asyncpg.Pool, run_id: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM runs WHERE id=$1", run_id)
    return _row(row) if row else None

async def list_runs_for_job(pool: asyncpg.Pool, job_id: str) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM runs WHERE job_id=$1 ORDER BY attempt", job_id
        )
    return [_row(r) for r in rows]

async def latest_run_for_job(pool: asyncpg.Pool, job_id: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM runs WHERE job_id=$1 ORDER BY attempt DESC LIMIT 1",
            job_id,
        )
    return _row(row) if row else None

async def update_run(
    pool: asyncpg.Pool, run_id: str, *,
    status: str | None = None, metrics: dict | None = None,
    elapsed_s: float | None = None, error_msg: str | None = None,
    worker_id: int | None = None, started_at: float | None = None,
    finished_at: float | None = None,
) -> None:
    sets, params = [], [run_id]
    for col, val in [("status", status), ("elapsed_s", elapsed_s),
                     ("error_msg", error_msg), ("worker_id", worker_id),
                     ("started_at", started_at), ("finished_at", finished_at)]:
        if val is not None:
            params.append(val)
            sets.append(f"{col}=${len(params)}")
    if metrics is not None:
        params.append(json.dumps(metrics))
        sets.append(f"metrics=${len(params)}")
    if not sets:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE runs SET {','.join(sets)} WHERE id=$1", *params
        )

def _row(row) -> dict:
    d = dict(row)
    if isinstance(d.get("metrics"), str):
        d["metrics"] = json.loads(d["metrics"])
    return d
```

- [ ] **Step 1.8: Create `backend/db/queries/episodes.py`**

```python
from __future__ import annotations
import json
import asyncpg

async def insert_episodes(
    pool: asyncpg.Pool, run_id: str, episodes: list[dict]
) -> None:
    """episodes: list of dicts with keys matching episodes table columns."""
    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO episodes
               (run_id,episode_index,success,reward_total,steps,
                termination_reason,metadata)
               VALUES($1,$2,$3,$4,$5,$6,$7)""",
            [
                (
                    run_id,
                    ep.get("episode_index", i),
                    ep.get("success", False),
                    ep.get("reward_total", 0.0),
                    ep.get("steps", 0),
                    ep.get("termination_reason", ""),
                    json.dumps(ep.get("metadata", {})),
                )
                for i, ep in enumerate(episodes)
            ],
        )

async def get_episodes(pool: asyncpg.Pool, run_id: str) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM episodes WHERE run_id=$1 ORDER BY episode_index",
            run_id,
        )
    return [dict(r) for r in rows]
```

- [ ] **Step 1.9: Create `backend/db/queries/templates.py`**

```python
from __future__ import annotations
import asyncpg

async def create_template(
    pool: asyncpg.Pool, *, name: str, version: str = "1.0",
    runner_type: str, config_yaml: str, description: str | None = None,
) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO templates(name,version,runner_type,config_yaml,description)
               VALUES($1,$2,$3,$4,$5) RETURNING *""",
            name, version, runner_type, config_yaml, description,
        )
    return dict(row)

async def get_template(pool: asyncpg.Pool, template_id: int) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM templates WHERE id=$1", template_id
        )
    return dict(row) if row else None

async def list_templates(pool: asyncpg.Pool) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM templates ORDER BY name, version"
        )
    return [dict(r) for r in rows]

async def delete_template(pool: asyncpg.Pool, template_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM templates WHERE id=$1", template_id)
```

- [ ] **Step 1.10: Write and run DB query tests**

```python
# tests/db/test_jobs_queries.py
import asyncio, os, pytest, asyncpg, uuid
import sys; sys.path.insert(0, ".")
from backend.db.schema import create_tables
from backend.db.queries import jobs as jq, runs as rq

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

@pytest.mark.asyncio
async def test_create_and_get_job(pool):
    jid = uuid.uuid4().hex[:8]
    job = await jq.create_job(pool, id=jid, name="test_job")
    assert job["id"] == jid
    assert job["status"] == "pending"
    assert job["retry_count"] == 0
    fetched = await jq.get_job(pool, jid)
    assert fetched["id"] == jid

@pytest.mark.asyncio
async def test_update_job_status(pool):
    jid = uuid.uuid4().hex[:8]
    await jq.create_job(pool, id=jid, name="status_test")
    await jq.update_job_status(pool, jid, "running")
    job = await jq.get_job(pool, jid)
    assert job["status"] == "running"

@pytest.mark.asyncio
async def test_increment_retry(pool):
    jid = uuid.uuid4().hex[:8]
    await jq.create_job(pool, id=jid, name="retry_test")
    count = await jq.increment_retry(pool, jid)
    assert count == 1
    count = await jq.increment_retry(pool, jid)
    assert count == 2

@pytest.mark.asyncio
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
```

Run:
```bash
TEST_DATABASE_URL="postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test" \
  pytest tests/db/ -v
```
Expected: all PASS

- [ ] **Step 1.11: Commit**

```bash
git add backend/db/ tests/db/ tests/conftest.py
git commit -m "feat: db schema migration + query helpers (Phase 1, Task 1)"
```

---

## Task 2: Runner Plugin Layer

**Files:**
- Create: `backend/runners/__init__.py`
- Create: `backend/runners/base.py`
- Create: `backend/runners/registry.py`
- Create: `backend/runners/isaaclab_runner.py`
- Create: `backend/runners/remote_policy.py`
- Create: `tests/runners/test_base.py`
- Create: `tests/runners/test_registry.py`
- Create: `tests/runners/test_remote_policy.py`

**Interfaces:**
- Consumes: nothing from Task 1 (fully independent)
- Produces:
  - `BaseRunner` ABC with `async def run(self, config: dict, seed: int) -> RunResult`
  - `RunResult(metrics: dict, episodes: list[EpisodeResult], elapsed_s: float, seed: int, raw_output: str = "")`
  - `EpisodeResult(index: int, success: bool, reward_total: float, steps: int, termination_reason: str, metadata: dict = {})`
  - `get_runner(runner_type: str, config: dict) -> BaseRunner`
  - `register_runner(name: str, cls: type[BaseRunner]) -> None`
  - `IsaacLabRunner(actor_name: str, namespace: str = "robot-eval")` — wraps Ray Actor
  - `RemotePolicyRunner(endpoint: str)` — HTTP policy server

- [ ] **Step 2.1: Write base runner tests**

```python
# tests/runners/test_base.py
import pytest
from dataclasses import asdict
import sys; sys.path.insert(0, ".")
from backend.runners.base import BaseRunner, RunResult, EpisodeResult

class ConcreteRunner(BaseRunner):
    async def run(self, config: dict, seed: int) -> RunResult:
        return RunResult(
            metrics={"success_rate": 1.0},
            episodes=[EpisodeResult(index=0, success=True, reward_total=5.0,
                                    steps=10, termination_reason="success")],
            elapsed_s=1.0, seed=seed,
        )
    def health_check(self) -> bool:
        return True

@pytest.mark.asyncio
async def test_runner_returns_run_result():
    runner = ConcreteRunner()
    result = await runner.run({}, seed=42)
    assert isinstance(result, RunResult)
    assert result.metrics["success_rate"] == 1.0
    assert result.seed == 42
    assert len(result.episodes) == 1
    assert result.episodes[0].success is True

def test_episode_result_to_dict():
    ep = EpisodeResult(index=0, success=True, reward_total=3.0,
                       steps=5, termination_reason="success")
    d = asdict(ep)
    assert d["success"] is True
    assert d["termination_reason"] == "success"

def test_abstract_runner_cannot_instantiate():
    with pytest.raises(TypeError):
        BaseRunner()
```

- [ ] **Step 2.2: Run test — expect FAIL**

```bash
pytest tests/runners/test_base.py -v
```
Expected: `ModuleNotFoundError: No module named 'backend.runners'`

- [ ] **Step 2.3: Create `backend/runners/__init__.py`**

```python
# empty
```

- [ ] **Step 2.4: Create `backend/runners/base.py`**

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class EpisodeResult:
    index:              int
    success:            bool
    reward_total:       float
    steps:              int
    termination_reason: str
    metadata:           dict = field(default_factory=dict)

@dataclass
class RunResult:
    metrics:    dict
    episodes:   list[EpisodeResult]
    elapsed_s:  float
    seed:       int
    raw_output: str = ""

class BaseRunner(ABC):
    @abstractmethod
    async def run(self, config: dict, seed: int) -> RunResult: ...

    @abstractmethod
    def health_check(self) -> bool: ...
```

- [ ] **Step 2.5: Run base test — expect PASS**

```bash
pytest tests/runners/test_base.py -v
```
Expected: 3 tests PASS

- [ ] **Step 2.6: Write registry test**

```python
# tests/runners/test_registry.py
import pytest
import sys; sys.path.insert(0, ".")
from backend.runners.base import BaseRunner, RunResult, EpisodeResult
from backend.runners.registry import get_runner, register_runner

class DummyRunner(BaseRunner):
    def __init__(self, config: dict): self.config = config
    async def run(self, config, seed): 
        return RunResult(metrics={}, episodes=[], elapsed_s=0, seed=seed)
    def health_check(self): return True

def test_register_and_get_custom_runner():
    register_runner("dummy", DummyRunner)
    runner = get_runner("dummy", {"foo": "bar"})
    assert isinstance(runner, DummyRunner)
    assert runner.config == {"foo": "bar"}

def test_get_unknown_runner_raises():
    with pytest.raises(KeyError, match="no_such_runner"):
        get_runner("no_such_runner", {})

def test_get_isaaclab_runner():
    runner = get_runner("isaaclab", {"actor_name": "arena-worker-0"})
    from backend.runners.isaaclab_runner import IsaacLabRunner
    assert isinstance(runner, IsaacLabRunner)

def test_get_remote_policy_runner():
    runner = get_runner("remote_policy", {"endpoint": "http://localhost:7860"})
    from backend.runners.remote_policy import RemotePolicyRunner
    assert isinstance(runner, RemotePolicyRunner)
```

- [ ] **Step 2.7: Create `backend/runners/registry.py`**

```python
from __future__ import annotations
from backend.runners.base import BaseRunner

def _lazy_isaaclab():
    from backend.runners.isaaclab_runner import IsaacLabRunner
    return IsaacLabRunner

def _lazy_remote_policy():
    from backend.runners.remote_policy import RemotePolicyRunner
    return RemotePolicyRunner

_REGISTRY: dict[str, type[BaseRunner]] = {}
_LAZY: dict[str, callable] = {
    "isaaclab":      _lazy_isaaclab,
    "remote_policy": _lazy_remote_policy,
}

def get_runner(runner_type: str, config: dict) -> BaseRunner:
    if runner_type not in _REGISTRY:
        if runner_type in _LAZY:
            _REGISTRY[runner_type] = _LAZY[runner_type]()
        else:
            raise KeyError(f"Unknown runner: {runner_type}. "
                           f"Available: {list(_LAZY)+list(_REGISTRY)}")
    return _REGISTRY[runner_type](config)

def register_runner(name: str, cls: type[BaseRunner]) -> None:
    _REGISTRY[name] = cls
```

- [ ] **Step 2.8: Create `backend/runners/isaaclab_runner.py`**

```python
from __future__ import annotations
import time, random, logging
from dataclasses import asdict
from backend.runners.base import BaseRunner, RunResult, EpisodeResult

logger = logging.getLogger(__name__)

class IsaacLabRunner(BaseRunner):
    """Dispatches a run_job call to a Ray Actor (IsaacLabArenaActor)."""

    def __init__(self, config: dict):
        self.actor_name = config.get("actor_name", "arena-worker-0")
        self.namespace  = config.get("namespace", "robot-eval")
        self._timeout   = config.get("timeout_s", 3600)

    def health_check(self) -> bool:
        try:
            import ray
            actor = ray.get_actor(self.actor_name, namespace=self.namespace)
            status = ray.get(actor.status.remote(), timeout=3)
            return not status.get("busy", True)
        except Exception:
            return False

    async def run(self, config: dict, seed: int) -> RunResult:
        import ray, asyncio
        t0 = time.time()

        actor = ray.get_actor(self.actor_name, namespace=self.namespace)
        job_dict = {**config, "seed": seed}
        ref = actor.run_job.remote(job_dict)

        loop = asyncio.get_event_loop()
        raw: dict = await loop.run_in_executor(None, ray.get, ref)

        elapsed = time.time() - t0
        episodes = _extract_episodes(raw)
        metrics  = {k: v for k, v in raw.items() if k != "episodes"}

        return RunResult(
            metrics=metrics,
            episodes=episodes,
            elapsed_s=round(elapsed, 3),
            seed=seed,
            raw_output=str(raw),
        )

def _extract_episodes(raw: dict) -> list[EpisodeResult]:
    """Convert actor-returned episode list (if any) to EpisodeResult list."""
    eps = raw.get("episodes", [])
    if not eps:
        # Build synthetic episodes from aggregate metrics
        n = raw.get("num_episodes") or raw.get("total_episodes", 0)
        sr = raw.get("success_rate", 0.0)
        return [
            EpisodeResult(
                index=i, success=(i < int(n * sr)),
                reward_total=0.0, steps=0,
                termination_reason="success" if i < int(n * sr) else "timeout",
            )
            for i in range(n)
        ]
    return [
        EpisodeResult(
            index=ep.get("episode_index", i),
            success=ep.get("success", False),
            reward_total=ep.get("reward_total", 0.0),
            steps=ep.get("steps", 0),
            termination_reason=ep.get("termination_reason", ""),
            metadata=ep.get("metadata", {}),
        )
        for i, ep in enumerate(eps)
    ]
```

- [ ] **Step 2.9: Create `backend/runners/remote_policy.py`**

```python
from __future__ import annotations
import time, logging
import httpx
from backend.runners.base import BaseRunner, RunResult, EpisodeResult

logger = logging.getLogger(__name__)

class RemotePolicyRunner(BaseRunner):
    """Runs eval by sending observations to an external HTTP policy server."""

    def __init__(self, config: dict):
        self.endpoint = config["endpoint"].rstrip("/")
        self.timeout  = config.get("timeout_s", 30)

    def health_check(self) -> bool:
        try:
            r = httpx.get(f"{self.endpoint}/info", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    async def run(self, config: dict, seed: int) -> RunResult:
        # RemotePolicyRunner drives the env from inside the actor;
        # here we just forward the full job_dict to an actor that supports
        # policy_server_url, or raise NotImplementedError for headless use.
        raise NotImplementedError(
            "RemotePolicyRunner must be used via IsaacLabRunner with "
            "policy_server_url set in config"
        )
```

- [ ] **Step 2.10: Write remote policy runner test**

```python
# tests/runners/test_remote_policy.py
import pytest
import sys; sys.path.insert(0, ".")
from backend.runners.remote_policy import RemotePolicyRunner

def test_instantiation():
    r = RemotePolicyRunner({"endpoint": "http://localhost:7860"})
    assert r.endpoint == "http://localhost:7860"

def test_run_raises_not_implemented():
    r = RemotePolicyRunner({"endpoint": "http://localhost:7860"})
    import asyncio
    with pytest.raises(NotImplementedError):
        asyncio.get_event_loop().run_until_complete(r.run({}, seed=0))
```

- [ ] **Step 2.11: Run all runner tests — expect PASS**

```bash
pytest tests/runners/ -v
```
Expected: 6+ tests PASS

- [ ] **Step 2.12: Commit**

```bash
git add backend/runners/ tests/runners/
git commit -m "feat: runner plugin layer — BaseRunner, RunResult, registry (Phase 1, Task 2)"
```

---

## Task 3: Job Engine + Scheduler

**Files:**
- Create: `backend/engines/__init__.py`
- Create: `backend/engines/job_engine.py`
- Create: `backend/engines/scheduler.py`
- Create: `tests/engines/test_job_engine.py`
- Create: `tests/engines/test_scheduler.py`

**Interfaces:**
- Consumes:
  - `db.pool` from Task 1
  - `jobs.create_job`, `jobs.update_job_status`, `jobs.increment_retry`, `jobs.get_job` from Task 1
  - `runs.create_run`, `runs.update_run`, `runs.latest_run_for_job` from Task 1
  - `episodes.insert_episodes` from Task 1
  - `BaseRunner`, `RunResult` from Task 2
  - `get_runner` from Task 2
- Produces:
  - `JobEngine` class with:
    - `async def create_job(name, model_name, submitter, policy_config, policy_server_url, template_id, max_retries, timeout_s, description) -> dict`
    - `async def cancel_job(job_id: str) -> None`
    - `async def reproduce_job(job_id: str) -> dict` — clone with same config+seed
    - `async def get_regression(job_id: str) -> dict`
  - `JobScheduler` class (singleton) with:
    - `async def start() -> None` — starts background dispatch loop
    - `async def enqueue(job_id: str) -> None`
    - `async def notify_free(actor_name: str) -> None`

- [ ] **Step 3.1: Write job engine tests**

```python
# tests/engines/test_job_engine.py
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

@pytest.mark.asyncio
async def test_create_job_persisted(pool):
    engine = JobEngine(pool, scheduler=MagicMock(enqueue=AsyncMock()))
    job = await engine.create_job(name="test", model_name="pi0",
                                   submitter="alice", policy_config={},
                                   policy_server_url="", max_retries=2)
    assert job["status"] == "pending"
    assert job["model_name"] == "pi0"
    persisted = await jq.get_job(pool, job["id"])
    assert persisted is not None

@pytest.mark.asyncio
async def test_cancel_job(pool):
    engine = JobEngine(pool, scheduler=MagicMock(enqueue=AsyncMock()))
    job = await engine.create_job(name="cancel_me", model_name="x",
                                   submitter="", policy_config={},
                                   policy_server_url="")
    await engine.cancel_job(job["id"])
    updated = await jq.get_job(pool, job["id"])
    assert updated["status"] == "cancelled"

@pytest.mark.asyncio
async def test_reproduce_job(pool):
    engine = JobEngine(pool, scheduler=MagicMock(enqueue=AsyncMock()))
    original = await engine.create_job(name="orig", model_name="pi0",
                                        submitter="bob", policy_config={"k": 1},
                                        policy_server_url="")
    clone = await engine.reproduce_job(original["id"])
    assert clone["id"] != original["id"]
    assert clone["model_name"] == original["model_name"]
    assert clone["policy_config"] == original["policy_config"]
```

- [ ] **Step 3.2: Run test — expect FAIL**

```bash
TEST_DATABASE_URL="postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test" \
  pytest tests/engines/test_job_engine.py -v
```
Expected: `ModuleNotFoundError: No module named 'backend.engines'`

- [ ] **Step 3.3: Create `backend/engines/__init__.py`**

```python
# empty
```

- [ ] **Step 3.4: Create `backend/engines/job_engine.py`**

```python
from __future__ import annotations
import random, time, uuid, logging
import asyncpg
from backend.db.queries import jobs as jq, runs as rq, episodes as eq

logger = logging.getLogger(__name__)

class JobEngine:
    def __init__(self, pool: asyncpg.Pool, scheduler):
        self._pool      = pool
        self._scheduler = scheduler  # JobScheduler instance

    async def create_job(
        self, *, name: str, model_name: str | None = None,
        submitter: str | None = None, policy_config: dict | None = None,
        policy_server_url: str = "", template_id: int | None = None,
        max_retries: int = 3, timeout_s: int = 3600,
        description: str | None = None,
    ) -> dict:
        job_id = uuid.uuid4().hex[:8]
        job = await jq.create_job(
            self._pool, id=job_id, name=name, template_id=template_id,
            model_name=model_name, submitter=submitter,
            policy_config=policy_config or {}, policy_server_url=policy_server_url,
            max_retries=max_retries, timeout_s=timeout_s, description=description,
        )
        await self._scheduler.enqueue(job_id)
        logger.info("job.created", extra={"job_id": job_id, "model": model_name})
        return job

    async def cancel_job(self, job_id: str) -> None:
        await jq.update_job_status(self._pool, job_id, "cancelled")
        logger.info("job.cancelled", extra={"job_id": job_id})

    async def reproduce_job(self, job_id: str) -> dict:
        original = await jq.get_job(self._pool, job_id)
        if not original:
            raise ValueError(f"Job {job_id} not found")
        clone_id = uuid.uuid4().hex[:8]
        clone = await jq.create_job(
            self._pool, id=clone_id,
            name=f"{original['name']}_repro",
            template_id=original.get("template_id"),
            model_name=original.get("model_name"),
            submitter=original.get("submitter"),
            policy_config=original.get("policy_config", {}),
            policy_server_url=original.get("policy_server_url", ""),
            max_retries=original.get("max_retries", 3),
            timeout_s=original.get("timeout_s", 3600),
            description=f"Reproduced from {job_id}",
        )
        await self._scheduler.enqueue(clone_id)
        return clone

    async def get_regression(self, job_id: str) -> dict:
        job = await jq.get_job(self._pool, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        baseline_run_id = job.get("baseline_run_id")
        if not baseline_run_id:
            return {"error": "no baseline set for this job"}
        current = await rq.latest_run_for_job(self._pool, job_id)
        baseline = await rq.get_run(self._pool, baseline_run_id)
        if not current or not baseline:
            return {"error": "missing run data"}
        return _compute_regression(baseline, current)

def _compute_regression(baseline: dict, current: dict) -> dict:
    b_metrics = baseline.get("metrics", {})
    c_metrics = current.get("metrics", {})
    deltas = []
    for key in b_metrics:
        if key in c_metrics and isinstance(b_metrics[key], (int, float)):
            bv = float(b_metrics[key])
            cv = float(c_metrics[key])
            delta = cv - bv
            deltas.append({
                "metric":    key,
                "baseline":  bv,
                "current":   cv,
                "delta":     round(delta, 4),
                "delta_pct": round((delta / bv * 100) if bv != 0 else 0, 2),
                "significant": abs(delta) > 0.02,  # simple threshold; Phase 3 adds bootstrap CI
            })
    return {
        "baseline_run_id": baseline["id"],
        "current_run_id":  current["id"],
        "deltas": deltas,
    }
```

- [ ] **Step 3.5: Create `backend/engines/scheduler.py`**

```python
from __future__ import annotations
import asyncio, random, time, uuid, logging
import asyncpg
from backend.db.queries import jobs as jq, runs as rq, episodes as eq
from backend.runners.registry import get_runner

logger = logging.getLogger(__name__)

class JobScheduler:
    """
    Queue-based job dispatcher.
    - _job_queue: job_ids waiting for a free actor
    - _free_actors: actor names that just became free
    """

    def __init__(self, pool: asyncpg.Pool, workers_meta: list[dict]):
        self._pool        = pool
        self._workers     = workers_meta   # [{"worker_id": 0, "actor_name": "arena-worker-0", ...}]
        self._job_queue:  asyncio.Queue[str] = asyncio.Queue()
        self._free_actors: asyncio.Queue[str] = asyncio.Queue()
        self._running     = False

    async def start(self) -> None:
        self._running = True
        # Seed free actor queue with all known workers
        for w in self._workers:
            await self._free_actors.put(w["actor_name"])
        asyncio.create_task(self._dispatch_loop())
        logger.info("scheduler.started", extra={"workers": len(self._workers)})

    async def enqueue(self, job_id: str) -> None:
        await self._job_queue.put(job_id)
        logger.info("scheduler.enqueued", extra={"job_id": job_id})

    async def notify_free(self, actor_name: str) -> None:
        await self._free_actors.put(actor_name)

    async def _dispatch_loop(self) -> None:
        while self._running:
            job_id     = await self._job_queue.get()
            actor_name = await self._free_actors.get()
            asyncio.create_task(self._run_job(job_id, actor_name))

    async def _run_job(self, job_id: str, actor_name: str) -> None:
        job = await jq.get_job(self._pool, job_id)
        if not job or job["status"] == "cancelled":
            await self._free_actors.put(actor_name)
            return

        run_id = uuid.uuid4().hex[:8]
        attempt = job.get("retry_count", 0)
        seed = random.randint(0, 2**31)

        await jq.update_job_status(self._pool, job_id, "running")
        run = await rq.create_run(self._pool, id=run_id, job_id=job_id,
                                   attempt=attempt, seed=seed)
        await rq.update_run(self._pool, run_id, status="running",
                             worker_id=_actor_worker_id(actor_name),
                             started_at=time.time())
        await jq.append_log(self._pool, job_id, f"分配 {actor_name} (attempt {attempt})")

        try:
            runner = _build_runner(job, actor_name)
            result = await asyncio.wait_for(
                runner.run(job, seed=seed),
                timeout=job.get("timeout_s", 3600),
            )
            t_end = time.time()
            await rq.update_run(
                self._pool, run_id, status="done",
                metrics=result.metrics,
                elapsed_s=result.elapsed_s,
                finished_at=t_end,
            )
            if result.episodes:
                await eq.insert_episodes(
                    self._pool, run_id,
                    [_ep_to_dict(ep) for ep in result.episodes],
                )
            await jq.update_job_status(self._pool, job_id, "done")
            await jq.append_log(self._pool, job_id,
                                  f"完成 metrics={result.metrics}")
            logger.info("job.done", extra={"job_id": job_id, "run_id": run_id})

        except asyncio.TimeoutError:
            await _handle_failure(self._pool, job_id, run_id,
                                   "timeout", job, self._job_queue)
        except Exception as exc:
            await _handle_failure(self._pool, job_id, run_id,
                                   str(exc), job, self._job_queue)
        finally:
            await self._free_actors.put(actor_name)

def _build_runner(job: dict, actor_name: str):
    """Build the appropriate runner for this job."""
    policy_url = job.get("policy_server_url", "")
    if policy_url:
        config = {
            "actor_name": actor_name,
            "policy_server_url": policy_url,
            **(job.get("policy_config") or {}),
            "arena_env_args": job.get("arena_env_args", {}),
        }
    else:
        config = {
            "actor_name": actor_name,
            **(job.get("policy_config") or {}),
            "arena_env_args": job.get("arena_env_args", {}),
            "num_envs": job.get("num_envs", 1),
            "num_episodes": job.get("num_episodes", 10),
            "num_steps": job.get("num_steps"),
            "policy_type": job.get("policy_type", "zero_action"),
        }
    return get_runner("isaaclab", config)

async def _handle_failure(pool, job_id, run_id, error, job, queue):
    await rq.update_run(pool, run_id, status="failed",
                         error_msg=error, finished_at=time.time())
    retry_count = await jq.increment_retry(pool, job_id)
    if retry_count <= job.get("max_retries", 3):
        backoff = 2 ** retry_count
        await jq.update_job_status(pool, job_id, "retry_pending")
        await jq.append_log(pool, job_id,
                              f"失败，{backoff}s 后重试 (attempt {retry_count})")
        await asyncio.sleep(backoff)
        await queue.put(job_id)
    else:
        await jq.update_job_status(pool, job_id, "failed_final")
        await jq.append_log(pool, job_id, f"ERROR: {error}")

def _actor_worker_id(actor_name: str) -> int:
    try: return int(actor_name.rsplit("-", 1)[-1])
    except ValueError: return 0

def _ep_to_dict(ep) -> dict:
    from dataclasses import asdict
    return asdict(ep)
```

- [ ] **Step 3.6: Write scheduler test**

```python
# tests/engines/test_scheduler.py
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

@pytest.mark.asyncio
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
        await asyncio.sleep(0.5)  # let dispatch loop run

        job = await jq.get_job(pool, jid)
        assert job["status"] in ("done", "running")
```

- [ ] **Step 3.7: Run engine tests**

```bash
TEST_DATABASE_URL="postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test" \
  pytest tests/engines/ -v
```
Expected: all PASS

- [ ] **Step 3.8: Commit**

```bash
git add backend/engines/ tests/engines/
git commit -m "feat: job engine + async scheduler with retry/cancel/reproduce (Phase 1, Task 3)"
```

---

## Task 4: API Restructure

**Files:**
- Create: `backend/api/__init__.py`
- Create: `backend/api/jobs.py`
- Create: `backend/api/runs.py`
- Create: `backend/api/workers.py`
- Create: `backend/api/templates.py`
- Modify: `backend/main.py` — replace all inline route handlers with router includes
- Create: `tests/api/test_jobs_api.py`

**Interfaces:**
- Consumes:
  - `db.db` singleton from Task 1
  - `JobEngine` from Task 3
  - `JobScheduler` from Task 3
  - `jq`, `rq` query helpers from Task 1
- Produces:
  - `POST /api/jobs` → `{"id": ..., "status": "pending", ...}`
  - `GET /api/jobs` → `[{...}, ...]`
  - `GET /api/jobs/{id}` → job + latest run
  - `DELETE /api/jobs/{id}` → `{"ok": true}`
  - `POST /api/jobs/{id}/reproduce` → cloned job
  - `GET /api/jobs/{id}/regression` → delta report
  - `GET /api/jobs/{id}/logs` → SSE stream
  - `PUT /api/runs/{id}/set-baseline` → `{"ok": true}`
  - `GET /api/runs/{id}` → run detail + episodes
  - `GET /api/workers` → worker list
  - `GET /api/templates` → template list (stub, returns `[]`)
  - `GET /api/health` → `{"status": "ok"}`

- [ ] **Step 4.1: Create `backend/api/__init__.py`**

```python
# empty
```

- [ ] **Step 4.2: Create `backend/api/jobs.py`**

```python
from __future__ import annotations
import asyncio, json, time
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from backend.db import db
from backend.db.queries import jobs as jq, runs as rq

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

class SubmitRequest(BaseModel):
    name:             str         = "eval_job"
    model_name:       str         = ""
    submitter:        str         = ""
    description:      str         = ""
    template_id:      int | None  = None
    arena_env_args:   dict[str, Any] = {}
    num_envs:         int         = 1
    num_episodes:     int | None  = 10
    num_steps:        int | None  = None
    policy_type:      str         = "zero_action"
    policy_config:    dict        = {}
    policy_server_url: str        = ""
    max_retries:      int         = 3
    timeout_s:        int         = 3600

@router.post("")
async def submit_job(req: SubmitRequest):
    from backend.engines.job_engine import job_engine
    config = req.model_dump()
    job = await job_engine.create_job(
        name=req.name, model_name=req.model_name or None,
        submitter=req.submitter or None, policy_config=req.policy_config,
        policy_server_url=req.policy_server_url,
        template_id=req.template_id, max_retries=req.max_retries,
        timeout_s=req.timeout_s, description=req.description or None,
    )
    # Stash full config as first log entry for reproduce fidelity
    await jq.append_log(db.pool, job["id"], json.dumps(config))
    return job

@router.get("")
async def list_jobs(status: str | None = None,
                    model_name: str | None = None,
                    submitter: str | None = None):
    return await jq.list_jobs(db.pool, status=status,
                               model_name=model_name, submitter=submitter)

@router.get("/{job_id}")
async def get_job(job_id: str):
    job = await jq.get_job(db.pool, job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    run = await rq.latest_run_for_job(db.pool, job_id)
    return {**job, "latest_run": run}

@router.delete("/{job_id}")
async def cancel_job(job_id: str):
    from backend.engines.job_engine import job_engine
    await job_engine.cancel_job(job_id)
    return {"ok": True}

@router.post("/{job_id}/reproduce")
async def reproduce_job(job_id: str):
    from backend.engines.job_engine import job_engine
    clone = await job_engine.reproduce_job(job_id)
    return clone

@router.get("/{job_id}/regression")
async def get_regression(job_id: str):
    from backend.engines.job_engine import job_engine
    return await job_engine.get_regression(job_id)

@router.get("/{job_id}/logs")
async def stream_logs(job_id: str):
    async def generator():
        sent = 0
        while True:
            lines = await jq.get_logs(db.pool, job_id)
            for line in lines[sent:]:
                yield f"data: {json.dumps(line)}\n\n"
                sent += 1
            job = await jq.get_job(db.pool, job_id)
            if job and job["status"] in ("done", "failed_final", "cancelled"):
                yield "data: __END__\n\n"
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
```

- [ ] **Step 4.3: Create `backend/api/runs.py`**

```python
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from backend.db import db
from backend.db.queries import runs as rq, jobs as jq, episodes as eq

router = APIRouter(prefix="/api/runs", tags=["runs"])

@router.get("/{run_id}")
async def get_run(run_id: str):
    run = await rq.get_run(db.pool, run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    episodes = await eq.get_episodes(db.pool, run_id)
    return {**run, "episodes": episodes}

@router.put("/{run_id}/set-baseline")
async def set_baseline(run_id: str):
    run = await rq.get_run(db.pool, run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    await jq.set_baseline_run(db.pool, run["job_id"], run_id)
    return {"ok": True, "run_id": run_id, "job_id": run["job_id"]}
```

- [ ] **Step 4.4: Create `backend/api/workers.py`**

```python
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
import httpx
from backend.db import db
from backend.db.queries.jobs import append_log

router = APIRouter(prefix="/api/workers", tags=["workers"])

@router.get("")
async def get_workers():
    import ray
    from backend.db.queries import jobs as jq
    workers = await db.list_remote_workers(status="running")
    results = []
    for w in workers:
        actor_name = f"arena-worker-{w['worker_id']}"
        host_row = await db.get_host(w["host_id"])
        try:
            actor  = ray.get_actor(actor_name, namespace="robot-eval")
            status = ray.get(actor.status.remote(), timeout=3)
            online = True
        except Exception:
            status = {}
            online = False
        results.append({
            "id":              w["worker_id"],
            "host":            host_row["host"] if host_row else "unknown",
            "http_port":       w["http_port"],
            "livestream_port": w["livestream_port"],
            "actor":           actor_name,
            "online":          online,
            "busy":            status.get("busy", False),
            "status":          status.get("status", ""),
        })
    return results

@router.get("/{worker_id}/stream")
async def worker_stream_info(worker_id: int):
    w = await db.get_remote_worker(worker_id)
    if not w:
        raise HTTPException(404)
    host_row = await db.get_host(w["host_id"])
    host = host_row["host"] if host_row else "unknown"
    return {
        "worker_id":       worker_id,
        "http_port":       w["http_port"],
        "livestream_port": w["livestream_port"],
        "host":            host,
        "signaling_url":   f"ws://{host}:{w['livestream_port']}",
    }
```

- [ ] **Step 4.5: Create `backend/api/templates.py`**

```python
from __future__ import annotations
from fastapi import APIRouter
from backend.db import db
from backend.db.queries import templates as tq

router = APIRouter(prefix="/api/templates", tags=["templates"])

@router.get("")
async def list_templates():
    return await tq.list_templates(db.pool)
```

- [ ] **Step 4.6: Rewrite `backend/main.py`**

```python
"""Robot Eval Platform v2 — FastAPI entry point."""
from __future__ import annotations
import asyncio, logging, os
from contextlib import asynccontextmanager
from pathlib import Path

import ray
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.db import db, init_db
from backend.db.schema import create_tables
from backend.base_actor import load_actor_class

logger = logging.getLogger(__name__)

_DATABASE_URL    = os.environ.get("DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval")
_RAY_ADDRESS     = os.environ.get("RAY_ADDRESS", "ray://127.0.0.1:10001")
_ACTOR_MODULE    = os.environ.get("EVAL_ACTOR_MODULE", "arena_actor")
_ACTOR_CLASS     = os.environ.get("EVAL_ACTOR_CLASS",  "IsaacLabArenaActor")
_STATIC          = Path(__file__).parent.parent / "frontend" / "dist"

_ISAAC_SIM = "/workspaces/isaaclab_arena/submodules/IsaacLab/_isaac_sim"
_ISAAC_LD  = ":".join([
    _ISAAC_SIM, f"{_ISAAC_SIM}/kit", f"{_ISAAC_SIM}/kit/kernel/plugins",
    f"{_ISAAC_SIM}/kit/libs/iray", f"{_ISAAC_SIM}/kit/plugins",
    f"{_ISAAC_SIM}/kit/plugins/bindings-python",
    f"{_ISAAC_SIM}/kit/plugins/carb_gfx", f"{_ISAAC_SIM}/kit/plugins/rtx",
    f"{_ISAAC_SIM}/kit/plugins/gpu.foundation",
])

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(_DATABASE_URL)

    # Init Ray
    try:
        ray.init(address=_RAY_ADDRESS, ignore_reinit_error=True,
                 log_to_driver=False,
                 runtime_env={"working_dir": "/app/backend"})
        logger.info("ray.connected", extra={"address": _RAY_ADDRESS})
    except Exception as exc:
        logger.warning("ray.unavailable", extra={"error": str(exc)})

    # Start scheduler
    from backend.engines.scheduler import JobScheduler
    from backend.engines.job_engine import JobEngine

    workers = await _get_workers_meta()
    scheduler = JobScheduler(db.pool, workers)
    await scheduler.start()

    # Wire singletons so routers can import them
    import backend.engines.job_engine as je_mod
    je_mod.job_engine = JobEngine(db.pool, scheduler)

    # Create Ray actors for running workers
    asyncio.create_task(_create_actors())

    yield
    await db.close()


async def _get_workers_meta() -> list[dict]:
    try:
        rows = await db.list_remote_workers(status="running")
        return [{"worker_id": r["worker_id"],
                 "actor_name": f"arena-worker-{r['worker_id']}"}
                for r in rows]
    except Exception:
        # Fallback for first-run before any workers are registered
        return [{"worker_id": 0, "actor_name": "arena-worker-0"}]


async def _create_actors():
    ActorClass = load_actor_class(_ACTOR_MODULE, _ACTOR_CLASS)
    runtime_env = {"env_vars": {
        "LD_LIBRARY_PATH": _ISAAC_LD,
        "CARB_APP_PATH":   f"{_ISAAC_SIM}/kit",
        "ISAAC_PATH":      _ISAAC_SIM,
        "EXP_PATH":        f"{_ISAAC_SIM}/apps",
        "RESOURCE_NAME":   "IsaacSim",
        "LD_PRELOAD":      f"{_ISAAC_SIM}/kit/libcarb.so",
    }}
    try:
        workers = await _get_workers_meta()
    except Exception:
        workers = [{"worker_id": 0, "actor_name": "arena-worker-0"}]

    for w in workers:
        name = w["actor_name"]
        try:
            ray.get_actor(name, namespace="robot-eval")
            logger.info("actor.exists", extra={"name": name})
        except Exception:
            logger.info("actor.creating", extra={"name": name})
            ActorClass.options(
                name=name, namespace="robot-eval",
                lifetime="detached", num_gpus=1,
                runtime_env=runtime_env,
            ).remote(w["worker_id"])


app = FastAPI(title="Robot Eval Platform v2", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

from backend.api.jobs      import router as jobs_router
from backend.api.runs      import router as runs_router
from backend.api.workers   import router as workers_router
from backend.api.templates import router as templates_router

app.include_router(jobs_router)
app.include_router(runs_router)
app.include_router(workers_router)
app.include_router(templates_router)

@app.get("/api/health")
async def health():
    try:
        await db.pool.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}

if _STATIC.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")
```

Note: `job_engine` is set as a module-level variable in `backend/engines/job_engine.py` by the lifespan. Add this line to the bottom of `job_engine.py`:

```python
# Singleton — set by main.py lifespan
job_engine: JobEngine | None = None
```

- [ ] **Step 4.7: Write API test**

```python
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
         patch("ray.init"):
        from backend.main import app
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as client:
            yield client

@pytest.mark.asyncio
async def test_submit_job(app_client):
    resp = await app_client.post("/api/jobs", json={
        "name": "test_job",
        "arena_env_args": {"environment": "lift_object"},
        "model_name": "pi0",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"

@pytest.mark.asyncio
async def test_list_jobs(app_client):
    resp = await app_client.get("/api/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

@pytest.mark.asyncio
async def test_health(app_client):
    resp = await app_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["db"] is True
```

- [ ] **Step 4.8: Install test dependencies**

```bash
cd /home/disk/lrx/robot-eval
pip install pytest pytest-asyncio httpx
```

- [ ] **Step 4.9: Run API tests**

```bash
TEST_DATABASE_URL="postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test" \
  pytest tests/api/test_jobs_api.py -v
```
Expected: 3 tests PASS

- [ ] **Step 4.10: Smoke-test the running platform**

```bash
# Restart eval-platform container with new code
docker restart eval-platform
sleep 10
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
```
Expected:
```json
{"status": "ok", "db": true}
```

```bash
curl -s http://127.0.0.1:8000/api/workers | python3 -m json.tool
```
Expected: worker list with `"online": true`

- [ ] **Step 4.11: Commit**

```bash
git add backend/api/ backend/engines/job_engine.py backend/main.py tests/api/
git commit -m "feat: API restructure — split routers, JobEngine wired to scheduler (Phase 1, Task 4)"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** DB schema (§4) ✓, BaseRunner/RunResult (§6.1) ✓, Runner registry (§6.2) ✓, Job lifecycle + scheduler (§5) ✓, API endpoints (§5.3) ✓, `/api/health` (§10) ✓
- [x] **Placeholder scan:** All code blocks are complete; no TBD/TODO
- [x] **Type consistency:**
  - `create_job` returns `dict` used throughout ✓
  - `RunResult.episodes: list[EpisodeResult]` used in scheduler `_ep_to_dict` ✓
  - `job_engine` singleton set in `job_engine.py`, imported in routers ✓
  - `append_log` signature: `(pool, job_id, line)` used consistently ✓
