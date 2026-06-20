"""第 16 篇 smoke test：Function Calling 跨模型翻译层关键路径.

跑法：
    pytest test_smoke.py -q
"""

from __future__ import annotations

import pytest

from tool_translator import (
    ToolSchema,
    UnifiedToolCall,
    from_anthropic_response,
    from_gemini_response,
    from_openai_response,
    to_anthropic,
    to_gemini,
    unify_tool_call,
)


# --------------------------- 测试 fixtures ---------------------------

@pytest.fixture
def weather_tool() -> ToolSchema:
    """带 strict + enum + additionalProperties 的工具，覆盖 strict 降级路径."""
    return ToolSchema(
        name="get_weather",
        description="查询某城市当前天气",
        parameters={
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "unit": {"type": "string", "enum": ["c", "f"]},
            },
            "required": ["location", "unit"],
            "additionalProperties": False,
        },
        strict=True,
    )


@pytest.fixture
def flight_tool() -> ToolSchema:
    """嵌套 object 工具，覆盖递归 schema 翻译."""
    return ToolSchema(
        name="query_flight",
        description="查询两地之间航班",
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
    )


# --------------------------- 翻译层正向 6 用例 ---------------------------

def test_to_anthropic_basic(weather_tool: ToolSchema) -> None:
    """OpenAI → Anthropic 基础翻译：扁平结构 + parameters 改 input_schema."""
    out = to_anthropic(weather_tool)

    # 扁平结构（无 type=function 外壳）
    assert "type" not in out and "function" not in out
    assert out["name"] == "get_weather"
    # parameters 字段改名 input_schema
    assert "parameters" not in out
    assert "input_schema" in out
    assert out["input_schema"]["type"] == "object"
    # additionalProperties 必须被剔除
    assert "additionalProperties" not in out["input_schema"]
    # strict 降级为 description 末尾说明，不再独立字段
    assert "strict" not in out
    assert "[strict]" in out["description"]


def test_to_gemini_nested(flight_tool: ToolSchema) -> None:
    """带 nested object 的 schema 翻到 Gemini：递归大写 + 剔除 additionalProperties."""
    out = to_gemini(flight_tool)
    schema = out["parameters"]

    # 顶层 type 大写
    assert schema["type"] == "OBJECT"
    # 嵌套 object 也要大写
    passengers = schema["properties"]["passengers"]
    assert passengers["type"] == "OBJECT"
    assert passengers["properties"]["adult"]["type"] == "INTEGER"
    # 顶层 + 嵌套 additionalProperties 都被剔除
    assert "additionalProperties" not in schema
    assert "additionalProperties" not in passengers
    # required 字段保留
    assert set(schema["required"]) == {"from", "to", "passengers"}


def test_from_anthropic_tool_use() -> None:
    """Anthropic 响应（tool_use 块 + text 块混排）翻回 UnifiedToolCall."""
    raw = {"content": [
        {"type": "text", "text": "我先查一下..."},
        {"type": "tool_use", "id": "toolu_01",
         "name": "get_weather", "input": {"location": "Beijing", "unit": "c"}},
        {"type": "tool_use", "id": "toolu_02",
         "name": "get_weather", "input": {"location": "Shanghai", "unit": "c"}},
    ]}
    calls = from_anthropic_response(raw)

    assert len(calls) == 2  # text 块被忽略
    assert all(isinstance(c, UnifiedToolCall) for c in calls)
    assert calls[0].provider == "anthropic"
    assert calls[0].tool_id == "toolu_01"
    assert calls[0].name == "get_weather"
    assert calls[0].arguments == {"location": "Beijing", "unit": "c"}
    assert calls[1].arguments["location"] == "Shanghai"


def test_from_gemini_function_call() -> None:
    """Gemini functionCall part 翻回 UnifiedToolCall（含合成 tool_id）."""
    raw = {"candidates": [{"content": {"parts": [
        {"text": "好的，我来查询。"},
        {"functionCall": {"name": "get_weather",
                          "args": {"location": "Beijing", "unit": "c"}}},
    ]}}]}
    calls = from_gemini_response(raw)

    assert len(calls) == 1
    assert calls[0].provider == "gemini"
    assert calls[0].name == "get_weather"
    # Gemini 没有原生 tool_id，本翻译层用 name + index 合成
    assert calls[0].tool_id.startswith("gemini_get_weather_")
    assert calls[0].arguments == {"location": "Beijing", "unit": "c"}


def test_unify_tool_call_5_providers() -> None:
    """五家 mock 响应都能走 unify_tool_call 统一出口，且 arguments 完全一致."""
    expected_args = {"location": "Beijing", "unit": "c"}

    openai_raw = {"choices": [{"message": {"tool_calls": [
        {"id": "call_001", "type": "function",
         "function": {"name": "get_weather",
                      "arguments": '{"location":"Beijing","unit":"c"}'}}
    ]}}]}
    anthropic_raw = {"content": [
        {"type": "tool_use", "id": "toolu_01", "name": "get_weather",
         "input": {"location": "Beijing", "unit": "c"}},
    ]}
    gemini_raw = {"candidates": [{"content": {"parts": [
        {"functionCall": {"name": "get_weather",
                          "args": {"location": "Beijing", "unit": "c"}}},
    ]}}]}

    cases = [
        ("openai", openai_raw),
        ("anthropic", anthropic_raw),
        ("gemini", gemini_raw),
        ("glm", openai_raw),         # OpenAI 兼容路径
        ("deepseek", openai_raw),    # OpenAI 兼容路径
    ]
    for provider, raw in cases:
        unified = unify_tool_call(provider, raw)
        assert len(unified) == 1, f"{provider} 应解析出一条调用"
        assert unified[0].provider == provider
        assert unified[0].name == "get_weather"
        assert unified[0].arguments == expected_args, f"{provider} 参数解析不一致"


def test_strict_mode_anthropic_fallback(weather_tool: ToolSchema) -> None:
    """strict=True 翻译到 Anthropic 时降级路径：
    - 不向 input_schema 添加 strict 字段（Anthropic 不识别）
    - 也不保留顶层 strict 字段
    - 把 strict 语义降级为 description 末尾的人类可读说明
    """
    weather_tool.strict = True
    out = to_anthropic(weather_tool)

    assert "strict" not in out
    assert "strict" not in out["input_schema"]
    assert "[strict]" in out["description"]

    # 关掉 strict 时 description 不被污染
    weather_tool.strict = False
    out2 = to_anthropic(weather_tool)
    assert "[strict]" not in out2["description"]


# --------------------------- 额外鲁棒性 ---------------------------

def test_openai_arguments_json_decode_error_safe() -> None:
    """OpenAI tool_calls.arguments 是非法 JSON 时不应抛异常，而是返回 _parse_error 标记."""
    raw = {"choices": [{"message": {"tool_calls": [
        {"id": "call_x", "type": "function",
         "function": {"name": "broken", "arguments": '{"oops":'}}
    ]}}]}
    calls = from_openai_response(raw)

    assert len(calls) == 1
    assert calls[0].arguments.get("_parse_error") is True
