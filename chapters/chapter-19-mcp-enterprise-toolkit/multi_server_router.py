"""多 Server 路由：解决 tool name / resource URI 撞名。

设计思路
========
1. 每个上游 MCP Server 注册时绑定一个 **namespace**（如 ``github``、``jira``）。
2. Client 暴露给 Host 的 tool name 永远是 ``"{namespace}.{tool}"`` 形式。
3. 反向解析时根据第一个 ``.`` 前缀路由到对应的 upstream。
4. 注册期检测同 namespace 内部 tool 撞名；外层不同 namespace 撞名通过前缀自动隔离。
5. resource URI 用 scheme 隔离（``upstream://{namespace}/...``）。
6. prompt 优先级用 ``priority`` 字段，数字越小越优先；撞名时按优先级返回。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_VALID_NS = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class RouterError(Exception):
    """路由层错误的统一基类。"""


class NamespaceCollision(RouterError):
    """namespace 撞名。"""


class ToolCollision(RouterError):
    """同 namespace 内 tool 撞名。"""


class UnknownTool(RouterError):
    """请求的 tool 在路由表中找不到。"""


@dataclass
class UpstreamServer:
    """一台被聚合的上游 MCP Server。"""

    namespace: str
    endpoint: str  # 远端 Streamable HTTP URL 或本地 stdio 标识
    transport: str = "streamable_http"  # "streamable_http" / "stdio"
    protocol_version: str = "2025-11-25"
    tools: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)
    weight: int = 100  # 同 namespace 多副本时用于负载均衡

    def __post_init__(self) -> None:
        if not _VALID_NS.match(self.namespace):
            raise ValueError(
                f"非法 namespace {self.namespace!r}，必须匹配 {_VALID_NS.pattern}"
            )
        if self.transport not in {"streamable_http", "stdio"}:
            raise ValueError(f"未知 transport：{self.transport}")


class MultiServerRouter:
    """聚合多台 MCP Server 的路由器。

    用法::

        router = MultiServerRouter()
        router.register(UpstreamServer("github", "https://github.example/mcp",
                                       tools=["create_issue", "list_repos"]))
        router.register(UpstreamServer("jira",   "https://jira.example/mcp",
                                       tools=["create_issue"]))

        # ← github.create_issue 与 jira.create_issue 在前缀下天然隔离
        ns, tool = router.resolve_tool("github.create_issue")
        assert ns == "github" and tool == "create_issue"
    """

    def __init__(self) -> None:
        self._servers: dict[str, UpstreamServer] = {}
        # prompt name -> [(priority, namespace)] 取最小 priority 的命中
        self._prompt_index: dict[str, list[tuple[int, str]]] = {}

    # ----------------------- 注册 / 注销 -----------------------
    def register(self, server: UpstreamServer) -> None:
        if server.namespace in self._servers:
            raise NamespaceCollision(
                f"namespace {server.namespace!r} 已存在；如要替换请先 unregister"
            )
        # 同 namespace 内部 tool 撞名兜底
        if len(set(server.tools)) != len(server.tools):
            dup = [t for t in server.tools if server.tools.count(t) > 1]
            raise ToolCollision(f"{server.namespace} 内部 tool 撞名：{set(dup)}")
        self._servers[server.namespace] = server
        for p in server.prompts:
            self._prompt_index.setdefault(p["name"], []).append(
                (p.get("priority", 100), server.namespace)
            )

    def unregister(self, namespace: str) -> None:
        self._servers.pop(namespace, None)
        for name, lst in list(self._prompt_index.items()):
            new = [(p, n) for (p, n) in lst if n != namespace]
            if new:
                self._prompt_index[name] = new
            else:
                self._prompt_index.pop(name, None)

    # ----------------------- 查询 -----------------------
    def list_namespaces(self) -> list[str]:
        return sorted(self._servers.keys())

    def list_qualified_tools(self) -> list[str]:
        out: list[str] = []
        for ns, srv in self._servers.items():
            out.extend(f"{ns}.{t}" for t in srv.tools)
        return sorted(out)

    def resolve_tool(self, qualified_name: str) -> tuple[str, str]:
        """``"github.create_issue"`` → ``("github", "create_issue")``."""
        if "." not in qualified_name:
            raise UnknownTool(
                f"工具名 {qualified_name!r} 未带 namespace 前缀；"
                "MCP Gateway 强制要求 ``{namespace}.{tool}`` 形式"
            )
        ns, _, tool = qualified_name.partition(".")
        if ns not in self._servers:
            raise UnknownTool(f"未注册的 namespace：{ns}")
        if tool not in self._servers[ns].tools:
            raise UnknownTool(f"namespace={ns} 下不存在 tool={tool}")
        return ns, tool

    def resolve_resource(self, uri: str) -> tuple[str, str]:
        """``upstream://github/issues/1`` → ``("github", "issues/1")``."""
        prefix = "upstream://"
        if not uri.startswith(prefix):
            raise UnknownTool(
                f"resource URI {uri!r} 未带 ``upstream://`` scheme；"
                "MCP Gateway 用 scheme 隔离不同上游"
            )
        path = uri[len(prefix):]
        ns, _, sub = path.partition("/")
        if ns not in self._servers:
            raise UnknownTool(f"未注册的 namespace：{ns}")
        return ns, sub

    def resolve_prompt(self, name: str) -> str:
        """prompt 撞名时按 priority 最小者命中。"""
        candidates = self._prompt_index.get(name, [])
        if not candidates:
            raise UnknownTool(f"prompt 未注册：{name}")
        # min by (priority asc, namespace asc) 让结果可重复
        _, ns = min(candidates, key=lambda x: (x[0], x[1]))
        return ns

    # ----------------------- 协议版本协商 -----------------------
    @staticmethod
    def negotiate_protocol_version(
        host_supports: list[str], server_supports: list[str]
    ) -> str:
        """挑选 host / server 都支持的最新版本。

        约定：版本号字符串按字典序倒序近似时间序（``2025-11-25 > 2025-06-18``）。
        若无交集，按 MCP 规范回退到最低共通版本 ``2024-11-05``。
        """
        common = sorted(set(host_supports) & set(server_supports), reverse=True)
        if not common:
            return "2024-11-05"
        return common[0]


__all__ = [
    "MultiServerRouter",
    "UpstreamServer",
    "RouterError",
    "NamespaceCollision",
    "ToolCollision",
    "UnknownTool",
]
