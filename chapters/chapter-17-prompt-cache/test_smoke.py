"""第 17 篇 smoke test: Prompt Cache 五家计费校验.

跑法：
    pytest test_smoke.py -q
"""

from __future__ import annotations

import pytest

from cache_bench import (
    PRICE_TABLES,
    PriceTable,
    Scenario,
    break_even,
    compare_all,
    cost_no_cache,
    cost_with_cache,
)


def _default_scenario() -> Scenario:
    return Scenario(
        name="t",
        system_prompt_tokens=8000,
        user_tokens_per_call=200,
        output_tokens_per_call=200,
        num_calls=100,
        interval_minutes=0.5,
    )


def test_price_tables_complete() -> None:
    """≥ 5 家、每家四件套字段齐全且非负，cache_read < input."""
    assert len(PRICE_TABLES) >= 5
    for key, p in PRICE_TABLES.items():
        assert p.input >= 0, f"{key} input 不能为负"
        assert p.output >= 0
        assert p.cache_write >= 0
        assert p.cache_read >= 0
        # cache_read 必须严格小于 input，否则缓存毫无价值
        assert p.cache_read < p.input, (
            f"{key} cache_read({p.cache_read}) >= input({p.input})，缓存无意义"
        )
        assert p.min_cache_tokens > 0
        assert p.default_ttl_minutes > 0
        assert p.trigger_mechanism in {
            "explicit_cache_control",
            "auto_prefix",
            "cached_contents",
            "disk_kv",
        }


def test_cost_no_cache_baseline() -> None:
    """无 cache 基准：100 次、每次 8200 token 输入、200 token 输出，
    Sonnet 4.5 = 820000 tok × $3 + 20000 tok × $15."""
    s = _default_scenario()
    p = PRICE_TABLES["anthropic_sonnet45"]
    r = cost_no_cache(s, p)

    expected_input = 100 * 8200 / 1_000_000 * 3.0
    expected_output = 100 * 200 / 1_000_000 * 15.0
    assert r["input_cost"] == pytest.approx(expected_input, rel=1e-3)
    assert r["output_cost"] == pytest.approx(expected_output, rel=1e-3)
    assert r["total_cost"] == pytest.approx(expected_input + expected_output, rel=1e-3)


def test_cost_with_cache_anthropic() -> None:
    """Anthropic Sonnet 4.5 5min TTL 计费：
    1×8000×$3.75 + 99×8000×$0.30 + 100×200×$3 + 100×200×$15.
    """
    s = _default_scenario()
    p = PRICE_TABLES["anthropic_sonnet45"]
    r = cost_with_cache(s, p, ttl_strategy="default")

    write = 1 * 8000 / 1_000_000 * 3.75
    read = 99 * 8000 / 1_000_000 * 0.30
    user_input = 100 * 200 / 1_000_000 * 3.0
    output = 100 * 200 / 1_000_000 * 15.0
    expected_total = write + read + user_input + output

    assert r["cache_write_cost"] == pytest.approx(write, rel=1e-3)
    assert r["cache_read_cost"] == pytest.approx(read, rel=1e-3)
    assert r["user_input_cost"] == pytest.approx(user_input, rel=1e-3)
    assert r["output_cost"] == pytest.approx(output, rel=1e-3)
    assert r["total_cost"] == pytest.approx(expected_total, rel=1e-3)
    assert r["renew_count"] == 1, "间隔 0.5min < 5min TTL，理应只写一次"


def test_break_even_under_3() -> None:
    """对于 8K 系统提示、200 user / 200 output 这种典型场景，
    所有 6 家厂商的 break-even 都应该 ≤ 3 次."""
    s = _default_scenario()
    for key, p in PRICE_TABLES.items():
        be = break_even(s, p)
        assert 1 <= be <= 3, f"{key} break-even = {be}，超出 1-3 区间"


def test_compare_all_ranking() -> None:
    """compare_all 必须返回所有 5 家以上，且按 savings_pct 严格降序，
    省钱比例非负."""
    s = _default_scenario()
    rows = compare_all(s)

    assert len(rows) == len(PRICE_TABLES)
    assert len(rows) >= 5

    for i in range(len(rows) - 1):
        assert rows[i]["savings_pct"] >= rows[i + 1]["savings_pct"], (
            f"排序错误：第 {i} 行 ({rows[i]['name']}) 省 "
            f"{rows[i]['savings_pct']}% 应 >= 第 {i+1} 行 "
            f"({rows[i+1]['name']}) 省 {rows[i+1]['savings_pct']}%"
        )

    for r in rows:
        assert r["savings_pct"] >= 0, f"{r['name']} 省钱比例为负，模型有 bug"
        assert r["with_cache_total"] <= r["no_cache_total"]


def test_ttl_renewal_5min_vs_1h() -> None:
    """间隔 6min（> 5min TTL）场景下：
    - 5m_renew：每次都 miss，等于 100 次写入
    - 1h：1 次写入即可（间隔 6 < 60）
    Anthropic Sonnet 4.5 1h 模式总成本必然低于 5m_renew，且续写次数更少.
    """
    s = Scenario(
        name="间隔 6min × 100 次",
        system_prompt_tokens=8000,
        user_tokens_per_call=200,
        output_tokens_per_call=200,
        num_calls=100,
        interval_minutes=6.0,
    )
    p = PRICE_TABLES["anthropic_sonnet45"]

    r_5m = cost_with_cache(s, p, ttl_strategy="5m_renew")
    r_1h = cost_with_cache(s, p, ttl_strategy="1h")

    assert r_5m["renew_count"] == 100, "间隔 6min ≥ 5min TTL，理应每次都 miss"
    assert r_1h["renew_count"] == 1, "间隔 6min < 60min TTL，理应只写一次"
    assert r_1h["total_cost"] < r_5m["total_cost"], (
        f"1h TTL 总成本 ${r_1h['total_cost']} 应严格小于 5m_renew ${r_5m['total_cost']}"
    )


def test_compare_all_keys_match_registry() -> None:
    """compare_all 返回的 key 集合必须严格等于 PRICE_TABLES 的 key 集合."""
    s = _default_scenario()
    rows = compare_all(s)
    assert {r["key"] for r in rows} == set(PRICE_TABLES.keys())
