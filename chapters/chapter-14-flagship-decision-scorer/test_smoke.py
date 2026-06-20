"""第 14 篇 smoke test：四强决策评分器关键路径覆盖.

跑法：
    pytest test_smoke.py -q
"""

from __future__ import annotations

import pytest

from decision_scorer import (
    MODELS,
    ModelProfile,
    Scenario,
    biz_flow_scenario,
    multimodal_scenario,
    recommend,
    rnd_agent_scenario,
    score_model,
)


def test_models_registry_complete() -> None:
    """4 款旗舰必须都在注册表里，能力分都在 0-100 区间."""
    assert set(MODELS) == {"GLM-5.2", "Fable 5", "GPT-5 Preview", "Gemini 3.0"}
    for m in MODELS.values():
        for field in (
            m.capability_code,
            m.capability_agent,
            m.capability_multimodal,
            m.capability_general,
            m.cn_compliance,
            m.sla_grade,
        ):
            assert 0 <= field <= 100
        assert m.price_input >= 0 and m.price_output >= 0


def test_score_model_blocks_non_compliant() -> None:
    """开启 require_cn_compliance 时海外模型必须被合规拦截."""
    sc = biz_flow_scenario()
    blocked_names = {
        r["name"] for r in (score_model(m, sc) for m in MODELS.values()) if r["blocked"]
    }
    # 仅 GLM-5.2 cn_compliance=100，其余三家应全部被拦
    assert blocked_names == {"Claude Fable 5", "GPT-5 Preview", "Gemini 3.0 Pro"}


def test_score_model_budget_block() -> None:
    """超预算时应当被预算拦截（不会因为合规先被拦）."""
    fable = MODELS["Fable 5"]
    sc = Scenario(
        name="低预算",
        monthly_input_tokens_m=10, monthly_output_tokens_m=2.5,
        require_cn_compliance=False, max_monthly_budget=10.0,
    )
    r = score_model(fable, sc)
    assert r["score"] == -1
    assert r["blocked"] and "超预算" in r["blocked"]


def test_business_flow_recommend_glm_first() -> None:
    """业务流场景下 GLM-5.2 应该是分数最高且唯一未被拦的."""
    ranked = recommend(biz_flow_scenario())
    assert ranked[0]["name"] == "GLM-5.2"
    assert ranked[0]["score"] > 0
    # 后面三家必须全部 blocked
    for r in ranked[1:]:
        assert r["score"] == -1


def test_research_agent_recommend_overseas_lead() -> None:
    """研发 Agent 场景（无合规约束）：编程/Agent 权重最高，
    Fable 5 与 GPT-5 Preview 应当排在 GLM-5.2 之前."""
    ranked = recommend(rnd_agent_scenario())
    names_by_rank = [r["name"] for r in ranked]
    assert "Claude Fable 5" in names_by_rank[:2] or "GPT-5 Preview" in names_by_rank[:2]
    assert names_by_rank[0] != "GLM-5.2"


def test_multimodal_recommend_gemini_lead() -> None:
    """多模态场景应当 Gemini 3.0 Pro 排第一."""
    ranked = recommend(multimodal_scenario())
    assert ranked[0]["name"] == "Gemini 3.0 Pro"


def test_score_is_deterministic() -> None:
    """同一组 (模型, 场景) 两次打分结果必须完全一致."""
    sc = rnd_agent_scenario()
    for m in MODELS.values():
        a = score_model(m, sc)
        b = score_model(m, sc)
        assert a == b
