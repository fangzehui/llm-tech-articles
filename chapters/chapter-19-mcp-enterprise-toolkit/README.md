# Chapter 19 - MCP 企业接入工具集

本目录是文章《[19 MCP 企业接入 2026 实战：从 OpenAI 6/14 新公告到生产部署的 6 大踩坑](../../19-MCP企业接入实战_2026年6大踩坑.md)》的配套示例代码。

## 项目介绍

把企业要把 **Model Context Protocol** 接入生产时最常踩的 6 个坑——协议版本协商、传输层选型、OAuth 2.1 规范化、多 Server 路由冲突、限流配额、可观测——写成一套可直接 fork 的最小工具集。

- **`mcp_gateway.py`**：单一入口聚合多个上游 MCP Server，对外暴露统一 Streamable HTTP，支持 ``initialize / tools/list / tools/call / resources/read / ping``；
- **`oauth_middleware.py`**：OAuth 2.1 Resource Server 验证（含 PKCE S256 + Resource Indicator RFC 8707）；
- **`multi_server_router.py`**：``namespace.tool`` 前缀路由 + ``upstream://`` scheme 隔离，彻底解决撞名；
- **`rate_limiter.py`**：令牌桶 + 日配额，多维度 ``tenant × user × tool`` key；
- **`observability.py`**：W3C Trace Context + MCP 专属 span attributes + 故障诊断决策器；
- **`tests/test_gateway.py`**：6 大踩坑各 1 个 pytest 用例 + 端到端用例。

> ⚠️ 本仓库定位是**工程参考**而非开箱即用的产品。生产部署还需替换 IdP / JWKS / 上游真实 HTTP 转发 / K8s 探活与 ConfigMap 装载等环节。

## 文件清单

| 文件 | 说明 |
|------|------|
| `mcp_gateway.py` | FastAPI Gateway + 纯逻辑 ``MCPGateway.handle()``（可单测） |
| `oauth_middleware.py` | JWT + Resource Indicator + PKCE 校验 + ``.well-known`` 元数据 |
| `multi_server_router.py` | ``UpstreamServer`` + ``MultiServerRouter`` + 协议版本协商 |
| `rate_limiter.py` | ``TokenBucket`` / ``QuotaTracker`` / ``RateLimiter`` + 多策略 |
| `observability.py` | ``InMemoryTracer`` + ``instrument_mcp_call`` + ``diagnose_from_spans`` |
| `tests/test_gateway.py` | 9 个 pytest 用例（含 6 大踩坑 + 端到端 + 元数据 + 样本数据） |
| `tests/conftest.py` | ``gateway`` / ``oauth_config`` / ``make_token`` 等共享 fixture |
| `data/sample_mcp_session.json` | 一次完整 MCP 会话的 5 条 span + 审计日志，可直接灌入 Jaeger |
| `requirements.txt` | fastapi / httpx / authlib / opentelemetry / pytest 等可选依赖 |

## 6 个踩坑场景索引

| # | 踩坑 | 关键代码 | 关键测试 |
|---:|------|---------|---------|
| 1 | 协议版本兼容 | `multi_server_router.negotiate_protocol_version` | `test_protocol_version_negotiation` |
| 2 | 传输层选错 | `UpstreamServer.transport` 校验 | `test_transport_streamable_http_only` |
| 3 | OAuth 2.1 接入不规范 | `oauth_middleware.verify_access_token` / `verify_pkce` | `test_oauth_2_1_resource_indicator` |
| 4 | 多 Server 路由冲突 | `MultiServerRouter.resolve_tool/resource/prompt` | `test_multi_server_tool_name_collision` |
| 5 | 限流与配额 | `RateLimiter.check` + `TokenBucket` | `test_rate_limit_token_bucket` |
| 6 | 可观测性缺失 | `instrument_mcp_call` + `diagnose_from_spans` | `test_observability_trace_diagnose` |

## 安装步骤

```bash
cd chapters/chapter-19-mcp-enterprise-toolkit
pip install -r requirements.txt   # 仅 pytest 必装，其余可选
```

> 即便只装了 ``pytest``，整个 ``tests/`` 也能完整跑过——所有强依赖都做了 ``try/except`` 守卫。

## 一行 Demo

```bash
# 1) 跑最小握手 demo（不依赖任何外网）
python mcp_gateway.py

# 2) 跑 observability 自动诊断 demo
python observability.py

# 3) smoke test 全绿
pytest tests/ -v
```

## 输出示意

```
$ python mcp_gateway.py
initialize → 200: {
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-11-25",
    "capabilities": {
      "tools": { "listChanged": true },
      "resources": { "listChanged": true },
      "prompts": {},
      "elicitation": { "form": {}, "url": {} }
    },
    "serverInfo": { "name": "enterprise-mcp-gateway", "version": "0.19.0" }
  }
}
router tools = ['github.boom', 'github.create_issue', 'github.list_repos',
                'github.search_code', 'jira.create_issue', 'jira.list_projects',
                'stripe.create_invoice', 'stripe.search_customer']
```

```
$ pytest tests/ -v
tests/test_gateway.py::test_protocol_version_negotiation        PASSED
tests/test_gateway.py::test_transport_streamable_http_only      PASSED
tests/test_gateway.py::test_oauth_2_1_resource_indicator        PASSED
tests/test_gateway.py::test_multi_server_tool_name_collision    PASSED
tests/test_gateway.py::test_rate_limit_token_bucket             PASSED
tests/test_gateway.py::test_observability_trace_diagnose        PASSED
tests/test_gateway.py::test_end_to_end_handshake_and_call       PASSED
tests/test_gateway.py::test_well_known_metadata                 PASSED
tests/test_gateway.py::test_sample_session_file_loadable        PASSED
```

## 数据声明

- ``sample_mcp_session.json`` 用 [MCP 2025-11-25 规范](https://modelcontextprotocol.io/specification/2025-11-25) 的字段命名，5 条 span 模拟了一次"初始化 → list → call ok → call timeout → resource read"的真实流。
- 协议版本号、capabilities 字段全部以官方规范为准；6 大踩坑的根因分析与官方变更日志（``2025-03-26`` Streamable HTTP / ``2025-06-18`` Resource Indicator / ``2025-11-25`` Elicitation+Tasks）双向对齐。
- 单元测试不依赖任何真实 IdP / 上游 MCP Server，方便嵌入 CI。

## 配套文章

- [19-MCP企业接入实战_2026年6大踩坑.md](../../19-MCP企业接入实战_2026年6大踩坑.md)
- **模型广场**（支持 MCP 协议的主流模型一站式调用）：https://activity.ldzktoken.com/activity/index.html
