# Chapter 16 - Function Calling 跨模型协议翻译层

本目录是文章《[16 Function Calling 跨模型兼容层实测](../../16-Function_Calling跨模型兼容层实测.md)》的配套示例代码。

## 核心概念

- **以 OpenAI 协议为内部基准**：`ToolSchema(name, description, parameters, strict)` 直接复刻 OpenAI `tools[].function` 字段，配合 `to_openai()` 在 OpenAI / GLM / DeepSeek 三家做 passthrough。
- **三条单向翻译**：`to_anthropic` 把 OpenAI schema 翻成 Anthropic 扁平 + `input_schema` 风格；`to_gemini` 把类型大写化、剔除 `additionalProperties`、对 `anyOf/oneOf` 做 description 降级。
- **响应五家归一**：`unify_tool_call(provider, raw)` 把 OpenAI / Anthropic / Gemini / GLM / DeepSeek 任意一家的工具调用响应翻成统一的 `UnifiedToolCall(provider, tool_id, name, arguments)`，业务侧不感知 provider。
- **strict 降级策略**：Anthropic / Gemini 没有等价 strict 字段，本层把 OpenAI strict 语义降级为 description 末尾的可读约束说明，靠模型自约束完成。
- **零外部 SDK 依赖**：纯 dict 演示，可完全脱网跑，便于单测与教学。

## 文件清单

| 文件 | 说明 |
|------|------|
| `tool_translator.py` | `ToolSchema` + `UnifiedToolCall` + `to_anthropic` + `to_gemini` + `from_*` + `unify_tool_call` + 演示 main |
| `test_smoke.py` | pytest 风格 7 个用例：OpenAI→Anthropic 基础翻译 / 嵌套 schema 翻 Gemini / 三家响应翻回 / 五家统一 / strict 降级 / 非法 JSON 安全 |
| `requirements.txt` | 仅 `pytest`（运行测试时需要） |

## 快速开始

```bash
pip install -r requirements.txt
python tool_translator.py            # 跑 demo，打印三家 schema 对照 + 五家响应统一
pytest test_smoke.py -q              # 跑 smoke test
```

## 输出示意

```
============================================================
OpenAI / GLM / DeepSeek (passthrough)
============================================================
{"type": "function",
 "function": {"name": "get_weather", ...,
              "parameters": {"type": "object", ...,
                             "additionalProperties": false},
              "strict": true}}
...

============================================================
Anthropic
============================================================
{"name": "get_weather",
 "description": "...\n\n[strict]: 严格遵守上述 schema...",
 "input_schema": {"type": "object", "properties": {...}, "required": [...]}}
...

============================================================
Gemini
============================================================
{"name": "get_weather",
 "description": "...",
 "parameters": {"type": "OBJECT",
                "properties": {"location": {"type": "STRING"}, ...}}}

============================================================
响应统一示例（mock 五家响应都翻成 UnifiedToolCall）
============================================================
  openai     → ["get_weather{'location': 'Beijing', 'unit': 'c'}"]
  anthropic  → ["get_weather{'location': 'Beijing', 'unit': 'c'}"]
  gemini     → ["get_weather{'location': 'Beijing', 'unit': 'c'}"]
  glm        → ["get_weather{'location': 'Beijing', 'unit': 'c'}"]
  deepseek   → ["get_weather{'location': 'Beijing', 'unit': 'c'}"]
```

## 配套文章

- [16-Function_Calling跨模型兼容层实测.md](../../16-Function_Calling跨模型兼容层实测.md)

## 数据声明

本目录代码为**协议翻译层最小可跑示例**，不依赖任何模型厂商 SDK，所有响应数据均为 mock。生产环境对接真实 API 时请：

1. 流式工具调用按文章 §七 给出的三套累加协议各写一份 SSE consumer；
2. `tool_choice` / `parallel_tool_calls` / `disable_parallel_tool_use` 等运行时开关请按业务在 provider 适配层透传；
3. `anyOf` / `oneOf` 等高级 schema 在 Anthropic / Gemini 上行为各异，上线前必须做 dryrun 兼容性矩阵；
4. 错误恢复请把 tool 执行异常归一为 `tool_result(is_error=true)` / `functionResponse(error=...)` 后回填模型自重试。
