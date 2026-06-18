from __future__ import annotations
import asyncio, json, pathlib, shutil, tempfile, time, uuid
import structlog
from backend.runners.base import BaseRunner, RunResult, EpisodeResult

logger = structlog.get_logger(__name__)


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
        import os
        tmp_root = tempfile.mkdtemp()
        try:
            output_dir = pathlib.Path(tmp_root) / f"lmeval_{uuid.uuid4().hex[:8]}"
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
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)


def _parse_lmeval_output(output_dir: pathlib.Path) -> dict:
    """Parse lm-eval JSON results file into flat metrics dict."""
    results_file = output_dir / "results.json"
    if not results_file.exists():
        # Try to find any JSON file recursively
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
