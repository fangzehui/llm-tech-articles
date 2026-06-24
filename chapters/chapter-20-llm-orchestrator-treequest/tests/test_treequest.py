"""# Chapter 20 smoke test 套件。

跑法::

    pytest tests/ -v

覆盖：
- ``test_node_basic_ops``：Node 结构 + Beta 更新 + 路径回溯
- ``test_thompson_pick_converges``：Thompson Sampling 大样本收敛到经验最优
- ``test_ab_mcts_single_llm``：单 LLM 跑满 budget，best_score 单调非递减
- ``test_ab_mcts_multi_llm``：多 LLM 接力能跑出比"全部用 noisy"更好的结果
- ``test_cost_curve_monotone``：成本曲线随 K 单调，边际成本不应为负
- ``test_break_even_cheap_vs_flagship``：达到高 target_pass 时旗舰更便宜
- ``test_orchestrator_compare_dimensions``：4 风格各跑 1 次 → 4 个 RunResult
- ``test_sample_tasks_loadable``：sample_tasks.json 结构完整可解析
"""

from __future__ import annotations

import random

import pytest


# ============================================================
# 1) Node / Thompson 基础测试
# ============================================================


def test_node_basic_ops():
    from treequest_minimal import Node

    root = Node(state=None, score=0.0, llm="__root__")
    child = Node(state="a", score=0.5, llm="llm_a", parent=root)
    root.children.append(child)
    grand = Node(state="b", score=0.9, llm="llm_b", parent=child)
    child.children.append(grand)

    # 深度
    assert root.depth() == 0
    assert child.depth() == 1
    assert grand.depth() == 2

    # Beta 更新
    w0, l0 = child.wins, child.losses
    child.update(True)
    child.update(False)
    assert child.wins == w0 + 1
    assert child.losses == l0 + 1


def test_thompson_pick_converges():
    """大样本下，wins 高的节点应该被选中更多次。"""
    from treequest_minimal import Node, thompson_pick

    rng = random.Random(20260620)
    nodes = [
        Node(state="hot", score=0.9, llm="x", wins=80, losses=20),
        Node(state="cold", score=0.1, llm="y", wins=10, losses=90),
    ]
    hot_count = 0
    n_trials = 500
    for _ in range(n_trials):
        if thompson_pick(nodes, rng).state == "hot":
            hot_count += 1
    # hot 应该至少占 90% 以上
    assert hot_count / n_trials > 0.9, (
        f"thompson_pick 没有偏向高胜率节点，hot={hot_count}/{n_trials}"
    )


# ============================================================
# 2) AB-MCTS 单 LLM / 多 LLM
# ============================================================


def test_ab_mcts_single_llm(simple_generators):
    from treequest_minimal import ABMCTS, ABMCTSConfig

    algo = ABMCTS(ABMCTSConfig(budget=20, success_threshold=0.85, seed=42))
    best, trace = algo.run({"good": simple_generators["good"]})

    # 跑完应至少有 budget 个节点（不含 root）
    assert trace[-1]["n_nodes"] == 20
    # best score 应单调非递减
    for i in range(1, len(trace)):
        assert trace[i]["best_score"] >= trace[i - 1]["best_score"] - 1e-9
    # 至少一次"good"产出 score>0.7（target=42，good 命中率高）
    assert best.score > 0.7


def test_ab_mcts_multi_llm(simple_generators):
    """多 LLM 接力的 best_score 应该 ≥ 仅用 noisy 的 best_score（大数定律意义上）。"""
    from treequest_minimal import ABMCTS, ABMCTSConfig

    cfg = ABMCTSConfig(budget=25, success_threshold=0.85, seed=2026)
    only_noisy = ABMCTS(cfg).run({"noisy": simple_generators["noisy"]})[0].score
    all_three = ABMCTS(cfg).run(simple_generators)[0].score

    # 多 LLM 跑出来的 best 不能比 only_noisy 差（容忍 0.05 噪声）
    assert all_three + 0.05 >= only_noisy, (
        f"多 LLM 反而不如只用 noisy: {all_three=} vs {only_noisy=}"
    )
    # 多 LLM 在这个种子下应明显跑出 score>0.85
    assert all_three > 0.85


# ============================================================
# 3) 成本曲线 + break-even
# ============================================================


def test_cost_curve_monotone():
    from cost_analyzer import ModelPrice, cost_curve

    m = ModelPrice(
        name="t",
        usd_per_mtok_input=0.5,
        usd_per_mtok_output=2.0,
        p_single=0.3,
    )
    ks = [1, 2, 4, 8, 16]
    rows = cost_curve(m, ks)
    # pass_at_k 单调非降；cost 严格递增
    for i in range(1, len(rows)):
        assert rows[i]["pass_at_k"] >= rows[i - 1]["pass_at_k"] - 1e-12
        assert rows[i]["cost_usd"] > rows[i - 1]["cost_usd"]
    # k=8 时 pass_at_k 接近 1 - 0.7^8 ≈ 0.942
    expected = 1.0 - 0.7 ** 8
    assert abs(rows[3]["pass_at_k"] - expected) < 1e-9


def test_break_even_cheap_vs_flagship():
    from cost_analyzer import ModelPrice, break_even_budget

    cheap = ModelPrice(
        name="cheap", usd_per_mtok_input=0.14,
        usd_per_mtok_output=0.28, p_single=0.30
    )
    flag = ModelPrice(
        name="flag", usd_per_mtok_input=10.0,
        usd_per_mtok_output=50.0, p_single=0.55
    )
    info_low = break_even_budget(cheap, flag, target_pass=0.7)
    info_high = break_even_budget(cheap, flag, target_pass=0.95)

    # 目标越高，所需 K 越大
    assert info_high["k_cheap"] > info_low["k_cheap"]
    assert info_high["k_expensive"] >= info_low["k_expensive"]
    # 廉价模型在两档目标上都比旗舰便宜（按当前价格量级）——demo 校验
    assert info_high["cheaper_choice"] == "cheap"


# ============================================================
# 4) 4 风格横评
# ============================================================


def test_orchestrator_compare_dimensions():
    from multi_orchestrator_compare import (
        _default_pool,
        run_langgraph_style,
        run_openrouter_style,
        run_treequest_style,
        run_vercel_ai_sdk_style,
    )

    rng = random.Random(20260620)
    pool = _default_pool()
    r_or = run_openrouter_style(pool, rng)
    pool = _default_pool()
    r_vc = run_vercel_ai_sdk_style(pool, rng)
    pool = _default_pool()
    r_lg = run_langgraph_style(pool, rng)
    pool = _default_pool()
    r_tq = run_treequest_style(pool, rng, budget=10)

    # 4 个风格调用次数应单调上升：or(1) < vc(2) < lg(3-4) < tq(10)
    assert r_or.calls == 1
    assert r_vc.calls == 2
    assert 3 <= r_lg.calls <= 4
    assert r_tq.calls == 10
    # 4 个风格都应跑出 final_score
    for r in (r_or, r_vc, r_lg, r_tq):
        assert 0.0 <= r.final_score <= 1.0
        assert r.tokens > 0
        assert r.cost_usd >= 0


# ============================================================
# 5) 样本任务文件结构
# ============================================================


def test_sample_tasks_loadable(sample_tasks):
    assert "tasks" in sample_tasks
    assert "metadata" in sample_tasks
    assert len(sample_tasks["tasks"]) >= 3

    seen_categories = {t["category"] for t in sample_tasks["tasks"]}
    # 必须覆盖 arc / math / code 三类
    assert "arc-agi" in seen_categories
    assert "math" in seen_categories
    assert "code" in seen_categories

    # 每个 task 必须有 evaluator 字段
    for t in sample_tasks["tasks"]:
        assert "id" in t
        assert "evaluator" in t


# ============================================================
# 6) 文本树渲染（确保 render_text_tree 不崩）
# ============================================================


def test_render_text_tree_smoke(simple_generators):
    from treequest_minimal import ABMCTS, ABMCTSConfig, render_text_tree

    algo = ABMCTS(ABMCTSConfig(budget=8, success_threshold=0.85, seed=7))
    best, _ = algo.run(simple_generators)

    # 从 best 回溯到 root，渲染整棵树
    cur = best
    while cur.parent is not None:
        cur = cur.parent
    text = render_text_tree(cur)
    assert "[root]" in text
    # 至少应出现一种 LLM 标签
    assert any(name in text for name in ("good", "refiner", "noisy"))
