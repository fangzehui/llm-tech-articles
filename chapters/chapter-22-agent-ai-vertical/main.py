"""Chapter 22 - Agent AI 三大黄金赛道场景 ROI 评估器（教学示例）。

输入：6 个具体落地场景的五维指标（市场规模 / 技术成熟度 / 付费意愿 / 回报周期 / 上手成本）
输出：综合 ROI 打分 + 估算回收期 + 三大赛道排行

Run::

    python main.py
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class Scenario:
    name: str
    vertical: str       # 三大赛道 + 子领域
    market: float       # 0-1，目标市场规模
    maturity: float     # 0-1，技术成熟度
    willing_pay: float  # 0-1，客户付费意愿
    payback: float      # 0-1，回报速度（越高越快）
    barrier: float = 0.5  # 0-1，进入门槛（越低越好，仅做打印参考）


SCENARIOS: List[Scenario] = [
    Scenario("代码开发 Agent",     "企业服务-通用",   0.90, 0.85, 0.90, 0.95, 0.30),
    Scenario("合同审查 Agent",     "企业服务-法律",   0.70, 0.85, 0.95, 0.90, 0.40),
    Scenario("发酵罐 AI Agent",    "工业-生物化工",   0.65, 0.80, 0.85, 0.90, 0.70),
    Scenario("整车质检 AI Agent",  "工业-汽车制造",   0.75, 0.80, 0.80, 0.85, 0.65),
    Scenario("分拣机器人 Agent",   "具身-物流仓储",   0.85, 0.75, 0.75, 0.80, 0.55),
    Scenario("人形机器人 Agent",   "具身-通用工厂",   0.95, 0.55, 0.60, 0.50, 0.85),
]

WEIGHTS = {"market": 0.30, "maturity": 0.25, "willing_pay": 0.25, "payback": 0.20}


def roi_score(s: Scenario) -> float:
    """五维加权 ROI 打分，输出 0-1。"""
    return round(
        WEIGHTS["market"] * s.market
        + WEIGHTS["maturity"] * s.maturity
        + WEIGHTS["willing_pay"] * s.willing_pay
        + WEIGHTS["payback"] * s.payback,
        4,
    )


def estimate_payback_months(s: Scenario) -> int:
    """payback 越高 → 回收期越短，简单映射到 [6, 36] 月。"""
    return int(round(36 - 30 * s.payback))


def rank_scenarios(scenarios: List[Scenario]) -> List[Scenario]:
    return sorted(scenarios, key=roi_score, reverse=True)


def main() -> None:
    print(">>> Agent AI 三大黄金赛道 - 场景 ROI 排行")
    header = (
        f"{'scenario':<20} {'vertical':<14} "
        f"{'market':>7} {'maturity':>9} {'willing_pay':>12} {'payback':>8} "
        f"{'roi_score':>10} {'payback(月)':>12}"
    )
    print(header)
    print("-" * len(header))
    for s in rank_scenarios(SCENARIOS):
        print(
            f"{s.name:<20} {s.vertical:<14} "
            f"{s.market:>7.2f} {s.maturity:>9.2f} {s.willing_pay:>12.2f} {s.payback:>8.2f} "
            f"{roi_score(s):>10.3f} {estimate_payback_months(s):>12d}"
        )


if __name__ == "__main__":
    main()
