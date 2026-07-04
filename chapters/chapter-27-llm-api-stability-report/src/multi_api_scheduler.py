"""Multi-provider redundancy scheduler.

Section 6 of the article: 3-D scoring over
(reliability_tier x latency_grade x cost_penalty) selecting best provider
for a given TaskTier.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List


class TaskTier(Enum):
    CRITICAL = "critical"
    STANDARD = "standard"
    BATCH = "batch"


RELIABILITY_MAP = {"A": 3.0, "B": 2.0, "C": 1.0}
LATENCY_MAP = {"<3s": 3.0, "3-8s": 2.0, ">8s": 1.0}


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    tier_reliability: str
    input_price_per_m: float
    output_price_per_m: float
    latency_grade: str

    def __post_init__(self) -> None:
        if self.tier_reliability not in RELIABILITY_MAP:
            raise ValueError(f"bad reliability tier: {self.tier_reliability}")
        if self.latency_grade not in LATENCY_MAP:
            raise ValueError(f"bad latency grade: {self.latency_grade}")


PROVIDERS_2026H1: List[ProviderProfile] = [
    ProviderProfile("doubao-1.5-pro", "A", 0.8, 2.0, "<3s"),
    ProviderProfile("deepseek-v3.2", "A", 0.5, 4.0, "3-8s"),
    ProviderProfile("qwen-max", "A", 4.0, 12.0, "3-8s"),
    ProviderProfile("hunyuan-turbo", "B", 1.0, 3.0, "<3s"),
    ProviderProfile("glm-4.5", "B", 1.5, 6.0, "3-8s"),
    ProviderProfile("kimi-k1.5", "B", 2.0, 10.0, "3-8s"),
    ProviderProfile("ernie-4.5-turbo", "C", 1.0, 4.0, "3-8s"),
    ProviderProfile("minimax-abab7", "C", 1.5, 6.0, "3-8s"),
    ProviderProfile("step-2", "C", 1.2, 5.0, ">8s"),
]


def cost_penalty(p: ProviderProfile) -> float:
    """Heuristic cost penalty based on a 1:3 input:output ratio."""
    return (p.input_price_per_m + p.output_price_per_m * 3) / 10.0


def score(p: ProviderProfile, tier: TaskTier) -> float:
    """Score a provider for a given task tier. Higher is better."""
    r = RELIABILITY_MAP[p.tier_reliability]
    l = LATENCY_MAP[p.latency_grade]
    c = cost_penalty(p)
    if tier == TaskTier.CRITICAL:
        return r * 3 + l * 2 - c * 0.3
    if tier == TaskTier.STANDARD:
        return r * 2 + l * 1.5 - c * 1.0
    return r * 1 + l * 0.5 - c * 2.5


def rank_providers(
    tier: TaskTier,
    providers: List[ProviderProfile] = None,
) -> List[ProviderProfile]:
    pool = providers if providers is not None else PROVIDERS_2026H1
    return sorted(pool, key=lambda p: -score(p, tier))


def top_n_for_tier(tier: TaskTier, n: int = 3) -> List[str]:
    return [p.name for p in rank_providers(tier)][:n]


if __name__ == "__main__":
    for tier in TaskTier:
        top = top_n_for_tier(tier, 3)
        print(f"{tier.value:>10s} top-3: {top}")
