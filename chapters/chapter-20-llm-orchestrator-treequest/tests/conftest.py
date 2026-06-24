"""共享 pytest fixture。

把仓库根目录加入 sys.path，让 ``from treequest_minimal import ...`` 在
tests 目录下直接可用；提供常用 fixture：``rng`` / ``simple_generators`` /
``sample_tasks``。
"""
from __future__ import annotations

import json
import os
import random
import sys
from typing import Dict, Tuple

import pytest


# 把 chapter-20 根目录加到 sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def rng() -> random.Random:
    """确定性随机源，避免 CI 上偶发 flaky。"""
    return random.Random(20260620)


@pytest.fixture
def simple_generators(rng):
    """3 个最小可用的 generator——target=42 数字逼近任务。"""

    def _score(answer: int) -> float:
        return max(0.0, 1.0 - abs(answer - 42) / 100.0)

    def good(parent_state):
        # one-shot 命中率约 50%
        base = 42 + (rng.randint(-3, 3) if rng.random() < 0.5
                     else rng.randint(-50, 50))
        return base, _score(base)

    def refiner(parent_state):
        if parent_state is None:
            base = 42 + rng.randint(-30, 30)
        else:
            base = parent_state + rng.randint(-5, 5)
        return base, _score(base)

    def noisy(parent_state):
        base = 42 + rng.randint(-60, 60)
        return base, _score(base)

    return {"good": good, "refiner": refiner, "noisy": noisy}


@pytest.fixture
def sample_tasks() -> dict:
    here = os.path.dirname(__file__)
    path = os.path.abspath(os.path.join(here, "..", "data", "sample_tasks.json"))
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)
