"""Chapter 23 smoke test."""
from __future__ import annotations

import math

from main import PLANS, AIToolPlan, annual_cost, estimate_savings, payback_months


def test_annual_cost_sums_correctly():
    p = AIToolPlan("demo", monthly_cost=1000, saved_hours=10, revenue_uplift=0.01, setup_cost=3000)
    assert annual_cost(p) == 1000 * 12 + 3000


def test_savings_scale_with_revenue():
    p = AIToolPlan("demo", monthly_cost=500, saved_hours=50, revenue_uplift=0.01)
    low = estimate_savings(p, monthly_revenue=100_000)
    high = estimate_savings(p, monthly_revenue=1_000_000)
    assert high > low


def test_payback_inf_when_no_net_gain():
    """月成本远大于月收益时应返回 inf，避免误导。"""
    bad = AIToolPlan("过度采购", monthly_cost=100_000, saved_hours=1, revenue_uplift=0.0)
    assert math.isinf(payback_months(bad, monthly_revenue=10_000))

    good = PLANS[0]
    pb = payback_months(good, monthly_revenue=500_000)
    assert pb < float("inf") and pb >= 0.5
