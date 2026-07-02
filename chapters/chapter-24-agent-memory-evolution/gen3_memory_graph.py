"""
第三代记忆：记忆图谱（模拟 Letta / Zep-Graphiti 风格）

核心思想：
1. 记忆不再是"扁平事实列表"，而是"实体-关系-事件"三层图。
   - Entities（节点）：用户、公司、产品、地点……
   - Facts / Relations（有向边）：user -[prefers_drink]-> latte
   - Episodes（时间戳事件）：一次对话/一次工具调用，指向它涉及的实体
2. 上下文分层（Letta MemGPT 思路，来源：docs.letta.com/concepts/letta）：
   - Core Memory（in-context，永远在 prompt 里，容量小）
   - Archival Memory（out-of-context，向量库，agent 主动 search/insert）
   - Recall Memory（对话历史检索）
3. Agent 主动"self-edit"记忆：通过工具调用 core_memory_append / archival_memory_insert。
4. 检索走图遍历 + 向量召回 + reranker（本 demo 用简化的 RRF 融合）。

参考：
- Letta 官方文档：https://docs.letta.com/guides/legacy/memgpt_agents_legacy
- Zep + Graphiti 论文：blog.getzep.com/content/files/2025/01/ZEP__USING_KNOWLEDGE_GRAPHS_TO_POWER_LLM_AGENT_MEMORY_2025011700.pdf

依赖：仅 stdlib。生产用 Neo4j / FalkorDB / Kuzu 存图，用 pgvector / Qdrant 存向量。
"""
from __future__ import annotations

import hashlib
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

DIM = 128


def fake_embed(text: str) -> List[float]:
    vec = [0.0] * DIM
    for tok in text.lower().split():
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        for i in range(DIM):
            vec[i] += 1.0 if (h >> i) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# ---------- 图元素 ----------
@dataclass
class Node:
    id: str
    label: str          # Person / Product / Place / ...
    props: Dict[str, str] = field(default_factory=dict)


@dataclass
class Edge:
    src: str            # node id
    dst: str
    rel: str            # prefers / works_in / located_at
    ts: float
    valid_to: Optional[float] = None
    vec: List[float] = field(default_factory=list)

    def render(self) -> str:
        return f"({self.src}) -[{self.rel}]-> ({self.dst})"


@dataclass
class Episode:
    """一次 raw 事件：对话/工具调用/文档。指向本次涉及的节点。"""
    id: str
    text: str
    ts: float
    entity_ids: List[str]
    vec: List[float] = field(default_factory=list)


# ---------- 记忆图 ----------
class MemoryGraph:
    """Graphiti / Letta-archival 简化版：Nodes + Edges + Episodes 三层。"""

    def __init__(self) -> None:
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self.episodes: List[Episode] = []
        # 邻接表加速图遍历
        self._adj: Dict[str, List[Edge]] = defaultdict(list)

    def upsert_node(self, node_id: str, label: str, **props: str) -> Node:
        if node_id in self.nodes:
            self.nodes[node_id].props.update(props)
        else:
            self.nodes[node_id] = Node(id=node_id, label=label, props=dict(props))
        return self.nodes[node_id]

    def add_edge(self, src: str, dst: str, rel: str) -> Edge:
        now = time.time()
        # bi-temporal：同 src/rel 的旧边失效
        for e in self.edges:
            if e.src == src and e.rel == rel and e.dst != dst and e.valid_to is None:
                e.valid_to = now
        edge = Edge(src=src, dst=dst, rel=rel, ts=now,
                    vec=fake_embed(f"{src} {rel} {dst}"))
        self.edges.append(edge)
        self._adj[src].append(edge)
        return edge

    def add_episode(self, text: str, entity_ids: List[str]) -> Episode:
        ep = Episode(id=f"ep{len(self.episodes)}", text=text, ts=time.time(),
                     entity_ids=list(entity_ids), vec=fake_embed(text))
        self.episodes.append(ep)
        return ep

    # ---------- 三路召回 ----------
    def vector_recall_edges(self, query: str, top_k: int = 5) -> List[Tuple[float, Edge]]:
        qv = fake_embed(query)
        pool = [(cosine(qv, e.vec), e) for e in self.edges if e.valid_to is None]
        pool.sort(key=lambda x: x[0], reverse=True)
        return pool[:top_k]

    def graph_walk(self, start_ids: List[str], hops: int = 2, only_current: bool = True) -> List[Edge]:
        """从一批种子节点出发，BFS 出 hops 跳内的所有边。"""
        visited: Set[str] = set(start_ids)
        frontier = deque([(nid, 0) for nid in start_ids])
        collected: List[Edge] = []
        while frontier:
            nid, depth = frontier.popleft()
            if depth >= hops:
                continue
            for e in self._adj.get(nid, []):
                if only_current and e.valid_to is not None:
                    continue
                collected.append(e)
                if e.dst not in visited:
                    visited.add(e.dst)
                    frontier.append((e.dst, depth + 1))
        return collected

    def episode_recall(self, query: str, top_k: int = 3) -> List[Tuple[float, Episode]]:
        qv = fake_embed(query)
        pool = [(cosine(qv, ep.vec), ep) for ep in self.episodes]
        pool.sort(key=lambda x: x[0], reverse=True)
        return pool[:top_k]

    # ---------- 融合检索（简化 RRF） ----------
    def hybrid_search(self, query: str, seed_entities: Optional[List[str]] = None) -> Dict[str, List[str]]:
        """三路召回 + RRF：向量 edges + 图遍历 + episodes。"""
        vec_edges = self.vector_recall_edges(query, top_k=5)
        walk_edges = self.graph_walk(seed_entities or [], hops=2) if seed_entities else []
        eps = self.episode_recall(query, top_k=3)

        # RRF 融合
        RRF_K = 60
        scores: Dict[str, float] = defaultdict(float)
        rendered: Dict[str, str] = {}
        for rank, (_, e) in enumerate(vec_edges):
            key = e.render()
            scores[key] += 1.0 / (RRF_K + rank + 1)
            rendered[key] = f"[vec]  {key}"
        for rank, e in enumerate(walk_edges):
            key = e.render()
            scores[key] += 1.0 / (RRF_K + rank + 1)
            rendered[key] = rendered.get(key, f"[graph]{key}")
        for rank, (_, ep) in enumerate(eps):
            key = f"episode:{ep.id}"
            scores[key] += 1.0 / (RRF_K + rank + 1)
            rendered[key] = f"[epi] {ep.text}"

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return {
            "final_context": [rendered[k] for k, _ in ranked],
            "seed_entities": seed_entities or [],
        }


# ---------- 分层上下文（MemGPT 思路） ----------
@dataclass
class TieredContext:
    """Letta / MemGPT 风格的分层记忆容器。"""
    core_memory: Dict[str, str]        # in-context，agent 可 append/replace
    archival: MemoryGraph              # out-of-context，agent 通过工具 search/insert
    core_char_limit: int = 500

    def core_render(self) -> str:
        s = "\n".join(f"[{k}] {v}" for k, v in self.core_memory.items())
        # 超限就淘汰最短的一条（真实场景是 LLM 摘要压缩）
        while len(s) > self.core_char_limit and self.core_memory:
            drop = min(self.core_memory, key=lambda k: len(self.core_memory[k]))
            self.core_memory.pop(drop)
            s = "\n".join(f"[{k}] {v}" for k, v in self.core_memory.items())
        return s

    def core_append(self, section: str, value: str) -> None:
        """模拟 core_memory_append 工具。"""
        old = self.core_memory.get(section, "")
        self.core_memory[section] = (old + "\n" + value).strip()

    def core_replace(self, section: str, value: str) -> None:
        self.core_memory[section] = value


# ---------- Demo ----------
def demo() -> None:
    g = MemoryGraph()

    # 建实体
    g.upsert_node("user", "Person", name="Alex")
    g.upsert_node("python", "Language")
    g.upsert_node("go", "Language")
    g.upsert_node("beijing", "City")
    g.upsert_node("shanghai", "City")
    g.upsert_node("latte", "Drink")

    # 建 T0 关系
    g.add_edge("user", "python", "uses_language")
    g.add_edge("user", "beijing", "works_in")
    g.add_edge("user", "latte", "prefers_drink")
    g.add_episode("我是后端工程师，主用 Python，在北京。", ["user", "python", "beijing"])

    time.sleep(0.01)
    # T1 用户改口
    g.add_edge("user", "go", "uses_language")
    g.add_edge("user", "shanghai", "works_in")
    g.add_episode("换工作了，主用 Go，搬去了上海。", ["user", "go", "shanghai"])

    print("=" * 60)
    print("Gen3 演示 1：hybrid 检索（vector + graph walk + episode）")
    print("=" * 60)
    ctx = g.hybrid_search("用户现在住哪、用什么语言", seed_entities=["user"])
    for line in ctx["final_context"][:8]:
        print("  " + line)
    print()

    print("=" * 60)
    print("Gen3 演示 2：时间旅行 —— 查看'工作城市'的历史演化")
    print("=" * 60)
    for e in g.edges:
        if e.src == "user" and e.rel == "works_in":
            state = "✓当前" if e.valid_to is None else "✗历史"
            print(f"  [{state}] user works_in {e.dst}  (ts={e.ts:.2f})")
    print()

    print("=" * 60)
    print("Gen3 演示 3：MemGPT 风格分层上下文")
    print("=" * 60)
    tiered = TieredContext(core_memory={}, archival=g)
    # agent 主动把关键 fact 提升到 core
    tiered.core_append("persona", "我是一名爱喝拿铁的资深后端工程师")
    tiered.core_replace("current_project", "正在给 Agent 加长期记忆")
    print("--- Core Memory (in-context) ---")
    print(tiered.core_render())
    print("--- Archival (out-of-context, on-demand) ---")
    print(f"共 {len(g.nodes)} nodes / {len(g.edges)} edges / {len(g.episodes)} episodes")


if __name__ == "__main__":
    demo()
