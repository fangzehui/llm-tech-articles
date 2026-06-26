"""Chapter 23 - 中小微企业 AI 落地成本测算器（教学示例）。

把"中小微企业要不要上 AI"做成一道可算的数学题：
输入员工数 / 月营收，输出每个工具的月成本、年化收益、净收益、回收期（月）。

Run::

    python main.py
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class AIToolPlan:
    name: str
    monthly_cost: int        # 月成本（元）
    saved_hours: int         # 每月节省工时（小时）
    revenue_uplift: float    # 月营收提升比例（0-0.2）
    setup_cost: int = 0      # 一次性接入成本（元）


PLANS: List[AIToolPlan] = [
    AIToolPlan("AI 内容写作",        600,  60, 0.005),
    AIToolPlan("AI 客服 7x24",      800,  80, 0.010),
    AIToolPlan("AI 办公助手",        500,  50, 0.000),
    AIToolPlan("AI 财务记账",       1200, 100, 0.000, setup_cost=2000),
    AIToolPlan("AI 合同审查",       1500, 150, 0.000),
    AIToolPlan("行业 SaaS (按行业可选)", 3000, 100, 0.020, setup_cost=5000),
]


def estimate_savings(plan: AIToolPlan, monthly_revenue: float, hourly_rate: int = 100) -> float:
    """年化收益 = 12 个月节省的人工费 + 营收提升带来的增量收入。"""
    labor_save = plan.saved_hours * hourly_rate * 12
    revenue_uplift = plan.revenue_uplift * monthly_revenue * 12
    return labor_save + revenue_uplift


def annual_cost(plan: AIToolPlan) -> float:
    return plan.monthly_cost * 12 + plan.setup_cost


def payback_months(plan: AIToolPlan, monthly_revenue: float) -> float:
    """回收期（月）= 一次性 + 月成本 / 月收益，取最大值 0.5 做下界，避免分母太大导致 0。"""
    monthly_save = estimate_savings(plan, monthly_revenue) / 12
    net_monthly = monthly_save - plan.monthly_cost
    if net_monthly <= 0:
        return float("inf")
    return round(max(0.5, (plan.setup_cost + plan.monthly_cost) / net_monthly), 1)


def main(employees: int = 20, monthly_revenue: int = 500_000) -> None:
    print(f">>> 中小微企业 AI 落地成本测算（员工={employees} 人，月营收={monthly_revenue // 10000} 万）")
    header = (
        f"{'plan':<22} {'月成本(元)':>10} {'年成本(元)':>10} "
        f"{'年化收益(元)':>12} {'净收益(元)':>11} {'回收期(月)':>10}"
    )
    print(header)
    print("-" * len(header))
    total_m, total_a, total_g, total_net = 0, 0, 0.0, 0.0
    for p in PLANS:
        gain = estimate_savings(p, monthly_revenue)
        cost = annual_cost(p)
        net = gain - cost
        pb = payback_months(p, monthly_revenue)
        print(
            f"{p.name:<22} {p.monthly_cost:>10d} {cost:>10.0f} "
            f"{gain:>12.0f} {net:>11.0f} {pb:>10}"
        )
        total_m += p.monthly_cost
        total_a += cost
        total_g += gain
        total_net += net
    print("-" * len(header))
    print(
        f"{'合计':<22} {total_m:>10d} {total_a:>10.0f} "
        f"{total_g:>12.0f} {total_net:>11.0f}"
    )


if __name__ == "__main__":
    main()
