"""Smoke tests for chapter-28 DeepSeek-V3.2 二五折半年记 配套源码。

覆盖：
- ScenarioScorer 的分档、批量、异常边界
- cost_quality_curve 的排序、筛选、快照
- DeepSeekTierRouter 的多档路由与成本估算
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.scenario_scorer import (  # noqa: E402
    BATCH_DATA_CLEANING,
    CUSTOMER_SERVICE,
    DEFAULT_2026H1_SCENARIOS,
    LONG_DOC_SUMMARY,
    Recommendation,
    STRONG_REASONING,
    ScenarioProfile,
    ScenarioScorer,
)
from src.cost_quality_curve import (  # noqa: E402
    ModelPoint,
    cheapest_above_quality,
    default_2026h1_snapshot,
    rank_by_cost_efficiency,
)
from src.tier_router import (  # noqa: E402
    DeepSeekTier,
    DeepSeekTierRouter,
    Request,
)


# ------------------- ScenarioScorer -------------------


def test_scorer_batch_data_cleaning_is_strong():
    """批量数据清洗场景应命中 STRONG 推荐。"""
    scorer = ScenarioScorer()
    assert scorer.recommend(BATCH_DATA_CLEANING) == Recommendation.STRONG
    s = scorer.score(BATCH_DATA_CLEANING)
    assert 0.8 <= s <= 0.85, f"expected score in [0.80, 0.85], got {s}"


def test_scorer_long_doc_summary_is_strong():
    """长文档摘要场景应命中 STRONG 推荐。"""
    scorer = ScenarioScorer()
    assert scorer.recommend(LONG_DOC_SUMMARY) == Recommendation.STRONG
    assert scorer.score(LONG_DOC_SUMMARY) >= 0.7


def test_scorer_strong_reasoning_is_not_recommended():
    """强推理场景应命中 NOT_RECOMMENDED。"""
    scorer = ScenarioScorer()
    assert scorer.recommend(STRONG_REASONING) == Recommendation.NOT_RECOMMENDED
    assert scorer.score(STRONG_REASONING) < 0.45


def test_scorer_customer_service_is_worth_try():
    """客服对话场景应命中 WORTH_TRY。"""
    scorer = ScenarioScorer()
    assert scorer.recommend(CUSTOMER_SERVICE) == Recommendation.WORTH_TRY


def test_scorer_batch_recommend_orders_correctly():
    """批量推荐应按分数降序。"""
    scorer = ScenarioScorer()
    results = scorer.batch_recommend(DEFAULT_2026H1_SCENARIOS)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    # 强推理必然是最后一名
    assert results[-1]["scenario"] == "strong_reasoning_agent"


def test_scorer_explain_breakdown_sums_to_score():
    """breakdown 各项之和应等于 score。"""
    scorer = ScenarioScorer()
    for profile in DEFAULT_2026H1_SCENARIOS:
        exp = scorer.explain(profile)
        breakdown_sum = sum(exp["breakdown"].values())
        assert abs(breakdown_sum - exp["score"]) < 1e-6


def test_scorer_rejects_out_of_range():
    """维度分数越界应抛 ValueError。"""
    with pytest.raises(ValueError):
        ScenarioProfile(
            name="bad",
            cost_sensitivity=1.5,
            context_density=0.5,
            quality_tolerance=0.5,
            latency_tolerance=0.5,
        )


def test_scorer_weights_sum_to_one():
    """权重和应为 1.0。"""
    total = (
        ScenarioScorer.W_COST
        + ScenarioScorer.W_CONTEXT
        + ScenarioScorer.W_QUALITY
        + ScenarioScorer.W_LATENCY
    )
    assert abs(total - 1.0) < 1e-9


# ------------------- cost_quality_curve -------------------


def test_snapshot_deepseek_is_most_efficient():
    """默认快照下 DeepSeek-V3.2 应是 cost-per-quality 最低的一家。"""
    models = default_2026h1_snapshot()
    ranked = rank_by_cost_efficiency(models)
    assert ranked[0].name == "DeepSeek-V3.2"
    # 首名应显著低于第二名
    assert ranked[0].cost_per_quality_point < ranked[1].cost_per_quality_point


def test_cheapest_above_quality_filter():
    """在质量下限 80 分之上，应挑出 Qwen3-Max（唯一满足）。"""
    models = default_2026h1_snapshot()
    picked = cheapest_above_quality(models, min_quality=80.0)
    assert picked is not None
    assert picked.name == "Qwen3-Max"


def test_cheapest_above_quality_returns_none_when_no_match():
    """质量下限过高时应返回 None。"""
    models = default_2026h1_snapshot()
    assert cheapest_above_quality(models, min_quality=99.0) is None


def test_model_point_validates_input():
    """ModelPoint 应校验负成本与越界质量分。"""
    with pytest.raises(ValueError):
        ModelPoint("bad", cost_per_1m=-1.0, quality_score=50.0)
    with pytest.raises(ValueError):
        ModelPoint("bad2", cost_per_1m=1.0, quality_score=150.0)


def test_plot_cost_quality_curve_writes_png(tmp_path):
    """plot 应真正落盘 PNG 文件。若无 matplotlib 环境则跳过。"""
    matplotlib = pytest.importorskip("matplotlib")
    from src.cost_quality_curve import plot_cost_quality_curve

    save = tmp_path / "curve.png"
    ret = plot_cost_quality_curve(default_2026h1_snapshot(), str(save))
    assert Path(ret).exists()
    assert Path(ret).stat().st_size > 100


# ------------------- DeepSeekTierRouter -------------------


def test_router_long_context_prefers_v32_econ():
    """长上下文（>=32K）非强推理走 V32_ECON。"""
    router = DeepSeekTierRouter()
    req = Request(
        prompt_tokens=60_000,
        expected_output_tokens=2_000,
        complexity=0.5,
        needs_reasoning=False,
        budget_sensitivity=0.3,
    )
    assert router.route(req) == DeepSeekTier.V32_ECON


def test_router_strong_reasoning_goes_r1():
    """强推理 + 高复杂度 -> R1_REASON。"""
    router = DeepSeekTierRouter()
    req = Request(
        prompt_tokens=4_000,
        expected_output_tokens=2_000,
        complexity=0.9,
        needs_reasoning=True,
        budget_sensitivity=0.3,
    )
    assert router.route(req) == DeepSeekTier.R1_REASON


def test_router_low_complexity_budget_sensitive_goes_v32():
    """简单任务 + 预算敏感 -> V32_ECON。"""
    router = DeepSeekTierRouter()
    req = Request(
        prompt_tokens=2_000,
        expected_output_tokens=500,
        complexity=0.2,
        needs_reasoning=False,
        budget_sensitivity=0.7,
    )
    assert router.route(req) == DeepSeekTier.V32_ECON


def test_router_default_falls_back_to_v3_main():
    """中等复杂度 + 中等预算敏感 -> V3_MAIN 默认档。"""
    router = DeepSeekTierRouter()
    req = Request(
        prompt_tokens=8_000,
        expected_output_tokens=2_000,
        complexity=0.5,
        needs_reasoning=False,
        budget_sensitivity=0.4,
    )
    assert router.route(req) == DeepSeekTier.V3_MAIN


def test_router_estimate_cost_makes_sense():
    """成本估算：1M in + 1M out ≈ 5 元。"""
    router = DeepSeekTierRouter()
    req = Request(
        prompt_tokens=1_000_000,
        expected_output_tokens=1_000_000,
        complexity=0.5,
        needs_reasoning=False,
        budget_sensitivity=0.5,
    )
    cost = router.estimate_cost_yuan(req, DeepSeekTier.V32_ECON)
    assert abs(cost - 5.0) < 1e-6


def test_router_batch_summary():
    """批量路由汇总统计。"""
    router = DeepSeekTierRouter()
    reqs = [
        Request(60_000, 1_000, 0.5, False, 0.3),  # V32 (long ctx)
        Request(2_000, 500, 0.2, False, 0.7),     # V32 (simple)
        Request(4_000, 2_000, 0.9, True, 0.3),    # R1
        Request(8_000, 2_000, 0.5, False, 0.4),   # V3_MAIN
    ]
    summary = router.summarize_batch(router.batch_route(reqs))
    assert summary["total_calls"] == 4
    by_tier = summary["by_tier"]
    assert by_tier[DeepSeekTier.V32_ECON.value]["calls"] == 2
    assert by_tier[DeepSeekTier.R1_REASON.value]["calls"] == 1
    assert by_tier[DeepSeekTier.V3_MAIN.value]["calls"] == 1
    assert summary["total_cost_yuan"] > 0


def test_router_rejects_bad_request():
    """Request 参数越界应抛 ValueError。"""
    with pytest.raises(ValueError):
        Request(-1, 100, 0.5, False, 0.5)
    with pytest.raises(ValueError):
        Request(100, 100, 1.5, False, 0.5)
    with pytest.raises(ValueError):
        Request(100, 100, 0.5, False, 2.0)


def test_router_extreme_budget_sensitivity_forces_v32():
    """budget_sensitivity>=0.8 且非强推理 -> V32_ECON 兜底。"""
    router = DeepSeekTierRouter()
    req = Request(
        prompt_tokens=8_000,
        expected_output_tokens=2_000,
        complexity=0.5,
        needs_reasoning=False,
        budget_sensitivity=0.85,
    )
    assert router.route(req) == DeepSeekTier.V32_ECON
