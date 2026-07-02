"""mcp_adoption_analyzer.py

MCP 企业接入成熟度评估器。

用途：
- 给出企业 MCP 接入的 5 维度打分模型（Auth / Permission / Observability / Registry / Governance）
- 每个维度 0-5 分，输出总分、等级（L0-L5）、瓶颈维度、下一步建议
- 支持 JSON 输入（`AdoptionSurvey`），方便对接问卷/Bot
- 完全不依赖网络，纯规则打分器，可作为 chapter-19 gateway 的"上层驾驶舱"

打分模型灵感来源：
- Anthropic 2025-11-25 官方规范中"Security and Enterprise Features"
- arxiv:2605.22333 MCP 认证实测研究
- Tachyonic MCP Security Report 2026 Q1
- 掘金/腾讯云 MCP 演进史（2025-03-26 OAuth 2.1 引入）
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

MAX_PER_DIMENSION = 5
DIMENSIONS = ("auth", "permission", "observability", "registry", "governance")


@dataclass
class AdoptionSurvey:
    """企业 MCP 接入现状调研输入。"""

    # 认证：是否走 OAuth 2.1 + PKCE + Resource Indicator
    uses_oauth_21: bool = False
    validates_token_audience: bool = False
    enforces_pkce_s256: bool = False
    restricts_dcr: bool = False
    # 权限
    scopes_per_tool_group: bool = False
    write_actions_require_human_confirm: bool = False
    per_client_consent: bool = False
    # 可观测
    uses_opentelemetry: bool = False
    session_to_trace_mapping: bool = False
    audit_log_persisted_days: int = 0  # 审计日志保留天数
    # Registry / Server 治理
    has_internal_registry: bool = False
    has_server_whitelist: bool = False
    has_version_pinning: bool = False
    # 组织治理
    dedicated_platform_team: bool = False
    has_incident_playbook: bool = False
    covered_by_devsecops_review: bool = False


@dataclass
class DimensionScore:
    name: str
    score: int
    max_score: int
    reasons: list[str] = field(default_factory=list)

    @property
    def ratio(self) -> float:
        return self.score / self.max_score if self.max_score else 0.0


@dataclass
class AdoptionReport:
    total_score: int
    level: str
    level_label: str
    bottlenecks: list[str]
    next_steps: list[str]
    dimension_scores: list[DimensionScore]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_score": self.total_score,
            "level": self.level,
            "level_label": self.level_label,
            "bottlenecks": list(self.bottlenecks),
            "next_steps": list(self.next_steps),
            "dimension_scores": [asdict(d) for d in self.dimension_scores],
        }


# 每个维度都是 0-5 分：把布尔条件累加，最后 clamp 到 5
def _score_auth(s: AdoptionSurvey) -> DimensionScore:
    checks = [
        (s.uses_oauth_21, "已切换到 OAuth 2.1"),
        (s.validates_token_audience, "校验 token audience（RFC 8707）"),
        (s.enforces_pkce_s256, "强制 PKCE S256"),
        (s.restricts_dcr, "限制或禁用不受控的 DCR"),
    ]
    hit = [reason for cond, reason in checks if cond]
    score = min(len(hit) + (1 if len(hit) == len(checks) else 0), MAX_PER_DIMENSION)
    return DimensionScore(name="auth", score=score, max_score=MAX_PER_DIMENSION, reasons=hit)


def _score_permission(s: AdoptionSurvey) -> DimensionScore:
    checks = [
        (s.scopes_per_tool_group, "按 tool group 拆分 scope"),
        (s.write_actions_require_human_confirm, "写操作强制人工确认"),
        (s.per_client_consent, "实施每客户端一次同意"),
    ]
    hit = [reason for cond, reason in checks if cond]
    # 三项都命中给 5，两项 3，一项 2，零项 0
    score_map = {0: 0, 1: 2, 2: 3, 3: 5}
    return DimensionScore(
        name="permission",
        score=score_map[len(hit)],
        max_score=MAX_PER_DIMENSION,
        reasons=hit,
    )


def _score_observability(s: AdoptionSurvey) -> DimensionScore:
    hit = []
    score = 0
    if s.uses_opentelemetry:
        hit.append("接入 OpenTelemetry")
        score += 2
    if s.session_to_trace_mapping:
        hit.append("MCP session ↔ trace 已映射")
        score += 2
    if s.audit_log_persisted_days >= 30:
        hit.append(f"审计日志保留 {s.audit_log_persisted_days} 天")
        score += 1
    return DimensionScore(
        name="observability",
        score=min(score, MAX_PER_DIMENSION),
        max_score=MAX_PER_DIMENSION,
        reasons=hit,
    )


def _score_registry(s: AdoptionSurvey) -> DimensionScore:
    checks = [
        (s.has_internal_registry, "已建内部 MCP Registry"),
        (s.has_server_whitelist, "对外部 Server 使用白名单"),
        (s.has_version_pinning, "版本已锁定"),
    ]
    hit = [reason for cond, reason in checks if cond]
    score_map = {0: 0, 1: 2, 2: 3, 3: 5}
    return DimensionScore(
        name="registry",
        score=score_map[len(hit)],
        max_score=MAX_PER_DIMENSION,
        reasons=hit,
    )


def _score_governance(s: AdoptionSurvey) -> DimensionScore:
    checks = [
        (s.dedicated_platform_team, "有专职平台团队"),
        (s.has_incident_playbook, "已建应急预案"),
        (s.covered_by_devsecops_review, "纳入 DevSecOps 评审"),
    ]
    hit = [reason for cond, reason in checks if cond]
    score_map = {0: 0, 1: 2, 2: 3, 3: 5}
    return DimensionScore(
        name="governance",
        score=score_map[len(hit)],
        max_score=MAX_PER_DIMENSION,
        reasons=hit,
    )


SCORERS = {
    "auth": _score_auth,
    "permission": _score_permission,
    "observability": _score_observability,
    "registry": _score_registry,
    "governance": _score_governance,
}


LEVEL_TABLE: tuple[tuple[int, str, str], ...] = (
    (0, "L0", "未接入/纯 PoC"),
    (5, "L1", "开发者试用"),
    (10, "L2", "试点小流量"),
    (15, "L3", "生产可用"),
    (20, "L4", "多团队规模化"),
    (24, "L5", "平台级 MCP-native"),
)


NEXT_STEPS = {
    "auth": "补齐 OAuth 2.1 + PKCE + Resource Indicator，Gateway 层统一 aud 校验（可复用 chapter-19 oauth_middleware.py）",
    "permission": "把工具按读/写/管理员分层授权，写操作走人工确认；代理型 Server 实施每客户端一次同意",
    "observability": "Day 1 就把 OTel Instrumentation 加进 Gateway，session ID → trace ID 建立映射",
    "registry": "建内部 Registry + 版本锁定 + 外部 Server 白名单，避免 mcp.so 上低分 Server 直连生产",
    "governance": "组建专职 MCP 平台团队，纳入 DevSecOps 评审，制定 MCP 事件应急预案",
}


def _resolve_level(total: int) -> tuple[str, str]:
    label = LEVEL_TABLE[0]
    for entry in LEVEL_TABLE:
        threshold, level, name = entry
        if total >= threshold:
            label = entry
    return label[1], label[2]


def analyze(survey: AdoptionSurvey) -> AdoptionReport:
    dim_scores: list[DimensionScore] = [SCORERS[d](survey) for d in DIMENSIONS]
    total = sum(d.score for d in dim_scores)
    level, label = _resolve_level(total)

    # 瓶颈：得分 <= max*0.4 的维度
    threshold = MAX_PER_DIMENSION * 0.4
    bottlenecks = [d.name for d in dim_scores if d.score <= threshold]

    next_steps = [NEXT_STEPS[name] for name in bottlenecks] or [
        "整体已到 L4+ 水位，建议关注 2026-07-28 无状态化 RC 与 Registry 治理动态",
    ]

    return AdoptionReport(
        total_score=total,
        level=level,
        level_label=label,
        bottlenecks=bottlenecks,
        next_steps=next_steps,
        dimension_scores=dim_scores,
    )


def render_text_report(report: AdoptionReport) -> str:
    lines = [
        "MCP Enterprise Adoption Report",
        "=" * 40,
        f"Total score : {report.total_score} / 25",
        f"Level       : {report.level} ({report.level_label})",
        "",
        "Dimension breakdown:",
    ]
    for d in report.dimension_scores:
        lines.append(f"  - {d.name:<13} {d.score}/{d.max_score}  ({d.ratio*100:5.1f}%)")
        for r in d.reasons:
            lines.append(f"      · {r}")
    lines.append("")
    lines.append("Bottlenecks : " + (", ".join(report.bottlenecks) or "none"))
    lines.append("Next steps :")
    for step in report.next_steps:
        lines.append(f"  → {step}")
    return "\n".join(lines)


def survey_from_dict(data: dict[str, Any]) -> AdoptionSurvey:
    """从 dict 构造 AdoptionSurvey，未知字段忽略，缺失字段用默认值。"""
    valid = {k: v for k, v in data.items() if k in AdoptionSurvey.__annotations__}
    return AdoptionSurvey(**valid)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MCP enterprise adoption analyzer")
    parser.add_argument("--input", default=None, help="调研 JSON 文件路径（可选）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出报告")
    parser.add_argument("--demo", action="store_true", help="用内置样例数据跑一次")
    args = parser.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8") as fh:
            survey = survey_from_dict(json.load(fh))
    elif args.demo:
        # 典型「L3 生产可用但仍缺可观测」画像
        survey = AdoptionSurvey(
            uses_oauth_21=True,
            validates_token_audience=True,
            enforces_pkce_s256=True,
            scopes_per_tool_group=True,
            write_actions_require_human_confirm=True,
            has_internal_registry=True,
            has_version_pinning=True,
            dedicated_platform_team=True,
            has_incident_playbook=True,
        )
    else:
        survey = AdoptionSurvey()

    report = analyze(survey)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_text_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
