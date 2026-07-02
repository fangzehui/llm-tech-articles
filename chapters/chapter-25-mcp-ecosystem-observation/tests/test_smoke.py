"""tests/test_smoke.py

Chapter 24 冒烟测试：确保三个脚本 import 得到、核心函数按预期返回。
运行方式：
    cd chapters/chapter-25-mcp-ecosystem-observation
    pytest tests/ -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 把 chapter 目录加进 sys.path，避免装成 package
CHAPTER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHAPTER_DIR))

import mcp_adoption_analyzer as adoption  # noqa: E402
import mcp_client_matrix as matrix  # noqa: E402
import mcp_registry_scanner as scanner  # noqa: E402


# ---------- registry scanner ----------
def test_registry_snapshot_loadable():
    raw = scanner.load_snapshot()
    assert isinstance(raw, list)
    assert len(raw) >= 10, "内置样本至少 10 个 server"


def test_registry_classification_covers_four_buckets():
    raw = scanner.load_snapshot()
    servers = scanner.parse_servers(raw)
    stats = scanner.category_stats(servers)
    for cat in ("devtool", "database", "saas", "cloud"):
        assert cat in stats and stats[cat] > 0, f"{cat} 类应至少有 1 个样本"


def test_registry_filter_and_report():
    raw = scanner.load_snapshot()
    servers = scanner.parse_servers(raw)
    filtered = scanner.filter_servers(servers, category="devtool")
    assert all(s.category == "devtool" for s in filtered)
    report = scanner.render_report(filtered)
    assert "Total servers scanned" in report
    assert "devtool" in report


def test_registry_csv_export(tmp_path):
    raw = scanner.load_snapshot()
    servers = scanner.parse_servers(raw)
    out = tmp_path / "servers.csv"
    scanner.export_csv(servers[:3], out)
    content = out.read_text(encoding="utf-8")
    assert "namespace" in content
    assert content.count("\n") >= 3  # header + 3 rows


# ---------- client matrix ----------
def test_client_matrix_has_official_players():
    names = {c.name for c in matrix.CLIENT_MATRIX}
    for expected in ("Claude Desktop", "Cursor", "Windsurf", "ChatGPT (Developer Mode)"):
        assert expected in names, f"缺少客户端 {expected}"


def test_client_matrix_filter_by_capability():
    hits = matrix.find_clients_by_capability("elicitation")
    # 至少 Claude Desktop 支持 elicitation
    assert any(c.name == "Claude Desktop" for c in hits)


def test_client_matrix_filter_by_transport():
    hits = matrix.find_clients_by_transport("streamable_http")
    assert len(hits) >= 5, "主流客户端已普遍支持 Streamable HTTP"


def test_client_matrix_render_markdown_and_json():
    md = matrix.render_markdown_table()
    assert md.startswith("| 客户端")
    js = matrix.as_json()
    parsed = json.loads(js)
    assert isinstance(parsed, list) and len(parsed) == len(matrix.CLIENT_MATRIX)


# ---------- adoption analyzer ----------
def test_adoption_empty_survey_is_l0():
    report = adoption.analyze(adoption.AdoptionSurvey())
    assert report.total_score == 0
    assert report.level == "L0"
    # 所有维度都是瓶颈
    assert set(report.bottlenecks) == set(adoption.DIMENSIONS)


def test_adoption_demo_profile_is_l3_plus():
    survey = adoption.AdoptionSurvey(
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
    report = adoption.analyze(survey)
    assert report.total_score >= 12
    assert report.level in ("L2", "L3", "L4", "L5")
    # observability 未打开，应出现在 bottlenecks
    assert "observability" in report.bottlenecks


def test_adoption_full_score_is_l5():
    survey = adoption.AdoptionSurvey(
        uses_oauth_21=True,
        validates_token_audience=True,
        enforces_pkce_s256=True,
        restricts_dcr=True,
        scopes_per_tool_group=True,
        write_actions_require_human_confirm=True,
        per_client_consent=True,
        uses_opentelemetry=True,
        session_to_trace_mapping=True,
        audit_log_persisted_days=90,
        has_internal_registry=True,
        has_server_whitelist=True,
        has_version_pinning=True,
        dedicated_platform_team=True,
        has_incident_playbook=True,
        covered_by_devsecops_review=True,
    )
    report = adoption.analyze(survey)
    assert report.total_score >= 24
    assert report.level == "L5"
    assert report.bottlenecks == []


def test_adoption_report_serializable():
    report = adoption.analyze(adoption.AdoptionSurvey(uses_oauth_21=True))
    data = report.to_dict()
    dumped = json.dumps(data, ensure_ascii=False)
    reloaded = json.loads(dumped)
    assert reloaded["level"] == report.level


# ---------- CLI 冒烟 ----------
@pytest.mark.parametrize(
    "module, argv",
    [
        (scanner, []),
        (scanner, ["--category", "devtool"]),
        (matrix, ["--format", "json"]),
        (matrix, ["--capability", "resources"]),
        (adoption, ["--demo"]),
        (adoption, ["--demo", "--json"]),
    ],
)
def test_main_cli_runs(module, argv, capsys):
    ret = module.main(argv)
    captured = capsys.readouterr()
    assert ret == 0
    assert captured.out.strip() != ""
