"""第 09 篇配套 demo：根据任务复杂度把请求路由到不同档位模型.

设计：
- TierConfig 定义档位（small / mid / flagship），每档配置候选模型 + 触发条件
- TierRouter 接收一个 RequestProfile，按规则选档位、选模型，并能降级
- 触发条件覆盖 token 长度、关键词、显式 tier_hint 三类

可独立运行：
    python tier_router.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import MockLLMClient  # noqa: E402


@dataclass
class RequestProfile:
    """一次业务请求的画像，用于驱动路由决策."""

    text: str
    estimated_input_tokens: int
    scenario: str = "chat"  # chat / rag / code / agent
    tier_hint: str | None = None  # 业务方显式指定档位


@dataclass
class TierConfig:
    """单个档位的配置.

    Attributes:
        tier: 档位名（small / mid / flagship）
        models: 候选模型列表，按优先级排序
        max_input_tokens: 该档位能处理的最长输入
        keywords: 命中即升档的触发词
    """

    tier: str
    models: list[str]
    max_input_tokens: int
    keywords: list[str] = field(default_factory=list)


class TierRouter:
    """分级路由器：复杂度 -> 档位 -> 模型."""

    TIER_ORDER = ["small", "mid", "flagship"]

    def __init__(self, tiers: dict[str, TierConfig]) -> None:
        for t in tiers:
            if t not in self.TIER_ORDER:
                raise ValueError(f"unknown tier: {t}")
        self.tiers = tiers
        # 每个 model 一个 mock client
        models: list[str] = []
        for cfg in tiers.values():
            models.extend(cfg.models)
        self._clients = {m: MockLLMClient("mock", m, 70, seed=hash(m) % 1000) for m in models}

    @classmethod
    def from_yaml(cls, path: Path) -> "TierRouter":
        """从 YAML 加载配置；无 PyYAML 时退到内置默认配置."""
        try:
            import yaml  # type: ignore
        except ImportError:
            return cls(default_tiers())
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        tiers = {
            name: TierConfig(tier=name, **cfg) for name, cfg in raw.get("tiers", {}).items()
        }
        return cls(tiers)

    def pick_tier(self, profile: RequestProfile) -> str:
        """决定该请求走哪一档."""
        if profile.tier_hint and profile.tier_hint in self.tiers:
            return profile.tier_hint
        # 关键词触发：从大到小匹配
        for tier in reversed(self.TIER_ORDER):
            cfg = self.tiers.get(tier)
            if not cfg:
                continue
            if any(kw in profile.text for kw in cfg.keywords):
                return tier
        # 按 token 长度兜底：小 -> 中 -> 大
        for tier in self.TIER_ORDER:
            cfg = self.tiers.get(tier)
            if not cfg:
                continue
            if profile.estimated_input_tokens <= cfg.max_input_tokens:
                return tier
        return self.TIER_ORDER[-1]

    def route(self, profile: RequestProfile) -> dict[str, Any]:
        """执行路由 + 一次调用，返回所选模型与响应."""
        tier = self.pick_tier(profile)
        cfg = self.tiers[tier]
        if not cfg.models:
            raise RuntimeError(f"tier {tier} has no candidate model")
        # 简化：取首选模型
        model = cfg.models[0]
        client = self._clients[model]
        resp = client.chat([{"role": "user", "content": profile.text}])
        return {
            "tier": tier,
            "model": model,
            "content": resp.content,
            "tokens": resp.total_tokens,
        }


def default_tiers() -> dict[str, TierConfig]:
    """内置兜底配置，避免 yaml 缺失时无法跑起."""
    return {
        "small": TierConfig(
            tier="small",
            models=["small-fast"],
            max_input_tokens=2000,
            keywords=[],
        ),
        "mid": TierConfig(
            tier="mid",
            models=["mid-balance"],
            max_input_tokens=20000,
            keywords=["请总结", "summarize"],
        ),
        "flagship": TierConfig(
            tier="flagship",
            models=["flagship"],
            max_input_tokens=200000,
            keywords=["请编写代码", "写一段代码", "code", "证明"],
        ),
    }


def main() -> None:  # pragma: no cover
    here = Path(__file__).resolve().parent
    router = TierRouter.from_yaml(here / "tier_config.yml")
    samples = [
        RequestProfile("今天天气怎么样", 50),
        RequestProfile("请总结这份 8000 字报告的核心结论", 8000),
        RequestProfile("请编写代码：实现一个 LRU 缓存", 200, scenario="code"),
        RequestProfile("强制走旗舰", 100, tier_hint="flagship"),
    ]
    for p in samples:
        out = router.route(p)
        print(f"  {out['tier']:8s} -> {out['model']:12s} | {out['content'][:50]}")


if __name__ == "__main__":  # pragma: no cover
    main()
