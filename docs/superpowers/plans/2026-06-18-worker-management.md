# Worker Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static `WORKERS_META` env-var with a UI-driven system to register remote hosts, probe GPU/resource status via SSH, and deploy/destroy Isaac Sim worker containers from the platform frontend.

**Architecture:** `host_manager.py` handles all SSH/Fernet/deploy logic; `db.py` migrates from SQLite to PostgreSQL (asyncpg); `main.py` switches to Gunicorn multi-process via a lifespan context; a new `HostsPanel.tsx` React component sits above the existing worker cards.

**Tech Stack:** asyncpg 0.29, Gunicorn 22, paramiko 3.4, cryptography 42, PostgreSQL 16-alpine, React + TypeScript (existing).

## Global Constraints

- Python 3.12 (existing)
- FastAPI ≥ 0.110 (existing)
- asyncpg ≥ 0.29 — all DB calls are async
- All DB state in PostgreSQL; no in-process globals for shared state
- Gunicorn `-k uvicorn.workers.UvicornWorker -w 4`
- SSH credentials encrypted with Fernet; key from `HOST_SECRET_KEY` env var
- Port rule: `http_port = 8042 + worker_id`, `livestream_port = 49200 + worker_id`
- `WORKERS_META` env var removed; active workers read from `remote_workers WHERE status='running'`
- Password never returned from any API response
- All Chinese UI strings match existing codebase conventions

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `docker-compose.yml` | Add postgres service, update platform command/env |
| Modify | `Dockerfile` | Add `entrypoint.sh`, switch CMD to gunicorn |
| Create | `backend/entrypoint.sh` | Auto-generate `HOST_SECRET_KEY` before gunicorn starts |
| Rewrite | `backend/db.py` | asyncpg pool, all existing + new tables |
| Modify | `backend/main.py` | Lifespan context, await db calls, new host endpoints, remove `_workers_meta` global |
| Create | `backend/host_manager.py` | Fernet encrypt/decrypt, `_ssh_run`, `probe_host`, `deploy_worker`, `destroy_worker` |
| Modify | `backend/requirements.txt` | Add asyncpg, gunicorn, paramiko, cryptography |
| Modify | `frontend/src/types.ts` | Add `Host`, `HostStatus`, `GpuInfo`, `MemInfo`, `DiskInfo`, `ContainerInfo`, `RemoteWorker` |
| Modify | `frontend/src/api.ts` | Add host/probe/deploy/destroy API functions |
| Create | `frontend/src/components/HostsPanel.tsx` | Host table, add-host drawer, probe expand, deploy button |
| Modify | `frontend/src/components/WorkersView.tsx` | Import HostsPanel, add destroy button to worker cards |

---

## Task 1: PostgreSQL Infrastructure + db.py Rewrite

**Files:**
- Modify: `docker-compose.yml`
- Modify: `Dockerfile`
- Create: `backend/entrypoint.sh`
- Rewrite: `backend/db.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Produces:
  - `Database` class with `async def init(url: str)`, `async def close()`
  - `async def create_job(job_id, config) -> dict`
  - `async def get_job(job_id) -> dict | None`
  - `async def list_jobs() -> list[dict]`
  - `async def update_status(job_id, status) -> None`
  - `async def append_log(job_id, line) -> None`
  - `async def get_logs(job_id) -> list[str]`
  - module-level `db: Database` (initialized in lifespan, Task 2)

- [ ] **Step 1: Add postgres to docker-compose.yml**

  Open `docker-compose.yml`. Add the postgres service and update the platform service:

  ```yaml
  # Add this service before `ray-head`:
  postgres:
    image: postgres:16-alpine
    container_name: robot-eval-db
    network_mode: host
    environment:
      POSTGRES_DB: robot_eval
      POSTGRES_USER: eval
      POSTGRES_PASSWORD: eval_secret
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    restart: unless-stopped

  # In the platform service, replace:
  #   command: uvicorn backend.main:app --host 0.0.0.0 --port 8000
  # with:
  #   command: /app/backend/entrypoint.sh
  # Add to environment:
  #   - DATABASE_URL=postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval
  # Remove from environment:
  #   - WORKERS_META=...
  # Add to depends_on:
  #   - postgres
  ```

  Full updated platform service block:

  ```yaml
  platform:
    build:
      context: .
      dockerfile: Dockerfile
    image: robot-eval-platform:latest
    container_name: eval-platform
    network_mode: host
    volumes:
      - ./scripts:/app/scripts:ro
      - ./configs:/app/configs:ro
      - ./results:/app/results
      - ./backend:/app/backend
      - ./frontend/dist:/app/frontend/dist:ro
      - ./.env:/app/.env
    environment:
      - PYTHONPATH=/app:/app/backend
      - RAY_ADDRESS=ray://127.0.0.1:10001
      - DATABASE_URL=postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval
      - EVAL_ACTOR_MODULE=arena_actor
      - EVAL_ACTOR_CLASS=IsaacLabArenaActor
      - EVAL_PYTHONPATH=/workspaces/isaaclab_arena:/workspaces/isaaclab_arena/isaaclab_arena_environments
    command: /app/backend/entrypoint.sh
    depends_on:
      - postgres
      - ray-head
    restart: unless-stopped
  ```

- [ ] **Step 2: Update requirements.txt**

  Replace the full contents of `backend/requirements.txt`:

  ```
  fastapi>=0.110
  uvicorn[standard]>=0.29
  pydantic>=2.0
  aiofiles
  httpx
  ray[client]==2.52.1
  asyncpg>=0.29
  gunicorn>=22.0
  paramiko>=3.4
  cryptography>=42.0
  ```

- [ ] **Step 3: Create backend/entrypoint.sh**

  ```bash
  #!/usr/bin/env bash
  set -e

  ENV_FILE="/app/.env"

  # Auto-generate HOST_SECRET_KEY if not already present
  if [ -z "${HOST_SECRET_KEY}" ]; then
    if grep -q "^HOST_SECRET_KEY=" "$ENV_FILE" 2>/dev/null; then
      export HOST_SECRET_KEY=$(grep "^HOST_SECRET_KEY=" "$ENV_FILE" | cut -d= -f2-)
    else
      KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
      echo "HOST_SECRET_KEY=${KEY}" >> "$ENV_FILE"
      export HOST_SECRET_KEY="$KEY"
      echo "[entrypoint] Generated new HOST_SECRET_KEY"
    fi
  fi

  exec gunicorn backend.main:app \
    -k uvicorn.workers.UvicornWorker \
    -w 4 \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --graceful-timeout 30
  ```

  Make it executable:
  ```bash
  chmod +x backend/entrypoint.sh
  ```

- [ ] **Step 4: Update Dockerfile to use entrypoint**

  Replace `backend/requirements.txt` install + CMD in `Dockerfile`:

  ```dockerfile
  # ── Stage 1: Build React frontend ────────────────────────────────────────────
  FROM node:20-alpine AS frontend-build
  WORKDIR /app
  COPY frontend/package*.json ./
  RUN npm ci --silent
  COPY frontend/ ./
  RUN npm run build

  # ── Stage 2: Python backend + serve everything ────────────────────────────────
  FROM python:3.12-slim
  WORKDIR /app

  COPY backend/requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt

  COPY backend/ ./backend/
  RUN chmod +x /app/backend/entrypoint.sh

  COPY --from=frontend-build /app/dist ./frontend/dist

  CMD ["/app/backend/entrypoint.sh"]
  ```

- [ ] **Step 5: Rewrite backend/db.py**

  Replace the entire file:

  ```python
  """PostgreSQL-backed store using asyncpg."""
  import json
  import time
  import asyncpg
  from typing import Optional


  class Database:
      def __init__(self):
          self._pool: asyncpg.Pool | None = None

      async def init(self, url: str) -> None:
          self._pool = await asyncpg.create_pool(url, min_size=2, max_size=10)
          async with self._pool.acquire() as conn:
              await conn.execute("""
                  CREATE TABLE IF NOT EXISTS jobs (
                      id TEXT PRIMARY KEY,
                      config TEXT,
                      status TEXT DEFAULT 'pending',
                      created_at DOUBLE PRECISION,
                      updated_at DOUBLE PRECISION
                  );
                  CREATE TABLE IF NOT EXISTS logs (
                      id SERIAL PRIMARY KEY,
                      job_id TEXT,
                      line TEXT,
                      ts DOUBLE PRECISION
                  );
                  CREATE TABLE IF NOT EXISTS hosts (
                      id SERIAL PRIMARY KEY,
                      label TEXT NOT NULL,
                      host TEXT NOT NULL,
                      port INTEGER DEFAULT 22,
                      username TEXT NOT NULL,
                      password_enc TEXT NOT NULL,
                      created_at TIMESTAMPTZ DEFAULT now()
                  );
                  CREATE TABLE IF NOT EXISTS remote_workers (
                      id SERIAL PRIMARY KEY,
                      host_id INTEGER REFERENCES hosts(id) ON DELETE CASCADE,
                      worker_id INTEGER NOT NULL,
                      gpu_index INTEGER NOT NULL,
                      http_port INTEGER NOT NULL,
                      livestream_port INTEGER NOT NULL,
                      container_name TEXT NOT NULL,
                      status TEXT DEFAULT 'deploying',
                      deployed_at TIMESTAMPTZ DEFAULT now(),
                      stopped_at TIMESTAMPTZ
                  );
              """)

      async def close(self) -> None:
          if self._pool:
              await self._pool.close()

      # ── Jobs ──────────────────────────────────────────────────────────────────

      async def create_job(self, job_id: str, config: dict) -> dict:
          now = time.time()
          async with self._pool.acquire() as conn:
              await conn.execute(
                  "INSERT INTO jobs VALUES ($1,$2,$3,$4,$5)",
                  job_id, json.dumps(config), "pending", now, now,
              )
          return await self.get_job(job_id)

      async def get_job(self, job_id: str) -> Optional[dict]:
          async with self._pool.acquire() as conn:
              row = await conn.fetchrow("SELECT * FROM jobs WHERE id=$1", job_id)
          if not row:
              return None
          d = dict(row)
          d["config"] = json.loads(d["config"])
          return d

      async def list_jobs(self) -> list:
          async with self._pool.acquire() as conn:
              rows = await conn.fetch("SELECT * FROM jobs ORDER BY created_at DESC")
          result = []
          for row in rows:
              d = dict(row)
              d["config"] = json.loads(d["config"])
              result.append(d)
          return result

      async def update_status(self, job_id: str, status: str) -> None:
          async with self._pool.acquire() as conn:
              await conn.execute(
                  "UPDATE jobs SET status=$1, updated_at=$2 WHERE id=$3",
                  status, time.time(), job_id,
              )

      async def append_log(self, job_id: str, line: str) -> None:
          async with self._pool.acquire() as conn:
              await conn.execute(
                  "INSERT INTO logs (job_id, line, ts) VALUES ($1,$2,$3)",
                  job_id, line, time.time(),
              )

      async def get_logs(self, job_id: str) -> list[str]:
          async with self._pool.acquire() as conn:
              rows = await conn.fetch(
                  "SELECT line FROM logs WHERE job_id=$1 ORDER BY id", job_id
              )
          return [r["line"] for r in rows]

      # ── Hosts ─────────────────────────────────────────────────────────────────

      async def insert_host(self, label: str, host: str, port: int,
                            username: str, password_enc: str) -> dict:
          async with self._pool.acquire() as conn:
              row = await conn.fetchrow(
                  """INSERT INTO hosts (label, host, port, username, password_enc)
                     VALUES ($1,$2,$3,$4,$5) RETURNING *""",
                  label, host, port, username, password_enc,
              )
          return dict(row)

      async def list_hosts(self) -> list[dict]:
          async with self._pool.acquire() as conn:
              rows = await conn.fetch("SELECT * FROM hosts ORDER BY id")
          return [dict(r) for r in rows]

      async def get_host(self, host_id: int) -> Optional[dict]:
          async with self._pool.acquire() as conn:
              row = await conn.fetchrow("SELECT * FROM hosts WHERE id=$1", host_id)
          return dict(row) if row else None

      async def delete_host(self, host_id: int) -> None:
          async with self._pool.acquire() as conn:
              await conn.execute("DELETE FROM hosts WHERE id=$1", host_id)

      # ── Remote workers ────────────────────────────────────────────────────────

      async def insert_remote_worker(self, host_id: int, worker_id: int,
                                     gpu_index: int, http_port: int,
                                     livestream_port: int,
                                     container_name: str) -> dict:
          async with self._pool.acquire() as conn:
              row = await conn.fetchrow(
                  """INSERT INTO remote_workers
                     (host_id, worker_id, gpu_index, http_port, livestream_port, container_name)
                     VALUES ($1,$2,$3,$4,$5,$6) RETURNING *""",
                  host_id, worker_id, gpu_index, http_port, livestream_port, container_name,
              )
          return dict(row)

      async def update_worker_status(self, worker_id: int, status: str) -> None:
          async with self._pool.acquire() as conn:
              if status == "stopped":
                  await conn.execute(
                      "UPDATE remote_workers SET status=$1, stopped_at=now() WHERE worker_id=$2",
                      status, worker_id,
                  )
              else:
                  await conn.execute(
                      "UPDATE remote_workers SET status=$1 WHERE worker_id=$2",
                      status, worker_id,
                  )

      async def list_remote_workers(self, host_id: Optional[int] = None,
                                    status: Optional[str] = None) -> list[dict]:
          conditions, params = [], []
          if host_id is not None:
              params.append(host_id)
              conditions.append(f"host_id=${len(params)}")
          if status is not None:
              params.append(status)
              conditions.append(f"status=${len(params)}")
          where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
          async with self._pool.acquire() as conn:
              rows = await conn.fetch(
                  f"SELECT * FROM remote_workers {where} ORDER BY worker_id", *params
              )
          return [dict(r) for r in rows]

      async def get_remote_worker(self, worker_id: int) -> Optional[dict]:
          async with self._pool.acquire() as conn:
              row = await conn.fetchrow(
                  "SELECT * FROM remote_workers WHERE worker_id=$1", worker_id
              )
          return dict(row) if row else None

      async def next_worker_id(self) -> int:
          """Return MAX(worker_id)+1 across all non-stopped workers, minimum 0."""
          async with self._pool.acquire() as conn:
              row = await conn.fetchrow(
                  "SELECT MAX(worker_id) AS m FROM remote_workers WHERE status != 'stopped'"
              )
          return (row["m"] or -1) + 1


  db = Database()
  ```

- [ ] **Step 6: Verify the schema creates without errors**

  ```bash
  cd /home/disk/lrx/robot-eval
  docker-compose up -d postgres
  sleep 3
  docker exec robot-eval-db psql -U eval -d robot_eval -c "\dt"
  ```

  Expected output:
  ```
           List of relations
   Schema |     Name       | Type  | Owner
  --------+----------------+-------+-------
   public | hosts          | table | eval
   public | jobs           | table | eval
   public | logs           | table | eval
   public | remote_workers | table | eval
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add backend/db.py backend/requirements.txt backend/entrypoint.sh \
          Dockerfile docker-compose.yml
  git commit -m "feat: migrate db to PostgreSQL, add gunicorn entrypoint"
  ```

---

## Task 2: Refactor main.py to Async + Lifespan

**Files:**
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `db: Database` from `backend.db` (Task 1)
- The global `db` object is initialized in the lifespan; all call sites `await db.<method>()`
- Removes: `_workers_meta` global and `WORKERS_META` env var usage
- `/api/workers` now queries `db.list_remote_workers(status='running')`

- [ ] **Step 1: Replace startup event + module-level db init with lifespan**

  At the top of `backend/main.py`, replace the imports and app creation:

  ```python
  import asyncio
  import json
  import os
  import time
  import uuid
  from contextlib import asynccontextmanager
  from pathlib import Path
  from typing import Any, AsyncIterator

  import httpx
  import ray
  from fastapi import FastAPI, HTTPException, Request
  from fastapi.middleware.cors import CORSMiddleware
  from fastapi.responses import StreamingResponse
  from fastapi.staticfiles import StaticFiles
  from pydantic import BaseModel

  from backend.db import db
  from backend.base_actor import load_actor_class

  ROOT        = Path(__file__).parent.parent
  RESULTS_DIR = ROOT / "results"
  STATIC      = Path(__file__).parent.parent / "frontend" / "dist"

  _ACTOR_MODULE    = os.environ.get("EVAL_ACTOR_MODULE", "arena_actor")
  _ACTOR_CLASS     = os.environ.get("EVAL_ACTOR_CLASS",  "IsaacLabArenaActor")
  _EVAL_PYTHONPATH = os.environ.get(
      "EVAL_PYTHONPATH",
      "/workspaces/isaaclab_arena:/workspaces/isaaclab_arena/isaaclab_arena_environments",
  )
  _DATABASE_URL = os.environ.get(
      "DATABASE_URL",
      "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval",
  )


  @asynccontextmanager
  async def lifespan(app: FastAPI):
      RESULTS_DIR.mkdir(parents=True, exist_ok=True)
      await db.init(_DATABASE_URL)
      ray_addr = os.environ.get("RAY_ADDRESS", "ray://127.0.0.1:10001")
      try:
          ray.init(address=ray_addr, ignore_reinit_error=True, log_to_driver=False)
          asyncio.create_task(_create_actors())
      except Exception as e:
          print(f"[platform] Ray not ready ({e}), will retry on job submit", flush=True)
      yield
      await db.close()


  app = FastAPI(title="Robot Eval Platform", lifespan=lifespan)
  app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
  ```

- [ ] **Step 2: Rewrite _create_actors to pull workers from DB**

  Replace the `_create_actors` function:

  ```python
  async def _create_actors():
      """Create Ray EvalActors for all running remote_workers rows."""
      ActorClass = load_actor_class(_ACTOR_MODULE, _ACTOR_CLASS)

      _ISAAC_SIM = "/workspaces/isaaclab_arena/submodules/IsaacLab/_isaac_sim"
      isaac_ldpath = ":".join([
          _ISAAC_SIM, f"{_ISAAC_SIM}/kit", f"{_ISAAC_SIM}/kit/kernel/plugins",
          f"{_ISAAC_SIM}/kit/libs/iray", f"{_ISAAC_SIM}/kit/plugins",
          f"{_ISAAC_SIM}/kit/plugins/bindings-python",
          f"{_ISAAC_SIM}/kit/plugins/carb_gfx", f"{_ISAAC_SIM}/kit/plugins/rtx",
          f"{_ISAAC_SIM}/kit/plugins/gpu.foundation",
      ])
      worker_runtime_env = {
          "env_vars": {
              "LD_LIBRARY_PATH": isaac_ldpath,
              "CARB_APP_PATH":   f"{_ISAAC_SIM}/kit",
              "ISAAC_PATH":      _ISAAC_SIM,
              "EXP_PATH":        f"{_ISAAC_SIM}/apps",
              "RESOURCE_NAME":   "IsaacSim",
              "LD_PRELOAD":      f"{_ISAAC_SIM}/kit/libcarb.so",
          }
      }

      workers = await db.list_remote_workers(status="running")
      for w in workers:
          actor_name = f"arena-worker-{w['worker_id']}"
          try:
              ray.get_actor(actor_name, namespace="robot-eval")
          except Exception:
              ActorClass.options(
                  name=actor_name,
                  namespace="robot-eval",
                  lifetime="detached",
                  num_gpus=1,
                  runtime_env=worker_runtime_env,
              ).remote(w["worker_id"], w["http_port"], w["livestream_port"])
  ```

- [ ] **Step 3: Update /api/workers to query DB**

  Replace the `get_workers` endpoint:

  ```python
  @app.get("/api/workers")
  async def get_workers():
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
              "worker_id":       w["worker_id"],
          })
      return results
  ```

- [ ] **Step 4: Update all remaining db calls to await**

  Replace every synchronous `db.<method>()` call in `main.py` with `await db.<method>()`. The affected spots are in `list_jobs`, `get_job`, `create_job`, `update_status`, `append_log`, `get_logs`, and `stream_logs`. Example diff pattern:

  ```python
  # Before:
  return db.list_jobs()
  # After:
  return await db.list_jobs()

  # Before:
  job = db.get_job(job_id)
  # After:
  job = await db.get_job(job_id)

  # Before:
  job = db.create_job(job_id, req.model_dump())
  # After:
  job = await db.create_job(job_id, req.model_dump())

  # Before:
  db.update_status(job_id, "running")
  # After:
  await db.update_status(job_id, "running")

  # Before:
  db.append_log(job_id, "...")
  # After:
  await db.append_log(job_id, "...")

  # Before (in stream_logs generator):
  lines = db.get_logs(job_id)
  job   = db.get_job(job_id)
  # After:
  lines = await db.get_logs(job_id)
  job   = await db.get_job(job_id)
  ```

  Also remove the old `startup` event handler and the `_workers_meta` global entirely.

- [ ] **Step 5: Remove /api/workers/health (duplicate of /api/workers)**

  Delete the `workers_health` endpoint — it was a duplicate; `/api/workers` already serves health.

- [ ] **Step 6: Smoke-test the refactored backend locally**

  ```bash
  cd /home/disk/lrx/robot-eval
  DATABASE_URL=postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval \
    HOST_SECRET_KEY=placeholder \
    uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload
  # In another terminal:
  curl http://localhost:8001/api/jobs
  curl http://localhost:8001/api/workers
  ```

  Expected: both return `[]` (empty list), no errors.

- [ ] **Step 7: Commit**

  ```bash
  git add backend/main.py
  git commit -m "refactor: main.py lifespan, async db calls, workers from DB"
  ```

---

## Task 3: host_manager.py

**Files:**
- Create: `backend/host_manager.py`

**Interfaces:**
- Consumes: `db: Database` from `backend.db`
- Produces (used in Task 4):
  - `async def add_host(label, host, port, username, password) -> dict`
  - `async def list_hosts() -> list[dict]`  — password_enc stripped, field `password` omitted
  - `async def delete_host(host_id) -> None`
  - `async def probe_host(host_id) -> dict`  — HostStatus shape from spec Section 4
  - `async def deploy_worker(host_id) -> dict`  — RemoteWorker row
  - `async def destroy_worker(host_id, worker_id) -> None`

- [ ] **Step 1: Create backend/host_manager.py with encryption helpers**

  ```python
  """Host management: SSH probe, worker deploy/destroy, Fernet credential encryption."""
  import asyncio
  import os
  import re
  import time
  from datetime import datetime, timezone
  from typing import Optional

  import paramiko
  from cryptography.fernet import Fernet

  from backend.db import db


  def _get_fernet() -> Fernet:
      key = os.environ.get("HOST_SECRET_KEY", "")
      if not key:
          raise RuntimeError("HOST_SECRET_KEY env var not set")
      return Fernet(key.encode())


  def _encrypt(plaintext: str) -> str:
      return _get_fernet().encrypt(plaintext.encode()).decode()


  def _decrypt(ciphertext: str) -> str:
      return _get_fernet().decrypt(ciphertext.encode()).decode()
  ```

- [ ] **Step 2: Add _ssh_run helper**

  Append to `host_manager.py`:

  ```python
  def _ssh_run_sync(host: str, port: int, username: str,
                    password: str, cmd: str) -> str:
      client = paramiko.SSHClient()
      client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
      try:
          client.connect(host, port=port, username=username,
                         password=password, timeout=10,
                         look_for_keys=False, allow_agent=False)
          _, stdout, stderr = client.exec_command(cmd, timeout=30)
          out = stdout.read().decode().strip()
          err = stderr.read().decode().strip()
          exit_code = stdout.channel.recv_exit_status()
          if exit_code != 0:
              raise RuntimeError(f"SSH command failed (exit {exit_code}): {err}")
          return out
      finally:
          client.close()


  async def _ssh_run(host: str, port: int, username: str,
                     password: str, cmd: str) -> str:
      return await asyncio.to_thread(
          _ssh_run_sync, host, port, username, password, cmd
      )
  ```

- [ ] **Step 3: Add add_host / list_hosts / delete_host**

  Append to `host_manager.py`:

  ```python
  async def add_host(label: str, host: str, port: int,
                     username: str, password: str) -> dict:
      password_enc = _encrypt(password)
      row = await db.insert_host(label, host, port, username, password_enc)
      row.pop("password_enc", None)
      return row


  async def list_hosts() -> list[dict]:
      rows = await db.list_hosts()
      result = []
      for r in rows:
          r = dict(r)
          r.pop("password_enc", None)
          # Count running workers for this host
          workers = await db.list_remote_workers(host_id=r["id"], status="running")
          r["worker_count"] = len(workers)
          result.append(r)
      return result


  async def delete_host(host_id: int) -> None:
      # Destroy all running workers first
      workers = await db.list_remote_workers(host_id=host_id, status="running")
      for w in workers:
          try:
              await destroy_worker(host_id, w["worker_id"])
          except Exception:
              pass
      await db.delete_host(host_id)
  ```

- [ ] **Step 4: Add probe_host**

  Append to `host_manager.py`:

  ```python
  def _parse_nvidia_smi(raw: str) -> list[dict]:
      """Parse: nvidia-smi --query-gpu=index,name,memory.total,memory.free,utilization.gpu --format=csv,noheader,nounits"""
      gpus = []
      for line in raw.strip().splitlines():
          parts = [p.strip() for p in line.split(",")]
          if len(parts) < 5:
              continue
          idx, name, mem_total, mem_free, util = parts[:5]
          try:
              gpus.append({
                  "index":          int(idx),
                  "name":           name,
                  "vram_total_mb":  int(mem_total),
                  "vram_free_mb":   int(mem_free),
                  "utilization_pct": int(util),
                  "busy":           int(util) > 10,
              })
          except ValueError:
              pass
      return gpus


  def _parse_free(raw: str) -> dict:
      """Parse: free -m  (Mem: line only)"""
      for line in raw.splitlines():
          if line.startswith("Mem:"):
              parts = line.split()
              return {"total_mb": int(parts[1]), "used_mb": int(parts[2])}
      return {"total_mb": 0, "used_mb": 0}


  def _parse_df(raw: str) -> dict:
      """Parse: df -BG /  (second line)"""
      lines = raw.strip().splitlines()
      if len(lines) < 2:
          return {"path": "/", "total_gb": 0, "used_gb": 0}
      parts = lines[1].split()
      return {
          "path":     parts[5] if len(parts) > 5 else "/",
          "total_gb": int(parts[1].rstrip("G")),
          "used_gb":  int(parts[2].rstrip("G")),
      }


  def _parse_docker_ps(raw: str) -> list[dict]:
      """Parse docker ps output for isaac-sim containers."""
      containers = []
      for line in raw.strip().splitlines():
          parts = line.split("\t")
          if len(parts) < 3:
              continue
          name, status, gpu_env = parts[0], parts[1], parts[2]
          gpu_index = None
          m = re.search(r"NVIDIA_VISIBLE_DEVICES=(\d+)", gpu_env)
          if m:
              gpu_index = int(m.group(1))
          containers.append({
              "name":      name,
              "status":    status,
              "gpu_index": gpu_index,
          })
      return containers


  def _parse_used_ports(raw: str) -> list[int]:
      """Parse ss -tlnp for numeric ports."""
      ports = set()
      for line in raw.strip().splitlines()[1:]:  # skip header
          m = re.search(r":(\d+)\s", line)
          if m:
              ports.add(int(m.group(1)))
      return sorted(ports)


  async def probe_host(host_id: int) -> dict:
      row = await db.get_host(host_id)
      if not row:
          raise ValueError(f"Host {host_id} not found")
      password = _decrypt(row["password_enc"])
      ssh = dict(host=row["host"], port=row["port"],
                 username=row["username"], password=password)

      try:
          gpu_raw, mem_raw, disk_raw, docker_raw, ports_raw = await asyncio.gather(
              _ssh_run(**ssh, cmd=(
                  "nvidia-smi --query-gpu=index,name,memory.total,memory.free,"
                  "utilization.gpu --format=csv,noheader,nounits"
              )),
              _ssh_run(**ssh, cmd="free -m"),
              _ssh_run(**ssh, cmd="df -BG /"),
              _ssh_run(**ssh, cmd=(
                  "docker ps --format '{{.Names}}\t{{.Status}}\t{{.Env}}' "
                  "2>/dev/null | grep -i isaac || true"
              )),
              _ssh_run(**ssh, cmd="ss -tlnp"),
          )
          return {
              "host_id":    host_id,
              "probed_at":  datetime.now(timezone.utc).isoformat(),
              "gpus":       _parse_nvidia_smi(gpu_raw),
              "memory":     _parse_free(mem_raw),
              "disk":       _parse_df(disk_raw),
              "containers": _parse_docker_ps(docker_raw),
              "used_ports": _parse_used_ports(ports_raw),
              "error":      None,
          }
      except Exception as e:
          return {
              "host_id":    host_id,
              "probed_at":  datetime.now(timezone.utc).isoformat(),
              "gpus": [], "memory": {}, "disk": {}, "containers": [],
              "used_ports": [],
              "error":      str(e),
          }
  ```

- [ ] **Step 5: Add deploy_worker**

  Append to `host_manager.py`:

  ```python
  _EVAL_PYTHONPATH = os.environ.get(
      "EVAL_PYTHONPATH",
      "/workspaces/isaaclab_arena:/workspaces/isaaclab_arena/isaaclab_arena_environments",
  )
  _EVAL_ACTOR_MODULE = os.environ.get("EVAL_ACTOR_MODULE", "arena_actor")
  _EVAL_ACTOR_CLASS  = os.environ.get("EVAL_ACTOR_CLASS",  "IsaacLabArenaActor")
  _RAY_HEAD_IP       = os.environ.get("RAY_HEAD_IP", "127.0.0.1")


  async def deploy_worker(host_id: int) -> dict:
      host_row = await db.get_host(host_id)
      if not host_row:
          raise ValueError(f"Host {host_id} not found")

      status = await probe_host(host_id)
      if status.get("error"):
          raise RuntimeError(f"Cannot probe host: {status['error']}")

      # Find first free GPU not already used by a running worker
      running = await db.list_remote_workers(host_id=host_id, status="running")
      used_gpus = {w["gpu_index"] for w in running}
      free_gpu = next(
          (g["index"] for g in status["gpus"] if not g["busy"] and g["index"] not in used_gpus),
          None,
      )
      if free_gpu is None:
          raise RuntimeError("No free GPU available on this host")

      worker_id       = await db.next_worker_id()
      http_port       = 8042 + worker_id
      livestream_port = 49200 + worker_id
      container_name  = f"isaac-lab-worker-{worker_id}"

      password = _decrypt(host_row["password_enc"])
      ssh = dict(host=host_row["host"], port=host_row["port"],
                 username=host_row["username"], password=password)

      docker_cmd = (
          f"docker run -d --runtime=nvidia --network=host "
          f"--name {container_name} "
          f"--gpus device={free_gpu} "
          f"--ulimit memlock=-1 --ulimit stack=67108864 "
          f"--shm-size=8g "
          f"-e NVIDIA_VISIBLE_DEVICES={free_gpu} "
          f"-e NVIDIA_DRIVER_CAPABILITIES=all "
          f"-e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y "
          f"-e WORKER_ID={worker_id} "
          f"-e HTTP_PORT={http_port} "
          f"-e LIVESTREAM_PORT={livestream_port} "
          f"-e EVAL_ACTOR_MODULE={_EVAL_ACTOR_MODULE} "
          f"-e EVAL_ACTOR_CLASS={_EVAL_ACTOR_CLASS} "
          f"-e EVAL_PYTHONPATH='{_EVAL_PYTHONPATH}' "
          f"-v /home/disk/ssl/isaac-sim5.0/cache/ov:/root/.cache/ov "
          f"-v /home/disk/ssl/isaacsim_assets:/isaac-sim/isaacsim_assets:ro "
          f"isaaclab_arena:latest "
          f"bash -c '"
          f"source /workspaces/isaaclab_arena/submodules/IsaacLab/_isaac_sim/setup_python_env.sh && "
          f"/workspaces/isaaclab_arena/submodules/IsaacLab/_isaac_sim/kit/python/bin/ray "
          f"start --address={_RAY_HEAD_IP}:6379 --num-gpus=1 --block'"
      )
      await _ssh_run(**ssh, cmd=docker_cmd)

      worker_row = await db.insert_remote_worker(
          host_id, worker_id, free_gpu, http_port, livestream_port, container_name
      )

      # Background health-check: poll docker inspect for up to 60 s
      asyncio.create_task(_wait_for_worker(host_row, worker_id, container_name, password))

      return {k: v for k, v in worker_row.items()
              if not isinstance(v, bytes)}


  async def _wait_for_worker(host_row: dict, worker_id: int,
                              container_name: str, password: str) -> None:
      ssh = dict(host=host_row["host"], port=host_row["port"],
                 username=host_row["username"], password=password)
      for _ in range(12):  # 12 × 5 s = 60 s
          await asyncio.sleep(5)
          try:
              out = await _ssh_run(
                  **ssh,
                  cmd=f"docker inspect --format='{{{{.State.Status}}}}' {container_name}"
              )
              if out.strip() == "running":
                  await db.update_worker_status(worker_id, "running")
                  return
              if out.strip() in ("exited", "dead"):
                  await db.update_worker_status(worker_id, "error")
                  return
          except Exception:
              pass
      await db.update_worker_status(worker_id, "error")
  ```

- [ ] **Step 6: Add destroy_worker**

  Append to `host_manager.py`:

  ```python
  async def destroy_worker(host_id: int, worker_id: int) -> None:
      worker_row = await db.get_remote_worker(worker_id)
      if not worker_row:
          raise ValueError(f"Worker {worker_id} not found")
      host_row = await db.get_host(host_id)
      if not host_row:
          raise ValueError(f"Host {host_id} not found")

      password = _decrypt(host_row["password_enc"])
      ssh = dict(host=host_row["host"], port=host_row["port"],
                 username=host_row["username"], password=password)
      container = worker_row["container_name"]
      try:
          await _ssh_run(**ssh, cmd=f"docker stop {container} && docker rm {container}")
      except Exception:
          pass  # Container may already be gone; mark stopped regardless
      await db.update_worker_status(worker_id, "stopped")
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add backend/host_manager.py
  git commit -m "feat: add host_manager (SSH probe, deploy, destroy, Fernet)"
  ```

---

## Task 4: Host API Endpoints in main.py

**Files:**
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: all functions from `backend.host_manager` (Task 3)
- Produces REST endpoints consumed by Task 5 frontend

- [ ] **Step 1: Add import and Pydantic model for AddHost**

  Add to the imports section at the top of `main.py`:

  ```python
  import backend.host_manager as hm
  ```

  Add a new Pydantic model after `SubmitRequest`:

  ```python
  class AddHostRequest(BaseModel):
      label:    str
      host:     str
      port:     int = 22
      username: str
      password: str
  ```

- [ ] **Step 2: Add all six host endpoints**

  Add these routes after the `/api/workers` block:

  ```python
  # ── Host management ───────────────────────────────────────────────────────────

  @app.get("/api/hosts")
  async def list_hosts():
      return await hm.list_hosts()

  @app.post("/api/hosts", status_code=201)
  async def add_host(req: AddHostRequest):
      return await hm.add_host(req.label, req.host, req.port, req.username, req.password)

  @app.delete("/api/hosts/{host_id}", status_code=204)
  async def delete_host(host_id: int):
      await hm.delete_host(host_id)

  @app.post("/api/hosts/{host_id}/probe")
  async def probe_host(host_id: int):
      return await hm.probe_host(host_id)

  @app.post("/api/hosts/{host_id}/deploy", status_code=202)
  async def deploy_worker(host_id: int):
      try:
          return await hm.deploy_worker(host_id)
      except RuntimeError as e:
          msg = str(e)
          if "No free GPU" in msg:
              raise HTTPException(409, detail=msg)
          raise HTTPException(500, detail=msg)

  @app.delete("/api/hosts/{host_id}/workers/{worker_id}", status_code=204)
  async def destroy_worker(host_id: int, worker_id: int):
      await hm.destroy_worker(host_id, worker_id)
  ```

- [ ] **Step 3: Smoke-test all six endpoints**

  ```bash
  # Start the backend (postgres must be running):
  DATABASE_URL=postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval \
    HOST_SECRET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
    uvicorn backend.main:app --host 0.0.0.0 --port 8001

  # In another terminal:
  curl -s http://localhost:8001/api/hosts
  # Expected: []

  curl -s -X POST http://localhost:8001/api/hosts \
    -H "Content-Type: application/json" \
    -d '{"label":"test","host":"10.0.0.1","port":22,"username":"root","password":"secret"}'
  # Expected: {"id":1,"label":"test","host":"10.0.0.1","port":22,"username":"root","worker_count":0,...}
  # Note: no password_enc in response

  curl -s http://localhost:8001/api/hosts
  # Expected: list with one host

  curl -s -X DELETE http://localhost:8001/api/hosts/1
  # Expected: 204 No Content

  curl -s http://localhost:8001/api/hosts
  # Expected: []
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add backend/main.py
  git commit -m "feat: add host management API endpoints"
  ```

---

## Task 5: Frontend Types + API Functions

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`

**Interfaces:**
- Produces types and functions consumed by Task 6 `HostsPanel.tsx`

- [ ] **Step 1: Add types to types.ts**

  Append to `frontend/src/types.ts` before the closing line:

  ```typescript
  // ── Host management ───────────────────────────────────────────────────────────

  export interface Host {
    id:           number
    label:        string
    host:         string
    port:         number
    username:     string
    worker_count: number
    created_at:   string
  }

  export interface GpuInfo {
    index:           number
    name:            string
    vram_total_mb:   number
    vram_free_mb:    number
    utilization_pct: number
    busy:            boolean
  }

  export interface MemInfo  { total_mb: number; used_mb: number }
  export interface DiskInfo { path: string; total_gb: number; used_gb: number }

  export interface ContainerInfo {
    name:      string
    status:    string
    gpu_index: number | null
  }

  export interface HostStatus {
    host_id:    number
    probed_at:  string
    gpus:       GpuInfo[]
    memory:     MemInfo
    disk:       DiskInfo
    containers: ContainerInfo[]
    used_ports: number[]
    error:      string | null
  }

  export interface RemoteWorker {
    id:              number
    host_id:         number
    worker_id:       number
    gpu_index:       number
    http_port:       number
    livestream_port: number
    container_name:  string
    status:          string
  }

  export interface AddHostRequest {
    label:    string
    host:     string
    port:     number
    username: string
    password: string
  }
  ```

- [ ] **Step 2: Add API functions to api.ts**

  Append to `frontend/src/api.ts`:

  ```typescript
  // ── Host management ───────────────────────────────────────────────────────────

  import type { Host, HostStatus, RemoteWorker, AddHostRequest } from './types'

  export async function fetchHosts(): Promise<Host[]> {
    const r = await fetch(`${BASE}/hosts`)
    return r.json()
  }

  export async function addHost(req: AddHostRequest): Promise<Host> {
    const r = await fetch(`${BASE}/hosts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    })
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  }

  export async function deleteHost(hostId: number): Promise<void> {
    await fetch(`${BASE}/hosts/${hostId}`, { method: 'DELETE' })
  }

  export async function probeHost(hostId: number): Promise<HostStatus> {
    const r = await fetch(`${BASE}/hosts/${hostId}/probe`, { method: 'POST' })
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  }

  export async function deployWorker(hostId: number): Promise<RemoteWorker> {
    const r = await fetch(`${BASE}/hosts/${hostId}/deploy`, { method: 'POST' })
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  }

  export async function destroyWorker(hostId: number, workerId: number): Promise<void> {
    await fetch(`${BASE}/hosts/${hostId}/workers/${workerId}`, { method: 'DELETE' })
  }
  ```

- [ ] **Step 3: Verify TypeScript compiles**

  ```bash
  cd /home/disk/lrx/robot-eval/frontend
  npm run build 2>&1 | tail -20
  ```

  Expected: build succeeds (or only pre-existing errors, none from types.ts/api.ts).

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/src/types.ts frontend/src/api.ts
  git commit -m "feat: add host management types and API functions"
  ```

---

## Task 6: HostsPanel.tsx + WorkersView Integration

**Files:**
- Create: `frontend/src/components/HostsPanel.tsx`
- Modify: `frontend/src/components/WorkersView.tsx`

**Interfaces:**
- Consumes: `fetchHosts`, `addHost`, `deleteHost`, `probeHost`, `deployWorker`, `destroyWorker` from `api.ts` (Task 5)
- Consumes: `Host`, `HostStatus`, `AddHostRequest` from `types.ts` (Task 5)

- [ ] **Step 1: Create HostsPanel.tsx**

  ```tsx
  import { useState, useCallback } from 'react'
  import type { Host, HostStatus, AddHostRequest } from '../types'
  import { fetchHosts, addHost, deleteHost, probeHost, deployWorker } from '../api'

  interface Props {
    onWorkersChanged: () => void  // triggers parent to refresh /api/workers
  }

  function AddHostDrawer({ onSave, onClose }: {
    onSave: (req: AddHostRequest) => Promise<void>
    onClose: () => void
  }) {
    const [form, setForm] = useState<AddHostRequest>({
      label: '', host: '', port: 22, username: 'root', password: '',
    })
    const [saving, setSaving] = useState(false)
    const [error, setError]   = useState<string | null>(null)

    const set = (k: keyof AddHostRequest, v: string | number) =>
      setForm(f => ({ ...f, [k]: v }))

    const handleSave = async () => {
      if (!form.label || !form.host || !form.username || !form.password) {
        setError('请填写所有必填字段')
        return
      }
      setSaving(true)
      setError(null)
      try {
        await onSave(form)
      } catch (e: any) {
        setError(e.message ?? '保存失败')
      } finally {
        setSaving(false)
      }
    }

    return (
      <div className="fixed inset-0 z-50 flex justify-end"
           style={{ background: 'rgba(0,0,0,.5)' }} onClick={onClose}>
        <div className="w-80 h-full bg-ink-900 border-l border-ink-800 p-5 flex flex-col gap-4 overflow-y-auto"
             onClick={e => e.stopPropagation()}>
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-white">添加主机</span>
            <button className="btn-sm" onClick={onClose}>
              <i className="fas fa-times" />
            </button>
          </div>

          {[
            { label: '标签', key: 'label', type: 'text', placeholder: 'GPU服务器-A' },
            { label: 'IP 地址', key: 'host', type: 'text', placeholder: '10.0.0.2' },
            { label: 'SSH 端口', key: 'port', type: 'number', placeholder: '22' },
            { label: '用户名', key: 'username', type: 'text', placeholder: 'root' },
            { label: '密码', key: 'password', type: 'password', placeholder: '••••••••' },
          ].map(({ label, key, type, placeholder }) => (
            <div key={key} className="flex flex-col gap-1">
              <label className="text-[11px] text-ink-400">{label}</label>
              <input
                type={type}
                placeholder={placeholder}
                value={String(form[key as keyof AddHostRequest])}
                onChange={e => set(
                  key as keyof AddHostRequest,
                  type === 'number' ? Number(e.target.value) : e.target.value
                )}
                className="bg-ink-800 border border-ink-700 rounded px-2.5 py-1.5 text-sm text-ink-200
                           focus:outline-none focus:border-sky2 placeholder:text-ink-600"
              />
            </div>
          ))}

          {error && <p className="text-[11px] text-red-400">{error}</p>}

          <div className="flex gap-2 mt-auto pt-2">
            <button className="btn-sm flex-1" onClick={onClose}>取消</button>
            <button
              className="btn-sm flex-1 bg-sky2/10 text-sky2 border-sky2/30 hover:bg-sky2/20"
              disabled={saving}
              onClick={handleSave}
            >
              {saving ? <i className="fas fa-spinner animate-spin mr-1" /> : null}
              保存
            </button>
          </div>
        </div>
      </div>
    )
  }

  function ProbeRow({ hostId, onDeployed }: {
    hostId: number
    onDeployed: () => void
  }) {
    const [status, setStatus] = useState<HostStatus | null>(null)
    const [probing, setProbing] = useState(false)
    const [deploying, setDeploying] = useState(false)
    const [deployMsg, setDeployMsg] = useState<string | null>(null)

    const handleProbe = useCallback(async () => {
      setProbing(true)
      try {
        const s = await probeHost(hostId)
        setStatus(s)
      } finally {
        setProbing(false)
      }
    }, [hostId])

    const handleDeploy = useCallback(async () => {
      setDeploying(true)
      setDeployMsg(null)
      try {
        await deployWorker(hostId)
        setDeployMsg('Worker 部署中，稍后在下方卡片查看状态')
        onDeployed()
      } catch (e: any) {
        setDeployMsg(`部署失败: ${e.message}`)
      } finally {
        setDeploying(false)
      }
    }, [hostId, onDeployed])

    if (!status && !probing) return null

    return (
      <div className="col-span-5 bg-ink-950 border border-ink-800 rounded-lg p-4 mx-1 mb-2 text-[11px]">
        {probing && (
          <div className="flex items-center gap-2 text-ink-500">
            <i className="fas fa-spinner animate-spin" /> 探测中...
          </div>
        )}
        {status && !probing && (
          <>
            {status.error ? (
              <p className="text-red-400">连接失败: {status.error}</p>
            ) : (
              <div className="space-y-3">
                {/* GPUs */}
                <div>
                  <span className="text-ink-500 mr-2">GPU</span>
                  {status.gpus.map(g => (
                    <span key={g.index} className="mr-3">
                      <span className="text-ink-300">#{g.index} {g.name}</span>
                      <span className="text-ink-500 ml-1">{g.vram_free_mb}MB 空闲</span>
                      <span className={`ml-1 chip ${g.busy ? 'chip-run' : 'chip-pend'}`}>
                        {g.busy ? '忙碌' : '空闲'}
                      </span>
                    </span>
                  ))}
                </div>
                {/* Memory + Disk */}
                <div className="flex gap-6">
                  <span>
                    <span className="text-ink-500">内存 </span>
                    <span className="text-ink-300 num">{status.memory.used_mb}
                      <span className="text-ink-500">/{status.memory.total_mb} MB</span>
                    </span>
                  </span>
                  <span>
                    <span className="text-ink-500">磁盘 </span>
                    <span className="text-ink-300 num">{status.disk.used_gb}
                      <span className="text-ink-500">/{status.disk.total_gb} GB</span>
                    </span>
                  </span>
                </div>
                {/* Containers */}
                {status.containers.length > 0 && (
                  <div>
                    <span className="text-ink-500 mr-2">容器</span>
                    {status.containers.map(c => (
                      <span key={c.name} className="mr-3">
                        <span className="font-mono text-ink-300">{c.name}</span>
                        <span className="text-ink-500 ml-1">{c.status}</span>
                        {c.gpu_index != null && <span className="text-ink-600 ml-1">GPU{c.gpu_index}</span>}
                      </span>
                    ))}
                  </div>
                )}
                {/* Deploy button */}
                <div className="flex items-center gap-3 pt-1">
                  <button
                    className="btn-sm bg-success/10 text-success border-success/30 hover:bg-success/20"
                    disabled={deploying || status.gpus.every(g => g.busy)}
                    onClick={handleDeploy}
                  >
                    {deploying
                      ? <><i className="fas fa-spinner animate-spin mr-1" />部署中...</>
                      : <><i className="fas fa-plus mr-1" />部署新 Worker</>}
                  </button>
                  {deployMsg && <span className="text-ink-400">{deployMsg}</span>}
                  {status.gpus.every(g => g.busy) && (
                    <span className="text-ink-500">所有 GPU 已占用</span>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    )
  }

  export default function HostsPanel({ onWorkersChanged }: Props) {
    const [hosts, setHosts]           = useState<Host[]>([])
    const [loading, setLoading]       = useState(false)
    const [showDrawer, setShowDrawer] = useState(false)
    const [probingId, setProbingId]   = useState<number | null>(null)
    const [expandedId, setExpandedId] = useState<number | null>(null)

    const refresh = useCallback(async () => {
      setLoading(true)
      try { setHosts(await fetchHosts()) } finally { setLoading(false) }
    }, [])

    // Load on mount
    useState(() => { refresh() })

    const handleAddHost = async (req: AddHostRequest) => {
      await addHost(req)
      setShowDrawer(false)
      await refresh()
    }

    const handleDelete = async (id: number) => {
      if (!confirm('删除该主机将同时销毁其所有 Worker，确认继续？')) return
      await deleteHost(id)
      await refresh()
      onWorkersChanged()
    }

    const handleProbe = async (id: number) => {
      setProbingId(id)
      setExpandedId(id)
      try { await refresh() } finally { setProbingId(null) }
    }

    return (
      <div className="form-section mb-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="tag text-ink-400">远端主机</span>
            {loading && <i className="fas fa-spinner animate-spin text-ink-600 text-[10px]" />}
          </div>
          <button
            className="btn-sm bg-sky2/10 text-sky2 border-sky2/30 hover:bg-sky2/20"
            onClick={() => setShowDrawer(true)}
          >
            <i className="fas fa-plus mr-1" />添加主机
          </button>
        </div>

        {hosts.length === 0 ? (
          <p className="text-[11px] text-ink-600 py-2">暂无注册主机。点击"添加主机"开始配置。</p>
        ) : (
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-ink-500 border-b border-ink-800">
                <th className="text-left py-1.5 pr-4 font-normal">标签</th>
                <th className="text-left py-1.5 pr-4 font-normal">IP</th>
                <th className="text-left py-1.5 pr-4 font-normal">用户</th>
                <th className="text-left py-1.5 pr-4 font-normal">Worker</th>
                <th className="text-right py-1.5 font-normal">操作</th>
              </tr>
            </thead>
            <tbody>
              {hosts.map(h => (
                <>
                  <tr key={h.id} className="border-b border-ink-800/50">
                    <td className="py-2 pr-4 text-ink-200 font-medium">{h.label}</td>
                    <td className="py-2 pr-4 font-mono text-ink-300">{h.host}:{h.port}</td>
                    <td className="py-2 pr-4 text-ink-400">{h.username}</td>
                    <td className="py-2 pr-4">
                      {h.worker_count > 0
                        ? <span className="chip chip-run">{h.worker_count} 运行</span>
                        : <span className="text-ink-600">—</span>}
                    </td>
                    <td className="py-2 text-right">
                      <div className="flex items-center gap-1.5 justify-end">
                        <button
                          className="btn-sm"
                          disabled={probingId === h.id}
                          onClick={() => handleProbe(h.id)}
                        >
                          {probingId === h.id
                            ? <i className="fas fa-spinner animate-spin" />
                            : <><i className="fas fa-satellite-dish mr-1" />探测</>}
                        </button>
                        <button
                          className="btn-sm text-red-400 border-red-400/30 hover:bg-red-400/10"
                          onClick={() => handleDelete(h.id)}
                        >
                          <i className="fas fa-trash" />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {expandedId === h.id && (
                    <tr key={`${h.id}-probe`}>
                      <td colSpan={5} className="pb-2">
                        <ProbeRow
                          hostId={h.id}
                          onDeployed={() => { onWorkersChanged(); refresh() }}
                        />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}

        {showDrawer && (
          <AddHostDrawer
            onSave={handleAddHost}
            onClose={() => setShowDrawer(false)}
          />
        )}
      </div>
    )
  }
  ```

- [ ] **Step 2: Add destroy button to worker cards in WorkersView.tsx**

  In `WorkersView.tsx`, add the `destroyWorker` import and a destroy button inside each worker card's stats bar. Open the file and make these changes:

  Add import at the top:
  ```tsx
  import { destroyWorker } from '../api'
  import HostsPanel from './HostsPanel'
  ```

  Change the component signature to accept a refresh callback:
  ```tsx
  interface Props {
    workers:      Worker[]
    onOpenModal:  (id: number) => void
    onRefresh:    () => void   // added
  }

  export default function WorkersView({ workers, onOpenModal, onRefresh }: Props) {
  ```

  Add `<HostsPanel onWorkersChanged={onRefresh} />` as the first child inside the outer `<div className="overflow-y-auto p-5 space-y-5">`:
  ```tsx
  <div className="overflow-y-auto p-5 space-y-5">
    <HostsPanel onWorkersChanged={onRefresh} />
    {/* Ray cluster overview — existing code unchanged */}
    <div className="form-section">
  ```

  Inside the worker card's `{!w.busy && ...}` block, add a destroy button after the existing one:
  ```tsx
  {!w.busy && (
    <div className="flex gap-1.5 mt-1">
      <button className="btn-sm flex-1" onClick={() => onOpenModal(w.id)}>
        <i className="fas fa-plus mr-1" />分配任务
      </button>
      <button
        className="btn-sm text-red-400 border-red-400/30 hover:bg-red-400/10"
        title="销毁 Worker"
        onClick={async () => {
          if (!confirm(`销毁 Worker #${w.id}？`)) return
          // Find host_id: workers now have it from DB via /api/workers
          await destroyWorker((w as any).host_id ?? 0, w.id)
          onRefresh()
        }}
      >
        <i className="fas fa-trash" />
      </button>
    </div>
  )}
  ```

- [ ] **Step 3: Update App.tsx to pass onRefresh to WorkersView**

  In `App.tsx`, find the `WorkersView` render and add `onRefresh`:

  ```tsx
  {view === 'workers' && (
    <WorkersView
      workers={workers}
      onOpenModal={setModalWorker}
      onRefresh={refreshWorkers}
    />
  )}
  ```

  Also add `host_id` to the `/api/workers` response so the destroy button can use it. Back in `backend/main.py`, in the `get_workers` function, the response already includes all `w` fields from DB — ensure `host_id` is included:

  ```python
  results.append({
      "id":              w["worker_id"],
      "host_id":         w["host_id"],      # ← add this
      "host":            host_row["host"] if host_row else "unknown",
      ...
  })
  ```

  And add `host_id` to the `Worker` type in `types.ts`:
  ```typescript
  export interface Worker {
    id:              number
    host_id:         number    // ← add this
    host:            string
    http_port:       number
    ...
  }
  ```

- [ ] **Step 4: Build and verify**

  ```bash
  cd /home/disk/lrx/robot-eval/frontend
  npm run build 2>&1 | tail -30
  ```

  Expected: build succeeds with no TypeScript errors.

- [ ] **Step 5: Commit**

  ```bash
  git add frontend/src/components/HostsPanel.tsx \
          frontend/src/components/WorkersView.tsx \
          frontend/src/App.tsx \
          frontend/src/types.ts \
          backend/main.py
  git commit -m "feat: HostsPanel UI, destroy button, WorkersView integration"
  ```

---

## Task 7: End-to-End Test + docker-compose Rebuild

**Files:**
- No new files — validation and integration only.

- [ ] **Step 1: Rebuild and start all services**

  ```bash
  cd /home/disk/lrx/robot-eval
  docker-compose build platform
  docker-compose up -d postgres
  sleep 5
  docker-compose up -d platform
  docker-compose logs -f platform 2>&1 | head -40
  ```

  Expected log lines:
  ```
  [entrypoint] Generated new HOST_SECRET_KEY   (first run only)
  [platform] Ray connected: ray://127.0.0.1:10001
  ```

- [ ] **Step 2: Verify API from host**

  ```bash
  curl -s http://localhost:8000/api/hosts     # → []
  curl -s http://localhost:8000/api/workers   # → []
  curl -s http://localhost:8000/api/jobs      # → []
  ```

- [ ] **Step 3: Add a host via UI**

  Open `http://localhost:8000` → 集群 tab → click "添加主机" → fill in a real or test host → Save. Verify the host appears in the table.

- [ ] **Step 4: Probe the host**

  Click "探测" on the newly added host. Verify the probe row expands showing GPU info, memory, disk, and containers.

- [ ] **Step 5: Verify persistence across restart**

  ```bash
  docker-compose restart platform
  sleep 5
  curl -s http://localhost:8000/api/hosts   # → host still present
  ```

- [ ] **Step 6: Final commit**

  ```bash
  git add .
  git commit -m "feat: worker management complete — hosts UI, SSH probe, deploy, destroy"
  ```

---

## Self-Review Notes

- **Spec Section 2 (multi-process):** Covered in Task 1 (entrypoint.sh + Gunicorn) and Task 2 (lifespan, no globals). ✓
- **Spec Section 3 (schema):** Covered in Task 1 db.py. ✓
- **Spec Section 4 (all 6 endpoints):** Covered in Task 4. ✓
- **Spec Section 5 (host_manager public interface):** All 6 functions implemented in Task 3. ✓
- **Spec Section 6 (HostsPanel, drawer, probe expand, destroy):** Covered in Task 6. ✓
- **Spec Section 7 (docker-compose changes):** Covered in Task 1. ✓
- **Spec Section 9 (error handling):** SSH errors return `error` field in probe; 409 on no-GPU; background task sets `error` status; restart re-registers actors. ✓
- **HOST_SECRET_KEY auto-generation:** entrypoint.sh in Task 1. ✓
- **Password never returned:** `pop("password_enc")` in `list_hosts`/`add_host`, no password field in API responses. ✓
- **WORKERS_META removed:** Checked — `_workers_meta` global removed in Task 2, env var removed from docker-compose in Task 1. ✓
