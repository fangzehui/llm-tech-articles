"""ScenarioScorer: DeepSeek-V3.2 场景推荐分打分器。

四维评分卡：
- cost_sensitivity: 成本敏感度 (token 费在场景总成本里的占比)
- context_density:  上下文密度 (单请求平均 prompt tokens 高低)
- quality_tolerance: 质量容忍度 (质量偏差引起业务损失的容忍上限)
- latency_tolerance: 时延容忍度 (首 token / 端到端时延要求)

权重公式：
    score = 0.35 * cost_sensitivity
          + 0.25 * context_density
          + 0.20 * quality_tolerance
          + 0.20 * latency_tolerance

分档阈值：
    score >= 0.65  -> STRONG (强推荐切 V3.2)
    0.45 <= score < 0.65 -> WORTH_TRY (值得试)
    score < 0.45  -> NOT_RECOMMENDED (不建议切)
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class Recommendation(str, Enum):
    STRONG = "strong_recommend"
    WORTH_TRY = "worth_try"
    NOT_RECOMMENDED = "not_recommend"


@dataclass(frozen=True)
class ScenarioProfile:
    """场景画像的四个维度打分，均取值 [0.0, 1.0]。"""

    name: str
    cost_sensitivity: float
    context_density: float
    quality_tolerance: float
    latency_tolerance: float

    def __post_init__(self) -> None:
        for f in (
            "cost_sensitivity",
            "context_density",
            "quality_tolerance",
            "latency_tolerance",
        ):
            v = getattr(self, f)
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{f}={v} out of [0,1]")


class ScenarioScorer:
    """DeepSeek-V3.2 场景推荐分打分器。"""

    W_COST = 0.35
    W_CONTEXT = 0.25
    W_QUALITY = 0.20
    W_LATENCY = 0.20

    THRESHOLD_STRONG = 0.65
    THRESHOLD_WORTH = 0.45

    def score(self, profile: ScenarioProfile) -> float:
        return (
            self.W_COST * profile.cost_sensitivity
            + self.W_CONTEXT * profile.context_density
            + self.W_QUALITY * profile.quality_tolerance
            + self.W_LATENCY * profile.latency_tolerance
        )

    def recommend(self, profile: ScenarioProfile) -> Recommendation:
        s = self.score(profile)
        if s >= self.THRESHOLD_STRONG:
            return Recommendation.STRONG
        if s >= self.THRESHOLD_WORTH:
            return Recommendation.WORTH_TRY
        return Recommendation.NOT_RECOMMENDED

    def explain(self, profile: ScenarioProfile) -> Dict[str, object]:
        return {
            "scenario": profile.name,
            "score": round(self.score(profile), 3),
            "recommendation": self.recommend(profile).value,
            "breakdown": {
                "cost": round(self.W_COST * profile.cost_sensitivity, 3),
                "context": round(self.W_CONTEXT * profile.context_density, 3),
                "quality": round(self.W_QUALITY * profile.quality_tolerance, 3),
                "latency": round(self.W_LATENCY * profile.latency_tolerance, 3),
            },
        }

    def batch_recommend(
        self, profiles: List[ScenarioProfile]
    ) -> List[Dict[str, object]]:
        """批量返回推荐结果，按分数从高到低排序。"""
        results = [self.explain(p) for p in profiles]
        results.sort(key=lambda r: r["score"], reverse=True)
        return results


# ------------------- 2026-H1 场景快照 -------------------

BATCH_DATA_CLEANING = ScenarioProfile(
    name="batch_data_cleaning",
    cost_sensitivity=0.9,
    context_density=0.7,
    quality_tolerance=0.7,
    latency_tolerance=0.9,
)

LONG_DOC_SUMMARY = ScenarioProfile(
    name="long_doc_summary_rag",
    cost_sensitivity=0.8,
    context_density=0.9,
    quality_tolerance=0.6,
    latency_tolerance=0.7,
)

STRONG_REASONING = ScenarioProfile(
    name="strong_reasoning_agent",
    cost_sensitivity=0.5,
    context_density=0.6,
    quality_tolerance=0.15,
    latency_tolerance=0.4,
)

CUSTOMER_SERVICE = ScenarioProfile(
    name="customer_service_chat",
    cost_sensitivity=0.7,
    context_density=0.4,
    quality_tolerance=0.5,
    latency_tolerance=0.5,
)

DEFAULT_2026H1_SCENARIOS: List[ScenarioProfile] = [
    BATCH_DATA_CLEANING,
    LONG_DOC_SUMMARY,
    STRONG_REASONING,
    CUSTOMER_SERVICE,
]
