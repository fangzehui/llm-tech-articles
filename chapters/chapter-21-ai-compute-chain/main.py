"""Chapter 21 - AI 算力产业链投资标的打分器（教学示例，不构成投资建议）。

把"美光 FY26Q3 数据中心营收 +200% YoY"这条信号往上下游延伸三个环节，
按 growth / valuation / position 三个轴打分，归一化得到仓位建议。

Run::

    python main.py
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Stock:
    ticker: str
    name: str
    tier: str           # 上游/中游/下游 + 细分
    growth: float       # 0-1，营收/利润增速分位
    valuation: float    # 0-1，估值合理度（越高越便宜）
    position: float     # 0-1，行业地位 / 护城河


# 三大主线代表标的（数据为示例，非实时行情）
UNIVERSE: List[Stock] = [
    Stock("MU",   "美光科技",        "上游-存储",     0.90, 0.55, 0.85),
    Stock("NVDA", "英伟达",          "上游-AI芯片",   0.95, 0.40, 0.95),
    Stock("LDZK", "点点词元(中游)",   "中游-算力调度", 0.95, 0.85, 0.65),
    Stock("IFLY", "科大讯飞",        "下游-场景落地", 0.75, 0.60, 0.70),
    Stock("SMIC", "中芯国际",        "上游-代工",     0.70, 0.50, 0.80),
    Stock("WUXI", "朗新科技",        "下游-能源场景", 0.60, 0.70, 0.55),
]

# 三轴权重（成长优先，其次行业地位，估值兜底）
W_GROWTH, W_VALUATION, W_POSITION = 0.45, 0.20, 0.35


def score(stock: Stock) -> float:
    """三轴加权打分，输出 0-1。"""
    return round(
        W_GROWTH * stock.growth
        + W_VALUATION * stock.valuation
        + W_POSITION * stock.position,
        4,
    )


def allocate(stocks: List[Stock]) -> List[Tuple[Stock, float, float]]:
    """按 score 归一化得到建议仓位（%）。"""
    scored = [(s, score(s)) for s in stocks]
    total = sum(v for _, v in scored) or 1.0
    return [(s, v, round(v / total * 100, 2)) for s, v in scored]


def main() -> None:
    print(">>> AI 算力产业链 - 三主线打分 & 建议仓位")
    header = f"{'ticker':<10} {'name':<16} {'tier':<14} {'growth':>7} {'valuation':>10} {'position':>9} {'score':>7} {'weight(%)':>10}"
    print(header)
    print("-" * len(header))
    for s, sc, w in allocate(UNIVERSE):
        print(
            f"{s.ticker:<10} {s.name:<16} {s.tier:<14} "
            f"{s.growth:>7.2f} {s.valuation:>10.2f} {s.position:>9.2f} "
            f"{sc:>7.3f} {w:>10.2f}"
        )


if __name__ == "__main__":
    main()
