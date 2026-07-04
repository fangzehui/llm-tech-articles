"""pricing_sensitivity.py

判断一次 API 降价长期是否可持续的敏感性分析器。

核心思想：
- 官方定价（list price）不等于实际单价——大部分头部厂商都有 Prompt Caching / KV Cache 命中折扣。
- 实际单价 = list × (1 - hit_rate) + list × cache_discount × hit_rate。
- 如果实际单价 > 估算推理边际成本，则该定价长期可持续；否则属于烧钱补贴。

配套第 26 篇《国产大模型价格战复盘 2024-2026》第四节使用。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PricingScenario:
    """一个可测算的定价场景快照。"""

    model_name: str
    list_price_per_m_tokens: float
    cache_hit_rate: float
    cache_discount: float
    inference_cost_per_m_tokens: float


def effective_price(
    list_price_per_m_tokens: float,
    cache_hit_rate: float,
    cache_discount: float,
) -> float:
    """计算命中率与折扣加权后的有效单价（元/百万 tokens）。"""
    if not 0.0 <= cache_hit_rate <= 1.0:
        raise ValueError(f"cache_hit_rate must be in [0, 1], got {cache_hit_rate}")
    if not 0.0 <= cache_discount <= 1.0:
        raise ValueError(f"cache_discount must be in [0, 1], got {cache_discount}")
    if list_price_per_m_tokens < 0:
        raise ValueError(f"list_price must be >= 0, got {list_price_per_m_tokens}")
    miss = list_price_per_m_tokens * (1 - cache_hit_rate)
    hit = list_price_per_m_tokens * cache_discount * cache_hit_rate
    return miss + hit


def is_sustainable_cut(
    list_price_per_m_tokens: float,
    cache_hit_rate: float,
    cache_discount: float,
    inference_cost_per_m_tokens: float,
) -> bool:
    """判断一次降价长期是否可持续。

    参数：
      list_price_per_m_tokens: 官方定价（元/百万 tokens）
      cache_hit_rate: 平均缓存命中率（0-1）
      cache_discount: 缓存命中的折扣系数（例如 0.1 表示 1 折价）
      inference_cost_per_m_tokens: 估算的推理边际成本（元/百万 tokens）

    返回：True 表示混合价格 > 边际成本，可持续；False 表示倒挂。
    """
    eff = effective_price(list_price_per_m_tokens, cache_hit_rate, cache_discount)
    return eff > inference_cost_per_m_tokens


def margin_ratio(
    list_price_per_m_tokens: float,
    cache_hit_rate: float,
    cache_discount: float,
    inference_cost_per_m_tokens: float,
) -> float:
    """毛利率：(有效单价 - 边际成本) / 有效单价。<0 表示倒挂。"""
    eff = effective_price(list_price_per_m_tokens, cache_hit_rate, cache_discount)
    if eff <= 0:
        # 免费档位或零单价场景，直接返回 -inf 语义（用负大数近似）
        return float("-inf")
    return (eff - inference_cost_per_m_tokens) / eff


def analyze(scenario: PricingScenario) -> dict:
    """一次性输出场景的三项关键指标。"""
    eff = effective_price(
        scenario.list_price_per_m_tokens,
        scenario.cache_hit_rate,
        scenario.cache_discount,
    )
    return {
        "model": scenario.model_name,
        "effective_price": round(eff, 4),
        "sustainable": eff > scenario.inference_cost_per_m_tokens,
        "margin_ratio": round(margin_ratio(
            scenario.list_price_per_m_tokens,
            scenario.cache_hit_rate,
            scenario.cache_discount,
            scenario.inference_cost_per_m_tokens,
        ), 4),
    }


# ---- 内置样本：2026-Q2 公开数据估算 ----
DEFAULT_SCENARIOS = (
    PricingScenario(
        model_name="DeepSeek-V3",
        list_price_per_m_tokens=0.5,
        cache_hit_rate=0.6,
        cache_discount=0.1,
        inference_cost_per_m_tokens=0.2,
    ),
    PricingScenario(
        model_name="Doubao 1.5-pro",
        list_price_per_m_tokens=0.8,
        cache_hit_rate=0.5,
        cache_discount=0.2,
        inference_cost_per_m_tokens=0.3,
    ),
    PricingScenario(
        model_name="Qwen-Max",
        list_price_per_m_tokens=4.0,
        cache_hit_rate=0.4,
        cache_discount=0.5,
        inference_cost_per_m_tokens=1.5,
    ),
)


def main() -> None:
    """CLI 入口：跑一遍内置样本并打印结果表。"""
    print(f"{'Model':22s} {'EffPrice':>10s} {'Sustainable':>13s} {'Margin':>10s}")
    print("-" * 60)
    for s in DEFAULT_SCENARIOS:
        r = analyze(s)
        print(
            f"{r['model']:22s} {r['effective_price']:>10.4f} "
            f"{str(r['sustainable']):>13s} {r['margin_ratio']:>10.2%}"
        )


if __name__ == "__main__":
    main()
