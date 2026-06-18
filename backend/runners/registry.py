from __future__ import annotations
from collections.abc import Callable
from backend.runners.base import BaseRunner

def _lazy_isaaclab():
    from backend.runners.isaaclab_runner import IsaacLabRunner
    return IsaacLabRunner

def _lazy_remote_policy():
    from backend.runners.remote_policy import RemotePolicyRunner
    return RemotePolicyRunner

def _lazy_lmeval():
    from backend.runners.lmeval_runner import LMEvalRunner
    return LMEvalRunner

def _lazy_subprocess():
    from backend.runners.subprocess_runner import SubprocessRunner
    return SubprocessRunner

_REGISTRY: dict[str, type[BaseRunner]] = {}
_LAZY: dict[str, Callable[[], type[BaseRunner]]] = {
    "isaaclab":      _lazy_isaaclab,
    "remote_policy": _lazy_remote_policy,
    "lmeval":        _lazy_lmeval,
    "subprocess":    _lazy_subprocess,
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
