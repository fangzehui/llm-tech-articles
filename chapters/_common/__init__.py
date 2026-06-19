"""chapters/_common 公共工具模块.

提供 12 篇章节 demo 共用的 mock LLM 客户端、计时辅助等工具。
各章节 demo 可以选择性地引用这里的工具，也可以完全独立实现。
"""

from .mock_llm import MockLLMClient, MockLLMResponse, MockProviderError

__all__ = ["MockLLMClient", "MockLLMResponse", "MockProviderError"]
