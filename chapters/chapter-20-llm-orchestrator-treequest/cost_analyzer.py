"""test-time compute 成本曲线计算器。

输入：
- 一组模型的 ``ModelPrice``（USD/Mtok input、USD/Mtok output、平均 input/output tokens）
- 预算列表（budget = 单次任务允许的 LLM 调用次数 K）
- 假设每次调用独立解出"正确答案"的概率 p_single

输出：
- 在 Pass@K 度量下，"至少有一次解对"的概率 = 1 - (1-p_single)^K
- 单任务的预期成本（USD） = K × (in_price × in_tok + out_price × out_tok) / 1e6
- "每 1% 准确率提升"对应的边际成本（边际成本递增曲线）

应用场景：
- 接 AB-MCTS / TreeQuest 之前先估算"花到多少预算之后，准确率提升的边际成本爆炸"
- 给业务方一张"成本 × 准确率"曲线，决定 budget 上限
- 跨模型对比同等准确率下"哪家最便宜"

⚠️ Pass@K 的"独立性"是简化假设——AB-MCTS 通过 Thompson Sampling 在
不同 step 之间共享信息，实际收益会优于 1 - (1-p)^K，但用这个上界做预算
规划仍然非常实用（worst-case 估计）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple


@dataclass
class ModelPrice:
    """单个模型的价格 + 调用规模假设。"""

    name: str
    usd_per_mtok_input: float
    usd_per_mtok_output: float
    avg_input_tokens: int = 1000
    avg_output_tokens: int = 800
    p_single: float = 0.40           # 单次直接解对的概率

    def cost_per_call(self) -> float:
        return (
            self.usd_per_mtok_input * self.avg_input_tokens
            + self.usd_per_mtok_output * self.avg_output_tokens
        ) / 1_000_000

    def pass_at_k(self, k: int) -> float:
        """简化 Pass@K：1 - (1-p)^k。"""
        if k <= 0:
            return 0.0
        return 1.0 - (1.0 - self.p_single) ** k

    def cost_at_k(self, k: int) -> float:
        return k * self.cost_per_call()


def cost_curve(model: ModelPrice, k_range: Sequence[int]) -> List[Dict[str, float]]:
    """返回 ``[{k, pass_at_k, cost_usd, marginal_cost_per_pct}]``。

    ``marginal_cost_per_pct`` = 相对 k-1 步，每 +1% pass 概率多花的钱。
    """
    rows: List[Dict[str, float]] = []
    prev_pass = 0.0
    prev_cost = 0.0
    for k in k_range:
        p = model.pass_at_k(k)
        c = model.cost_at_k(k)
        dp = max(p - prev_pass, 1e-9)
        dc = c - prev_cost
        rows.append(
            {
                "k": k,
                "pass_at_k": p,
                "cost_usd": c,
                "marginal_cost_per_pct": dc / (dp * 100),
            }
        )
        prev_pass, prev_cost = p, c
    return rows


def break_even_budget(
    cheap: ModelPrice, expensive: ModelPrice, target_pass: float
) -> Dict[str, float]:
    """给定目标准确率 ``target_pass``：
    - 廉价模型需要多少次 K_cheap 才能达成；
    - 旗舰模型需要多少次 K_exp 才能达成；
    - 两者成本谁更便宜；
    """
    def _k_for(m: ModelPrice, target: float) -> int:
        if m.p_single >= target:
            return 1
        if m.p_single <= 0:
            return math.inf  # type: ignore[return-value]
        # 1 - (1-p)^k >= target  → k >= log(1-target)/log(1-p)
        return int(math.ceil(math.log(1 - target) / math.log(1 - m.p_single)))

    k_cheap = _k_for(cheap, target_pass)
    k_exp = _k_for(expensive, target_pass)
    cost_cheap = cheap.cost_at_k(k_cheap) if k_cheap != math.inf else math.inf
    cost_exp = expensive.cost_at_k(k_exp) if k_exp != math.inf else math.inf
    cheaper = "cheap" if cost_cheap <= cost_exp else "expensive"
    return {
        "target_pass": target_pass,
        "k_cheap": k_cheap,
        "k_expensive": k_exp,
        "cost_cheap_usd": cost_cheap,
        "cost_expensive_usd": cost_exp,
        "cheaper_choice": cheaper,
    }


def multi_llm_pass_at_budget(
    models: Sequence[ModelPrice], budget: int, allocation: Sequence[float]
) -> Dict[str, float]:
    """假设把 ``budget`` 次调用按 ``allocation`` 分给若干模型，
    计算"整体 Pass@budget"（任一模型解出即算 pass，独立性假设）。
    """
    assert abs(sum(allocation) - 1.0) < 1e-6, "allocation 必须归一化"
    fail_prob = 1.0
    total_cost = 0.0
    for m, frac in zip(models, allocation):
        k = max(0, int(round(budget * frac)))
        fail_prob *= (1.0 - m.p_single) ** k
        total_cost += m.cost_at_k(k)
    return {
        "budget": budget,
        "pass_at_budget": 1.0 - fail_prob,
        "cost_usd": total_cost,
    }


# ============================================================
# Demo：3 个真实价位档的模型 + 不同 budget 下的曲线
# ============================================================


def _demo_models() -> Dict[str, ModelPrice]:
    """价格量级取自 2026 年 6 月的几家主流定价（仅作教学示例，非选型推荐）。

    - cheap：DeepSeek-V4-Flash 量级；
    - mid：Gemini 3 Pro 量级；
    - flagship：Claude Opus 4.8 量级。
    """
    return {
        "cheap": ModelPrice(
            name="cheap",
            usd_per_mtok_input=0.14,
            usd_per_mtok_output=0.28,
            p_single=0.30,
        ),
        "mid": ModelPrice(
            name="mid",
            usd_per_mtok_input=1.00,
            usd_per_mtok_output=4.00,
            p_single=0.45,
        ),
        "flagship": ModelPrice(
            name="flagship",
            usd_per_mtok_input=10.00,
            usd_per_mtok_output=50.00,
            p_single=0.55,
        ),
    }


def main() -> None:                                # pragma: no cover
    print(">>> 单模型成本-准确率曲线（k=1..32）")
    ks = [1, 2, 4, 8, 16, 32]
    for name, m in _demo_models().items():
        print(f"\n模型={name}  p_single={m.p_single}  单次成本=${m.cost_per_call():.5f}")
        print(f"  {'k':>3}  {'pass@k':>8}  {'cost(USD)':>10}  {'边际/+1%':>10}")
        for row in cost_curve(m, ks):
            print(
                f"  {row['k']:>3}  {row['pass_at_k']:>8.3f}  "
                f"{row['cost_usd']:>10.5f}  ${row['marginal_cost_per_pct']:>9.5f}"
            )

    print("\n>>> 给定 target_pass=0.85，廉价 vs 旗舰 谁更便宜？")
    models = _demo_models()
    for target in (0.7, 0.85, 0.95):
        info = break_even_budget(models["cheap"], models["flagship"], target)
        print(
            f"  target={target}  K_cheap={info['k_cheap']:>3}  "
            f"K_flag={info['k_expensive']:>3}  cost_cheap=${info['cost_cheap_usd']:.4f}  "
            f"cost_flag=${info['cost_expensive_usd']:.4f}  cheaper={info['cheaper_choice']}"
        )

    print("\n>>> Multi-LLM 在 budget=20 下 (cheap:mid:flag = 0.5:0.3:0.2)")
    info = multi_llm_pass_at_budget(
        [models["cheap"], models["mid"], models["flagship"]],
        budget=20,
        allocation=[0.5, 0.3, 0.2],
    )
    print(
        f"  pass={info['pass_at_budget']:.3f}  cost=${info['cost_usd']:.4f}"
    )


if __name__ == "__main__":                          # pragma: no cover
    main()
