"""cost_compare.py

6 家主流国产模型 2026-Q2 月账单对比脚本。

配套第 26 篇《国产大模型价格战复盘 2024-2026》第六节使用。
所有价格数据均为 2026-Q2 公开定价页快照，不代表实时刊例价。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ModelPricing:
    """一款模型的公开定价快照。"""

    name: str
    input_price_per_m: float   # 元/百万 tokens（列表价）
    output_price_per_m: float  # 元/百万 tokens
    cache_discount: float      # 命中缓存的输入折扣（0.1 = 1 折）
    notes: str = ""


MODELS_2026Q2: tuple[ModelPricing, ...] = (
    ModelPricing("DeepSeek-V3",   0.5, 8.0,  0.1, "缓存命中 1 折"),
    ModelPricing("DeepSeek-R1",   1.0, 16.0, 0.1, "推理档位"),
    ModelPricing("Doubao 1.5-pro", 0.8, 2.0,  0.2, "字节内部使用量最大"),
    ModelPricing("Qwen-Max",       4.0, 12.0, 0.5, "旗舰对标 GPT-4"),
    ModelPricing("Kimi K1.5",      2.0, 10.0, 0.25, "长文本 + Context Caching"),
    ModelPricing("GLM-4.5",        1.5, 6.0,  0.5, "智谱高端档位"),
)


def monthly_cost(
    model: ModelPricing,
    input_tokens_m: float,
    output_tokens_m: float,
    cache_hit_rate: float,
) -> float:
    """按月计算总账单（元）。"""
    if not 0.0 <= cache_hit_rate <= 1.0:
        raise ValueError(f"cache_hit_rate must be in [0, 1], got {cache_hit_rate}")
    if input_tokens_m < 0 or output_tokens_m < 0:
        raise ValueError("token counts must be >= 0")

    cache_hit_input = input_tokens_m * cache_hit_rate
    cache_miss_input = input_tokens_m * (1 - cache_hit_rate)
    input_cost = (
        cache_miss_input * model.input_price_per_m
        + cache_hit_input * model.input_price_per_m * model.cache_discount
    )
    output_cost = output_tokens_m * model.output_price_per_m
    return input_cost + output_cost


def rank_by_cost(
    models: Iterable[ModelPricing],
    input_tokens_m: float,
    output_tokens_m: float,
    cache_hit_rate: float,
) -> list[tuple[ModelPricing, float]]:
    """返回按月账单从低到高排序的 (model, cost) 列表。"""
    rows = [
        (m, monthly_cost(m, input_tokens_m, output_tokens_m, cache_hit_rate))
        for m in models
    ]
    rows.sort(key=lambda x: x[1])
    return rows


def render_markdown_table(
    rows: list[tuple[ModelPricing, float]],
    baseline_name: str = "DeepSeek-V3",
) -> str:
    """把排序结果渲染成 Markdown 表。"""
    baseline_cost = next(
        (c for m, c in rows if m.name == baseline_name), rows[0][1]
    )
    if baseline_cost == 0:
        baseline_cost = 1.0  # 避免除零
    lines = [
        "| 模型 | 月账单（元） | 相对基线倍率 |",
        "|---|---:|---:|",
    ]
    for m, c in rows:
        ratio = c / baseline_cost
        lines.append(f"| {m.name} | ¥{c:,.0f} | {ratio:.2f}× |")
    return "\n".join(lines)


def main() -> None:
    """CLI：默认场景（月 10 亿输入 + 3 亿输出、缓存命中率 50%）跑一遍对比。"""
    rows = rank_by_cost(MODELS_2026Q2, 1000, 300, 0.5)
    print("场景：月消耗 10 亿 tokens 输入 + 3 亿 tokens 输出，缓存命中率 50%\n")
    for m, c in rows:
        print(f"{m.name:20s} ¥{c:>10,.0f}   ({m.notes})")
    print()
    print(render_markdown_table(rows))


if __name__ == "__main__":
    main()
