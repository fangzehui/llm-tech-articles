"""mcp_client_matrix.py

MCP 客户端 × 能力兼容性矩阵。

用途：
- 给 CTO / 平台负责人一份「哪个客户端支持什么」的可查询数据结构
- 支持按能力（tools / resources / prompts / sampling / elicitation）反查客户端
- 支持按传输层（stdio / http+sse / streamable_http）反查
- 输出 Markdown 表格，可直接贴进内部技术选型文档

数据基线（截至 2026 年年中，公开来源）：
- Claude Desktop / Claude Code、Cursor、Windsurf、Zed —— 官方或 IDE 原生
- Cline、Continue、Roo Code —— VS Code 扩展
- ChatGPT Developer Mode、Gemini（Code Assist / CLI）、Microsoft 365 Copilot —— 大厂 host

注意：本矩阵是"公开信息 + 常见默认配置"的结构化整理，具体能力以各家最新文档为准。
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Literal

Transport = Literal["stdio", "http+sse", "streamable_http"]
Capability = Literal["tools", "resources", "prompts", "sampling", "elicitation"]


@dataclass(frozen=True)
class MCPClient:
    """一个 MCP 客户端的公开能力画像。"""

    name: str
    vendor: str
    kind: str  # desktop / ide / cli / plugin / chat / enterprise
    native: bool
    transports: frozenset[Transport]
    capabilities: frozenset[Capability]
    config_path: str = ""
    notes: str = ""

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def supports_transport(self, transport: Transport) -> bool:
        return transport in self.transports


CLIENT_MATRIX: tuple[MCPClient, ...] = (
    MCPClient(
        name="Claude Desktop",
        vendor="Anthropic",
        kind="desktop",
        native=True,
        transports=frozenset({"stdio", "streamable_http"}),
        capabilities=frozenset({"tools", "resources", "prompts", "sampling", "elicitation"}),
        config_path="~/Library/Application Support/Claude/claude_desktop_config.json",
        notes="MCP 协议发起方，覆盖度最全。",
    ),
    MCPClient(
        name="Claude Code",
        vendor="Anthropic",
        kind="cli",
        native=True,
        transports=frozenset({"stdio", "streamable_http"}),
        capabilities=frozenset({"tools", "resources", "prompts", "sampling"}),
        notes="面向终端开发的 Claude CLI。",
    ),
    MCPClient(
        name="Cursor",
        vendor="Cursor",
        kind="ide",
        native=True,
        transports=frozenset({"stdio", "http+sse", "streamable_http"}),
        capabilities=frozenset({"tools", "resources", "prompts"}),
        config_path="~/.cursor/mcp.json",
        notes="严格跟随官方规范，兼容度好。",
    ),
    MCPClient(
        name="Windsurf",
        vendor="Codeium",
        kind="ide",
        native=True,
        transports=frozenset({"stdio", "streamable_http"}),
        capabilities=frozenset({"tools", "resources", "prompts"}),
        config_path="~/.codeium/windsurf/mcp_config.json",
        notes="用 serverUrl 而非 url 字段。",
    ),
    MCPClient(
        name="Zed",
        vendor="Zed Industries",
        kind="ide",
        native=True,
        transports=frozenset({"stdio", "streamable_http"}),
        capabilities=frozenset({"tools", "resources"}),
        config_path="~/.config/zed/settings.json",
        notes="配置键名为 context_servers。",
    ),
    MCPClient(
        name="Cline",
        vendor="Community",
        kind="plugin",
        native=False,
        transports=frozenset({"stdio", "streamable_http"}),
        capabilities=frozenset({"tools", "resources", "prompts"}),
        notes="VS Code 扩展，开源、bring-your-own-key。",
    ),
    MCPClient(
        name="Continue",
        vendor="Community",
        kind="plugin",
        native=False,
        transports=frozenset({"stdio"}),
        capabilities=frozenset({"tools", "resources"}),
        notes="VS Code / JetBrains 通用扩展。",
    ),
    MCPClient(
        name="ChatGPT (Developer Mode)",
        vendor="OpenAI",
        kind="chat",
        native=True,
        transports=frozenset({"http+sse", "streamable_http"}),
        capabilities=frozenset({"tools", "resources"}),
        notes="需 Plus/Pro/Business/Enterprise，写工具限企业版。",
    ),
    MCPClient(
        name="Gemini Code Assist",
        vendor="Google",
        kind="ide",
        native=True,
        transports=frozenset({"stdio", "streamable_http"}),
        capabilities=frozenset({"tools", "resources"}),
        config_path="mcp.json（IntelliJ / VS Code）",
    ),
    MCPClient(
        name="Microsoft 365 Copilot",
        vendor="Microsoft",
        kind="enterprise",
        native=True,
        transports=frozenset({"streamable_http"}),
        capabilities=frozenset({"tools", "resources"}),
        notes="2025-12 GA，走 declarative agent。",
    ),
    MCPClient(
        name="Trae CN",
        vendor="ByteDance",
        kind="ide",
        native=True,
        transports=frozenset({"stdio", "streamable_http"}),
        capabilities=frozenset({"tools", "resources", "prompts"}),
        notes="国产 AI IDE，内置支持。",
    ),
)


def find_clients_by_capability(capability: Capability) -> list[MCPClient]:
    return [c for c in CLIENT_MATRIX if c.supports(capability)]


def find_clients_by_transport(transport: Transport) -> list[MCPClient]:
    return [c for c in CLIENT_MATRIX if c.supports_transport(transport)]


def find_clients_by_kind(kind: str) -> list[MCPClient]:
    return [c for c in CLIENT_MATRIX if c.kind == kind]


def render_markdown_table(clients: tuple[MCPClient, ...] | list[MCPClient] = CLIENT_MATRIX) -> str:
    """输出 Markdown 表，便于直接贴进技术方案。"""
    header = (
        "| 客户端 | 厂商 | 类型 | 原生 | 传输 | 能力 | 备注 |\n"
        "|--------|------|------|------|------|------|------|"
    )
    rows = []
    for c in clients:
        rows.append(
            f"| {c.name} | {c.vendor} | {c.kind} | "
            f"{'✅' if c.native else '⚠️'} | "
            f"{', '.join(sorted(c.transports))} | "
            f"{', '.join(sorted(c.capabilities))} | "
            f"{c.notes} |"
        )
    return "\n".join([header, *rows])


def as_json(clients: tuple[MCPClient, ...] | list[MCPClient] = CLIENT_MATRIX) -> str:
    """结构化输出，供其他脚本/前端消费。"""
    return json.dumps(
        [
            {
                "name": c.name,
                "vendor": c.vendor,
                "kind": c.kind,
                "native": c.native,
                "transports": sorted(c.transports),
                "capabilities": sorted(c.capabilities),
                "config_path": c.config_path,
                "notes": c.notes,
            }
            for c in clients
        ],
        ensure_ascii=False,
        indent=2,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MCP client capability matrix")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--capability", default=None, help="按能力筛选")
    parser.add_argument("--transport", default=None, help="按传输筛选")
    parser.add_argument("--kind", default=None, help="按客户端类型筛选")
    args = parser.parse_args(argv)

    clients: list[MCPClient] = list(CLIENT_MATRIX)
    if args.capability:
        clients = [c for c in clients if c.supports(args.capability)]  # type: ignore[arg-type]
    if args.transport:
        clients = [c for c in clients if c.supports_transport(args.transport)]  # type: ignore[arg-type]
    if args.kind:
        clients = [c for c in clients if c.kind == args.kind]

    output = render_markdown_table(clients) if args.format == "markdown" else as_json(clients)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
