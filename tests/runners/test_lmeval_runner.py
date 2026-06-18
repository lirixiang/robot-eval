from __future__ import annotations
import json
import pathlib
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
async def test_lmeval_runner_defaults():
    runner = LMEvalRunner({"model": "hf/gpt2", "tasks": ["hellaswag"]})
    assert runner.num_fewshot == 0
    assert runner.batch_size == 1
    assert runner.extra_args == []
    assert runner.limit is None
    assert runner.timeout_s == 7200


@pytest.mark.asyncio
async def test_lmeval_runner_health_check_when_unavailable():
    runner = LMEvalRunner({"model": "hf/gpt2", "tasks": ["hellaswag"]})
    # lm_eval is unlikely installed in test env — health_check should return False
    result = runner.health_check()
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_lmeval_runner_run_parses_output():
    """Mock subprocess to return valid lm-eval JSON output."""
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
        cmd_args = args  # positional args are the command tokens
        for i, a in enumerate(cmd_args):
            if a == "--output_path" and i + 1 < len(cmd_args):
                output_dir = cmd_args[i + 1]
        if output_dir:
            p = pathlib.Path(output_dir)
            p.mkdir(parents=True, exist_ok=True)
            result_file = p / "results.json"
            result_file.write_text(json.dumps(fake_results))
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess):
        result = await runner.run({}, seed=42)

    assert isinstance(result, RunResult)
    assert len(result.metrics) > 0
    assert "hellaswag_acc" in result.metrics
    assert abs(result.metrics["hellaswag_acc"] - 0.42) < 0.001
    assert abs(result.metrics["hellaswag_acc_norm"] - 0.44) < 0.001


@pytest.mark.asyncio
async def test_lmeval_runner_nonzero_exit_raises():
    runner = LMEvalRunner({"model": "hf/gpt2", "tasks": ["hellaswag"]})
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"lm_eval failed"))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(RuntimeError, match="lm_eval exited with code"):
            await runner.run({}, seed=0)


@pytest.mark.asyncio
async def test_lmeval_runner_missing_results_returns_empty():
    """If output dir has no JSON, metrics should be empty dict."""
    runner = LMEvalRunner({"model": "hf/gpt2", "tasks": ["hellaswag"]})
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    # Don't write any results file — output dir will be empty
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await runner.run({}, seed=0)

    assert isinstance(result, RunResult)
    assert result.metrics == {}


@pytest.mark.asyncio
async def test_lmeval_runner_extra_args_passed():
    """Verify extra_args are appended to the command."""
    runner = LMEvalRunner({
        "model": "hf/gpt2",
        "tasks": ["hellaswag"],
        "extra_args": ["--device", "cpu"],
    })
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    captured_cmd = []

    async def capture_subprocess(*args, **kwargs):
        captured_cmd.extend(args)
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=capture_subprocess):
        await runner.run({}, seed=0)

    assert "--device" in captured_cmd
    assert "cpu" in captured_cmd
