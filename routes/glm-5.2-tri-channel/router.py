"""
GLM-5.2 三通道智能路由器（完整可跑版本）

对应技术文章：13-GLM-5.2 三通道实测 第 7 章 + 附录 B。
本文件把第 7.5 节的 ~50 行骨架扩展为生产可参考实现，新增能力包括：

1. 三通道 Provider 抽象：ZhipuProvider / SCNetProvider / SelfHostProvider
2. 异步健康检查任务（asyncio + httpx async）
3. 主备容灾路由 + circuit breaker（半开探测 + 自动恢复）
4. 多 profile 策略（realtime / batch / longctx）
5. Prometheus 埋点（latency / qps / error_rate / fallback_count）
6. OpenAI 兼容协议（FastAPI 实现 /v1/chat/completions）

设计取舍说明详见 README.md。
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger("glm-router")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ---------------------------------------------------------------------------
# Prometheus 指标定义
# ---------------------------------------------------------------------------

METRIC_REQUESTS = Counter(
    "glm_router_requests_total",
    "路由器接收到的请求总数",
    ["profile", "channel", "outcome"],
)
METRIC_FALLBACK = Counter(
    "glm_router_fallback_total",
    "fallback 触发次数（按 profile 与最终落点 channel 切片）",
    ["profile", "channel"],
)
METRIC_LATENCY = Histogram(
    "glm_router_latency_seconds",
    "请求端到端延迟（含 fallback 时间）",
    ["profile", "channel"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)
METRIC_CIRCUIT_OPEN = Gauge(
    "glm_router_circuit_open",
    "通道熔断状态：1 表示可用，0 表示熔断中",
    ["channel"],
)


# ---------------------------------------------------------------------------
# 基础数据结构
# ---------------------------------------------------------------------------


class Profile(str, Enum):
    """路由 profile：决定 fallback 链的优先级。"""

    REALTIME = "realtime"  # 低延迟优先：智谱主、SCNet 备、自部署兜底
    BATCH = "batch"  # 批量推理成本优先：SCNet 主、自部署备、智谱兜底
    LONGCTX = "longctx"  # 超长上下文：自部署主、SCNet 备、智谱兜底


@dataclass
class ProviderConfig:
    """Provider 配置项（来自 YAML）。"""

    name: str
    base_url: str
    api_key_env: str
    model_alias: str
    priority: int = 100
    weight: float = 1.0
    timeout_s: float = 30.0
    cost_per_million_tokens: float = 0.0  # 单位：元 / 百万 token，仅用于成本路由排序
    enabled: bool = True


@dataclass
class CircuitBreakerConfig:
    """熔断器阈值配置。"""

    failure_threshold: float = 0.5  # success_rate 跌破该值则熔断
    cooldown_s: int = 60  # 熔断后等待多久进入半开
    half_open_success_rate: float = 0.8  # 半开窗口内的 success_rate 起始值
    smoothing_alpha: float = 0.1  # EMA 平滑系数（新值权重）


@dataclass
class RouterConfig:
    """路由器整体配置。"""

    profile: Profile
    providers: list[ProviderConfig]
    fallback_strategy: str = "priority"  # priority | cost | weighted
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    health_check_interval_s: int = 30
    health_check_timeout_s: float = 5.0


@dataclass
class ChannelHealth:
    """单通道运行时健康状态。"""

    success_rate: float = 1.0
    ttft_p95_ms: float = 1000.0
    last_check_at: float = 0.0
    is_open: bool = True  # True = 可用，False = 熔断中


# ---------------------------------------------------------------------------
# Provider 抽象与三通道实现
# ---------------------------------------------------------------------------


class BaseProvider:
    """所有 Provider 的统一抽象。

    子类只需要实现 `chat_completions` 与 `health_check` 两个方法。
    """

    name: str = "base"

    def __init__(self, config: ProviderConfig, http_client: httpx.AsyncClient) -> None:
        self.config = config
        self.http = http_client

    @property
    def api_key(self) -> str:
        """从环境变量读取 API Key，未配置时返回空串。"""
        return os.environ.get(self.config.api_key_env, "")

    async def chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        """转发 OpenAI 兼容的 chat/completions 请求。

        参数:
            payload: 标准 OpenAI Chat Completions 请求体（含 messages 等字段）。
        返回:
            上游返回的 JSON dict。
        """
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # model_alias 允许用 YAML 把"glm-5.2"映射到通道侧的实际模型名
        body = dict(payload)
        body["model"] = self.config.model_alias
        resp = await self.http.post(
            url, json=body, headers=headers, timeout=self.config.timeout_s
        )
        resp.raise_for_status()
        return resp.json()

    async def health_check(self) -> bool:
        """轻量探活：HEAD / GET base_url，2xx/3xx 视为健康。"""
        try:
            resp = await self.http.get(self.config.base_url, timeout=5.0)
            return resp.status_code < 500
        except Exception as exc:  # noqa: BLE001
            logger.warning("health_check 失败 channel=%s err=%s", self.name, exc)
            return False


class ZhipuProvider(BaseProvider):
    """智谱开放平台官方通道。

    base_url 示例: https://open.bigmodel.cn/api/paas/v4
    协议: OpenAI 兼容 chat/completions。
    """

    name = "zhipu"


class SCNetProvider(BaseProvider):
    """国家超算互联网通道。

    base_url 示例: https://api.scnet.cn/api/llm/v1（以控制台为准）。
    协议: OpenAI 兼容；模型别名以平台「Chat → 模型 API」入口的实时显示为准。
    """

    name = "scnet"


class SelfHostProvider(BaseProvider):
    """自部署通道（vLLM / SGLang 等推理框架）。

    base_url 由 SELFHOST_BASE_URL 环境变量注入，例如
    http://your-vllm-server:8000/v1。
    """

    name = "self"


PROVIDER_CLASSES: dict[str, type[BaseProvider]] = {
    "zhipu": ZhipuProvider,
    "scnet": SCNetProvider,
    "self": SelfHostProvider,
}


# ---------------------------------------------------------------------------
# 路由器主体
# ---------------------------------------------------------------------------


class TriChannelRouter:
    """三通道智能路由器。

    主要职责:
        1. 按 profile 与策略（priority / cost）排出 fallback 链；
        2. 按链路顺序调用，捕获异常后切换下一个；
        3. 维护各通道的健康状态与熔断器；
        4. 暴露 Prometheus 指标。
    """

    def __init__(self, config: RouterConfig) -> None:
        self.config = config
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        self._providers: dict[str, BaseProvider] = {}
        self._health: dict[str, ChannelHealth] = {}
        self._health_task: asyncio.Task | None = None

        for pc in config.providers:
            if not pc.enabled:
                continue
            cls = PROVIDER_CLASSES.get(pc.name)
            if cls is None:
                logger.warning("未知的 provider name=%s，已跳过", pc.name)
                continue
            self._providers[pc.name] = cls(pc, self._http)
            self._health[pc.name] = ChannelHealth()
            METRIC_CIRCUIT_OPEN.labels(channel=pc.name).set(1)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """启动后台健康检查任务。"""
        if self._health_task is None:
            self._health_task = asyncio.create_task(self._health_loop())
            logger.info("健康检查后台任务已启动 interval=%ss", self.config.health_check_interval_s)

    async def stop(self) -> None:
        """优雅关闭：取消健康检查任务、关闭 http client。"""
        if self._health_task is not None:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None
        await self._http.aclose()

    # ------------------------------------------------------------------ #
    # 路由决策
    # ------------------------------------------------------------------ #

    def _build_chain(self) -> list[str]:
        """根据 fallback_strategy 构造 fallback 链。

        返回:
            按调度优先级排好序的 channel 名称列表。
        """
        candidates = [p for p in self.config.providers if p.enabled and p.name in self._providers]
        if self.config.fallback_strategy == "cost":
            # 成本最优：cost_per_million_tokens 升序
            candidates.sort(key=lambda p: (p.cost_per_million_tokens, p.priority))
        else:
            # 默认 priority 升序（数字越小越优先）
            candidates.sort(key=lambda p: (p.priority, -p.weight))
        return [p.name for p in candidates]

    async def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        """执行一次三通道智能路由调用。

        参数:
            payload: OpenAI 兼容的 chat/completions 请求体。
        返回:
            上游 JSON 结果，并附加 `router_chain` / `router_picked` 字段。
        异常:
            RuntimeError: 所有通道都失败时抛出。
        """
        chain = self._build_chain()
        last_exc: Exception | None = None
        profile = self.config.profile.value
        first_choice = chain[0] if chain else "none"

        for idx, ch in enumerate(chain):
            health = self._health[ch]
            if not health.is_open:
                logger.info("熔断中跳过 channel=%s", ch)
                continue
            t0 = time.time()
            try:
                result = await self._providers[ch].chat_completions(payload)
                elapsed = time.time() - t0
                self._on_success(ch, elapsed)
                METRIC_REQUESTS.labels(profile=profile, channel=ch, outcome="ok").inc()
                METRIC_LATENCY.labels(profile=profile, channel=ch).observe(elapsed)
                if idx > 0:
                    # 出现了 fallback：链上有更高优先级通道未能成功
                    METRIC_FALLBACK.labels(profile=profile, channel=ch).inc()
                    logger.warning(
                        "fallback 命中 first=%s picked=%s idx=%d", first_choice, ch, idx
                    )
                return {**result, "router_chain": chain, "router_picked": ch}
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self._on_failure(ch)
                METRIC_REQUESTS.labels(profile=profile, channel=ch, outcome="error").inc()
                logger.warning("channel=%s 调用失败 err=%s", ch, exc)
                continue

        raise RuntimeError(
            f"all channels exhausted for profile={profile} chain={chain}: {last_exc}"
        )

    # ------------------------------------------------------------------ #
    # 熔断器与健康状态
    # ------------------------------------------------------------------ #

    def _on_success(self, channel: str, elapsed_s: float) -> None:
        """成功调用后滚动更新健康指标（EMA 平滑）。"""
        cb = self.config.circuit_breaker
        h = self._health[channel]
        h.ttft_p95_ms = (1 - cb.smoothing_alpha) * h.ttft_p95_ms + cb.smoothing_alpha * (
            elapsed_s * 1000
        )
        h.success_rate = min(1.0, h.success_rate + 0.001)

    def _on_failure(self, channel: str) -> None:
        """失败后扣减 success_rate，触达阈值则熔断并启动半开恢复任务。"""
        cb = self.config.circuit_breaker
        h = self._health[channel]
        h.success_rate = max(0.0, h.success_rate - 0.05)
        if h.success_rate < cb.failure_threshold and h.is_open:
            h.is_open = False
            METRIC_CIRCUIT_OPEN.labels(channel=channel).set(0)
            logger.error("channel=%s 熔断 success_rate=%.3f", channel, h.success_rate)
            asyncio.create_task(self._reset_circuit(channel, cb.cooldown_s))

    async def _reset_circuit(self, channel: str, after: int) -> None:
        """熔断窗口结束后半开恢复，给一次试探机会。"""
        await asyncio.sleep(after)
        h = self._health[channel]
        h.is_open = True
        h.success_rate = self.config.circuit_breaker.half_open_success_rate
        METRIC_CIRCUIT_OPEN.labels(channel=channel).set(1)
        logger.info("channel=%s 熔断恢复（半开）", channel)

    async def _health_loop(self) -> None:
        """定时巡检每个 provider 的健康端点。"""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval_s)
                for name, provider in self._providers.items():
                    ok = await provider.health_check()
                    self._health[name].last_check_at = time.time()
                    if not ok and self._health[name].is_open:
                        # 探活失败但目前未熔断：扣一次失败积分
                        self._on_failure(name)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("health_loop 异常 err=%s", exc)

    # ------------------------------------------------------------------ #
    # 调试 / 状态查询
    # ------------------------------------------------------------------ #

    def status(self) -> dict[str, Any]:
        """返回当前路由器状态快照（供 /status 端点使用）。"""
        return {
            "profile": self.config.profile.value,
            "fallback_strategy": self.config.fallback_strategy,
            "chain": self._build_chain(),
            "channels": {
                name: {
                    "is_open": h.is_open,
                    "success_rate": round(h.success_rate, 4),
                    "ttft_p95_ms": round(h.ttft_p95_ms, 2),
                    "last_check_at": h.last_check_at,
                }
                for name, h in self._health.items()
            },
        }


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------


def _expand_env(value: Any) -> Any:
    """递归替换字符串中的 ${VAR} 引用为环境变量值（未设置时保留原文）。"""
    import re

    pattern = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")

    def repl(s: str) -> str:
        return pattern.sub(lambda m: os.environ.get(m.group(1), m.group(0)), s)

    if isinstance(value, str):
        return repl(value)
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    return value


def load_router_config(yaml_path: str | Path) -> RouterConfig:
    """从 YAML 文件加载路由配置。

    YAML 顶层 schema:
        profile: realtime | batch | longctx
        providers: [{name, base_url, api_key_env, model_alias, priority,
                     weight, timeout_s, cost_per_million_tokens, enabled}]
        router:
          fallback_strategy: priority | cost
          circuit_breaker: {failure_threshold, cooldown_s, ...}
        observability:
          health_check_interval_s: 30

    支持 ${ENV_VAR} 形式的环境变量插值（用于 SELFHOST_BASE_URL 等动态值）。
    """
    path = Path(yaml_path)
    with path.open("r", encoding="utf-8") as fp:
        raw = yaml.safe_load(fp)

    raw = _expand_env(raw)
    providers = [ProviderConfig(**p) for p in raw["providers"]]

    router_section = raw.get("router", {}) or {}
    cb_raw = router_section.get("circuit_breaker", {}) or {}
    cb = CircuitBreakerConfig(
        failure_threshold=cb_raw.get("failure_threshold", 0.5),
        cooldown_s=cb_raw.get("cooldown_s", 60),
        half_open_success_rate=cb_raw.get("half_open_success_rate", 0.8),
        smoothing_alpha=cb_raw.get("smoothing_alpha", 0.1),
    )

    obs = raw.get("observability", {}) or {}

    return RouterConfig(
        profile=Profile(raw["profile"]),
        providers=providers,
        fallback_strategy=router_section.get("fallback_strategy", "priority"),
        circuit_breaker=cb,
        health_check_interval_s=obs.get("health_check_interval_s", 30),
        health_check_timeout_s=obs.get("health_check_timeout_s", 5.0),
    )


# ---------------------------------------------------------------------------
# FastAPI 应用（OpenAI 兼容协议）
# ---------------------------------------------------------------------------


_router_instance: TriChannelRouter | None = None


def get_router() -> TriChannelRouter:
    """供 FastAPI handler 使用的全局 router 取值器。"""
    if _router_instance is None:
        raise RuntimeError("router 尚未初始化，请通过 lifespan 启动")
    return _router_instance


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期钩子：启动时加载配置 + 启动健康检查。"""
    global _router_instance
    config_path = os.environ.get(
        "ROUTER_CONFIG",
        str(Path(__file__).parent / "configs" / "profile_realtime.yml"),
    )
    cfg = load_router_config(config_path)
    _router_instance = TriChannelRouter(cfg)
    await _router_instance.start()
    logger.info("router 启动完成 profile=%s", cfg.profile.value)
    try:
        yield
    finally:
        await _router_instance.stop()
        _router_instance = None


def create_app() -> FastAPI:
    """构造 FastAPI 应用，OpenAI 兼容路径 /v1/chat/completions。"""
    app = FastAPI(title="GLM-5.2 Tri-Channel Router", version="1.0.0", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/status")
    async def status() -> dict[str, Any]:
        return get_router().status()

    @app.get("/metrics")
    async def metrics() -> Response:
        # Prometheus text exposition format
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"bad json: {exc}") from exc
        if "messages" not in payload:
            raise HTTPException(status_code=400, detail="missing 'messages'")
        try:
            result = await get_router().chat(payload)
            return JSONResponse(result)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "router:app",
        host=os.environ.get("ROUTER_HOST", "0.0.0.0"),
        port=int(os.environ.get("ROUTER_PORT", "8000")),
        reload=False,
    )
