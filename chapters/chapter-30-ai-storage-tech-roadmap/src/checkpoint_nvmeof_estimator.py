"""分布式训练 checkpoint 通过 NVMe-oF 落盘的吞吐 / 落盘时间估算器

模型：
  checkpoint_size = params * (weight_bytes + optimizer_state_bytes + grad_bytes)
  落盘时间 = checkpoint_size / effective_write_bandwidth

优化器状态：
  Adam / AdamW 通常需 2 份 FP32 状态（m, v），即 8 bytes per param（不算主权重）
  ZeRO-3 全 shard 分布式落盘可把每卡负担除以世界规模

参考：
- Meta SIGCOMM 2024 RoCE：single-cluster 24K+ GPUs，400G RDMA
  https://cs.stanford.edu/~keithw/sigcomm2024/sigcomm24-final246-acmpaginated.pdf
- NVIDIA DGX SuperPOD B300：storage fabric 400G NDR，NVMe-oF over IB
  https://docs.nvidia.com/dgx-superpod/reference-architecture/scalable-infrastructure-b300-xdr/latest/storage-architecture.html
- DDN AI400X2 参考架构：InfiniBand 400G NDR，ConnectX-7
  https://lenovopress.lenovo.com/lp2021.pdf
"""
from dataclasses import dataclass
from typing import Literal


Precision = Literal["FP32", "BF16", "FP16", "FP8"]

PRECISION_BYTES = {"FP32": 4, "BF16": 2, "FP16": 2, "FP8": 1}


@dataclass
class CheckpointPlan:
    model_name: str
    params_b: float          # 模型参数量（Billions）
    weight_precision: Precision
    include_optimizer: bool = True
    include_gradients: bool = False   # 训练中一般不会 checkpoint 梯度
    world_size: int = 1               # ZeRO-3 shard 数（1=不 shard）


def checkpoint_size_gb(plan: CheckpointPlan) -> float:
    """按计划返回单次全局 checkpoint 总大小（GB）"""
    w_bytes = PRECISION_BYTES[plan.weight_precision]
    per_param = w_bytes
    if plan.include_optimizer:
        # Adam m + v，各存 FP32（8 bytes）
        per_param += 8
    if plan.include_gradients:
        per_param += w_bytes
    total_bytes = plan.params_b * 1e9 * per_param
    return round(total_bytes / (1024 ** 3), 2)


def per_rank_size_gb(plan: CheckpointPlan) -> float:
    """ZeRO-3 shard 后每张卡实际落盘的大小"""
    return round(checkpoint_size_gb(plan) / max(plan.world_size, 1), 3)


def dump_time_seconds(plan: CheckpointPlan,
                      write_bandwidth_gb_s: float,
                      effective_pct: float = 0.7) -> float:
    """给定聚合写带宽（GB/s）和实测利用率，返回落盘秒数"""
    size = checkpoint_size_gb(plan)
    eff_bw = write_bandwidth_gb_s * effective_pct
    return round(size / eff_bw, 2)


def max_checkpoints_per_day(plan: CheckpointPlan,
                            write_bandwidth_gb_s: float,
                            checkpoint_overhead_pct_max: float = 5.0) -> int:
    """要求 checkpoint I/O 不超过训练总时间的 checkpoint_overhead_pct_max，反推每天上限"""
    dump_s = dump_time_seconds(plan, write_bandwidth_gb_s)
    budget_s = 86400 * (checkpoint_overhead_pct_max / 100.0)
    return int(budget_s // dump_s) if dump_s > 0 else 0


# 典型网络带宽（GB/s，双向单向近似）
NETWORK_BW_GB_S = {
    "IB_HDR_200G_x1":  25,      # 200 Gb/s ≈ 25 GB/s
    "IB_NDR_400G_x1":  50,      # 400 Gb/s ≈ 50 GB/s
    "IB_XDR_800G_x1":  100,     # 800 Gb/s ≈ 100 GB/s
    "IB_NDR_400G_x8":  400,     # 单节点 8 端口 400G
    "IB_XDR_800G_x8":  800,     # 单节点 8 端口 800G
}


if __name__ == "__main__":
    plans = [
        CheckpointPlan("Llama-3.1-70B",    70,  "BF16", world_size=64),
        CheckpointPlan("DeepSeek-V3-671B", 671, "BF16", world_size=256),
        CheckpointPlan("Kimi-K2-1T",      1000, "BF16", world_size=512),
    ]
    for p in plans:
        for label, bw in NETWORK_BW_GB_S.items():
            t = dump_time_seconds(p, bw)
            n = max_checkpoints_per_day(p, bw)
            print(f"{p.model_name} | {label:16s} | size={checkpoint_size_gb(p)}GB | "
                  f"dump={t}s | day_max={n}")
