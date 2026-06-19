"""第 12 篇配套 demo：Checkpoint 保存 + 断点续跑.

设计：
- StepRecord 描述一步的元信息：step_id / status / input / output
- CheckpointStore 提供 save / load / list 三个原子操作（落到 JSON 文件）
- DurableRunner 跑一段步骤序列，崩溃后用相同 run_id 再调 run，会从最近一个
  succeeded 的 step 之后继续

可独立运行：
    python checkpoint_demo.py
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class StepRecord:
    """单个步骤的检查点记录."""

    step_id: str
    status: str  # pending / running / succeeded / failed
    started_at: float = 0.0
    finished_at: float = 0.0
    input: Any = None
    output: Any = None
    error: str | None = None


@dataclass
class RunState:
    """一次 Durable 任务的整体状态."""

    run_id: str
    created_at: float = field(default_factory=time.time)
    steps: list[StepRecord] = field(default_factory=list)


class CheckpointStore:
    """文件系统上的 checkpoint 存储；每个 run 一个 JSON 文件.

    生产可换成 S3 / Postgres / Redis；接口保持一致即可。
    """

    def __init__(self, base_dir: str | os.PathLike[str]) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        return self.base_dir / f"{run_id}.json"

    def save(self, state: RunState) -> None:
        """原子写：先写 .tmp 再 rename，避免半截文件."""
        target = self._path(state.run_id)
        tmp = target.with_suffix(".tmp")
        payload = {
            "run_id": state.run_id,
            "created_at": state.created_at,
            "steps": [asdict(s) for s in state.steps],
        }
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)

    def load(self, run_id: str) -> RunState | None:
        """加载已有 run；不存在返回 None."""
        p = self._path(run_id)
        if not p.exists():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        steps = [StepRecord(**s) for s in raw.get("steps", [])]
        return RunState(run_id=raw["run_id"], created_at=raw["created_at"], steps=steps)

    def delete(self, run_id: str) -> None:
        self._path(run_id).unlink(missing_ok=True)


class DurableRunner:
    """带 checkpoint 的步骤执行器.

    使用方法：
        runner = DurableRunner(store)
        runner.run("my-run", [
            ("fetch", lambda inp: ...),
            ("transform", lambda inp: ...),
        ], initial_input={...})

    第一次执行会从头跑；中间崩溃后用相同 run_id 再调 run，会自动跳过
    已经 succeeded 的步骤，只从断点继续。
    """

    def __init__(self, store: CheckpointStore) -> None:
        self.store = store

    def run(
        self,
        run_id: str,
        steps: list[tuple[str, Callable[[Any], Any]]],
        initial_input: Any = None,
    ) -> Any:
        """跑一段步骤序列.

        Args:
            run_id: 唯一标识，复用相同 id 即可断点续跑
            steps: [(step_name, fn)] 列表，fn 签名为 fn(prev_output) -> new_output
            initial_input: 第一步的输入

        Returns:
            最后一步的 output

        Raises:
            原 step fn 抛出的异常会被记录后再抛出
        """
        state = self.store.load(run_id) or RunState(run_id=run_id)
        # 把现有 steps 按 step_id 索引
        existing = {s.step_id: s for s in state.steps}
        prev_output = initial_input

        for step_name, fn in steps:
            rec = existing.get(step_name)
            if rec is not None and rec.status == "succeeded":
                prev_output = rec.output
                continue
            if rec is None:
                rec = StepRecord(step_id=step_name, status="pending", input=prev_output)
                state.steps.append(rec)
                existing[step_name] = rec
            rec.status = "running"
            rec.started_at = time.time()
            rec.input = prev_output
            self.store.save(state)
            try:
                rec.output = fn(prev_output)
                rec.status = "succeeded"
                rec.finished_at = time.time()
                self.store.save(state)
                prev_output = rec.output
            except Exception as exc:  # noqa: BLE001
                rec.status = "failed"
                rec.error = repr(exc)
                rec.finished_at = time.time()
                self.store.save(state)
                raise
        return prev_output


def _flaky_step_factory(fail_first_n: int):
    """造一个前 N 次会失败、之后成功的 step，用于演示断点续跑."""
    state = {"count": 0}

    def step(inp: Any) -> Any:
        state["count"] += 1
        if state["count"] <= fail_first_n:
            raise RuntimeError("simulated transient failure")
        return f"processed:{inp}"

    return step


def main() -> None:  # pragma: no cover
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        store = CheckpointStore(d)
        runner = DurableRunner(store)
        run_id = f"demo-{uuid.uuid4().hex[:6]}"

        # 第 2 步会失败一次再成功
        flaky = _flaky_step_factory(fail_first_n=1)
        steps = [
            ("fetch", lambda inp: f"raw:{inp}"),
            ("transform", flaky),
            ("emit", lambda inp: f"emit({inp})"),
        ]
        try:
            runner.run(run_id, steps, initial_input="seed")
        except RuntimeError as exc:
            print(f"first run crashed at step transform: {exc}")

        print("--- 重新跑相同 run_id，应自动跳过 fetch、重试 transform ---")
        out = runner.run(run_id, steps, initial_input="seed")
        print(f"final output: {out}")
        st = store.load(run_id)
        assert st is not None
        for s in st.steps:
            print(f"  step {s.step_id:12s} -> {s.status}")


if __name__ == "__main__":  # pragma: no cover
    main()
