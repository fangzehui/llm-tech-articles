"""
基于 GSM8K / HumanEval 子集的快速回归评测脚本。

设计目标:
    每次 GLM-5.2 通道升级或路由策略调整后，跑一遍这个脚本，
    确认核心数学/代码能力没有出现回归。为了保证 CI 时长可接受，
    每个 benchmark 只取前 20 条样本作为快速烟囱测试。

用法:
    # 1. 按 datasets/README.md 准备数据；
    # 2. 启动 router；
    # 3. 运行：
    python run_eval.py --base-url http://localhost:8000 \
        --benchmark gsm8k --limit 20

输出:
    results_eval_<benchmark>.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

DATASETS_DIR = Path(__file__).parent / "datasets"


def load_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    """从本地 JSONL 文件读取前 N 条样本。"""
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
            if len(items) >= limit:
                break
    return items


def parse_gsm8k_answer(text: str) -> str | None:
    """从 GSM8K 标注里提取最终数字答案（"#### 42" 形式）。"""
    m = re.search(r"####\s*([\-0-9.,/]+)", text)
    if not m:
        return None
    return m.group(1).replace(",", "").strip()


def parse_model_number(text: str) -> str | None:
    """从模型回复里抽取最末尾的数值（容错最常见的几种表达）。"""
    nums = re.findall(r"-?\d+(?:\.\d+)?", text or "")
    return nums[-1] if nums else None


async def call_router(
    client: httpx.AsyncClient,
    base_url: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    """统一的 router 调用包装。"""
    payload = {"model": "glm-5.2", "messages": messages, "temperature": 0, "max_tokens": 512}
    resp = await client.post(f"{base_url}/v1/chat/completions", json=payload, timeout=120.0)
    resp.raise_for_status()
    return resp.json()


async def eval_gsm8k(base_url: str, limit: int) -> dict[str, Any]:
    """GSM8K 数学子集快速回归。"""
    path = DATASETS_DIR / "gsm8k_test.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"未找到数据集 {path}，请按 datasets/README.md 下载")
    items = load_jsonl(path, limit)
    correct = 0
    detail: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        for i, item in enumerate(items):
            q = item["question"]
            gold = parse_gsm8k_answer(item["answer"])
            try:
                resp = await call_router(
                    client,
                    base_url,
                    [
                        {
                            "role": "system",
                            "content": "你是一个数学家。请逐步计算，最后一行只输出数字答案。",
                        },
                        {"role": "user", "content": q},
                    ],
                )
                pred_text = resp["choices"][0]["message"]["content"]
                pred = parse_model_number(pred_text)
                ok = pred is not None and gold is not None and float(pred) == float(gold)
                correct += int(ok)
                detail.append(
                    {
                        "idx": i,
                        "gold": gold,
                        "pred": pred,
                        "ok": ok,
                        "picked": resp.get("router_picked"),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                detail.append({"idx": i, "error": str(exc)})

    return {
        "benchmark": "gsm8k",
        "total": len(items),
        "correct": correct,
        "accuracy": round(correct / len(items), 4) if items else 0.0,
        "detail": detail,
    }


async def eval_humaneval(base_url: str, limit: int) -> dict[str, Any]:
    """HumanEval 代码子集——本脚本只做"是否生成了非空 Python 代码块"的烟囱判定。

    严肃评测请配合官方 evaluate 脚本在沙箱环境运行；这里只做快速回归。
    """
    path = DATASETS_DIR / "humaneval_test.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"未找到数据集 {path}，请按 datasets/README.md 下载")
    items = load_jsonl(path, limit)
    has_code = 0
    detail: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        for i, item in enumerate(items):
            prompt = item["prompt"]
            try:
                resp = await call_router(
                    client,
                    base_url,
                    [
                        {
                            "role": "system",
                            "content": "你是一个 Python 工程师，按要求补全代码，只返回代码块。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                )
                content = resp["choices"][0]["message"]["content"]
                ok = "def " in content or "```" in content
                has_code += int(ok)
                detail.append(
                    {"idx": i, "ok": ok, "picked": resp.get("router_picked")}
                )
            except Exception as exc:  # noqa: BLE001
                detail.append({"idx": i, "error": str(exc)})

    return {
        "benchmark": "humaneval",
        "total": len(items),
        "code_emitted": has_code,
        "code_emit_rate": round(has_code / len(items), 4) if items else 0.0,
        "detail": detail,
    }


async def main_async(args: argparse.Namespace) -> None:
    """主入口：根据 --benchmark 参数选择评测，写 JSON。"""
    if args.benchmark == "gsm8k":
        result = await eval_gsm8k(args.base_url, args.limit)
    elif args.benchmark == "humaneval":
        result = await eval_humaneval(args.base_url, args.limit)
    else:
        raise ValueError(f"unknown benchmark: {args.benchmark}")

    out = Path(__file__).parent / f"results_eval_{args.benchmark}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[done] {args.benchmark} -> {out}")
    if "accuracy" in result:
        print(f"accuracy = {result['accuracy']}")
    if "code_emit_rate" in result:
        print(f"code_emit_rate = {result['code_emit_rate']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="GLM-5.2 路由器快速回归评测")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--benchmark", choices=["gsm8k", "humaneval"], default="gsm8k"
    )
    parser.add_argument("--limit", type=int, default=20, help="样本数（默认 20）")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
