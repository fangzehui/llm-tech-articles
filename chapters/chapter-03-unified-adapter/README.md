# Chapter 03 - 统一 API 适配层 Demo

本目录是文章《[03 大模型 API 统一适配层设计](../../03-大模型API统一适配层设计.md)》的配套示例代码。

## 核心概念

- **OpenAI 协议作为事实标准**：把 Anthropic / Gemini 等异构请求结构统一映射到 OpenAI Chat Completions 风格
- **双向适配**：既能 `to_openai`，也能 `from_openai`，方便业务层在统一抽象 + 调用真实后端之间做转换
- **关键差异点**：role 命名、system 字段位置、`max_tokens` vs `maxOutputTokens`

## 文件清单

| 文件 | 说明 |
|------|------|
| `openai_adapter.py` | `AnthropicAdapter` + `GeminiAdapter` 双向适配器 |
| `requirements.txt` | 仅依赖标准库 |

## 快速开始

```bash
pip install -r requirements.txt
python openai_adapter.py
```

## 配套文章

- [03-大模型API统一适配层设计.md](../../03-大模型API统一适配层设计.md)
