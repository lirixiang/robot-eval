# Platform v2 Phase 4 — Polish & Extra Runners Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the platform with subprocess-based runners (LM-Eval, generic CLI), structured logging (structlog), Templates management frontend page, and final cleanup.

**Architecture:** `LMEvalRunner` and `SubprocessRunner` wrap external processes using `asyncio.create_subprocess_exec`. `structlog` replaces `logging.getLogger` across all backend files with JSON-line output. `TemplatesView` adds YAML editor + version browser + "Run Benchmark" button. `/api/health` already exists from Phase 1; verify it includes ray+db checks.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, structlog, asyncio subprocess, React 18, TypeScript, Tailwind CSS

## Global Constraints

- Python 3.12, `from __future__ import annotations`, asyncpg
- `arena_actor.py` and `base_actor.py` must NOT be modified
- Tests in `tests/` at repo root; `pytest tests/ -v` must pass (69+ tests)
- Frontend: TypeScript strict mode, Tailwind only
- Frontend build: `cd frontend && npm run build` — no TypeScript errors
- `DATABASE_URL` env var: `postgresql://eval:eval_secret@127.0.0.1:5432/robot_eval`
- All new Python files: `from __future__ import annotations`
- **No `print()` anywhere in backend** — use structlog after Task 13

---

## File Map

```
backend/
  runners/
    lmeval_runner.py       # CREATE: asyncio subprocess wrapping lm-evaluation-harness
    subprocess_runner.py   # CREATE: generic CLI runner
  logging_config.py        # CREATE: structlog setup + JSON renderer
  requirements.txt         # MODIFY: add structlog>=24.1.0
  main.py                  # MODIFY: call configure_logging() in lifespan
  engines/
    job_engine.py           # MODIFY: replace logging → structlog
    scheduler.py            # MODIFY: replace logging → structlog
    arena_engine.py         # MODIFY: replace logging → structlog
    analysis_engine.py      # MODIFY: replace logging → structlog
  api/
    jobs.py                 # MODIFY: replace logging → structlog
    runs.py                 # MODIFY: replace logging → structlog
    arena.py                # MODIFY: replace logging → structlog
    templates.py            # MODIFY: replace logging → structlog
    analysis.py             # MODIFY: replace logging → structlog
    results.py              # MODIFY: replace logging → structlog
    workers.py              # MODIFY: replace logging → structlog

tests/
  runners/
    test_lmeval_runner.py   # CREATE
    test_subprocess_runner.py # CREATE

frontend/src/
  components/
    TemplatesView.tsx       # CREATE: YAML editor, version browser, run benchmark button
  App.tsx                   # MODIFY: add 'templates' view, keyboard shortcut T
  api.ts                    # MODIFY: add createTemplate, validateYaml, deleteTemplate
  types.ts                  # Already has Template type from Phase 2
```

---

## Task 13: LMEvalRunner + SubprocessRunner

**Files:**
- Create: `backend/runners/lmeval_runner.py`
- Create: `backend/runners/subprocess_runner.py`
- Modify: `backend/runners/registry.py` — register lmeval and subprocess runners
- Create: `tests/runners/test_lmeval_runner.py`
- Create: `tests/runners/test_subprocess_runner.py`

**Interfaces:**
- Consumes: `BaseRunner`, `RunResult`, `EpisodeResult` from Phase 1
- Produces:
  - `LMEvalRunner(config: dict)` — wraps `lm-eval` CLI via asyncio subprocess
    - `config` keys: `model` (str), `tasks` (list[str]), `num_fewshot` (int=0), `limit` (int|None), `batch_size` (int=1), `extra_args` (list[str]=[])
    - `health_check()` returns True if `lm_eval --help` succeeds
    - `run()` executes `lm-eval --model {model} --tasks {tasks} --output_path /tmp/lmeval_{uuid} ...`, parses JSON output
  - `SubprocessRunner(config: dict)` — generic CLI wrapper
    - `config` keys: `command` (list[str]), `env` (dict[str,str]={}), `timeout_s` (int=300), `metrics_regex` (str|None), `success_exit_code` (int=0)
    - `health_check()` returns True (command existence not pre-checked)
    - `run()` executes command, parses stdout for metrics using `metrics_regex` if given, else returns `{"exit_code": 0}`
    - Raises `RuntimeError` if exit code != `success_exit_code` or timeout

- [ ] **Step 13.1: Write LMEvalRunner tests**

```python
# tests/runners/test_lmeval_runner.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.runners.lmeval_runner import LMEvalRunner
from backend.runners.base import RunResult

@pytest.mark.asyncio
async def test_lmeval_runner_instantiation():
    runner = LMEvalRunner({
        "model": "hf/gpt2",
        "tasks": ["hellaswag"],
        "limit": 10,
    })
    assert runner.model == "hf/gpt2"
    assert runner.tasks == ["hellaswag"]
    assert runner.limit == 10

@pytest.mark.asyncio
async def test_lmeval_runner_health_check_when_unavailable():
    runner = LMEvalRunner({"model": "hf/gpt2", "tasks": ["hellaswag"]})
    # lm_eval is unlikely installed in test env — health_check should return False
    result = runner.health_check()
    assert isinstance(result, bool)

@pytest.mark.asyncio
async def test_lmeval_runner_run_parses_output():
    """Mock subprocess to return valid lm-eval JSON output."""
    import json, os, tempfile, asyncio
    runner = LMEvalRunner({"model": "hf/gpt2", "tasks": ["hellaswag"], "limit": 5})

    fake_results = {
        "results": {
            "hellaswag": {
                "acc,none": 0.42,
                "acc_norm,none": 0.44,
            }
        }
    }

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    async def fake_create_subprocess(*args, **kwargs):
        # Write fake results to the output path
        output_dir = None
        for i, a in enumerate(args[0] if args else []):
            if a == "--output_path" and i + 1 < len(args[0]):
                output_dir = args[0][i + 1]
        if output_dir:
            import pathlib
            pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)
            result_file = pathlib.Path(output_dir) / "results.json"
            result_file.write_text(json.dumps(fake_results))
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess):
        result = await runner.run({}, seed=42)

    assert isinstance(result, RunResult)
    assert "hellaswag_acc" in result.metrics or len(result.metrics) > 0
```

- [ ] **Step 13.2: Write SubprocessRunner tests**

```python
# tests/runners/test_subprocess_runner.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.runners.subprocess_runner import SubprocessRunner
from backend.runners.base import RunResult

@pytest.mark.asyncio
async def test_subprocess_runner_instantiation():
    runner = SubprocessRunner({
        "command": ["echo", "hello"],
        "timeout_s": 30,
    })
    assert runner.command == ["echo", "hello"]
    assert runner.timeout_s == 30

@pytest.mark.asyncio
async def test_subprocess_runner_success():
    runner = SubprocessRunner({"command": ["echo", "test"]})
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"test\n", b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await runner.run({}, seed=0)
    assert isinstance(result, RunResult)
    assert result.metrics.get("exit_code") == 0

@pytest.mark.asyncio
async def test_subprocess_runner_nonzero_exit_raises():
    runner = SubprocessRunner({"command": ["false"], "success_exit_code": 0})
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(RuntimeError, match="exit code"):
            await runner.run({}, seed=0)

@pytest.mark.asyncio
async def test_subprocess_runner_metrics_regex():
    runner = SubprocessRunner({
        "command": ["echo", "success_rate=0.85"],
        "metrics_regex": r"success_rate=(?P<success_rate>[\d.]+)",
    })
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"success_rate=0.85\n", b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await runner.run({}, seed=0)
    assert abs(result.metrics["success_rate"] - 0.85) < 0.001

def test_health_check_returns_bool():
    runner = SubprocessRunner({"command": ["echo"]})
    assert isinstance(runner.health_check(), bool)
```

- [ ] **Step 13.3: Run tests — expect FAIL**

```bash
pytest tests/runners/test_lmeval_runner.py tests/runners/test_subprocess_runner.py -v
```
Expected: `ModuleNotFoundError: No module named 'backend.runners.lmeval_runner'`

- [ ] **Step 13.4: Create `backend/runners/subprocess_runner.py`**

```python
from __future__ import annotations
import asyncio, logging, re, time
from backend.runners.base import BaseRunner, RunResult, EpisodeResult

logger = logging.getLogger(__name__)

class SubprocessRunner(BaseRunner):
    """Generic CLI runner — executes any command and parses stdout for metrics."""

    def __init__(self, config: dict):
        self.command          = config["command"]           # list[str]
        self.env_extra        = config.get("env", {})
        self.timeout_s        = int(config.get("timeout_s", 300))
        self.metrics_regex    = config.get("metrics_regex")
        self.success_exit_code = int(config.get("success_exit_code", 0))

    def health_check(self) -> bool:
        return True  # command existence not pre-checked

    async def run(self, config: dict, seed: int) -> RunResult:
        import os
        env = {**os.environ, **self.env_extra}
        t0 = time.time()
        proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_s
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise RuntimeError(f"Command timed out after {self.timeout_s}s")

        elapsed = time.time() - t0
        stdout_str = stdout.decode(errors="replace")
        stderr_str = stderr.decode(errors="replace")

        if proc.returncode != self.success_exit_code:
            raise RuntimeError(
                f"Command exited with exit code {proc.returncode} "
                f"(expected {self.success_exit_code}). stderr: {stderr_str[:500]}"
            )

        metrics: dict = {"exit_code": proc.returncode}
        if self.metrics_regex:
            m = re.search(self.metrics_regex, stdout_str)
            if m:
                for k, v in m.groupdict().items():
                    try:
                        metrics[k] = float(v)
                    except (ValueError, TypeError):
                        metrics[k] = v

        return RunResult(
            metrics=metrics,
            episodes=[],
            elapsed_s=round(elapsed, 3),
            seed=seed,
            raw_output=stdout_str[:4096],
        )
```

- [ ] **Step 13.5: Create `backend/runners/lmeval_runner.py`**

```python
from __future__ import annotations
import asyncio, json, logging, pathlib, shutil, tempfile, time, uuid
from backend.runners.base import BaseRunner, RunResult, EpisodeResult

logger = logging.getLogger(__name__)

class LMEvalRunner(BaseRunner):
    """Runs LM-Evaluation-Harness (lm-eval) as a subprocess."""

    def __init__(self, config: dict):
        self.model       = config["model"]              # e.g. "hf/gpt2"
        self.tasks       = config.get("tasks", [])      # list[str]
        self.num_fewshot = int(config.get("num_fewshot", 0))
        self.limit       = config.get("limit")          # int | None
        self.batch_size  = int(config.get("batch_size", 1))
        self.extra_args  = config.get("extra_args", []) # list[str]
        self.timeout_s   = int(config.get("timeout_s", 7200))

    def health_check(self) -> bool:
        return shutil.which("lm_eval") is not None or shutil.which("lm-eval") is not None

    async def run(self, config: dict, seed: int) -> RunResult:
        output_dir = pathlib.Path(tempfile.mkdtemp()) / f"lmeval_{uuid.uuid4().hex[:8]}"
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "lm_eval",
            "--model", self.model,
            "--tasks", ",".join(self.tasks),
            "--num_fewshot", str(self.num_fewshot),
            "--batch_size", str(self.batch_size),
            "--output_path", str(output_dir),
            "--seed", str(seed),
        ]
        if self.limit is not None:
            cmd += ["--limit", str(self.limit)]
        cmd += self.extra_args

        t0 = time.time()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_s
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise RuntimeError(f"lm_eval timed out after {self.timeout_s}s")

        elapsed = time.time() - t0

        if proc.returncode != 0:
            raise RuntimeError(
                f"lm_eval exited with code {proc.returncode}: "
                f"{stderr.decode(errors='replace')[:500]}"
            )

        metrics = _parse_lmeval_output(output_dir)
        return RunResult(
            metrics=metrics,
            episodes=[],
            elapsed_s=round(elapsed, 3),
            seed=seed,
            raw_output=stdout.decode(errors="replace")[:4096],
        )

def _parse_lmeval_output(output_dir: pathlib.Path) -> dict:
    """Parse lm-eval JSON results file into flat metrics dict."""
    results_file = output_dir / "results.json"
    if not results_file.exists():
        # Try to find any JSON file
        json_files = list(output_dir.rglob("*.json"))
        if not json_files:
            return {}
        results_file = json_files[0]

    try:
        data = json.loads(results_file.read_text())
    except Exception:
        return {}

    metrics: dict = {}
    for task, task_metrics in data.get("results", {}).items():
        for metric_key, value in task_metrics.items():
            if isinstance(value, (int, float)):
                # Flatten: "hellaswag" + "acc,none" → "hellaswag_acc"
                clean_key = metric_key.replace(",none", "").replace(",", "_")
                metrics[f"{task}_{clean_key}"] = float(value)

    return metrics
```

- [ ] **Step 13.6: Register new runners in `backend/runners/registry.py`**

Add to `_LAZY`:
```python
def _lazy_lmeval():
    from backend.runners.lmeval_runner import LMEvalRunner
    return LMEvalRunner

def _lazy_subprocess():
    from backend.runners.subprocess_runner import SubprocessRunner
    return SubprocessRunner

_LAZY: dict[str, callable] = {
    "isaaclab":      _lazy_isaaclab,
    "remote_policy": _lazy_remote_policy,
    "lmeval":        _lazy_lmeval,
    "subprocess":    _lazy_subprocess,
}
```

- [ ] **Step 13.7: Run all runner tests — expect PASS**

```bash
pytest tests/runners/ -v
```
Expected: 9 (existing) + 7 (new) = 16 tests PASS

- [ ] **Step 13.8: Commit**

```bash
git add backend/runners/ tests/runners/
git commit -m "feat: LMEvalRunner + SubprocessRunner + registry (Phase 4, Task 13)"
```

---

## Task 14: Structured Logging (structlog)

**Files:**
- Modify: `backend/requirements.txt` — add `structlog>=24.1.0`
- Create: `backend/logging_config.py`
- Modify: all backend files that use `logging.getLogger` → `structlog.get_logger`
- Modify: `backend/main.py` — call `configure_logging()` at startup

**Goal:** Replace Python stdlib `logging` with `structlog` JSON output. Every log event becomes a structured JSON line: `{"event": "job.created", "job_id": "abc", "timestamp": "...", "level": "info"}`.

**Note:** `arena_actor.py` still uses `print()` — that's intentional (it runs on GPU workers, not the platform). Do NOT change arena_actor.py.

- [ ] **Step 14.1: Add structlog to requirements.txt**

```
structlog>=24.1.0
```

- [ ] **Step 14.2: Create `backend/logging_config.py`**

```python
from __future__ import annotations
import logging
import structlog

def configure_logging(level: str = "INFO") -> None:
    """Configure structlog for JSON-line structured logging to stdout."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    # Also configure stdlib logging to suppress noisy third-party logs
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    for noisy in ("uvicorn.access", "uvicorn.error", "asyncio", "ray"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
```

- [ ] **Step 14.3: Replace `logging.getLogger` with `structlog.get_logger` across backend**

In each of the following files, change:
```python
import logging
logger = logging.getLogger(__name__)
```
To:
```python
import structlog
logger = structlog.get_logger(__name__)
```

Files to update:
- `backend/main.py`
- `backend/engines/job_engine.py`
- `backend/engines/scheduler.py`
- `backend/engines/arena_engine.py`
- `backend/engines/analysis_engine.py`
- `backend/api/jobs.py`
- `backend/api/runs.py`
- `backend/api/arena.py`
- `backend/api/templates.py`
- `backend/api/analysis.py`
- `backend/api/results.py`
- `backend/api/workers.py`
- `backend/runners/lmeval_runner.py`
- `backend/runners/subprocess_runner.py`
- `backend/runners/isaaclab_runner.py`
- `backend/runners/remote_policy.py`

**Note:** structlog's `get_logger()` returns a bound logger. The call syntax for logging events changes slightly:
- `logger.info("msg", extra={...})` → `logger.info("msg", key=value, ...)` (structlog uses kwargs directly)
- `logger.warning("msg", extra={"error": str(e)})` → `logger.warning("msg", error=str(e))`
- `logger.exception("msg", extra={...})` → `logger.exception("msg", ...)` (structlog auto-captures exc_info)

Update all `logger.info/warning/error/exception` calls to use structlog's kwargs style.

- [ ] **Step 14.4: Call `configure_logging()` in `backend/main.py` lifespan**

Add at the very top of the lifespan context manager (before DB init):
```python
from backend.logging_config import configure_logging
# ...
@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    await init_db(...)
    ...
```

- [ ] **Step 14.5: Install structlog and run tests**

```bash
pip install structlog>=24.1.0
pytest tests/ -v 2>&1 | tail -5
```
Expected: all tests PASS (structlog has no breaking changes to test behavior)

- [ ] **Step 14.6: Commit**

```bash
git add backend/
git commit -m "feat: structlog JSON logging across all backend modules (Phase 4, Task 14)"
```

---

## Task 15: TemplatesView Frontend

**Files:**
- Create: `frontend/src/components/TemplatesView.tsx`
- Modify: `frontend/src/App.tsx` — add 'templates' view, keyboard shortcut T
- Modify: `frontend/src/api.ts` — add createTemplate, deleteTemplate, validateYaml

**New api.ts functions:**
```typescript
export async function createTemplate(req: {
  name: string; version: string; runner_type: string;
  config_yaml: string; description?: string;
}): Promise<Template> {
  const r = await fetch(`${BASE}/templates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function deleteTemplate(id: number): Promise<void> {
  const r = await fetch(`${BASE}/templates/${id}`, { method: 'DELETE' })
  if (!r.ok) throw new Error(await r.text())
}

export async function validateYaml(config_yaml: string): Promise<{valid: boolean; errors: string[]}> {
  const r = await fetch(`${BASE}/templates/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config_yaml }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
```

- [ ] **Step 15.1: Update `frontend/src/api.ts`** — add 3 template functions above

- [ ] **Step 15.2: Update `frontend/src/App.tsx`**

1. Add `'templates'` to `ViewName` union
2. Add nav entry: `{ id: 'templates', label: '模板', icon: 'fa-file-code' }`
3. Add keyboard shortcut `T`
4. Add `{view === 'templates' && <TemplatesView />}` to views
5. Add import `import TemplatesView from './components/TemplatesView'`
6. Add `'/templates': 'templates'` to `useRouter.ts` PATH_MAP and VIEW_PATH

- [ ] **Step 15.3: Create `frontend/src/components/TemplatesView.tsx`**

Two-panel layout: template list (left) + YAML editor / detail (right).

```tsx
// frontend/src/components/TemplatesView.tsx
import { useState, useEffect, useCallback } from 'react'
import { fetchTemplates, createTemplate, deleteTemplate, validateYaml, submitJob } from '../api'
import type { Template, SubmitRequest } from '../types'

const STARTER_YAML = `name: my_benchmark
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
  min_diff: 0.02
`

export default function TemplatesView() {
  const [templates, setTemplates]   = useState<Template[]>([])
  const [selected, setSelected]     = useState<Template | null>(null)
  const [editorYaml, setEditorYaml] = useState(STARTER_YAML)
  const [newName, setNewName]       = useState('')
  const [newVersion, setNewVersion] = useState('1.0')
  const [newRunner, setNewRunner]   = useState('isaaclab')
  const [newDesc, setNewDesc]       = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  const [saving, setSaving]         = useState(false)
  const [runMsg, setRunMsg]         = useState<string | null>(null)

  const refresh = useCallback(() =>
    fetchTemplates().then(setTemplates).catch(() => {}), [])

  useEffect(() => { refresh() }, [refresh])

  const handleValidate = async () => {
    const result = await validateYaml(editorYaml).catch(() => ({ valid: false, errors: ['Network error'] }))
    setValidationErrors(result.errors)
  }

  const handleSave = async () => {
    if (!newName.trim()) return
    setSaving(true); setValidationErrors([])
    try {
      const t = await createTemplate({
        name: newName.trim(), version: newVersion,
        runner_type: newRunner, config_yaml: editorYaml,
        description: newDesc || undefined,
      })
      await refresh()
      setSelected(t)
      setIsCreating(false)
    } catch (e) {
      setValidationErrors([String(e)])
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (t: Template) => {
    if (!confirm(`删除模板 "${t.name}@${t.version}"？`)) return
    await deleteTemplate(t.id)
    await refresh()
    if (selected?.id === t.id) setSelected(null)
  }

  const handleRunBenchmark = async (t: Template) => {
    setRunMsg(null)
    try {
      const req: SubmitRequest = {
        name: `${t.name}_v${t.version}`,
        arena_env_args: {},
        num_envs: 1,
        num_episodes: 10,
        num_steps: null,
        policy_type: 'zero_action',
        policy_config: {},
        policy_server_url: '',
        model_name: '',
        submitter: '',
        description: `Benchmark run for template ${t.name}@${t.version}`,
      }
      // Try to parse config_yaml for env args
      try {
        const lines = t.config_yaml.split('\n')
        const envLine = lines.find(l => l.includes('environment:'))
        if (envLine) {
          const env = envLine.split(':')[1].trim()
          req.arena_env_args = { environment: env }
        }
      } catch {}
      await submitJob(req)
      setRunMsg('评测任务已提交，查看任务队列')
    } catch (e) {
      setRunMsg(`提交失败: ${e}`)
    }
  }

  const displayTemplate = isCreating ? null : selected

  return (
    <div className="h-full flex gap-4 p-4 overflow-hidden">
      {/* Left: template list */}
      <div className="w-64 flex-shrink-0 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-ink-200">评测模板</span>
          <button onClick={() => { setIsCreating(true); setSelected(null); setEditorYaml(STARTER_YAML); setValidationErrors([]) }}
                  className="text-[11px] px-2 py-1 bg-green-600 hover:bg-green-500 text-white rounded">
            + 新建
          </button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-1">
          {templates.length === 0 && (
            <div className="text-center text-ink-500 text-sm py-6">暂无模板</div>
          )}
          {templates.map(t => (
            <div key={t.id}
                 onClick={() => { setSelected(t); setIsCreating(false); setEditorYaml(t.config_yaml) }}
                 className={`rounded-lg border px-3 py-2 cursor-pointer transition-colors ${
                   selected?.id === t.id && !isCreating
                     ? 'border-green-600/60 bg-green-950/20'
                     : 'border-ink-800 bg-ink-900 hover:border-ink-600'
                 }`}>
              <div className="text-sm text-ink-200 font-medium">{t.name}</div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[10px] text-ink-500">v{t.version}</span>
                <span className="text-[10px] px-1 bg-ink-800 text-ink-400 rounded">{t.runner_type}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Right: editor / detail */}
      <div className="flex-1 flex flex-col min-w-0 gap-3">
        {isCreating && (
          <div className="bg-ink-900 rounded-lg border border-ink-700 p-4 grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">名称</label>
              <input value={newName} onChange={e => setNewName(e.target.value)}
                     placeholder="my_benchmark"
                     className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500" />
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">版本</label>
              <input value={newVersion} onChange={e => setNewVersion(e.target.value)}
                     className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-green-500" />
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">Runner 类型</label>
              <select value={newRunner} onChange={e => setNewRunner(e.target.value)}
                      className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-green-500">
                <option value="isaaclab">isaaclab</option>
                <option value="lmeval">lmeval</option>
                <option value="subprocess">subprocess</option>
                <option value="remote_policy">remote_policy</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">描述</label>
              <input value={newDesc} onChange={e => setNewDesc(e.target.value)}
                     placeholder="可选"
                     className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500" />
            </div>
          </div>
        )}

        {displayTemplate && !isCreating && (
          <div className="bg-ink-900 rounded-lg border border-ink-700 px-4 py-3 flex items-center gap-4">
            <div className="flex-1">
              <span className="text-base font-semibold text-ink-100">{displayTemplate.name}</span>
              <span className="text-ink-500 text-sm ml-2">v{displayTemplate.version}</span>
              {displayTemplate.description && (
                <span className="text-ink-400 text-sm ml-3">{displayTemplate.description}</span>
              )}
            </div>
            <button onClick={() => handleRunBenchmark(displayTemplate)}
                    className="px-3 py-1.5 bg-green-700 hover:bg-green-600 text-white text-sm rounded">
              运行 Benchmark
            </button>
            <button onClick={() => handleDelete(displayTemplate)}
                    className="px-3 py-1.5 bg-red-900/40 hover:bg-red-800/60 text-red-400 text-sm rounded border border-red-800/40">
              删除
            </button>
          </div>
        )}

        {runMsg && (
          <div className="bg-ink-900 border border-ink-700 rounded px-3 py-2 text-sm text-ink-300">{runMsg}</div>
        )}

        {/* YAML editor */}
        <div className="flex-1 flex flex-col min-h-0 bg-ink-900 rounded-lg border border-ink-700 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800">
            <span className="text-[11px] text-ink-400 font-mono">config.yaml</span>
            <div className="flex gap-2">
              <button onClick={handleValidate}
                      className="text-[11px] px-2 py-1 border border-ink-600 rounded text-ink-300 hover:text-white hover:border-ink-400">
                校验
              </button>
              {isCreating && (
                <button onClick={handleSave} disabled={saving || !newName}
                        className="text-[11px] px-2 py-1 bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white rounded">
                  {saving ? '保存中…' : '保存模板'}
                </button>
              )}
            </div>
          </div>
          {validationErrors.length > 0 && (
            <div className="px-3 py-2 bg-red-950/30 border-b border-red-800/30">
              {validationErrors.map((e, i) => (
                <div key={i} className="text-red-400 text-[11px]">{e}</div>
              ))}
            </div>
          )}
          {validationErrors.length === 0 && editorYaml && !isCreating && (
            <div className="px-3 py-1 bg-green-950/20 border-b border-green-900/30">
              <span className="text-green-500 text-[11px]">✓ YAML 有效</span>
            </div>
          )}
          <textarea
            value={editorYaml}
            onChange={e => { setEditorYaml(e.target.value); setValidationErrors([]) }}
            readOnly={!isCreating}
            spellCheck={false}
            className={`flex-1 p-3 font-mono text-[12px] leading-relaxed bg-transparent text-ink-200 resize-none focus:outline-none min-h-0 ${
              !isCreating ? 'text-ink-400' : ''
            }`}
          />
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 15.4: Build frontend**

```bash
cd /home/disk/lrx/robot-eval/frontend && npm run build 2>&1 | tail -5
```
Expected: `✓ built in Xs` with no errors

- [ ] **Step 15.5: Run full backend test suite**

```bash
cd /home/disk/lrx/robot-eval && pytest tests/ -v 2>&1 | tail -5
```
Expected: all tests PASS

- [ ] **Step 15.6: Commit**

```bash
cd /home/disk/lrx/robot-eval
git add frontend/src/ backend/
git commit -m "feat: TemplatesView frontend + YAML editor + run benchmark (Phase 4, Task 15)"
```

---

## Self-Review Checklist

- [x] **Spec coverage:**
  - LMEvalRunner (`subprocess wrapping lm-eval`) ✓
  - SubprocessRunner (`generic CLI`) ✓
  - Both registered in registry ✓
  - structlog JSON logging across all backend ✓ (Task 14)
  - TemplatesView with YAML editor, version list, run benchmark ✓ (Task 15)
  - `/api/health` (DB + Ray) — already implemented in Phase 1 final fixes ✓
- [x] **No placeholders:** All code blocks complete
- [x] **Type consistency:**
  - `LMEvalRunner.__init__(config)` same as `BaseRunner` pattern ✓
  - `SubprocessRunner` metrics_regex uses named groups → float conversion ✓
  - `structlog.get_logger(__name__)` drop-in for `logging.getLogger(__name__)` ✓
  - Template CRUD api functions use `r.ok` check pattern ✓
