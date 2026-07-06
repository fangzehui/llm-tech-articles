"""chapter-30 pytest 全套：KV-Cache 四级卸载 / HBM Roofline / NVMe-oF checkpoint"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kv_cache_tiered_offload import (
    Tier, place_kv_cache, estimate_load_latency, recommend_strategy, DEFAULT_TIERS,
)
from hbm_arithmetic_intensity import (
    GpuSpec, arithmetic_intensity_pivot, classify_workload,
    effective_throughput_tflops, report, PRESET_GPUS,
)
from checkpoint_nvmeof_estimator import (
    CheckpointPlan, checkpoint_size_gb, per_rank_size_gb,
    dump_time_seconds, max_checkpoints_per_day, NETWORK_BW_GB_S,
)


# ============== 1. KV-Cache 四级卸载 ==============

class TestKVCacheOffload:
    def test_placement_fits_in_l1(self):
        p = place_kv_cache(50)  # 50 GB 全放 GPU HBM
        assert p["L1_GPU_HBM"] == 50
        assert "L2_CPU_DRAM" not in p or p.get("L2_CPU_DRAM", 0) == 0

    def test_placement_overflow_to_dram(self):
        p = place_kv_cache(500)  # L1=192 GB，剩下 308 GB 进 DRAM
        assert p["L1_GPU_HBM"] == 192
        assert p["L2_CPU_DRAM"] == 308

    def test_placement_uses_all_tiers(self):
        # 20 TB 大 KV cache（假想极端长上下文）
        p = place_kv_cache(20_000)
        assert p["L1_GPU_HBM"] == 192
        assert p["L2_CPU_DRAM"] == 2048
        assert p["L3_CXL_POOL"] == 16384
        assert p["L4_NVMe_SSD"] > 0

    def test_overflow_beyond_all_tiers(self):
        p = place_kv_cache(500_000)  # 超过全部四级
        assert p.get("OVERFLOW", 0) > 0

    def test_load_latency_dram_gt_hbm(self):
        p = {"L1_GPU_HBM": 100, "L2_CPU_DRAM": 100}
        lat = estimate_load_latency(p)
        assert lat["L1_GPU_HBM"] == 0
        assert lat["L2_CPU_DRAM"] > 0
        assert lat["TOTAL_ms"] > 0

    def test_load_latency_ordered(self):
        p = {
            "L1_GPU_HBM": 10, "L2_CPU_DRAM": 10,
            "L3_CXL_POOL": 10, "L4_NVMe_SSD": 10,
        }
        lat = estimate_load_latency(p)
        assert lat["L2_CPU_DRAM"] < lat["L3_CXL_POOL"] < lat["L4_NVMe_SSD"]

    def test_recommend_strategy_small_model(self):
        r = recommend_strategy(model_params_b=7, ctx_tokens=8_000, batch=1,
                                kv_bytes_per_token=0.5)
        assert r["kv_total_gb"] > 0
        assert "L1_GPU_HBM" in r["layers_used"]
        assert r["overflow"] == 0

    def test_recommend_strategy_big_model_spills(self):
        r = recommend_strategy(model_params_b=671, ctx_tokens=200_000,
                                batch=256, kv_bytes_per_token=10)
        assert r["kv_total_gb"] > 192
        assert len(r["layers_used"]) >= 2


# ============== 2. HBM Arithmetic Intensity Roofline ==============

class TestHBMRoofline:
    def test_h100_pivot(self):
        spec = PRESET_GPUS["H100_SXM_BF16"]
        pivot = arithmetic_intensity_pivot(spec.peak_flops_tflops, spec.hbm_bandwidth_tb_s)
        # 989 / 3.35 ≈ 295
        assert 290 < pivot < 300

    def test_b200_pivot(self):
        spec = PRESET_GPUS["B200_FP8"]
        pivot = arithmetic_intensity_pivot(spec.peak_flops_tflops, spec.hbm_bandwidth_tb_s)
        # 4500 / 8.0 ≈ 562.5
        assert 550 < pivot < 575

    def test_gb300_pivot(self):
        spec = PRESET_GPUS["GB300_FP4"]
        pivot = arithmetic_intensity_pivot(spec.peak_flops_tflops, spec.hbm_bandwidth_tb_s)
        # 15000 / 8 = 1875
        assert 1800 < pivot < 1900

    def test_zero_bandwidth_raises(self):
        with pytest.raises(ValueError):
            arithmetic_intensity_pivot(1000, 0)

    def test_workload_memory_bound(self):
        # decode 阶段 wi=1 远远小于 H100 pivot 295
        assert classify_workload(1, 295) == "memory_bound"

    def test_workload_compute_bound(self):
        # prefill 阶段大 batch，wi=1000
        assert classify_workload(1000, 295) == "compute_bound"

    def test_effective_throughput_capped(self):
        spec = PRESET_GPUS["H100_SXM_BF16"]
        # wi 极大，被峰值算力封顶
        eff = effective_throughput_tflops(spec, 100_000)
        assert eff == pytest.approx(spec.peak_flops_tflops)

    def test_effective_throughput_bw_limited(self):
        spec = PRESET_GPUS["H100_SXM_BF16"]
        eff = effective_throughput_tflops(spec, 1)  # decode
        assert eff < spec.peak_flops_tflops * 0.1

    def test_report_structure(self):
        spec = PRESET_GPUS["H200_SXM_BF16"]
        r = report(spec, 100)
        assert set(r.keys()) >= {
            "gpu", "pivot_flops_per_byte", "regime", "effective_tflops", "utilization_pct"
        }


# ============== 3. NVMe-oF checkpoint 估算 ==============

class TestCheckpointEstimator:
    def test_llama_70b_bf16_size(self):
        p = CheckpointPlan("Llama-70B", 70, "BF16", include_optimizer=True)
        # 70e9 * (2 + 8) = 700 GB
        size = checkpoint_size_gb(p)
        assert 640 < size < 720

    def test_no_optimizer_smaller(self):
        p1 = CheckpointPlan("m", 100, "BF16", include_optimizer=True)
        p2 = CheckpointPlan("m", 100, "BF16", include_optimizer=False)
        assert checkpoint_size_gb(p1) > checkpoint_size_gb(p2)

    def test_zero3_shards_by_world_size(self):
        p = CheckpointPlan("m", 100, "BF16", world_size=100)
        total = checkpoint_size_gb(p)
        per_rank = per_rank_size_gb(p)
        assert per_rank == pytest.approx(total / 100, rel=1e-2)

    def test_dump_time_scales_with_bw(self):
        p = CheckpointPlan("m", 671, "BF16")
        t_slow = dump_time_seconds(p, NETWORK_BW_GB_S["IB_HDR_200G_x1"])
        t_fast = dump_time_seconds(p, NETWORK_BW_GB_S["IB_XDR_800G_x1"])
        # 800G 应约为 200G 的 1/4
        assert t_slow > t_fast * 3

    def test_effective_pct_applied(self):
        p = CheckpointPlan("m", 100, "BF16")
        t70 = dump_time_seconds(p, 100, effective_pct=0.7)
        t100 = dump_time_seconds(p, 100, effective_pct=1.0)
        assert t70 > t100

    def test_day_max_positive(self):
        p = CheckpointPlan("Llama-70B", 70, "BF16")
        n = max_checkpoints_per_day(p, NETWORK_BW_GB_S["IB_NDR_400G_x8"])
        assert n > 0

    def test_fp8_smaller_than_bf16(self):
        p_bf16 = CheckpointPlan("m", 100, "BF16", include_optimizer=False)
        p_fp8 = CheckpointPlan("m", 100, "FP8", include_optimizer=False)
        assert checkpoint_size_gb(p_fp8) < checkpoint_size_gb(p_bf16)

    def test_1t_model_super_size(self):
        p = CheckpointPlan("Kimi-K2-1T", 1000, "BF16", include_optimizer=True)
        # 1000e9 * 10 bytes ≈ 9.31 TB
        assert checkpoint_size_gb(p) > 9000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
