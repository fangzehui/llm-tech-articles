# Chapter 25 - Agent 长期记忆三代演进

本目录是文章《[Agent长期记忆三代演进：从RAG到Memory Graph，mem0 / Zep / LangMem / Letta 深度对比](../../25-Agent长期记忆三代演进.md)》的配套示例代码。

## 项目介绍

三份最小可读的 Python demo，把 Agent 长期记忆的三代演进用 ~600 行代码演示清楚：
从「把 RAG 当记忆用」（Gen1），到「结构化 fact + 冲突消解」（Gen2），
再到「实体-关系-事件三层记忆图 + MemGPT 分层上下文」（Gen3）。
配一个 `memory_selector.py` 输入场景就能给出 4 大主流开源方案的排序。

> 三代分法是本仓库的一种"叙述视角"，业界公开的划分包括「工程化 / 结构化 / 认知架构」等；
> 本 README 与文章都在开头明确说明这一点，不宣称是唯一分类。

## 演进图（一张图看懂）

```
 Gen1: RAG-as-Memory                Gen2: Structured Memory              Gen3: Memory Graph
 ─────────────────                  ────────────────────                 ──────────────────
                                                                        
   [user text] ──┐                     [user text]                          [user text]
                 │                          │                                    │
                 ▼                          ▼                                    ▼
           chunk & embed              LLM extract facts               LLM extract entities+relations
                 │                          │                                    │
                 ▼                          ▼                                    ▼
           +───────────+              +──────────────+                +──────────────────────+
           │ vector DB │              │ facts table  │                │ nodes + edges +      │
           │  (top-k)  │              │  + bi-temp   │                │ episodes  +  vecs    │
           +───────────+              +──────────────+                +──────────────────────+
                 │                          │                                    │
                 ▼                          ▼                                    ▼
        cosine top-k              filter valid + vector          vec + graph walk + episode
        (原文拼进 prompt)          (只召回 valid fact)              (三路召回 + RRF + rerank)

 代表方案                          代表方案                              代表方案
 - LlamaIndex/LangChain            - mem0 (Apache 2.0)                 - Letta / MemGPT
   基础 RAG                        - Zep 的 Fact 层                     - Graphiti (Zep)
 - OpenAI Assistants               - LangMem semantic memory           - Hindsight (arxiv 2512.12818)
   file_search
```

## 四大开源方案速查表

| 项目 | GitHub | 定位 | 存储 | 时序 | 图关系 | 自托管 | 关键数据 / 事件 |
|------|--------|------|------|------|--------|--------|----------------|
| **mem0** | [mem0ai/mem0](https://github.com/mem0ai/mem0) | Memory-as-a-Service，全栈 Apache 2.0 | 向量 + Mem0g 可选图 | 时间戳 + update 语义 | 中（Mem0g 变体） | 完全支持 | 2025-10 融资 24M USD 系列 A，累计 41k+ stars（来源：[mem0.ai/series-a](https://mem0.ai/series-a)） |
| **Zep / Graphiti** | [getzep/graphiti](https://github.com/getzep/graphiti) | 双时态知识图 + 企业托管 | Neo4j / FalkorDB / Kuzu 图 | bi-temporal 原生 | 强 | Graphiti 可，Zep Cloud 不可 | Graphiti 8 个月内破 14k stars（来源：[Zep 博客 2025-07](https://blog.getzep.com/graphiti-knowledge-graphs-falkordb-support/)） |
| **LangMem** | [langchain-ai/langmem](https://github.com/langchain-ai/langmem) | LangChain 官方长期记忆 SDK | LangGraph Store（KV + 向量） | 命名空间隔离 | 弱 | 支持（InMemoryStore/Postgres） | 2025-02-18 发布（来源：[LangChain 博客](https://www.langchain.com/blog/langmem-sdk-launch)） |
| **Letta**（原 MemGPT）| [letta-ai/letta](https://github.com/letta-ai/letta) | OS 风格分层记忆、agent 自主 self-edit | core + archival + recall | 依赖 archival 元数据 | 中 | 完全支持 | 2024 由 MemGPT rebrand（来源：[Letta 官方文档](https://docs.letta.com/concepts/letta)） |

> star 数是快速变化指标，正文只保留论文/官方公告里的锚点数据，最新数字请去 GitHub 页面右上角查。

## 文件清单

| 文件 | 说明 | 依赖 |
|------|------|------|
| `gen1_rag_memory.py` | 第一代：纯向量 RAG 记忆（含 3 个"暴露局限"的 demo） | stdlib only |
| `gen2_structured_memory.py` | 第二代：正则式事实抽取 + bi-temporal 冲突消解（模拟 mem0/Zep） | stdlib only |
| `gen3_memory_graph.py` | 第三代：实体+关系+事件三层图 + RRF hybrid 检索 + MemGPT 分层上下文 | stdlib only |
| `memory_selector.py` | 交互式选型器：输入场景权重，输出 4 方案排序（含 `--demo` 跑 6 类典型场景） | stdlib only |
| `tests/test_memory.py` | 18 个 pytest 用例覆盖上述四个模块 | pytest |
| `requirements.txt` | 只需 pytest；接真实 LLM 时按需装 mem0ai / langmem / letta | — |

## 安装 & 一行 Demo

```bash
cd chapters/chapter-24-agent-memory-evolution
pip install -r requirements.txt   # 实际只需要 pytest

# 1) 跑第一代 RAG 记忆的 3 个暴露局限的 demo
python gen1_rag_memory.py

# 2) 跑第二代结构化记忆的抽取 + 冲突消解
python gen2_structured_memory.py

# 3) 跑第三代记忆图 + MemGPT 分层上下文
python gen3_memory_graph.py

# 4) 交互式选型器
python memory_selector.py --scenario long_session --users many --graph   # 单场景
python memory_selector.py --demo                                          # 6 类典型场景
python memory_selector.py --langchain --json                              # JSON 输出

# 5) 冒烟测试全绿
pytest tests/ -v
```

## 三代记忆的关键差异（对着代码看）

### 什么触发了从 Gen1 → Gen2？
Gen1 的 `RagMemory` 只有 `add / search`，没有 `update / invalidate`。
`gen1_rag_memory.py` 的三个 demo 分别暴露：
- **冲突召回**：老"用 Python"和新"用 Go"一起进 prompt，LLM 只能猜。
- **冗余爆炸**：同一句话重复说会占 5 个 chunk。
- **无法忘记**：改口只能靠更长 prompt 补丁。

Gen2 用 `Fact(subject, predicate, object, valid_from, valid_to)` 三元组把每条 fact 独立化，
`add_from_conversation` 里做冲突消解：`current[key]` 命中就把老的置 `INVALID`。
这就是 mem0 论文（arxiv 2504.19413）的"update phase"和 Zep 的"fact invalidation"。

### 什么触发了从 Gen2 → Gen3？
Gen2 是"扁平事实列表"，回答"用户和他老板都住在哪些城市"这类需要多跳的问题就抓瞎。
Gen3 把 fact 拆成 `Node + Edge`，加上 `Episode` 层保留原始事件；
检索走"向量召回 + 图 BFS + episode 相似"三路 RRF 融合（做法参考
[Zep 论文里的三步 search / rerank / constructor 流程](https://blog.getzep.com/content/files/2025/01/ZEP__USING_KNOWLEDGE_GRAPHS_TO_POWER_LLM_AGENT_MEMORY_2025011700.pdf)）。

再叠上 `TieredContext` 就是 MemGPT/Letta 的"OS 虚拟内存"直觉：
- `core_memory`（in-context，直接放 prompt）
- `archival`（out-of-context，agent 通过工具主动 search/insert）
- 超限自动淘汰（真实场景是 LLM 摘要压缩）

## 输出示意（截自 gen2 演示 2）

```
第二轮之后（老事实应被自动置为 invalid）：
  [✗过期] user - uses_language - Python
  [✓]     user - works_in - 北京
  [✓]     user - role - 一名后端
  [✓]     user - uses_language - Go
  [✓]     user - lives_in - 上海

检索：'用户目前用什么语言' —— 只应召回 valid 的 Go
[✓当前] user - uses_language - Go
```

## 生产落地怎么改？

| 本仓库 stub | 生产替换成 |
|-------------|-----------|
| `fake_embed` hash 向量 | OpenAI `text-embedding-3-small` / bge-large-zh-v1.5 |
| 正则 `EXTRACT_RULES` | LLM function-call 抽取（gpt-4o-mini / claude-haiku 都够） |
| 内存 list 存 facts | mem0 的 Postgres / Qdrant，Zep 的 Neo4j |
| BFS `graph_walk` | Graphiti / Kuzu 的 Cypher 查询 |
| RRF `hybrid_search` | Elasticsearch + `cross-encoder` reranker（参考 [Elastic 博客](https://elasticstack.blog.csdn.net/article/details/162063727)） |

## 测试

```bash
pytest tests/ -v
# ============================== 18 passed in 1.29s ==============================
```

18 个用例分组：
- Gen1: 归一化 / add+search / build_prompt / demo runs（4）
- Gen2: fact 抽取 / 冲突消解 / only_valid 过滤 / demo runs（4）
- Gen3: 节点边 / bi-temporal / BFS / hybrid_search / tiered 淘汰 / demo runs（6）
- Selector: 目录完整性 / LangChain 场景选 LangMem / 图场景选 Zep / demo runs（4）

## 参考资料

- mem0：[官方博客 - $24M 系列 A](https://mem0.ai/series-a)、[论文 arxiv 2504.19413](https://arxiv.org/abs/2504.19413)
- Zep：[getzep/graphiti](https://github.com/getzep/graphiti)、[论文 PDF](https://blog.getzep.com/content/files/2025/01/ZEP__USING_KNOWLEDGE_GRAPHS_TO_POWER_LLM_AGENT_MEMORY_2025011700.pdf)、[Neo4j 集成博客](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)
- LangMem：[SDK 发布公告 2025-02-18](https://www.langchain.com/blog/langmem-sdk-launch)、[LangChain 官方文档](https://docs.langchain.com/oss/javascript/langchain/long-term-memory)
- Letta：[官方文档 concepts](https://docs.letta.com/concepts/letta)、[MemGPT legacy agent 架构](https://docs.letta.com/guides/legacy/memgpt_agents_legacy)
- Anthropic memory tool：[官方文档](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- Elastic 混合检索：[博客 - Elasticsearch 上的持久 agent 记忆层](https://elasticstack.blog.csdn.net/article/details/162063727)
