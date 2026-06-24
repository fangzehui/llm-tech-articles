"""TreeQuest / AB-MCTS 最小可读实现（教学版）。

完全用标准库写完，不依赖任何外部包：
- 节点：树节点，记录 state（候选答案）、score（外部反馈分）、parent、children；
- 动作：每一步在树上选一个父节点，调用一个 LLM-style ``generate_fn`` 生成新候选；
- 三件事：
    1. ``Go Deeper``：在已有节点上继续 refine（用同一个 LLM 改进当前答案）；
    2. ``Go Wider``：从父节点重新生成新候选（同一个 LLM 但不同种子）；
    3. ``Multi-LLM``：换一个 LLM 重新生成（多家模型接力试错）。
- 选择：Thompson Sampling 在多个动作 / 多个 LLM 之间按"胜率后验"采样，
  既不是纯贪心也不是纯均匀；
- 终止：跑满 ``budget`` 次 LLM 调用之后返回最高 score 的节点。

⚠️ 这是一份**最小可读教学实现**，刻意把以下东西做了简化：
- Beta 分布的更新直接用"胜负计数"（α/β 加 1），而不是 PyMC 混合贝叶斯；
- "score" 假设是 [0, 1] 标量，真实场景里你要自己写 ``evaluate(state)`` 把模型
  输出翻译成单标量分数（test pass rate / judge score / etc）；
- 没有并发批量调用——真生产里要按 ``ask_batch`` / ``tell`` 两阶段拆。

但这 ~250 行代码已经能跑出 ARC-AGI 风格的"o4-mini 错→Gemini/DeepSeek 接力改对"
模式，足够用来理解原理 + 调试自家任务。

参考资料：
- Sakana AB-MCTS 官博：https://sakana.ai/ab-mcts/
- 论文 *Wider or Deeper?* arXiv 2503.04412v4：https://arxiv.org/abs/2503.04412
- 官方实现 TreeQuest（Apache 2.0）：https://github.com/SakanaAI/treequest
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# ============================================================
# 1) 数据结构：节点 + 树
# ============================================================


@dataclass
class Node:
    """搜索树节点。

    state 可以是任意 Python 对象（字符串答案、代码、PIL.Image、序列化的工作流…），
    我们只要求 ``score`` 是 [0, 1] 的浮点数，且越高越好。
    """

    state: Any
    score: float
    llm: str                            # 当前节点是由哪个 LLM 生成的
    parent: Optional["Node"] = None
    children: List["Node"] = field(default_factory=list)
    # Thompson Sampling 用：在这个节点上"再走一步"成功 / 失败的次数
    wins: int = 1                       # 先验 α=1（Beta(1,1) = Uniform）
    losses: int = 1                     # 先验 β=1

    def depth(self) -> int:
        d, cur = 0, self
        while cur.parent is not None:
            d += 1
            cur = cur.parent
        return d

    def update(self, success: bool) -> None:
        """子树里一次新生成的成败回传到本节点。"""
        if success:
            self.wins += 1
        else:
            self.losses += 1


def _all_nodes(root: Node) -> List[Node]:
    out, stack = [], [root]
    while stack:
        n = stack.pop()
        out.append(n)
        stack.extend(n.children)
    return out


# ============================================================
# 2) Thompson Sampling：在多个候选之间按 Beta 后验采样
# ============================================================


def thompson_pick(candidates: List[Node], rng: random.Random) -> Node:
    """对每个候选从 ``Beta(wins, losses)`` 采一个值，取最大者。

    Beta(α, β) 的均值是 α/(α+β)；用 ``random.betavariate`` 直接采样。
    采样的好处：早期均匀探索（先验 α=β=1 时是 Uniform），后期收敛到经验最优。
    """
    best, best_v = None, -1.0
    for c in candidates:
        v = rng.betavariate(c.wins, c.losses)
        if v > best_v:
            best, best_v = c, v
    assert best is not None
    return best


def thompson_pick_llm(
    llm_stats: Dict[str, Tuple[int, int]], rng: random.Random
) -> str:
    """跨 LLM 的 Thompson Sampling——决定本步用哪家模型生成。"""
    best, best_v = None, -1.0
    for llm, (w, l) in llm_stats.items():
        v = rng.betavariate(w, l)
        if v > best_v:
            best, best_v = llm, v
    assert best is not None
    return best


# ============================================================
# 3) 三动作 + 单步 step()
# ============================================================


GenerateFn = Callable[[Optional[Any]], Tuple[Any, float]]
# 签名：(parent_state | None) -> (new_state, score in [0,1])


@dataclass
class ABMCTSConfig:
    """搜索算法的超参——故意只保留 3 个，避免调参噩梦。"""

    budget: int = 50                    # 总共允许的 LLM 调用次数
    success_threshold: float = 0.8      # score ≥ 阈值 → 标 win，反之 loss
    seed: Optional[int] = None


@dataclass
class ABMCTS:
    """AB-MCTS-A 的简化教学实现（A 表示 "aggregate"，即用节点统计聚合后验）。"""

    config: ABMCTSConfig = field(default_factory=ABMCTSConfig)

    def init_tree(self) -> Node:
        # 用一个虚拟 root，state 为 None，永远不会被当作答案返回
        return Node(state=None, score=0.0, llm="__root__")

    def step(
        self,
        tree: Node,
        generate_fns: Dict[str, GenerateFn],
        rng: Optional[random.Random] = None,
    ) -> Node:
        """走一步：
        1) 跨 LLM 用 Thompson 选一家；
        2) 在树里所有"已存在节点 ∪ 虚拟扩展点"中 Thompson 选一个父节点；
        3) 调对应 LLM 生成新候选并挂到父节点下；
        4) 把成败回传给祖先与该 LLM 的全局统计。
        """
        if rng is None:
            rng = random.Random(self.config.seed)

        # —— 跨 LLM 选谁来生成 ——
        # 把每个 LLM 的历史成败聚合成 (wins, losses) 给 Thompson
        if not hasattr(tree, "_llm_stats"):
            tree._llm_stats = {n: (1, 1) for n in generate_fns}   # 先验 Uniform
        # 新出现的 LLM（动态注册）也补一份先验
        for n in generate_fns:
            tree._llm_stats.setdefault(n, (1, 1))
        chosen_llm = thompson_pick_llm(tree._llm_stats, rng)
        gen_fn = generate_fns[chosen_llm]

        # —— 选父节点 ——
        # 候选 = 整棵树里所有节点（含 root）；root 代表"go wider"——从 0 开始生成新候选
        all_n = _all_nodes(tree)
        parent = thompson_pick(all_n, rng)

        # —— 生成新候选 ——
        new_state, new_score = gen_fn(parent.state if parent is not tree else None)
        # 把 score 兜底到 [0,1]，避免外部评分器写飞了
        new_score = max(0.0, min(1.0, float(new_score)))

        new_node = Node(
            state=new_state, score=new_score, llm=chosen_llm, parent=parent
        )
        parent.children.append(new_node)

        # —— 回传成败 ——
        success = new_score >= self.config.success_threshold
        # 1) 更新祖先节点的 Beta（典型的 MCTS backup）
        cur = new_node.parent
        while cur is not None:
            cur.update(success)
            cur = cur.parent
        # 2) 更新该 LLM 的全局胜率
        w, l = tree._llm_stats[chosen_llm]
        tree._llm_stats[chosen_llm] = (w + int(success), l + int(not success))

        return tree

    def run(
        self, generate_fns: Dict[str, GenerateFn]
    ) -> Tuple[Node, List[Dict[str, Any]]]:
        """跑满 budget 步，返回 (最佳节点, 轨迹日志)。"""
        rng = random.Random(self.config.seed)
        tree = self.init_tree()
        trace: List[Dict[str, Any]] = []
        for i in range(self.config.budget):
            tree = self.step(tree, generate_fns, rng=rng)
            best_so_far = self.top_k(tree, k=1)[0]
            trace.append(
                {
                    "step": i + 1,
                    "best_score": best_so_far.score,
                    "best_llm": best_so_far.llm,
                    "n_nodes": len(_all_nodes(tree)) - 1,   # 不含 root
                }
            )
        return self.top_k(tree, k=1)[0], trace

    def top_k(self, tree: Node, k: int = 1) -> List[Node]:
        """返回 score 最高的 k 个节点（不含 root）。"""
        nodes = [n for n in _all_nodes(tree) if n is not tree]
        nodes.sort(key=lambda n: n.score, reverse=True)
        return nodes[:k] if nodes else [tree]


# ============================================================
# 4) 工具函数：方便 demo 调用
# ============================================================


def render_text_tree(root: Node, max_lines: int = 20) -> str:
    """把搜索树渲染成人眼可读的文本树，方便 demo / 测试 / 排查。

    格式::

        [root]
          ├─ [o4-mini score=0.62]
          │    └─ [gemini score=0.91]
          └─ [deepseek score=0.74]
    """
    lines: List[str] = []

    def _walk(n: Node, prefix: str = "", is_last: bool = True) -> None:
        if len(lines) >= max_lines:
            return
        if n is root:
            lines.append("[root]")
        else:
            connector = "└─ " if is_last else "├─ "
            tag = f"[{n.llm} score={n.score:.2f} w={n.wins} l={n.losses}]"
            lines.append(prefix + connector + tag)
        new_prefix = prefix + ("   " if is_last else "│  ")
        for i, c in enumerate(n.children):
            _walk(c, new_prefix, i == len(n.children) - 1)

    _walk(root)
    return "\n".join(lines)


# ============================================================
# 5) 自带 demo：跑一个不依赖外网的"伪数学题"任务
# ============================================================


def _build_demo_generators(target: int = 42) -> Dict[str, GenerateFn]:
    """构造 3 个"假 LLM"，模拟真实的多模型行为差异：

    - ``o4_mini_like``：擅长起头，但容易卡在某个区间；
    - ``gemini_like``：refine 能力强，在父节点 score 高时更可能进一步提升；
    - ``deepseek_like``：偶尔 one-shot 中靶但波动大。

    每个 generator 返回 ``(候选答案, 评分)``——评分 = 1 - |answer - target|/100。
    """

    rng = random.Random(20260620)

    def _score(answer: int) -> float:
        return max(0.0, 1.0 - abs(answer - target) / 100.0)

    def o4_mini_like(parent_state: Optional[int]) -> Tuple[int, float]:
        # 从 [target-30, target+30] 起步，但有 20% 概率跑偏
        if parent_state is None:
            base = target + rng.randint(-30, 30)
        else:
            base = parent_state + rng.randint(-15, 15)
        if rng.random() < 0.2:
            base += rng.randint(-50, 50)
        return base, _score(base)

    def gemini_like(parent_state: Optional[int]) -> Tuple[int, float]:
        # refine 时偏移更小（擅长改进），但 fresh start 较弱
        if parent_state is None:
            base = target + rng.randint(-40, 40)
        else:
            # 父节点 score 越高，偏移越小
            spread = max(2, int(20 * (1 - _score(parent_state))))
            base = parent_state + rng.randint(-spread, spread)
        return base, _score(base)

    def deepseek_like(parent_state: Optional[int]) -> Tuple[int, float]:
        # 30% 概率 one-shot 命中，70% 概率乱跑
        if rng.random() < 0.3:
            base = target + rng.randint(-3, 3)
        else:
            base = target + rng.randint(-60, 60)
        return base, _score(base)

    return {
        "o4_mini_like": o4_mini_like,
        "gemini_like": gemini_like,
        "deepseek_like": deepseek_like,
    }


def main() -> None:                                # pragma: no cover
    print(">>> TreeQuest minimal demo：3 个伪 LLM 协作求 target=42")
    fns = _build_demo_generators(target=42)
    algo = ABMCTS(ABMCTSConfig(budget=30, success_threshold=0.9, seed=42))
    best, trace = algo.run(fns)
    print(f"\n[best] state={best.state} score={best.score:.3f} llm={best.llm}")
    print(f"[best] depth={best.depth()} 路径=", end="")
    cur, path = best, []
    while cur.parent is not None:
        path.append(cur.llm)
        cur = cur.parent
    print(" → ".join(reversed(path)))
    print("\n[trace 前 10 步]")
    for row in trace[:10]:
        print(
            f"  step={row['step']:>2}  best={row['best_score']:.3f}"
            f"  by={row['best_llm']:<14}  n_nodes={row['n_nodes']}"
        )
    print("\n[搜索树前 20 行]")
    print(render_text_tree(_root_of(best), max_lines=20))


def _root_of(node: Node) -> Node:
    """从任意节点回溯到 root（root.parent is None）。"""
    cur = node
    while cur.parent is not None:
        cur = cur.parent
    return cur


if __name__ == "__main__":                          # pragma: no cover
    main()
