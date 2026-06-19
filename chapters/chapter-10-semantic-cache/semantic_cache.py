"""第 10 篇配套 demo：语义缓存（embedding + 余弦相似度 + LRU）.

特征：
- 简化的 hashing-based embedding，避免依赖外部模型，保证 demo 完全本地可跑
- 余弦相似度 + 阈值判定命中
- LRU 容量控制 + 可选 TTL
- 对外暴露与 LLM 客户端一致的 chat-like 接口

可独立运行：
    python semantic_cache.py
"""

from __future__ import annotations

import hashlib
import math
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import MockLLMClient  # noqa: E402

EMBED_DIM = 256


def hashing_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """非常轻量的 hashing-trick embedding，不依赖任何模型.

    生产请替换为 sentence-transformers / BGE / OpenAI text-embedding-3。
    这里只是为了让 demo 可以脱网跑，且能演示余弦相似度阈值的工程意义。
    """
    vec = [0.0] * dim
    tokens = text.lower().split()
    if not tokens:
        return vec
    for tok in tokens:
        h = hashlib.md5(tok.encode("utf-8")).digest()
        for i in range(0, min(len(h), 8)):
            idx = (h[i] * 31 + i) % dim
            sign = 1.0 if (h[i] & 1) else -1.0
            vec[idx] += sign
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """已归一化向量的余弦相似度（=点积）."""
    return sum(x * y for x, y in zip(a, b))


@dataclass
class CacheEntry:
    query: str
    embedding: list[float]
    answer: str
    created_at: float


class SemanticCache:
    """带 LRU 与 TTL 的语义缓存.

    Args:
        capacity: 最多保存多少条
        threshold: 余弦相似度阈值，超过即视为命中
        ttl_seconds: 单条 entry 的最大存活时长，0 表示不过期
    """

    def __init__(
        self,
        capacity: int = 1000,
        threshold: float = 0.85,
        ttl_seconds: float = 0,
    ) -> None:
        self.capacity = capacity
        self.threshold = threshold
        self.ttl_seconds = ttl_seconds
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self.hit_count = 0
        self.miss_count = 0

    def _expired(self, entry: CacheEntry) -> bool:
        if self.ttl_seconds <= 0:
            return False
        return (time.time() - entry.created_at) > self.ttl_seconds

    def lookup(self, query: str) -> tuple[str | None, float, str | None]:
        """在缓存里找最相似的条目.

        Returns:
            (命中答案 or None, 最大相似度, 命中 query 原文 or None)
        """
        emb = hashing_embed(query)
        best: tuple[float, CacheEntry | None] = (-1.0, None)
        # 顺便做一次惰性过期清理
        expired_keys = [k for k, v in self._store.items() if self._expired(v)]
        for k in expired_keys:
            self._store.pop(k, None)

        for entry in self._store.values():
            sim = cosine(emb, entry.embedding)
            if sim > best[0]:
                best = (sim, entry)
        if best[1] is not None and best[0] >= self.threshold:
            self.hit_count += 1
            # 命中后把它挪到末尾（LRU 续期）
            self._store.move_to_end(best[1].query)
            return best[1].answer, best[0], best[1].query
        self.miss_count += 1
        return None, best[0] if best[1] else 0.0, best[1].query if best[1] else None

    def put(self, query: str, answer: str) -> None:
        emb = hashing_embed(query)
        self._store[query] = CacheEntry(query, emb, answer, time.time())
        self._store.move_to_end(query)
        while len(self._store) > self.capacity:
            self._store.popitem(last=False)

    @property
    def hit_rate(self) -> float:
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total else 0.0


class CachedLLM:
    """一个把 SemanticCache 包到 LLM 客户端外面的 wrapper."""

    def __init__(self, cache: SemanticCache, client: MockLLMClient) -> None:
        self.cache = cache
        self.client = client

    def chat(self, query: str) -> dict:
        answer, sim, hit_query = self.cache.lookup(query)
        if answer is not None:
            return {"from_cache": True, "similarity": sim, "answer": answer, "matched": hit_query}
        resp = self.client.chat([{"role": "user", "content": query}])
        self.cache.put(query, resp.content)
        return {"from_cache": False, "similarity": sim, "answer": resp.content, "matched": None}


def main() -> None:  # pragma: no cover
    cache = SemanticCache(capacity=200, threshold=0.6, ttl_seconds=3600)
    client = MockLLMClient("openai", "gpt-mock", base_latency_ms=50, seed=42)
    cached = CachedLLM(cache, client)

    queries = [
        "今天的天气怎么样",
        "今天的天气如何",  # 应该接近，可能命中
        "明天会下雨吗",
        "请介绍一下 Python 装饰器",
        "Python 装饰器是什么",  # 高度相似
        "Python 装饰器是什么",  # 完全相同，铁命中
    ]
    for q in queries:
        out = cached.chat(q)
        marker = "HIT " if out["from_cache"] else "MISS"
        print(f"  [{marker}] sim={out['similarity']:.2f} | {q[:30]} -> {out['answer'][:40]}")
    print(f"\n  hit_rate = {cache.hit_rate:.2%}")


if __name__ == "__main__":  # pragma: no cover
    main()
