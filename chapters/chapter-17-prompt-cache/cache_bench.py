"""第 17 篇配套 demo: Prompt Cache 五家成本横评（Anthropic / OpenAI / Gemini / 智谱 / DeepSeek）.

设计：
- ``PriceTable`` 描述一家厂商一个具体型号的 Prompt Cache 计费四件套
  （input / output / cache_write / cache_read，单位 USD / 1M tokens），并附最小
  缓存粒度、默认 TTL、命中机制等元数据
- ``PRICE_TABLES`` 注册表收录 6 款主流模型：Sonnet 4.5 / Fable 5 / GPT-5 /
  Gemini 3 Pro / GLM-5.2 / DeepSeek V3.2
- ``Scenario`` 描述一个"长系统提示词复用"场景：system_prompt_tokens × num_calls
  + 每次 user_tokens / output_tokens
- ``cost_no_cache`` / ``cost_with_cache`` 把 (Scenario, PriceTable) 折算成总成本
  字典；后者支持 ``default`` / ``5m_renew`` / ``1h`` 三种 TTL 策略
- ``compare_all`` 五家横评 + 按省钱比例降序
- ``break_even`` 第几次轮询开始 cache 净回本

可独立运行：
    python cache_bench.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


# ============================================================================
# 一、计费表
# ============================================================================

@dataclass
class PriceTable:
    """单家模型的 Prompt Cache 计费四件套.

    四个核心价格字段单位均为 USD / 1M tokens；``cache_write_long`` 仅 Anthropic
    在 1h 长 TTL 模式下使用，其它厂商保持 ``None`` 即可.
    """

    name: str
    input: float                       # 标准输入价
    output: float                      # 输出价
    cache_write: float                 # cache miss / 写缓存价（首次或续写）
    cache_read: float                  # cache hit / 读缓存价
    cache_write_long: float | None = None   # 1h TTL 写入价（仅 Anthropic）
    min_cache_tokens: int = 1024       # 触发缓存的最小 token 数
    default_ttl_minutes: int = 5       # 默认 TTL（分钟）
    max_ttl_minutes: int = 60          # 最长可配置 TTL（分钟）
    trigger_mechanism: str = "auto_prefix"  # explicit_cache_control / auto_prefix / cached_contents / disk_kv


# 6 家计费表，价格截至 2026-06-19，参见正文 §三 厂商官方文档表.
PRICE_TABLES: dict[str, PriceTable] = {
    # Anthropic Claude Sonnet 4.5（2025-09 公开价，2026-06 仍为现价）
    "anthropic_sonnet45": PriceTable(
        name="Claude Sonnet 4.5",
        input=3.0, output=15.0,
        cache_write=3.75,         # 5min: input × 1.25
        cache_write_long=6.0,     # 1h:   input × 2.0
        cache_read=0.30,          # input × 0.10
        min_cache_tokens=1024,
        default_ttl_minutes=5,
        max_ttl_minutes=60,
        trigger_mechanism="explicit_cache_control",
    ),
    # Anthropic Claude Fable 5（本系列虚拟旗舰，对标 Opus 5.x；与 14 号文一致）
    "anthropic_fable5": PriceTable(
        name="Claude Fable 5",
        input=10.0, output=50.0,
        cache_write=12.5,         # 5min: 1.25×
        cache_write_long=20.0,    # 1h:   2.0×
        cache_read=1.0,           # 0.10×
        min_cache_tokens=1024,
        default_ttl_minutes=5,
        max_ttl_minutes=60,
        trigger_mechanism="explicit_cache_control",
    ),
    # OpenAI GPT-5（2025-08 launch）
    "openai_gpt5": PriceTable(
        name="GPT-5",
        input=1.25, output=10.0,
        cache_write=1.25,         # 自动前缀缓存，写入按标准输入价（无溢价）
        cache_read=0.125,         # 90% off
        min_cache_tokens=1024,
        default_ttl_minutes=10,   # 5-10 min 闲置回收，热门可延长
        max_ttl_minutes=60,
        trigger_mechanism="auto_prefix",
    ),
    # Google Gemini 3 Pro（Vertex AI / AI Studio 显式 cachedContents）
    "gemini_3_pro": PriceTable(
        name="Gemini 3 Pro",
        input=1.00, output=4.00,
        cache_write=1.00,         # 显式 cachedContents 创建按标准输入价
        cache_read=0.10,          # input × 0.10
        min_cache_tokens=4096,    # Pro 系最低 4096 tokens
        default_ttl_minutes=60,
        max_ttl_minutes=24 * 60,
        trigger_mechanism="cached_contents",
    ),
    # 智谱 BigModel GLM-5.2（隐式缓存）
    "glm_5_2": PriceTable(
        name="GLM-5.2",
        input=0.60, output=2.00,
        cache_write=0.60,         # 隐式缓存写入 = 标准输入价
        cache_read=0.10,          # 与 14 号文一致
        min_cache_tokens=1024,
        default_ttl_minutes=10,
        max_ttl_minutes=60,
        trigger_mechanism="auto_prefix",
    ),
    # DeepSeek V3.2（硬盘缓存，64 token 起）
    "deepseek_v32": PriceTable(
        name="DeepSeek V3.2",
        input=0.07, output=1.10,
        cache_write=0.07,         # 硬盘缓存写入 = 标准输入价
        cache_read=0.014,         # 80% off
        min_cache_tokens=64,
        default_ttl_minutes=60,   # 几小时到几天，按 best-effort
        max_ttl_minutes=24 * 60,
        trigger_mechanism="disk_kv",
    ),
}


# ============================================================================
# 二、场景
# ============================================================================

@dataclass
class Scenario:
    """长系统提示词 × N 次轮询场景.

    Attributes:
        system_prompt_tokens: 长系统提示 token 数（默认 8000，对应一份典型客服 Bot
            instruction + few-shot + RAG context 拼接后的体量）
        user_tokens_per_call: 每次用户输入 token 数（变化部分，不可缓存）
        output_tokens_per_call: 每次输出 token 数
        num_calls: 总轮询次数
        cache_ttl_minutes: 期望的 TTL；用于 Anthropic 选 5m 还是 1h 价
        interval_minutes: 相邻两次调用的间隔（决定 5m TTL 是否能持续续命）
    """

    name: str
    system_prompt_tokens: int = 8000
    user_tokens_per_call: int = 200
    output_tokens_per_call: int = 200
    num_calls: int = 100
    cache_ttl_minutes: int = 5
    interval_minutes: float = 0.5


# ============================================================================
# 三、成本模型
# ============================================================================

def cost_no_cache(s: Scenario, p: PriceTable) -> dict[str, float]:
    """不开缓存：每次都把 system + user 当全新输入算一遍.

    Returns:
        ``{"input_cost": ..., "output_cost": ..., "total_cost": ...}``，
        单位 USD.
    """
    total_input_tokens = (s.system_prompt_tokens + s.user_tokens_per_call) * s.num_calls
    total_output_tokens = s.output_tokens_per_call * s.num_calls
    input_cost = total_input_tokens / 1_000_000 * p.input
    output_cost = total_output_tokens / 1_000_000 * p.output
    return {
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "total_cost": round(input_cost + output_cost, 6),
    }


def _compute_renew_count(s: Scenario, ttl: int) -> int:
    """根据请求间隔与 TTL，估算需要重写缓存的次数.

    模型简化为：
    - num_calls ≤ 1 → renew_count = num_calls
    - 间隔 < TTL → 1 次写入即可（cache 在每次命中时被自动续命）
    - 间隔 ≥ TTL → 每次都 miss，等于 num_calls 次写入
    """
    if s.num_calls <= 1:
        return s.num_calls
    if s.interval_minutes < ttl:
        return 1
    return s.num_calls


def cost_with_cache(
    s: Scenario,
    p: PriceTable,
    ttl_strategy: str = "default",
) -> dict[str, Any]:
    """开缓存：首次写入 system_prompt 走 cache_write，后续 N-1 次走 cache_read.

    Args:
        s: 场景
        p: 模型计费表
        ttl_strategy: 三选一
            - ``default``：使用 ``p.default_ttl_minutes`` 与 ``p.cache_write``
            - ``5m_renew``：强制按 5min TTL 续命（间隔 ≥ 5min 时退化为每次 miss）
            - ``1h``：使用 ``p.cache_write_long``（仅 Anthropic 有效，其余厂商
              ``cache_write_long`` 为 ``None`` 时回退到 ``cache_write``）

    Returns:
        ``{"cache_write_cost", "cache_read_cost", "user_input_cost", "output_cost",
        "total_cost", "renew_count"}``，单位 USD.
    """
    if ttl_strategy == "1h" and p.cache_write_long is not None:
        write_price = p.cache_write_long
        ttl = 60
    elif ttl_strategy == "5m_renew":
        write_price = p.cache_write
        ttl = 5
    else:
        write_price = p.cache_write
        ttl = p.default_ttl_minutes

    renew_count = _compute_renew_count(s, ttl)

    write_token_total = s.system_prompt_tokens * renew_count
    read_token_total = s.system_prompt_tokens * (s.num_calls - renew_count)
    user_input_total = s.user_tokens_per_call * s.num_calls
    output_total = s.output_tokens_per_call * s.num_calls

    write_cost = write_token_total / 1_000_000 * write_price
    read_cost = read_token_total / 1_000_000 * p.cache_read
    user_input_cost = user_input_total / 1_000_000 * p.input
    output_cost = output_total / 1_000_000 * p.output
    total = write_cost + read_cost + user_input_cost + output_cost

    return {
        "cache_write_cost": round(write_cost, 6),
        "cache_read_cost": round(read_cost, 6),
        "user_input_cost": round(user_input_cost, 6),
        "output_cost": round(output_cost, 6),
        "total_cost": round(total, 6),
        "renew_count": renew_count,
    }


def compare_all(s: Scenario) -> list[dict[str, Any]]:
    """对所有注册模型同时跑 no_cache vs with_cache，按省钱比例降序返回."""
    rows: list[dict[str, Any]] = []
    for key, p in PRICE_TABLES.items():
        no_c = cost_no_cache(s, p)
        with_c = cost_with_cache(s, p, ttl_strategy="default")
        savings_usd = no_c["total_cost"] - with_c["total_cost"]
        savings_pct = (
            savings_usd / no_c["total_cost"] * 100 if no_c["total_cost"] else 0.0
        )
        rows.append({
            "key": key,
            "name": p.name,
            "no_cache_total": no_c["total_cost"],
            "with_cache_total": with_c["total_cost"],
            "savings_usd": round(savings_usd, 4),
            "savings_pct": round(savings_pct, 1),
            "trigger": p.trigger_mechanism,
        })
    rows.sort(key=lambda x: x["savings_pct"], reverse=True)
    return rows


def break_even(
    s: Scenario,
    p: PriceTable,
    ttl_strategy: str = "default",
) -> int:
    """从第几次轮询开始，启用 cache 的总成本严格低于不开 cache？

    Returns:
        最小满足条件的 ``n``（1-indexed）；遍历至 ``s.num_calls`` 仍未回本时返回 ``-1``.
    """
    for n in range(1, s.num_calls + 1):
        sub = Scenario(
            name=s.name,
            system_prompt_tokens=s.system_prompt_tokens,
            user_tokens_per_call=s.user_tokens_per_call,
            output_tokens_per_call=s.output_tokens_per_call,
            num_calls=n,
            cache_ttl_minutes=s.cache_ttl_minutes,
            interval_minutes=s.interval_minutes,
        )
        if (
            cost_with_cache(sub, p, ttl_strategy)["total_cost"]
            < cost_no_cache(sub, p)["total_cost"]
        ):
            return n
    return -1


# ============================================================================
# 四、main demo
# ============================================================================

def main() -> None:  # pragma: no cover
    """跑 8000 token 系统提示 × 100 次轮询，间隔 30s 的典型场景."""
    s = Scenario(
        name="长系统提示 8K × 100 次轮询",
        system_prompt_tokens=8000,
        user_tokens_per_call=200,
        output_tokens_per_call=200,
        num_calls=100,
        interval_minutes=0.5,
    )
    print(f"\n=== 场景：{s.name} ===")
    print(
        f"  system={s.system_prompt_tokens} tok / "
        f"user={s.user_tokens_per_call} tok / "
        f"output={s.output_tokens_per_call} tok / "
        f"calls={s.num_calls} / 间隔 {s.interval_minutes} min"
    )

    print(
        f"\n{'模型':<20s} {'无cache$':>10s} {'有cache$':>10s} "
        f"{'省$':>8s} {'省比例':>8s}  机制"
    )
    for row in compare_all(s):
        print(
            f"  {row['name']:<18s} {row['no_cache_total']:>10.4f} "
            f"{row['with_cache_total']:>10.4f} {row['savings_usd']:>8.4f} "
            f"{row['savings_pct']:>7.1f}%  {row['trigger']}"
        )

    print("\n=== break-even 分析（第几次开始 cache 净回本）===")
    for _, p in PRICE_TABLES.items():
        be = break_even(s, p)
        print(f"  {p.name:<18s} break-even = {be} 次")

    # 5min vs 1h TTL 续命对比（仅 Anthropic 有效）
    print("\n=== 5min × N 续命 vs 1h 一把锁（间隔 6 min）===")
    s_long_interval = Scenario(
        name="间隔 6min × 100 次轮询",
        system_prompt_tokens=8000, user_tokens_per_call=200,
        output_tokens_per_call=200, num_calls=100,
        interval_minutes=6.0,
    )
    for key in ("anthropic_sonnet45", "anthropic_fable5"):
        p = PRICE_TABLES[key]
        r5 = cost_with_cache(s_long_interval, p, ttl_strategy="5m_renew")
        r1 = cost_with_cache(s_long_interval, p, ttl_strategy="1h")
        print(
            f"  {p.name:<18s} 5m_renew=${r5['total_cost']:.4f} "
            f"(写{r5['renew_count']}次) | "
            f"1h=${r1['total_cost']:.4f} (写{r1['renew_count']}次)"
        )


if __name__ == "__main__":  # pragma: no cover
    main()
