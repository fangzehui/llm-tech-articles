"""price_timeline.py

国产大模型 24 个月价格战关键节点（2024-05 至 2026-06）。

数据来源：新华网 / 新华社经济参考报 / 每日经济新闻 / 36 氪 / 腾讯新闻 / 证券时报 /
Forbes China / 各家官方定价页与技术博客。截至 2026-07-08 快照。

配套第 26 篇《国产大模型价格战复盘 2024-2026》第二节使用。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal

Wave = Literal["wave1", "wave2", "wave3", "convergence", "post"]


@dataclass(frozen=True)
class PriceEvent:
    """一次价格调整事件。"""

    date: str            # ISO 日期字符串
    vendor: str          # 厂商简称
    model: str           # 模型 SKU
    change: str          # 变化描述（含旧价 → 新价）
    wave: Wave           # 归属冲击波
    source_url: str      # 来源链接
    source_title: str    # 来源标题


TIMELINE: tuple[PriceEvent, ...] = (
    PriceEvent(
        date="2024-05-11",
        vendor="Zhipu",
        model="GLM-3 Turbo",
        change="0.005 元/千tokens → 0.001 元/千tokens（降 80%）",
        wave="wave1",
        source_url="https://www.forbeschina.com/innovation/67924",
        source_title="Forbes China: 百模大战杀疯了",
    ),
    PriceEvent(
        date="2024-05-15",
        vendor="ByteDance",
        model="Doubao pro-32k",
        change="首发定价：输入 0.0008 元/千tokens、输出 0.002 元/千tokens",
        wave="wave1",
        source_url="http://www1.xinhuanet.com/tech/20240515/0cbd896c16e14a398c26f4195a360410/c.html",
        source_title="新华网: 字节跳动发布豆包大模型",
    ),
    PriceEvent(
        date="2024-05-21",
        vendor="Alibaba",
        model="Qwen-Long",
        change="输入 0.02 → 0.0005 元/千tokens（降 97%）",
        wave="wave1",
        source_url="http://www.jjckb.cn/2024-05/21/c_1310775525.htm",
        source_title="经济参考报: 通义千问 GPT-4 级主力模型降价 97%",
    ),
    PriceEvent(
        date="2024-05-21",
        vendor="Alibaba",
        model="Qwen-Max",
        change="输入 0.12 → 0.04 元/千tokens（降 67%）",
        wave="wave1",
        source_url="http://www.jjckb.cn/2024-05/21/c_1310775525.htm",
        source_title="经济参考报: 通义千问 GPT-4 级主力模型降价 97%",
    ),
    PriceEvent(
        date="2024-05-21",
        vendor="Baidu",
        model="ERNIE Speed / ERNIE Lite",
        change="全面免费（含 8K / 128K）",
        wave="wave1",
        source_url="https://m.36kr.com/p/2785589121451142",
        source_title="36 氪: 祭出免费大旗百度卷入价格混战",
    ),
    PriceEvent(
        date="2024-05-22",
        vendor="Tencent",
        model="Hunyuan-lite",
        change="0.008 元/千tokens → 免费，上下文 4K → 256K",
        wave="wave1",
        source_url="https://cloud.tencent.com/developer/article/2419914",
        source_title="腾讯云: 混元大模型全面降价 lite 即日起免费",
    ),
    PriceEvent(
        date="2024-05-22",
        vendor="Tencent",
        model="Hunyuan-standard",
        change="输入 0.01 → 0.0045 元/千tokens",
        wave="wave1",
        source_url="https://cloud.tencent.com/developer/article/2419914",
        source_title="腾讯云: 混元大模型全面降价 lite 即日起免费",
    ),
    PriceEvent(
        date="2024-05-22",
        vendor="iFlytek",
        model="Spark Lite",
        change="免费",
        wave="wave1",
        source_url="https://m.bjnews.com.cn/detail/1716542831129290.html",
        source_title="新京报: 17 天跌进免费时代",
    ),
    PriceEvent(
        date="2024-06-05",
        vendor="Zhipu",
        model="GLM-4-Flash",
        change="纳入 API 家族：0.1 元/百万 tokens",
        wave="wave2",
        source_url="https://news.qq.com/rain/a/20240605A08K1K00",
        source_title="腾讯新闻: 智谱大模型宣布再降价",
    ),
    PriceEvent(
        date="2024-07-01",
        vendor="Moonshot",
        model="Kimi Context Caching",
        change="公测：24 元/M 创建 + 10 元/M/分 存储 + 0.02 元/次调用",
        wave="wave2",
        source_url="https://platform.moonshot.cn/blog/posts/context-caching",
        source_title="Moonshot 官博: Context Caching 正式公测",
    ),
    PriceEvent(
        date="2024-08-07",
        vendor="Moonshot",
        model="Kimi Context Caching",
        change="存储费降 50%：10 元/M/分 → 5 元/M/分",
        wave="wave2",
        source_url="https://www.36kr.com/newsflashes/2895627467037572",
        source_title="36 氪: Kimi Cache 存储费降价 50%",
    ),
    PriceEvent(
        date="2024-12-26",
        vendor="DeepSeek",
        model="DeepSeek V3",
        change="发布 671B MoE，激活 37B，全模型开源",
        wave="wave3",
        source_url="https://api-docs.deepseek.com/quick_start/pricing",
        source_title="DeepSeek 官网: V3 定价与说明",
    ),
    PriceEvent(
        date="2025-01-20",
        vendor="DeepSeek",
        model="DeepSeek R1",
        change="发布：推理成本约为 OpenAI o1 的 3%",
        wave="wave3",
        source_url="https://api-docs.deepseek.com/quick_start/pricing",
        source_title="DeepSeek 官网: R1 定价与说明",
    ),
    PriceEvent(
        date="2025-02-26",
        vendor="DeepSeek",
        model="DeepSeek V3 / R1",
        change="错峰优惠：00:30-08:30 时段，V3 五折、R1 二五折",
        wave="wave3",
        source_url="https://www.stcn.com/article/detail/1548559.html",
        source_title="证券时报: DeepSeek 最高降价 75%",
    ),
    PriceEvent(
        date="2026-05-01",
        vendor="DeepSeek",
        model="DeepSeek V3.2",
        change="输出价格 0.56 → 0.42 美金/M，缓存命中折扣 90%",
        wave="post",
        source_url="https://deepseak.org/deepseek-pricing/",
        source_title="deepseak.org: DeepSeek 定价复盘 2026",
    ),
)


def events_by_wave(wave: Wave) -> tuple[PriceEvent, ...]:
    """按冲击波筛选事件。"""
    return tuple(e for e in TIMELINE if e.wave == wave)


def events_by_vendor(vendor: str) -> tuple[PriceEvent, ...]:
    """按厂商筛选事件（大小写不敏感）。"""
    v = vendor.lower()
    return tuple(e for e in TIMELINE if e.vendor.lower() == v)


def export_json(path: str | Path) -> None:
    """导出全量时间线到 JSON 文件。"""
    data = [asdict(e) for e in TIMELINE]
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def render_markdown_table() -> str:
    """渲染时间线为 Markdown 表格。"""
    lines = [
        "| 日期 | 厂商 | 模型 | 变化 |",
        "|---|---|---|---|",
    ]
    for e in TIMELINE:
        lines.append(f"| {e.date} | {e.vendor} | {e.model} | {e.change} |")
    return "\n".join(lines)


def main() -> None:
    print(f"共 {len(TIMELINE)} 条价格战关键节点\n")
    for wave in ("wave1", "wave2", "wave3", "post"):
        count = len(events_by_wave(wave))  # type: ignore[arg-type]
        print(f"  {wave}: {count} 条")


if __name__ == "__main__":
    main()
