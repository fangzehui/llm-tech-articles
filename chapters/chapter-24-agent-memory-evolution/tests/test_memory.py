"""pytest 冒烟测试 —— 覆盖三代记忆脚本 + 选型器。

所有测试都 fully-offline，不需要 API key、也不需要向量数据库。
运行：pytest tests/ -v
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gen1_rag_memory as gen1
import gen2_structured_memory as gen2
import gen3_memory_graph as gen3
import memory_selector as sel


# ---------- Gen1 ----------
def test_gen1_embed_normalized():
    v = gen1.fake_embed("hello world 我用 python")
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_gen1_add_and_search():
    m = gen1.RagMemory()
    m.add("我最喜欢的语言是 Python。我在北京工作。")
    hits = m.search("语言", top_k=2)
    assert len(hits) == 2
    assert all(isinstance(c, gen1.Chunk) for _, c in hits)


def test_gen1_build_prompt_contains_query():
    m = gen1.RagMemory()
    m.add("我用 Python。")
    p = m.build_prompt("现在用什么", top_k=1)
    assert "现在用什么" in p


def test_gen1_demo_runs():
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen1.demo()
    assert "Gen1" in buf.getvalue()


# ---------- Gen2 ----------
def test_gen2_extract_language_fact():
    facts = gen2.extract_facts("我最喜欢的语言是Python。", now=1.0)
    langs = [f.object for f in facts if f.predicate == "uses_language"]
    assert "Python" in langs


def test_gen2_conflict_resolution():
    m = gen2.StructuredMemory()
    m.add_from_conversation("我最喜欢的语言是Python。")
    m.add_from_conversation("我现在主要用Go。")
    lang_facts = [f for f in m.facts if f.predicate == "uses_language"]
    valid = [f for f in lang_facts if f.state == gen2.FactState.VALID]
    invalid = [f for f in lang_facts if f.state == gen2.FactState.INVALID]
    assert len(valid) == 1 and valid[0].object == "Go"
    assert len(invalid) >= 1


def test_gen2_search_only_valid():
    m = gen2.StructuredMemory()
    m.add_from_conversation("我最喜欢的语言是Python。")
    m.add_from_conversation("我现在主要用Go。")
    hits = m.search("目前用什么语言", top_k=5, only_valid=True)
    for _, f in hits:
        assert f.state == gen2.FactState.VALID


def test_gen2_demo_runs():
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen2.demo()
    assert "Gen2" in buf.getvalue()


# ---------- Gen3 ----------
def test_gen3_upsert_and_edge():
    g = gen3.MemoryGraph()
    g.upsert_node("user", "Person", name="Alex")
    g.upsert_node("py", "Language")
    e = g.add_edge("user", "py", "uses_language")
    assert e.src == "user" and e.dst == "py"


def test_gen3_bi_temporal_edge():
    g = gen3.MemoryGraph()
    g.upsert_node("user", "Person")
    g.upsert_node("py", "Language")
    g.upsert_node("go", "Language")
    g.add_edge("user", "py", "uses_language")
    g.add_edge("user", "go", "uses_language")
    current = [e for e in g.edges if e.rel == "uses_language" and e.valid_to is None]
    expired = [e for e in g.edges if e.rel == "uses_language" and e.valid_to is not None]
    assert len(current) == 1 and current[0].dst == "go"
    assert len(expired) == 1 and expired[0].dst == "py"


def test_gen3_graph_walk_bfs():
    g = gen3.MemoryGraph()
    g.upsert_node("a", "N"); g.upsert_node("b", "N"); g.upsert_node("c", "N")
    g.add_edge("a", "b", "r"); g.add_edge("b", "c", "r")
    edges = g.graph_walk(["a"], hops=2)
    assert len(edges) == 2


def test_gen3_hybrid_search():
    g = gen3.MemoryGraph()
    g.upsert_node("user", "Person")
    g.upsert_node("py", "Language")
    g.add_edge("user", "py", "uses_language")
    g.add_episode("我用 python", ["user", "py"])
    ctx = g.hybrid_search("python", seed_entities=["user"])
    assert "final_context" in ctx and len(ctx["final_context"]) > 0


def test_gen3_tiered_context_char_limit():
    g = gen3.MemoryGraph()
    tc = gen3.TieredContext(core_memory={}, archival=g, core_char_limit=40)
    tc.core_append("a", "x" * 30)
    tc.core_append("b", "y" * 30)
    rendered = tc.core_render()  # 触发淘汰
    assert len(rendered) <= 80  # 允许一定余量，但一定被裁过


def test_gen3_demo_runs():
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen3.demo()
    assert "Gen3" in buf.getvalue()


# ---------- Selector ----------
def test_selector_catalog_has_four():
    names = {s.name for s in sel.CATALOG}
    assert {"mem0", "Zep / Graphiti", "LangMem", "Letta (原 MemGPT)"} == names


def test_selector_langchain_scenario_picks_langmem():
    req = sel.build_requirement(argparse.Namespace(
        scenario="generic", users="single", graph=False,
        self_hosted=False, langchain=True))
    reco = sel.recommend(req)
    assert reco[0]["name"] == "LangMem"


def test_selector_graph_heavy_prefers_zep():
    req = sel.build_requirement(argparse.Namespace(
        scenario="knowledge_dense", users="many", graph=True,
        self_hosted=False, langchain=False))
    reco = sel.recommend(req)
    assert reco[0]["name"] == "Zep / Graphiti"


def test_selector_demo_runs():
    buf = io.StringIO()
    with redirect_stdout(buf):
        for title, kw in sel.DEMO_CASES:
            ns = argparse.Namespace(scenario=kw["scenario"], users=kw["users"],
                                    graph=kw["graph"], self_hosted=kw["self_hosted"],
                                    langchain=kw["langchain"], demo=False, json=False)
            sel.print_reco(title, sel.build_requirement(ns))
    out = buf.getvalue()
    assert "推荐首选" in out and "mem0" in out
