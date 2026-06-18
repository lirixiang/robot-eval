from __future__ import annotations
from backend.runners.base import BaseRunner

def _lazy_isaaclab():
    from backend.runners.isaaclab_runner import IsaacLabRunner
    return IsaacLabRunner

def _lazy_remote_policy():
    from backend.runners.remote_policy import RemotePolicyRunner
    return RemotePolicyRunner

_REGISTRY: dict[str, type[BaseRunner]] = {}
_LAZY: dict[str, callable] = {
    "isaaclab":      _lazy_isaaclab,
    "remote_policy": _lazy_remote_policy,
}

def get_runner(runner_type: str, config: dict) -> BaseRunner:
    if runner_type not in _REGISTRY:
        if runner_type in _LAZY:
            _REGISTRY[runner_type] = _LAZY[runner_type]()
        else:
            raise KeyError(f"Unknown runner: {runner_type}. "
                           f"Available: {list(_LAZY)+list(_REGISTRY)}")
    return _REGISTRY[runner_type](config)

def register_runner(name: str, cls: type[BaseRunner]) -> None:
    _REGISTRY[name] = cls
