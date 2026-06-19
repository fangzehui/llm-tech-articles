"""第 12 篇 smoke test：演示断点续跑 + 检查点幂等.

跑法：
    pytest test_smoke.py -q
"""

from __future__ import annotations

import os
import tempfile
import uuid

import pytest

from checkpoint_demo import (
    CheckpointStore,
    DurableRunner,
    StepRecord,
    _flaky_step_factory,
)


def test_save_and_load_roundtrip() -> None:
    """保存后能原样 load 回来."""
    with tempfile.TemporaryDirectory() as d:
        store = CheckpointStore(d)
        runner = DurableRunner(store)
        run_id = f"t-{uuid.uuid4().hex[:6]}"
        runner.run(
            run_id,
            [("a", lambda inp: f"A({inp})"), ("b", lambda inp: f"B({inp})")],
            initial_input="x",
        )
        state = store.load(run_id)
        assert state is not None
        assert [s.step_id for s in state.steps] == ["a", "b"]
        assert all(s.status == "succeeded" for s in state.steps)


def test_resume_after_failure() -> None:
    """第一次中途失败，第二次相同 run_id 应能续跑."""
    with tempfile.TemporaryDirectory() as d:
        store = CheckpointStore(d)
        runner = DurableRunner(store)
        run_id = f"t-{uuid.uuid4().hex[:6]}"
        flaky = _flaky_step_factory(fail_first_n=1)
        steps = [
            ("fetch", lambda inp: f"raw:{inp}"),
            ("transform", flaky),
            ("emit", lambda inp: f"emit({inp})"),
        ]
        with pytest.raises(RuntimeError):
            runner.run(run_id, steps, initial_input="seed")
        # 第二次应当跳过 fetch，重跑 transform，再跑 emit
        out = runner.run(run_id, steps, initial_input="seed")
        assert out.startswith("emit(")
        st = store.load(run_id)
        assert st is not None
        statuses = [s.status for s in st.steps]
        assert statuses == ["succeeded", "succeeded", "succeeded"]


def test_atomic_save_no_partial_file() -> None:
    """模拟写入时不会留下 .tmp 残骸."""
    with tempfile.TemporaryDirectory() as d:
        store = CheckpointStore(d)
        runner = DurableRunner(store)
        run_id = "atomic-1"
        runner.run(run_id, [("only", lambda inp: 1)], initial_input=None)
        files = os.listdir(d)
        assert any(f == f"{run_id}.json" for f in files)
        assert not any(f.endswith(".tmp") for f in files)


def test_step_record_fields() -> None:
    """StepRecord 关键字段被正确填充."""
    rec = StepRecord(step_id="x", status="pending")
    assert rec.input is None and rec.output is None and rec.error is None
