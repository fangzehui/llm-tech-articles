"""visualize.py
==============

第 18 篇配套源码：可视化模块，使用 matplotlib。

提供两张核心图：
1. ``draw_top_models_bar()``：Top 10 单模型周调用量条形图（中美双色）
2. ``draw_weekly_trend()``：单个模型近 N 周的调用量折线 + 环比柱状

为了支持在无 matplotlib 环境下被 import（例如 CI 跑 smoke test 时），
matplotlib 只在函数内部 lazy import，且每个函数都有 ``dry_run`` 参数：
``dry_run=True`` 时只返回构造好的 figure 数据 dict，不真正画图。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from weekly_tracker import WeekSnapshot

# 让 matplotlib 在没有显示器的环境也能跑
os.environ.setdefault("MPLBACKEND", "Agg")


# ---------------------------------------------------------------------------
# 1) Top 10 条形图
# ---------------------------------------------------------------------------


def _top_models_payload(snap: WeekSnapshot) -> Dict[str, Any]:
    """提取画图所需数据（不依赖 matplotlib），用于 dry_run 与单测."""
    models = list(reversed(snap.top_models))  # 横向条形图从下往上画
    return {
        "title": f"OpenRouter 单模型 Top {len(snap.top_models)}（{snap.start_date}~{snap.end_date}）",
        "x_label": "周调用量（万亿 Token）",
        "labels": [f"{m.rank}. {m.model}" for m in models],
        "values": [m.tokens_trillion for m in models],
        "colors": ["#d23f31" if m.is_china() else "#1f78b4" for m in models],
        "wow_pct": [m.wow_pct for m in models],
    }


def draw_top_models_bar(
    snap: WeekSnapshot,
    out_path: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    payload = _top_models_payload(snap)
    if dry_run:
        return payload

    import matplotlib.pyplot as plt  # type: ignore

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(payload["labels"], payload["values"], color=payload["colors"])
    ax.set_title(payload["title"])
    ax.set_xlabel(payload["x_label"])
    for bar, v, wow in zip(bars, payload["values"], payload["wow_pct"]):
        sign = "+" if wow > 0 else ""
        ax.text(
            v + max(payload["values"]) * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{v:.2f}T ({sign}{wow:.0f}%)",
            va="center",
            fontsize=9,
        )
    # 图例：中美双色
    from matplotlib.patches import Patch  # type: ignore
    ax.legend(handles=[
        Patch(color="#d23f31", label="China"),
        Patch(color="#1f78b4", label="US"),
    ], loc="lower right")
    plt.tight_layout()

    if out_path:
        plt.savefig(out_path, dpi=120)
    plt.close(fig)
    payload["saved_to"] = out_path
    return payload


# ---------------------------------------------------------------------------
# 2) 单模型周趋势
# ---------------------------------------------------------------------------


def _trend_payload(snap: WeekSnapshot, model: str) -> Dict[str, Any]:
    hist = snap.history_v4_flash
    if not hist:
        raise ValueError("snapshot 未包含历史数据")
    return {
        "title": f"{model} · 近 {len(hist)} 周调用量趋势",
        "weeks": [h["week"] for h in hist],
        "tokens": [h["tokens_trillion"] for h in hist],
        "wow_pct": [h["wow_pct"] for h in hist],
    }


def draw_weekly_trend(
    snap: WeekSnapshot,
    model: str = "DeepSeek-V4-Flash",
    out_path: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    payload = _trend_payload(snap, model)
    if dry_run:
        return payload

    import matplotlib.pyplot as plt  # type: ignore

    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax1.plot(payload["weeks"], payload["tokens"], marker="o", color="#d23f31",
             linewidth=2, label="周调用量 (T)")
    ax1.set_ylabel("周调用量（万亿 Token）", color="#d23f31")
    ax1.tick_params(axis="y", labelcolor="#d23f31")

    ax2 = ax1.twinx()
    ax2.bar(payload["weeks"], payload["wow_pct"], alpha=0.3, color="#1f78b4",
            label="环比 (%)")
    ax2.set_ylabel("环比变化（%）", color="#1f78b4")
    ax2.tick_params(axis="y", labelcolor="#1f78b4")

    ax1.set_title(payload["title"])
    fig.autofmt_xdate(rotation=45)
    plt.tight_layout()

    if out_path:
        plt.savefig(out_path, dpi=120)
    plt.close(fig)
    payload["saved_to"] = out_path
    return payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    from weekly_tracker import load_week

    snap = load_week()
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    os.makedirs(out_dir, exist_ok=True)

    p1 = draw_top_models_bar(snap, out_path=os.path.join(out_dir, "top_models.png"))
    p2 = draw_weekly_trend(snap, model="DeepSeek-V4-Flash",
                           out_path=os.path.join(out_dir, "trend_v4_flash.png"))
    print(f"已生成: {p1.get('saved_to')}")
    print(f"已生成: {p2.get('saved_to')}")


if __name__ == "__main__":
    main()
