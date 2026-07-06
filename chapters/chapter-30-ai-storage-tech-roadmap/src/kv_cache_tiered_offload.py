"""KV-Cache 四级卸载策略推演器

四级：L1 GPU HBM → L2 CPU DRAM → L3 CXL 内存池 → L4 NVMe SSD

数据来源：
- HBM3E 带宽 ~1.2 TB/s / stack；单卡多栈 → 单 GPU 3.35~8 TB/s
  https://semiconductor.samsung.com/kr/dram/hbm/hbm3e/
- DDR5 6400 单通道 ~51.2 GB/s；单 socket 12 通道 ~614 GB/s
  https://www.jedec.org/standards-documents/docs/jesd79-5b-01
- CXL 3.x x16 单向 64 GB/s (PCIe 6.0 base)
  https://www.computeexpresslink.org/
- PCIe 5.0 x4 NVMe SSD ~14 GB/s，PCIe 6.0 x4 ~28 GB/s
  https://pcisig.com/specifications
- 延迟数量级来自 LMCache / Beluga 论文
  https://docs.lmcache.ai/
  https://arxiv.org/html/2511.20172v2
"""
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class Tier:
    name: str
    capacity_gb: float          # 单节点该层容量上限
    bandwidth_gb_s: float       # 单向可用有效带宽
    latency_ns: float           # 首字节延迟

    def load_time_ms(self, size_gb: float) -> float:
        """把 size_gb 大小的 KV chunk 从本层拉到 GPU 需要多少毫秒（不含 GPU 内部拷贝）"""
        # 带宽项 + 延迟项，延迟项在大传输下几乎可忽略
        return size_gb / self.bandwidth_gb_s * 1000 + self.latency_ns / 1_000_000


DEFAULT_TIERS: List[Tier] = [
    Tier("L1_GPU_HBM",   capacity_gb=192,   bandwidth_gb_s=3350, latency_ns=100),      # B200 单卡 HBM3E 192GB
    Tier("L2_CPU_DRAM",  capacity_gb=2048,  bandwidth_gb_s=614,  latency_ns=100),      # 单 socket 12ch DDR5-6400
    Tier("L3_CXL_POOL",  capacity_gb=16384, bandwidth_gb_s=64,   latency_ns=350),      # CXL 3.x x16 池
    Tier("L4_NVMe_SSD",  capacity_gb=122880, bandwidth_gb_s=14,  latency_ns=100_000),  # Solidigm 122TB QLC
]


def place_kv_cache(total_gb: float, tiers: List[Tier] = None) -> Dict[str, float]:
    """按 L1→L4 顺序填装 KV cache，返回每层实际占用（GB）"""
    if tiers is None:
        tiers = DEFAULT_TIERS
    remain = float(total_gb)
    placement: Dict[str, float] = {}
    for t in tiers:
        take = min(remain, t.capacity_gb)
        placement[t.name] = round(take, 3)
        remain -= take
        if remain <= 0:
            break
    if remain > 0:
        placement["OVERFLOW"] = round(remain, 3)
    return placement


def estimate_load_latency(placement: Dict[str, float], tiers: List[Tier] = None) -> Dict[str, float]:
    """按分层结果算重新加载到 GPU 的总时延（毫秒）"""
    if tiers is None:
        tiers = DEFAULT_TIERS
    lookup = {t.name: t for t in tiers}
    breakdown: Dict[str, float] = {}
    total = 0.0
    for name, gb in placement.items():
        if name == "OVERFLOW" or gb <= 0:
            continue
        if name == "L1_GPU_HBM":
            # 已在 GPU，本地读，忽略搬运
            breakdown[name] = 0.0
            continue
        t = lookup[name]
        cost = t.load_time_ms(gb)
        breakdown[name] = round(cost, 3)
        total += cost
    breakdown["TOTAL_ms"] = round(total, 3)
    return breakdown


def recommend_strategy(model_params_b: float, ctx_tokens: int, batch: int,
                       kv_bytes_per_token: float = 2.5) -> Dict[str, object]:
    """按模型参数量、上下文长度、batch 反推 KV cache 大小并给策略建议

    kv_bytes_per_token 缺省 2.5KB，对应 Llama-70B BF16 单 token KV
    大模型（DeepSeek-V3 671B）此参数应上调至 8~10 KB
    """
    kv_total_gb = (kv_bytes_per_token * 1024 * ctx_tokens * batch) / (1024 ** 3)
    placement = place_kv_cache(kv_total_gb)
    latency = estimate_load_latency(placement)
    layers_used = [k for k, v in placement.items() if v > 0 and k != "OVERFLOW"]
    return {
        "kv_total_gb": round(kv_total_gb, 3),
        "placement": placement,
        "load_latency_ms": latency,
        "layers_used": layers_used,
        "overflow": placement.get("OVERFLOW", 0.0),
    }


if __name__ == "__main__":
    # 案例：671B MoE + 128K 上下文 + batch=32
    res = recommend_strategy(
        model_params_b=671, ctx_tokens=128_000, batch=32, kv_bytes_per_token=8.5
    )
    print("KV total (GB):", res["kv_total_gb"])
    print("Placement:", res["placement"])
    print("Load latency (ms):", res["load_latency_ms"])
