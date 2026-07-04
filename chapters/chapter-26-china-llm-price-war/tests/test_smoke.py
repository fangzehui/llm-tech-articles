"""tests/test_smoke.py

Chapter 26 冒烟测试：确保三个脚本 import 得到、核心函数按预期返回。
运行方式：
    cd chapters/chapter-26-china-llm-price-war
    pytest tests/ -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 把 chapter 目录加进 sys.path
CHAPTER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHAPTER_DIR))

from src import cost_compare, price_timeline, pricing_sensitivity  # noqa: E402


# ---------- pricing_sensitivity ----------
def test_effective_price_no_cache():
    # 命中率 0 时，有效单价 = 列表价
    p = pricing_sensitivity.effective_price(1.0, 0.0, 0.1)
    assert p == pytest.approx(1.0)


def test_effective_price_full_cache():
    # 命中率 100% + 1 折 → 有效单价 = list × 0.1
    p = pricing_sensitivity.effective_price(1.0, 1.0, 0.1)
    assert p == pytest.approx(0.1)


def test_effective_price_half_and_half():
    # 命中率 50% + 5 折 → 有效单价 = 0.5 + 0.5 × 0.5 = 0.75
    p = pricing_sensitivity.effective_price(1.0, 0.5, 0.5)
    assert p == pytest.approx(0.75)


def test_effective_price_invalid_hit_rate():
    with pytest.raises(ValueError):
        pricing_sensitivity.effective_price(1.0, 1.5, 0.1)
    with pytest.raises(ValueError):
        pricing_sensitivity.effective_price(1.0, -0.1, 0.1)


def test_is_sustainable_cut_true():
    # 有效单价 0.29，成本 0.2 → 可持续
    ok = pricing_sensitivity.is_sustainable_cut(0.5, 0.6, 0.1, 0.2)
    assert ok is True


def test_is_sustainable_cut_false():
    # 免费定价 + 成本 > 0 → 一定倒挂
    ok = pricing_sensitivity.is_sustainable_cut(0.0, 0.0, 0.1, 0.2)
    assert ok is False


def test_margin_ratio_positive():
    # 参数：list=0.5, hit=0.6, discount=0.1, cost=0.2
    # effective = 0.5*0.4 + 0.5*0.6*0.1 = 0.23
    # margin = (0.23 - 0.2) / 0.23 ≈ 0.1304
    ratio = pricing_sensitivity.margin_ratio(0.5, 0.6, 0.1, 0.2)
    assert ratio > 0
    assert ratio == pytest.approx((0.23 - 0.2) / 0.23, abs=1e-3)


def test_analyze_returns_all_fields():
    s = pricing_sensitivity.DEFAULT_SCENARIOS[0]
    result = pricing_sensitivity.analyze(s)
    assert set(result.keys()) == {"model", "effective_price", "sustainable", "margin_ratio"}
    assert result["model"] == s.model_name


# ---------- cost_compare ----------
def test_cost_compare_default_models_count():
    assert len(cost_compare.MODELS_2026Q2) == 6


def test_monthly_cost_zero_tokens():
    m = cost_compare.MODELS_2026Q2[0]
    assert cost_compare.monthly_cost(m, 0, 0, 0.5) == 0


def test_monthly_cost_only_output():
    # 只算输出、cache_hit_rate 无关
    m = cost_compare.ModelPricing("test", 1.0, 10.0, 0.1)
    cost = cost_compare.monthly_cost(m, 0, 100, 0.5)
    assert cost == pytest.approx(1000.0)


def test_monthly_cost_cache_hit_reduces_input():
    m = cost_compare.ModelPricing("test", 1.0, 10.0, 0.1)
    no_cache = cost_compare.monthly_cost(m, 100, 0, 0.0)
    full_cache = cost_compare.monthly_cost(m, 100, 0, 1.0)
    assert full_cache < no_cache
    assert full_cache == pytest.approx(no_cache * 0.1)


def test_rank_by_cost_returns_sorted():
    rows = cost_compare.rank_by_cost(cost_compare.MODELS_2026Q2, 1000, 300, 0.5)
    costs = [c for _, c in rows]
    assert costs == sorted(costs)
    assert len(rows) == 6


def test_render_markdown_table_contains_all_models():
    rows = cost_compare.rank_by_cost(cost_compare.MODELS_2026Q2, 1000, 300, 0.5)
    md = cost_compare.render_markdown_table(rows)
    for m in cost_compare.MODELS_2026Q2:
        assert m.name in md
    assert "月账单" in md


def test_monthly_cost_invalid_hit_rate():
    m = cost_compare.MODELS_2026Q2[0]
    with pytest.raises(ValueError):
        cost_compare.monthly_cost(m, 100, 100, 1.5)


# ---------- price_timeline ----------
def test_timeline_has_events():
    assert len(price_timeline.TIMELINE) >= 15


def test_timeline_covers_three_waves():
    for wave in ("wave1", "wave2", "wave3"):
        events = price_timeline.events_by_wave(wave)  # type: ignore[arg-type]
        assert len(events) > 0, f"wave {wave} should have events"


def test_timeline_events_have_sources():
    for e in price_timeline.TIMELINE:
        assert e.source_url.startswith(("http://", "https://")), \
            f"event {e.date} missing valid source_url"
        assert e.source_title, f"event {e.date} missing source_title"


def test_events_by_vendor_case_insensitive():
    a = price_timeline.events_by_vendor("DeepSeek")
    b = price_timeline.events_by_vendor("deepseek")
    assert a == b
    assert len(a) >= 3  # V3、R1、错峰、V3.2 至少 3 条


def test_export_json(tmp_path):
    out = tmp_path / "timeline.json"
    price_timeline.export_json(out)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "DeepSeek" in text
    assert "2024-05-15" in text


def test_render_markdown_table_timeline():
    md = price_timeline.render_markdown_table()
    assert "| 日期 | 厂商 |" in md
    assert "2024-05-15" in md


# ---------- 集成：三份数据交叉验证 ----------
def test_all_default_scenarios_sustainable():
    # 内置样本的三个厂商应该都是可持续的（否则说明假设有误）
    for s in pricing_sensitivity.DEFAULT_SCENARIOS:
        r = pricing_sensitivity.analyze(s)
        assert r["sustainable"] is True, f"{s.model_name} 内置样本应可持续"


def test_deepseek_in_both_pricing_and_timeline():
    # DeepSeek 应该同时出现在 cost_compare 和 price_timeline 里
    names = {m.name for m in cost_compare.MODELS_2026Q2}
    vendors = {e.vendor for e in price_timeline.TIMELINE}
    assert any("DeepSeek" in n for n in names)
    assert "DeepSeek" in vendors
