"""
第二代记忆：结构化记忆（模拟 mem0 / Zep-style Fact Memory）

核心思想（对齐 mem0 论文 arxiv 2504.19413 与 Zep 论文的 Fact 层）：
1. 不再存原文，而是用 LLM 从对话里抽取"事实三元组 / 结构化条目"。
2. 每条 fact 带 subject / predicate / object / ts，可查询、可更新、可失效。
3. 冲突消解：新事实进来时，找到 subject+predicate 相同的老事实，
   老的置为 invalid，新的置为 valid（bi-temporal 思想）。
4. 检索时同时用向量相似度 + 结构化过滤（如 subject=alex）。

本脚本用规则式抽取器（keyword-based）近似真实 LLM 抽取，
纯 stdlib，可独立跑通；生产替换成 gpt-4o-mini / claude-haiku 做 fact extraction。
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

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


class FactState(str, Enum):
    VALID = "valid"
    INVALID = "invalid"  # 被新事实替代


@dataclass
class Fact:
    """结构化事实条目：subject/predicate/object 三元组 + 时间窗口。
    对应 Zep 的 semantic edge / mem0 的 memory item。"""
    subject: str
    predicate: str
    object: str
    valid_from: float
    valid_to: Optional[float] = None      # 被替代时刻
    state: FactState = FactState.VALID
    source_text: str = ""
    vec: List[float] = field(default_factory=list)

    def key(self) -> str:
        return f"{self.subject}::{self.predicate}"

    def render(self) -> str:
        return f"{self.subject} - {self.predicate} - {self.object}"


# ---------- 事实抽取器 ----------
# 生产：换成 LLM function call, 返回 [{"subject","predicate","object"}] 列表。
EXTRACT_RULES: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"我(最喜欢|喜欢)喝(.+?)[。$]"), "user", "prefers_drink"),
    (re.compile(r"我(现在|目前)?(主要)?用(.+?)[语言。$]"), "user", "uses_language"),
    (re.compile(r"我最喜欢的语言是(.+?)[。$]"), "user", "uses_language"),
    (re.compile(r"我在(.+?)工作[。$]"), "user", "works_in"),
    (re.compile(r"我搬去了(.+?)[。$]"), "user", "lives_in"),
    (re.compile(r"我(是|叫)(.+?)工程师[。$]"), "user", "role"),
]


def extract_facts(text: str, now: float) -> List[Fact]:
    """从一段文本里抽 fact。真实场景交给 LLM，此处用正则近似。"""
    facts: List[Fact] = []
    for pat, subj, pred in EXTRACT_RULES:
        for m in pat.finditer(text):
            obj = m.group(m.lastindex).strip()
            f = Fact(
                subject=subj, predicate=pred, object=obj,
                valid_from=now, source_text=text,
                vec=fake_embed(f"{subj} {pred} {obj}"),
            )
            facts.append(f)
    return facts


# ---------- 结构化记忆 ----------
class StructuredMemory:
    """mem0 / Zep 风格：事实抽取 → 冲突消解 → 结构化 + 向量双索引。"""

    def __init__(self) -> None:
        self.facts: List[Fact] = []
        # subject+predicate → 当前 valid 的 fact（O(1) 冲突查找）
        self.current: Dict[str, Fact] = {}

    def add_from_conversation(self, text: str) -> List[Fact]:
        now = time.time()
        new_facts = extract_facts(text, now)
        merged: List[Fact] = []
        for nf in new_facts:
            k = nf.key()
            old = self.current.get(k)
            if old is not None and old.object != nf.object:
                # 冲突消解：老事实失效
                old.state = FactState.INVALID
                old.valid_to = now
            self.facts.append(nf)
            self.current[k] = nf
            merged.append(nf)
        return merged

    def search(
        self,
        query: str,
        top_k: int = 3,
        only_valid: bool = True,
        subject: Optional[str] = None,
    ) -> List[Tuple[float, Fact]]:
        qv = fake_embed(query)
        pool = [f for f in self.facts
                if (not only_valid or f.state == FactState.VALID)
                and (subject is None or f.subject == subject)]
        scored = [(cosine(qv, f.vec), f) for f in pool]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]

    def build_context(self, query: str, top_k: int = 5) -> str:
        hits = self.search(query, top_k=top_k)
        lines = []
        for _, f in hits:
            tag = "✓当前" if f.state == FactState.VALID else "✗过期"
            lines.append(f"[{tag}] {f.render()}")
        return "\n".join(lines) if lines else "(无相关记忆)"


# ---------- Demo ----------
def demo() -> None:
    mem = StructuredMemory()

    print("=" * 60)
    print("Gen2 演示：抽取 + 冲突消解")
    print("=" * 60)
    mem.add_from_conversation("我是一名后端工程师。我最喜欢的语言是Python。我在北京工作。")
    print("第一轮抽取的 facts：")
    for f in mem.facts:
        print(f"  {f.render()}  [{f.state.value}]")
    print()

    time.sleep(0.01)
    mem.add_from_conversation("我最近换工作了。我现在主要用Go。我搬去了上海。")
    print("第二轮之后（老事实应被自动置为 invalid）：")
    for f in mem.facts:
        tag = "✓" if f.state == FactState.VALID else "✗过期"
        print(f"  [{tag}] {f.render()}")
    print()

    print("=" * 60)
    print("检索：'用户目前用什么语言' —— 只应召回 valid 的 Go")
    print("=" * 60)
    print(mem.build_context("目前用什么语言", top_k=3))
    print()

    print("=" * 60)
    print("检索：查完整历史（including invalid，用于时间旅行式问答）")
    print("=" * 60)
    for score, f in mem.search("用什么语言", top_k=5, only_valid=False):
        tag = "✓当前" if f.state == FactState.VALID else "✗过期"
        print(f"  score={score:.3f}  [{tag}] {f.render()}")


if __name__ == "__main__":
    demo()
