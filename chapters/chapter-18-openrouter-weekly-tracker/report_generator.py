"""report_generator.py
===================

第 18 篇配套源码：基于抓取数据生成 Markdown 周报。

支持两种输出模式：
- ``brief()``   ：200 字极简版，用于企业内部 Slack/飞书推送
- ``full()``    ：结构化 Markdown 版，完整覆盖正文 §一数据全景的表格内容

使用方式::

    from report_generator import full, brief
    from weekly_tracker import load_week

    snap = load_week()
    print(full(snap))
    print(brief(snap))
"""
from __future__ import annotations

from datetime import date
from typing import List

from weekly_tracker import ModelRow, WeekSnapshot


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _pct(v: float, sign: bool = True) -> str:
    prefix = "+" if sign and v > 0 else ""
    return f"{prefix}{v:.1f}%"


def _tok(t: float) -> str:
    if t >= 1:
        return f"{t:.2f}T"
    return f"{t * 1000:.0f}B"


def _streak(n: int) -> str:
    if n <= 1:
        return ""
    return f"（连续{n}周）"


def _delta_arrow(pct: float) -> str:
    if pct > 0:
        return "▲"
    if pct < 0:
        return "▼"
    return "─"


# ---------------------------------------------------------------------------
# 模型表格
# ---------------------------------------------------------------------------


def _model_table_header() -> str:
    return (
        "| 排名 | 模型 | 厂商 | 国别 | 周调用量 | 环比 | 备注 |\n"
        "|---:|---|---|---|---:|---:|---|\n"
    )


def _model_table_row(m: ModelRow) -> str:
    flag = "🇨🇳" if m.is_china() else "🇺🇸"
    delta = f"{_delta_arrow(m.wow_pct)}{_pct(abs(m.wow_pct), sign=False)}"
    note = m.note or ""
    return (
        f"| {m.rank} | {m.model} | {m.vendor} | {flag} "
        f"| {m.tokens_trillion:.2f}T | {delta} | {note} |\n"
    )


def _vendor_table_header() -> str:
    return (
        "| 排名 | 品牌 | 国别 | 周调用量 | 市场份额 | 备注 |\n"
        "|---:|---|---|---:|---:|---|\n"
    )


def _vendor_table(vendors: List, snapshot: WeekSnapshot) -> str:
    lines = [_vendor_table_header()]
    for v in vendors:
        flag = "🇨🇳" if v.country == "CN" else "🇺🇸"
        streak = _streak(v.streak_first_weeks) if v.streak_first_weeks > 0 else ""
        models_str = ", ".join(v.main_models) if v.main_models else ""
        note = f"{models_str} {streak}".strip()
        lines.append(
            f"| {v.rank} | {v.vendor} | {flag} | "
            f"{v.tokens_trillion:.2f}T | {v.share_pct:.1f}% | {note} |\n"
        )
    return "".join(lines)


# ---------------------------------------------------------------------------
# DeepSeek-V4-Flash 历史趋势表格
# ---------------------------------------------------------------------------


def _v4_flash_history(history: List[dict]) -> str:
    if not history:
        return ""
    rows = ["| 周次 | 统计起始日 | 周调用量 | 环比 | 备注 |\n|---:|---|---|---:|---|\n"]
    for h in history:
        delta = f"{_delta_arrow(h['wow_pct'])}{_pct(abs(h['wow_pct']), sign=False)}"
        note = h.get("note", "")
        rows.append(
            f"| {h['week']} | {h['start_date']} | "
            f"{h['tokens_trillion']:.2f}T | {delta} | {note} |\n"
        )
    return "".join(rows)


# ---------------------------------------------------------------------------
# 全量周报
# ---------------------------------------------------------------------------


def full(snap: WeekSnapshot) -> str:
    today = date.today().isoformat()
    lines: List[str] = []

    lines.append(f"# OpenRouter 周榜快照\n\n**统计周期**：{snap.start_date} ~ {snap.end_date}\n")
    lines.append(f"**生成时间**：{today} · **数据来源**：{snap.source}\n\n")

    # ── 一、宏观数据 ──
    lines.append("## 一、宏观数据\n\n")
    lines.append(
        f"- **全球周调用总量**：{snap.global_total_t} 万亿 Token"
        f"，环比 {_pct(snap.global_wow_pct)}，"
        f"连续 {snap.global_wow_pct} 周上涨\n"
    )
    lines.append(
        f"- **中国上榜模型**：{snap.cn_total_t} 万亿 Token"
        f"，环比 {_pct(snap.cn_wow_pct)}，"
        f"{_streak(snap.consecutive_overtake_us_weeks)}超越美国\n"
    )
    lines.append(
        f"- **美国上榜模型**：{snap.us_total_t} 万亿 Token"
        f"，环比 {_pct(snap.us_wow_pct)}\n"
    )
    lines.append(
        f"- **中国 / 美国比值**：{snap.cn_us_ratio():.2f}×"
        f"（中国占全球 {snap.cn_share():.1f}%）\n"
    )
    lines.append("\n")

    # ── 二、单模型 Top10 ──
    lines.append("## 二、单模型 Top 10\n\n")
    lines.append(_model_table_header())
    for m in snap.top_models:
        lines.append(_model_table_row(m))
    lines.append("\n")

    # ── 三、品牌 Top10 ──
    lines.append("## 三、品牌 Top 10\n\n")
    lines.append(_vendor_table(snap.top_vendors, snap))
    lines.append("\n")

    # ── 四、DeepSeek-V4-Flash 五连冠趋势 ──
    lines.append("## 四、DeepSeek-V4-Flash 调用量趋势（近 6 周）\n\n")
    lines.append(_v4_flash_history(snap.history_v4_flash))
    lines.append("\n")

    # ── 五、附注 ──
    if snap.notes:
        lines.append("## 五、附注\n\n")
        for n in snap.notes:
            lines.append(f"- {n}\n")
        lines.append("\n")

    lines.append(
        "---\n\n"
        "*本报告由 [chapter-18-openrouter-weekly-tracker]"
        "(https://github.com/LDZKKJ/llm-work/tree/main/chapters/chapter-18-openrouter-weekly-tracker) "
        "自动生成，数据仅供参考，不构成选型建议。*\n"
    )
    return "".join(lines)


def brief(snap: WeekSnapshot) -> str:
    top = snap.top_models[0]
    top2 = snap.top_models[1]
    return (
        f"[{snap.start_date}~{snap.end_date}] "
        f"全球{snap.global_total_t}万亿Token({_pct(snap.global_wow_pct)}) · "
        f"🇨🇳{snap.cn_total_t}T · 🇺🇸{snap.us_total_t}T · "
        f"榜首{top.model}({top.tokens_trillion:.2f}T {_pct(top.wow_pct)}) · "
        f"第2{top2.model}({top2.tokens_trillion:.2f}T)\n"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    from weekly_tracker import load_week

    snap = load_week()
    print("=== FULL REPORT ===")
    print(full(snap))
    print("=== BRIEF ===")
    print(brief(snap))


if __name__ == "__main__":
    main()
