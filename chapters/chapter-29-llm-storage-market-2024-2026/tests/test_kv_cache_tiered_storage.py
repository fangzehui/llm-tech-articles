"""tests for kv_cache_tiered_storage"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from kv_cache_tiered_storage import TieredKVCache, TIER_HOT, TIER_WARM, TIER_COLD, TIER_MISS


def test_first_access_is_miss():
    cache = TieredKVCache(hot_cap_gb=2.0, warm_cap_gb=5.0, cold_cap_gb=10.0)
    assert cache.access("s1", 0.5) == TIER_MISS
    assert cache.hits[TIER_MISS] == 1


def test_immediate_reaccess_hits_hot():
    cache = TieredKVCache(hot_cap_gb=2.0, warm_cap_gb=5.0, cold_cap_gb=10.0)
    cache.access("s1", 0.5)
    assert cache.access("s1", 0.5) == TIER_HOT


def test_size_gb_must_be_positive():
    cache = TieredKVCache(hot_cap_gb=2.0, warm_cap_gb=5.0, cold_cap_gb=10.0)
    with pytest.raises(ValueError):
        cache.access("s1", 0.0)
    with pytest.raises(ValueError):
        cache.access("s1", -1.0)


def test_hot_overflow_migrates_to_warm():
    cache = TieredKVCache(hot_cap_gb=1.0, warm_cap_gb=5.0, cold_cap_gb=10.0)
    cache.access("s1", 0.6)
    cache.access("s2", 0.6)  # 触发 s1 从 hot 溢出到 warm
    h, w, c = cache.usage()
    assert pytest.approx(h, abs=1e-9) == 0.6
    assert pytest.approx(w, abs=1e-9) == 0.6
    assert c == 0.0
    # 现在访问 s1 应该命中 warm
    assert cache.access("s1", 0.6) == TIER_WARM


def test_warm_overflow_migrates_to_cold():
    cache = TieredKVCache(hot_cap_gb=1.0, warm_cap_gb=1.0, cold_cap_gb=10.0)
    cache.access("s1", 0.6)
    cache.access("s2", 0.6)  # s1 -> warm
    cache.access("s3", 0.6)  # s2 -> warm, s1 溢出 warm -> cold
    h, w, c = cache.usage()
    assert pytest.approx(h, abs=1e-9) == 0.6
    assert pytest.approx(w, abs=1e-9) == 0.6
    assert pytest.approx(c, abs=1e-9) == 0.6


def test_cold_overflow_is_dropped():
    cache = TieredKVCache(hot_cap_gb=0.5, warm_cap_gb=0.5, cold_cap_gb=0.5)
    for i in range(10):
        cache.access(f"s{i}", 0.5)
    h, w, c = cache.usage()
    assert h + w + c <= 1.5 + 1e-9


def test_hit_rate_calc():
    cache = TieredKVCache(hot_cap_gb=2.0, warm_cap_gb=5.0, cold_cap_gb=10.0)
    cache.access("s1", 0.5)  # miss
    cache.access("s1", 0.5)  # hot hit
    cache.access("s1", 0.5)  # hot hit
    rates = cache.hit_rate()
    assert rates[TIER_HOT] == pytest.approx(2 / 3)
    assert rates[TIER_MISS] == pytest.approx(1 / 3)


def test_monthly_cost_nonnegative():
    cache = TieredKVCache(hot_cap_gb=2.0, warm_cap_gb=5.0, cold_cap_gb=10.0)
    for i in range(20):
        cache.access(f"s{i}", 0.4)
    assert cache.monthly_cost() >= 0
