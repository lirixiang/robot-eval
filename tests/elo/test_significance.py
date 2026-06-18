from __future__ import annotations
import pytest
from backend.elo.significance import bootstrap_ci, SignificanceResult


def test_clearly_different_rates():
    a = [True] * 80 + [False] * 20   # 80% success
    b = [True] * 20 + [False] * 80   # 20% success
    result = bootstrap_ci(a, b, n_bootstrap=500)
    assert result.significant is True
    assert result.ci_low > 0.0   # CI excludes 0 (A is better)


def test_identical_rates_not_significant():
    a = [True] * 50 + [False] * 50
    b = [True] * 50 + [False] * 50
    result = bootstrap_ci(a, b, n_bootstrap=500)
    assert result.significant is False


def test_empty_lists():
    result = bootstrap_ci([], [], n_bootstrap=100)
    assert result.significant is False
    assert result.ci_low == 0.0
    assert result.ci_high == 0.0


def test_result_fields():
    a = [True] * 6 + [False] * 4
    b = [True] * 4 + [False] * 6
    result = bootstrap_ci(a, b, n_bootstrap=200)
    assert isinstance(result, SignificanceResult)
    assert result.ci_low <= result.ci_high
    assert 0.0 <= result.p_value <= 1.0
