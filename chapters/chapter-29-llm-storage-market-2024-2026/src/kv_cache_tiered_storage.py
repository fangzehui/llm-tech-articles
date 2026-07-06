"""KV-Cache 分层落盘策略

模拟 hot / warm / cold 三层调度：
- hot: HBM 层，容量最小，每 GB 成本最高（此处只算相对权重）
- warm: 本地 NVMe / SSD 层，容量中等
- cold: 对象存储冷层，容量最大，每 GB 成本最低

策略：LRU 淘汰 + 层间自动迁移。
每次 access(session_id, size_gb) 时：
  - 若已在某层，命中该层并提升到 hot 队列头部；
  - 若未命中，加入 hot；hot 溢出的项落到 warm；warm 溢出的项落到 cold；cold 溢出直接丢弃。

来源参考：
  正文 §2.2 KV-Cache 落盘（HBF 概念）
  正文 §5 场景 2 推理 KV-Cache 三层调度成本推演
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, Tuple


TIER_HOT = "hot"
TIER_WARM = "warm"
TIER_COLD = "cold"
TIER_MISS = "miss"


@dataclass
class TieredKVCache:
    hot_cap_gb: float
    warm_cap_gb: float
    cold_cap_gb: float
    # 每 GB 相对成本权重，参考 AliOSS 阶梯：NVMe 温层 ≈ 0.15, 低频冷 ≈ 0.07, 归档 ≈ 0.03
    hot_cost_per_gb: float = 0.5
    warm_cost_per_gb: float = 0.15
    cold_cost_per_gb: float = 0.07

    hot: "OrderedDict[str, float]" = field(default_factory=OrderedDict)
    warm: "OrderedDict[str, float]" = field(default_factory=OrderedDict)
    cold: "OrderedDict[str, float]" = field(default_factory=OrderedDict)

    hits: Dict[str, int] = field(default_factory=lambda: {TIER_HOT: 0, TIER_WARM: 0, TIER_COLD: 0, TIER_MISS: 0})

    def _total(self, layer: "OrderedDict[str, float]") -> float:
        return sum(layer.values())

    def _evict(self, layer: "OrderedDict[str, float]", cap: float) -> Dict[str, float]:
        evicted: Dict[str, float] = {}
        while self._total(layer) > cap and layer:
            k, v = layer.popitem(last=False)  # 淘汰最旧
            evicted[k] = v
        return evicted

    def access(self, session_id: str, size_gb: float) -> str:
        """访问一次 session_id，返回本次命中层级。会自动做层间迁移。"""
        if size_gb <= 0:
            raise ValueError("size_gb must be positive")

        hit_tier = TIER_MISS
        for tier, layer in ((TIER_HOT, self.hot), (TIER_WARM, self.warm), (TIER_COLD, self.cold)):
            if session_id in layer:
                hit_tier = tier
                del layer[session_id]
                break

        self.hot[session_id] = size_gb
        self.hits[hit_tier] += 1

        # 逐层溢出
        to_warm = self._evict(self.hot, self.hot_cap_gb)
        for k, v in to_warm.items():
            self.warm[k] = v
        to_cold = self._evict(self.warm, self.warm_cap_gb)
        for k, v in to_cold.items():
            self.cold[k] = v
        self._evict(self.cold, self.cold_cap_gb)  # cold 溢出丢弃

        return hit_tier

    def usage(self) -> Tuple[float, float, float]:
        return self._total(self.hot), self._total(self.warm), self._total(self.cold)

    def hit_rate(self) -> Dict[str, float]:
        total = sum(self.hits.values())
        if total == 0:
            return {k: 0.0 for k in self.hits}
        return {k: v / total for k, v in self.hits.items()}

    def monthly_cost(self) -> float:
        """按当前占用量估算月度成本（元/月）"""
        h, w, c = self.usage()
        return h * self.hot_cost_per_gb + w * self.warm_cost_per_gb + c * self.cold_cost_per_gb


if __name__ == "__main__":
    cache = TieredKVCache(hot_cap_gb=2.0, warm_cap_gb=5.0, cold_cap_gb=20.0)
    for sid in range(30):
        cache.access(f"s{sid}", 0.5)
    # 反复访问前 4 个，让它们成为高频
    for _ in range(10):
        for sid in range(4):
            cache.access(f"s{sid}", 0.5)
    print("usage (H/W/C GB):", cache.usage())
    print("hit rate:", cache.hit_rate())
    print("monthly cost (¥):", round(cache.monthly_cost(), 3))
