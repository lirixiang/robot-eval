from __future__ import annotations
import asyncio, os, re, time
import structlog
from backend.runners.base import BaseRunner, RunResult, EpisodeResult

logger = structlog.get_logger(__name__)


class SubprocessRunner(BaseRunner):
    """Generic CLI runner — executes any command and parses stdout for metrics."""

    def __init__(self, config: dict):
        self.command           = config["command"]               # list[str]
        self.env_extra         = config.get("env", {})
        self.timeout_s         = int(config.get("timeout_s", 300))
        self.metrics_regex     = config.get("metrics_regex")
        self.success_exit_code = int(config.get("success_exit_code", 0))

    def health_check(self) -> bool:
        return True  # command existence not pre-checked

    async def run(self, config: dict, seed: int) -> RunResult:
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
