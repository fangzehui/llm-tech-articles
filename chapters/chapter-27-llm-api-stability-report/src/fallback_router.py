"""Fallback / circuit-breaker router for multi-provider LLM API calls.

Implements the dataclass-driven fallback strategy from Section 5 of the
article: primary provider -> fallbacks list, with circuit breaker keyed
on consecutive failures and P99 latency ceiling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProviderHealth:
    """Runtime health state for a single upstream provider."""

    name: str
    consecutive_failures: int = 0
    last_p99_ms: float = 0.0
    circuit_open_until_ts: float = 0.0

    def record_success(self, p99_ms: Optional[float] = None) -> None:
        self.consecutive_failures = 0
        if p99_ms is not None:
            self.last_p99_ms = p99_ms

    def record_failure(self) -> None:
        self.consecutive_failures += 1


@dataclass
class FallbackRule:
    """Primary + fallbacks + thresholds."""

    primary: str
    fallbacks: List[str] = field(default_factory=list)
    max_consecutive_failures: int = 3
    p99_ceiling_ms: float = 8_000.0
    open_duration_sec: float = 60.0

    def should_open_circuit(self, h: ProviderHealth) -> bool:
        if h.consecutive_failures >= self.max_consecutive_failures:
            return True
        if h.last_p99_ms > self.p99_ceiling_ms:
            return True
        return False


@dataclass
class RouteDecision:
    chosen: str
    fallback_used: bool
    reason: str
    tried: List[str] = field(default_factory=list)


def choose_provider(
    rule: FallbackRule,
    health: Dict[str, ProviderHealth],
    now_ts: float,
) -> RouteDecision:
    """Pick a healthy provider in primary -> fallbacks order."""
    candidates = [rule.primary, *rule.fallbacks]
    tried: List[str] = []
    for idx, name in enumerate(candidates):
        tried.append(name)
        h = health.setdefault(name, ProviderHealth(name=name))
        if h.circuit_open_until_ts > now_ts:
            continue
        if rule.should_open_circuit(h):
            h.circuit_open_until_ts = now_ts + rule.open_duration_sec
            continue
        return RouteDecision(
            chosen=name,
            fallback_used=(idx != 0),
            reason="primary_ok" if idx == 0 else f"fallback_to_{name}",
            tried=tried,
        )
    return RouteDecision(chosen="", fallback_used=True, reason="all_unhealthy", tried=tried)


def close_circuit_after_recovery(
    health: Dict[str, ProviderHealth],
    provider: str,
    p99_ms: float,
) -> None:
    """Explicit helper: mark provider as recovered."""
    h = health.setdefault(provider, ProviderHealth(name=provider))
    h.record_success(p99_ms=p99_ms)
    h.circuit_open_until_ts = 0.0


if __name__ == "__main__":
    import time

    rule = FallbackRule(
        primary="deepseek-v3.2",
        fallbacks=["doubao-1.5-pro", "qwen-max"],
        max_consecutive_failures=2,
        p99_ceiling_ms=8000,
        open_duration_sec=30,
    )
    health: Dict[str, ProviderHealth] = {}
    now = time.time()

    # simulate two failures on primary -> should trigger circuit
    health["deepseek-v3.2"] = ProviderHealth("deepseek-v3.2", consecutive_failures=2)
    d = choose_provider(rule, health, now)
    print(f"decision={d.chosen} fallback_used={d.fallback_used} reason={d.reason}")
