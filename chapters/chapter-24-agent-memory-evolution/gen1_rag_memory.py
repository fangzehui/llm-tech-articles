"""
第一代记忆：把 RAG 当记忆用（Vector-only）

核心思想：把用户历史消息切成 chunk，用嵌入模型编码存进向量库，
每次对话前用当前 query 做相似度检索，把 top-k 拼进 prompt。

局限：
1. 没有"事实抽取"，存的是原文，冗余高、召回噪声大。
2. 没有时序感知：老事实和新事实一起返回，冲突无法自动消解。
3. 没有"更新"语义：只能追加，不能改写、不能失效。
4. 长会话下 chunk 数量爆炸，检索质量退化。

本脚本用最小依赖（只用 numpy + hash-based fake embedding）演示这类记忆的行为。
生产环境请替换为 sentence-transformers / OpenAI embeddings + FAISS/Qdrant。
"""
from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import List, Tuple


# ---------- 极简向量工具（无外部依赖） ----------
DIM = 128


def fake_embed(text: str) -> List[float]:
    """把文本 hash 到 DIM 维向量。仅演示用，不代表真实语义相似度。
    真实场景用 OpenAI text-embedding-3-small / bge-large-zh 等。"""
    vec = [0.0] * DIM
    tokens = text.lower().split()
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        for i in range(DIM):
            bit = (h >> i) & 1
            vec[i] += 1.0 if bit else -1.0
    # L2 归一化
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# ---------- Gen1 记忆存储 ----------
@dataclass
class Chunk:
    text: str
    ts: float
    vec: List[float] = field(default_factory=list)


class RagMemory:
    """纯向量 RAG 记忆：把对话原文分块存起来，用相似度检索。"""

    def __init__(self) -> None:
        self.chunks: List[Chunk] = []

    def add(self, text: str) -> None:
        """把一条对话/文档追加进记忆库。这里做的最"傻"——
        原文分句后每句一个 chunk，不做去重、不做事实抽取。"""
        for sent in [s.strip() for s in text.split("。") if s.strip()]:
            self.chunks.append(Chunk(text=sent, ts=time.time(), vec=fake_embed(sent)))

    def search(self, query: str, top_k: int = 3) -> List[Tuple[float, Chunk]]:
        qv = fake_embed(query)
        scored = [(cosine(qv, c.vec), c) for c in self.chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]

    def build_prompt(self, query: str, top_k: int = 3) -> str:
        """典型 Gen1 用法：检索 → 拼 prompt → 交给 LLM。"""
        hits = self.search(query, top_k=top_k)
        recalled = "\n".join(f"- {c.text}" for _, c in hits)
        return (
            "以下是可能相关的历史片段：\n"
            f"{recalled}\n\n"
            f"用户当前问题：{query}\n"
            "请基于上面的历史片段回答（无关请忽略）。"
        )


# ---------- Demo：暴露 Gen1 的三个典型问题 ----------
def demo() -> None:
    mem = RagMemory()

    # 用户历史：先说"我用 Python"，几天后改成"我现在用 Go"
    mem.add("我是一名后端工程师。我最喜欢的语言是 Python。我在北京工作。")
    time.sleep(0.01)
    mem.add("我最近换工作了。我现在主要用 Go。我搬去了上海。")

    print("=" * 60)
    print("Gen1 演示 1：新问答")
    print("=" * 60)
    print(mem.build_prompt("我目前用什么语言？"))
    print()
    print("=> Gen1 的痛点：老事实（Python）和新事实（Go）会一起被召回，")
    print("   没有 valid_from / valid_to 概念，LLM 只能猜。")
    print()

    print("=" * 60)
    print("Gen1 演示 2：冗余爆炸")
    print("=" * 60)
    # 用户不断重复一件事，chunk 数量会线性膨胀
    for _ in range(5):
        mem.add("我特别喜欢喝拿铁。")
    print(f"记忆库当前有 {len(mem.chunks)} 个 chunk（含重复）。")
    hits = mem.search("我喜欢喝什么？", top_k=5)
    for score, c in hits:
        print(f"  score={score:.3f}  {c.text}")
    print("=> Gen1 没有去重合并，同一事实占据多个坑位，浪费上下文。")
    print()

    print("=" * 60)
    print("Gen1 演示 3：无法'忘记'")
    print("=" * 60)
    print("Gen1 只有 add / search，没有原生 update / invalidate 语义。")
    print("要让 LLM 相信'我改口了'，只能靠更长的 prompt 或人工清库。")


if __name__ == "__main__":
    demo()
