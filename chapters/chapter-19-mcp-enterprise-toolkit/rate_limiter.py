"""令牌桶限流 + 配额管理。

为什么限流必须放在 MCP Gateway 这一层？
======================================
- Agent 失控时一秒钟可以发出几百次 ``tools/call``，会瞬间把下游 SaaS API
  额度打爆，且 SaaS 侧的限流通常按"调用方"而非"租户"判断；
- Host / Client / Server 三层都各自做限流会导致策略分散、无法审计；
- 把限流统一收口到 Gateway 才能做"按租户 / 按 user / 按 tool"的多维度配额。

本模块提供两类原语：
1. ``TokenBucket``：经典令牌桶，毫秒级精度，纯标准库；
2. ``QuotaTracker``：按窗口（小时 / 天）的硬上限计数；
3. ``RateLimiter``：把多维度 key（``tenant`` × ``user`` × ``tool``）映射到上
   面两个原语。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


# --------------------- 异常 ---------------------


class RateLimitError(Exception):
    """限流命中时统一抛出，由 Gateway 翻译为 HTTP 429。"""

    def __init__(self, key: str, reason: str, retry_after: float):
        super().__init__(f"rate limited: key={key} reason={reason}")
        self.key = key
        self.reason = reason
        self.retry_after = retry_after


# --------------------- 令牌桶 ---------------------


@dataclass
class TokenBucket:
    """经典令牌桶：``capacity`` 容量、``refill_rate`` token/秒。

    线程安全：内部 ``_lock``。
    """

    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last: float = field(init=False)
    _lock: threading.Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.capacity <= 0 or self.refill_rate <= 0:
            raise ValueError("capacity / refill_rate 必须为正")
        self.tokens = float(self.capacity)
        self.last = time.monotonic()
        self._lock = threading.Lock()

    def try_consume(self, n: float = 1.0) -> bool:
        with self._lock:
            self._refill()
            if self.tokens + 1e-9 < n:
                return False
            self.tokens -= n
            return True

    def retry_after(self, n: float = 1.0) -> float:
        """返回需要等待几秒钟才能拿到 n 个 token。"""
        with self._lock:
            self._refill()
            if self.tokens + 1e-9 >= n:
                return 0.0
            return (n - self.tokens) / self.refill_rate

    def _refill(self) -> None:
        now = time.monotonic()
        delta = now - self.last
        if delta > 0:
            self.tokens = min(self.capacity, self.tokens + delta * self.refill_rate)
            self.last = now


# --------------------- 配额（按窗口硬上限）---------------------


@dataclass
class _Window:
    start: float
    used: int


class QuotaTracker:
    """按 ``window_seconds`` 窗口的硬上限计数。

    比令牌桶严格：用满即拒绝，不允许任何 burst。
    例如"单租户每天 10 万次 tools/call"用这个。
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("limit / window_seconds 必须为正")
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows: dict[str, _Window] = {}
        self._lock = threading.Lock()

    def try_consume(self, key: str, n: int = 1) -> bool:
        with self._lock:
            now = time.monotonic()
            w = self._windows.get(key)
            if w is None or now - w.start >= self.window_seconds:
                self._windows[key] = _Window(start=now, used=n)
                return n <= self.limit
            if w.used + n > self.limit:
                return False
            w.used += n
            return True

    def usage(self, key: str) -> int:
        with self._lock:
            w = self._windows.get(key)
            if w is None:
                return 0
            if time.monotonic() - w.start >= self.window_seconds:
                return 0
            return w.used

    def retry_after(self, key: str) -> float:
        with self._lock:
            w = self._windows.get(key)
            if w is None:
                return 0.0
            elapsed = time.monotonic() - w.start
            if elapsed >= self.window_seconds:
                return 0.0
            if w.used >= self.limit:
                return self.window_seconds - elapsed
            return 0.0


# --------------------- 组合限流器 ---------------------


@dataclass
class RatePolicy:
    """单条策略：``key_template`` 决定限流键，``capacity/refill`` 是 burst 与稳态。"""

    name: str
    key_template: str  # e.g. "{tenant}:{tool}"
    capacity: float
    refill_rate: float  # tokens per second
    daily_quota: int | None = None  # 当日上限，可选


class RateLimiter:
    """企业 MCP Gateway 限流主入口。

    用法::

        limiter = RateLimiter([
            RatePolicy("per_user_tool", "{tenant}:{user}:{tool}",
                       capacity=20, refill_rate=2.0),
            RatePolicy("per_tenant",    "{tenant}",
                       capacity=200, refill_rate=20.0, daily_quota=100_000),
        ])
        limiter.check({"tenant": "acme", "user": "u1", "tool": "gh.create_issue"})
    """

    def __init__(self, policies: list[RatePolicy]) -> None:
        if not policies:
            raise ValueError("至少要配一条策略")
        self.policies = policies
        self._buckets: dict[str, TokenBucket] = {}
        self._quota = QuotaTracker(
            limit=max(p.daily_quota or 0 for p in policies) or 10**9,
            window_seconds=86400,
        )
        self._lock = threading.Lock()

    def _bucket(self, key: str, policy: RatePolicy) -> TokenBucket:
        full_key = f"{policy.name}::{key}"
        with self._lock:
            b = self._buckets.get(full_key)
            if b is None:
                b = TokenBucket(capacity=policy.capacity, refill_rate=policy.refill_rate)
                self._buckets[full_key] = b
            return b

    def check(self, context: dict[str, Any]) -> None:
        """所有策略都得过；任意一条拒绝即抛 ``RateLimitError``。"""
        for p in self.policies:
            try:
                key = p.key_template.format(**context)
            except KeyError as e:
                raise ValueError(
                    f"策略 {p.name!r} 的 key_template={p.key_template!r} "
                    f"需要 context 字段 {e}"
                ) from e
            bucket = self._bucket(key, p)
            if not bucket.try_consume():
                raise RateLimitError(
                    key=key, reason=f"policy={p.name} bucket_empty",
                    retry_after=bucket.retry_after(),
                )
            if p.daily_quota and not self._quota.try_consume(key):
                raise RateLimitError(
                    key=key, reason=f"policy={p.name} daily_quota_exceeded",
                    retry_after=self._quota.retry_after(key),
                )


__all__ = [
    "TokenBucket",
    "QuotaTracker",
    "RateLimiter",
    "RatePolicy",
    "RateLimitError",
]
