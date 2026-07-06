"""tests for checkpoint_cost_calculator"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from checkpoint_cost_calculator import CheckpointCostCalculator


def test_all_archive_100tb():
    calc = CheckpointCostCalculator()
    total = 100 * 1024  # 100 TB
    b = calc.bill(total, {"standard": 0.0, "ia": 0.0, "archive": 1.0, "deep_archive": 0.0})
    # 100 * 1024 * 0.03 = 3072
    assert b["total_cost"] == pytest.approx(3072.0)
    assert b["archive_cost"] == pytest.approx(3072.0)


def test_ratio_sum_check():
    calc = CheckpointCostCalculator()
    with pytest.raises(ValueError):
        calc.bill(100, {"standard": 0.5, "ia": 0.3, "archive": 0.1, "deep_archive": 0.05})


def test_negative_total_rejected():
    calc = CheckpointCostCalculator()
    with pytest.raises(ValueError):
        calc.bill(-1, {"standard": 1.0, "ia": 0.0, "archive": 0.0, "deep_archive": 0.0})


def test_missing_key_rejected():
    calc = CheckpointCostCalculator()
    with pytest.raises(ValueError):
        calc.bill(100, {"standard": 1.0})


def test_mixed_tier_bill():
    calc = CheckpointCostCalculator()
    # 1000 GB, 20% 标准 / 30% 低频 / 30% 归档 / 20% 深归档
    b = calc.bill(1000, {"standard": 0.2, "ia": 0.3, "archive": 0.3, "deep_archive": 0.2})
    # 200*0.09 + 300*0.07 + 300*0.03 + 200*0.01 = 18 + 21 + 9 + 2 = 50
    assert b["total_cost"] == pytest.approx(50.0)


def test_flat_bill_matches():
    calc = CheckpointCostCalculator()
    assert calc.flat_bill(1000, "standard") == pytest.approx(90.0)
    assert calc.flat_bill(1000, "deep_archive") == pytest.approx(10.0)


def test_unknown_tier_rejected():
    calc = CheckpointCostCalculator()
    with pytest.raises(ValueError):
        calc.flat_bill(100, "nvme")


def test_zero_total_returns_zero():
    calc = CheckpointCostCalculator()
    b = calc.bill(0, {"standard": 1.0, "ia": 0.0, "archive": 0.0, "deep_archive": 0.0})
    assert b["total_cost"] == 0.0
