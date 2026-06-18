# Worker Management — Design Spec
**Date:** 2026-06-18  
**Status:** Approved

---

## 1. Overview

Replace the static `WORKERS_META` env-var approach with a UI-driven worker management system. Users can register remote hosts, probe their GPU/resource status, and deploy/destroy Isaac Sim worker containers — all from the platform frontend, without editing config files or restarting the platform.

---

## 2. Architecture

```
frontend (React)
    │
    ▼
backend/main.py  ──── Gunicorn + 4× UvicornWorker (multi-process)
    │
    ├── backend/host_manager.py   # SSH, probe, deploy, destroy
    └── backend/db.py             # PostgreSQL via asyncpg
         └── postgres container (docker-compose)
```

**Multi-process:** `gunicorn -k uvicorn.workers.UvicornWorker -w 4`. Each process holds its own `asyncpg` connection pool. All shared state lives in PostgreSQL — no in-process globals.

**SSH credentials:** Encrypted with `cryptography.fernet.Fernet`. The encryption key is read from env var `HOST_SECRET_KEY`. On first platform startup, a key is auto-generated and written to `.env` so it survives container restarts.

**WORKERS_META env var:** Deprecated. At runtime, active workers are read from `remote_workers WHERE status='running'`.

---

## 3. Database Schema

Existing `jobs` and `logs` tables migrate from SQLite to PostgreSQL unchanged.

```sql
-- Registered remote hosts
CREATE TABLE hosts (
    id           SERIAL PRIMARY KEY,
    label        TEXT NOT NULL,
    host         TEXT NOT NULL,        -- IP or hostname
    port         INTEGER DEFAULT 22,
    username     TEXT NOT NULL,
    password_enc TEXT NOT NULL,        -- Fernet-encrypted ciphertext
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- Deployed worker instances
CREATE TABLE remote_workers (
    id              SERIAL PRIMARY KEY,
    host_id         INTEGER REFERENCES hosts(id) ON DELETE CASCADE,
    worker_id       INTEGER NOT NULL,   -- globally unique Ray actor ID
    gpu_index       INTEGER NOT NULL,   -- GPU index on the remote host
    http_port       INTEGER NOT NULL,   -- Kit HTTP port (8042 + offset)
    livestream_port INTEGER NOT NULL,   -- WebRTC port (49200 + offset)
    container_name  TEXT NOT NULL,
    status          TEXT DEFAULT 'deploying',  -- deploying|running|stopped|error
    deployed_at     TIMESTAMPTZ DEFAULT now(),
    stopped_at      TIMESTAMPTZ
);
```

Port allocation rule: `http_port = 8042 + worker_id`, `livestream_port = 49200 + worker_id`. `worker_id` is assigned as `MAX(worker_id) + 1` across all non-stopped workers globally.

---

## 4. Backend API

All new endpoints are added to `main.py` and delegate to `host_manager.py`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/hosts` | Register a host (save encrypted credentials) |
| `GET` | `/api/hosts` | List all hosts with last-known probe summary |
| `DELETE` | `/api/hosts/{host_id}` | Remove host and destroy all its workers |
| `POST` | `/api/hosts/{host_id}/probe` | SSH probe: GPU, CPU, memory, disk, containers, ports |
| `POST` | `/api/hosts/{host_id}/deploy` | Deploy one worker (auto-select GPU + ports) |
| `DELETE` | `/api/hosts/{host_id}/workers/{worker_id}` | Destroy a specific worker |

### `POST /api/hosts/{host_id}/probe` — response shape

```json
{
  "host_id": 1,
  "probed_at": "2026-06-18T10:00:00Z",
  "gpus": [
    { "index": 0, "name": "RTX 4090", "vram_total_mb": 24576,
      "vram_free_mb": 24000, "utilization_pct": 2, "busy": false }
  ],
  "memory": { "total_mb": 131072, "used_mb": 42000 },
  "disk":   { "path": "/", "total_gb": 2000, "used_gb": 800 },
  "containers": [
    { "name": "isaac-lab-worker-0", "status": "running", "gpu_index": 0 }
  ],
  "used_ports": [8042, 49200]
}
```

### `POST /api/hosts/{host_id}/deploy` — logic

1. Call `probe_host()` to get current GPU and port state.
2. Select the first GPU where `busy=false` and no existing `remote_workers` row with `status='running'` on that GPU.
3. Compute `worker_id = MAX(worker_id)+1`, `http_port = 8042 + worker_id`, `livestream_port = 49200 + worker_id`.
4. SSH → `docker run -d --runtime=nvidia --network=host --gpus device=<gpu_index> -e WORKER_ID=<n> -e HTTP_PORT=<p> -e LIVESTREAM_PORT=<p2> ... isaaclab_arena:latest`.
5. Insert row into `remote_workers` with `status='deploying'`.
6. Background task polls `docker inspect` every 5 s for up to 60 s; sets status to `running` or `error`.
7. On `running`: register Ray actor via existing `_create_actors()` logic.

---

## 5. `host_manager.py` Module

```python
# Public interface
async def add_host(label, host, port, username, password) -> Host
async def list_hosts() -> list[Host]
async def delete_host(host_id) -> None

async def probe_host(host_id) -> HostStatus
async def deploy_worker(host_id) -> RemoteWorker
async def destroy_worker(host_id, worker_id) -> None

# Internal
def _encrypt(plaintext: str) -> str   # Fernet encrypt
def _decrypt(ciphertext: str) -> str  # Fernet decrypt
async def _ssh_run(host, port, user, password, cmd) -> str  # paramiko exec
```

`paramiko` is used for SSH (synchronous calls wrapped in `asyncio.to_thread`). Connections are short-lived per-operation — no persistent SSH connection pool needed.

---

## 6. Frontend

### New component: `HostsPanel.tsx`

Rendered at the top of `WorkersView.tsx`, above the existing worker cards.

**Host table:**
```
┌─────────────────────────────────────────────────────┐
│ 远端主机                              [+ 添加主机]   │
├──────────┬──────────┬────────┬────────┬─────────────┤
│ 标签     │ IP       │ 状态   │ Worker │ 操作        │
├──────────┼──────────┼────────┼────────┼─────────────┤
│ GPU-A    │ 10.0.0.2 │ ●在线  │ 2 运行 │ [探测][部署]│
│ GPU-B    │ 10.0.0.3 │ ○离线  │ —      │ [探测]      │
└──────────┴──────────┴────────┴────────┴─────────────┘
```

**Add host — slide-in drawer (right side):**
- Fields: 标签, IP, SSH端口 (default 22), 用户名, 密码
- Password field is `type="password"`, never echoed back from API
- Submit → `POST /api/hosts`

**Probe result — inline expand row:**
- Triggered by `[探测]` button → `POST /api/hosts/{id}/probe`
- Shows: GPU list (name, VRAM, free/busy), memory, disk, running containers, occupied ports
- `[部署新 Worker]` button at bottom-right → `POST /api/hosts/{id}/deploy`
- Deploy shows a spinner then updates the worker cards section on success

**Destroy worker:** Each worker card gains a `[销毁]` button → `DELETE /api/hosts/{host_id}/workers/{worker_id}` with a confirmation dialog.

### Modified: `WorkersView.tsx`

- Import and render `<HostsPanel />` above the worker grid.
- Worker grid now reads from `/api/workers` which queries `remote_workers WHERE status='running'`.

### New type additions to `types.ts`

```typescript
interface Host {
  id: number; label: string; host: string; port: number; username: string
}
interface HostStatus {
  host_id: number; probed_at: string
  gpus: GpuInfo[]; memory: MemInfo; disk: DiskInfo
  containers: ContainerInfo[]; used_ports: number[]
}
interface RemoteWorker {
  id: number; host_id: number; worker_id: number
  gpu_index: number; http_port: number; livestream_port: number
  container_name: string; status: string
}
```

---

## 7. Docker Compose Changes

```yaml
services:
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

  platform:
    # change command:
    command: gunicorn backend.main:app
               -k uvicorn.workers.UvicornWorker
               -w 4 --bind 0.0.0.0:8000
    environment:
      - DATABASE_URL=postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval
      - HOST_SECRET_KEY=<auto-generated on first run>
    depends_on:
      - postgres
      - ray-head
```

`WORKERS_META` env var is removed from the platform service.

---

## 8. Dependency Changes

**`backend/requirements.txt` additions:**
```
asyncpg>=0.29
gunicorn>=22.0
paramiko>=3.4
cryptography>=42.0
```

---

## 9. Error Handling

| Scenario | Behaviour |
|----------|-----------|
| SSH connection fails (wrong password, unreachable) | Probe returns `{ "error": "SSH failed: ..." }`, host row status shown as "连接失败" |
| No free GPU on host | Deploy returns 409 with `"no free GPU available"` |
| Docker run fails on remote | Worker status set to `error`, container logs captured and returned |
| Worker container exits unexpectedly | Background health-check sets status to `error`; frontend shows error chip on worker card |
| Platform restart | `startup` event re-reads `remote_workers WHERE status='running'` and re-registers Ray actors |

---

## 10. Out of Scope

- SSH key authentication (password only for now)
- Multi-host Ray cluster spanning different subnets
- Automatic worker auto-scaling based on job queue depth
