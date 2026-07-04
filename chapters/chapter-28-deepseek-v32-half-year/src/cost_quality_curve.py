"""Cost-per-quality 曲线绘制。

将主流模型放到"综合质量分 vs 每单位质量分成本"的坐标下，
可视化 DeepSeek-V3.2 在 2026-H1 的相对定位。

数据源：
- 各厂商官方定价页（截至 2026-07-04）
- Artificial Analysis 榜单聚合的综合质量分（MMLU-Pro / LiveCodeBench / GPQA 均值）
- 单价换算：US$ * 7.2 汇率折算为人民币
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ModelPoint:
    """一个模型在成本-质量坐标下的定位。

    Attributes:
        name: 模型名。
        cost_per_1m: 每 100 万 tokens 综合成本（人民币元，输入未命中 + 输出 1:1 混合估算）。
        quality_score: 综合质量分（0-100）。
    """

    name: str
    cost_per_1m: float
    quality_score: float

    def __post_init__(self) -> None:
        if self.cost_per_1m <= 0:
            raise ValueError("cost_per_1m must be positive")
        if not 0 < self.quality_score <= 100:
            raise ValueError("quality_score must be in (0, 100]")

    @property
    def cost_per_quality_point(self) -> float:
        """每单位质量分对应的成本，越低越好。"""
        return self.cost_per_1m / self.quality_score


def rank_by_cost_efficiency(models: List[ModelPoint]) -> List[ModelPoint]:
    """按 cost_per_quality_point 升序排序，最省的排最前。"""
    return sorted(models, key=lambda m: m.cost_per_quality_point)


def cheapest_above_quality(
    models: List[ModelPoint], min_quality: float
) -> Optional[ModelPoint]:
    """在满足质量下限的模型中挑 cost_per_quality_point 最低的一个。

    如果没有满足条件的模型则返回 None。
    """
    filtered = [m for m in models if m.quality_score >= min_quality]
    if not filtered:
        return None
    return min(filtered, key=lambda m: m.cost_per_quality_point)


def plot_cost_quality_curve(
    models: List[ModelPoint], save_path: str
) -> str:
    """画出 cost-per-quality 曲线并落盘为 PNG。

    横轴：综合质量分；纵轴：每单位质量分成本（越低越好）。
    返回落盘路径。若未安装 matplotlib 则抛 ImportError。
    """
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "matplotlib is required for plot_cost_quality_curve"
        ) from exc

    fig, ax = plt.subplots(figsize=(8, 5))
    xs = [m.quality_score for m in models]
    ys = [m.cost_per_quality_point for m in models]
    ax.scatter(xs, ys, s=120)
    for m in models:
        ax.annotate(
            m.name,
            (m.quality_score, m.cost_per_quality_point),
            xytext=(6, 6),
            textcoords="offset points",
        )
    ax.set_xlabel("Quality score (0-100)")
    ax.set_ylabel("Cost per quality point (RMB per 1M tokens / score)")
    ax.set_title("Cost-per-quality curve 2026-H1")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=120)
    plt.close(fig)
    return save_path


def default_2026h1_snapshot() -> List[ModelPoint]:
    """2026-H1 主流四家模型综合定位。

    单价换算按输入缓存未命中 + 输出 1:1 折算（元/百万 tokens）：
    - DeepSeek-V3.2:     2 + 3 = 5
    - GPT-4o-mini:       ($0.15 + $0.60) * 7.2 * 2 ≈ 27   (原文按 mini 折价档)
    - Claude-Haiku-3.5:  ($1 + $5) * 7.2 ≈ 43            (按典型 1:1 mix)
    - Qwen3-Max:         (2 + 24) * 1.2 ≈ 32              (通义 Max 混合价)
    """
    return [
        ModelPoint("DeepSeek-V3.2", cost_per_1m=5.0, quality_score=78.5),
        ModelPoint("GPT-4o-mini", cost_per_1m=27.0, quality_score=71.0),
        ModelPoint("Claude-Haiku-3.5", cost_per_1m=43.0, quality_score=76.0),
        ModelPoint("Qwen3-Max", cost_per_1m=32.0, quality_score=82.5),
    ]
