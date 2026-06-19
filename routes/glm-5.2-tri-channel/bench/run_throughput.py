"""
三通道吞吐压测：用 asyncio.gather 并发，统计 QPS / 成功率 / 平均延迟。

用法:
    python run_throughput.py --base-url http://localhost:8000 \
        --concurrency 16 --duration 30

输出:
    results_throughput.json
    results_throughput.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx

PROMPT_PATH = Path(__file__).parent / "prompts" / "short.txt"


async def worker(
    client: httpx.AsyncClient,
    base_url: str,
    prompt: str,
    stop_at: float,
    stats: dict,
) -> None:
    """单个 worker：在截止时间前不停发请求，统计 ok/fail/latency。"""
    payload = {
        "model": "glm-5.2",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 64,
    }
    while time.perf_counter() < stop_at:
        t0 = time.perf_counter()
        try:
            resp = await client.post(
                f"{base_url}/v1/chat/completions",
                json=payload,
                timeout=60.0,
            )
            elapsed = time.perf_counter() - t0
            if resp.status_code == 200:
                stats["ok"] += 1
                stats["latency_sum"] += elapsed
                picked = resp.json().get("router_picked")
                if picked:
                    stats["picked"][picked] = stats["picked"].get(picked, 0) + 1
            else:
                stats["fail"] += 1
        except Exception:  # noqa: BLE001
            stats["fail"] += 1


async def run_one(base_url: str, concurrency: int, duration: int, prompt: str) -> dict:
    """指定并发与持续时间，跑一次吞吐压测并汇总。"""
    stats = {"ok": 0, "fail": 0, "latency_sum": 0.0, "picked": {}}
    stop_at = time.perf_counter() + duration
    async with httpx.AsyncClient() as client:
        tasks = [
            asyncio.create_task(worker(client, base_url, prompt, stop_at, stats))
            for _ in range(concurrency)
        ]
        await asyncio.gather(*tasks)

    total = stats["ok"] + stats["fail"]
    qps = stats["ok"] / duration if duration > 0 else 0.0
    avg_lat_ms = (stats["latency_sum"] / stats["ok"] * 1000) if stats["ok"] else 0.0
    return {
        "concurrency": concurrency,
        "duration_s": duration,
        "total": total,
        "ok": stats["ok"],
        "fail": stats["fail"],
        "qps": round(qps, 2),
        "avg_latency_ms": round(avg_lat_ms, 1),
        "success_rate": round(stats["ok"] / total, 4) if total else 0.0,
        "picked_distribution": stats["picked"],
    }


async def main_async(args: argparse.Namespace) -> None:
    """主入口：跑指定参数组合，写 JSON + Markdown。"""
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"prompt 文件缺失: {PROMPT_PATH}")
    prompt = PROMPT_PATH.read_text(encoding="utf-8")

    results = []
    for c in args.concurrencies:
        print(f"[bench] concurrency={c} duration={args.duration}s")
        r = await run_one(args.base_url, c, args.duration, prompt)
        results.append(r)

    here = Path(__file__).parent
    (here / "results_throughput.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    md = [
        "# 三通道吞吐压测结果",
        "",
        f"- 压测时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 路由器: {args.base_url}",
        f"- 持续时间: {args.duration}s",
        "",
        "| 并发 | 总数 | 成功 | 失败 | QPS | 平均延迟 (ms) | 成功率 | 落点分布 |",
        "|------|------|------|------|-----|---------------|--------|----------|",
    ]
    for r in results:
        dist = ", ".join(f"{k}={v}" for k, v in r["picked_distribution"].items())
        md.append(
            f"| {r['concurrency']} | {r['total']} | {r['ok']} | {r['fail']} | "
            f"{r['qps']} | {r['avg_latency_ms']} | {r['success_rate']} | {dist} |"
        )
    (here / "results_throughput.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"[done] -> {here}/results_throughput.{{json,md}}")


def main() -> None:
    parser = argparse.ArgumentParser(description="GLM-5.2 三通道吞吐压测")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--concurrencies",
        type=int,
        nargs="+",
        default=[1, 4, 16, 64],
        help="并发档位列表，默认 1/4/16/64",
    )
    parser.add_argument("--duration", type=int, default=30, help="每档持续秒数")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
