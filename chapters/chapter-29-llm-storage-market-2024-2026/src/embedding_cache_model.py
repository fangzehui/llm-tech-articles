"""向量库 embedding cache 命中率对总成本影响的推演模型

参考 2026-07-06 Pinecone Serverless 刊例：
- 未命中一次向量检索约 $0.001（含存储 + 读单元均摊）
- 命中缓存的一次查询约 $0.0001（本地 KV 命中）

命中率从 0% 到 90% 时，总成本呈线性递减。
"""

from dataclasses import dataclass
from typing import List, Dict


DEFAULT_MISS_COST_USD = 0.001
DEFAULT_HIT_COST_USD = 0.0001


@dataclass
class EmbeddingCacheCostModel:
    miss_cost_usd: float = DEFAULT_MISS_COST_USD
    hit_cost_usd: float = DEFAULT_HIT_COST_USD

    def monthly_cost(self, monthly_queries: int, hit_rate: float) -> float:
        """给定月度查询次数和命中率，估算月度成本（美元）"""
        if monthly_queries < 0:
            raise ValueError("monthly_queries must be non-negative")
        if not 0.0 <= hit_rate <= 1.0:
            raise ValueError("hit_rate must be in [0, 1]")
        hits = monthly_queries * hit_rate
        misses = monthly_queries * (1 - hit_rate)
        return hits * self.hit_cost_usd + misses * self.miss_cost_usd

    def sweep(self, monthly_queries: int, hit_rates: List[float]) -> List[Dict[str, float]]:
        """扫描一组命中率，返回每一档的成本与相对节省"""
        base = self.monthly_cost(monthly_queries, 0.0)
        rows = []
        for hr in hit_rates:
            cost = self.monthly_cost(monthly_queries, hr)
            saving = 0.0 if base == 0 else (base - cost) / base
            rows.append({"hit_rate": hr, "monthly_cost_usd": cost, "saving_ratio": saving})
        return rows

    def marginal_saving_per_10pct(self, monthly_queries: int) -> float:
        """每提升 10% 命中率，边际节省的月成本（美元）"""
        base = self.monthly_cost(monthly_queries, 0.0)
        step = self.monthly_cost(monthly_queries, 0.1)
        return base - step


if __name__ == "__main__":
    model = EmbeddingCacheCostModel()
    monthly_q = 1_500_000  # 场景 3：月 150 万次查询
    for hr in [0.0, 0.3, 0.5, 0.7, 0.9]:
        cost = model.monthly_cost(monthly_q, hr)
        print(f"命中率 {hr:.0%}：月成本 ${cost:.2f}")
    print(f"每 +10% 命中率边际节省：${model.marginal_saving_per_10pct(monthly_q):.2f}/月")
