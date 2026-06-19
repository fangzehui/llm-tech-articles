"""第 06 篇配套 demo：国产模型 OpenAI 兼容 client 封装.

国产模型大都提供 OpenAI 兼容协议（DashScope、火山方舟、DeepSeek、智谱、Kimi 等），
只是 base_url 与默认模型名不同。本 demo 把这些差异封装成一个 registry，
业务侧只需要按厂商名 + 模型 alias 调用，无需关心具体 base_url。

为了脱网可跑，默认使用 mock 后端；真实接入时把 _real_call 实现替换为
官方 SDK（如 openai.OpenAI(base_url=..., api_key=...)）。

可独立运行：
    python domestic_benchmark.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import MockLLMClient  # noqa: E402


@dataclass(frozen=True)
class VendorEndpoint:
    """国产模型厂商接入信息.

    Attributes:
        vendor: 厂商英文短名
        display_name: 中文显示名
        base_url: OpenAI 兼容 endpoint
        default_model: 默认模型名
        notes: 备注（计费口径、特性等）
    """

    vendor: str
    display_name: str
    base_url: str
    default_model: str
    notes: str = ""


# 注册表：base_url 摘自各厂商公开文档，请以官方文档最新版本为准
VENDOR_REGISTRY: dict[str, VendorEndpoint] = {
    "qwen": VendorEndpoint(
        vendor="qwen",
        display_name="阿里云 通义千问 / DashScope",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
        notes="OpenAI 兼容模式；支持 1M 上下文档位",
    ),
    "deepseek": VendorEndpoint(
        vendor="deepseek",
        display_name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        notes="原生 OpenAI 兼容；提供 chat 与 reasoner",
    ),
    "doubao": VendorEndpoint(
        vendor="doubao",
        display_name="字节火山方舟 豆包",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        default_model="doubao-seed-pro",
        notes="模型 ID 形如 'ep-...' 或 model alias",
    ),
    "zhipu": VendorEndpoint(
        vendor="zhipu",
        display_name="智谱 GLM 开放平台",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-5",
        notes="OpenAI 风格；JWT 鉴权可选",
    ),
    "moonshot": VendorEndpoint(
        vendor="moonshot",
        display_name="月之暗面 Kimi",
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-128k",
        notes="OpenAI 兼容；按上下文档位计费",
    ),
    "minimax": VendorEndpoint(
        vendor="minimax",
        display_name="MiniMax",
        base_url="https://api.minimaxi.com/v1",
        default_model="MiniMax-Text-01",
        notes="提供 OpenAI 兼容路径",
    ),
}


class DomesticLLMClient:
    """国产模型统一客户端.

    use_mock=True 时所有调用都走 MockLLMClient，便于脱网 demo / 单测。
    真实使用时把 use_mock=False，并提供 api_key。
    """

    def __init__(
        self,
        vendor: str,
        api_key: str | None = None,
        model: str | None = None,
        use_mock: bool = True,
    ) -> None:
        if vendor not in VENDOR_REGISTRY:
            raise KeyError(f"unknown vendor: {vendor}")
        self.endpoint = VENDOR_REGISTRY[vendor]
        self.api_key = api_key
        self.model = model or self.endpoint.default_model
        self.use_mock = use_mock
        self._mock = MockLLMClient(vendor, self.model, base_latency_ms=80, seed=hash(vendor) % 1000)

    def chat(self, messages: list[dict[str, str]], max_tokens: int = 256) -> dict:
        """统一 chat 调用，返回 OpenAI 风格 dict 形式的响应."""
        if self.use_mock:
            r = self._mock.chat(messages, max_tokens=max_tokens)
            return {
                "id": f"mock-{r.provider}",
                "model": r.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": r.content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "total_tokens": r.total_tokens,
                },
            }
        return self._real_call(messages, max_tokens)

    def _real_call(
        self, messages: list[dict[str, str]], max_tokens: int
    ) -> dict:  # pragma: no cover
        """真实调用入口；在示例中故意只放骨架，不在 demo 里联网."""
        raise NotImplementedError(
            "请安装 openai SDK，并使用 base_url=" + self.endpoint.base_url
        )


def main() -> None:  # pragma: no cover
    print("== 国产模型注册表 ==")
    for v, ep in VENDOR_REGISTRY.items():
        print(f"  {v:10s} -> {ep.display_name} | {ep.base_url}")
    print()
    print("== mock 模式调用每家一次 ==")
    for v in VENDOR_REGISTRY:
        cli = DomesticLLMClient(v, use_mock=True)
        resp = cli.chat([{"role": "user", "content": "国产模型谁性价比最高？"}])
        print(f"  [{v}] -> {resp['choices'][0]['message']['content'][:50]}")
    # 也可以把注册表 dump 成 JSON 给前端用
    if "--dump" in sys.argv:
        dump = {v: ep.__dict__ for v, ep in VENDOR_REGISTRY.items()}
        print(json.dumps(dump, ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
