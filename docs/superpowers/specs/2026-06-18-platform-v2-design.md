# Robot Eval Platform v2 — Design Spec
**Date:** 2026-06-18  
**Status:** Approved  
**Scope:** Full rewrite — open-source, general-purpose eval platform with Arena, Elo, pluggable Runners

---

## 1. Goals & Constraints

| Goal | Detail |
|---|---|
| Open-source, self-hosted | No auth/account system; anyone can fork and deploy |
| General-purpose | Pluggable Runner layer: robots (Isaac Lab), LLMs (LM-Eval/OpenCompass), VLA, custom scripts |
| Arena / competitive ranking | Full match scheduling, Elo/Glicko-2, blind mode, significance testing |
| Observability | Structured logging + job status; no tracing infrastructure required |
| Storage | PostgreSQL + asyncpg (already migrated) |
| Code approach | Full rewrite — clean structure, no legacy compatibility shims |

---

## 2. System Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Frontend (React + Vite)              │
│  Dashboard | Jobs | Results | Analysis | Arena |      │
│  Leaderboard | Templates                              │
└────────────────────────┬─────────────────────────────┘
                         │ HTTP / SSE
┌────────────────────────▼─────────────────────────────┐
│              FastAPI Backend (/app/backend/)          │
│                                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ Job Engine  │  │ Arena Engine │  │ Analysis    │ │
│  │ lifecycle   │  │ match/elo    │  │ Engine      │ │
│  └──────┬──────┘  └──────┬───────┘  └──────┬──────┘ │
│         └────────────────┼──────────────────┘        │
│                          │                            │
│  ┌───────────────────────▼──────────────────────┐    │
│  │           Runner Plugin Layer                 │    │
│  │  IsaacLabRunner | RemotePolicyRunner |        │    │
│  │  LMEvalRunner | OpenCompassRunner |           │    │
│  │  SubprocessRunner                             │    │
│  └───────────────────────┬──────────────────────┘    │
└──────────────────────────┼───────────────────────────┘
                           │ Ray remote call
┌──────────────────────────▼───────────────────────────┐
│           Ray Cluster (GPU Workers)                   │
│           IsaacLabArenaActor × N                      │
└──────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────┐
│                    PostgreSQL                         │
│  templates | jobs | runs | episodes                   │
│  matches | match_runs | elo_ratings                   │
│  hosts | remote_workers                               │
└──────────────────────────────────────────────────────┘
```

---

## 3. Directory Structure (rewrite target)

```
backend/
  engines/
    job_engine.py        # lifecycle: create/schedule/retry/cancel/reproduce
    arena_engine.py      # match scheduling, blind mode, judge
    analysis_engine.py   # compare, trend, regression
  runners/
    base.py              # BaseRunner ABC + RunResult dataclass
    isaaclab_runner.py   # Ray Actor dispatch
    remote_policy.py     # HTTP Policy Server
    lmeval_runner.py     # lm-evaluation-harness subprocess
    opencompass_runner.py
    subprocess_runner.py # generic CLI wrapper
    registry.py          # runner discovery + YAML registration
  elo/
    calculator.py        # Elo + Glicko-2 math
    significance.py      # bootstrap CI, p-value
  db/
    schema.py            # CREATE TABLE migrations
    queries/
      jobs.py
      runs.py
      episodes.py
      matches.py
      elo.py
  api/
    jobs.py
    runs.py
    arena.py
    analysis.py
    workers.py
    templates.py
  main.py                # FastAPI app + lifespan
  base_actor.py          # unchanged
  arena_actor.py         # unchanged

frontend/src/
  components/
    DashboardView.tsx    # + trend mini-charts, recent regression
    JobsView.tsx         # + retry count, reproduce button
    ResultsView.tsx      # + episode detail, compare selector
    AnalysisView.tsx     # NEW: compare table, trend chart
    ArenaView.tsx        # NEW: start match, match list, Elo board
    LeaderboardView.tsx  # upgraded: Elo score, CI, match matrix
    TemplatesView.tsx    # NEW: template management, YAML editor
```

---

## 4. Database Schema

### 4.1 templates
```sql
CREATE TABLE templates (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    version     TEXT NOT NULL DEFAULT '1.0',
    runner_type TEXT NOT NULL,           -- 'isaaclab' | 'lmeval' | 'subprocess' | ...
    config_yaml TEXT NOT NULL,           -- full YAML blob
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(name, version)
);
```

### 4.2 jobs
```sql
-- Note: baseline_run_id FK to runs added after runs table is created (deferred in schema.py)
CREATE TABLE jobs (
    id              TEXT PRIMARY KEY,    -- uuid8
    name            TEXT NOT NULL,
    template_id     INTEGER REFERENCES templates(id),
    model_name      TEXT,
    submitter       TEXT,
    policy_config   JSONB DEFAULT '{}',
    policy_server_url TEXT DEFAULT '',
    status          TEXT DEFAULT 'pending',
    retry_count     INTEGER DEFAULT 0,
    max_retries     INTEGER DEFAULT 3,
    timeout_s       INTEGER DEFAULT 3600,
    baseline_run_id TEXT,               -- FK to runs(id), added after runs table
    description     TEXT,
    created_at      DOUBLE PRECISION,
    updated_at      DOUBLE PRECISION
);
```

### 4.3 runs
```sql
CREATE TABLE runs (
    id          TEXT PRIMARY KEY,        -- uuid8
    job_id      TEXT REFERENCES jobs(id),
    attempt     INTEGER DEFAULT 0,       -- retry index
    worker_id   INTEGER,
    status      TEXT DEFAULT 'pending',  -- pending|running|done|failed
    metrics     JSONB DEFAULT '{}',      -- {"success_rate": 0.8, "uph": 120, ...}
    seed        BIGINT,
    elapsed_s   DOUBLE PRECISION,
    error_msg   TEXT,
    started_at  DOUBLE PRECISION,
    finished_at DOUBLE PRECISION
);
```

### 4.4 episodes
```sql
CREATE TABLE episodes (
    id                 SERIAL PRIMARY KEY,
    run_id             TEXT REFERENCES runs(id),
    episode_index      INTEGER,
    success            BOOLEAN,
    reward_total       DOUBLE PRECISION,
    steps              INTEGER,
    termination_reason TEXT,             -- 'success'|'timeout'|'dropped'|...
    metadata           JSONB DEFAULT '{}'
);
```

### 4.5 matches
```sql
CREATE TABLE matches (
    id          TEXT PRIMARY KEY,
    env_name    TEXT NOT NULL,
    template_id INTEGER REFERENCES templates(id),
    seed        BIGINT,
    mode        TEXT DEFAULT 'direct',   -- direct|swiss|round_robin
    status      TEXT DEFAULT 'pending',  -- pending|running|done
    model_a     TEXT NOT NULL,
    model_b     TEXT NOT NULL,
    winner      TEXT,                    -- 'a'|'b'|'draw'|null
    is_blind    BOOLEAN DEFAULT false,
    judge_config JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE match_runs (
    match_id TEXT REFERENCES matches(id),
    model    TEXT,                       -- 'a' or 'b'
    run_id   TEXT REFERENCES runs(id),
    PRIMARY KEY (match_id, model)
);
```

### 4.6 elo_ratings
```sql
CREATE TABLE elo_ratings (
    id          SERIAL PRIMARY KEY,
    model_name  TEXT NOT NULL,
    env_name    TEXT NOT NULL,
    rating      DOUBLE PRECISION DEFAULT 1500,
    rd          DOUBLE PRECISION DEFAULT 350,   -- Glicko-2 rating deviation
    volatility  DOUBLE PRECISION DEFAULT 0.06,  -- Glicko-2 volatility
    updated_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(model_name, env_name)
);

CREATE TABLE elo_history (
    id          SERIAL PRIMARY KEY,
    model_name  TEXT NOT NULL,
    env_name    TEXT NOT NULL,
    rating      DOUBLE PRECISION,
    rd          DOUBLE PRECISION,
    match_id    TEXT REFERENCES matches(id),
    recorded_at TIMESTAMPTZ DEFAULT now()
);
```

### 4.7 hosts & remote_workers
*(already exists in current db.py — keep as-is)*

---

## 5. Job Engine

### 5.1 Lifecycle State Machine
```
pending → running → done
             ↓         ↓
           failed → retry_pending → running  (attempt < max_retries)
             ↓
         failed_final  (attempt >= max_retries)
             ↓
         cancelled     (user cancel at any state)
```

### 5.2 Scheduler (replaces polling loop)
```python
class JobScheduler:
    _queue: asyncio.Queue[str]     # job_ids waiting for a free actor
    _free_actors: asyncio.Queue    # actor names that just became free
    
    async def enqueue(job_id): ...
    async def _dispatch_loop(): ...  # background task: queue → actor
    async def _on_actor_free(actor_name): ...
```
- No more 60×5s polling — actors signal free via `_free_actors` queue
- Retry: exponential backoff `2^attempt` seconds before re-enqueue

### 5.3 Key APIs
```
POST   /api/jobs                    create + enqueue
GET    /api/jobs                    list (filter: status, model, env, submitter)
GET    /api/jobs/{id}               detail with latest run
DELETE /api/jobs/{id}               cancel + kill actor
POST   /api/jobs/{id}/reproduce     clone job with same config+seed
GET    /api/jobs/{id}/regression    delta vs baseline_run_id
PUT    /api/runs/{id}/set-baseline  mark run as baseline for its job
GET    /api/jobs/{id}/logs          SSE stream
```

---

## 6. Runner Plugin Layer

### 6.1 BaseRunner ABC
```python
class BaseRunner(ABC):
    @abstractmethod
    async def run(self, config: dict, seed: int) -> RunResult: ...
    
    @abstractmethod
    def health_check(self) -> bool: ...

@dataclass
class RunResult:
    metrics:  dict                  # arbitrary key/value
    episodes: list[EpisodeResult]
    elapsed_s: float
    seed:     int
    raw_output: str = ""

@dataclass
class EpisodeResult:
    index:              int
    success:            bool
    reward_total:       float
    steps:              int
    termination_reason: str
    metadata:           dict = field(default_factory=dict)
```

### 6.2 Runner Registry
```python
# runners/registry.py
_REGISTRY: dict[str, type[BaseRunner]] = {
    "isaaclab":    IsaacLabRunner,
    "remote_policy": RemotePolicyRunner,
    "lmeval":      LMEvalRunner,
    "opencompass": OpenCompassRunner,
    "subprocess":  SubprocessRunner,
}

def get_runner(runner_type: str, config: dict) -> BaseRunner: ...
def register_runner(name: str, cls: type[BaseRunner]): ...  # plugin entry point
```

Custom runners: drop a Python file in `runners/` and add to `configs/runners.yaml`.

### 6.3 EvalTemplate YAML format
```yaml
name: lift_object
version: "1.0"
runner: isaaclab
runner_config:
  environment: lift_object
  embodiment: franka_joint_pos
  num_envs: 1
metrics:
  - name: success_rate
    type: ratio
    higher_is_better: true
  - name: uph
    type: float
    higher_is_better: true
episodes: 50
timeout_s: 3600
judge:
  type: metric_compare
  metric: success_rate
  tiebreak: uph
  min_diff: 0.02          # diff < 2% → draw
```

---

## 7. Arena Engine

### 7.1 Match Scheduling Modes

| Mode | Description |
|---|---|
| `direct` | Caller specifies model_a + model_b explicitly |
| `swiss` | System pairs models with closest Elo ratings |
| `round_robin` | All submitted models play each other once |

### 7.2 Blind Mode
- `is_blind=true`: `/api/arena/matches/{id}` returns `model_b = "?"` until `status=done`
- Prevents submitters from gaming against a known opponent

### 7.3 Judge
```python
class MetricCompareJudge:
    def judge(self, result_a: RunResult, result_b: RunResult,
              config: dict) -> Literal["a", "b", "draw"]:
        diff = result_a.metrics[config["metric"]] - result_b.metrics[config["metric"]]
        if abs(diff) < config["min_diff"]: return "draw"
        return "a" if diff > 0 else "b"
```
Future: `LLMJudge`, `HumanJudge` implementing same interface.

### 7.4 Elo/Glicko-2
```python
# elo/calculator.py
def update_glicko2(
    winner: GlickoPlayer, loser: GlickoPlayer
) -> tuple[GlickoPlayer, GlickoPlayer]: ...

@dataclass
class GlickoPlayer:
    rating:     float = 1500.0
    rd:         float = 350.0    # rating deviation
    volatility: float = 0.06
```
- New models start at rating=1500, rd=350 (wide CI)
- rd shrinks as matches accumulate
- Leaderboard shows `rating ± 2×rd` as 95% confidence interval

### 7.5 Significance Testing
```python
# elo/significance.py
def bootstrap_ci(
    successes_a: list[bool], successes_b: list[bool],
    n_bootstrap: int = 1000, alpha: float = 0.05
) -> SignificanceResult:
    """Returns CI for (rate_a - rate_b) and whether it excludes 0."""
```

### 7.6 Arena APIs
```
POST /api/arena/matches              create match (direct/swiss/round_robin)
GET  /api/arena/matches              list matches
GET  /api/arena/matches/{id}         detail (blind: model_b hidden until done)
GET  /api/arena/leaderboard          Elo rankings per env
GET  /api/arena/models/{name}        model profile + Elo history
GET  /api/arena/matrix?env=...       win-rate matrix (N×N heatmap data)
```

---

## 8. Analysis Engine

### 8.1 Compare
```
GET /api/analysis/compare?runs=id1,id2,id3
Response:
{
  "runs": [...],
  "metrics": {
    "success_rate": {"id1": 0.72, "id2": 0.81, "id3": 0.68, "best": "id2"},
    "uph":          {"id1": 110,  "id2": 135,  "id3": 98,  "best": "id2"}
  },
  "episodes": [
    {"index": 0, "id1": true, "id2": true,  "id3": false},
    ...
  ]
}
```

### 8.2 Trend
```
GET /api/analysis/trend?model=pi0&env=lift_object&days=30
Response: time-series of success_rate per run, sorted by finished_at
```

### 8.3 Regression Report
```
GET /api/jobs/{id}/regression
Response:
{
  "baseline_run_id": "abc123",
  "current_run_id":  "def456",
  "deltas": [
    {
      "metric": "success_rate",
      "baseline": 0.72, "current": 0.68,
      "delta": -0.04, "delta_pct": -5.6,
      "significant": true,
      "ci_95": [-0.08, -0.01]
    }
  ]
}
```

---

## 9. Frontend Pages

| Page | Key additions vs current |
|---|---|
| **Dashboard** | Trend sparklines per env, recent regression alerts (red if significant drop) |
| **Jobs** | Retry count badge, "Reproduce" button, "Set as Baseline" on run detail |
| **Results** | Episode detail accordion (success/fail per episode), multi-select for compare |
| **Analysis** *(new)* | Multi-run compare table with highlight, trend line chart |
| **Arena** *(new)* | "New Match" form, match list with status, Elo leaderboard per env |
| **Leaderboard** | Elo score + ±CI, win-rate matrix heatmap, Elo history line chart |
| **Templates** *(new)* | YAML editor, version list, "Run Benchmark" button |

---

## 10. Observability (minimal)

- All `print()` replaced with `structlog` JSON lines → stdout
- Job state transitions logged as structured events: `{"event": "job.state", "job_id": ..., "from": "pending", "to": "running"}`
- `elapsed_s` correctly computed and stored in `runs` table
- `/api/health` endpoint: DB ping + Ray cluster reachable

---

## 11. Implementation Phases

### Phase 1 — Foundation (prerequisite for everything)
1. DB schema migration (templates, runs, episodes, matches, elo tables)
2. Runner plugin layer (BaseRunner, RunResult, IsaacLabRunner refactor)
3. Job Engine rewrite (scheduler queue, retry, cancel, reproduce)
4. API restructure (`/api/jobs`, `/api/runs`, `/api/templates`)

### Phase 2 — Evaluation Body
5. EvalTemplate CRUD + YAML validation
6. Episode-level data capture in IsaacLabRunner
7. Analysis Engine (compare, trend, regression)
8. Frontend: Jobs + Results + Analysis pages

### Phase 3 — Arena
9. Arena Engine (match creation, scheduling modes, judge)
10. Elo/Glicko-2 calculator + significance testing
11. Arena APIs
12. Frontend: Arena + upgraded Leaderboard pages

### Phase 4 — Extra Runners & Polish
13. LMEvalRunner (subprocess wrapper)
14. SubprocessRunner (generic CLI)
15. Templates page frontend
16. Structured logging (structlog)
17. `/api/health` endpoint

---

## 12. Out of Scope

- User authentication / authorization
- Multi-tenant isolation
- CI/CD pipeline integration
- Kubernetes deployment (docker-compose only)
- Real-time step-level streaming from episodes (batch only)
