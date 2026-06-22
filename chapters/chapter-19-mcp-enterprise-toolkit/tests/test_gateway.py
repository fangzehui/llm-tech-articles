"""第 19 篇 smoke test：MCP 企业接入 6 大踩坑各覆盖至少 1 个用例。

跑法::

    pytest tests/ -v

用例与踩坑映射
==============
- ``test_protocol_version_negotiation``      → 踩坑 1：协议版本兼容
- ``test_transport_streamable_http_only``    → 踩坑 2：传输层选错
- ``test_oauth_2_1_resource_indicator``      → 踩坑 3：OAuth 2.1 接入不规范
- ``test_multi_server_tool_name_collision``  → 踩坑 4：多 Server 路由冲突
- ``test_rate_limit_token_bucket``           → 踩坑 5：限流与配额
- ``test_observability_trace_diagnose``      → 踩坑 6：可观测性缺失
另附 1 个端到端用例，把全链路串起来跑一遍。
"""

from __future__ import annotations

import time

import pytest


# ============================================================
# 踩坑 1：协议版本兼容
# ============================================================


def test_protocol_version_negotiation(gateway):
    """initialize 阶段 Host 报老版本，Gateway 必须按规范回退而非直接报错。"""
    # Host 只报 2024-11-05（早期版），Gateway 自己最高支持 2025-11-25
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    }
    status, resp = gateway.handle(body, authorization=None)
    assert status == 200
    # 应协商到双方共同的最低版本
    assert resp["result"]["protocolVersion"] == "2024-11-05"

    # Host 报 2025-11-25 → 协商到最新
    body["params"]["protocolVersion"] = "2025-11-25"
    status, resp = gateway.handle(body, authorization=None)
    assert resp["result"]["protocolVersion"] == "2025-11-25"

    # 必须声明 elicitation 与 tools capability（11-25 版规范）
    caps = resp["result"]["capabilities"]
    assert "elicitation" in caps
    assert caps["tools"]["listChanged"] is True


# ============================================================
# 踩坑 2：传输层选错（stdio vs Streamable HTTP）
# ============================================================


def test_transport_streamable_http_only(gateway):
    """注册 stdio 上游应被允许（本地场景），但远端调用都走 streamable_http。

    Gateway 自身只对外暴露 streamable_http；stdio 仅用于本地 server 嵌入。
    """
    from multi_server_router import UpstreamServer

    # 合法：stdio 用于本地 server
    local = UpstreamServer(
        namespace="localfs", endpoint="cmd://fs-server", transport="stdio",
        tools=["read_file"]
    )
    assert local.transport == "stdio"

    # 非法 transport 必须拒绝
    with pytest.raises(ValueError):
        UpstreamServer(namespace="bad", endpoint="x", transport="http+sse")

    # 默认 transport 是 streamable_http（2025-03-26 规范后的一等公民）
    default_srv = UpstreamServer(namespace="d", endpoint="https://x/mcp", tools=[])
    assert default_srv.transport == "streamable_http"


# ============================================================
# 踩坑 3：OAuth 2.1 接入不规范（PKCE + Resource Indicator）
# ============================================================


def test_oauth_2_1_resource_indicator(gateway, make_token):
    """
    1) 没带 Bearer → 401
    2) Bearer 但 resource claim 是别家 RS → 401 invalid_target
    3) Bearer 正常 → 200
    4) PKCE plain 被禁用
    5) PKCE S256 校验通过
    """
    from oauth_middleware import (
        InvalidResource,
        PKCEError,
        generate_pkce_pair,
        verify_access_token,
        verify_pkce,
    )

    body = {"jsonrpc": "2.0", "id": 9, "method": "tools/list"}

    # 1) 匿名调用
    status, resp = gateway.handle(body, authorization=None)
    assert status == 401
    assert "OAuth" in resp["error"]["message"]

    # 2) token 的 resource claim 是别家 RS（典型透传攻击）
    bad_token = make_token(resource="https://other-rs.example")
    status, resp = gateway.handle(body, authorization=bad_token)
    assert status == 401
    assert "invalid_target" in resp["error"]["message"]

    # 3) 合法 token
    good = make_token()
    status, resp = gateway.handle(body, authorization=good)
    assert status == 200
    tool_names = [t["name"] for t in resp["result"]["tools"]]
    assert "github.create_issue" in tool_names

    # 4) PKCE plain 必须被拒
    verifier, challenge = generate_pkce_pair()
    with pytest.raises(PKCEError):
        verify_pkce(verifier, challenge, method="plain")

    # 5) PKCE S256 正常
    verify_pkce(verifier, challenge, method="S256")

    # 6) 过期 token（超出 leeway=30s 范围）
    expired = make_token(exp_in=-3600)
    status, resp = gateway.handle(body, authorization=expired)
    assert status == 401
    assert "expired" in resp["error"]["message"].lower() or "invalid_token" in resp["error"]["message"].lower()


# ============================================================
# 踩坑 4：多 Server 路由冲突（tool name / resource URI 撞名）
# ============================================================


def test_multi_server_tool_name_collision(gateway):
    """github.create_issue 与 jira.create_issue 通过 namespace 前缀隔离。"""
    from multi_server_router import (
        MultiServerRouter,
        NamespaceCollision,
        ToolCollision,
        UnknownTool,
        UpstreamServer,
    )

    r = gateway.config.router
    # gateway 默认装配里就有 github.create_issue 和 jira.create_issue
    qualified = r.list_qualified_tools()
    assert "github.create_issue" in qualified
    assert "jira.create_issue" in qualified

    # 路由解析
    ns, tool = r.resolve_tool("github.create_issue")
    assert (ns, tool) == ("github", "create_issue")
    ns, tool = r.resolve_tool("jira.create_issue")
    assert (ns, tool) == ("jira", "create_issue")

    # 不带 namespace 前缀必须被拒
    with pytest.raises(UnknownTool):
        r.resolve_tool("create_issue")

    # namespace 撞名拒绝注册
    with pytest.raises(NamespaceCollision):
        r.register(UpstreamServer(namespace="github", endpoint="x", tools=[]))

    # 同 namespace 内 tool 撞名拒绝注册
    bad = MultiServerRouter()
    with pytest.raises(ToolCollision):
        bad.register(UpstreamServer(namespace="x", endpoint="x", tools=["a", "a"]))

    # prompt 撞名按 priority 选 —— github(10) < jira(50)，github 优先
    assert r.resolve_prompt("summarize_pr") == "github"

    # resource URI scheme 隔离
    ns, sub = r.resolve_resource("upstream://github/issues/42")
    assert ns == "github" and sub == "issues/42"
    with pytest.raises(UnknownTool):
        r.resolve_resource("https://wrong-scheme/issues/42")


# ============================================================
# 踩坑 5：限流与配额
# ============================================================


def test_rate_limit_token_bucket(gateway, make_token):
    """capacity=20 的桶被打满后必须 429，且 retry_after 大于 0。"""
    token = make_token(sub="alice", tenant="acme")

    body_template = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "github.list_repos", "arguments": {}},
    }

    successes = 0
    rate_limited = 0
    for i in range(40):  # capacity=20，超出后应该有大量 429
        body = dict(body_template, id=i)
        status, resp = gateway.handle(body, authorization=token)
        if status == 200:
            successes += 1
        elif status == 429:
            rate_limited += 1
            assert "rate limited" in resp["error"]["message"]
            assert "retry_after" in resp["error"]["message"]

    assert successes >= 18, f"应允许至少 18 次（capacity≈20），实际 {successes}"
    assert rate_limited >= 10, f"应至少 10 次被限流，实际 {rate_limited}"

    # 单独验证 TokenBucket 数学语义
    from rate_limiter import TokenBucket

    b = TokenBucket(capacity=2, refill_rate=10.0)
    assert b.try_consume() is True
    assert b.try_consume() is True
    assert b.try_consume() is False
    # 100ms 回 1 token
    time.sleep(0.11)
    assert b.try_consume() is True


# ============================================================
# 踩坑 6：可观测性缺失（trace + 故障诊断）
# ============================================================


def test_observability_trace_diagnose(gateway, make_token):
    """跑 1 个失败的 tools/call，应当能在 span 里定位到 upstream 故障。"""
    from observability import (
        ATTR_MCP_METHOD,
        ATTR_MCP_TOOL_NAME,
        ATTR_MCP_NAMESPACE,
        diagnose_from_spans,
        get_tracer,
    )

    tracer = get_tracer()
    token = make_token()

    # 一个正常请求 + 一个故意爆炸的请求
    gateway.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "github.list_repos", "arguments": {}}},
        authorization=token,
    )
    status_bad, resp_bad = gateway.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "github.boom", "arguments": {}}},
        authorization=token,
    )

    assert status_bad == 502
    spans = tracer.spans
    assert len(spans) >= 2

    # 关键 attribute 必须存在
    tool_call_spans = [s for s in spans if s.attributes.get(ATTR_MCP_METHOD) == "tools/call"]
    assert len(tool_call_spans) == 2
    for s in tool_call_spans:
        assert s.attributes.get(ATTR_MCP_NAMESPACE) == "github"
        assert s.attributes.get(ATTR_MCP_TOOL_NAME) in {"list_repos", "boom"}

    # 故障诊断要识别出 upstream 错误
    diag = diagnose_from_spans(spans)
    assert diag["error_count"] >= 1
    assert diag["stage"] in {"upstream", "tool"}


# ============================================================
# 端到端：跑一次完整握手 + 工具调用
# ============================================================


def test_end_to_end_handshake_and_call(gateway, make_token):
    """initialize → tools/list → tools/call 完整链路。"""
    # 1) initialize
    status, init_resp = gateway.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-11-25"}},
        authorization=None,
    )
    assert status == 200
    assert init_resp["result"]["protocolVersion"] == "2025-11-25"

    # 2) tools/list 需要 token
    token = make_token()
    status, list_resp = gateway.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        authorization=token,
    )
    assert status == 200
    qualified_names = [t["name"] for t in list_resp["result"]["tools"]]
    assert "github.create_issue" in qualified_names
    assert "stripe.search_customer" in qualified_names

    # 3) tools/call
    status, call_resp = gateway.handle(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "github.create_issue",
                    "arguments": {"title": "hello", "body": "world"}}},
        authorization=token,
    )
    assert status == 200
    content = call_resp["result"]["content"][0]
    assert content["type"] == "text"

    # 4) resources/read
    status, res_resp = gateway.handle(
        {"jsonrpc": "2.0", "id": 4, "method": "resources/read",
         "params": {"uri": "upstream://github/issues/1"}},
        authorization=token,
    )
    assert status == 200
    assert res_resp["result"]["contents"][0]["namespace"] == "github"

    # 5) ping
    status, ping_resp = gateway.handle(
        {"jsonrpc": "2.0", "id": 5, "method": "ping"},
        authorization=token,
    )
    assert status == 200
    assert ping_resp["result"] == {}


def test_well_known_metadata():
    """.well-known/oauth-protected-resource 元数据格式必须符合 RFC 9728。"""
    from oauth_middleware import build_protected_resource_metadata

    meta = build_protected_resource_metadata(
        resource="https://mcp.acme.example",
        authorization_servers=["https://auth.acme.example"],
    )
    assert meta["resource"] == "https://mcp.acme.example"
    assert meta["authorization_servers"] == ["https://auth.acme.example"]
    assert "mcp.tools" in meta["scopes_supported"]
    assert "header" in meta["bearer_methods_supported"]


def test_sample_session_file_loadable():
    """配套的 sample_mcp_session.json 必须能被 trace 模块消费。"""
    import json
    import os

    here = os.path.dirname(__file__)
    path = os.path.abspath(os.path.join(here, "..", "data", "sample_mcp_session.json"))
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["session_id"]
    assert data["protocol_version"] in {"2025-11-25", "2025-06-18", "2025-03-26"}
    assert len(data["spans"]) >= 3
    # 至少要有 initialize + tools/call
    methods = {s["attributes"]["mcp.method"] for s in data["spans"]}
    assert "initialize" in methods
    assert "tools/call" in methods
