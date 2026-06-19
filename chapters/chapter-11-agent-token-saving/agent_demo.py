"""第 11 篇配套 demo：Agent Token 降本 4 条工程路径示意.

四条路径：
1. 执行链路裁剪（PathCut）：跳过冗余 plan / 反思
2. 上下文压缩（ContextCompressor）：滑动窗口 + 工具结果裁剪
3. 模型分级路由（TierDispatch）：按子任务复杂度选模型
4. Prompt Cache（PromptCache）：高频前缀 prefix caching 模拟

每条路径都给出一个可独立调用的工具函数 + Agent 主循环里如何使用。

可独立运行：
    python agent_demo.py
"""

from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import MockLLMClient  # noqa: E402


# ============================================================
# 路径 1：执行链路裁剪
# ============================================================

@dataclass
class PathCut:
    """根据置信度裁掉非必要的 plan/reflection 步骤."""

    confidence_threshold: float = 0.85

    def should_skip_replan(self, last_step_confidence: float) -> bool:
        """上一步置信度足够高就跳过 replan，省一次 LLM 调用."""
        return last_step_confidence >= self.confidence_threshold

    def should_skip_reflection(self, completed_subtasks: int) -> bool:
        """子任务<=2 时不必反思，直接出最终答案."""
        return completed_subtasks <= 2


# ============================================================
# 路径 2：上下文压缩
# ============================================================

@dataclass
class ContextCompressor:
    """滑动窗口 + 工具结果摘要裁剪."""

    keep_messages: int = 6
    tool_result_max_chars: int = 500

    def trim_history(self, history: list[dict]) -> list[dict]:
        """只保留最近 N 条消息，加上系统消息."""
        sys_msgs = [m for m in history if m.get("role") == "system"]
        rest = [m for m in history if m.get("role") != "system"]
        return sys_msgs + rest[-self.keep_messages :]

    def truncate_tool_result(self, content: str) -> str:
        """大段 tool output 截断，避免污染上下文."""
        if len(content) <= self.tool_result_max_chars:
            return content
        return content[: self.tool_result_max_chars] + "\n...[truncated]"


# ============================================================
# 路径 3：模型分级路由
# ============================================================

@dataclass
class TierDispatch:
    """按 subtask 类型选择对应档位的 mock client."""

    clients: dict[str, MockLLMClient] = field(default_factory=dict)
    rules: dict[str, str] = field(default_factory=dict)

    def pick(self, subtask_type: str) -> MockLLMClient:
        tier = self.rules.get(subtask_type, "small")
        if tier not in self.clients:
            raise KeyError(f"no client for tier {tier}")
        return self.clients[tier]


def build_default_dispatch() -> TierDispatch:
    """内置一份默认档位映射，方便 demo 直接跑."""
    clients = {
        "small": MockLLMClient("mock", "small", 50, seed=1),
        "mid": MockLLMClient("mock", "mid", 90, seed=2),
        "flagship": MockLLMClient("mock", "flagship", 150, seed=3),
    }
    rules = {
        "extract": "small",
        "summarize": "mid",
        "plan": "flagship",
        "code": "flagship",
        "answer": "mid",
    }
    return TierDispatch(clients=clients, rules=rules)


# ============================================================
# 路径 4：Prompt Cache
# ============================================================

@dataclass
class PromptCache:
    """模拟 prefix caching：相同前缀只算一份输入 token."""

    _cached_prefix: str = ""
    cache_hits: int = 0
    saved_tokens: int = 0

    def call(
        self,
        client: MockLLMClient,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int]:
        """带 prefix cache 的调用.

        Returns:
            (内容, 实际计费的输入 token 数)
        """
        if system_prompt == self._cached_prefix and self._cached_prefix:
            # 命中：只算 user 部分
            self.cache_hits += 1
            real_input = max(1, len(user_prompt) // 2)
            self.saved_tokens += max(1, len(system_prompt) // 2)
        else:
            self._cached_prefix = system_prompt
            real_input = max(1, (len(system_prompt) + len(user_prompt)) // 2)
        resp = client.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        return resp.content, real_input


# ============================================================
# 综合主循环
# ============================================================

@dataclass
class AgentRunSummary:
    """Agent 执行汇总."""

    steps: int = 0
    skipped_plan: int = 0
    skipped_reflection: int = 0
    cache_hits: int = 0
    saved_tokens_via_cache: int = 0


def run_agent(
    subtasks: list[tuple[str, str]],
    *,
    last_confidence_provider: Callable[[int], float] = lambda _: 0.9,
) -> AgentRunSummary:
    """跑一段 Agent 演示，叠加 4 条降本路径.

    Args:
        subtasks: [(subtask_type, prompt)] 列表
        last_confidence_provider: 给定步号返回当步置信度，用于演示 PathCut

    Returns:
        汇总信息
    """
    cut = PathCut(confidence_threshold=0.85)
    compressor = ContextCompressor(keep_messages=4, tool_result_max_chars=200)
    dispatch = build_default_dispatch()
    cache = PromptCache()
    history: deque[dict] = deque()
    summary = AgentRunSummary()

    system_prompt = "你是一个高效执行多步任务的 Agent，回答尽量简短。"

    for idx, (subtype, prompt) in enumerate(subtasks):
        # 路径 1：是否跳过 replan
        if idx > 0 and cut.should_skip_replan(last_confidence_provider(idx - 1)):
            summary.skipped_plan += 1

        # 路径 2：trim 历史
        list(history)  # 显式调用以触发 logic（这里只是示意）
        trimmed = compressor.trim_history(list(history))

        # 路径 3：选档
        client = dispatch.pick(subtype)

        # 路径 4：prompt cache
        content, _ = cache.call(client, system_prompt, prompt)
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": compressor.truncate_tool_result(content)})
        _ = trimmed
        summary.steps += 1

    # 路径 1：是否跳过最终反思
    if cut.should_skip_reflection(len(subtasks)):
        summary.skipped_reflection += 1

    summary.cache_hits = cache.cache_hits
    summary.saved_tokens_via_cache = cache.saved_tokens
    return summary


def main() -> None:  # pragma: no cover
    subtasks = [
        ("plan", "把这个 monorepo 升级到 Node 22 需要哪些步骤"),
        ("extract", "从 package.json 中提取所有依赖"),
        ("code", "为 axios 升级写一段兼容性代码"),
        ("answer", "给出最终的升级清单"),
    ]
    s = run_agent(subtasks)
    print(s)


if __name__ == "__main__":  # pragma: no cover
    main()
