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
