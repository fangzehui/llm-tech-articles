"""
IPO Timeline Visualization for SK Hynix Nasdaq Listing (July 2026).

Data source:
- SK Hynix IR: https://www.skhynix.com/ir/UI-FR-IR12_T1_view/?seq=6809 (2026-07-09)
- Nasdaq.com: https://www.nasdaq.com/articles/sk-hynix-just-raised-265-billion-biggest-us-ipo-ever-foreign-company-heres-what-it-signals (2026-07-11)
- Xinhua: http://www.xinhuanet.com/20260711/2796573c95ee495caa770af318ffc731/c.html
- PomiNews: https://pomegra.io/news/sk-hynix-micron-build-buffers-against-ai-memory-slump

Usage:
    python ipo-timeline.py
Outputs: ipo-timeline.png (300 DPI)
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# Set Chinese font
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial Unicode MS", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False


def build_events():
    """Key IPO-related events, in chronological order."""
    return [
        ("2026-07-02", "KOSPI trading halt: SK Hynix -14.6%, Micron -10%+", "risk"),
        ("2026-07-09", "SEC registration effective; ADR priced at $149", "price"),
        ("2026-07-10", "Nasdaq debut (SKHYV); open $170, high $177, close $168.01 (+12.8%)", "listing"),
        ("2026-07-13", "Ticker switch to regular-way SKHY", "listing"),
        ("2026-07-14", "Offering scheduled to close; $26.5B proceeds locked in", "price"),
    ]


def draw_timeline(events, output_path="ipo-timeline.png"):
    fig, ax = plt.subplots(figsize=(14, 6))

    color_map = {"risk": "#d1495b", "price": "#2e86ab", "listing": "#00a676"}

    y_baseline = 0
    x_positions = list(range(len(events)))

    # Baseline
    ax.axhline(y=y_baseline, color="#333333", linewidth=2, zorder=1)

    for i, (date, desc, kind) in enumerate(events):
        color = color_map[kind]
        # Dot
        ax.scatter([i], [y_baseline], s=200, color=color, zorder=3, edgecolor="white", linewidth=2)
        # Alternating above/below
        y_offset = 0.6 if i % 2 == 0 else -0.6
        va = "bottom" if y_offset > 0 else "top"
        # Date label
        ax.annotate(
            date,
            xy=(i, y_baseline),
            xytext=(i, y_baseline + y_offset * 0.4),
            ha="center",
            va=va,
            fontsize=11,
            fontweight="bold",
            color=color,
        )
        # Description
        ax.annotate(
            desc,
            xy=(i, y_baseline),
            xytext=(i, y_baseline + y_offset),
            ha="center",
            va=va,
            fontsize=9,
            color="#222222",
            wrap=True,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#f5f5f5", edgecolor=color, linewidth=1.2),
        )
        # Connector line
        ax.plot([i, i], [y_baseline, y_baseline + y_offset * 0.35], color=color, linewidth=1.2, linestyle="--")

    # Title & clean up
    ax.set_xlim(-0.7, len(events) - 0.3)
    ax.set_ylim(-1.6, 1.6)
    ax.set_yticks([])
    ax.set_xticks([])
    for spine in ["top", "right", "left", "bottom"]:
        ax.spines[spine].set_visible(False)
    ax.set_title(
        "SK Hynix Nasdaq IPO Timeline (Jul 2026) — 8 days from KOSPI halt to $1.22T market cap",
        fontsize=13,
        fontweight="bold",
        pad=20,
    )

    # Legend
    legend_elements = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=color_map["risk"], markersize=12, label="Market risk event"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=color_map["price"], markersize=12, label="Pricing / proceeds"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=color_map["listing"], markersize=12, label="Listing action"),
    ]
    ax.legend(handles=legend_elements, loc="lower center", ncol=3, frameon=False, fontsize=10, bbox_to_anchor=(0.5, -0.05))

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"[ok] saved -> {output_path}")


if __name__ == "__main__":
    events = build_events()
    draw_timeline(events, output_path="ipo-timeline.png")
