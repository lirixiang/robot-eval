import pytest
import sys; sys.path.insert(0, ".")
from backend.runners.base import BaseRunner, RunResult, EpisodeResult
from backend.runners.registry import get_runner, register_runner

class DummyRunner(BaseRunner):
    def __init__(self, config: dict): self.config = config
    async def run(self, config, seed):
        return RunResult(metrics={}, episodes=[], elapsed_s=0, seed=seed)
    def health_check(self): return True

def test_register_and_get_custom_runner():
    register_runner("dummy", DummyRunner)
    runner = get_runner("dummy", {"foo": "bar"})
    assert isinstance(runner, DummyRunner)
    assert runner.config == {"foo": "bar"}

def test_get_unknown_runner_raises():
    with pytest.raises(KeyError, match="no_such_runner"):
        get_runner("no_such_runner", {})

def test_get_isaaclab_runner():
    runner = get_runner("isaaclab", {"actor_name": "arena-worker-0"})
    from backend.runners.isaaclab_runner import IsaacLabRunner
    assert isinstance(runner, IsaacLabRunner)

def test_get_remote_policy_runner():
    runner = get_runner("remote_policy", {"endpoint": "http://localhost:7860"})
    from backend.runners.remote_policy import RemotePolicyRunner
    assert isinstance(runner, RemotePolicyRunner)
