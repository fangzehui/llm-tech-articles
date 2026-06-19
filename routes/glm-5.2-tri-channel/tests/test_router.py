"""
路由器单元测试集：通过 mock provider 验证核心路由逻辑。

覆盖用例:
    1. provider 选择：按 priority 排序构造 fallback 链
    2. fallback 触发：主通道异常时自动切到备通道
    3. circuit breaker：连续失败触发熔断 & 半开恢复
    4. metrics 暴露：/metrics 端点可被 prometheus 解析
    5. OpenAI 协议兼容：/v1/chat/completions 能正确转发 messages
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# 把上一层目录加入 import 路径，便于 `import router`
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import router as router_mod  # noqa: E402


# ---------------------------------------------------------------------------
# 公共 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def realtime_config() -> router_mod.RouterConfig:
    """构造 realtime profile 的 RouterConfig（不做实际网络调用）。"""
    providers = [
        router_mod.ProviderConfig(
            name="zhipu",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            api_key_env="ZHIPU_API_KEY",
            model_alias="glm-5.2",
            priority=10,
            cost_per_million_tokens=22.0,
        ),
        router_mod.ProviderConfig(
            name="scnet",
            base_url="https://api.scnet.cn/api/llm/v1",
            api_key_env="SCNET_API_KEY",
            model_alias="glm-5.2",
            priority=20,
            cost_per_million_tokens=18.0,
        ),
        router_mod.ProviderConfig(
            name="self",
            base_url="http://self:8000/v1",
            api_key_env="SELFHOST_API_KEY",
            model_alias="glm-5.2",
            priority=30,
            cost_per_million_tokens=8.0,
        ),
    ]
    return router_mod.RouterConfig(
        profile=router_mod.Profile.REALTIME,
        providers=providers,
        fallback_strategy="priority",
        circuit_breaker=router_mod.CircuitBreakerConfig(
            failure_threshold=0.5, cooldown_s=1, half_open_success_rate=0.8
        ),
    )


def _stub_provider(
    r: router_mod.TriChannelRouter,
    name: str,
    *,
    fail: bool = False,
    payload: dict[str, Any] | None = None,
) -> None:
    """把指定 channel 的 chat_completions 替换成可控的 stub。"""

    async def fake_chat(p: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
        if fail:
            raise RuntimeError(f"stub fail on {name}")
        return payload or {"id": "test", "channel": name, "choices": []}

    r._providers[name].chat_completions = fake_chat  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 1. provider 选择
# ---------------------------------------------------------------------------


def test_build_chain_priority(realtime_config):
    """priority 策略：按 priority 升序排链。"""
    r = router_mod.TriChannelRouter(realtime_config)
    assert r._build_chain() == ["zhipu", "scnet", "self"]


def test_build_chain_cost(realtime_config):
    """cost 策略：按 cost_per_million_tokens 升序排链。"""
    realtime_config.fallback_strategy = "cost"
    r = router_mod.TriChannelRouter(realtime_config)
    # self(8) < scnet(18) < zhipu(22)
    assert r._build_chain() == ["self", "scnet", "zhipu"]


# ---------------------------------------------------------------------------
# 2. fallback 触发
# ---------------------------------------------------------------------------


def test_fallback_when_primary_fails(realtime_config):
    """主通道异常时自动落到第二条。"""
    r = router_mod.TriChannelRouter(realtime_config)
    _stub_provider(r, "zhipu", fail=True)
    _stub_provider(r, "scnet", payload={"id": "x", "choices": [{"message": {"content": "ok"}}]})
    _stub_provider(r, "self", fail=True)

    result = asyncio.run(r.chat({"messages": [{"role": "user", "content": "hi"}]}))
    assert result["router_picked"] == "scnet"
    assert result["router_chain"] == ["zhipu", "scnet", "self"]


def test_all_channels_exhausted_raises(realtime_config):
    """全部通道异常应抛 RuntimeError。"""
    r = router_mod.TriChannelRouter(realtime_config)
    for n in ("zhipu", "scnet", "self"):
        _stub_provider(r, n, fail=True)

    with pytest.raises(RuntimeError, match="all channels exhausted"):
        asyncio.run(r.chat({"messages": []}))


# ---------------------------------------------------------------------------
# 3. circuit breaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_trips_then_recovers(realtime_config):
    """连续失败把 success_rate 打穿后熔断；cooldown 后半开恢复。"""

    async def scenario() -> tuple[bool, bool]:
        r = router_mod.TriChannelRouter(realtime_config)
        # 让 zhipu 一直失败，scnet 也失败但保持半开状态以便观察
        _stub_provider(r, "zhipu", fail=True)
        _stub_provider(r, "scnet", payload={"choices": []})
        _stub_provider(r, "self", payload={"choices": []})

        # 连续触发 zhipu 失败，最多 50 次，加速 success_rate 跌破 0.5
        for _ in range(50):
            try:
                await r.chat({"messages": []})
            except RuntimeError:
                pass

        opened = not r._health["zhipu"].is_open
        # 等待 cooldown 后半开恢复
        await asyncio.sleep(realtime_config.circuit_breaker.cooldown_s + 0.5)
        recovered = r._health["zhipu"].is_open
        return opened, recovered

    opened, recovered = asyncio.run(scenario())
    assert opened, "应已熔断"
    assert recovered, "cooldown 后应半开恢复"


# ---------------------------------------------------------------------------
# 4. metrics 暴露
# ---------------------------------------------------------------------------


def test_metrics_endpoint_exposed():
    """/metrics 端点应返回 Prometheus 文本格式。"""
    # 不通过 lifespan 启动；直接构造一个最小 app + 注入 router
    app = router_mod.create_app()
    # 用 fixture-style 直接塞一个轻量 router 给全局
    cfg = router_mod.RouterConfig(
        profile=router_mod.Profile.REALTIME,
        providers=[
            router_mod.ProviderConfig(
                name="zhipu",
                base_url="https://open.bigmodel.cn/api/paas/v4",
                api_key_env="ZHIPU_API_KEY",
                model_alias="glm-5.2",
                priority=10,
            )
        ],
    )
    router_mod._router_instance = router_mod.TriChannelRouter(cfg)
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "glm_router_requests_total" in resp.text or "python_info" in resp.text
    finally:
        router_mod._router_instance = None


# ---------------------------------------------------------------------------
# 5. OpenAI 协议兼容
# ---------------------------------------------------------------------------


def test_openai_chat_completions_protocol(realtime_config):
    """/v1/chat/completions 能正确接收 messages 并返回 router_picked。"""
    app = router_mod.create_app()
    r = router_mod.TriChannelRouter(realtime_config)
    _stub_provider(
        r,
        "zhipu",
        payload={
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "choices": [{"message": {"role": "assistant", "content": "pong"}, "finish_reason": "stop"}],
        },
    )
    router_mod._router_instance = r

    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "ping"}]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["router_picked"] == "zhipu"
        assert body["choices"][0]["message"]["content"] == "pong"
    finally:
        router_mod._router_instance = None


def test_openai_protocol_missing_messages_returns_400():
    """缺失 messages 字段应返回 400。"""
    app = router_mod.create_app()
    cfg = router_mod.RouterConfig(
        profile=router_mod.Profile.REALTIME,
        providers=[
            router_mod.ProviderConfig(
                name="zhipu",
                base_url="https://open.bigmodel.cn/api/paas/v4",
                api_key_env="ZHIPU_API_KEY",
                model_alias="glm-5.2",
                priority=10,
            )
        ],
    )
    router_mod._router_instance = router_mod.TriChannelRouter(cfg)
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/v1/chat/completions", json={"model": "glm-5.2"})
        assert resp.status_code == 400
    finally:
        router_mod._router_instance = None
