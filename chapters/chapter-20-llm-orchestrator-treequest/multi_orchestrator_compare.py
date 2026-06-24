"""把同一个任务用 4 种编排风格各跑一遍——OpenRouter 路由 / Vercel AI SDK 流式 /
LangGraph 状态图 / TreeQuest 树搜索——对比 token 消耗、调用次数、最终质量。

⚠️ 注意：这里**不真的去打 OpenAI / Anthropic / Gemini** 的网，
所有"LLM 调用"都用本地的 fake worker 模拟 token 数与正确率。
真实工程里把 ``FakeWorker.invoke()`` 换成 ``openai.ChatCompletion.create``
或 ``langchain_openai.ChatOpenAI(...).invoke`` 就完事。

四种风格的核心差异：

- **OpenRouter 风格**：单请求 → 自动 / 显式选 1 个 LLM，**只调 1 次**；
  适合"价格 / 配额 / 区域路由"为目的的网关层。
- **Vercel AI SDK 风格**：``streamText`` + ``prepareStep`` 同步流式给前端，
  允许 step 之间切模型，**典型 1-3 次**调用，关注用户感知延迟。
- **LangGraph 风格**：把任务拆成 planner → executor → verifier 三个节点
  的状态图，状态可 checkpoint、可 HITL，**3-5 次**调用，关注鲁棒性。
- **TreeQuest / AB-MCTS 风格**：让多个 LLM 在搜索树上接力试错，
  **N 次**调用（N = budget），关注 test-time compute 换质量上限。
"""

from __future__ import annotations

import random
import statistics
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

# 复用最小 TreeQuest 实现（同目录下的相对 import）
from treequest_minimal import ABMCTS, ABMCTSConfig, GenerateFn


# ============================================================
# 1) Fake LLM worker：模拟"调用一次 LLM"的 token 消耗与正确率
# ============================================================


@dataclass
class FakeWorker:
    """模拟一个 LLM 的属性。

    - ``name``：模型名（标签用）；
    - ``one_shot_accuracy``：单次直接给正确答案的概率；
    - ``refine_bonus``：若 parent 已有部分对的答案，refine 后正确率提升；
    - ``token_per_call``：每次调用大致消耗的 token 数（input+output）；
    - ``usd_per_mtok``：每百万 token 的美元价（用于成本估算）。
    """

    name: str
    one_shot_accuracy: float
    refine_bonus: float
    token_per_call: int
    usd_per_mtok: float

    # 运行时累计
    calls: int = 0
    tokens_used: int = 0

    def invoke(
        self, parent_state: Optional[Tuple[str, float]], rng: random.Random
    ) -> Tuple[Tuple[str, float], float]:
        """返回 ``((答案文本, 答案 score), score)``。
        score 同时塞进 state 里方便 refine 时 parent_state 读到。
        """
        self.calls += 1
        self.tokens_used += self.token_per_call

        if parent_state is None:
            base = self.one_shot_accuracy
        else:
            # parent 已有 score → refine 之后 score 提升 refine_bonus（受上限钳制）
            _, parent_score = parent_state
            base = min(0.99, parent_score + self.refine_bonus)
        # 加点噪声让多次采样不完全一致
        score = max(0.0, min(1.0, base + rng.uniform(-0.1, 0.1)))
        return (f"[{self.name}-answer]", score), score

    @property
    def cost_usd(self) -> float:
        return self.tokens_used * self.usd_per_mtok / 1_000_000


def _default_pool() -> Dict[str, FakeWorker]:
    """构造 3 个有代表性的"模型"，分别对应低端 / 中端 / 高端的价位与正确率。"""
    return {
        "o4_mini_like": FakeWorker(
            name="o4_mini_like",
            one_shot_accuracy=0.35,
            refine_bonus=0.10,
            token_per_call=1200,
            usd_per_mtok=1.10,            # 低价
        ),
        "gemini_pro_like": FakeWorker(
            name="gemini_pro_like",
            one_shot_accuracy=0.55,
            refine_bonus=0.20,            # 擅长 refine
            token_per_call=1800,
            usd_per_mtok=4.00,            # 中价
        ),
        "deepseek_r1_like": FakeWorker(
            name="deepseek_r1_like",
            one_shot_accuracy=0.50,
            refine_bonus=0.05,            # 擅长 one-shot 但 refine 差
            token_per_call=2200,
            usd_per_mtok=0.80,            # 低价
        ),
    }


# ============================================================
# 2) 四种风格的"跑一遍"函数
#    全都返回相同结构 RunResult，方便横向对比
# ============================================================


@dataclass
class RunResult:
    style: str
    final_score: float
    calls: int
    tokens: int
    cost_usd: float
    wall_time_s: float
    notes: str = ""


def run_openrouter_style(
    pool: Dict[str, FakeWorker], rng: random.Random
) -> RunResult:
    """OpenRouter 风格：1 次调用，按权重路由到 1 个 LLM。"""
    t0 = time.perf_counter()
    # 路由策略：按"价格倒数 × 经验正确率"加权随机挑 1 个
    weights = [
        (1.0 / w.usd_per_mtok) * w.one_shot_accuracy for w in pool.values()
    ]
    names = list(pool.keys())
    idx = _weighted_choice(weights, rng)
    worker = pool[names[idx]]
    _, score = worker.invoke(None, rng)
    return RunResult(
        style="openrouter",
        final_score=score,
        calls=worker.calls,
        tokens=worker.tokens_used,
        cost_usd=worker.cost_usd,
        wall_time_s=time.perf_counter() - t0,
        notes=f"routed_to={worker.name}",
    )


def run_vercel_ai_sdk_style(
    pool: Dict[str, FakeWorker], rng: random.Random
) -> RunResult:
    """Vercel AI SDK 风格：streamText + prepareStep 切模型，**2 步**。

    第 1 步：用便宜模型出草稿；第 2 步：用中端模型 refine。
    流式响应在这里不模拟（只关心 token 与质量）。
    """
    t0 = time.perf_counter()
    draft_worker = pool["o4_mini_like"]
    refine_worker = pool["gemini_pro_like"]
    state, _ = draft_worker.invoke(None, rng)
    _, score = refine_worker.invoke(state, rng)
    total_tokens = draft_worker.tokens_used + refine_worker.tokens_used
    total_cost = draft_worker.cost_usd + refine_worker.cost_usd
    return RunResult(
        style="vercel_ai_sdk",
        final_score=score,
        calls=draft_worker.calls + refine_worker.calls,
        tokens=total_tokens,
        cost_usd=total_cost,
        wall_time_s=time.perf_counter() - t0,
        notes="draft=o4_mini_like → refine=gemini_pro_like",
    )


def run_langgraph_style(
    pool: Dict[str, FakeWorker], rng: random.Random
) -> RunResult:
    """LangGraph 风格：planner → executor → verifier 三节点状态图。

    每个节点用不同模型；verifier 不达标会回退到 executor 多跑一轮（带 checkpoint）。
    简化版只回退 1 次。
    """
    t0 = time.perf_counter()
    planner = pool["gemini_pro_like"]
    executor = pool["deepseek_r1_like"]
    verifier = pool["o4_mini_like"]

    plan_state, _ = planner.invoke(None, rng)
    exec_state, exec_score = executor.invoke(plan_state, rng)
    _, judge_score = verifier.invoke(exec_state, rng)
    # 简化"verifier 不过 → 再 refine 一次"分支
    if judge_score < 0.7:
        exec_state, exec_score = executor.invoke(exec_state, rng)
    total_tokens = (
        planner.tokens_used + executor.tokens_used + verifier.tokens_used
    )
    total_cost = (
        planner.cost_usd + executor.cost_usd + verifier.cost_usd
    )
    return RunResult(
        style="langgraph",
        final_score=exec_score,
        calls=planner.calls + executor.calls + verifier.calls,
        tokens=total_tokens,
        cost_usd=total_cost,
        wall_time_s=time.perf_counter() - t0,
        notes="planner → executor → verifier (+1 retry if score<0.7)",
    )


def run_treequest_style(
    pool: Dict[str, FakeWorker], rng: random.Random, budget: int = 12
) -> RunResult:
    """TreeQuest 风格：把 3 个 worker 扔进 AB-MCTS 跑 ``budget`` 步。"""
    t0 = time.perf_counter()

    def _wrap(worker: FakeWorker) -> GenerateFn:
        def _fn(parent_state):                    # noqa: ANN001
            new_state, score = worker.invoke(parent_state, rng)
            return new_state, score
        return _fn

    fns = {name: _wrap(w) for name, w in pool.items()}
    algo = ABMCTS(ABMCTSConfig(budget=budget, success_threshold=0.85))
    best, _ = algo.run(fns)
    total_calls = sum(w.calls for w in pool.values())
    total_tokens = sum(w.tokens_used for w in pool.values())
    total_cost = sum(w.cost_usd for w in pool.values())
    return RunResult(
        style="treequest",
        final_score=best.score,
        calls=total_calls,
        tokens=total_tokens,
        cost_usd=total_cost,
        wall_time_s=time.perf_counter() - t0,
        notes=f"budget={budget} best_llm={best.llm}",
    )


# ============================================================
# 3) Helpers
# ============================================================


def _weighted_choice(weights: List[float], rng: random.Random) -> int:
    total = sum(weights)
    r = rng.uniform(0, total)
    acc = 0.0
    for i, w in enumerate(weights):
        acc += w
        if r <= acc:
            return i
    return len(weights) - 1


def benchmark(
    n_trials: int = 30, seed: int = 20260620, budget: int = 12
) -> List[Dict[str, float]]:
    """跑 ``n_trials`` 次每种风格，返回均值统计。"""
    summary: Dict[str, Dict[str, List[float]]] = {}
    for trial in range(n_trials):
        rng = random.Random(seed + trial)
        # 每次用新 pool，避免累计 calls
        for style_name, runner in (
            ("openrouter", run_openrouter_style),
            ("vercel_ai_sdk", run_vercel_ai_sdk_style),
            ("langgraph", run_langgraph_style),
            ("treequest", lambda p, r: run_treequest_style(p, r, budget=budget)),
        ):
            pool = _default_pool()
            result = runner(pool, rng)
            bucket = summary.setdefault(
                style_name, {"score": [], "calls": [], "tokens": [], "cost": []}
            )
            bucket["score"].append(result.final_score)
            bucket["calls"].append(result.calls)
            bucket["tokens"].append(result.tokens)
            bucket["cost"].append(result.cost_usd)

    rows = []
    for style_name, m in summary.items():
        rows.append(
            {
                "style": style_name,
                "score_mean": statistics.mean(m["score"]),
                "score_p90": _percentile(m["score"], 0.9),
                "calls_mean": statistics.mean(m["calls"]),
                "tokens_mean": statistics.mean(m["tokens"]),
                "cost_mean_usd": statistics.mean(m["cost"]),
            }
        )
    return rows


def _percentile(xs: List[float], q: float) -> float:
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round((len(s) - 1) * q))))
    return s[k]


def main() -> None:                                # pragma: no cover
    print(">>> 4 风格横评（n_trials=30, budget=12）")
    rows = benchmark()
    print(f"{'style':<16}  score_mean  score_p90   calls   tokens   cost(USD)")
    print("-" * 70)
    for r in rows:
        print(
            f"{r['style']:<16}  {r['score_mean']:.3f}       "
            f"{r['score_p90']:.3f}      "
            f"{r['calls_mean']:>5.1f}   {r['tokens_mean']:>6.0f}  "
            f"{r['cost_mean_usd']:.5f}"
        )


if __name__ == "__main__":                          # pragma: no cover
    main()
