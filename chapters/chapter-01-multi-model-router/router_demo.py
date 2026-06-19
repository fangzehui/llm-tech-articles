"""第 01 篇配套 demo：简化版多模型主备路由器.

包含：
- 三个 mock provider（GPT 系 / Claude 系 / Qwen 系）
- 主备切换 + 故障熔断
- 三种路由策略（cost_first / quality_first / balanced）

可独立运行：
    python router_demo.py
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# 让 demo 既能在章节目录单独跑，也能从仓库根 import
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import MockLLMClient, MockLLMResponse, MockProviderError  # noqa: E402


@dataclass
class ProviderEntry:
    """一个候选 provider 的元信息.

    Attributes:
        name: 标识
        client: 实际调用客户端
        cost_score: 成本评分（数值越低代表单价越低）
        quality_score: 质量评分（越高越强）
        weight: balanced 模式下用于打分
    """

    name: str
    client: MockLLMClient
    cost_score: float
    quality_score: float
    weight: float = 1.0


class MultiModelRouter:
    """简化版多模型路由器，演示策略选型 + 主备切换.

    策略：
        - cost_first: 按 cost_score 升序
        - quality_first: 按 quality_score 降序
        - balanced: 按 quality / cost 比值降序
    """

    STRATEGIES: dict[str, Callable[[ProviderEntry], float]] = {
        "cost_first": lambda p: p.cost_score,
        "quality_first": lambda p: -p.quality_score,
        "balanced": lambda p: -(p.quality_score / max(p.cost_score, 0.01)),
    }

    def __init__(
        self,
        providers: list[ProviderEntry],
        strategy: str = "balanced",
        max_failover: int = 2,
    ) -> None:
        """初始化路由器.

        Args:
            providers: 候选 provider 列表
            strategy: 路由策略
            max_failover: 单次请求最多尝试多少个备选
        """
        if strategy not in self.STRATEGIES:
            raise ValueError(f"unknown strategy: {strategy}")
        self.providers = providers
        self.strategy = strategy
        self.max_failover = max_failover
        self._cooldown_until: dict[str, float] = {}

    def _rank(self) -> list[ProviderEntry]:
        """按当前策略给候选排序，剔除处于冷却期的 provider."""
        now = time.time()
        alive = [p for p in self.providers if self._cooldown_until.get(p.name, 0) <= now]
        return sorted(alive, key=self.STRATEGIES[self.strategy])

    def _mark_failed(self, name: str, cooldown_sec: float = 5.0) -> None:
        """把出错的 provider 放入冷却池，避免短时间反复打到坏节点."""
        self._cooldown_until[name] = time.time() + cooldown_sec

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 256,
    ) -> MockLLMResponse:
        """按策略+主备切换发起一次请求.

        Args:
            messages: OpenAI 风格消息
            max_tokens: 输出 token 上限

        Returns:
            首个成功 provider 的响应

        Raises:
            RuntimeError: 所有候选都失败
        """
        candidates = self._rank()
        if not candidates:
            raise RuntimeError("no provider available (all in cooldown)")
        last_err: Exception | None = None
        tried = 0
        for entry in candidates:
            if tried >= self.max_failover + 1:
                break
            tried += 1
            try:
                resp = entry.client.chat(messages, max_tokens=max_tokens)
                resp.meta["router_strategy"] = self.strategy
                resp.meta["router_attempts"] = tried
                return resp
            except MockProviderError as exc:
                last_err = exc
                self._mark_failed(entry.name)
        raise RuntimeError(f"all providers failed, last error: {last_err}")


def build_demo_router(strategy: str = "balanced") -> MultiModelRouter:
    """构造一个内置三家 provider 的演示路由器."""
    return MultiModelRouter(
        providers=[
            ProviderEntry(
                name="gpt-mock",
                client=MockLLMClient("openai", "gpt-mock", 80, 0.0, seed=1),
                cost_score=10.0,
                quality_score=95.0,
            ),
            ProviderEntry(
                name="claude-mock",
                client=MockLLMClient("anthropic", "claude-mock", 70, 0.0, seed=2),
                cost_score=12.0,
                quality_score=93.0,
            ),
            ProviderEntry(
                name="qwen-mock",
                client=MockLLMClient("qwen", "qwen-mock", 50, 0.0, seed=3),
                cost_score=1.0,
                quality_score=82.0,
            ),
        ],
        strategy=strategy,
    )


def main() -> None:  # pragma: no cover
    msgs = [{"role": "user", "content": "用一句话解释多模型路由"}]
    for stg in ("cost_first", "quality_first", "balanced"):
        router = build_demo_router(stg)
        resp = router.chat(msgs)
        print(f"[{stg}] -> {resp.provider}/{resp.model} | {resp.content[:60]}")


if __name__ == "__main__":  # pragma: no cover
    main()
