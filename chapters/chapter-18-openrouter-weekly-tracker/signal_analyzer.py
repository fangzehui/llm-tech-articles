"""signal_analyzer.py
====================

第 18 篇配套源码：基于市场调用量信号的「选型 5 维度打分模型」。

5 个维度（与正文 §六 一一对应）：

1. **call_volume_trend** —— 调用量趋势：当周调用量绝对值 + 在 Top10 中的排名
2. **price_trend**       —— 价格趋势：是否近期有官方降价（带方向）
3. **ecosystem_maturity** —— 生态成熟度：所属厂商在品牌榜的排名 + 同厂商有效模型数
4. **capability_match**   —— 能力匹配度：上下文长度、思考/工具调用能力对当前场景的覆盖
5. **substitutability**   —— 可替代性：同档位是否存在 ≥2 个独立厂商的等价替代

打分范围统一 0-100，加权（默认等权 0.2）汇总成 ``final_score``，并给出
``recommendation`` 三档：

- ≥ 80：建议进入 production shortlist
- 60 ~ 80：建议进入灰度评估
- < 60：建议观察，不进入候选池
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from weekly_tracker import ModelRow, WeekSnapshot


# ---------------------------------------------------------------------------
# 输入模型：场景画像
# ---------------------------------------------------------------------------


@dataclass
class ScenarioProfile:
    """企业本次选型的场景画像。"""

    name: str
    needs_long_context: bool = False       # 是否要 ≥ 128K 上下文
    needs_thinking: bool = False           # 是否要思考模式
    needs_tool_call: bool = True           # 是否要 function call
    sensitive_to_price: bool = True
    min_context_tokens: int = 32_000
    preferred_country: Optional[str] = None  # "CN" / "US" / None
    weight: Dict[str, float] = field(default_factory=lambda: {
        "call_volume_trend": 0.25,
        "price_trend": 0.20,
        "ecosystem_maturity": 0.20,
        "capability_match": 0.25,
        "substitutability": 0.10,
    })

    def __post_init__(self) -> None:
        total = sum(self.weight.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weight 总和必须 = 1，当前 = {total}")


# ---------------------------------------------------------------------------
# 模型能力卡：在调用量信号之外补充静态事实
# ---------------------------------------------------------------------------


@dataclass
class CapabilityCard:
    model: str
    vendor: str
    context_tokens: int = 128_000
    has_thinking_mode: bool = False
    has_tool_call: bool = True
    input_price_usd_per_mtok: float = 1.0
    output_price_usd_per_mtok: float = 4.0
    recent_price_cut_pct: float = 0.0      # 最近 30 天累计降幅，0 表示无降价


# 本期 6/15-21 真实数据（公开来源整理）。生产环境请放在 capability_cards.json
# 里按周更新，这里作为示例硬编码。
DEFAULT_CAPABILITY_CARDS: Dict[str, CapabilityCard] = {
    "DeepSeek-V4-Flash": CapabilityCard(
        model="DeepSeek-V4-Flash",
        vendor="DeepSeek",
        context_tokens=1_000_000,
        has_thinking_mode=True,
        has_tool_call=True,
        input_price_usd_per_mtok=0.14,
        output_price_usd_per_mtok=0.28,
        recent_price_cut_pct=0.0,
    ),
    "DeepSeek-V4-Pro": CapabilityCard(
        model="DeepSeek-V4-Pro",
        vendor="DeepSeek",
        context_tokens=1_000_000,
        has_thinking_mode=True,
        has_tool_call=True,
        input_price_usd_per_mtok=0.42,
        output_price_usd_per_mtok=0.84,
        recent_price_cut_pct=75.0,  # 5/31 永久降价至原价 1/4
    ),
    "Xiaomi MiMo-V2.5": CapabilityCard(
        model="Xiaomi MiMo-V2.5",
        vendor="Xiaomi",
        context_tokens=1_000_000,
        has_thinking_mode=True,
        has_tool_call=True,
        input_price_usd_per_mtok=0.14,
        output_price_usd_per_mtok=0.28,
        recent_price_cut_pct=82.0,  # 5/27 永久降价
    ),
    "MiniMax M3": CapabilityCard(
        model="MiniMax M3",
        vendor="MiniMax",
        context_tokens=1_000_000,
        has_thinking_mode=True,
        has_tool_call=True,
        input_price_usd_per_mtok=0.30,
        output_price_usd_per_mtok=1.20,
        recent_price_cut_pct=0.0,
    ),
    "Tencent Hy3 preview": CapabilityCard(
        model="Tencent Hy3 preview",
        vendor="Tencent",
        context_tokens=256_000,
        has_thinking_mode=True,
        has_tool_call=True,
        input_price_usd_per_mtok=0.50,
        output_price_usd_per_mtok=2.00,
    ),
    "Qwen3.6 Plus": CapabilityCard(
        model="Qwen3.6 Plus",
        vendor="Alibaba",
        context_tokens=1_000_000,
        has_thinking_mode=True,
        has_tool_call=True,
        input_price_usd_per_mtok=0.20,
        output_price_usd_per_mtok=0.60,
    ),
    "Claude Sonnet 4.6": CapabilityCard(
        model="Claude Sonnet 4.6",
        vendor="Anthropic",
        context_tokens=200_000,
        has_thinking_mode=True,
        has_tool_call=True,
        input_price_usd_per_mtok=3.00,
        output_price_usd_per_mtok=15.00,
    ),
    "GLM-5.2": CapabilityCard(
        model="GLM-5.2",
        vendor="Zhipu",
        context_tokens=200_000,
        has_thinking_mode=True,
        has_tool_call=True,
        input_price_usd_per_mtok=0.60,
        output_price_usd_per_mtok=2.00,
    ),
    "Claude Opus 4.8": CapabilityCard(
        model="Claude Opus 4.8",
        vendor="Anthropic",
        context_tokens=200_000,
        has_thinking_mode=True,
        has_tool_call=True,
        input_price_usd_per_mtok=10.00,
        output_price_usd_per_mtok=50.00,
    ),
    "Gemini 3 Pro": CapabilityCard(
        model="Gemini 3 Pro",
        vendor="Google",
        context_tokens=2_000_000,
        has_thinking_mode=True,
        has_tool_call=True,
        input_price_usd_per_mtok=1.00,
        output_price_usd_per_mtok=4.00,
    ),
}


# ---------------------------------------------------------------------------
# 5 维度评分函数
# ---------------------------------------------------------------------------


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def score_call_volume_trend(model: ModelRow, snapshot: WeekSnapshot) -> float:
    """rank 越前、wow 越正 → 分越高."""
    top_n = len(snapshot.top_models)
    rank_part = (top_n - model.rank + 1) / top_n * 60  # 0~60
    # wow_pct 在 [-30, +30] 区间映射到 0~40
    wow_part = _clamp((model.wow_pct + 30) / 60 * 40, 0, 40)
    return _clamp(rank_part + wow_part)


def score_price_trend(card: CapabilityCard, scenario: ScenarioProfile) -> float:
    """近期有官方降价 → 加分；价格越低相对越好."""
    # 1) 绝对价格分（input + output）: 越便宜分越高
    blended = card.input_price_usd_per_mtok + card.output_price_usd_per_mtok * 0.5
    # 假设 blended ∈ [0.05, 25] 映射到 [100, 0]
    abs_part = _clamp(100 - (blended - 0.05) / (25 - 0.05) * 100, 0, 70)
    # 2) 近期降价：每 10% 降幅 +5 分，上限 30
    cut_part = _clamp(card.recent_price_cut_pct / 10 * 5, 0, 30)
    raw = abs_part + cut_part
    # 价格敏感场景：保留原分；不敏感场景：把价格分压缩到 50% 上限
    return _clamp(raw if scenario.sensitive_to_price else raw * 0.5)


def score_ecosystem_maturity(card: CapabilityCard, snapshot: WeekSnapshot) -> float:
    """所在厂商品牌榜排名 + 同厂商 Top10 模型数."""
    vendor = snapshot.find_vendor(card.vendor)
    if vendor is None:
        return 20.0  # 完全不在品牌榜 = 极低
    # 品牌排名：第 1 → 60，第 10 → 6
    rank_part = max(0, (11 - vendor.rank)) * 6  # 0~60
    # 同厂商进入 Top10 的模型数 × 10，上限 40
    same_vendor_count = sum(
        1 for m in snapshot.top_models if m.vendor == card.vendor
    )
    cnt_part = min(same_vendor_count * 15, 40)
    return _clamp(rank_part + cnt_part)


def score_capability_match(card: CapabilityCard, scenario: ScenarioProfile) -> float:
    """硬指标：context、thinking、tool_call 是否覆盖场景需求."""
    score = 0.0
    # 上下文：满足 → 40 分，部分满足按比例
    if card.context_tokens >= scenario.min_context_tokens:
        score += 40
    else:
        score += 40 * card.context_tokens / scenario.min_context_tokens

    # 长上下文额外加分（≥ 128K 即认为是「长上下文友好」）
    if scenario.needs_long_context:
        if card.context_tokens >= 128_000:
            score += 20
        else:
            score += 10 * card.context_tokens / 128_000
    else:
        score += 20  # 不需要长上下文，默认满分加成

    if scenario.needs_thinking:
        score += 20 if card.has_thinking_mode else 0
    else:
        score += 15

    if scenario.needs_tool_call:
        score += 20 if card.has_tool_call else 0
    else:
        score += 15

    return _clamp(score)


def score_substitutability(card: CapabilityCard, snapshot: WeekSnapshot) -> float:
    """同档位独立厂商替代品越多 → 分越高（越不至于绑死）."""
    # 同档位：input_price 落在该模型 0.5x ~ 2.0x 之间，且 vendor 不同
    lo = card.input_price_usd_per_mtok * 0.5
    hi = card.input_price_usd_per_mtok * 2.0
    other_vendors = set()
    for other_name, other_card in DEFAULT_CAPABILITY_CARDS.items():
        if other_name == card.model:
            continue
        if other_card.vendor == card.vendor:
            continue
        if lo <= other_card.input_price_usd_per_mtok <= hi:
            other_vendors.add(other_card.vendor)
    # 每多一家加 25 分，上限 100
    return _clamp(len(other_vendors) * 25, 0, 100)


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------


@dataclass
class ScoreCard:
    model: str
    vendor: str
    dimension_scores: Dict[str, float]
    final_score: float
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate(
    model_name: str,
    scenario: ScenarioProfile,
    snapshot: WeekSnapshot,
    cards: Optional[Dict[str, CapabilityCard]] = None,
) -> ScoreCard:
    cards = cards or DEFAULT_CAPABILITY_CARDS
    if model_name not in cards:
        raise KeyError(f"未知模型 {model_name}，请先在 capability_cards 注册")
    card = cards[model_name]
    model_row = snapshot.find_model(model_name)
    if model_row is None:
        # 没在榜上的，调用量分给 30 分基线（仍可入选，但显著降权）
        from copy import deepcopy
        model_row = deepcopy(snapshot.top_models[-1])
        model_row.model = model_name
        model_row.vendor = card.vendor
        model_row.rank = len(snapshot.top_models) + 5
        model_row.tokens_trillion = 0.0
        model_row.wow_pct = 0.0

    dim = {
        "call_volume_trend": score_call_volume_trend(model_row, snapshot),
        "price_trend": score_price_trend(card, scenario),
        "ecosystem_maturity": score_ecosystem_maturity(card, snapshot),
        "capability_match": score_capability_match(card, scenario),
        "substitutability": score_substitutability(card, snapshot),
    }
    final = sum(dim[k] * scenario.weight[k] for k in dim)
    if final >= 80:
        rec = "shortlist"
    elif final >= 60:
        rec = "trial"
    else:
        rec = "watch"
    return ScoreCard(
        model=model_name,
        vendor=card.vendor,
        dimension_scores={k: round(v, 1) for k, v in dim.items()},
        final_score=round(final, 1),
        recommendation=rec,
    )


def rank_models(
    scenario: ScenarioProfile,
    snapshot: WeekSnapshot,
    cards: Optional[Dict[str, CapabilityCard]] = None,
) -> List[ScoreCard]:
    cards = cards or DEFAULT_CAPABILITY_CARDS
    results = [evaluate(name, scenario, snapshot, cards) for name in cards]
    results.sort(key=lambda r: r.final_score, reverse=True)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    from weekly_tracker import load_week

    snap = load_week(prefer_remote=False)
    scenario = ScenarioProfile(
        name="高频对话 + 工具调用，预算敏感",
        needs_long_context=False,
        needs_thinking=False,
        needs_tool_call=True,
        sensitive_to_price=True,
        min_context_tokens=32_000,
    )
    results = rank_models(scenario, snap)
    print(f"==== 场景：{scenario.name} ====")
    print(f"{'模型':<22}{'厂商':<12}{'综合':<6}  推荐")
    for r in results:
        print(f"{r.model:<22}{r.vendor:<12}{r.final_score:<6}  {r.recommendation}")


if __name__ == "__main__":
    main()
