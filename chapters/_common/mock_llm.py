"""Mock LLM 客户端，用于在 demo 中模拟模型调用而不依赖真实网络.

设计目标：
- 可控制延迟与失败率，方便演示重试 / 熔断 / 故障切换
- 返回结构尽量贴近 OpenAI Chat Completions 风格
- 完全本地运行，所有章节 demo 都可在无密钥环境下跑通
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any


class MockProviderError(RuntimeError):
    """Mock 后端抛出的故障，用于测试容错逻辑."""


@dataclass
class MockLLMResponse:
    """模拟一次 chat completion 的返回值.

    Attributes:
        model: 模型名
        content: 文本内容
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数
        latency_ms: 实际耗时
        provider: 提供方标识
        meta: 其他元信息
    """

    model: str
    content: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    provider: str = "mock"
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class MockLLMClient:
    """一个本地 mock 的 LLM 客户端.

    不会发起任何网络请求，根据传入的延迟与失败率配置返回结果或抛错。
    """

    def __init__(
        self,
        provider: str = "mock",
        model: str = "mock-small",
        base_latency_ms: float = 50.0,
        failure_rate: float = 0.0,
        seed: int | None = None,
    ) -> None:
        """构造 mock 客户端.

        Args:
            provider: 提供方名称（如 openai / anthropic / qwen）
            model: 模型名
            base_latency_ms: 基础延迟，会叠加 0~30ms 的抖动
            failure_rate: 0~1，本次调用抛错的概率
            seed: 随机种子，便于在测试中复现
        """
        self.provider = provider
        self.model = model
        self.base_latency_ms = base_latency_ms
        self.failure_rate = failure_rate
        self._rng = random.Random(seed)

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 256,
    ) -> MockLLMResponse:
        """模拟一次 chat 调用.

        Args:
            messages: OpenAI 风格的消息列表
            max_tokens: 输出 token 上限（仅用于估算）

        Returns:
            MockLLMResponse 对象

        Raises:
            MockProviderError: 当随机抛错命中时
        """
        jitter = self._rng.uniform(0, 30)
        latency_ms = self.base_latency_ms + jitter
        # 真实 sleep 太慢，demo 里只睡很小一段
        time.sleep(latency_ms / 10000.0)

        if self._rng.random() < self.failure_rate:
            raise MockProviderError(
                f"mock provider {self.provider} simulated failure"
            )

        text = "".join(m.get("content", "") for m in messages)
        prompt_tokens = max(1, len(text) // 2)
        completion_tokens = min(max_tokens, max(8, len(text) // 4))
        content = (
            f"[{self.provider}/{self.model}] echo: "
            f"{text[:80]}{'...' if len(text) > 80 else ''}"
        )
        return MockLLMResponse(
            model=self.model,
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            provider=self.provider,
        )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"MockLLMClient(provider={self.provider!r}, model={self.model!r}, "
            f"failure_rate={self.failure_rate})"
        )
