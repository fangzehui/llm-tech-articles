"""第 07 篇配套 demo：根据日均请求量估算月度成本.

输入：模型名 + 单次平均输入/输出 token + 日均请求数 + 工作天数
输出：每个候选模型的月度成本，并按性价比排序。

价格表来自 pricing_data.json（占位数据，实际以厂商公告为准）。

可独立运行：
    python pricing_calculator.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelPricing:
    """单个模型的价格条目."""

    name: str
    vendor: str
    input_per_m: float
    output_per_m: float
    context_window: int
    tier: str

    def cost_per_call(self, in_tokens: int, out_tokens: int) -> float:
        """单次调用的美金成本."""
        return (
            in_tokens / 1_000_000.0 * self.input_per_m
            + out_tokens / 1_000_000.0 * self.output_per_m
        )


def load_pricing(path: Path | None = None) -> list[ModelPricing]:
    """从 JSON 加载价格表."""
    p = path or (Path(__file__).resolve().parent / "pricing_data.json")
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [ModelPricing(**m) for m in raw["models"]]


@dataclass
class WorkloadProfile:
    """业务画像，用于估算月度成本.

    Attributes:
        name: 业务名
        avg_input_tokens: 单次平均输入
        avg_output_tokens: 单次平均输出
        daily_requests: 日均请求数
        active_days: 一个月活跃天数（默认按 30 天）
    """

    name: str
    avg_input_tokens: int
    avg_output_tokens: int
    daily_requests: int
    active_days: int = 30

    @property
    def calls_per_month(self) -> int:
        return self.daily_requests * self.active_days


def estimate_monthly_cost(
    workload: WorkloadProfile, models: list[ModelPricing]
) -> list[tuple[ModelPricing, float, float]]:
    """估算每个候选模型的月度成本，并按成本升序返回.

    Args:
        workload: 业务画像
        models: 候选模型列表

    Returns:
        [(模型, 单次成本, 月度成本)]，按月度成本升序
    """
    rows: list[tuple[ModelPricing, float, float]] = []
    for m in models:
        per_call = m.cost_per_call(workload.avg_input_tokens, workload.avg_output_tokens)
        monthly = per_call * workload.calls_per_month
        rows.append((m, per_call, monthly))
    rows.sort(key=lambda r: r[2])
    return rows


def render_table(rows: list[tuple[ModelPricing, float, float]]) -> str:
    """把估算结果渲染成对齐的纯文本表."""
    lines = [
        f"{'model':18s} {'vendor':10s} {'tier':8s} "
        f"{'per_call_USD':>14s} {'monthly_USD':>14s}"
    ]
    lines.append("-" * len(lines[0]))
    for m, per, month in rows:
        lines.append(
            f"{m.name:18s} {m.vendor:10s} {m.tier:8s} "
            f"{per:>14.6f} {month:>14.2f}"
        )
    return "\n".join(lines)


def main() -> None:  # pragma: no cover
    models = load_pricing()
    workloads = [
        WorkloadProfile("客服 QA", avg_input_tokens=600, avg_output_tokens=200, daily_requests=20000),
        WorkloadProfile("文档 RAG", avg_input_tokens=8000, avg_output_tokens=400, daily_requests=2000),
        WorkloadProfile("Code Gen", avg_input_tokens=2500, avg_output_tokens=800, daily_requests=5000),
    ]
    for w in workloads:
        print(f"\n=== {w.name} | {w.calls_per_month} calls/month ===")
        rows = estimate_monthly_cost(w, models)
        print(render_table(rows))


if __name__ == "__main__":  # pragma: no cover
    main()
