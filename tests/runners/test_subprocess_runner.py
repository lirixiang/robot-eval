from __future__ import annotations
import asyncio
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


@pytest.mark.asyncio
async def test_subprocess_runner_env_passthrough():
    runner = SubprocessRunner({
        "command": ["printenv", "MY_VAR"],
        "env": {"MY_VAR": "hello"},
    })
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"hello\n", b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await runner.run({}, seed=0)
    # Verify env was passed through (contains MY_VAR)
    call_kwargs = mock_exec.call_args[1]
    assert "MY_VAR" in call_kwargs.get("env", {})
    assert call_kwargs["env"]["MY_VAR"] == "hello"


@pytest.mark.asyncio
async def test_subprocess_runner_timeout_raises():
    runner = SubprocessRunner({"command": ["sleep", "9999"], "timeout_s": 1})
    mock_proc = MagicMock()
    mock_proc.returncode = -9
    mock_proc.kill = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            with pytest.raises(RuntimeError, match="timed out"):
                await runner.run({}, seed=0)
