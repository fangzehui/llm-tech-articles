"""第 18 篇 smoke test: OpenRouter 周榜抓取 + 解析 + 信号打分 + 周报 + 可视化.

跑法：
    pytest tests/ -v
"""
from __future__ import annotations

import json
import os

import pytest

# 这些 import 依赖 conftest.py 把根目录加入 sys.path
from weekly_tracker import (
    DEFAULT_SAMPLE,
    ModelRow,
    VendorRow,
    WeekSnapshot,
    load_local,
    parse_snapshot,
)
from signal_analyzer import (
    DEFAULT_CAPABILITY_CARDS,
    ScenarioProfile,
    evaluate,
    rank_models,
    score_call_volume_trend,
    score_capability_match,
)
from report_generator import brief, full
from visualize import draw_top_models_bar, draw_weekly_trend


# ===========================================================================
# 1) 抓取/加载层
# ===========================================================================


def test_load_local_snapshot_structure(snapshot):
    """sample_weekly.json 必须能被加载，且字段合规。

    强校验：
      - top_models / top_vendors 至少 10 条；
      - 中国模型周调用量 > 美国（这是 W25 的事实）；
      - 全球数据为正。
    """
    assert isinstance(snapshot, WeekSnapshot)
    assert snapshot.week == "2026-W25"
    assert snapshot.start_date == "2026-06-15"
    assert snapshot.end_date == "2026-06-21"

    assert len(snapshot.top_models) >= 10
    assert len(snapshot.top_vendors) >= 10

    # 事实校验：中国调用量必须 > 美国
    assert snapshot.cn_total_t > snapshot.us_total_t
    assert snapshot.cn_us_ratio() >= 3.0, "本期中国应明显领先美国"

    # 历史趋势：DeepSeek-V4-Flash 应该有 ≥ 5 条历史
    assert len(snapshot.history_v4_flash) >= 5


def test_parse_snapshot_rank_monotonic(tmp_path):
    """构造一个 rank 错乱的 dict，parse_snapshot 应该抛 ValueError."""
    with open(DEFAULT_SAMPLE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # 把第二条 rank 改成 99
    raw["top_models"][1]["rank"] = 99
    with pytest.raises(ValueError, match="rank"):
        parse_snapshot(raw)


# ===========================================================================
# 2) 解析层 / 派生字段
# ===========================================================================


def test_derived_fields(snapshot):
    """cn_share + us_share + (其他) 应该 ≤ 100；cn_us_ratio 与原始数据一致."""
    cn_share = snapshot.cn_share()
    us_share = snapshot.us_share()
    assert 30 <= cn_share <= 60, f"中国份额异常: {cn_share}"
    assert 5 <= us_share <= 30, f"美国份额异常: {us_share}"

    # Top10 中中国席位至少 6 席（这是 W25 的事实，参见正文 §一）
    assert snapshot.top_n_china_count(10) >= 6

    # find_model 命中
    flash = snapshot.find_model("DeepSeek-V4-Flash")
    assert flash is not None
    assert flash.rank == 1
    assert flash.tokens_trillion >= 4.5

    # find_vendor 命中
    ds = snapshot.find_vendor("DeepSeek")
    assert ds is not None
    assert ds.rank == 1
    assert ds.streak_first_weeks >= 6


# ===========================================================================
# 3) 信号打分层
# ===========================================================================


def test_signal_dimensions_in_range(snapshot, default_scenario):
    """所有 5 个维度的分数都必须落在 [0, 100] 区间；final_score 也是."""
    for model_name in DEFAULT_CAPABILITY_CARDS:
        card = evaluate(model_name, default_scenario, snapshot)
        for dim, score in card.dimension_scores.items():
            assert 0 <= score <= 100, f"{model_name}/{dim} = {score} 超出 [0,100]"
        assert 0 <= card.final_score <= 100
        assert card.recommendation in {"shortlist", "trial", "watch"}


def test_signal_top_picks_match_reality(snapshot, default_scenario):
    """高频对话 + 价格敏感场景下，DeepSeek-V4-Flash 与 MiMo-V2.5
    应该都进入前 3 名（来自正文 §六、§八 的判断）.
    """
    results = rank_models(default_scenario, snapshot)
    top3 = [r.model for r in results[:3]]
    assert "DeepSeek-V4-Flash" in top3, f"V4-Flash 居然没进前 3: {top3}"
    assert "Xiaomi MiMo-V2.5" in top3, f"MiMo-V2.5 没进前 3: {top3}"

    # 第 1 名分数 > 70（高质量推荐）
    assert results[0].final_score >= 70


def test_signal_call_volume_trend_monotonic(snapshot):
    """调用量趋势分数：rank 越前 + wow 越正，分数越高."""
    flash = snapshot.find_model("DeepSeek-V4-Flash")
    sonnet = snapshot.find_model("Claude Sonnet 4.6")
    assert flash is not None and sonnet is not None
    s_flash = score_call_volume_trend(flash, snapshot)
    s_sonnet = score_call_volume_trend(sonnet, snapshot)
    assert s_flash > s_sonnet, "V4-Flash 调用量信号应严格高于 Sonnet 4.6"


def test_signal_capability_long_context(snapshot):
    """场景需要 ≥ 256K 上下文时，1M 上下文模型应明显得分更高."""
    long_scenario = ScenarioProfile(
        name="long-doc",
        needs_long_context=True,
        min_context_tokens=256_000,
    )
    short_card = DEFAULT_CAPABILITY_CARDS["Claude Sonnet 4.6"]  # 200K
    long_card = DEFAULT_CAPABILITY_CARDS["DeepSeek-V4-Flash"]   # 1M

    s_short = score_capability_match(short_card, long_scenario)
    s_long = score_capability_match(long_card, long_scenario)
    assert s_long > s_short, "长文档场景下 1M 模型必须严格胜过 200K 模型"


# ===========================================================================
# 4) 周报生成
# ===========================================================================


def test_report_full_contains_critical_facts(snapshot):
    md = full(snapshot)
    # 关键事实必须出现在周报里
    assert "46.7" in md, "全球总量缺失"
    assert "18.81" in md, "中国总量缺失"
    assert "5.76" in md, "美国总量缺失"
    assert "DeepSeek-V4-Flash" in md
    assert "MiMo-V2.5" in md
    # 表头
    assert "周调用量" in md
    assert "市场份额" in md


def test_report_brief_compact(snapshot):
    s = brief(snapshot)
    # brief 必须 ≤ 200 字（含标点空格）
    assert len(s) <= 200, f"brief 长度 {len(s)} 超过 200 字"
    assert "DeepSeek-V4-Flash" in s
    assert "2026-06-15" in s


# ===========================================================================
# 5) 可视化（dry_run，不依赖 matplotlib 实际渲染）
# ===========================================================================


def test_visualize_top_models_dry_run(snapshot):
    payload = draw_top_models_bar(snapshot, dry_run=True)
    assert len(payload["labels"]) == len(snapshot.top_models)
    assert len(payload["values"]) == len(snapshot.top_models)
    # 颜色必须只有两种值（中红 / 美蓝）
    unique_colors = set(payload["colors"])
    assert unique_colors.issubset({"#d23f31", "#1f78b4"})
    # 至少有中国模型（红色）
    assert "#d23f31" in unique_colors


def test_visualize_trend_dry_run(snapshot):
    payload = draw_weekly_trend(snapshot, model="DeepSeek-V4-Flash", dry_run=True)
    assert len(payload["weeks"]) >= 5
    assert all(t > 0 for t in payload["tokens"])
    # 最后一周（W25）应该是当前 snapshot 中的 4.94
    assert payload["tokens"][-1] == pytest.approx(4.94, rel=1e-3)


def test_visualize_top_models_real_save(snapshot, tmp_path):
    """真实渲染到 PNG 文件，验证 matplotlib 整条链路正常."""
    out = tmp_path / "top.png"
    draw_top_models_bar(snapshot, out_path=str(out))
    assert out.exists()
    assert out.stat().st_size > 1024, "PNG 文件过小，渲染可能失败"
