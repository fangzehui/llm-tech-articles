"""第 03 篇配套 demo：把 Anthropic / Gemini 风格请求适配为 OpenAI 协议.

OpenAI Chat Completions 的协议事实上已经成为业界标准。本 demo 提供：
- AnthropicAdapter：把 Anthropic Messages 风格 dict 转成 OpenAI 风格
- GeminiAdapter：把 Gemini generateContent 风格 dict 转成 OpenAI 风格
- 反向适配（OpenAI -> 各家）的关键字段映射

可独立运行：
    python openai_adapter.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OpenAIRequest:
    """OpenAI Chat Completions 风格的请求体（核心字段）."""

    model: str
    messages: list[dict[str, str]]
    max_tokens: int = 1024
    temperature: float = 0.7
    stream: bool = False


class AnthropicAdapter:
    """Anthropic Messages -> OpenAI Chat Completions 双向适配器.

    适配规则：
    - Anthropic 的 system 是顶层字段，OpenAI 是放进 messages
    - Anthropic 用 max_tokens（必填），OpenAI 也是 max_tokens
    - Anthropic 的 content 可以是 str 也可以是 list[block]，本 demo 仅取 str
    """

    @staticmethod
    def to_openai(req: dict[str, Any]) -> OpenAIRequest:
        """将 Anthropic 风格 dict 转成 OpenAIRequest.

        Args:
            req: Anthropic Messages API 请求体

        Returns:
            等价的 OpenAIRequest
        """
        msgs: list[dict[str, str]] = []
        if system := req.get("system"):
            msgs.append({"role": "system", "content": str(system)})
        for m in req.get("messages", []):
            content = m.get("content", "")
            if isinstance(content, list):
                content = "".join(
                    blk.get("text", "") for blk in content if isinstance(blk, dict)
                )
            msgs.append({"role": m["role"], "content": str(content)})
        return OpenAIRequest(
            model=req["model"],
            messages=msgs,
            max_tokens=req.get("max_tokens", 1024),
            temperature=req.get("temperature", 0.7),
            stream=req.get("stream", False),
        )

    @staticmethod
    def from_openai(req: OpenAIRequest) -> dict[str, Any]:
        """OpenAI -> Anthropic 反向适配."""
        system_chunks = [m["content"] for m in req.messages if m["role"] == "system"]
        msgs = [
            {"role": m["role"], "content": m["content"]}
            for m in req.messages
            if m["role"] != "system"
        ]
        body: dict[str, Any] = {
            "model": req.model,
            "messages": msgs,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        if system_chunks:
            body["system"] = "\n".join(system_chunks)
        return body


class GeminiAdapter:
    """Gemini generateContent -> OpenAI Chat Completions 双向适配器.

    适配规则：
    - Gemini 的 role 是 user/model，OpenAI 是 user/assistant
    - Gemini 的 contents[].parts[].text，需要拍平
    - Gemini 的 systemInstruction 转 OpenAI 的 system message
    """

    GEMINI_TO_OPENAI_ROLE = {"user": "user", "model": "assistant"}
    OPENAI_TO_GEMINI_ROLE = {"user": "user", "assistant": "model"}

    @classmethod
    def to_openai(cls, req: dict[str, Any]) -> OpenAIRequest:
        """Gemini -> OpenAI."""
        msgs: list[dict[str, str]] = []
        if sys_inst := req.get("systemInstruction"):
            text = ""
            for p in sys_inst.get("parts", []):
                text += p.get("text", "")
            if text:
                msgs.append({"role": "system", "content": text})
        for c in req.get("contents", []):
            text = ""
            for p in c.get("parts", []):
                text += p.get("text", "")
            role = cls.GEMINI_TO_OPENAI_ROLE.get(c.get("role", "user"), "user")
            msgs.append({"role": role, "content": text})
        gen_cfg = req.get("generationConfig", {})
        return OpenAIRequest(
            model=req.get("model", "gemini-pro"),
            messages=msgs,
            max_tokens=gen_cfg.get("maxOutputTokens", 1024),
            temperature=gen_cfg.get("temperature", 0.7),
        )

    @classmethod
    def from_openai(cls, req: OpenAIRequest) -> dict[str, Any]:
        """OpenAI -> Gemini."""
        body: dict[str, Any] = {
            "model": req.model,
            "contents": [],
            "generationConfig": {
                "maxOutputTokens": req.max_tokens,
                "temperature": req.temperature,
            },
        }
        for m in req.messages:
            if m["role"] == "system":
                body["systemInstruction"] = {"parts": [{"text": m["content"]}]}
                continue
            body["contents"].append(
                {
                    "role": cls.OPENAI_TO_GEMINI_ROLE.get(m["role"], "user"),
                    "parts": [{"text": m["content"]}],
                }
            )
        return body


def main() -> None:  # pragma: no cover
    anthropic_req = {
        "model": "claude-sonnet",
        "system": "你是简洁的助手",
        "messages": [{"role": "user", "content": "解释一下什么是适配层"}],
        "max_tokens": 256,
    }
    oai = AnthropicAdapter.to_openai(anthropic_req)
    print("[Anthropic -> OpenAI]", oai)

    gemini_req = {
        "model": "gemini-pro",
        "systemInstruction": {"parts": [{"text": "你是简洁的助手"}]},
        "contents": [
            {"role": "user", "parts": [{"text": "解释一下什么是适配层"}]},
        ],
        "generationConfig": {"maxOutputTokens": 256, "temperature": 0.5},
    }
    oai2 = GeminiAdapter.to_openai(gemini_req)
    print("[Gemini -> OpenAI]", oai2)

    # 反向再回到各家协议，验证是否对称
    print("[OpenAI -> Anthropic]", AnthropicAdapter.from_openai(oai))
    print("[OpenAI -> Gemini]", GeminiAdapter.from_openai(oai2))


if __name__ == "__main__":  # pragma: no cover
    main()
