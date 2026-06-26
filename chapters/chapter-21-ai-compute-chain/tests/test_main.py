"""Chapter 21 smoke test."""
from __future__ import annotations

import math

from main import UNIVERSE, Stock, allocate, score


def test_score_in_range():
    """所有标的的打分应在 [0, 1] 区间内，且对相同输入幂等。"""
    for s in UNIVERSE:
        v = score(s)
        assert 0.0 <= v <= 1.0
        assert score(s) == v


def test_allocate_sums_to_100():
    """归一化后的仓位之和应约等于 100%。"""
    weights = [w for _, _, w in allocate(UNIVERSE)]
    assert math.isclose(sum(weights), 100.0, abs_tol=0.5)
    assert all(w > 0 for w in weights)


def test_higher_growth_higher_score():
    """同等估值 + 行业地位下，growth 更高的标的得分更高。"""
    low = Stock("L", "低增速", "上游", growth=0.40, valuation=0.60, position=0.60)
    high = Stock("H", "高增速", "上游", growth=0.95, valuation=0.60, position=0.60)
    assert score(high) > score(low)
