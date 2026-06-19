"""第 04 篇配套 demo：retry + circuit breaker + timeout 三件套.

通过装饰器组合提供生产环境最常用的三种容错原语：
- retry: 指数退避重试
- circuit_breaker: 失败次数触发熔断，进入半开/关闭循环
- timeout: 单次调用硬超时（基于线程，非 asyncio）

可独立运行：
    python ha_demo.py
"""

from __future__ import annotations

import functools
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


class TimeoutError_(Exception):
    """统一的超时异常."""


class CircuitOpenError(Exception):
    """熔断器处于 open 状态时直接抛出."""


def with_timeout(seconds: float) -> Callable:
    """硬超时装饰器，基于子线程实现.

    Args:
        seconds: 超时阈值，秒

    注意：这是一个 demo 实现；生产建议用 asyncio 或 signal.SIGALRM。
    """

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrap(*args: Any, **kwargs: Any) -> Any:
            result: list[Any] = []
            err: list[BaseException] = []

            def runner() -> None:
                try:
                    result.append(fn(*args, **kwargs))
                except BaseException as e:  # noqa: BLE001
                    err.append(e)

            t = threading.Thread(target=runner, daemon=True)
            t.start()
            t.join(seconds)
            if t.is_alive():
                raise TimeoutError_(f"call exceeded {seconds}s")
            if err:
                raise err[0]
            return result[0]

        return wrap

    return deco


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    jitter: bool = True,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> Callable:
    """指数退避重试装饰器.

    Args:
        max_attempts: 总尝试次数（包含首次）
        base_delay: 初始退避，秒
        max_delay: 最大退避，秒
        jitter: 是否加 0~base_delay 抖动
        retry_on: 命中这些异常类型才重试
    """

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrap(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except retry_on as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                    if jitter:
                        delay += random.uniform(0, base_delay)
                    time.sleep(delay)
            assert last_exc is not None
            raise last_exc

        return wrap

    return deco


@dataclass
class CircuitBreaker:
    """简化版熔断器，三态：closed / open / half_open.

    Attributes:
        fail_threshold: 连续失败多少次后打开
        recovery_seconds: open 状态停留多久后进入 half_open
        half_open_allow: half_open 允许的探测次数
    """

    fail_threshold: int = 5
    recovery_seconds: float = 10.0
    half_open_allow: int = 1
    _state: str = "closed"
    _fail_count: int = 0
    _opened_at: float = 0.0
    _half_open_inflight: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _allow(self) -> bool:
        with self._lock:
            now = time.time()
            if self._state == "open":
                if now - self._opened_at >= self.recovery_seconds:
                    self._state = "half_open"
                    self._half_open_inflight = 0
                else:
                    return False
            if self._state == "half_open":
                if self._half_open_inflight >= self.half_open_allow:
                    return False
                self._half_open_inflight += 1
            return True

    def _on_success(self) -> None:
        with self._lock:
            self._fail_count = 0
            self._state = "closed"
            self._half_open_inflight = 0

    def _on_failure(self) -> None:
        with self._lock:
            self._fail_count += 1
            if self._state == "half_open" or self._fail_count >= self.fail_threshold:
                self._state = "open"
                self._opened_at = time.time()
                self._half_open_inflight = 0

    def __call__(self, fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrap(*args: Any, **kwargs: Any) -> Any:
            if not self._allow():
                raise CircuitOpenError("circuit is open")
            try:
                ret = fn(*args, **kwargs)
            except Exception:
                self._on_failure()
                raise
            self._on_success()
            return ret

        return wrap

    @property
    def state(self) -> str:
        return self._state


def main() -> None:  # pragma: no cover
    counter = {"n": 0}
    cb = CircuitBreaker(fail_threshold=3, recovery_seconds=0.5)

    @cb
    @with_retry(max_attempts=2, base_delay=0.05)
    @with_timeout(0.3)
    def flaky(name: str) -> str:
        counter["n"] += 1
        if counter["n"] < 5:
            raise RuntimeError("backend hiccup")
        return f"hello {name}"

    for i in range(8):
        try:
            print(i, flaky("world"), "state=", cb.state)
        except Exception as exc:  # noqa: BLE001
            print(i, type(exc).__name__, exc, "state=", cb.state)
        time.sleep(0.1)


if __name__ == "__main__":  # pragma: no cover
    main()
