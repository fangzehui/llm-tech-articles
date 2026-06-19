"""
三通道延迟压测：TTFT 与端到端延迟（短/中/长 prompt × P50/P95）。

用法:
    # 启动 router 后
    python run_latency.py --base-url http://localhost:8000 --runs 50

输出:
    results_latency.json：原始数据
    results_latency.md  ：Markdown 表格
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx

PROMPTS = {
    "short": "prompts/short.txt",
    "medium": "prompts/medium.txt",
    "long": "prompts/long.txt",
}


def percentile(data: list[float], p: float) -> float:
    """计算分位数（线性插值），p ∈ [0, 100]。"""
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


async def one_request(client: httpx.AsyncClient, base_url: str, prompt: str) -> dict:
    """发起一次 chat/completions 请求并测量 TTFT 与总耗时。"""
    payload = {
        "model": "glm-5.2",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 256,
        "stream": False,
    }
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            f"{base_url}/v1/chat/completions",
            json=payload,
            timeout=120.0,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        ok = resp.status_code == 200
        picked = None
        if ok:
            try:
                picked = resp.json().get("router_picked")
            except Exception:  # noqa: BLE001
                pass
        return {"ok": ok, "elapsed_ms": elapsed_ms, "status": resp.status_code, "picked": picked}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "elapsed_ms": (time.perf_counter() - t0) * 1000,
            "error": str(exc),
            "picked": None,
        }


async def bench_one(base_url: str, prompt_name: str, prompt: str, runs: int) -> dict:
    """对单一 prompt 串行跑 N 次，输出延迟分布。"""
    print(f"[bench] prompt={prompt_name} runs={runs}")
    samples: list[float] = []
    pickeds: dict[str, int] = {}
    fail = 0
    async with httpx.AsyncClient() as client:
        for i in range(runs):
            r = await one_request(client, base_url, prompt)
            if r["ok"]:
                samples.append(r["elapsed_ms"])
                k = r.get("picked") or "unknown"
                pickeds[k] = pickeds.get(k, 0) + 1
            else:
                fail += 1
    return {
        "prompt": prompt_name,
        "runs": runs,
        "ok": len(samples),
        "fail": fail,
        "p50_ms": round(percentile(samples, 50), 1),
        "p95_ms": round(percentile(samples, 95), 1),
        "mean_ms": round(statistics.fmean(samples), 1) if samples else 0,
        "picked_distribution": pickeds,
    }


async def main_async(args: argparse.Namespace) -> None:
    """主入口：依次对短/中/长 prompt 跑测，结果同时写 JSON 与 Markdown。"""
    here = Path(__file__).parent
    results = []
    for name, rel in PROMPTS.items():
        path = here / rel
        if not path.exists():
            print(f"[skip] {path} 不存在")
            continue
        prompt = path.read_text(encoding="utf-8")
        r = await bench_one(args.base_url, name, prompt, args.runs)
        results.append(r)

    out_json = here / "results_latency.json"
    out_json.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[done] JSON -> {out_json}")

    md_lines = [
        "# 三通道延迟压测结果",
        "",
        f"- 压测时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 路由器: {args.base_url}",
        f"- 每档样本数: {args.runs}",
        "",
        "| Prompt | OK | Fail | P50 (ms) | P95 (ms) | Mean (ms) | 落点分布 |",
        "|--------|----|------|----------|----------|-----------|----------|",
    ]
    for r in results:
        dist = ", ".join(f"{k}={v}" for k, v in r["picked_distribution"].items())
        md_lines.append(
            f"| {r['prompt']} | {r['ok']} | {r['fail']} | {r['p50_ms']} | "
            f"{r['p95_ms']} | {r['mean_ms']} | {dist} |"
        )
    out_md = here / "results_latency.md"
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"[done] MD   -> {out_md}")


def main() -> None:
    parser = argparse.ArgumentParser(description="GLM-5.2 三通道延迟压测")
    parser.add_argument("--base-url", default="http://localhost:8000", help="路由器地址")
    parser.add_argument("--runs", type=int, default=20, help="每档 prompt 的样本数")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
