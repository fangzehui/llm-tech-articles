"""HBM 带宽 vs GPU 算力 —— arithmetic intensity 平衡点计算器

Roofline 模型：
  达峰 FLOPs = min(peak_flops, arithmetic_intensity * peak_bw)
  平衡点  I* = peak_flops / peak_bw    (FLOPs per Byte)

工作负载 arithmetic intensity < I* → memory-bound（带宽墙）
工作负载 arithmetic intensity > I* → compute-bound（算力墙）

参考硬件规格（截至 2026-07）：
- H100 SXM：BF16 989 TFLOPS，HBM3 3.35 TB/s → I* ≈ 295
  https://resources.nvidia.com/en-us-hopper-architecture/nvidia-h100-tensor-c
- B200：FP8 4500 TFLOPS，HBM3E 8.0 TB/s → I* ≈ 563
  https://www.nvidia.com/en-us/data-center/hgx/
- GB300 NVL72：单 GPU FP4 15 PFLOPS，HBM3E 8 TB/s → I* ≈ 1875
- Rubin R100 (HBM4 3.3 TB/s / stack × 8 = 26 TB/s 目标)：待正式发布
  https://news.samsungsemiconductor.com/kr/영상-인포그래픽으로-보는-hbm4/
"""
from dataclasses import dataclass
from typing import Literal


Precision = Literal["FP32", "TF32", "BF16", "FP16", "FP8", "FP4"]


@dataclass
class GpuSpec:
    name: str
    peak_flops_tflops: float   # 目标精度下峰值算力（TFLOPS）
    hbm_bandwidth_tb_s: float  # HBM 聚合带宽（TB/s）
    precision: Precision


def arithmetic_intensity_pivot(peak_flops_tflops: float, hbm_bandwidth_tb_s: float) -> float:
    """返回平衡点 I*（FLOPs / Byte）"""
    if hbm_bandwidth_tb_s <= 0:
        raise ValueError("hbm_bandwidth_tb_s must be > 0")
    # 单位换算：TFLOPS = 1e12 FLOPs/s，TB/s = 1e12 Bytes/s
    return peak_flops_tflops / hbm_bandwidth_tb_s


def classify_workload(workload_intensity: float, pivot: float) -> str:
    if workload_intensity < pivot * 0.9:
        return "memory_bound"
    if workload_intensity > pivot * 1.1:
        return "compute_bound"
    return "balanced"


def effective_throughput_tflops(spec: GpuSpec, workload_intensity: float) -> float:
    """给定 workload 的 arithmetic intensity，返回实际可达 TFLOPS"""
    bw_limited = workload_intensity * spec.hbm_bandwidth_tb_s
    return min(spec.peak_flops_tflops, bw_limited)


PRESET_GPUS = {
    "H100_SXM_BF16": GpuSpec("H100 SXM", 989,   3.35, "BF16"),
    "H200_SXM_BF16": GpuSpec("H200 SXM", 989,   4.8,  "BF16"),   # HBM3E 141GB
    "B200_FP8":      GpuSpec("B200",     4500,  8.0,  "FP8"),
    "GB300_FP4":     GpuSpec("GB300",   15000,  8.0,  "FP4"),
    "MI350X_FP8":    GpuSpec("MI350X",   9200,  8.0,  "FP8"),    # AMD Instinct MI350
}


def report(spec: GpuSpec, workload_intensity: float) -> dict:
    pivot = arithmetic_intensity_pivot(spec.peak_flops_tflops, spec.hbm_bandwidth_tb_s)
    eff = effective_throughput_tflops(spec, workload_intensity)
    return {
        "gpu": spec.name,
        "precision": spec.precision,
        "pivot_flops_per_byte": round(pivot, 2),
        "workload_intensity": workload_intensity,
        "regime": classify_workload(workload_intensity, pivot),
        "effective_tflops": round(eff, 2),
        "utilization_pct": round(eff / spec.peak_flops_tflops * 100, 2),
    }


if __name__ == "__main__":
    # 典型 LLM decode 阶段 arithmetic intensity ≈ 1（每 byte 读回只做 1 次乘加）
    # prefill 阶段可达数百
    for name, spec in PRESET_GPUS.items():
        for wi in (1, 50, 300, 1000):
            r = report(spec, wi)
            print(f"[{name}] wi={wi}: pivot={r['pivot_flops_per_byte']}, "
                  f"regime={r['regime']}, util={r['utilization_pct']}%")
