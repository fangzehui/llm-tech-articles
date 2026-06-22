"""共享 pytest fixture。

主要做两件事：
1. 把仓库根目录加入 ``sys.path``，让 ``from weekly_tracker import ...`` 在
   tests 目录下直接可用；
2. 提供一个 ``snapshot`` fixture，跨多个用例复用。
"""
from __future__ import annotations

import os
import sys

import pytest

# 把 chapters/chapter-18-... 根目录加到 sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def snapshot():
    """加载本地 sample_weekly.json 的 WeekSnapshot，供所有用例复用."""
    from weekly_tracker import load_local
    return load_local()


@pytest.fixture
def default_scenario():
    """缺省场景画像：中等频次 Agent，工具调用 + 价格敏感."""
    from signal_analyzer import ScenarioProfile
    return ScenarioProfile(
        name="default",
        needs_long_context=False,
        needs_thinking=False,
        needs_tool_call=True,
        sensitive_to_price=True,
        min_context_tokens=32_000,
    )
