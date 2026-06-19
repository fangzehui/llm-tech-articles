"""第 08 篇配套 demo：企业级 Token 配额管理器（Redis mock）.

提供：
- InMemoryRedis：单进程线程安全的极简 Redis 替身（incrby / expire / get / ttl）
- QuotaManager：按 (tenant, scope) 维度的日 / 月 token 配额限制
- 调用前预占 + 调用后回填的两段式记账（避免估算偏差长期累积）

可独立运行：
    python quota_manager.py
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


class QuotaExceededError(RuntimeError):
    """超出配额时抛出."""


class InMemoryRedis:
    """内存版的 mini Redis，线程安全；只覆盖 demo 用到的命令.

    生产请把这个类替换为 redis-py 的 Redis 实例，接口完全一致。
    """

    def __init__(self) -> None:
        self._data: dict[str, int] = {}
        self._expire: dict[str, float] = {}
        self._lock = threading.Lock()

    def _expire_check(self, key: str) -> None:
        exp = self._expire.get(key)
        if exp is not None and time.time() >= exp:
            self._data.pop(key, None)
            self._expire.pop(key, None)

    def get(self, key: str) -> int:
        with self._lock:
            self._expire_check(key)
            return int(self._data.get(key, 0))

    def incrby(self, key: str, delta: int) -> int:
        """原子 incrby，新建 key 默认值 0，与 redis 行为一致."""
        with self._lock:
            self._expire_check(key)
            new_val = int(self._data.get(key, 0)) + delta
            self._data[key] = new_val
            return new_val

    def expire(self, key: str, ttl_seconds: float) -> None:
        with self._lock:
            self._expire[key] = time.time() + ttl_seconds

    def ttl(self, key: str) -> float:
        with self._lock:
            exp = self._expire.get(key)
            if exp is None:
                return -1.0
            return max(0.0, exp - time.time())


@dataclass
class QuotaPolicy:
    """配额策略.

    Attributes:
        daily_token_limit: 单租户日 token 上限，0 表示不限
        monthly_token_limit: 单租户月 token 上限，0 表示不限
        soft_warn_ratio: 达到此比例时返回 warn=True，但仍允许调用
    """

    daily_token_limit: int = 1_000_000
    monthly_token_limit: int = 20_000_000
    soft_warn_ratio: float = 0.8


@dataclass
class ReserveResult:
    """配额预占结果."""

    allowed: bool
    warn: bool
    used_daily: int
    used_monthly: int
    reason: str = ""


@dataclass
class QuotaManager:
    """两段式 Token 配额管理器.

    使用方式：
        qm = QuotaManager(...)
        ok = qm.reserve(tenant, estimated_tokens)
        # ... 调 LLM ...
        qm.commit(tenant, real_tokens, estimated_tokens)
    """

    redis: InMemoryRedis
    policy: QuotaPolicy = field(default_factory=QuotaPolicy)

    @staticmethod
    def _bucket_keys(tenant: str) -> tuple[str, str]:
        today = time.strftime("%Y%m%d")
        month = time.strftime("%Y%m")
        return f"q:{tenant}:d:{today}", f"q:{tenant}:m:{month}"

    def reserve(self, tenant: str, estimated_tokens: int) -> ReserveResult:
        """调用前预占配额."""
        d_key, m_key = self._bucket_keys(tenant)
        used_d = self.redis.get(d_key)
        used_m = self.redis.get(m_key)

        new_d = used_d + estimated_tokens
        new_m = used_m + estimated_tokens

        if self.policy.daily_token_limit and new_d > self.policy.daily_token_limit:
            return ReserveResult(False, False, used_d, used_m, "daily limit exceeded")
        if self.policy.monthly_token_limit and new_m > self.policy.monthly_token_limit:
            return ReserveResult(False, False, used_d, used_m, "monthly limit exceeded")

        self.redis.incrby(d_key, estimated_tokens)
        self.redis.incrby(m_key, estimated_tokens)
        # 给 key 设过期，避免长尾留存：日桶 36h，月桶 35d
        self.redis.expire(d_key, 36 * 3600)
        self.redis.expire(m_key, 35 * 86400)

        warn = False
        if self.policy.daily_token_limit:
            warn |= new_d / self.policy.daily_token_limit >= self.policy.soft_warn_ratio
        if self.policy.monthly_token_limit:
            warn |= new_m / self.policy.monthly_token_limit >= self.policy.soft_warn_ratio
        return ReserveResult(True, warn, new_d, new_m)

    def commit(self, tenant: str, real_tokens: int, estimated_tokens: int) -> None:
        """调用后用真实用量回填差额."""
        diff = real_tokens - estimated_tokens
        if diff == 0:
            return
        d_key, m_key = self._bucket_keys(tenant)
        self.redis.incrby(d_key, diff)
        self.redis.incrby(m_key, diff)


def main() -> None:  # pragma: no cover
    redis = InMemoryRedis()
    qm = QuotaManager(redis, QuotaPolicy(daily_token_limit=10_000, monthly_token_limit=100_000))
    for i in range(15):
        est = 1500
        rv = qm.reserve("tenant-A", est)
        if not rv.allowed:
            print(f"call {i}: BLOCKED -> {rv.reason} (used_d={rv.used_daily})")
            break
        # 假装真实用量比估算多 100
        qm.commit("tenant-A", est + 100, est)
        flag = "(WARN)" if rv.warn else ""
        print(f"call {i}: OK used_d={rv.used_daily + 100} {flag}")


if __name__ == "__main__":  # pragma: no cover
    main()
