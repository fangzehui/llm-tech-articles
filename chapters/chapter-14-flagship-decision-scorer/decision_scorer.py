"""第 14 篇配套 demo：2026.6 旗舰大模型四强决策评分器.

设计：
- ``ModelProfile`` 描述一个旗舰模型的能力、价格、合规、SLA 元信息
- ``MODELS`` 注册表收录 4 款主流旗舰：GLM-5.2 / Claude Fable 5 / GPT-5 Preview / Gemini 3.0 Pro
- ``Scenario`` 描述一个业务场景的能力权重 + 月度调用量 + 合规约束 + 预算
- ``score_model`` 把 (模型, 场景) 映射到一行带 ``score`` / ``monthly_cost_usd`` /
  ``blocked`` 的结果字典；合规或预算被拒时 ``blocked`` 不为 None 且 score=-1
- ``recommend`` 对全部模型打分后按分值倒序返回，分数越高越推荐

可独立运行：
    python decision_scorer.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ModelProfile:
    """单个旗舰模型的画像（能力分 / 价格 / 合规 / SLA）.

    能力分均为 0-100 区间，越高越强；价格单位为 USD / 1M tokens.
    """

    name: str
    capability_code: int          # 编程能力 (0-100)
    capability_agent: int         # Agent / 工具调用能力 (0-100)
    capability_multimodal: int    # 多模态（视觉/音频/视频）(0-100)
    capability_general: int       # 通用对话 / 中文 / RAG (0-100)
    price_input: float            # 输入价 USD/1M tokens
    price_output: float           # 输出价 USD/1M tokens
    cn_compliance: int            # 国内合规度 (0-100)
    sla_grade: int                # SLA 等级 (0-100)


# 4 款旗舰模型的 2026.6 画像，数字综合自第 14 篇正文 § 三/四/五的整理.
MODELS: dict[str, ModelProfile] = {
    "GLM-5.2": ModelProfile(
        name="GLM-5.2",
        capability_code=72, capability_agent=70,
        capability_multimodal=70, capability_general=85,
        price_input=0.6, price_output=2.0,
        cn_compliance=100, sla_grade=85,
    ),
    "Fable 5": ModelProfile(
        name="Claude Fable 5",
        capability_code=95, capability_agent=82,
        capability_multimodal=82, capability_general=90,
        price_input=10.0, price_output=50.0,
        cn_compliance=20, sla_grade=50,
    ),
    "GPT-5 Preview": ModelProfile(
        name="GPT-5 Preview",
        capability_code=78, capability_agent=92,
        capability_multimodal=80, capability_general=90,
        price_input=1.25, price_output=10.0,
        cn_compliance=20, sla_grade=70,
    ),
    "Gemini 3.0": ModelProfile(
        name="Gemini 3.0 Pro",
        capability_code=75, capability_agent=78,
        capability_multimodal=95, capability_general=88,
        price_input=1.0, price_output=4.0,
        cn_compliance=25, sla_grade=85,
    ),
}


@dataclass
class Scenario:
    """业务场景的评分权重 + 调用量 + 合规约束 + 预算.

    6 个 weight_* 之和不强制为 1.0，得分本身仅用于相对排序，绝对值不必苛求.
    """

    name: str
    weight_code: float = 0.2
    weight_agent: float = 0.2
    weight_multimodal: float = 0.2
    weight_general: float = 0.2
    weight_price: float = 0.1
    weight_compliance: float = 0.1
    monthly_input_tokens_m: float = 10.0   # 月输入 (M tokens)
    monthly_output_tokens_m: float = 2.5   # 月输出 (M tokens)
    require_cn_compliance: bool = False
    max_monthly_budget: float = 1e9        # 月预算 USD


# GLM-5.2 (input 0.6 + output 2.0) × 默认 Scenario(10 + 2.5) = 11.0 USD/月
# 把这个值作为价格归一基准，其他模型的成本按比例衰减
_BASELINE_MONTHLY_COST = 8.8


def score_model(m: ModelProfile, s: Scenario) -> dict[str, Any]:
    """对 (模型, 场景) 给出一行评分结果.

    Args:
        m: 模型画像
        s: 场景定义

    Returns:
        ``{"name": ..., "score": ..., "monthly_cost_usd": ..., "blocked": ...}``
        若被合规或预算拦截，``score`` 置 -1，``blocked`` 给出原因.
    """
    if s.require_cn_compliance and m.cn_compliance < 80:
        return {"name": m.name, "score": -1, "monthly_cost_usd": None, "blocked": "合规不通过"}

    monthly_cost = (
        m.price_input * s.monthly_input_tokens_m
        + m.price_output * s.monthly_output_tokens_m
    )
    if monthly_cost > s.max_monthly_budget:
        return {
            "name": m.name,
            "score": -1,
            "monthly_cost_usd": round(monthly_cost, 2),
            "blocked": f"超预算 ${monthly_cost:.0f}",
        }

    # 价格归一：以最低价 GLM-5.2 月度账单为基准 100，每超出 1× 扣 20 分，下限 0
    price_score = max(0.0, 100.0 - (monthly_cost - _BASELINE_MONTHLY_COST) / _BASELINE_MONTHLY_COST * 20)

    score = (
        m.capability_code * s.weight_code
        + m.capability_agent * s.weight_agent
        + m.capability_multimodal * s.weight_multimodal
        + m.capability_general * s.weight_general
        + price_score * s.weight_price
        + m.cn_compliance * s.weight_compliance
    )
    return {
        "name": m.name,
        "score": round(score, 1),
        "monthly_cost_usd": round(monthly_cost, 2),
        "blocked": None,
    }


def recommend(scenario: Scenario) -> list[dict[str, Any]]:
    """对所有注册模型打分后按 score 倒序返回.

    被合规 / 预算拦截的模型 score=-1，会自然落到最后；不会从结果中移除，
    便于上游展示\"为什么没选这家\".
    """
    results = [score_model(m, scenario) for m in MODELS.values()]
    return sorted(results, key=lambda x: x["score"], reverse=True)


# ------------------------------- 预置场景 -------------------------------

def biz_flow_scenario() -> Scenario:
    """业务流·客服 RAG：通用能力 + 价格权重最高，强制国内合规."""
    return Scenario(
        name="业务流·客服RAG",
        weight_code=0.05, weight_agent=0.10,
        weight_multimodal=0.10, weight_general=0.40,
        weight_price=0.20, weight_compliance=0.15,
        monthly_input_tokens_m=200, monthly_output_tokens_m=50,
        require_cn_compliance=True,
    )


def rnd_agent_scenario() -> Scenario:
    """研发 Agent：编程 + Agent 权重最高，海外主体允许，无合规约束.

    研发场景对单 token 价格和合规相对不敏感（量小且团队多在海外环境跑），
    所以 weight_price / weight_compliance 压低、把权重留给能力维度.
    """
    return Scenario(
        name="研发·Agent编程",
        weight_code=0.40, weight_agent=0.35,
        weight_multimodal=0.05, weight_general=0.15,
        weight_price=0.025, weight_compliance=0.025,
        monthly_input_tokens_m=20, monthly_output_tokens_m=5,
        require_cn_compliance=False,
    )


def multimodal_scenario() -> Scenario:
    """多模态视频/音频处理：多模态权重最高."""
    return Scenario(
        name="多模态·视频音频",
        weight_code=0.05, weight_agent=0.10,
        weight_multimodal=0.45, weight_general=0.20,
        weight_price=0.10, weight_compliance=0.10,
        monthly_input_tokens_m=50, monthly_output_tokens_m=10,
        require_cn_compliance=False,
    )


def main() -> None:  # pragma: no cover
    """跑三个示例场景，把推荐排名打到 stdout."""
    for build in (biz_flow_scenario, rnd_agent_scenario, multimodal_scenario):
        sc = build()
        print(f"\n=== 场景：{sc.name} ===")
        for r in recommend(sc):
            tag = r["blocked"] or f"score={r['score']:>5}  cost=${r['monthly_cost_usd']}"
            print(f"  {r['name']:<20s} {tag}")


if __name__ == "__main__":  # pragma: no cover
    main()
