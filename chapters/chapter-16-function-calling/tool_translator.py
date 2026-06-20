"""第 16 篇配套 demo：Function Calling 跨模型协议翻译层.

设计：
- ``ToolSchema``：以 OpenAI tools[].function 为基准的内部抽象（name + description + parameters + strict）
- ``UnifiedToolCall``：五家模型工具调用响应统一抽象（provider + tool_id + name + arguments）
- ``to_anthropic`` / ``to_gemini``：把 OpenAI 风格 ToolSchema 单向翻译到 Anthropic / Gemini 协议
- ``from_anthropic_response`` / ``from_gemini_response``：响应翻回 OpenAI 风格
- ``unify_tool_call``：统一入口，五家模型 raw response 都能归一
- GLM / DeepSeek 走 OpenAI 兼容兜底，passthrough 处理

运行：
    python tool_translator.py     # 打印三家 schema 对照
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ----------------------------- 内部抽象 --------------------------------

@dataclass
class ToolSchema:
    """OpenAI 风格工具描述（内部基准）.

    ``parameters`` 严格遵循 JSON Schema 子集：``type=object``，
    ``properties`` / ``required`` / ``additionalProperties`` 三件套.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    strict: bool = False

    def to_openai(self) -> dict[str, Any]:
        """OpenAI / GLM / DeepSeek 兼容路径直接透传."""
        spec: dict[str, Any] = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
        if self.strict:
            spec["function"]["strict"] = True
        return spec


@dataclass
class UnifiedToolCall:
    """五家模型工具调用响应统一抽象.

    上层业务只看这一份结构，不关心 provider 是哪家.
    """

    provider: str            # "openai" / "anthropic" / "gemini" / "glm" / "deepseek"
    tool_id: str             # OpenAI=call_xxx / Anthropic=toolu_xxx / Gemini=合成
    name: str
    arguments: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)


# --------------------------- OpenAI → Anthropic ---------------------------

# Anthropic input_schema 不识别的字段（翻译时降级）
_ANTHROPIC_DROP_KEYS = {"additionalProperties", "$schema"}


def _strip_for_anthropic(schema: dict[str, Any]) -> dict[str, Any]:
    """递归剔除 Anthropic 不识别的 schema 字段."""
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for k, v in schema.items():
        if k in _ANTHROPIC_DROP_KEYS:
            continue
        if isinstance(v, dict):
            out[k] = _strip_for_anthropic(v)
        elif isinstance(v, list):
            out[k] = [_strip_for_anthropic(x) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out


def to_anthropic(tool: ToolSchema) -> dict[str, Any]:
    """把 OpenAI 风格 ToolSchema 翻译为 Anthropic tools[] 元素.

    关键差异：
    - 扁平结构（没有 ``type=function`` 外壳）
    - ``parameters`` → ``input_schema``
    - 丢弃 ``strict`` 字段（Anthropic 走自约束，没有 strict 解码）
    - 丢弃 ``additionalProperties`` 兼容字段（Anthropic 默认更宽容）
    """
    payload: dict[str, Any] = {
        "name": tool.name,
        "description": tool.description,
        "input_schema": _strip_for_anthropic(tool.parameters),
    }
    # 把 strict 降级为 description 后置说明，让模型自行收敛
    if tool.strict:
        payload["description"] = (
            tool.description
            + "\n\n[strict]: 严格遵守上述 schema，不要输出 schema 中未声明的字段。"
        )
    return payload


# ---------------------------- OpenAI → Gemini -----------------------------

# Gemini 用大写 OpenAPI 类型名，与 OpenAI 的小写不一致
_GEMINI_TYPE_MAP = {
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "object": "OBJECT",
    "array": "ARRAY",
    "null": "NULL",
}


def _to_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """递归把 schema 里的 ``type`` 全部转为 Gemini 大写形式.

    ``anyOf`` / ``oneOf`` 字段 Gemini 支持不稳定，降级为 description 末尾追加提示
    （由 ``to_gemini`` 调用方负责追加）.
    """
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for k, v in schema.items():
        if k == "type" and isinstance(v, str) and v in _GEMINI_TYPE_MAP:
            out[k] = _GEMINI_TYPE_MAP[v]
        elif k in ("anyOf", "oneOf"):
            # Gemini 不稳定支持，剔除并标记
            out["_anyOf_dropped"] = True
            continue
        elif k == "additionalProperties":
            # Gemini OpenAPI schema 不识别该字段
            continue
        elif isinstance(v, dict):
            out[k] = _to_gemini_schema(v)
        elif isinstance(v, list):
            out[k] = [_to_gemini_schema(x) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out


def to_gemini(tool: ToolSchema) -> dict[str, Any]:
    """把 OpenAI 风格 ToolSchema 翻译为 Gemini functionDeclarations 单条.

    关键差异：
    - 包在 ``tools[].functionDeclarations[]`` 数组里（本函数返回单条）
    - schema ``type`` 全部转大写
    - ``anyOf/oneOf`` 字段降级为 description 末尾提示
    - 丢弃 ``strict`` 字段（Gemini 没有等价开关）
    """
    schema = _to_gemini_schema(tool.parameters)
    desc = tool.description
    if schema.pop("_anyOf_dropped", False):
        desc += "\n\n[note]: 本工具部分参数允许多种类型，请严格按业务语义选取一种。"
    return {
        "name": tool.name,
        "description": desc,
        "parameters": schema,
    }


# ----------------------------- 响应翻回 OpenAI 风格 -----------------------------

def from_anthropic_response(resp: dict[str, Any]) -> list[UnifiedToolCall]:
    """把 Anthropic Messages API 的响应翻成 ``UnifiedToolCall`` 列表.

    Anthropic 响应：``content: [{type: text/tool_use, ...}]``，
    每个 ``tool_use`` block 都是一个独立调用.
    """
    calls: list[UnifiedToolCall] = []
    for block in resp.get("content", []) or []:
        if block.get("type") != "tool_use":
            continue
        calls.append(UnifiedToolCall(
            provider="anthropic",
            tool_id=block.get("id", ""),
            name=block.get("name", ""),
            arguments=dict(block.get("input") or {}),
            raw=block,
        ))
    return calls


def from_gemini_response(resp: dict[str, Any]) -> list[UnifiedToolCall]:
    """把 Gemini generateContent 响应翻成 ``UnifiedToolCall`` 列表.

    Gemini 响应：``candidates[0].content.parts[]``，
    其中 ``functionCall`` part 与 ``text`` part 可能混排.
    """
    calls: list[UnifiedToolCall] = []
    candidates = resp.get("candidates") or []
    if not candidates:
        return calls
    parts = (candidates[0].get("content") or {}).get("parts") or []
    for idx, part in enumerate(parts):
        fc = part.get("functionCall")
        if not fc:
            continue
        # Gemini 没有官方 tool_id，用 name + index 合成稳定 id
        name = fc.get("name", "")
        synthetic_id = f"gemini_{name}_{idx}"
        args = fc.get("args") or {}
        if not isinstance(args, dict):
            # 某些 SDK 把 args 包成 protobuf Message，调用方需自行 dict() 一次
            args = dict(args)
        calls.append(UnifiedToolCall(
            provider="gemini",
            tool_id=synthetic_id,
            name=name,
            arguments=args,
            raw=part,
        ))
    return calls


def from_openai_response(resp: dict[str, Any], provider: str = "openai") -> list[UnifiedToolCall]:
    """把 OpenAI / GLM / DeepSeek 兼容响应翻成 ``UnifiedToolCall`` 列表.

    三家共享 ``message.tool_calls[]`` 字段，arguments 是 JSON 字符串.
    """
    calls: list[UnifiedToolCall] = []
    choices = resp.get("choices") or []
    if not choices:
        return calls
    msg = choices[0].get("message") or {}
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        raw_args = fn.get("arguments")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        except json.JSONDecodeError:
            args = {"_raw": raw_args, "_parse_error": True}
        calls.append(UnifiedToolCall(
            provider=provider,
            tool_id=tc.get("id", ""),
            name=fn.get("name", ""),
            arguments=args,
            raw=tc,
        ))
    return calls


def unify_tool_call(provider: str, raw_response: dict[str, Any]) -> list[UnifiedToolCall]:
    """五家模型 raw response 统一出口.

    ``provider`` 取值：openai / anthropic / gemini / glm / deepseek.
    GLM / DeepSeek 走 OpenAI 兼容路径，复用 ``from_openai_response``.
    """
    p = provider.lower()
    if p == "anthropic":
        return from_anthropic_response(raw_response)
    if p == "gemini":
        return from_gemini_response(raw_response)
    if p in ("openai", "glm", "deepseek"):
        return from_openai_response(raw_response, provider=p)
    raise ValueError(f"unknown provider: {provider}")


# ------------------------------- 演示 main -----------------------------------

def _demo_tools() -> list[ToolSchema]:
    """构造两件套：weather + flight，覆盖嵌套 object + enum + strict."""
    return [
        ToolSchema(
            name="get_weather",
            description="查询某城市当前天气",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "城市名，如 Beijing"},
                    "unit": {"type": "string", "enum": ["c", "f"]},
                },
                "required": ["location", "unit"],
                "additionalProperties": False,
            },
            strict=True,
        ),
        ToolSchema(
            name="query_flight",
            description="查询两地之间的航班",
            parameters={
                "type": "object",
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "passengers": {
                        "type": "object",
                        "properties": {
                            "adult": {"type": "integer"},
                            "child": {"type": "integer"},
                        },
                        "required": ["adult"],
                        "additionalProperties": False,
                    },
                },
                "required": ["from", "to", "passengers"],
                "additionalProperties": False,
            },
            strict=False,
        ),
    ]


def main() -> None:  # pragma: no cover
    """跑一个 weather + flight 翻译演示，打印三家 schema 对照."""
    tools = _demo_tools()
    print("=" * 60)
    print("OpenAI / GLM / DeepSeek (passthrough)")
    print("=" * 60)
    for t in tools:
        print(json.dumps(t.to_openai(), ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("Anthropic")
    print("=" * 60)
    for t in tools:
        print(json.dumps(to_anthropic(t), ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("Gemini")
    print("=" * 60)
    for t in tools:
        print(json.dumps(to_gemini(t), ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("响应统一示例（mock 五家响应都翻成 UnifiedToolCall）")
    print("=" * 60)
    mocks = {
        "openai": {"choices": [{"message": {"tool_calls": [
            {"id": "call_001", "type": "function",
             "function": {"name": "get_weather",
                          "arguments": '{"location":"Beijing","unit":"c"}'}}
        ]}}]},
        "anthropic": {"content": [
            {"type": "text", "text": "我先查一下天气..."},
            {"type": "tool_use", "id": "toolu_01", "name": "get_weather",
             "input": {"location": "Beijing", "unit": "c"}},
        ]},
        "gemini": {"candidates": [{"content": {"parts": [
            {"functionCall": {"name": "get_weather",
                              "args": {"location": "Beijing", "unit": "c"}}}
        ]}}]},
    }
    mocks["glm"] = mocks["openai"]
    mocks["deepseek"] = mocks["openai"]
    for provider, raw in mocks.items():
        unified = unify_tool_call(provider, raw)
        print(f"  {provider:<10s} → {[u.name + str(u.arguments) for u in unified]}")


if __name__ == "__main__":  # pragma: no cover
    main()
