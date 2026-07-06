"""训练 checkpoint 分层存储成本计算器

参考 2026-07-06 阿里云 OSS 中国大陆刊例价：
- 标准（本地冗余）：0.09 元/GB/月
- 低频访问：0.07 元/GB/月
- 归档：0.03 元/GB/月
- 深度归档（腾讯云 COS 参考）：0.01 元/GB/月

策略：最近 N 个 checkpoint 保标准，往前 M 个保低频，再往前 P 个保归档，其余归深归档。
输入总 GB 数 + 各段占比，输出月度账单及各层占比。
"""

from dataclasses import dataclass
from typing import Dict


DEFAULT_STANDARD_PRICE = 0.09
DEFAULT_IA_PRICE = 0.07
DEFAULT_ARCHIVE_PRICE = 0.03
DEFAULT_DEEP_ARCHIVE_PRICE = 0.01


@dataclass
class CheckpointCostCalculator:
    standard_price: float = DEFAULT_STANDARD_PRICE
    ia_price: float = DEFAULT_IA_PRICE
    archive_price: float = DEFAULT_ARCHIVE_PRICE
    deep_archive_price: float = DEFAULT_DEEP_ARCHIVE_PRICE

    def bill(self, total_gb: float, ratios: Dict[str, float]) -> Dict[str, float]:
        """计算月度账单。

        Args:
            total_gb: 总 checkpoint 数据量（GB）
            ratios: 各层占比，键为 standard/ia/archive/deep_archive，值之和须为 1.0

        Returns:
            dict，包含各层月成本、总成本、各层占比。
        """
        if total_gb < 0:
            raise ValueError("total_gb must be non-negative")
        for k in ("standard", "ia", "archive", "deep_archive"):
            if k not in ratios:
                raise ValueError(f"missing ratio key: {k}")
            if ratios[k] < 0:
                raise ValueError(f"ratio {k} must be non-negative")
        s = sum(ratios.values())
        if abs(s - 1.0) > 1e-6:
            raise ValueError(f"ratios sum must be 1.0, got {s}")

        std_gb = total_gb * ratios["standard"]
        ia_gb = total_gb * ratios["ia"]
        arc_gb = total_gb * ratios["archive"]
        da_gb = total_gb * ratios["deep_archive"]

        std_cost = std_gb * self.standard_price
        ia_cost = ia_gb * self.ia_price
        arc_cost = arc_gb * self.archive_price
        da_cost = da_gb * self.deep_archive_price
        total_cost = std_cost + ia_cost + arc_cost + da_cost

        return {
            "standard_gb": std_gb,
            "ia_gb": ia_gb,
            "archive_gb": arc_gb,
            "deep_archive_gb": da_gb,
            "standard_cost": std_cost,
            "ia_cost": ia_cost,
            "archive_cost": arc_cost,
            "deep_archive_cost": da_cost,
            "total_cost": total_cost,
        }

    def flat_bill(self, total_gb: float, tier: str) -> float:
        """全部走同一层的月成本（对比基线用）"""
        price_map = {
            "standard": self.standard_price,
            "ia": self.ia_price,
            "archive": self.archive_price,
            "deep_archive": self.deep_archive_price,
        }
        if tier not in price_map:
            raise ValueError(f"unknown tier: {tier}")
        return total_gb * price_map[tier]


if __name__ == "__main__":
    calc = CheckpointCostCalculator()
    # 场景 1：中型 AI 公司年产 100 TB checkpoint，全部归档
    total = 100 * 1024  # GB
    b = calc.bill(total, {"standard": 0.0, "ia": 0.0, "archive": 1.0, "deep_archive": 0.0})
    print(f"100 TB 全归档月成本：¥{b['total_cost']:.2f}")
    # 相比标准存储省了多少
    flat = calc.flat_bill(total, "standard")
    print(f"vs 全标准月成本：¥{flat:.2f}，节省 {(1 - b['total_cost'] / flat) * 100:.1f}%")
