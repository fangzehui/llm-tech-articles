"""第 05 篇配套 demo：跑 prompt 集合对比模型延迟与 token 用量.

只用 mock 后端，不发起真实 API 请求，所以可以脱网跑通。
真实落地时可以把 _call 替换成 OpenAI 兼容 SDK。

可独立运行：
    python benchmark_runner.py
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import MockLLMClient  # noqa: E402


@dataclass
class BenchCase:
    """评测用的单条 prompt."""

    case_id: str
    prompt: str
    category: str = "general"


@dataclass
class BenchResult:
    """单次调用的评测结果."""

    case_id: str
    model: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    ok: bool


def load_cases(path: Path) -> list[BenchCase]:
    """从 json 文件加载评测用例."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [BenchCase(**c) for c in raw]


def build_clients() -> dict[str, MockLLMClient]:
    """返回一组 mock 客户端，模拟不同档位模型.

    base_latency 是大致量级，仅用于演示对比逻辑。
    实际延迟请以真实 API 测试为准。
    """
    return {
        "small-fast": MockLLMClient("vendorA", "small-fast", 60, seed=11),
        "mid-balance": MockLLMClient("vendorB", "mid-balance", 120, seed=12),
        "flagship": MockLLMClient("vendorC", "flagship", 200, seed=13),
    }


def run_benchmark(
    cases: list[BenchCase], clients: dict[str, MockLLMClient]
) -> list[BenchResult]:
    """对每个 case × 每个 client 跑一遍.

    Args:
        cases: 评测用例
        clients: 模型名 -> 客户端

    Returns:
        BenchResult 列表
    """
    results: list[BenchResult] = []
    for case in cases:
        for name, client in clients.items():
            try:
                resp = client.chat([{"role": "user", "content": case.prompt}])
                results.append(
                    BenchResult(
                        case_id=case.case_id,
                        model=name,
                        latency_ms=resp.latency_ms,
                        prompt_tokens=resp.prompt_tokens,
                        completion_tokens=resp.completion_tokens,
                        ok=True,
                    )
                )
            except Exception:  # noqa: BLE001
                results.append(
                    BenchResult(
                        case_id=case.case_id,
                        model=name,
                        latency_ms=0.0,
                        prompt_tokens=0,
                        completion_tokens=0,
                        ok=False,
                    )
                )
    return results


def aggregate(results: list[BenchResult]) -> dict[str, dict[str, float]]:
    """按模型聚合延迟 P50/P95、token 平均."""
    by_model: dict[str, list[BenchResult]] = {}
    for r in results:
        by_model.setdefault(r.model, []).append(r)
    out: dict[str, dict[str, float]] = {}
    for model, rs in by_model.items():
        ok = [r for r in rs if r.ok]
        latencies = [r.latency_ms for r in ok] or [0.0]
        out[model] = {
            "n": float(len(rs)),
            "ok_rate": len(ok) / max(1, len(rs)),
            "p50_ms": statistics.median(latencies),
            "p95_ms": (
                statistics.quantiles(latencies, n=20)[-1]
                if len(latencies) >= 20
                else max(latencies)
            ),
            "avg_prompt_tokens": (
                statistics.mean(r.prompt_tokens for r in ok) if ok else 0.0
            ),
            "avg_completion_tokens": (
                statistics.mean(r.completion_tokens for r in ok) if ok else 0.0
            ),
        }
    return out


def main() -> None:  # pragma: no cover
    here = Path(__file__).resolve().parent
    cases = load_cases(here / "prompts.json")
    clients = build_clients()
    results = run_benchmark(cases, clients)
    summary = aggregate(results)
    print(f"ran {len(cases)} cases x {len(clients)} models")
    for model, stats in summary.items():
        print(f"  {model:12s} -> {json.dumps(stats, ensure_ascii=False)}")
    if "--dump" in sys.argv:
        for r in results:
            print(json.dumps(asdict(r), ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover
    main()
