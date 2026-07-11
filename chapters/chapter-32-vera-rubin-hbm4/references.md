# References — chapter-32-vera-rubin-hbm4

本篇所有硬数据信源清单。按主题分类，每条含标题 + URL + 发布时间。

---

## 一、NVIDIA 官方（一手）

1. **《NVIDIA Vera Rubin Ramps Into Full Production to Power Agentic AI Factories Worldwide》** — NVIDIA 官方 Newsroom  
   URL: https://nvidianews.nvidia.com/news/vera-rubin-full-production-agentic-ai-factory  
   发布时间: 2026-05-31  
   要点: Vera Rubin 全面量产、10× agent throughput vs Grace Blackwell、CoreWeave/Lambda/Oracle 首批部署、Spectrum-X Ethernet Photonics 800G CPO。

2. **《GTC Taipei 2026 Keynote with Jensen Huang》** — NVIDIA 官方录像  
   URL: https://www.nvidia.com/en-us/on-demand/session/gtctaipei26-stw61044/  
   发布时间: 2026-06 GTC Taipei  
   要点: 六款自研芯片、Rubin Compute Board 6T 晶体管 / 18000+ 元件、MGX 第三代机架 130 万个零件、5000A 液冷母排。

3. **《Inside the NVIDIA Vera Rubin Platform: Six New Chips, One AI Supercomputer》** — NVIDIA Developer Blog  
   URL: https://developer.nvidia.com/blog/inside-the-NVIDIA-rubin-platform-six-new-chips-one-ai-supercomputer/  
   发布时间: 2026-01-05  
   要点: Rubin 3360 亿晶体管、双 die 组包、NVFP4 推理 50 PFLOPS、NVFP4 训练 35 PFLOPS Dense、288 GB HBM4 单卡 / 22 TB/s、NVLink 6 3.6 TB/s、NVLink-C2C 1.8 TB/s。

4. **《Reducing High-Bandwidth Memory Bottlenecks in JAX-Based LLM Training with Host Offloading》** — NVIDIA Developer Blog  
   URL: https://developer.nvidia.com/blog/reducing-high-bandwidth-memory-bottlenecks-in-jax-based-llm-training-with-host-offloading/  
   发布时间: 2026-07-10  
   要点: NVLink-C2C 900 GB/s → 1.8 TB/s；DeepSeek-V3 671B / Llama 3.1 405B 在 GB200 NVL72 上 host offloading 相比 activation rematerialization 提升 57% 吞吐；MoE 稀疏大模型收益最大。

5. **《NVIDIA Vera Rubin NVL72 产品页》**  
   URL: https://www.nvidia.com/en-eu/data-center/vera-rubin-nvl72/  
   发布时间: 官方产品页（持续更新）  
   要点: NVL72 完整 spec：20.7 TB HBM4 / 1580 TB/s、260 TB/s NVLink、3168 Olympus core、54 TB LPDDR5X、3.6 EF FP4 推理、1.2 EF FP8 训练。

6. **《NVIDIA Unveils Rubin CPX: A New Class of GPU Designed for Massive-Context Inference》** — NVIDIA 官方新闻稿  
   URL: https://nvidianews.nvidia.com/_gallery/download_pdf/68c044263d63320a35b99089/  
   发布时间: 2025-09 AI Infra Summit  
   要点: Vera Rubin NVL144 CPX 单机架 8 EF、100 TB fast memory、1.7 PB/s memory bandwidth；Rubin CPX 单卡 30 PFLOPS NVFP4 + 128 GB GDDR7。

---

## 二、HBM4 三家（一手厂商稿）

7. **《Samsung Ships Industry-First Commercial HBM4 With Ultimate Performance for AI Computing》** — Samsung Global Newsroom  
   URL: https://news.samsung.com/global/samsung-ships-industry-first-commercial-hbm4-with-ultimate-performance-for-ai-computing  
   发布时间: 2026-02-12  
   要点: 三星 HBM4 首家量产、11.7 Gbps 稳定 / 最高 13 Gbps、单栈 3.3 TB/s、12H 24-36GB / 16H 48GB、4nm base die + 1c DRAM、能效 +40%、热阻 -10%、散热 +30%。

8. **《SK 海力士完成 HBM4 开发并构建量产体系》** — SK hynix China Newsroom  
   URL: https://news.skhynix.com.cn/sk-hynix-completes-worlds-first-hbm4-development-and-readies-mass-production  
   发布时间: 2025-09-12  
   要点: SK 海力士全球首家完成 HBM4 开发、2048 I/O、带宽翻倍、能效 +40%、AI 服务性能最高 +69%、10 Gb/s 运行、MR-MUF + 1b DRAM。

9. **《美光专为 NVIDIA Vera Rubin 打造的 HBM4 进入大规模量产》** — Micron IR  
   URL: https://micron.gcs-web.com/news-releases/news-release-details/meiguangzhuanwei-nvidia-vera-rubin-dazaode-hbm4  
   发布时间: 2026-03-17  
   要点: 12H 36 GB HBM4 量产、pin >11 Gb/s、单栈 >2.8 TB/s、比 HBM3E 提升 2.3×、能效 +20%；同步 PCIe 6.0 SSD（读 28 GB/s、随机 550 万 IOPS）和 192GB SOCAMM2 量产。

10. **《SK 海力士 HBM4 产品页》**  
    URL: https://product.skhynix.com/products/dram/hbm/hbm4.go  
    发布时间: 官方产品页  
    要点: 2K I/O 架构、单栈 >2.8 TB/s、能效 +40%、Advanced MR-MUF 16H 堆叠。

11. **《SK 하이닉스, CES 2026에서 차세대 AI 메모리 혁신 선보인다》** — SK hynix Newsroom  
    URL: https://news.skhynix.co.kr/ces2026/  
    发布时间: 2026-01-06  
    要点: CES 2026 首度公开 HBM4 16 层 48 GB 样品；HBM3E 12H 36 GB 同展；MR-MUF 关键封装。

---

## 三、Vera Rubin GPU / Rubin Ultra（二手权威）

12. **《Nvidia Vera Rubin HBM4: Jensen Huang Confirms All Three Suppliers in Production for Q3 Ship》** — c114pro 引 Reuters/Bloomberg  
    URL: https://www.c114pro.com/chip/169789.html  
    发布时间: 2026-06-06  
    要点: 6-5 首尔机场三家 HBM4 认证；SK 60-70% / 三星 25-30% / 美光其余；HBM4 12-Hi 单 die 50μm 厚度、16-Hi 目标 30μm、封装总高 720μm 上限；每 Rubin GPU 8 HBM4 stack、NVL72 共 576 stack。

13. **《NVIDIA Rubin Ultra Four-Die GPU Cancelled》** — c114pro 引 SemiAnalysis  
    URL: https://www.c114pro.com/chip/175293.html  
    发布时间: 2026-07-01  
    要点: SemiAnalysis 6-30 报道 4-die Rubin Ultra 取消；改回 2-die + 8 HBM4E stack；384 GB HBM4E / GPU；HBM4E 16 Gb/s pin / 4.1 TB/s stack；CoWoS-L 是瓶颈、CoPoS 2028-2029 才量产。

14. **《SK Hynix Fires Back In The AI Memory Race With Next Gen 48GB HBM4E》** — HotHardware  
    URL: https://hothardware.com/news/sk-hynix-sampling-hbm4e-16gbps-4tb-second  
    发布时间: 2026-06-20  
    要点: SK 海力士 12H HBM4E 样品交付、48 GB/stack、16 Gbps/pin、>4 TB/s/stack、能效 +20%、MR-MUF 让热阻 -17%。

15. **《SK 海力士展示 16 层堆叠 HBM4》** — 腾讯云开发者社区 / Tom's Hardware  
    URL: https://developer.cloud.tencent.com/article/2641123  
    发布时间: 2026-03-19  
    要点: 16H HBM4 2048-bit 接口、10 GT/s 运行、比 JEDEC 高 25%；封装尺寸 10.5×12mm；16H 堆叠高度 950μm、12H HBM3 约 750μm。

16. **《英伟达 CEO 黄仁勋发布 Vera Rubin 超级芯片：性能提升超 3 倍，HBM4 显存登场》** — IT 之家  
    URL: https://m.ithome.com/html/893102.htm  
    发布时间: 2025-10-29  
    要点: Vera Rubin NVL144 平台 3.6 EF FP4 推理 / 1.2 EF FP8 训练、13 TB/s HBM4 内存 / 75 TB fast memory、比 GB300 NVL72 提升 3.3×、NVLink 260 TB/s、CX9 28.8 TB/s；Rubin Ultra NVL576 原 15 EF / 5 EF / HBM4E 4.6 PB/s（后调整）。

17. **《NVIDIA Rubin R100 GPU Chip Specs: Architecture, VRAM, and Cloud Availability (2026)》** — Spheron Network  
    URL: https://www.spheron.network/blog/nvidia-rubin-r100-guide/  
    发布时间: 2026-05-15  
    要点: R100/H300 完整 spec：288 GB HBM4 / 22 TB/s / 50 PFLOPS FP4 / 336B 晶体管 / TSMC N3 / NVLink 6 3.6 TB/s / TDP ~2300W / ConnectX-9 1.6T。

18. **《Samsung HBM4 Passes $1 Billion in Four Months as Its 4nm Bet Starts to Pay Off》** — c114pro 引 TechTimes  
    URL: https://www.c114pro.com/chip/173690.html  
    发布时间: 2026-06-24  
    要点: 三星 HBM4 首 4 个月营收破 10 亿美元；Q1 HBM 市场份额 SK 58% / 三星 21% / 美光 21%（Counterpoint）；HBM 市场 2026 年预计 $546 亿（+58%）；三星 2026 年 HBM 营收翻 3 倍。

---

## 四、Rubin Ultra 与 BOM（二手财务）

19. **《Los servidores NVIDIA Rubin Ultra se disparan: hasta 21 millones de dólares por rack》** — fanaticosdelhardware 引 BofA Global Research  
    URL: https://fanaticosdelhardware.com/los-servidores-nvidia-rubin-ultra-se-disparan-hasta-21-millones-de-dolares-por-rack-y-15-millones-solo-en-hbm4e/  
    发布时间: 2026-07-09  
    要点: Rubin Oberon 单机架 HBM 约 $382k（vs Blackwell $156k）；HBM 占 BOM 6.4% vs 5.2%；单机架 BOM 从 ~$3M 涨到 ~$6M；Rubin Ultra V300 Kyber NVL144 单 GPU 576 GB HBM4E。

20. **《Nvidia Reportedly Drops Quad-Die Rubin Ultra for a Dual-GPU Design》** — topcpu.net 引 SemiAnalysis  
    URL: https://www.topcpu.net/en/news/nvidia-reportedly-cancels-quad-die-rubin-ultra-for-dual-gpu-design  
    发布时间: 2026-06-30  
    要点: 4-die Rubin Ultra 取消；改 2-die + HBM4E；Kyber 液冷机架单 domain ≥ 144 GPU；HBM4E vs HBM4 保留优势。

21. **《SK 海力士 16 层 HBM4，速度上看 10GT/s、2048-bit 架构成形》** — TechNews  
    URL: https://technews.tw/2026/01/15/sk-16-hi-10gts/  
    发布时间: 2026-01-15  
    要点: CES 2026 首度公开 16 层 HBM4；MR-MUF 关键封装工艺；16H 堆叠高度 950μm；封装 10.5×12mm。

---

## 五、副线信源

22. **《C2CServe: Leveraging NVLink-C2C for Elastic Serverless LLM Serving on MIG》** — arXiv  
    URL: https://arxiv.org/pdf/2605.19481  
    发布时间: 2026  
    要点: NVLink-C2C 单向 450 GB/s、比 PCIe 5.0 x16 单向 64 GB/s 高 7×；host memory 可作为 GPU HBM 的活性扩展而非 backing tier。

23. **《SK 海力士量产 HBM4！》** — 电子工程专辑  
    URL: https://www.eet-china.com/mp/a438449.html  
    发布时间: 2025-09-16  
    要点: HBM4 12 层 2 TB/s / 单栈；2048 I/O 比 HBM3E 快 60%；能效 +40%、AI 性能 +69%；MR-MUF + 1bnm DRAM。

---

**信源合计：23 条**（一手厂商稿 11 条、NVIDIA 官方 6 条、二手权威 6 条）。所有数据交叉核对至少 2 个独立信源；矛盾点以 NVIDIA 官方数据为准。
