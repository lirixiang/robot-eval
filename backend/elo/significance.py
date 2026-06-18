from __future__ import annotations
import random
from dataclasses import dataclass


@dataclass
class SignificanceResult:
    ci_low:      float   # lower bound of 95% CI for (rate_a - rate_b)
    ci_high:     float   # upper bound
    significant: bool    # True if CI excludes 0
    p_value:     float   # fraction of bootstrap samples where diff <= 0


def bootstrap_ci(
    successes_a: list[bool],
    successes_b: list[bool],
    n_bootstrap: int = 1000,
    alpha: float = 0.05,
) -> SignificanceResult:
    if not successes_a or not successes_b:
        return SignificanceResult(0.0, 0.0, False, 1.0)

    n_a, n_b = len(successes_a), len(successes_b)
    obs_diff = sum(successes_a) / n_a - sum(successes_b) / n_b

    diffs = []
    rng = random.Random(42)   # deterministic seed for reproducibility
    for _ in range(n_bootstrap):
        sample_a = [rng.choice(successes_a) for _ in range(n_a)]
        sample_b = [rng.choice(successes_b) for _ in range(n_b)]
        diffs.append(sum(sample_a) / n_a - sum(sample_b) / n_b)

    diffs.sort()
    lo = diffs[int(n_bootstrap * alpha / 2)]
    hi = diffs[int(n_bootstrap * (1 - alpha / 2))]
    p_value = sum(1 for d in diffs if d <= 0) / n_bootstrap

    return SignificanceResult(
        ci_low=round(lo, 4),
        ci_high=round(hi, 4),
        significant=(lo > 0 or hi < 0),
        p_value=round(p_value, 4),
    )
