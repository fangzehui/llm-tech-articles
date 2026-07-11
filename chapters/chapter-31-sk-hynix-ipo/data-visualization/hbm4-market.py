"""
HBM Market Share & HBM4 Premium Visualization.

Data source:
- Counterpoint / SK Hynix Q1 2026 filings (56.4% market share)
- PomiNews: https://pomegra.io/news/sk-hynix-micron-build-buffers-against-ai-memory-slump (HBM4 ~50% premium over HBM3E)
- DigiTimes 2026-07 via EET-China: https://www.eet-china.com/mp/a509086.html (HBM4 pricing curve $2/Gb -> $4-5/Gb)
- 融中财经 2026-07-11: https://www.thecapital.com.cn/newsDetail/124080 (Q1 gross margin 79.3%, net margin 77%)

Usage:
    python hbm4-market.py
Outputs: hbm4-market.png (300 DPI)
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial Unicode MS", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False


def market_share_data():
    """HBM market share Q1 2026 (Counterpoint)."""
    return {
        "SK Hynix": 56.4,
        "Micron": 23.6,
        "Samsung": 18.5,
        "Others": 1.5,
    }


def hbm4_premium_data():
    """HBM4 vs HBM3E contract price index (HBM3E = 100)."""
    return {
        "HBM3E 12H": 100,
        "HBM4 12H (2026 H2)": 150,   # ~50% premium (PomiNews)
        "HBM4 12H (2027 H1)": 225,   # DigiTimes forecast 2x by 2027
    }


def draw_dual_chart(share, premium, output_path="hbm4-market.png"):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # Left: HBM market share pie chart
    labels = list(share.keys())
    sizes = list(share.values())
    colors = ["#00a676", "#f4a259", "#5b8e7d", "#bc4b51"]
    explode = (0.08, 0, 0, 0)

    wedges, texts, autotexts = ax1.pie(
        sizes,
        labels=labels,
        colors=colors,
        autopct="%1.1f%%",
        startangle=90,
        explode=explode,
        pctdistance=0.75,
        textprops={"fontsize": 11, "fontweight": "bold"},
        wedgeprops={"edgecolor": "white", "linewidth": 2},
    )
    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontweight("bold")

    ax1.set_title(
        "Global HBM Market Share — Q1 2026 (Counterpoint)\nSK Hynix leads with 56.4%",
        fontsize=12,
        fontweight="bold",
        pad=15,
    )

    # Right: HBM4 pricing premium bar chart
    p_labels = list(premium.keys())
    p_values = list(premium.values())
    x_pos = np.arange(len(p_labels))

    bar_colors = ["#5b8e7d", "#f4a259", "#d1495b"]
    bars = ax2.bar(x_pos, p_values, color=bar_colors, edgecolor="white", linewidth=2, width=0.6)

    # Value labels on top
    for bar, val in zip(bars, p_values):
        h = bar.get_height()
        ax2.annotate(
            f"{val}",
            xy=(bar.get_x() + bar.get_width() / 2, h),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
        )
        # Premium label
        if val > 100:
            ax2.annotate(
                f"+{val - 100}%",
                xy=(bar.get_x() + bar.get_width() / 2, h / 2),
                ha="center",
                va="center",
                fontsize=13,
                fontweight="bold",
                color="white",
            )

    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(p_labels, fontsize=10)
    ax2.set_ylabel("Contract Price Index (HBM3E = 100)", fontsize=11)
    ax2.set_ylim(0, 260)
    ax2.set_title(
        "HBM4 Contract Price Premium\n(PomiNews / DigiTimes 2026-07)",
        fontsize=12,
        fontweight="bold",
        pad=15,
    )
    ax2.grid(True, axis="y", alpha=0.3, linestyle="--")
    ax2.axhline(y=100, color="#333", linestyle=":", linewidth=1, alpha=0.6)

    for spine in ["top", "right"]:
        ax2.spines[spine].set_visible(False)

    fig.suptitle(
        "SK Hynix's Moat: Market Leadership + HBM4 Pricing Power (locked 2026-2027)",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"[ok] saved -> {output_path}")


if __name__ == "__main__":
    share = market_share_data()
    premium = hbm4_premium_data()
    draw_dual_chart(share, premium, output_path="hbm4-market.png")
