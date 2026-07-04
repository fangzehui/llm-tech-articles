"""90-day error-rate windowing tool.

Reproduces the Section 4 methodology used in the article:
given a list of incidents (each with start/end timestamps and an
impact_ratio ∈ (0, 1]), slide a rolling window of `window_days` length
and report the weighted cumulative minutes / total window minutes.

Notes:
- This tool is for *reproducible* aggregation of publicly available
  incident data (e.g. vendor status pages). It does NOT perform real
  traffic monitoring against any LLM provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Tuple


@dataclass(frozen=True)
class Incident:
    """A single reported incident record."""

    api_name: str
    start: datetime
    end: datetime
    impact_ratio: float = 1.0
    source_url: str = ""
    severity: str = "SEV3"

    def __post_init__(self) -> None:
        if not (0.0 <= self.impact_ratio <= 1.0):
            raise ValueError(f"impact_ratio must be in [0, 1], got {self.impact_ratio}")
        if self.end < self.start:
            raise ValueError("end must be >= start")

    @property
    def duration_min(self) -> float:
        return (self.end - self.start).total_seconds() / 60.0

    @property
    def weighted_min(self) -> float:
        return self.duration_min * self.impact_ratio


def error_rate_in_window(
    incidents: Iterable[Incident],
    window_start: datetime,
    window_end: datetime,
) -> float:
    """Compute error-rate (∈ [0, 1]) over a single window.

    Only incident time that actually overlaps the window is counted, and
    only the weighted portion (duration * impact_ratio) is included.
    """
    total_min = (window_end - window_start).total_seconds() / 60.0
    if total_min <= 0:
        return 0.0
    accumulated = 0.0
    for inc in incidents:
        overlap_start = max(inc.start, window_start)
        overlap_end = min(inc.end, window_end)
        if overlap_end > overlap_start:
            overlap_min = (overlap_end - overlap_start).total_seconds() / 60.0
            accumulated += overlap_min * inc.impact_ratio
    return round(accumulated / total_min, 6)


def rolling_error_rate(
    incidents: List[Incident],
    end_date: datetime,
    window_days: int = 90,
    step_days: int = 7,
    total_windows: int = 12,
) -> List[Tuple[datetime, float]]:
    """Return (window_end, error_rate) series stepping backwards."""
    series: List[Tuple[datetime, float]] = []
    for i in range(total_windows):
        w_end = end_date - timedelta(days=step_days * i)
        w_start = w_end - timedelta(days=window_days)
        rate = error_rate_in_window(incidents, w_start, w_end)
        series.append((w_end, rate))
    return list(reversed(series))


def incident_summary_table(incidents: Iterable[Incident]) -> List[dict]:
    """Return a per-incident summary dict (useful for CLI / JSON)."""
    return [
        {
            "api_name": inc.api_name,
            "start": inc.start.isoformat(),
            "end": inc.end.isoformat(),
            "duration_min": round(inc.duration_min, 1),
            "impact_ratio": inc.impact_ratio,
            "weighted_min": round(inc.weighted_min, 1),
            "severity": inc.severity,
        }
        for inc in sorted(incidents, key=lambda x: x.start)
    ]


def api_level_rollup(incidents: Iterable[Incident], window_days: int = 90) -> List[dict]:
    """Aggregate by api_name and compute total weighted downtime."""
    by_api: dict[str, float] = {}
    by_count: dict[str, int] = {}
    for inc in incidents:
        by_api[inc.api_name] = by_api.get(inc.api_name, 0.0) + inc.weighted_min
        by_count[inc.api_name] = by_count.get(inc.api_name, 0) + 1
    rows = []
    for api, total in by_api.items():
        rows.append(
            {
                "api_name": api,
                "incident_count": by_count[api],
                "weighted_downtime_min": round(total, 1),
                "error_rate_90d": round(total / (window_days * 24 * 60), 6),
            }
        )
    return sorted(rows, key=lambda r: r["error_rate_90d"])


if __name__ == "__main__":
    import json

    sample = [
        Incident("deepseek-v3.2", datetime(2026, 5, 14, 10, 0),
                 datetime(2026, 5, 14, 10, 47), 0.6,
                 "https://api-status.deepseek.com/", "SEV3"),
        Incident("doubao-1.5-pro", datetime(2026, 6, 11, 14, 0),
                 datetime(2026, 6, 11, 14, 31), 0.4,
                 "https://status.volcengine.com/", "SEV3"),
        Incident("qwen-max", datetime(2026, 4, 18, 9, 0),
                 datetime(2026, 4, 18, 9, 47), 0.9,
                 "https://status.aliyun.com/", "SEV2"),
    ]
    print(json.dumps(api_level_rollup(sample), ensure_ascii=False, indent=2))
