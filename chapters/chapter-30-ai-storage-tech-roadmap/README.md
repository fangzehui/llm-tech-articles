# chapter-30-ai-storage-tech-roadmap

《AI 存储技术方向硬核解析》配套源码。承接第 29 篇市场侧分析，本篇聚焦"技术怎么支撑这个变"：HBM3E/HBM4、CXL 内存池化、QLC 大容量 SSD、存算一体 PIM/CIM、KV-Cache 卸载、RDMA/NVMe-oF 六条主线。

## 目录结构

```
chapter-30-ai-storage-tech-roadmap/
├── README.md
├── requirements.txt
├── src/
│   ├── kv_cache_tiered_offload.py     # KV-Cache 四级卸载策略（HBM/DRAM/CXL/SSD）
│   ├── hbm_arithmetic_intensity.py    # HBM 带宽 vs 算力 Roofline 平衡点
│   └── checkpoint_nvmeof_estimator.py # NVMe-oF checkpoint 落盘时间估算
└── tests/
    └── test_all.py                    # 三段代码全 pytest 覆盖
```

## 快速跑通

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## 3 段代码一句话摘要

1. **kv_cache_tiered_offload**：给定 KV cache 总量，按 L1 GPU HBM → L2 CPU DRAM → L3 CXL 池 → L4 NVMe SSD 顺序装填，估算每层重加载延迟。
2. **hbm_arithmetic_intensity**：Roofline 模型给出 H100 / H200 / B200 / GB300 / MI350X 的算力-带宽平衡点，判定 workload 是 memory-bound 还是 compute-bound。
3. **checkpoint_nvmeof_estimator**：按参数量、精度、优化器、ZeRO-3 shard 数、网络带宽算 checkpoint 单次落盘时间与一天最多能存几次。

数据源见每个源文件顶部 docstring。
