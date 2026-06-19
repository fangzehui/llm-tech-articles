"""第 02 篇配套 demo：Token 成本计数与汇总.

支持：
- 优先用 tiktoken 精确计 token，未安装时回退到字符长度估算
- 多模型单价表，输入输出分开计费
- 单条调用记账 + 周期汇总

可独立运行：
    python cost_tracker.py
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

# 单价表，单位：USD / 1M tokens
# 数据仅用于演示成本结构，实际单价请以厂商官方公告为准
MODEL_PRICING_USD_PER_M: dict[str, tuple[float, float]] = {
    # model: (input_price, output_price)
    "gpt-mini": (0.15, 0.60),
    "gpt-pro": (3.50, 14.00),
    "claude-haiku": (0.25, 1.25),
    "claude-sonnet": (4.00, 18.00),
    "qwen-flash": (0.05, 0.15),
    "deepseek-v": (0.27, 1.10),
}


def _try_tiktoken_encoder(model: str):
    """尝试加载 tiktoken 编码器，失败返回 None."""
    try:
        import tiktoken  # type: ignore
    except ImportError:
        return None
    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None


def count_tokens(text: str, model: str = "gpt-mini") -> int:
    """计算文本的 token 数量.

    Args:
        text: 待计数文本
        model: 用于选择合适 tokenizer

    Returns:
        token 数；tiktoken 不可用时按经验比例估算
        （英文 4 字符≈1 token，中文 1.5 字符≈1 token）
    """
    enc = _try_tiktoken_encoder(model)
    if enc is not None:
        return len(enc.encode(text))
    # fallback：按字符 + 中文字比例估算
    chinese = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - chinese
    return max(1, int(chinese / 1.5 + other / 4))


@dataclass
class UsageRecord:
    """单次调用的用量记账."""

    model: str
    input_tokens: int
    output_tokens: int
    tag: str = "default"

    def cost_usd(self) -> float:
        """根据单价表计算这条记录的美金成本."""
        in_p, out_p = MODEL_PRICING_USD_PER_M.get(self.model, (0.0, 0.0))
        return (
            self.input_tokens / 1_000_000.0 * in_p
            + self.output_tokens / 1_000_000.0 * out_p
        )


@dataclass
class CostTracker:
    """累计多个 UsageRecord，并按 tag / model 汇总."""

    records: list[UsageRecord] = field(default_factory=list)

    def record(
        self,
        model: str,
        prompt: str | None = None,
        completion: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        tag: str = "default",
    ) -> UsageRecord:
        """登记一次调用.

        既可以传文本（自动计 token），也可以直接传 token 数。

        Args:
            model: 模型名
            prompt: 输入文本，与 input_tokens 二选一
            completion: 输出文本，与 output_tokens 二选一
            input_tokens: 已知的输入 token
            output_tokens: 已知的输出 token
            tag: 业务标签，用于后续按业务汇总

        Returns:
            新建的 UsageRecord
        """
        if input_tokens is None:
            input_tokens = count_tokens(prompt or "", model=model)
        if output_tokens is None:
            output_tokens = count_tokens(completion or "", model=model)
        rec = UsageRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tag=tag,
        )
        self.records.append(rec)
        return rec

    def total_cost_usd(self, records: Iterable[UsageRecord] | None = None) -> float:
        """汇总成本（USD）."""
        seq = list(records) if records is not None else self.records
        return sum(r.cost_usd() for r in seq)

    def summary_by(self, key: str = "model") -> dict[str, dict[str, float]]:
        """按指定字段聚合用量与成本.

        Args:
            key: 'model' 或 'tag'

        Returns:
            {分组键: {input_tokens, output_tokens, cost_usd, n_calls}}
        """
        if key not in {"model", "tag"}:
            raise ValueError("key must be 'model' or 'tag'")
        out: dict[str, dict[str, float]] = defaultdict(
            lambda: {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "n_calls": 0}
        )
        for r in self.records:
            k = getattr(r, key)
            out[k]["input_tokens"] += r.input_tokens
            out[k]["output_tokens"] += r.output_tokens
            out[k]["cost_usd"] += r.cost_usd()
            out[k]["n_calls"] += 1
        return dict(out)


def main() -> None:  # pragma: no cover
    tracker = CostTracker()
    tracker.record("gpt-pro", prompt="Hello, world. " * 50, completion="OK", tag="chat")
    tracker.record(
        "claude-haiku", prompt="长文档摘要任务" * 100, completion="摘要：...", tag="rag"
    )
    tracker.record("qwen-flash", prompt="今天天气怎么样", completion="阴", tag="chat")
    print(f"total cost = ${tracker.total_cost_usd():.6f}")
    for k, v in tracker.summary_by("model").items():
        print(f"  {k:15s} -> {v}")


if __name__ == "__main__":  # pragma: no cover
    main()
