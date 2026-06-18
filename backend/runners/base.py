from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class EpisodeResult:
    index:              int
    success:            bool
    reward_total:       float
    steps:              int
    termination_reason: str
    metadata:           dict = field(default_factory=dict)

@dataclass
class RunResult:
    metrics:    dict
    episodes:   list[EpisodeResult]
    elapsed_s:  float
    seed:       int
    raw_output: str = ""

class BaseRunner(ABC):
    @abstractmethod
    async def run(self, config: dict, seed: int) -> RunResult: ...

    @abstractmethod
    def health_check(self) -> bool: ...
