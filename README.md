# llm-tech-articles

半自动数字人社区配套技术文章库 —— 作者 **方泽辉**。

本仓库收录"LLM 工程化与运维"主题的系列长文，每一篇都尝试把生产环境踩过的坑、踩坑后形成的工程取舍、以及对应的可复用代码沉淀下来。文章首发于 CSDN，源文件以中文 Markdown 形式同步在这里，便于读者按需检索、对照代码、提交勘误。

---

## 文章索引

| # | 标题 | 一句话摘要 |
|---|------|-----------|
| 01 | [LLM 多模型路由架构设计](./01-LLM多模型路由架构设计.md) | 多模型场景下统一调度层的拓扑设计与抽象边界 |
| 02 | [Token 成本优化实战](./02-Token成本优化实战.md) | 从 prompt 重构到缓存命中率的成本压缩路径 |
| 03 | [大模型 API 统一适配层设计](./03-大模型API统一适配层设计.md) | OpenAI 兼容协议下多 provider 抽象的工程要点 |
| 04 | [生产环境 LLM 高可用方案](./04-生产环境LLM高可用方案.md) | 主备容灾、熔断、限流、降级的端到端实践 |
| 05 | [2026 主流大模型 API 横评](./05-2026主流大模型API横评.md) | 主流厂商 API 在延迟 / 价格 / 稳定性的实测对比 |
| 06 | [国产大模型横评 2026 年中](./06-国产大模型横评2026年中.md) | 国产模型在通用能力 / 长上下文 / 代码能力的横评 |
| 07 | [大模型 API 价格全景图 2026.6](./07-大模型API价格全景图2026.6.md) | 主流厂商定价矩阵与单位 token 成本测算方法 |
| 08 | [企业级 LLM Token 成本治理架构](./08-企业级LLM-Token成本治理架构.md) | 配额、预算、对账、归因的治理体系搭建 |
| 09 | [分级路由策略实战](./09-分级路由策略实战.md) | 4 个真实业务场景倒推出的路由表设计 |
| 10 | [语义缓存命中率工程实战](./10-语义缓存命中率工程实战.md) | 把语义缓存命中率从 30% 拉到 70% 的工程清单 |
| 11 | [Agent Token 降 75%：4 条工程路径](./11-Agent_Token降75%_4条工程路径.md) | 对标 DuMate Harness 的 4 条 Token 压缩路径拆解 |
| 12 | [长程 Agent 容错：Checkpoint 与 Durable Execution](./12-长程Agent容错_Checkpoint与Durable_Execution.md) | 长程 Agent 的状态持久化与可恢复执行设计 |
| 13 | [GLM-5.2 三通道实测：企业接入决策报告](./13-GLM-5.2_三通道实测_企业接入决策报告.md) | 智谱官方 / 国家超算互联网 / 自部署三通道选型与决策矩阵 |
| 14 | [2026.6 旗舰大模型四强横评](./14-2026.6_旗舰大模型四强横评.md) | GLM-5.2 / Claude Fable 5 / GPT-5 Preview / Gemini 3.0 中国企业接入决策矩阵 |
| 15 | [vLLM v0.23 vs SGLang vs TensorRT-LLM 三引擎自部署横评](./15-vLLM_SGLang_TensorRT-LLM_三引擎自部署横评.md) | 三大主流推理引擎在吞吐 / 延迟 / 成本 / Agent 适配上的横评 |

> 已同步首发于 CSDN（账号 LDZKKJ）；后续如发现事实性偏差会以各文附录 C 形式追加修订。

---

## 配套源码

文章中出现的"可跑代码 / 配置模板"按定位分两层放置：

### 历史文章配套（`chapters/`）

每个 `chapter-XX-<keyword>/` 子目录对位一篇文章，提供从文章里提炼的**最小可跑 demo**，让读者把关键工程思想跑起来、改起来。
完整章节索引、依赖说明、一键 smoke 测试见 [`chapters/README.md`](./chapters/README.md)。

| 章节 | 关键词 |
|------|--------|
| [01](./chapters/chapter-01-multi-model-router/) | 多模型路由 + 故障切换 |
| [02](./chapters/chapter-02-token-cost/) | tiktoken 计数 + 成本汇总 |
| [03](./chapters/chapter-03-unified-adapter/) | 多协议双向适配 |
| [04](./chapters/chapter-04-ha-pattern/) | retry + circuit breaker + timeout |
| [05](./chapters/chapter-05-benchmark/) | 多模型并跑 + P50/P95 聚合 |
| [06](./chapters/chapter-06-domestic-benchmark/) | 国产模型 OpenAI 兼容 client 注册表 |
| [07](./chapters/chapter-07-pricing-calculator/) | 月度账单估算 + 性价比排序 |
| [08](./chapters/chapter-08-quota-manager/) | InMemoryRedis + 两段式 token 配额 |
| [09](./chapters/chapter-09-tier-router/) | small/mid/flagship 三档 YAML 路由 |
| [10](./chapters/chapter-10-semantic-cache/) | embedding + 余弦相似度 + LRU/TTL |
| [11](./chapters/chapter-11-agent-token-saving/) | Agent 4 条 Token 降本路径 |
| [12](./chapters/chapter-12-checkpoint-recovery/) | Checkpoint + 断点续跑 + smoke test |

依赖：所有 demo 通过 `chapters/_common/mock_llm.py` 共用一个本地 mock LLM 客户端，**完全脱网可跑**，不需要任何 API key。

### 生产级实现（`routes/`）

可直接部署的工程参考实现，对位特定文章的"完整附录"。

| 目录 | 配套文章 | 内容 |
|------|----------|------|
| [`routes/glm-5.2-tri-channel/`](./routes/glm-5.2-tri-channel/README.md) | 第 13 篇 | GLM-5.2 三通道智能路由器：FastAPI + httpx 异步实现，含 priority/cost fallback、circuit breaker、Prometheus 埋点、三档 profile 配置（realtime/batch/longctx）、压测脚本、回归评测脚本、Docker Compose 一键栈、pytest 用例 |

后续文章如有配套代码会陆续补到这里。

---

## 联系方式

- 邮箱: <fangzehui@chinaresc.com>
- 勘误/讨论: 欢迎提交 Issue 或 PR

---

## 许可证

代码部分采用 [MIT License](./LICENSE) 发布；文章内容版权归作者所有，转载请保留原作者署名与原文链接。
