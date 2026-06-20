# chapters/ — 技术文章配套源码索引

本目录收录仓库技术文章的可运行 demo 代码，每个 chapter 子目录都包含：

- `README.md`：一句话简介 + 文件清单 + 快速开始
- 至少 1 个核心 `.py` 文件：从文章中提炼的最小可跑工程示例
- `requirements.txt`：仅列出该 demo 实际用到的依赖
- 部分章节附带 `*.yml` / `*.json` 配置文件或 `test_smoke.py`

> **定位说明**：每个 demo 都是「概念可跑示例」，目的是让读者把文章里的关键工程思想跑起来、改起来。**生产级路由器 / 配置管理实战请看仓库根目录的 `routes/glm-5.2-tri-channel/`**。

## 章节索引

| # | 章节目录 | 配套文章 | 一句话简介 |
|---|---------|---------|-----------|
| 01 | [chapter-01-multi-model-router](chapter-01-multi-model-router/) | [01-LLM多模型路由架构设计.md](../01-LLM多模型路由架构设计.md) | 三 mock provider + 故障切换 + 三种路由策略 |
| 02 | [chapter-02-token-cost](chapter-02-token-cost/) | [02-Token成本优化实战.md](../02-Token成本优化实战.md) | tiktoken 计数 + 多模型成本汇总 |
| 03 | [chapter-03-unified-adapter](chapter-03-unified-adapter/) | [03-大模型API统一适配层设计.md](../03-大模型API统一适配层设计.md) | Anthropic / Gemini ↔ OpenAI 协议双向适配 |
| 04 | [chapter-04-ha-pattern](chapter-04-ha-pattern/) | [04-生产环境LLM高可用方案.md](../04-生产环境LLM高可用方案.md) | retry + circuit breaker + timeout 三件套 |
| 05 | [chapter-05-benchmark](chapter-05-benchmark/) | [05-2026主流大模型API横评.md](../05-2026主流大模型API横评.md) | prompt 集合 × 多模型并跑 + P50/P95 聚合 |
| 06 | [chapter-06-domestic-benchmark](chapter-06-domestic-benchmark/) | [06-国产大模型横评2026年中.md](../06-国产大模型横评2026年中.md) | 6 家国产模型 OpenAI 兼容 client 注册表 |
| 07 | [chapter-07-pricing-calculator](chapter-07-pricing-calculator/) | [07-大模型API价格全景图2026.6.md](../07-大模型API价格全景图2026.6.md) | 12 款模型月度账单估算 + 性价比排序 |
| 08 | [chapter-08-quota-manager](chapter-08-quota-manager/) | [08-企业级LLM-Token成本治理架构.md](../08-企业级LLM-Token成本治理架构.md) | InMemoryRedis + 两段式 token 配额 |
| 09 | [chapter-09-tier-router](chapter-09-tier-router/) | [09-分级路由策略实战.md](../09-分级路由策略实战.md) | small/mid/flagship 三档 + YAML 配置驱动 |
| 10 | [chapter-10-semantic-cache](chapter-10-semantic-cache/) | [10-语义缓存命中率工程实战.md](../10-语义缓存命中率工程实战.md) | embedding + 余弦相似度 + LRU + TTL |
| 11 | [chapter-11-agent-token-saving](chapter-11-agent-token-saving/) | [11-Agent_Token降75%_4条工程路径.md](../11-Agent_Token降75%_4条工程路径.md) | Agent 4 条降本路径示意（裁剪/压缩/分级/缓存） |
| 12 | [chapter-12-checkpoint-recovery](chapter-12-checkpoint-recovery/) | [12-长程Agent容错_Checkpoint与Durable_Execution.md](../12-长程Agent容错_Checkpoint与Durable_Execution.md) | Checkpoint 保存 + 断点续跑 + 4 个 smoke test |
| 14 | [chapter-14-flagship-decision-scorer](chapter-14-flagship-decision-scorer/) | [14-2026.6_旗舰大模型四强横评.md](../14-2026.6_旗舰大模型四强横评.md) | 4 款旗舰画像 + 6 维加权打分 + 三场景推荐 + 7 个 smoke test |
| 15 | [chapter-15-self-host-engines](chapter-15-self-host-engines/) | [15-vLLM_SGLang_TensorRT-LLM_三引擎自部署横评.md](../15-vLLM_SGLang_TensorRT-LLM_三引擎自部署横评.md) | vLLM / SGLang / TRT-LLM 三套 K8s Deployment YAML + 压测脚本 + bash smoke test |

> 第 13 篇配套放在仓库根目录的 [`routes/glm-5.2-tri-channel/`](../routes/glm-5.2-tri-channel/) 下（生产级 FastAPI 路由器，不在本目录）.

## 公共模块

`_common/` 提供一个不依赖网络的 mock LLM 客户端 `MockLLMClient`，多个 demo 共用它演示路由、降级、缓存等逻辑。各 demo 仍可独立运行。

## 一键 import 自检

```bash
bash run_all_smoke.sh
```

脚本会循环跑 12 个章节的核心模块的 `python -c "import ..."`，并汇总 PASS/FAIL 计数。

## 数据声明

涉及价格、性能、调用量数字均为**示意数据**，实际请以厂商最新官方公告与你自己的实测为准。
