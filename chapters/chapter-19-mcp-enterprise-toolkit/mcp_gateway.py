"""企业 MCP Gateway 主程序（FastAPI 实现）。

设计目标
========
- **单一入口聚合多个上游 MCP Server**，对外暴露统一 Streamable HTTP；
- 强制 OAuth 2.1 + Resource Indicator，PKCE 由 IdP 完成；
- 内置令牌桶 + 日配额限流；
- W3C Trace Context 跨 JSON-RPC 边界注入；
- 支持协议版本协商（2024-11-05 / 2025-03-26 / 2025-06-18 / 2025-11-25）。

为什么是 FastAPI？
- Streamable HTTP 本质是 ``POST + SSE``，FastAPI 的 ``StreamingResponse`` 天生匹配；
- 中间件链清晰、依赖注入对单测友好；
- 与企业现有的 K8s ingress / Service Mesh 集成无障碍。

⚠️ 本文件**仅供工程参考**。生产部署时：
- ``UPSTREAM_REGISTRY`` 应从 ConfigMap 装载；
- OAuth secret 应来自 HashiCorp Vault / K8s Secret 而非环境变量；
- 上游 HTTP 调用应使用 ``httpx.AsyncClient(timeout=...)`` + 重试策略。

如果 ``fastapi`` 没装，文件依然可以 import：所有路由代码会被守卫挂到
``HAS_FASTAPI=False`` 分支，单测只测路由器 / 限流 / OAuth 等纯逻辑。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from multi_server_router import (
    MultiServerRouter,
    RouterError,
    UpstreamServer,
)
from oauth_middleware import (
    OAuthConfig,
    OAuthError,
    build_protected_resource_metadata,
    verify_access_token,
)
from observability import (
    ATTR_MCP_ERROR_CODE,
    diagnose_from_spans,
    get_tracer,
    instrument_mcp_call,
)
from rate_limiter import RateLimiter, RateLimitError


try:
    from fastapi import FastAPI, Header, HTTPException, Request
    from fastapi.responses import JSONResponse

    HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    HAS_FASTAPI = False


# --------------------- Gateway 核心（纯逻辑，可单测）---------------------


SUPPORTED_PROTOCOL_VERSIONS = [
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
]


@dataclass
class GatewayConfig:
    oauth: OAuthConfig
    rate_limiter: RateLimiter
    router: MultiServerRouter
    default_protocol_version: str = "2025-11-25"


class MCPGateway:
    """对外暴露 ``handle()`` —— 给定 raw JSON-RPC 请求 + auth header，
    返回 (status_code, body_json)。FastAPI 路由层只是它的薄包装。"""

    def __init__(self, config: GatewayConfig) -> None:
        self.config = config

    # ------------- 主分派 -------------
    def handle(
        self,
        body: dict[str, Any],
        *,
        authorization: str | None,
        tenant: str | None = None,
        traceparent: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        method = body.get("method")
        req_id = body.get("id")
        if not method:
            return 400, _error(req_id, -32600, "Invalid Request: missing method")

        # 1) initialize 是握手，单独走，且**不要求 token**
        if method == "initialize":
            return self._handle_initialize(body, traceparent=traceparent)

        # 2) 其余方法都强制 OAuth
        try:
            payload = verify_access_token(
                authorization or "",
                self.config.oauth,
                required_scope="mcp.tools" if "tools" in method else None,
            )
        except OAuthError as e:
            return e.status_code, _error(
                req_id, -32001, f"OAuth 校验失败: {e.error_code}: {e}"
            )

        user = payload.get("sub", "anonymous")
        tenant = tenant or payload.get("tenant") or "default"

        # 3) tools/call → 限流 + 路由 + 转发
        if method == "tools/call":
            return self._handle_tools_call(
                body, tenant=tenant, user=user, traceparent=traceparent
            )

        if method == "tools/list":
            return self._handle_tools_list(body, traceparent=traceparent)

        if method == "resources/read":
            return self._handle_resources_read(
                body, tenant=tenant, user=user, traceparent=traceparent
            )

        if method == "ping":
            return 200, {"jsonrpc": "2.0", "id": req_id, "result": {}}

        return 400, _error(req_id, -32601, f"Method not found: {method}")

    # ------------- initialize -------------
    def _handle_initialize(
        self, body: dict[str, Any], *, traceparent: str | None
    ) -> tuple[int, dict[str, Any]]:
        params = body.get("params") or {}
        host_versions = [
            params.get("protocolVersion") or self.config.default_protocol_version
        ]
        chosen = self.config.router.negotiate_protocol_version(
            host_versions, SUPPORTED_PROTOCOL_VERSIONS
        )
        with instrument_mcp_call(
            method="initialize",
            protocol_version=chosen,
            traceparent=traceparent,
        ):
            result = {
                "protocolVersion": chosen,
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"listChanged": True},
                    "prompts": {},
                    "elicitation": {"form": {}, "url": {}},
                },
                "serverInfo": {
                    "name": "enterprise-mcp-gateway",
                    "version": "0.19.0",
                },
            }
            return 200, {"jsonrpc": "2.0", "id": body.get("id"), "result": result}

    # ------------- tools/list -------------
    def _handle_tools_list(
        self, body: dict[str, Any], *, traceparent: str | None
    ) -> tuple[int, dict[str, Any]]:
        with instrument_mcp_call(method="tools/list", traceparent=traceparent):
            tools = [
                {"name": q, "description": f"aggregated tool {q}"}
                for q in self.config.router.list_qualified_tools()
            ]
            return 200, {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {"tools": tools},
            }

    # ------------- tools/call -------------
    def _handle_tools_call(
        self,
        body: dict[str, Any],
        *,
        tenant: str,
        user: str,
        traceparent: str | None,
    ) -> tuple[int, dict[str, Any]]:
        params = body.get("params") or {}
        qualified = params.get("name") or ""
        try:
            ns, tool = self.config.router.resolve_tool(qualified)
        except RouterError as e:
            return 400, _error(body.get("id"), -32602, f"tool resolve 失败: {e}")

        # 限流
        try:
            self.config.rate_limiter.check(
                {"tenant": tenant, "user": user, "tool": qualified}
            )
        except RateLimitError as e:
            return 429, _error(
                body.get("id"),
                -32011,
                f"rate limited: {e.reason}; retry_after={e.retry_after:.1f}s",
            )

        # 真正的转发省略：本仓库给的是 reference，
        # 生产代码替换为 ``await httpx_client.post(upstream.endpoint, json=...)``
        with instrument_mcp_call(
            method="tools/call",
            namespace=ns,
            tool=tool,
            tenant=tenant,
            user=user,
            traceparent=traceparent,
        ) as span:
            try:
                result = self._mock_upstream_invoke(ns, tool, params.get("arguments"))
            except Exception as exc:  # noqa: BLE001
                span.set_attribute(ATTR_MCP_ERROR_CODE, "upstream_error")
                # 显式标记 span 为 error 状态，配合 diagnose_from_spans 使用
                span.set_status("error", f"upstream_error: {exc}")
                from observability import ATTR_MCP_STATUS
                span.set_attribute(ATTR_MCP_STATUS, "error")
                return 502, _error(body.get("id"), -32010, f"upstream error: {exc}")
        return 200, {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {"content": [{"type": "text", "text": json.dumps(result)}]},
        }

    # ------------- resources/read -------------
    def _handle_resources_read(
        self,
        body: dict[str, Any],
        *,
        tenant: str,
        user: str,
        traceparent: str | None,
    ) -> tuple[int, dict[str, Any]]:
        params = body.get("params") or {}
        uri = params.get("uri") or ""
        try:
            ns, sub = self.config.router.resolve_resource(uri)
        except RouterError as e:
            return 400, _error(body.get("id"), -32602, f"resource resolve 失败: {e}")
        with instrument_mcp_call(
            method="resources/read",
            namespace=ns,
            tenant=tenant,
            user=user,
            traceparent=traceparent,
        ):
            data = {"uri": uri, "namespace": ns, "path": sub, "content": "<stub>"}
            return 200, {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {"contents": [data]},
            }

    # ------------- mock 上游（仅供单测）-------------
    def _mock_upstream_invoke(
        self, namespace: str, tool: str, arguments: dict[str, Any] | None
    ) -> dict[str, Any]:
        if tool == "boom":
            raise RuntimeError("simulated upstream failure")
        return {
            "namespace": namespace,
            "tool": tool,
            "echo": arguments or {},
            "ts": int(time.time()),
            "trace_id": uuid.uuid4().hex[:16],
        }


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }


# --------------------- FastAPI 路由薄包装 ---------------------


def build_app(gateway: MCPGateway):  # noqa: ANN201
    """构造 FastAPI app；仅在 fastapi 已安装时可用。"""
    if not HAS_FASTAPI:
        raise RuntimeError("fastapi 未安装，请 `pip install -r requirements.txt`")

    app = FastAPI(title="Enterprise MCP Gateway", version="0.19.0")

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"status": "ok", "version": "0.19.0"}

    @app.get("/.well-known/oauth-protected-resource")
    def metadata() -> dict[str, Any]:
        return build_protected_resource_metadata(
            resource=gateway.config.oauth.resource,
            authorization_servers=[gateway.config.oauth.issuer],
            scopes_supported=["mcp.read", "mcp.tools"],
        )

    @app.post("/mcp")
    async def mcp_endpoint(
        request: Request,
        authorization: str | None = Header(default=None),
        x_tenant_id: str | None = Header(default=None),
        traceparent: str | None = Header(default=None),
    ):
        body = await request.json()
        status, payload = gateway.handle(
            body,
            authorization=authorization,
            tenant=x_tenant_id,
            traceparent=traceparent,
        )
        return JSONResponse(status_code=status, content=payload)

    @app.get("/diagnose")
    def diagnose() -> dict[str, Any]:
        """SRE 一键看链路诊断；生产应改成查 Jaeger / Tempo。"""
        return diagnose_from_spans(get_tracer().spans)

    return app


# --------------------- 默认装配（demo / 单测用）---------------------


def build_default_gateway(secret: str = "dev-secret-only-for-tests") -> MCPGateway:
    """装配一个开箱即用的 Gateway，用于本地 demo 与 pytest。"""
    from rate_limiter import RatePolicy

    router = MultiServerRouter()
    router.register(
        UpstreamServer(
            namespace="github",
            endpoint="https://api.githubcopilot.com/mcp",
            tools=["create_issue", "list_repos", "search_code", "boom"],
            resources=["repos", "issues"],
            prompts=[{"name": "summarize_pr", "priority": 10}],
        )
    )
    router.register(
        UpstreamServer(
            namespace="jira",
            endpoint="https://acme.atlassian.net/mcp",
            tools=["create_issue", "list_projects"],
            prompts=[{"name": "summarize_pr", "priority": 50}],
        )
    )
    router.register(
        UpstreamServer(
            namespace="stripe",
            endpoint="https://mcp.stripe.com",
            tools=["search_customer", "create_invoice"],
        )
    )

    oauth = OAuthConfig(
        issuer="https://auth.acme.example",
        resource="https://mcp.acme.example",
        hs256_secret=secret,
        audience="enterprise-mcp-gateway",
    )

    limiter = RateLimiter(
        [
            RatePolicy(
                name="per_user_tool",
                key_template="{tenant}:{user}:{tool}",
                capacity=20,
                refill_rate=2.0,
            ),
            RatePolicy(
                name="per_tenant",
                key_template="{tenant}",
                capacity=200,
                refill_rate=20.0,
                daily_quota=100_000,
            ),
        ]
    )

    cfg = GatewayConfig(oauth=oauth, rate_limiter=limiter, router=router)
    return MCPGateway(cfg)


__all__ = [
    "MCPGateway",
    "GatewayConfig",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "build_app",
    "build_default_gateway",
    "HAS_FASTAPI",
]


# `python mcp_gateway.py` 跑一个最小握手 demo
if __name__ == "__main__":
    gw = build_default_gateway()
    status, resp = gw.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-11-25"}},
        authorization=None,
    )
    print(f"initialize → {status}: {json.dumps(resp, ensure_ascii=False, indent=2)}")
    print(f"router tools = {gw.config.router.list_qualified_tools()}")
