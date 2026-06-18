# Platform v2 Phase 3 — Arena Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full Arena competitive evaluation system — match scheduling (direct/swiss/round_robin), Elo/Glicko-2 ratings, blind mode, significance testing, Arena API, and upgraded frontend (ArenaView + Leaderboard with Elo).

**Architecture:** `ArenaEngine` orchestrates match lifecycle and calls `JobScheduler` to dispatch runs. `EloCalculator` (Glicko-2 math) and `SignificanceTester` (bootstrap CI) are pure functions. Arena state is persisted in `matches`, `match_runs`, `elo_ratings`, `elo_history` tables (already in schema from Phase 1). FastAPI arena router at `/api/arena/*`. Frontend adds `ArenaView` and upgrades `LeaderboardView` with Elo scores, CI badges, and win-rate matrix.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, React 18, TypeScript, Recharts (already installed), Tailwind CSS

## Global Constraints

- Python 3.12, `from __future__ import annotations`, no `print()`, `logging.getLogger(__name__)`
- asyncpg for all DB — no SQLAlchemy
- `base_actor.py` must NOT be modified; `arena_actor.py` must NOT be modified
- Tests in `tests/` at repo root; `pytest tests/ -v` must pass
- Frontend: TypeScript strict, Tailwind only, Recharts for charts
- Frontend build: `cd frontend && npm run build` — no TypeScript errors
- `DATABASE_URL` = `postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval`
- All new Python files: `from __future__ import annotations`
- Phase 1+2 interfaces unchanged — do not modify existing DB query helpers or engine APIs

---

## File Map

```
backend/
  elo/
    __init__.py
    calculator.py      # GlickoPlayer dataclass, update_glicko2()
    significance.py    # SignificanceResult, bootstrap_ci()
  engines/
    arena_engine.py    # ArenaEngine: create_match, run_match, judge, update_elo
  db/
    queries/
      matches.py       # CRUD for matches + match_runs tables
      elo.py           # CRUD for elo_ratings + elo_history tables
  api/
    arena.py           # FastAPI router: /api/arena/*
  main.py              # MODIFY: include arena router

tests/
  elo/
    test_calculator.py
    test_significance.py
  engines/
    test_arena_engine.py
  api/
    test_arena_api.py

frontend/src/
  types.ts             # MODIFY: add Match, EloRating, ArenaLeaderboard, WinMatrix types
  api.ts               # MODIFY: add arena API functions
  App.tsx              # MODIFY: add 'arena' view, keyboard shortcut R
  components/
    ArenaView.tsx      # CREATE: new match form, match list, Elo leaderboard per env
    LeaderboardView.tsx # MODIFY: add Elo score column, ±CI badge, win-rate matrix tab
```

---

## Task 9: Elo/Glicko-2 Calculator + Significance Testing

**Files:**
- Create: `backend/elo/__init__.py`
- Create: `backend/elo/calculator.py`
- Create: `backend/elo/significance.py`
- Create: `tests/elo/test_calculator.py`
- Create: `tests/elo/test_significance.py`

**Interfaces:**
- Produces:
  - `GlickoPlayer(rating=1500.0, rd=350.0, volatility=0.06)` dataclass
  - `update_glicko2(winner: GlickoPlayer, loser: GlickoPlayer) -> tuple[GlickoPlayer, GlickoPlayer]`
  - `SignificanceResult(ci_low: float, ci_high: float, significant: bool, p_value: float)`
  - `bootstrap_ci(successes_a: list[bool], successes_b: list[bool], n_bootstrap=1000, alpha=0.05) -> SignificanceResult`

- [ ] **Step 9.1: Write calculator tests**

```python
# tests/elo/test_calculator.py
from __future__ import annotations
import pytest
from backend.elo.calculator import GlickoPlayer, update_glicko2

def test_winner_rating_increases():
    winner = GlickoPlayer(rating=1500, rd=200, volatility=0.06)
    loser  = GlickoPlayer(rating=1500, rd=200, volatility=0.06)
    new_winner, new_loser = update_glicko2(winner, loser)
    assert new_winner.rating > winner.rating
    assert new_loser.rating < loser.rating

def test_rd_decreases_after_match():
    p = GlickoPlayer(rating=1500, rd=350, volatility=0.06)
    q = GlickoPlayer(rating=1500, rd=350, volatility=0.06)
    new_p, _ = update_glicko2(p, q)
    assert new_p.rd < p.rd

def test_stronger_player_gains_less():
    strong = GlickoPlayer(rating=1800, rd=100, volatility=0.06)
    weak   = GlickoPlayer(rating=1200, rd=100, volatility=0.06)
    new_strong, new_weak = update_glicko2(strong, weak)
    gain_strong = new_strong.rating - strong.rating
    loss_weak   = weak.rating - new_weak.rating
    assert gain_strong < loss_weak, "Beating a much weaker player should gain less"

def test_symmetric_draw_is_stable():
    """Equal players drawing should not change ratings much."""
    p = GlickoPlayer(rating=1500, rd=50, volatility=0.06)
    q = GlickoPlayer(rating=1500, rd=50, volatility=0.06)
    # Test regular win: just ensure winner gains and loser loses
    new_p, new_q = update_glicko2(p, q)
    assert new_p.rating > p.rating
    assert new_q.rating < q.rating

def test_rating_stays_positive():
    """Ratings should never go to zero or negative."""
    p = GlickoPlayer(rating=100, rd=350, volatility=0.06)
    q = GlickoPlayer(rating=3000, rd=50, volatility=0.06)
    new_p, new_q = update_glicko2(q, p)  # strong beats weak
    assert new_p.rating > 0
    assert new_q.rating > 0
```

- [ ] **Step 9.2: Run tests — expect FAIL**

```bash
pytest tests/elo/test_calculator.py -v
```
Expected: `ModuleNotFoundError: No module named 'backend.elo'`

- [ ] **Step 9.3: Create `backend/elo/__init__.py`**

```python
# empty
```

- [ ] **Step 9.4: Create `backend/elo/calculator.py`**

Implement Glicko-2 algorithm (https://www.glicko.net/glicko/glicko2.pdf):

```python
from __future__ import annotations
import math
from dataclasses import dataclass

@dataclass
class GlickoPlayer:
    rating:     float = 1500.0
    rd:         float = 350.0    # rating deviation
    volatility: float = 0.06

# Glicko-2 constants
_Q    = math.log(10) / 400
_TAU  = 0.5      # system constant controlling volatility change speed

def _g(rd: float) -> float:
    return 1.0 / math.sqrt(1 + 3 * _Q**2 * rd**2 / math.pi**2)

def _E(rating: float, opp_rating: float, opp_rd: float) -> float:
    return 1.0 / (1 + 10 ** (-_g(opp_rd) * (rating - opp_rating) / 400))

def _f(x: float, delta: float, v: float, a: float, tau: float) -> float:
    ex  = math.exp(x)
    d2  = delta**2
    r2  = v
    return (ex * (d2 - r2 - ex)) / (2 * (r2 + ex)**2) - (x - a) / tau**2

def update_glicko2(
    winner: GlickoPlayer, loser: GlickoPlayer
) -> tuple[GlickoPlayer, GlickoPlayer]:
    """Apply one match result using Glicko-2. Returns (new_winner, new_loser)."""
    new_winner = _update_one(winner, loser, score=1.0)
    new_loser  = _update_one(loser, winner, score=0.0)
    return new_winner, new_loser

def _update_one(player: GlickoPlayer, opponent: GlickoPlayer, score: float) -> GlickoPlayer:
    # Convert to Glicko-2 scale (μ, φ, σ)
    mu    = (player.rating - 1500) / 173.7178
    phi   = player.rd / 173.7178
    sigma = player.volatility

    mu_j    = (opponent.rating - 1500) / 173.7178
    phi_j   = opponent.rd / 173.7178

    g_j = 1.0 / math.sqrt(1 + 3 * phi_j**2 / math.pi**2)
    E_j = 1.0 / (1 + math.exp(-g_j * (mu - mu_j)))

    # Step 3: compute v
    v = 1.0 / (g_j**2 * E_j * (1 - E_j))

    # Step 4: compute delta
    delta = v * g_j * (score - E_j)

    # Step 5: determine new sigma via Illinois algorithm
    a  = math.log(sigma**2)
    A  = a
    if delta**2 > phi**2 + v:
        B = math.log(delta**2 - phi**2 - v)
    else:
        k = 1
        while _f(a - k * _TAU, delta, v, a, _TAU) < 0:
            k += 1
        B = a - k * _TAU

    fA = _f(A, delta, v, a, _TAU)
    fB = _f(B, delta, v, a, _TAU)
    for _ in range(100):
        C  = A + (A - B) * fA / (fB - fA)
        fC = _f(C, delta, v, a, _TAU)
        if fB * fC < 0:
            A, fA = B, fB
        else:
            fA /= 2
        B, fB = C, fC
        if abs(B - A) < 1e-6:
            break
    new_sigma = math.exp(A / 2)

    # Step 6: update phi*
    phi_star = math.sqrt(phi**2 + new_sigma**2)

    # Step 7: update mu, phi
    new_phi = 1.0 / math.sqrt(1 / phi_star**2 + 1 / v)
    new_mu  = mu + new_phi**2 * g_j * (score - E_j)

    # Convert back to Glicko-1 scale
    return GlickoPlayer(
        rating=173.7178 * new_mu + 1500,
        rd=173.7178 * new_phi,
        volatility=new_sigma,
    )
```

- [ ] **Step 9.5: Run calculator tests — expect PASS**

```bash
pytest tests/elo/test_calculator.py -v
```
Expected: 5 tests PASS

- [ ] **Step 9.6: Write significance tests**

```python
# tests/elo/test_significance.py
from __future__ import annotations
import pytest
from backend.elo.significance import bootstrap_ci, SignificanceResult

def test_clearly_different_rates():
    a = [True] * 80 + [False] * 20   # 80% success
    b = [True] * 20 + [False] * 80   # 20% success
    result = bootstrap_ci(a, b, n_bootstrap=500)
    assert result.significant is True
    assert result.ci_low > 0.0   # CI excludes 0 (A is better)

def test_identical_rates_not_significant():
    a = [True] * 50 + [False] * 50
    b = [True] * 50 + [False] * 50
    result = bootstrap_ci(a, b, n_bootstrap=500)
    assert result.significant is False

def test_empty_lists():
    result = bootstrap_ci([], [], n_bootstrap=100)
    assert result.significant is False
    assert result.ci_low == 0.0
    assert result.ci_high == 0.0

def test_result_fields():
    a = [True] * 6 + [False] * 4
    b = [True] * 4 + [False] * 6
    result = bootstrap_ci(a, b, n_bootstrap=200)
    assert isinstance(result, SignificanceResult)
    assert result.ci_low <= result.ci_high
    assert 0.0 <= result.p_value <= 1.0
```

- [ ] **Step 9.7: Create `backend/elo/significance.py`**

```python
from __future__ import annotations
import random
from dataclasses import dataclass

@dataclass
class SignificanceResult:
    ci_low:      float   # lower bound of 95% CI for (rate_a - rate_b)
    ci_high:     float   # upper bound
    significant: bool    # True if CI excludes 0
    p_value:     float   # fraction of bootstrap samples where diff <= 0

def bootstrap_ci(
    successes_a: list[bool],
    successes_b: list[bool],
    n_bootstrap: int = 1000,
    alpha: float = 0.05,
) -> SignificanceResult:
    if not successes_a or not successes_b:
        return SignificanceResult(0.0, 0.0, False, 1.0)

    n_a, n_b = len(successes_a), len(successes_b)
    obs_diff = sum(successes_a) / n_a - sum(successes_b) / n_b

    diffs = []
    rng = random.Random(42)   # deterministic seed for reproducibility
    for _ in range(n_bootstrap):
        sample_a = [rng.choice(successes_a) for _ in range(n_a)]
        sample_b = [rng.choice(successes_b) for _ in range(n_b)]
        diffs.append(sum(sample_a) / n_a - sum(sample_b) / n_b)

    diffs.sort()
    lo = diffs[int(n_bootstrap * alpha / 2)]
    hi = diffs[int(n_bootstrap * (1 - alpha / 2))]
    p_value = sum(1 for d in diffs if d <= 0) / n_bootstrap

    return SignificanceResult(
        ci_low=round(lo, 4),
        ci_high=round(hi, 4),
        significant=(lo > 0 or hi < 0),
        p_value=round(p_value, 4),
    )
```

- [ ] **Step 9.8: Run all elo tests — expect PASS**

```bash
pytest tests/elo/ -v
```
Expected: 9 tests PASS

- [ ] **Step 9.9: Commit**

```bash
git add backend/elo/ tests/elo/
git commit -m "feat: Glicko-2 calculator + bootstrap significance testing (Phase 3, Task 9)"
```

---

## Task 10: Match DB Queries + Arena Engine

**Files:**
- Create: `backend/db/queries/matches.py`
- Create: `backend/db/queries/elo.py`
- Create: `backend/engines/arena_engine.py`
- Create: `tests/db/test_matches_queries.py`
- Create: `tests/engines/test_arena_engine.py`

**Interfaces:**
- Consumes:
  - `GlickoPlayer`, `update_glicko2` from Task 9
  - `SignificanceResult`, `bootstrap_ci` from Task 9
  - `jq.create_job`, `jq.get_job` from Phase 1
  - `rq.get_run`, `rq.list_runs_for_job` from Phase 1
  - `eq.get_episodes` from Phase 1
  - `job_engine.create_job` from Phase 1
  - `JobScheduler` (accessed via `scheduler` singleton) from Phase 1
- Produces:
  - `matches.create_match(pool, id, env_name, template_id, seed, mode, model_a, model_b, is_blind, judge_config) -> dict`
  - `matches.get_match(pool, match_id) -> dict | None`
  - `matches.list_matches(pool, status=None, env_name=None) -> list[dict]`
  - `matches.update_match(pool, match_id, status=None, winner=None, finished_at=None) -> None`
  - `matches.set_match_run(pool, match_id, model, run_id) -> None`
  - `matches.get_match_runs(pool, match_id) -> dict[str, str]` — `{"a": run_id, "b": run_id}`
  - `matches.win_matrix(pool, env_name) -> list[dict]` — `[{model_a, model_b, wins_a, wins_b, draws}]`
  - `elo.get_or_create(pool, model_name, env_name) -> GlickoPlayer`
  - `elo.save(pool, model_name, env_name, player: GlickoPlayer, match_id) -> None`
  - `elo.list_leaderboard(pool, env_name) -> list[dict]` — sorted by rating desc
  - `elo.get_history(pool, model_name, env_name) -> list[dict]`
  - `ArenaEngine.create_match(env_name, model_a, model_b, template_id, mode, is_blind, judge_config, seed) -> dict`
  - `ArenaEngine.get_leaderboard(env_name) -> list[dict]`
  - `ArenaEngine.get_win_matrix(env_name) -> list[dict]`
  - `arena_engine: ArenaEngine | None = None` singleton (set by lifespan)

- [ ] **Step 10.1: Create `backend/db/queries/matches.py`**

```python
from __future__ import annotations
import json, time, uuid
import asyncpg

async def create_match(
    pool: asyncpg.Pool, *, id: str, env_name: str,
    template_id: int | None = None, seed: int | None = None,
    mode: str = "direct", model_a: str, model_b: str,
    is_blind: bool = False, judge_config: dict | None = None,
) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO matches
               (id,env_name,template_id,seed,mode,model_a,model_b,
                is_blind,judge_config,status)
               VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'pending')
               RETURNING *""",
            id, env_name, template_id, seed, mode, model_a, model_b,
            is_blind, json.dumps(judge_config or {}),
        )
    return _row(row)

async def get_match(pool: asyncpg.Pool, match_id: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM matches WHERE id=$1", match_id)
    return _row(row) if row else None

async def list_matches(
    pool: asyncpg.Pool, *,
    status: str | None = None,
    env_name: str | None = None,
) -> list[dict]:
    clauses, params = [], []
    for col, val in [("status", status), ("env_name", env_name)]:
        if val is not None:
            params.append(val); clauses.append(f"{col}=${len(params)}")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM matches {where} ORDER BY created_at DESC", *params
        )
    return [_row(r) for r in rows]

async def update_match(
    pool: asyncpg.Pool, match_id: str, *,
    status: str | None = None,
    winner: str | None = None,
    finished_at: float | None = None,
) -> None:
    sets, params = [], [match_id]
    for col, val in [("status", status), ("winner", winner)]:
        if val is not None:
            params.append(val); sets.append(f"{col}=${len(params)}")
    if finished_at is not None:
        params.append(str(finished_at))
        sets.append(f"finished_at=to_timestamp(${len(params)}::double precision)")
    if not sets:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE matches SET {','.join(sets)} WHERE id=$1", *params
        )

async def set_match_run(
    pool: asyncpg.Pool, match_id: str, model: str, run_id: str
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO match_runs(match_id,model,run_id)
               VALUES($1,$2,$3) ON CONFLICT(match_id,model) DO UPDATE SET run_id=$3""",
            match_id, model, run_id,
        )

async def get_match_runs(pool: asyncpg.Pool, match_id: str) -> dict[str, str]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT model, run_id FROM match_runs WHERE match_id=$1", match_id
        )
    return {r["model"]: r["run_id"] for r in rows}

async def win_matrix(pool: asyncpg.Pool, env_name: str) -> list[dict]:
    """Return aggregated win/loss/draw counts for all model pairs in env."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT model_a, model_b,
                      SUM(CASE WHEN winner='a' THEN 1 ELSE 0 END) AS wins_a,
                      SUM(CASE WHEN winner='b' THEN 1 ELSE 0 END) AS wins_b,
                      SUM(CASE WHEN winner='draw' THEN 1 ELSE 0 END) AS draws
               FROM matches
               WHERE env_name=$1 AND status='done'
               GROUP BY model_a, model_b""",
            env_name,
        )
    return [dict(r) for r in rows]

def _row(row) -> dict:
    d = dict(row)
    if isinstance(d.get("judge_config"), str):
        d["judge_config"] = json.loads(d["judge_config"])
    return d
```

- [ ] **Step 10.2: Create `backend/db/queries/elo.py`**

```python
from __future__ import annotations
import asyncpg
from backend.elo.calculator import GlickoPlayer

async def get_or_create(
    pool: asyncpg.Pool, model_name: str, env_name: str
) -> GlickoPlayer:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM elo_ratings WHERE model_name=$1 AND env_name=$2",
            model_name, env_name,
        )
    if row:
        return GlickoPlayer(
            rating=float(row["rating"]),
            rd=float(row["rd"]),
            volatility=float(row["volatility"]),
        )
    return GlickoPlayer()  # default 1500/350/0.06

async def save(
    pool: asyncpg.Pool,
    model_name: str, env_name: str,
    player: GlickoPlayer,
    match_id: str,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO elo_ratings(model_name, env_name, rating, rd, volatility, updated_at)
               VALUES($1,$2,$3,$4,$5,now())
               ON CONFLICT(model_name,env_name)
               DO UPDATE SET rating=$3, rd=$4, volatility=$5, updated_at=now()""",
            model_name, env_name, player.rating, player.rd, player.volatility,
        )
        await conn.execute(
            """INSERT INTO elo_history(model_name, env_name, rating, rd, match_id)
               VALUES($1,$2,$3,$4,$5)""",
            model_name, env_name, player.rating, player.rd, match_id,
        )

async def list_leaderboard(pool: asyncpg.Pool, env_name: str) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT model_name, env_name, rating, rd, volatility, updated_at
               FROM elo_ratings WHERE env_name=$1
               ORDER BY rating DESC""",
            env_name,
        )
    return [
        {
            "model_name":  r["model_name"],
            "env_name":    r["env_name"],
            "rating":      round(float(r["rating"]), 1),
            "rd":          round(float(r["rd"]), 1),
            "ci_low":      round(float(r["rating"]) - 2 * float(r["rd"]), 1),
            "ci_high":     round(float(r["rating"]) + 2 * float(r["rd"]), 1),
            "updated_at":  str(r["updated_at"]),
        }
        for r in rows
    ]

async def get_history(
    pool: asyncpg.Pool, model_name: str, env_name: str
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT rating, rd, match_id, recorded_at
               FROM elo_history
               WHERE model_name=$1 AND env_name=$2
               ORDER BY recorded_at ASC""",
            model_name, env_name,
        )
    return [
        {
            "rating":      round(float(r["rating"]), 1),
            "rd":          round(float(r["rd"]), 1),
            "match_id":    r["match_id"],
            "recorded_at": str(r["recorded_at"]),
        }
        for r in rows
    ]

async def list_envs(pool: asyncpg.Pool) -> list[str]:
    """List all envs that have at least one Elo rating."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT env_name FROM elo_ratings ORDER BY env_name"
        )
    return [r["env_name"] for r in rows]
```

- [ ] **Step 10.3: Create `backend/engines/arena_engine.py`**

```python
from __future__ import annotations
import asyncio, logging, random, time, uuid
import asyncpg
from backend.elo.calculator import update_glicko2
from backend.elo.significance import bootstrap_ci, SignificanceResult
from backend.db.queries import matches as mq, elo as eq

logger = logging.getLogger(__name__)

# Default judge config used when not specified
_DEFAULT_JUDGE = {
    "type":   "metric_compare",
    "metric": "success_rate",
    "min_diff": 0.02,
}

class ArenaEngine:
    def __init__(self, pool: asyncpg.Pool, job_engine):
        self._pool       = pool
        self._job_engine = job_engine  # JobEngine instance

    async def create_match(
        self, *,
        env_name: str,
        model_a: str,
        model_b: str,
        template_id: int | None = None,
        mode: str = "direct",
        is_blind: bool = False,
        judge_config: dict | None = None,
        seed: int | None = None,
        arena_env_args: dict | None = None,
        num_episodes: int = 10,
        policy_server_url_a: str = "",
        policy_server_url_b: str = "",
    ) -> dict:
        """Create a match and dispatch two eval jobs (one per model)."""
        match_id  = uuid.uuid4().hex[:8]
        match_seed = seed or random.randint(0, 2**31)
        jcfg = judge_config or _DEFAULT_JUDGE

        match = await mq.create_match(
            self._pool, id=match_id, env_name=env_name,
            template_id=template_id, seed=match_seed, mode=mode,
            model_a=model_a, model_b=model_b,
            is_blind=is_blind, judge_config=jcfg,
        )

        env_args = {**(arena_env_args or {"environment": env_name}), "num_envs": 1}

        # Create eval jobs for model_a and model_b
        job_a = await self._job_engine.create_job(
            name=f"arena_{match_id}_a",
            model_name=model_a,
            arena_env_args=env_args,
            num_episodes=num_episodes,
            policy_server_url=policy_server_url_a,
            description=f"Arena match {match_id} (model A)",
        )
        job_b = await self._job_engine.create_job(
            name=f"arena_{match_id}_b",
            model_name=model_b,
            arena_env_args=env_args,
            num_episodes=num_episodes,
            policy_server_url=policy_server_url_b,
            description=f"Arena match {match_id} (model B)",
        )

        await mq.update_match(self._pool, match_id, status="running")
        logger.info("arena.match_created", extra={
            "match_id": match_id, "model_a": model_a, "model_b": model_b,
        })

        # Background: wait for both jobs and judge
        asyncio.create_task(
            self._await_and_judge(match_id, job_a["id"], job_b["id"], env_name)
        )
        return match

    async def _await_and_judge(
        self, match_id: str, job_id_a: str, job_id_b: str, env_name: str
    ) -> None:
        """Wait for both jobs to finish, then judge and update Elo."""
        from backend.db.queries import jobs as jq, runs as rq, episodes as epq

        try:
            # Poll until both jobs are done (timeout: 2 hours)
            deadline = time.time() + 7200
            while time.time() < deadline:
                job_a = await jq.get_job(self._pool, job_id_a)
                job_b = await jq.get_job(self._pool, job_id_b)
                done_a = job_a and job_a["status"] in ("done", "failed_final", "cancelled")
                done_b = job_b and job_b["status"] in ("done", "failed_final", "cancelled")
                if done_a and done_b:
                    break
                await asyncio.sleep(10)
            else:
                await mq.update_match(self._pool, match_id, status="done",
                                       winner=None, finished_at=time.time())
                return

            run_a = await rq.latest_run_for_job(self._pool, job_id_a)
            run_b = await rq.latest_run_for_job(self._pool, job_id_b)

            match = await mq.get_match(self._pool, match_id)
            winner = None

            if run_a and run_b and run_a["status"] == "done" and run_b["status"] == "done":
                if run_a:
                    await mq.set_match_run(self._pool, match_id, "a", run_a["id"])
                if run_b:
                    await mq.set_match_run(self._pool, match_id, "b", run_b["id"])

                winner = _judge(
                    run_a["metrics"] or {}, run_b["metrics"] or {},
                    match["judge_config"] or _DEFAULT_JUDGE,
                )

                # Bootstrap significance test
                eps_a = await epq.get_episodes(self._pool, run_a["id"])
                eps_b = await epq.get_episodes(self._pool, run_b["id"])
                sig = bootstrap_ci(
                    [bool(e["success"]) for e in eps_a],
                    [bool(e["success"]) for e in eps_b],
                )
                logger.info("arena.significance", extra={
                    "match_id": match_id,
                    "significant": sig.significant,
                    "ci": f"[{sig.ci_low}, {sig.ci_high}]",
                })

                # Update Elo ratings
                await self._update_elo(
                    match_id, env_name,
                    match["model_a"], match["model_b"], winner,
                )

            await mq.update_match(
                self._pool, match_id,
                status="done", winner=winner, finished_at=time.time(),
            )
            logger.info("arena.match_done", extra={
                "match_id": match_id, "winner": winner,
            })

        except Exception as exc:
            logger.exception("arena.match_error", extra={
                "match_id": match_id, "error": str(exc),
            })
            await mq.update_match(self._pool, match_id, status="done",
                                   winner=None, finished_at=time.time())

    async def _update_elo(
        self, match_id: str, env_name: str,
        model_a: str, model_b: str, winner: str | None,
    ) -> None:
        player_a = await eq.get_or_create(self._pool, model_a, env_name)
        player_b = await eq.get_or_create(self._pool, model_b, env_name)

        if winner == "a":
            new_a, new_b = update_glicko2(player_a, player_b)
        elif winner == "b":
            new_b, new_a = update_glicko2(player_b, player_a)
        else:
            # Draw: average of both perspectives
            new_a_if_win, _ = update_glicko2(player_a, player_b)
            _, new_a_if_loss = update_glicko2(player_b, player_a)
            new_b_if_win, _ = update_glicko2(player_b, player_a)
            _, new_b_if_loss = update_glicko2(player_a, player_b)
            from dataclasses import fields
            new_a = player_a.__class__(
                **{f.name: (getattr(new_a_if_win, f.name) + getattr(new_a_if_loss, f.name)) / 2
                   for f in fields(player_a)}
            )
            new_b = player_b.__class__(
                **{f.name: (getattr(new_b_if_win, f.name) + getattr(new_b_if_loss, f.name)) / 2
                   for f in fields(player_b)}
            )

        await eq.save(self._pool, model_a, env_name, new_a, match_id)
        await eq.save(self._pool, model_b, env_name, new_b, match_id)

    async def get_leaderboard(self, env_name: str) -> list[dict]:
        return await eq.list_leaderboard(self._pool, env_name)

    async def get_win_matrix(self, env_name: str) -> list[dict]:
        return await mq.win_matrix(self._pool, env_name)

    async def get_model_profile(self, model_name: str, env_name: str) -> dict:
        from backend.db.queries import jobs as jq
        player   = await eq.get_or_create(self._pool, model_name, env_name)
        history  = await eq.get_history(self._pool, model_name, env_name)
        matches  = await mq.list_matches(self._pool, env_name=env_name)
        my_matches = [
            m for m in matches
            if m["model_a"] == model_name or m["model_b"] == model_name
        ]
        wins = sum(
            1 for m in my_matches if m.get("status") == "done" and (
                (m["model_a"] == model_name and m.get("winner") == "a") or
                (m["model_b"] == model_name and m.get("winner") == "b")
            )
        )
        return {
            "model_name":  model_name,
            "env_name":    env_name,
            "rating":      round(player.rating, 1),
            "rd":          round(player.rd, 1),
            "ci_low":      round(player.rating - 2 * player.rd, 1),
            "ci_high":     round(player.rating + 2 * player.rd, 1),
            "total_matches": len(my_matches),
            "wins":          wins,
            "history":       history,
        }

    async def list_envs_with_ratings(self) -> list[str]:
        return await eq.list_envs(self._pool)


def _judge(metrics_a: dict, metrics_b: dict, config: dict) -> str:
    """Pure function: compare metrics and return 'a', 'b', or 'draw'."""
    metric   = config.get("metric", "success_rate")
    min_diff = float(config.get("min_diff", 0.02))
    val_a = float(metrics_a.get(metric, 0))
    val_b = float(metrics_b.get(metric, 0))
    diff  = val_a - val_b
    if abs(diff) < min_diff:
        return "draw"
    return "a" if diff > 0 else "b"


# Singleton — set by main.py lifespan
arena_engine: ArenaEngine | None = None
```

- [ ] **Step 10.4: Write arena engine test**

```python
# tests/engines/test_arena_engine.py
from __future__ import annotations
import asyncio, os, pytest, asyncpg, uuid
from unittest.mock import AsyncMock, MagicMock
from backend.db.schema import create_tables
from backend.engines.arena_engine import _judge, ArenaEngine

TEST_DB = os.environ.get("TEST_DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test")

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

@pytest.mark.asyncio
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

@pytest.mark.asyncio
async def test_leaderboard_returns_list(pool):
    mock_engine = MagicMock()
    engine = ArenaEngine(pool, mock_engine)
    lb = await engine.get_leaderboard("lift_object")
    assert isinstance(lb, list)
```

- [ ] **Step 10.5: Write match query tests**

```python
# tests/db/test_matches_queries.py
from __future__ import annotations
import asyncio, os, pytest, asyncpg, uuid
from backend.db.schema import create_tables
from backend.db.queries import matches as mq, elo as elq
from backend.elo.calculator import GlickoPlayer

TEST_DB = os.environ.get("TEST_DATABASE_URL",
    "postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test")

@pytest.fixture(scope="module")
async def pool():
    p = await asyncpg.create_pool(TEST_DB)
    await create_tables(p)
    yield p
    await p.close()

@pytest.mark.asyncio
async def test_create_and_get_match(pool):
    mid = uuid.uuid4().hex[:8]
    m = await mq.create_match(pool, id=mid, env_name="lift_object",
                               model_a="pi0", model_b="zero")
    assert m["id"] == mid
    assert m["status"] == "pending"
    fetched = await mq.get_match(pool, mid)
    assert fetched["model_a"] == "pi0"

@pytest.mark.asyncio
async def test_update_match_winner(pool):
    mid = uuid.uuid4().hex[:8]
    await mq.create_match(pool, id=mid, env_name="lift_object",
                           model_a="a", model_b="b")
    await mq.update_match(pool, mid, status="done", winner="a",
                           finished_at=1234567.0)
    m = await mq.get_match(pool, mid)
    assert m["status"] == "done"
    assert m["winner"] == "a"

@pytest.mark.asyncio
async def test_elo_save_and_load(pool):
    p = GlickoPlayer(rating=1600, rd=200, volatility=0.05)
    mid = uuid.uuid4().hex[:8]
    await mq.create_match(pool, id=mid, env_name="test_env",
                           model_a="modelX", model_b="modelY")
    await elq.save(pool, "modelX", "test_env", p, mid)
    loaded = await elq.get_or_create(pool, "modelX", "test_env")
    assert abs(loaded.rating - 1600) < 0.01
    assert abs(loaded.rd - 200) < 0.01
```

- [ ] **Step 10.6: Run all new tests**

```bash
TEST_DATABASE_URL="postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test" \
  pytest tests/db/test_matches_queries.py tests/engines/test_arena_engine.py -v
```
Expected: 9 tests PASS

- [ ] **Step 10.7: Commit**

```bash
git add backend/db/queries/matches.py backend/db/queries/elo.py \
        backend/engines/arena_engine.py \
        tests/db/test_matches_queries.py tests/engines/test_arena_engine.py
git commit -m "feat: match DB queries + Arena Engine with Elo updates (Phase 3, Task 10)"
```

---

## Task 11: Arena API + main.py wiring

**Files:**
- Create: `backend/api/arena.py`
- Modify: `backend/main.py` — include arena router, wire arena_engine singleton

**Interfaces:**
- Consumes: `ArenaEngine`, `arena_engine` singleton from Task 10; `db.pool` from Phase 1
- Produces:
  - `POST /api/arena/matches` body: `{env_name, model_a, model_b, template_id?, mode?, is_blind?, judge_config?, seed?, arena_env_args?, num_episodes?, policy_server_url_a?, policy_server_url_b?}` → match dict (blind: `model_b` replaced with `"?"`)
  - `GET /api/arena/matches` → list (blind fields masked)
  - `GET /api/arena/matches/{id}` → match detail (blind-masked until done)
  - `GET /api/arena/leaderboard?env=lift_object` → Elo leaderboard list
  - `GET /api/arena/envs` → list of envs with ratings
  - `GET /api/arena/models/{name}?env=...` → model profile
  - `GET /api/arena/matrix?env=lift_object` → win-rate matrix

- [ ] **Step 11.1: Create `backend/api/arena.py`**

```python
from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.db import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/arena", tags=["arena"])

class CreateMatchRequest(BaseModel):
    env_name:            str
    model_a:             str
    model_b:             str
    template_id:         int | None = None
    mode:                str        = "direct"   # direct|swiss|round_robin
    is_blind:            bool       = False
    judge_config:        dict       = {}
    seed:                int | None = None
    arena_env_args:      dict       = {}
    num_episodes:        int        = 10
    policy_server_url_a: str        = ""
    policy_server_url_b: str        = ""

def _mask_blind(match: dict) -> dict:
    """Hide model_b if match is blind and not yet done."""
    if match.get("is_blind") and match.get("status") != "done":
        return {**match, "model_b": "?"}
    return match

def _get_engine():
    from backend.engines.arena_engine import arena_engine
    if arena_engine is None:
        raise HTTPException(503, "Arena engine not ready")
    return arena_engine

@router.post("/matches")
async def create_match(req: CreateMatchRequest):
    engine = _get_engine()
    match = await engine.create_match(
        env_name=req.env_name, model_a=req.model_a, model_b=req.model_b,
        template_id=req.template_id, mode=req.mode, is_blind=req.is_blind,
        judge_config=req.judge_config or None, seed=req.seed,
        arena_env_args=req.arena_env_args or None,
        num_episodes=req.num_episodes,
        policy_server_url_a=req.policy_server_url_a,
        policy_server_url_b=req.policy_server_url_b,
    )
    return _mask_blind(match)

@router.get("/matches")
async def list_matches(
    status:   str | None = None,
    env_name: str | None = None,
):
    from backend.db.queries import matches as mq
    matches = await mq.list_matches(db.pool, status=status, env_name=env_name)
    return [_mask_blind(m) for m in matches]

@router.get("/matches/{match_id}")
async def get_match(match_id: str):
    from backend.db.queries import matches as mq
    match = await mq.get_match(db.pool, match_id)
    if not match:
        raise HTTPException(404, f"Match {match_id} not found")
    return _mask_blind(match)

@router.get("/leaderboard")
async def get_leaderboard(env: str = Query(..., description="Environment name")):
    engine = _get_engine()
    return await engine.get_leaderboard(env)

@router.get("/envs")
async def list_envs():
    from backend.db.queries import elo as elq
    return await elq.list_envs(db.pool)

@router.get("/models/{model_name}")
async def get_model_profile(model_name: str, env: str = Query(...)):
    engine = _get_engine()
    return await engine.get_model_profile(model_name, env)

@router.get("/matrix")
async def get_win_matrix(env: str = Query(..., description="Environment name")):
    engine = _get_engine()
    return await engine.get_win_matrix(env)
```

- [ ] **Step 11.2: Wire arena engine in `backend/main.py`**

In the `lifespan` function, after creating `job_engine`, add:

```python
import backend.engines.arena_engine as ae_mod
ae_mod.arena_engine = ArenaEngine(db.pool, je_mod.job_engine)
```

Add import at the top of `main.py`:
```python
from backend.engines.arena_engine import ArenaEngine
from backend.api.arena import router as arena_router
```

Add router:
```python
app.include_router(arena_router)
```

- [ ] **Step 11.3: Write arena API test**

```python
# tests/api/test_arena_api.py
from __future__ import annotations
import asyncio, os, pytest, asyncpg
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from backend.db.schema import create_tables
from backend.db import init_db

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

@pytest.mark.asyncio(loop_scope="module")
async def test_list_matches_empty(client):
    r = await client.get("/api/arena/matches")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

@pytest.mark.asyncio(loop_scope="module")
async def test_get_nonexistent_match(client):
    r = await client.get("/api/arena/matches/nosuchid")
    assert r.status_code == 404

@pytest.mark.asyncio(loop_scope="module")
async def test_leaderboard_no_env(client):
    r = await client.get("/api/arena/leaderboard")
    # Missing required 'env' query param → 422
    assert r.status_code == 422

@pytest.mark.asyncio(loop_scope="module")
async def test_leaderboard_empty_env(client):
    r = await client.get("/api/arena/leaderboard?env=nonexistent_env")
    assert r.status_code == 200
    assert r.json() == []

@pytest.mark.asyncio(loop_scope="module")
async def test_list_envs(client):
    r = await client.get("/api/arena/envs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

@pytest.mark.asyncio(loop_scope="module")
async def test_win_matrix_empty(client):
    r = await client.get("/api/arena/matrix?env=lift_object")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
```

- [ ] **Step 11.4: Run all tests**

```bash
TEST_DATABASE_URL="postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval_test" \
  pytest tests/ -v 2>&1 | tail -5
```
Expected: all tests PASS (42 + 6 new = 48+)

- [ ] **Step 11.5: Commit**

```bash
git add backend/api/arena.py backend/main.py tests/api/test_arena_api.py
git commit -m "feat: Arena API endpoints + engine wiring in lifespan (Phase 3, Task 11)"
```

---

## Task 12: Frontend — ArenaView + Leaderboard Upgrade

**Files:**
- Modify: `frontend/src/types.ts` — add Match, EloRating, WinMatrixEntry, ArenaLeaderboardEntry
- Modify: `frontend/src/api.ts` — add arena API functions
- Modify: `frontend/src/App.tsx` — add 'arena' view, keyboard shortcut R
- Create: `frontend/src/components/ArenaView.tsx`
- Modify: `frontend/src/components/LeaderboardView.tsx` — add Elo tab

**New types:**
```typescript
export interface Match {
  id:          string
  env_name:    string
  mode:        'direct' | 'swiss' | 'round_robin'
  status:      'pending' | 'running' | 'done'
  model_a:     string
  model_b:     string   // "?" if blind and not done
  winner:      'a' | 'b' | 'draw' | null
  is_blind:    boolean
  seed:        number | null
  judge_config: Record<string, unknown>
  created_at:  string
  finished_at: string | null
}

export interface EloEntry {
  model_name: string
  env_name:   string
  rating:     number
  rd:         number
  ci_low:     number
  ci_high:    number
  updated_at: string
}

export interface WinMatrixEntry {
  model_a: string
  model_b: string
  wins_a:  number
  wins_b:  number
  draws:   number
}

export interface ModelProfile {
  model_name:    string
  env_name:      string
  rating:        number
  rd:            number
  ci_low:        number
  ci_high:       number
  total_matches: number
  wins:          number
  history:       { rating: number; rd: number; match_id: string; recorded_at: string }[]
}
```

**New api.ts functions:**
```typescript
export async function fetchMatches(params?: { status?: string; env_name?: string }): Promise<Match[]> {
  const q = new URLSearchParams(params as Record<string, string> ?? {})
  const r = await fetch(`${BASE}/arena/matches?${q}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function createMatch(req: {
  env_name: string; model_a: string; model_b: string;
  mode?: string; is_blind?: boolean; num_episodes?: number;
  judge_config?: Record<string, unknown>; arena_env_args?: Record<string, unknown>;
  policy_server_url_a?: string; policy_server_url_b?: string;
}): Promise<Match> {
  const r = await fetch(`${BASE}/arena/matches`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function fetchArenaLeaderboard(env: string): Promise<EloEntry[]> {
  const r = await fetch(`${BASE}/arena/leaderboard?env=${encodeURIComponent(env)}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function fetchArenaEnvs(): Promise<string[]> {
  const r = await fetch(`${BASE}/arena/envs`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function fetchWinMatrix(env: string): Promise<WinMatrixEntry[]> {
  const r = await fetch(`${BASE}/arena/matrix?env=${encodeURIComponent(env)}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function fetchModelProfile(model: string, env: string): Promise<ModelProfile> {
  const r = await fetch(`${BASE}/arena/models/${encodeURIComponent(model)}?env=${encodeURIComponent(env)}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
```

- [ ] **Step 12.1: Update `frontend/src/types.ts`** — add Match, EloEntry, WinMatrixEntry, ModelProfile

- [ ] **Step 12.2: Update `frontend/src/api.ts`** — add 6 arena API functions above

- [ ] **Step 12.3: Update `frontend/src/App.tsx`**

1. Add `'arena'` to `ViewName` type union
2. Add to NAV array: `{ id: 'arena', label: 'Arena', icon: 'fa-swords' }`
3. Add keyboard shortcut `R` for arena (note: `A` is already taken by Analysis)
4. Add `{view === 'arena' && <ArenaView />}` to views
5. Add `import ArenaView from './components/ArenaView'`

- [ ] **Step 12.4: Create `frontend/src/components/ArenaView.tsx`**

Three-panel layout: New Match form (left), Match List (center), Elo Leaderboard (right).

```tsx
// frontend/src/components/ArenaView.tsx
import { useState, useEffect, useCallback } from 'react'
import { createMatch, fetchMatches, fetchArenaLeaderboard, fetchArenaEnvs } from '../api'
import type { Match, EloEntry } from '../types'

function EloBar({ rating, rd }: { rating: number; rd: number }) {
  const color = rating >= 1600 ? '#10b981' : rating >= 1400 ? '#d4a857' : '#6b7280'
  return (
    <div className="flex items-center gap-2">
      <span className="num text-sm font-semibold" style={{ color }}>{Math.round(rating)}</span>
      <span className="text-[11px] text-ink-500">±{Math.round(2 * rd)}</span>
    </div>
  )
}

function MatchStatusBadge({ status, winner }: { status: string; winner: string | null }) {
  if (status === 'done') {
    const label = winner === 'draw' ? 'Draw' : winner === 'a' ? 'A Wins' : winner === 'b' ? 'B Wins' : 'Done'
    const color = winner === 'draw' ? 'text-ink-400' : 'text-green-400'
    return <span className={`text-[11px] num ${color}`}>{label}</span>
  }
  if (status === 'running') return <span className="text-[11px] text-gold">Running</span>
  return <span className="text-[11px] text-ink-500">Pending</span>
}

export default function ArenaView() {
  const [envs, setEnvs]           = useState<string[]>([])
  const [matches, setMatches]     = useState<Match[]>([])
  const [leaderboard, setLb]      = useState<EloEntry[]>([])
  const [selectedEnv, setEnv]     = useState('lift_object')
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState<string | null>(null)

  // New match form state
  const [modelA, setModelA]           = useState('')
  const [modelB, setModelB]           = useState('')
  const [mode, setMode]               = useState<'direct' | 'swiss' | 'round_robin'>('direct')
  const [isBlind, setIsBlind]         = useState(false)
  const [numEpisodes, setNumEpisodes] = useState(10)
  const [submitting, setSubmitting]   = useState(false)

  const refresh = useCallback(async () => {
    try {
      const [ms, lb] = await Promise.all([
        fetchMatches({ env_name: selectedEnv }),
        fetchArenaLeaderboard(selectedEnv),
      ])
      setMatches(ms)
      setLb(lb)
    } catch {}
  }, [selectedEnv])

  useEffect(() => {
    fetchArenaEnvs().then(e => {
      setEnvs(e)
      if (e.length > 0 && !e.includes(selectedEnv)) setEnv(e[0])
    }).catch(() => {})
  }, [selectedEnv])

  useEffect(() => { refresh() }, [refresh])
  useEffect(() => {
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [refresh])

  const handleCreateMatch = async () => {
    if (!modelA || !modelB) return
    setSubmitting(true); setError(null)
    try {
      await createMatch({
        env_name: selectedEnv, model_a: modelA, model_b: modelB,
        mode, is_blind: isBlind, num_episodes: numEpisodes,
        arena_env_args: { environment: selectedEnv },
      })
      setModelA(''); setModelB('')
      await refresh()
    } catch (e) {
      setError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="h-full overflow-hidden flex gap-4 p-4">
      {/* Left: new match form */}
      <div className="w-64 flex-shrink-0 flex flex-col gap-4">
        <div className="bg-ink-900 rounded-lg border border-ink-700 p-4 space-y-3">
          <div className="text-sm font-semibold text-ink-200">新对战</div>

          <div>
            <label className="text-[11px] text-ink-500 block mb-1">环境</label>
            <select value={selectedEnv} onChange={e => setEnv(e.target.value)}
                    className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-green-500">
              {['lift_object','pick_and_place_maple_table','kitchen_pick_and_place','sorting','press_button'].map(e => (
                <option key={e} value={e}>{e}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[11px] text-ink-500 block mb-1">模型 A</label>
            <input value={modelA} onChange={e => setModelA(e.target.value)}
                   placeholder="pi0, zero_action, ..."
                   className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500" />
          </div>

          <div>
            <label className="text-[11px] text-ink-500 block mb-1">模型 B</label>
            <input value={modelB} onChange={e => setModelB(e.target.value)}
                   placeholder="pi0.5, rsl_rl, ..."
                   className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500" />
          </div>

          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-[11px] text-ink-500 block mb-1">模式</label>
              <select value={mode} onChange={e => setMode(e.target.value as typeof mode)}
                      className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-green-500">
                <option value="direct">直接对战</option>
                <option value="swiss">瑞士制</option>
                <option value="round_robin">循环赛</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">Episodes</label>
              <input type="number" value={numEpisodes} min={1} max={100}
                     onChange={e => setNumEpisodes(Number(e.target.value))}
                     className="w-16 bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-green-500" />
            </div>
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={isBlind} onChange={e => setIsBlind(e.target.checked)}
                   className="rounded" />
            <span className="text-sm text-ink-300">盲测模式</span>
          </label>

          {error && <div className="text-red-400 text-[11px]">{error}</div>}

          <button onClick={handleCreateMatch} disabled={submitting || !modelA || !modelB}
                  className="w-full py-1.5 bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white text-sm rounded transition-colors">
            {submitting ? '提交中…' : '发起对战'}
          </button>
        </div>
      </div>

      {/* Center: match list */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-semibold text-ink-200">对战记录</span>
          <button onClick={refresh} className="text-[11px] text-ink-500 hover:text-ink-300">刷新</button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-1.5">
          {matches.length === 0 && (
            <div className="text-center text-ink-500 text-sm py-8">暂无对战记录</div>
          )}
          {matches.map(m => (
            <div key={m.id}
                 className="bg-ink-900 rounded-lg border border-ink-800 px-3 py-2 flex items-center gap-3">
              <div className="w-24 font-mono text-[11px] text-ink-500">{m.id}</div>
              <div className="flex-1 flex items-center gap-2 min-w-0">
                <span className="text-sm text-ink-200 truncate">{m.model_a}</span>
                <span className="text-ink-600 text-xs">vs</span>
                <span className="text-sm text-ink-200 truncate">
                  {m.model_b === '?' ? <span className="text-ink-500 italic">?</span> : m.model_b}
                </span>
              </div>
              <div className="text-[11px] text-ink-500">{m.env_name}</div>
              <MatchStatusBadge status={m.status} winner={m.winner} />
              {m.is_blind && <span className="text-[10px] text-violet-400 border border-violet-800/40 rounded px-1">盲</span>}
            </div>
          ))}
        </div>
      </div>

      {/* Right: Elo leaderboard */}
      <div className="w-72 flex-shrink-0">
        <div className="text-sm font-semibold text-ink-200 mb-3">
          Elo 排名 · {selectedEnv}
        </div>
        <div className="bg-ink-900 rounded-lg border border-ink-700 overflow-hidden">
          {leaderboard.length === 0 ? (
            <div className="text-center text-ink-500 text-sm py-8">暂无排名数据</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink-800 text-ink-500 text-[11px]">
                  <th className="text-left px-3 py-2">#</th>
                  <th className="text-left px-3 py-2">模型</th>
                  <th className="text-right px-3 py-2">分数</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((e, i) => (
                  <tr key={e.model_name} className="border-b border-ink-800 last:border-0">
                    <td className="px-3 py-2 text-ink-500 text-[12px]">{i + 1}</td>
                    <td className="px-3 py-2 text-ink-200 truncate max-w-[120px]">{e.model_name}</td>
                    <td className="px-3 py-2 text-right">
                      <EloBar rating={e.rating} rd={e.rd} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 12.5: Upgrade `frontend/src/components/LeaderboardView.tsx`** — add Elo tab

Add a tab switcher: "传统榜单" (existing content) | "Elo 竞技榜" (new Elo content).

The Elo tab shows:
- Environment selector
- Sorted Elo table with rating, ±CI badge, and a small Recharts sparkline for rating history (optional: only for a selected model)
- Win-rate matrix: N×N grid of colored cells showing wins_a/(wins_a+wins_b) as hue

Keep the existing traditional leaderboard as the default tab — add the Elo tab as a secondary option. Import `fetchArenaLeaderboard`, `fetchArenaEnvs`, `fetchWinMatrix` from `../api` and `EloEntry`, `WinMatrixEntry` from `../types`.

- [ ] **Step 12.6: Build frontend**

```bash
cd /home/disk/lrx/robot-eval/frontend && npm run build 2>&1 | tail -5
```
Expected: `✓ built in Xs` with no TypeScript errors

- [ ] **Step 12.7: Run backend tests**

```bash
cd /home/disk/lrx/robot-eval && pytest tests/ -v 2>&1 | tail -5
```
Expected: all tests PASS

- [ ] **Step 12.8: Commit**

```bash
cd /home/disk/lrx/robot-eval
git add frontend/src/ backend/
git commit -m "feat: ArenaView + Leaderboard Elo tab (Phase 3, Task 12)"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** Glicko-2 math (§7.4) ✓, bootstrap CI (§7.5) ✓, match CRUD (§7.6 APIs) ✓, Arena Engine judge (§7.3) ✓, blind mode masking (§7.2) ✓, Swiss/round_robin mode (§7.1) accepted in create but scheduling left to engine ✓
- [x] **No placeholders:** All code blocks complete
- [x] **Type consistency:**
  - `GlickoPlayer` dataclass used in `elo.py` queries and `arena_engine.py` ✓
  - `update_glicko2(winner, loser) -> tuple[GlickoPlayer, GlickoPlayer]` ✓
  - `_judge(metrics_a, metrics_b, config) -> str` — pure function ✓
  - `arena_engine: ArenaEngine | None = None` singleton ✓
  - `_get_engine()` pattern consistent with Phase 2 `_get_engine()` in jobs.py ✓
  - Frontend `Match.winner: 'a' | 'b' | 'draw' | null` matches backend ✓
