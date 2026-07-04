"""DeepSeekTierRouter: 多档 DeepSeek 路由伪代码。

根据请求复杂度、是否需要强推理、预算敏感度、上下文长度
自动在以下三档之间路由：

- V32_ECON  : deepseek-v3.2-exp    (二五折经济档，长上下文/低复杂度首选)
- V3_MAIN   : deepseek-chat-main   (V3 主档，稳定通道)
- R1_REASON : deepseek-reasoner    (强推理档，复杂 Agent / 数学 / 代码)

路由规则按优先级：
    1) 长上下文 (>=32K) + 非强推理  -> V32_ECON (DSA 直接收益)
    2) needs_reasoning=True & complexity>=0.7  -> R1_REASON
    3) complexity<0.35 & budget_sensitivity>=0.6 -> V32_ECON
    4) budget_sensitivity>=0.8  -> V32_ECON (预算兜底)
    5) 其它默认 -> V3_MAIN
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple


class DeepSeekTier(str, Enum):
    V32_ECON = "deepseek-v3.2-exp"
    V3_MAIN = "deepseek-chat-main"
    R1_REASON = "deepseek-reasoner"


@dataclass(frozen=True)
class Request:
    """一次 LLM 调用请求的最小刻画。"""

    prompt_tokens: int
    expected_output_tokens: int
    complexity: float
    needs_reasoning: bool
    budget_sensitivity: float

    def __post_init__(self) -> None:
        if self.prompt_tokens < 0 or self.expected_output_tokens < 0:
            raise ValueError("token counts must be non-negative")
        if not 0.0 <= self.complexity <= 1.0:
            raise ValueError("complexity must be in [0, 1]")
        if not 0.0 <= self.budget_sensitivity <= 1.0:
            raise ValueError("budget_sensitivity must be in [0, 1]")


class DeepSeekTierRouter:
    """多档 DeepSeek 路由器。"""

    LONG_CONTEXT_THRESHOLD = 32_000

    # 单价矩阵（元/百万 tokens），输入按缓存未命中最坏估算
    _PRICE_MATRIX: Dict[DeepSeekTier, Tuple[float, float]] = {
        DeepSeekTier.V32_ECON: (2.0, 3.0),
        DeepSeekTier.V3_MAIN: (2.0, 3.0),
        DeepSeekTier.R1_REASON: (2.0, 3.0),
    }

    def route(self, req: Request) -> DeepSeekTier:
        # 长上下文 + 非强推理，走 V32 吃 DSA 红利
        if (
            req.prompt_tokens >= self.LONG_CONTEXT_THRESHOLD
            and not req.needs_reasoning
        ):
            return DeepSeekTier.V32_ECON
        # 强推理直通 R1
        if req.needs_reasoning and req.complexity >= 0.7:
            return DeepSeekTier.R1_REASON
        # 简单任务 + 预算敏感 -> 经济档
        if req.complexity < 0.35 and req.budget_sensitivity >= 0.6:
            return DeepSeekTier.V32_ECON
        # 极度敏感预算 -> 经济档兜底
        if req.budget_sensitivity >= 0.8:
            return DeepSeekTier.V32_ECON
        return DeepSeekTier.V3_MAIN

    def estimate_cost_yuan(
        self, req: Request, tier: DeepSeekTier
    ) -> float:
        """估算单次调用成本（元），事后核对与预算追踪。"""
        p_in, p_out = self._PRICE_MATRIX[tier]
        return (req.prompt_tokens / 1e6) * p_in + (
            req.expected_output_tokens / 1e6
        ) * p_out

    def route_and_estimate(
        self, req: Request
    ) -> Tuple[DeepSeekTier, float]:
        """返回 (tier, estimated_cost_yuan)。"""
        t = self.route(req)
        return t, self.estimate_cost_yuan(req, t)

    def batch_route(
        self, requests: List[Request]
    ) -> List[Tuple[DeepSeekTier, float]]:
        """批量路由 + 成本估算。"""
        return [self.route_and_estimate(r) for r in requests]

    @staticmethod
    def summarize_batch(
        results: List[Tuple[DeepSeekTier, float]]
    ) -> Dict[str, object]:
        """对批量结果做汇总：各档调用次数与总成本。"""
        summary: Dict[str, object] = {
            "total_calls": len(results),
            "total_cost_yuan": round(sum(cost for _, cost in results), 4),
            "by_tier": {},
        }
        by_tier: Dict[str, Dict[str, float]] = {}
        for tier, cost in results:
            key = tier.value
            if key not in by_tier:
                by_tier[key] = {"calls": 0, "cost_yuan": 0.0}
            by_tier[key]["calls"] += 1
            by_tier[key]["cost_yuan"] += cost
        for key, stat in by_tier.items():
            stat["cost_yuan"] = round(stat["cost_yuan"], 4)
        summary["by_tier"] = by_tier
        return summary
