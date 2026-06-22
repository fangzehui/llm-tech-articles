"""可观测：OpenTelemetry trace 注入（含 MCP 专用 span attributes）。

为什么需要 MCP 专用埋点？
========================
- MCP 调用是 ``Host → Client → Gateway → Upstream → Tool → Data → Response``
  长链路，没有 trace 出故障时只能"猜"在哪一层；
- W3C Trace Context 让 traceparent 跨 JSON-RPC 边界继续流转；
- 通过加 ``mcp.method``、``mcp.tool_name``、``mcp.session_id``、``mcp.namespace``
  等专属属性，可以在 Jaeger / Tempo / OTEL Collector 里做精细化查询。

实现策略
========
- 优先用真 OpenTelemetry SDK；如果 ``opentelemetry`` 未安装，退化为本文件内
  的 ``InMemoryTracer``，保证库可以被单测直接 import 不报错。
"""

from __future__ import annotations

import os
import random
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


# --------------------- MCP 专属 span attribute keys ---------------------
# 参考 OTel "semantic conventions"，命名空间为 mcp.*

ATTR_MCP_METHOD = "mcp.method"               # initialize / tools/call / resources/read ...
ATTR_MCP_TOOL_NAME = "mcp.tool_name"
ATTR_MCP_NAMESPACE = "mcp.namespace"
ATTR_MCP_SESSION_ID = "mcp.session_id"
ATTR_MCP_PROTOCOL_VERSION = "mcp.protocol_version"
ATTR_MCP_TRANSPORT = "mcp.transport"         # streamable_http / stdio
ATTR_MCP_REQUEST_ID = "mcp.request_id"
ATTR_MCP_STATUS = "mcp.status"               # ok / error
ATTR_MCP_ERROR_CODE = "mcp.error_code"
ATTR_MCP_TENANT = "mcp.tenant"
ATTR_MCP_USER = "mcp.user"


# --------------------- W3C traceparent 解析 ---------------------


def parse_traceparent(value: str | None) -> dict[str, str] | None:
    """``00-{trace_id_32}-{span_id_16}-{flags_2}`` → dict 或 None。"""
    if not value:
        return None
    parts = value.split("-")
    if len(parts) != 4 or len(parts[1]) != 32 or len(parts[2]) != 16:
        return None
    return {
        "version": parts[0],
        "trace_id": parts[1],
        "parent_span_id": parts[2],
        "trace_flags": parts[3],
    }


def build_traceparent(trace_id: str, span_id: str, sampled: bool = True) -> str:
    flags = "01" if sampled else "00"
    return f"00-{trace_id}-{span_id}-{flags}"


def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_span_id() -> str:
    return uuid.uuid4().hex[:16]


# --------------------- 内置 InMemoryTracer ---------------------


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    start_ns: int
    end_ns: int | None = None
    status: str = "unset"
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, **attrs: Any) -> None:
        self.events.append({"name": name, "time_ns": time.time_ns(), **attrs})

    def set_status(self, status: str, description: str = "") -> None:
        self.status = status
        if description:
            self.attributes.setdefault("status.description", description)

    @property
    def duration_ms(self) -> float:
        if self.end_ns is None:
            return -1.0
        return (self.end_ns - self.start_ns) / 1e6


class InMemoryTracer:
    """供单测 / 离线 demo 使用的进程内 Tracer。

    生产请替换为真正的 OTel SDK：``tracer = trace.get_tracer(__name__)``。
    """

    def __init__(self) -> None:
        self.spans: list[Span] = []
        self._stack: list[Span] = []

    @contextmanager
    def start_as_current_span(
        self, name: str, *, traceparent: str | None = None, attributes: dict[str, Any] | None = None
    ) -> Iterator[Span]:
        if self._stack:
            parent = self._stack[-1]
            trace_id, parent_id = parent.trace_id, parent.span_id
        else:
            ctx = parse_traceparent(traceparent)
            if ctx:
                trace_id, parent_id = ctx["trace_id"], ctx["parent_span_id"]
            else:
                trace_id, parent_id = new_trace_id(), None
        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=new_span_id(),
            parent_span_id=parent_id,
            start_ns=time.time_ns(),
        )
        if attributes:
            span.attributes.update(attributes)
        self._stack.append(span)
        try:
            yield span
        except Exception as e:  # noqa: BLE001
            span.set_status("error", f"{type(e).__name__}: {e}")
            span.set_attribute(ATTR_MCP_STATUS, "error")
            raise
        finally:
            span.end_ns = time.time_ns()
            if span.status == "unset":
                span.set_status("ok")
                span.set_attribute(ATTR_MCP_STATUS, "ok")
            self._stack.pop()
            self.spans.append(span)

    def reset(self) -> None:
        self.spans.clear()
        self._stack.clear()

    def find(self, name: str) -> list[Span]:
        return [s for s in self.spans if s.name == name]


# 单例：保证 Gateway / 测试代码共享同一份 trace 流水
_GLOBAL_TRACER = InMemoryTracer()


def get_tracer() -> InMemoryTracer:
    return _GLOBAL_TRACER


# --------------------- 业务侧装饰 ---------------------


def instrument_mcp_call(
    *,
    method: str,
    namespace: str | None = None,
    tool: str | None = None,
    session_id: str | None = None,
    protocol_version: str | None = None,
    transport: str = "streamable_http",
    tenant: str | None = None,
    user: str | None = None,
    traceparent: str | None = None,
):
    """业务代码用这个 ``with instrument_mcp_call(...)`` 包一次 MCP 调用。

    会自动写入 mcp.* 标准 attributes。
    """
    tracer = get_tracer()
    attrs: dict[str, Any] = {
        ATTR_MCP_METHOD: method,
        ATTR_MCP_TRANSPORT: transport,
        ATTR_MCP_REQUEST_ID: uuid.uuid4().hex[:12],
    }
    if namespace is not None:
        attrs[ATTR_MCP_NAMESPACE] = namespace
    if tool is not None:
        attrs[ATTR_MCP_TOOL_NAME] = tool
    if session_id is not None:
        attrs[ATTR_MCP_SESSION_ID] = session_id
    if protocol_version is not None:
        attrs[ATTR_MCP_PROTOCOL_VERSION] = protocol_version
    if tenant is not None:
        attrs[ATTR_MCP_TENANT] = tenant
    if user is not None:
        attrs[ATTR_MCP_USER] = user

    span_name = f"mcp.{method}" if not tool else f"mcp.{method}:{namespace}.{tool}"
    return tracer.start_as_current_span(span_name, traceparent=traceparent, attributes=attrs)


# --------------------- 故障排查决策树（程序化版本）---------------------


def diagnose_from_spans(spans: list[Span]) -> dict[str, Any]:
    """从一组 span 自动诊断"链路在哪一层挂了"，给 SRE 用。

    返回结构::

        {
          "stage": "client" / "gateway" / "upstream" / "tool" / "unknown",
          "error_count": 1,
          "slowest_span": "mcp.tools/call:github.create_issue",
          "hints": ["..."]
        }
    """
    if not spans:
        return {"stage": "unknown", "error_count": 0, "slowest_span": None, "hints": []}

    error_spans = [s for s in spans if s.status == "error"]
    slowest = max(spans, key=lambda s: s.duration_ms if s.end_ns else -1)

    hints: list[str] = []
    stage = "unknown"
    if error_spans:
        first_err = error_spans[0]
        name = first_err.name
        if name.startswith("mcp.initialize"):
            stage = "client"
            hints.append("initialize 阶段失败：检查 protocolVersion 协商 / 传输层连通性")
        elif "tools/call" in name or first_err.attributes.get(ATTR_MCP_METHOD) == "tools/call":
            if first_err.attributes.get(ATTR_MCP_ERROR_CODE) in {"upstream_timeout", "upstream_error"}:
                stage = "upstream"
                hints.append("upstream MCP Server 超时 / 不可达：查上游健康检查")
            else:
                stage = "tool"
                hints.append("tool 执行失败：检查权限 / 参数 / 业务异常")
        else:
            stage = "gateway"
            hints.append("Gateway 自身异常：查日志中的 traceback 与限流命中")
    if slowest.duration_ms > 1000:
        hints.append(
            f"最慢 span={slowest.name} 耗时 {slowest.duration_ms:.0f}ms，"
            "建议在 upstream / tool 内部加更细粒度埋点"
        )

    return {
        "stage": stage,
        "error_count": len(error_spans),
        "slowest_span": slowest.name,
        "slowest_duration_ms": round(slowest.duration_ms, 2),
        "hints": hints,
    }


__all__ = [
    "Span",
    "InMemoryTracer",
    "get_tracer",
    "instrument_mcp_call",
    "parse_traceparent",
    "build_traceparent",
    "new_trace_id",
    "new_span_id",
    "diagnose_from_spans",
    "ATTR_MCP_METHOD",
    "ATTR_MCP_TOOL_NAME",
    "ATTR_MCP_NAMESPACE",
    "ATTR_MCP_SESSION_ID",
    "ATTR_MCP_PROTOCOL_VERSION",
    "ATTR_MCP_TRANSPORT",
    "ATTR_MCP_STATUS",
    "ATTR_MCP_ERROR_CODE",
    "ATTR_MCP_TENANT",
    "ATTR_MCP_USER",
]


# 让 ``python observability.py`` 跑一个最小 demo
if __name__ == "__main__":
    tracer = get_tracer()
    with instrument_mcp_call(method="initialize", protocol_version="2025-11-25"):
        time.sleep(0.005)
    with instrument_mcp_call(
        method="tools/call",
        namespace="github",
        tool="create_issue",
        session_id="sess-001",
        tenant="acme",
        user="alice",
    ) as span:
        time.sleep(0.002)
        span.add_event("upstream_response_received", duration_ms=1.2)
    print(f"采集到 {len(tracer.spans)} 条 span：")
    for s in tracer.spans:
        print(f"  - {s.name}  status={s.status}  duration={s.duration_ms:.2f}ms")
    print("诊断：", diagnose_from_spans(tracer.spans))
