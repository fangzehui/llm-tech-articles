"""Chapter 22 smoke test."""
from __future__ import annotations

from main import SCENARIOS, Scenario, estimate_payback_months, rank_scenarios, roi_score


def test_roi_score_in_range():
    for s in SCENARIOS:
        v = roi_score(s)
        assert 0.0 <= v <= 1.0


def test_rank_is_sorted_descending():
    ranked = rank_scenarios(SCENARIOS)
    scores = [roi_score(s) for s in ranked]
    assert scores == sorted(scores, reverse=True)


def test_higher_payback_shorter_months():
    fast = Scenario("快回收", "企业服务-通用", 0.7, 0.7, 0.7, 0.95)
    slow = Scenario("慢回收", "具身-通用工厂", 0.7, 0.7, 0.7, 0.30)
    assert estimate_payback_months(fast) < estimate_payback_months(slow)
    assert estimate_payback_months(fast) >= 6
    assert estimate_payback_months(slow) <= 36
