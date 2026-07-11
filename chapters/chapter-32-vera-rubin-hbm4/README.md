# chapter-32-vera-rubin-hbm4

**篇名：** 英伟达 Vera Rubin HBM4 三家齐过：2048-bit 总线 × 288GB/stack × 50 PFLOPS 世代切换拆解

**CSDN 链接：** 待发布后回填…

**发布时间：** 2026-07-12

**主线：** NVIDIA Vera Rubin 平台 2026-06-01 GTC Taipei keynote 全面量产，同一周三星 / SK 海力士 / 美光三家 HBM4 全部通过 NVIDIA 认证。围绕"2048-bit 总线翻倍 × 288GB HBM4 显存 × 50 PFLOPS NVFP4 算力"这三个核心数字，拆到芯片、封装、互联、Rubin Ultra 2027 路线、Host Offloading 副线，全部标注一手信源。

---

## 核心数据速查表

### Vera Rubin GPU 主参数

| 项 | Rubin | Blackwell B200 | 倍数 |
|---|---|---|---|
| 晶体管 | 336B | 208B | 1.62× |
| 制程 | TSMC N3 | TSMC N4P | — |
| NVFP4 推理 (PFLOPS) | 50 | 10 | 5× |
| NVFP4 训练 (PFLOPS) | 35 (dense) | 10 | 3.5× |
| HBM 容量 (GB/GPU) | 288 (HBM4) | 192 (HBM3E) | 1.5× |
| HBM 带宽 (TB/s) | 22 | 8 | 2.75× |
| NVLink 带宽 (TB/s) | 3.6 (NVLink 6) | 1.8 (NVLink 5) | 2× |
| NVLink-C2C (TB/s) | 1.8 | 0.9 | 2× |
| TDP (W) | ~2300 | 1400 | 1.64× |

### HBM4 vs HBM3E

| 项 | HBM4 | HBM3E | Delta |
|---|---|---|---|
| I/O 位宽 | 2048 bit | 1024 bit | 翻倍 |
| 独立数据通道 | 32 | 16 | 翻倍 |
| pin 速度 (JEDEC baseline) | 8 Gb/s | 8 Gb/s | — |
| pin 速度 (实产最高) | 13 Gbps (三星) | 9.6 Gbps | 1.35× |
| 单栈带宽 (最高) | 3.3 TB/s (三星) | 1.2 TB/s | 2.75× |
| 单栈容量 (12H) | 36 GB | 24 GB | 1.5× |
| 单栈容量 (16H) | 48 GB | 36 GB | 1.33× |
| 能效 (vs HBM3E) | +40% (SK/三星) / +20% (美光) | baseline | — |

### 三家 HBM4 分配比例（Vera Rubin）

| 厂商 | 分配份额 | 量产时间 | 关键工艺 |
|---|---|---|---|
| SK 海力士 | 60-70% | 2025-09 首完开发 | MR-MUF + 1b DRAM |
| 三星 | 25-30% | 2026-02-12 首家量产 | 4nm base die + 1c DRAM |
| 美光 | 剩余 | 2026-03-17 GTC 2026 量产 | 1β DRAM + 12H |

### Vera Rubin NVL72 机架

| 项 | 值 |
|---|---|
| GPU 数量 | 72 |
| HBM4 总容量 | 20.7 TB |
| 聚合 HBM 带宽 | 1580 TB/s |
| NVLink 聚合带宽 | 260 TB/s |
| Vera Olympus core 数 | 3168 |
| LPDDR5X CPU 内存 | 54 TB |
| NVFP4 推理 | 3.6 Exaflops |
| FP8 训练 | 1.2 Exaflops |
| 相比 GB300 NVL72 | 3.3× 提升 |
| 相比 Grace Blackwell（agent throughput）| 10× |

---

## 章节关系

- **上游资本侧姊妹篇：** [chapter-31-sk-hynix-ipo](../chapter-31-sk-hynix-ipo/)（SK 海力士 IPO 与 HBM 溢价 50% 定价机制）
- **技术全景背景：** [chapter-30-ai-storage-tech-roadmap](../chapter-30-ai-storage-tech-roadmap/)（AI 存储六大主线全景，HBM4/CXL/QLC/KV cache 四级卸载）
- **市场结构背景：** [chapter-29-llm-storage-market-2024-2026](../chapter-29-llm-storage-market-2024-2026/)（存储市场复盘 2024-2026，HBM 涨价三年翻四倍）
- **模型侧对应：** [chapter-28-deepseek-v32-half-year](../chapter-28-deepseek-v32-half-year/)（V3.2 稀疏注意力如何降低 KV-Cache 存储压力）

---

## 目录结构

```
chapter-32-vera-rubin-hbm4/
├── README.md                              # 本文
├── references.md                          # 参考来源清单（≥ 10 条，全 URL + 发布时间）
└── data-visualization/
    ├── hbm_generation_compare.py          # HBM3E → HBM4 世代对比柱状图
    ├── hbm_generation_compare.png         # 生成图（300 DPI）
    ├── rubin_vs_blackwell_radar.py        # Rubin vs Blackwell 参数雷达图
    └── rubin_vs_blackwell_radar.png       # 生成图（300 DPI）
```

---

## 使用

```bash
cd data-visualization/
pip install matplotlib numpy
python3 hbm_generation_compare.py
python3 rubin_vs_blackwell_radar.py
```

生成的 PNG 已同步入库，可直接查看。

---

## 数据截止日

2026-07-12
