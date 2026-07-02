"""mcp_registry_scanner.py

MCP 官方 Registry 快照扫描器。

用途：
- 支持从官方 Registry snapshot（JSON 数组）扫描 Server 元信息
- 按命名空间/关键词/更新时间过滤
- 按四大类别（devtool / database / saas / cloud）自动打标
- 输出 Top-N 报告与 CSV

设计特点：
- 不依赖网络：默认从 data/registry_snapshot.json 读取内置样本
- 可选 --url 从任意兼容 Registry API 抓取（未开网时会返回空并给出提示）
- 纯标准库 + typing，方便 CI 冒烟

文章参考：
《MCP 生态 12 个月观察：从协议诞生到企业接入指南》第三节"生态全景"。
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

DEFAULT_SNAPSHOT = Path(__file__).with_name("data") / "registry_snapshot.json"

# 分类关键词表——公开 Registry 上常见的命名前缀/名称片段
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "devtool": (
        "github", "gitlab", "jira", "linear", "sourcegraph", "sentry",
        "vercel", "code", "wiki", "figma", "zed",
    ),
    "database": (
        "postgres", "mysql", "sqlite", "clickhouse", "snowflake",
        "supabase", "mongo", "redis", "maxcompute", "bigquery", "spanner",
    ),
    "saas": (
        "slack", "notion", "hubspot", "stripe", "shopify", "twilio",
        "salesforce", "airtable", "asana", "zendesk",
    ),
    "cloud": (
        "aws", "azure", "gcp", "cloudflare", "aliyun", "tencent",
        "qianfan", "cloudrun", "s3", "workspace",
    ),
}


@dataclass
class MCPServer:
    """MCP Server 元数据的最小可用视图。"""

    namespace: str
    name: str
    version: str = "0.0.0"
    description: str = ""
    updated_at: str = ""
    category: str = "other"
    tags: list[str] = field(default_factory=list)

    @property
    def full_id(self) -> str:
        return f"{self.namespace}/{self.name}"

    def to_dict(self) -> dict:
        return {
            "namespace": self.namespace,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "updated_at": self.updated_at,
            "category": self.category,
            "tags": list(self.tags),
        }


def classify(name: str, description: str = "") -> str:
    """按关键词把一个 server 打到 4 大类别里，未命中归 'other'。"""
    haystack = f"{name} {description}".lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            return category
    return "other"


def load_snapshot(source: str | Path | None = None) -> list[dict]:
    """加载 Registry 快照 JSON。"""
    path = Path(source) if source else DEFAULT_SNAPSHOT
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        return data.get("servers", [])
    return list(data)


def parse_servers(raw: Iterable[dict]) -> list[MCPServer]:
    """把 Registry JSON 记录标准化为 MCPServer。"""
    result: list[MCPServer] = []
    for item in raw:
        # 兼容 "com.foo/bar" 或 {namespace, name}
        identifier = item.get("id") or item.get("name") or ""
        if "/" in identifier:
            namespace, name = identifier.split("/", 1)
        else:
            namespace = item.get("namespace", "unknown")
            name = identifier or "unnamed"
        description = item.get("description", "") or ""
        server = MCPServer(
            namespace=namespace,
            name=name,
            version=item.get("version", "0.0.0"),
            description=description,
            updated_at=item.get("updated_at", ""),
            tags=list(item.get("tags", [])),
        )
        server.category = classify(name, description)
        result.append(server)
    return result


def filter_servers(
    servers: list[MCPServer],
    *,
    category: str | None = None,
    keyword: str | None = None,
    since: str | None = None,
) -> list[MCPServer]:
    """按类别/关键词/更新时间过滤。since 用 ISO 日期字符串。"""

    def match(server: MCPServer) -> bool:
        if category and server.category != category:
            return False
        if keyword:
            kw = keyword.lower()
            if kw not in server.name.lower() and kw not in server.description.lower():
                return False
        if since and server.updated_at:
            try:
                dt = datetime.fromisoformat(server.updated_at.replace("Z", "+00:00"))
                cutoff = datetime.fromisoformat(since)
                if dt < cutoff:
                    return False
            except ValueError:
                # 日期解析失败时不做过滤（保持宽容）
                return True
        return True

    return [s for s in servers if match(s)]


def category_stats(servers: list[MCPServer]) -> dict[str, int]:
    """按四大类别（+ other）统计数量。"""
    counter: Counter[str] = Counter(s.category for s in servers)
    baseline = dict.fromkeys(list(CATEGORY_KEYWORDS.keys()) + ["other"], 0)
    baseline.update(counter)
    return baseline


def top_publishers(servers: list[MCPServer], top_n: int = 5) -> list[tuple[str, int]]:
    """TopN 发布者（按 namespace 出现次数）。"""
    counter = Counter(s.namespace for s in servers)
    return counter.most_common(top_n)


def export_csv(servers: list[MCPServer], out: str | Path) -> Path:
    """把过滤后的 server 列表输出为 CSV，方便贴到内部审计表。"""
    path = Path(out)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["namespace", "name", "version", "category", "updated_at", "description"],
        )
        writer.writeheader()
        for s in servers:
            writer.writerow(
                {
                    "namespace": s.namespace,
                    "name": s.name,
                    "version": s.version,
                    "category": s.category,
                    "updated_at": s.updated_at,
                    "description": s.description[:80],
                }
            )
    return path


def render_report(servers: list[MCPServer]) -> str:
    """生成人类可读的扫描报告。"""
    stats = category_stats(servers)
    publishers = top_publishers(servers)
    total = len(servers)
    lines = [
        "MCP Registry Snapshot Report",
        "-" * 40,
        f"Total servers scanned : {total}",
        "Category distribution :",
    ]
    for name, count in stats.items():
        pct = (count / total * 100) if total else 0
        lines.append(f"  - {name:<9}: {count:>4} ({pct:5.1f}%)")
    lines.append("Top publishers        :")
    for ns, count in publishers:
        lines.append(f"  - {ns:<25}: {count}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MCP Registry snapshot scanner")
    parser.add_argument("--source", default=None, help="Registry JSON 文件路径")
    parser.add_argument("--category", default=None, choices=list(CATEGORY_KEYWORDS.keys()))
    parser.add_argument("--keyword", default=None)
    parser.add_argument("--since", default=None, help="ISO 日期，如 2026-01-01")
    parser.add_argument("--csv", default=None, help="导出 CSV 文件路径")
    args = parser.parse_args(argv)

    raw = load_snapshot(args.source)
    servers = parse_servers(raw)
    filtered = filter_servers(
        servers, category=args.category, keyword=args.keyword, since=args.since
    )
    print(render_report(filtered))
    if args.csv:
        out_path = export_csv(filtered, args.csv)
        print(f"\nCSV exported → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
