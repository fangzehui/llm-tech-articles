"""tests for embedding_cache_model"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from embedding_cache_model import EmbeddingCacheCostModel


def test_zero_hit_rate_baseline():
    m = EmbeddingCacheCostModel()
    # 1_000_000 * 0.001 = 1000
    assert m.monthly_cost(1_000_000, 0.0) == pytest.approx(1000.0)


def test_full_hit_rate_min_cost():
    m = EmbeddingCacheCostModel()
    # 1_000_000 * 0.0001 = 100
    assert m.monthly_cost(1_000_000, 1.0) == pytest.approx(100.0)


def test_hit_rate_out_of_range_rejected():
    m = EmbeddingCacheCostModel()
    with pytest.raises(ValueError):
        m.monthly_cost(1000, -0.1)
    with pytest.raises(ValueError):
        m.monthly_cost(1000, 1.1)


def test_negative_queries_rejected():
    m = EmbeddingCacheCostModel()
    with pytest.raises(ValueError):
        m.monthly_cost(-1, 0.5)


def test_monotonic_decreasing():
    m = EmbeddingCacheCostModel()
    rates = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9]
    costs = [m.monthly_cost(1_000_000, r) for r in rates]
    for a, b in zip(costs, costs[1:]):
        assert a > b


def test_sweep_saving_ratio():
    m = EmbeddingCacheCostModel()
    rows = m.sweep(1_000_000, [0.0, 0.5, 1.0])
    assert rows[0]["saving_ratio"] == pytest.approx(0.0)
    # 命中率 100% 时相对 0% 的节省 = 1 - 0.0001/0.001 = 0.9
    assert rows[2]["saving_ratio"] == pytest.approx(0.9)


def test_marginal_saving_per_10pct():
    m = EmbeddingCacheCostModel()
    # 每 +10% 命中率，节省 = 1_000_000 * 0.1 * (0.001 - 0.0001) = 90
    assert m.marginal_saving_per_10pct(1_000_000) == pytest.approx(90.0)


def test_zero_queries_returns_zero():
    m = EmbeddingCacheCostModel()
    assert m.monthly_cost(0, 0.5) == 0.0
