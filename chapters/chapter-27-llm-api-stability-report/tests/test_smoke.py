"""Smoke tests for chapter-27 LLM API stability toolkit."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.error_rate_windower import (  # noqa: E402
    Incident,
    api_level_rollup,
    error_rate_in_window,
    incident_summary_table,
    rolling_error_rate,
)
from src.fallback_router import (  # noqa: E402
    FallbackRule,
    ProviderHealth,
    choose_provider,
    close_circuit_after_recovery,
)
from src.multi_api_scheduler import (  # noqa: E402
    PROVIDERS_2026H1,
    ProviderProfile,
    TaskTier,
    cost_penalty,
    rank_providers,
    score,
    top_n_for_tier,
)


# ---------------- error_rate_windower ----------------


def _sample_incidents():
    return [
        Incident(
            api_name="deepseek",
            start=datetime(2026, 5, 14, 10, 0),
            end=datetime(2026, 5, 14, 10, 47),
            impact_ratio=0.6,
        ),
        Incident(
            api_name="doubao",
            start=datetime(2026, 6, 11, 14, 0),
            end=datetime(2026, 6, 11, 14, 30),
            impact_ratio=1.0,
        ),
    ]


def test_incident_weighted_min():
    inc = _sample_incidents()[0]
    assert pytest.approx(inc.duration_min, abs=0.01) == 47.0
    assert pytest.approx(inc.weighted_min, abs=0.01) == 28.2


def test_incident_rejects_bad_impact():
    with pytest.raises(ValueError):
        Incident("x", datetime(2026, 1, 1), datetime(2026, 1, 1, 1), impact_ratio=1.5)


def test_error_rate_in_window_covers_incident():
    incs = _sample_incidents()
    w_start = datetime(2026, 4, 1)
    w_end = datetime(2026, 6, 30)
    rate = error_rate_in_window(incs, w_start, w_end)
    total_min = (w_end - w_start).total_seconds() / 60.0
    expected = (47 * 0.6 + 30 * 1.0) / total_min
    assert pytest.approx(rate, abs=1e-6) == round(expected, 6)


def test_error_rate_empty_window_returns_zero():
    assert error_rate_in_window([], datetime(2026, 4, 1), datetime(2026, 4, 1)) == 0.0


def test_rolling_error_rate_returns_series_length():
    incs = _sample_incidents()
    series = rolling_error_rate(
        incs,
        end_date=datetime(2026, 6, 30),
        window_days=90,
        step_days=7,
        total_windows=6,
    )
    assert len(series) == 6
    # ascending time
    for a, b in zip(series, series[1:]):
        assert a[0] < b[0]


def test_incident_summary_table_sorted_by_start():
    incs = _sample_incidents()
    rows = incident_summary_table(incs)
    assert len(rows) == 2
    assert rows[0]["api_name"] == "deepseek"
    assert rows[1]["api_name"] == "doubao"


def test_api_level_rollup_aggregates():
    incs = _sample_incidents() + [
        Incident("deepseek", datetime(2026, 4, 5), datetime(2026, 4, 5, 0, 30), 0.5)
    ]
    rows = api_level_rollup(incs, window_days=90)
    # deepseek should have 2 incidents
    ds = next(r for r in rows if r["api_name"] == "deepseek")
    assert ds["incident_count"] == 2
    assert ds["weighted_downtime_min"] > 0


# ---------------- fallback_router ----------------


def test_router_picks_primary_when_healthy():
    rule = FallbackRule(primary="A", fallbacks=["B", "C"])
    health = {}
    d = choose_provider(rule, health, now_ts=1000.0)
    assert d.chosen == "A"
    assert d.fallback_used is False


def test_router_falls_back_when_primary_circuit_open():
    rule = FallbackRule(primary="A", fallbacks=["B"], max_consecutive_failures=2)
    health = {"A": ProviderHealth("A", consecutive_failures=3)}
    d = choose_provider(rule, health, now_ts=1000.0)
    assert d.chosen == "B"
    assert d.fallback_used is True
    assert "A" in d.tried


def test_router_returns_empty_when_all_unhealthy():
    rule = FallbackRule(primary="A", fallbacks=["B"], max_consecutive_failures=1)
    health = {
        "A": ProviderHealth("A", consecutive_failures=5),
        "B": ProviderHealth("B", consecutive_failures=5),
    }
    d = choose_provider(rule, health, now_ts=1000.0)
    assert d.chosen == ""
    assert d.reason == "all_unhealthy"


def test_p99_ceiling_triggers_open():
    rule = FallbackRule(primary="A", fallbacks=["B"], p99_ceiling_ms=5000)
    health = {"A": ProviderHealth("A", last_p99_ms=9000)}
    d = choose_provider(rule, health, now_ts=1000.0)
    assert d.chosen == "B"


def test_close_circuit_after_recovery_resets_state():
    health = {"A": ProviderHealth("A", consecutive_failures=5, circuit_open_until_ts=9999)}
    close_circuit_after_recovery(health, "A", p99_ms=1200)
    assert health["A"].consecutive_failures == 0
    assert health["A"].circuit_open_until_ts == 0.0
    assert health["A"].last_p99_ms == 1200


# ---------------- multi_api_scheduler ----------------


def test_provider_profile_rejects_bad_tier():
    with pytest.raises(ValueError):
        ProviderProfile("x", "Z", 1.0, 2.0, "<3s")


def test_provider_profile_rejects_bad_latency():
    with pytest.raises(ValueError):
        ProviderProfile("x", "A", 1.0, 2.0, "bad")


def test_cost_penalty_monotonic():
    cheap = ProviderProfile("cheap", "A", 0.5, 2.0, "<3s")
    expensive = ProviderProfile("exp", "A", 4.0, 12.0, "<3s")
    assert cost_penalty(cheap) < cost_penalty(expensive)


def test_critical_tier_prefers_reliability_a():
    ranked = rank_providers(TaskTier.CRITICAL)
    assert ranked[0].tier_reliability == "A"


def test_batch_tier_prefers_cheap_provider():
    # Batch tier: cost weight is highest
    ranked = rank_providers(TaskTier.BATCH)
    # deepseek-v3.2 has cheapest output (4.0) among A tier; should be top-3
    top_names = [p.name for p in ranked[:3]]
    assert "deepseek-v3.2" in top_names


def test_top_n_for_tier_returns_expected_length():
    top = top_n_for_tier(TaskTier.STANDARD, n=5)
    assert len(top) == 5
    assert len(set(top)) == 5


def test_default_provider_pool_covers_9_apis():
    assert len(PROVIDERS_2026H1) == 9
    names = {p.name for p in PROVIDERS_2026H1}
    for expected in ("deepseek-v3.2", "doubao-1.5-pro", "qwen-max", "glm-4.5"):
        assert expected in names


def test_score_deterministic():
    p = PROVIDERS_2026H1[0]
    s1 = score(p, TaskTier.CRITICAL)
    s2 = score(p, TaskTier.CRITICAL)
    assert s1 == s2
