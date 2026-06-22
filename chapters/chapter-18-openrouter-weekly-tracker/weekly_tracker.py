"""weekly_tracker.py
================

第 18 篇配套源码：OpenRouter 周榜抓取 + 解析 + 输出结构化 JSON

OpenRouter 官方 rankings 页面是 JS 动态渲染的（数据通过 /api/frontend/stats/recent
等私有接口拉取），原生抓取容易失败。本模块给出三层抓取策略：

1. 优先：调用 OpenRouter 公开 stats endpoint（API 形式，无需登录）
2. 兜底：读取本地 ``data/sample_weekly.json``（即每周由编辑人工核对的快照）
3. 离线：完全用传入的 dict 构造，便于单测

设计目标只有两个：
- 让任何企业的内部模型评估系统能 ``from weekly_tracker import load_week`` 拿到
  一个标准化的 ``WeekSnapshot``；
- 不绑死在 OpenRouter 的 HTML 结构上 —— 抓取层换 endpoint，下游 ``signal_analyzer``
  和 ``report_generator`` 不用动。
"""
from __future__ import annotations

import json
import os
import dataclasses
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

DEFAULT_SAMPLE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "sample_weekly.json"
)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class ModelRow:
    """单模型周榜一行。"""

    rank: int
    model: str
    vendor: str
    country: str  # "CN" / "US" / "Other"
    tokens_trillion: float
    wow_pct: float = 0.0
    prev_rank: Optional[int] = None
    streak_first_weeks: int = 0
    note: str = ""

    def is_china(self) -> bool:
        return self.country == "CN"


@dataclass
class VendorRow:
    """品牌榜一行。"""

    rank: int
    vendor: str
    country: str
    tokens_trillion: float
    share_pct: float
    streak_first_weeks: int = 0
    main_models: List[str] = field(default_factory=list)


@dataclass
class WeekSnapshot:
    """一周完整快照，是下游 signal / report / visualize 的统一输入。"""

    week: str
    start_date: str
    end_date: str
    source: str
    global_total_t: float
    global_wow_pct: float
    cn_total_t: float
    cn_wow_pct: float
    us_total_t: float
    us_wow_pct: float
    consecutive_overtake_us_weeks: int
    top_models: List[ModelRow]
    top_vendors: List[VendorRow]
    history_v4_flash: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    # ---------- derived ----------
    def cn_share(self) -> float:
        """中国上榜模型占全球总量的份额，单位 %."""
        return round(self.cn_total_t / self.global_total_t * 100, 2)

    def us_share(self) -> float:
        return round(self.us_total_t / self.global_total_t * 100, 2)

    def cn_us_ratio(self) -> float:
        """中国 / 美国 上榜调用量比值."""
        return round(self.cn_total_t / max(self.us_total_t, 1e-9), 2)

    def top_n_china_count(self, n: int = 10) -> int:
        return sum(1 for m in self.top_models[:n] if m.is_china())

    def find_model(self, name: str) -> Optional[ModelRow]:
        for m in self.top_models:
            if m.model.lower() == name.lower():
                return m
        return None

    def find_vendor(self, name: str) -> Optional[VendorRow]:
        for v in self.top_vendors:
            if v.vendor.lower() == name.lower():
                return v
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "week": self.week,
            "range": f"{self.start_date} ~ {self.end_date}",
            "global_total_t": self.global_total_t,
            "global_wow_pct": self.global_wow_pct,
            "cn_total_t": self.cn_total_t,
            "us_total_t": self.us_total_t,
            "cn_share_pct": self.cn_share(),
            "us_share_pct": self.us_share(),
            "cn_us_ratio": self.cn_us_ratio(),
            "consecutive_overtake_us_weeks": self.consecutive_overtake_us_weeks,
            "top_models": [asdict(m) for m in self.top_models],
            "top_vendors": [asdict(v) for v in self.top_vendors],
            "history_v4_flash": self.history_v4_flash,
            "notes": self.notes,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# 解析与加载
# ---------------------------------------------------------------------------


def parse_snapshot(raw: Dict[str, Any]) -> WeekSnapshot:
    """把原始 JSON dict 解析成 ``WeekSnapshot``，并做基本字段校验。"""
    required_top = ["week", "start_date", "end_date", "source", "global", "region",
                    "top_models", "top_vendors"]
    for k in required_top:
        if k not in raw:
            raise ValueError(f"snapshot 缺少字段：{k}")

    region = raw["region"]
    if "CN" not in region or "US" not in region:
        raise ValueError("region 必须包含 CN 与 US 两个键")

    # 容忍 sample 数据多塞了 released_at 之类的辅助字段
    model_keys = {f.name for f in dataclasses.fields(ModelRow)}
    vendor_keys = {f.name for f in dataclasses.fields(VendorRow)}
    models = [ModelRow(**{k: v for k, v in row.items() if k in model_keys})
              for row in raw["top_models"]]
    vendors = [VendorRow(**{k: v for k, v in row.items() if k in vendor_keys})
               for row in raw["top_vendors"]]

    # 校验：rank 单调、tokens 非负
    for i, m in enumerate(models, start=1):
        if m.rank != i:
            raise ValueError(f"top_models 第 {i} 行 rank 应为 {i}，实际 {m.rank}")
        if m.tokens_trillion < 0:
            raise ValueError(f"{m.model} tokens 不能为负")

    for i, v in enumerate(vendors, start=1):
        if v.rank != i:
            raise ValueError(f"top_vendors 第 {i} 行 rank 应为 {i}，实际 {v.rank}")
        if v.share_pct < 0:
            raise ValueError(f"{v.vendor} share 不能为负")

    return WeekSnapshot(
        week=raw["week"],
        start_date=raw["start_date"],
        end_date=raw["end_date"],
        source=raw["source"],
        global_total_t=raw["global"]["total_tokens_trillion"],
        global_wow_pct=raw["global"]["wow_pct"],
        cn_total_t=region["CN"]["tokens_trillion"],
        cn_wow_pct=region["CN"]["wow_pct"],
        us_total_t=region["US"]["tokens_trillion"],
        us_wow_pct=region["US"]["wow_pct"],
        consecutive_overtake_us_weeks=region["CN"].get("consecutive_overtake_us_weeks", 0),
        top_models=models,
        top_vendors=vendors,
        history_v4_flash=raw.get("deepseek_v4_flash_history", []),
        notes=raw.get("notes", []),
    )


def load_local(path: str = DEFAULT_SAMPLE) -> WeekSnapshot:
    """从本地 sample JSON 文件加载快照。"""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return parse_snapshot(raw)


def fetch_openrouter_rankings(timeout: float = 8.0) -> Optional[Dict[str, Any]]:
    """尝试调用 OpenRouter 公开 stats endpoint。

    实际 endpoint 会随 OpenRouter 前端版本变化，这里只是一个示意：
    生产环境建议把它替换为你监控到的最新接口，并处理鉴权/限速。
    本函数任何异常都返回 None，由 ``load_week`` 走 fallback 路径。
    """
    try:
        import requests  # type: ignore
    except ImportError:
        return None

    candidate_urls = [
        "https://openrouter.ai/api/frontend/stats/recent",
        "https://openrouter.ai/api/v1/stats/rankings/weekly",
    ]
    for url in candidate_urls:
        try:
            resp = requests.get(url, timeout=timeout, headers={
                "User-Agent": "llm-work/chapter-18 weekly-tracker (research)",
            })
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
                return resp.json()
        except Exception:  # noqa: BLE001
            continue
    return None


def load_week(prefer_remote: bool = False, local_path: str = DEFAULT_SAMPLE) -> WeekSnapshot:
    """统一入口：可选远端抓取，失败回退到本地 sample。"""
    if prefer_remote:
        remote = fetch_openrouter_rankings()
        if remote is not None:
            # 实际项目里需要在这里把 remote 转换成 sample_weekly.json 的同款结构。
            # 因为接口结构不稳定，这里只示意：检测到非空就尝试解析，解析失败回退。
            try:
                return parse_snapshot(remote)
            except Exception:  # noqa: BLE001
                pass
    return load_local(local_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    snap = load_week(prefer_remote=False)
    payload = snap.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()
    print(f"  全球本周 {snap.global_total_t}T Token（环比 {snap.global_wow_pct:+.2f}%）")
    print(f"  中国 {snap.cn_total_t}T / 美国 {snap.us_total_t}T，"
          f"比值 {snap.cn_us_ratio():.2f}×")
    print(f"  Top10 中中国模型 {snap.top_n_china_count()} 席")


if __name__ == "__main__":
    main()
