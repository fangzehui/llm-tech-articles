# 2026.6 Prompt Caching 成本实测横评：Anthropic / OpenAI / Gemini / 智谱 / DeepSeek 五家计费机制 + 长系统提示词复用省钱量化

> 一份 8000 token 的系统提示，每天被一个轮询 Agent 跑 100 次，一年下来你为「重复处理同一段前缀」多付的钱够给团队加一台 H100。Prompt Caching 是 2026 年最值得开的开关之一，但五家厂商的计费规则差异巨大，开错了反而更贵。

## 一、引言：为什么不开 cache 一年烧掉一台 H100

跑过任何一个生产 Agent 都会发现一件事：每次请求里，真正变化的 user prompt 通常只有几百个 token，而前面那段 system prompt + few-shot examples + RAG 检索上下文加起来动不动就是 5K～30K token。每一轮调用，你都在让模型把这段几乎完全相同的前缀重新算一遍——这是 LLM API 账单上最大的单笔浪费。

我们用一个最朴素的轮询场景来量化这件事：

- **系统提示**：8000 token（一份典型的客服 Bot 角色设定 + 200 行业务规则 + 5 条 few-shot 示例 + 一段 RAG 拼接的 1.5K 文档摘要）
- **用户输入**：每次 200 token
- **输出**：每次 200 token
- **频率**：每 30 秒 1 次，全天 24 小时持续轮询

365 天合计 100 万次调用，光是输入 token 就要消耗 (8000 + 200) × 1,000,000 ≈ 82 亿 token。落到价格上：

| 模型 | 一年纯输入账单（无缓存） | 开缓存后（命中率 99%） | 一年差价 |
|---|---|---|---|
| Claude Sonnet 4.5 | $24,600 | $5,766 | **$18,834** |
| Claude Fable 5 | $82,000 | $19,294 | **$62,706** |
| GPT-5 | $10,250 | $2,889 | **$7,361** |
| Gemini 3 Pro | $8,200 | $1,719 | **$6,481** |
| GLM-5.2 | $4,920 | $1,237 | **$3,683** |
| DeepSeek V3.2 | $574 | $322 | **$252** |

> 计算口径：每次调用首次写入按 cache_write 价、后续 99% 调用按 cache_read 价；表格只算输入侧，输出侧每家差异并不主要由缓存决定。

差距非常直观：旗舰级模型一年因为不开 cache 多烧六位数美金，国产一线也是几千到上万美金的浪费——这个数字够给团队加一台 H100 推理卡，或者多招一个实习生。

但开 cache 不是"打个开关"那么简单。Anthropic 要你显式标 `cache_control`、OpenAI 是自动前缀匹配但有 1024 token 起步线、Gemini 必须先 `cachedContents.create()` 拿到 ID、智谱是隐式自动、DeepSeek 走硬盘 KV cache。**计费维度也分裂**：Anthropic 区分 5min / 1h 两档 TTL 而且 1h 写入要 2 倍溢价；OpenAI 没有写入溢价但 cache 只活 5～10 分钟；Gemini 还要单独按"GB·小时"收存储费，不删 cache 等于一直在烧钱。

这篇文章把五家（实际是 6 个具体型号）的计费机制、命中机制、TTL 规则全部拉到同一张表里横着对比，并给出 4 个关键场景的实测：长系统提示冷启动、100 次连续轮询、5min vs 1h TTL break-even、以及 Tool 定义可缓存性。所有数据都用 [chapter-17/cache_bench.py](./chapters/chapter-17-prompt-cache/) 计算，不依赖 SDK，纯 dict + 数学，欢迎自己 fork 改场景再算一遍。

跟前几篇的关系：02 号文（Token 成本优化实战）讲了 token 是怎么烧出来的；08 号文（Token 成本治理架构）给了企业级配额管控；这一篇站在第三个维度——**单笔账单里的"重复部分"如何用 cache 省下 50%~95%**，并补齐 16 号文 Function Calling 文章里没展开的"tools 块如何上 cache"细节。

## 二、五家 Prompt Cache 一图速览

按 2026-06-19 截图各家最新公开定价页（链接在 §三 每小节内），用同一张表把五家拍成一张图。

| 模型 | 输入 | 输出 | Cache write | Cache read | 触发机制 | 最小粒度 | 默认 TTL | 长 TTL |
|---|---|---|---|---|---|---|---|---|
| Claude Sonnet 4.5 | $3 | $15 | $3.75（5m）/ $6（1h） | $0.30 | 显式 cache_control | 1024 tok | 5 min | 1h |
| Claude Fable 5 ★ | $10 | $50 | $12.5（5m）/ $20（1h） | $1.00 | 显式 cache_control | 1024 tok | 5 min | 1h |
| OpenAI GPT-5 | $1.25 | $10 | $1.25（无溢价） | $0.125 | 自动前缀 | 1024 tok | 5～10 min | ~1h（off-peak） |
| Google Gemini 3 Pro | $1.0 | $4.0 | $1.0（无溢价） | $0.10 | cachedContents 显式 / 隐式自动 | 4096 tok（Pro） | 60 min | 24h |
| 智谱 GLM-5.2 | $0.6 | $2.0 | $0.6（无溢价） | $0.10 | 自动前缀（隐式） | 1024 tok | ~10 min | ~60 min |
| DeepSeek V3.2 | $0.07 | $1.10 | $0.07（无溢价） | $0.014 | 硬盘 KV / 自动 | 64 tok | 数小时～数日 | best-effort |

> ★ Fable 5 是本系列虚拟旗舰（对标 Anthropic Opus 5.x，参考 13/14 号文一致设定）；其它五家是真实公开定价。单价单位均为 USD / 1M tokens。

读这张表，先看三件事：

1. **写入溢价只有 Anthropic 收**。Sonnet 4.5 写一段 5 分钟缓存要付 $3.75/M（标准价 1.25×），写一段 1 小时缓存要付 $6/M（2×）。其它四家写入都是 input 价本身——这意味着你只要"写"一次 cache 就立刻不亏，break-even 就 1 次。
2. **读取折扣 OpenAI 最狠**。GPT-5 cache_read 0.125/M，相对 input 1.25/M 是 **90% off**（$1.125/M tokens 的差价）。Anthropic 同样是 90%（0.30 / 3.0）；Gemini / GLM 是 90%；DeepSeek 是 80%。但因为 OpenAI 写入无溢价，"省钱比例"实际由 input 与 output 的相对占比决定。
3. **触发机制差异最大**。Anthropic 是唯一要你**显式**调用 `cache_control` 的；其它四家全部支持自动前缀匹配。Gemini 在自动模式之外还提供"显式 cachedContents 资源对象"——后者会单独按时间收存储费（$1/MTok·hour），这是最容易踩坑的"我加了 cache 反而账单涨了"陷阱。

接下来 §三 把每家的具体规则单独拆开，§四 集中讲触发机制，§五 ~ §八 跑四个场景的真实成本。

## 三、五家 Prompt Cache 计费机制详解

### 3.1 Anthropic：显式 cache_control + 5min/1h 双档 TTL

Anthropic 在 [Prompt caching 官方文档](https://docs.claude.com/en/docs/build-with-claude/prompt-caching) 里把规则讲得最细。核心三条：

- **必须显式打标**：在 `system` / `messages` 里挑某个 content block 加 `cache_control: {"type": "ephemeral"}`，这一标记表示"从请求开头到这个 block 为止的所有 token，全部作为一段候选缓存前缀"。
- **完全前缀匹配**：缓存键是这段前缀的哈希；多一个空格、大小写不一致都会让 cache miss。
- **5min 默认 / 1h 可选**：默认 TTL 5 分钟，每次命中自动续命（不再扣写入费）。要拉长到 1h，把 `cache_control` 写成 `{"type": "ephemeral", "ttl": "1h"}`，同时通过请求头 `anthropic-beta: extended-cache-ttl-2025-04-11` 启用。

最小可用调用 dict（节选自官方示例）：

```python
{
  "model": "claude-sonnet-4-5",
  "max_tokens": 1024,
  "system": [
    {
      "type": "text",
      "text": "<8000 token 的稳定 instruction + few-shot + RAG 上下文>",
      "cache_control": {"type": "ephemeral"}        # 默认 5min
      # 想要 1h 就改成 {"type": "ephemeral", "ttl": "1h"}
    }
  ],
  "messages": [
    {"role": "user", "content": "用户的实际提问，每次变化"}
  ]
}
```

返回 `usage` 里会多三个字段，对账时直接看：

```python
"usage": {
  "input_tokens": 200,
  "cache_creation_input_tokens": 8000,    # 首次写入
  "cache_read_input_tokens": 0,
  "output_tokens": 200,
  "cache_creation": {
    "ephemeral_5m_input_tokens": 8000,
    "ephemeral_1h_input_tokens": 0
  }
}
```

第二次同前缀调用，`cache_creation_input_tokens` 变 0、`cache_read_input_tokens` 变 8000，这就是命中。

价格表（[官方 docs](https://docs.claude.com/en/docs/build-with-claude/prompt-caching)，截至 2026-06-19）：

| 模型 | 基础输入 | 5min 写入 | 1h 写入 | 命中读取 | 输出 |
|---|---|---|---|---|---|
| Claude Opus 4.x | $5 / MTok | $6.25 / MTok | $10 / MTok | $0.50 / MTok | $25 / MTok |
| Claude Opus 4.1 | $15 / MTok | $18.75 / MTok | $30 / MTok | $1.50 / MTok | $75 / MTok |
| Claude Sonnet 4.5 | $3 / MTok | $3.75 / MTok | $6 / MTok | $0.30 / MTok | $15 / MTok |
| Claude Haiku 4.5 | $1 / MTok | $1.25 / MTok | $2 / MTok | $0.10 / MTok | $5 / MTok |
| Claude Fable 5 ★ | $10 / MTok | $12.5 / MTok | $20 / MTok | $1.00 / MTok | $50 / MTok |

> 所有 Anthropic 模型严格遵循三条乘数：`5min写 = 输入 × 1.25`、`1h写 = 输入 × 2.0`、`读 = 输入 × 0.10`（[参考 Spring AI 总结](https://spring.io/blog/2025/10/27/spring-ai-anthropic-prompt-caching-blog/)）。

不能缓存或不该缓存的字段：

- **变化的 user message**：每次都不一样，放在 cache_control 之后即可；前缀以前到 cache_control 为止的部分都被缓存
- **多于 4 个 cache_control 标记**：Anthropic 一次最多接受 4 段缓存前缀，超出会报错
- **小于 1024 token 的前缀**：Sonnet/Haiku 系最小缓存粒度 1024，Opus 是 2048（小于这个数也允许打标，但实际不会写入）

### 3.2 OpenAI：自动前缀 + GPT-5 90% off

OpenAI 在 [Prompt Caching 官方指南](https://platform.openai.com/docs/guides/prompt-caching) 里采取了完全相反的设计哲学：**用户什么都不用做**。

- **完全自动**：任何 ≥ 1024 token 的请求自动启用前缀缓存，并按 128 token 为增量命中（即命中 token 数总是 1024、1152、1280、1408……）。无 API 参数、无 SDK 调整。
- **没有写入溢价**：cache_write = 标准 input 价（你"写"的那一次根本不知道自己在写，按 input 计费）。
- **TTL 5～10 分钟**：闲置 5 分钟以上即可能被回收；非高峰期可能持续到 1 小时（["实际表现" 来自 OpenAI 社区与 markaicode 实测](https://markaicode.com/openai-prompt-caching-how-it-works)）。
- **打折比例分两档**：GPT-4o 系是 50% off（cached $1.25 vs input $2.50）；**GPT-5 系是 90% off**（cached $0.125 vs input $1.25），具体见 [LLM API Pricing Comparison 2025（intuitionlabs PDF）](https://intuitionlabs.ai/pdfs/llm-api-pricing-comparison-2025-openai-gemini-claude.pdf)。

最小可用调用就是普通的 chat.completions：

```python
{
  "model": "gpt-5",
  "messages": [
    {"role": "system", "content": "<8000 token 的稳定指令>"},     # 自动入 cache
    {"role": "user", "content": "用户的实际提问"}                   # 变化部分
  ]
}
```

返回 `usage.prompt_tokens_details.cached_tokens` 直接告诉你这次有多少 token 命中：

```python
"usage": {
  "prompt_tokens": 8200,
  "completion_tokens": 200,
  "prompt_tokens_details": {"cached_tokens": 7936}     # 1024 + 6×128 + ...
}
```

GPT-5 系（含 GPT-5 Mini / Nano）的统一公式：**cache_read = input × 0.10**。OpenAI 在 [GPT-5 launch 页](https://openai.com/index/introducing-gpt-5/) 把这条 90% off 列为了 GPT-5 家族的"默认行为"。

不可缓存或会破缓存的内容：

- **任何前缀里的非确定性 token**：常见踩坑——把 `timestamp` 或 `request_id` 当成系统提示开头，每次都不一样，cache 永远 miss。**动态字段必须放后端**。
- **图像 / 多模态内容**：纯文本的 message 走标准缓存；带 image 的 message 在 GPT-4o 系会按图像 token 单独计费，cache 行为以官方文档为准
- **小于 1024 token 的前缀**：再短的提示也不会进 cache，`cached_tokens` 恒为 0

### 3.3 Google Gemini：implicit + explicit 双轨

Gemini 在 [Context caching 官方文档](https://ai.google.dev/gemini-api/docs/caching) 给出了两种缓存机制，差异比 Anthropic 还大：

#### 3.3.1 隐式缓存（implicit caching）

- **2.5 系及以上默认开启**，无需任何代码改动
- **触发条件**：前缀 token 数 ≥ 2048（Pro）/ 1024（Flash）；近一段时间内有相同前缀的请求
- **不保证命中**：Google 自己说"no guaranteed cost savings"，命中走 input × 0.10 折扣
- **零额外成本**：不收存储费，命中失败也不收钱

#### 3.3.2 显式缓存（cachedContents）

- 必须先调用 `cachedContents.create()` 拿到一个 `name` 资源 ID，后续 `generateContent` 通过 `cachedContent` 字段引用
- **保证命中并保证打折**
- **最小 token 数 4096**（Pro 系）/ 2048（Flash 系）；小于这个数会报 INVALID_ARGUMENT
- **TTL 默认 60 min，最长 24h，可主动 update / delete**
- **额外按存储计费**：Gemini 3 Pro 约 **$1.0 / MTok / 小时**，这是最容易把账单跑飞的部分

最小可用调用：

```python
# Step 1: 创建一个 cachedContents 资源
cached = client.caches.create(
    model="gemini-3-pro-preview",
    config={
        "contents": [{"role": "user", "parts": [{"text": "<8000 token 系统提示>"}]}],
        "system_instruction": "你是一个客服 Bot",
        "ttl": "3600s",                # 1h
    }
)
# cached.name = "cachedContents/abc123..."

# Step 2: 后续请求引用它
response = client.models.generate_content(
    model="gemini-3-pro-preview",
    contents=[{"role": "user", "parts": [{"text": "用户实际提问"}]}],
    config={"cached_content": cached.name},
)
# response.usage_metadata.cached_content_token_count == 8000
```

最容易踩的坑（[gemilab 实战警告](https://gemilab.net/en/blog/gemini-context-caching-cost-without-bill-surprise-2026)）：

- **存储费按小时收**：哪怕你这一小时一次都不调用，那段缓存只要还在就会按 $1/MTok·h 一直收。一段 30K token 的缓存放一周 = 30 × 24 × 7 × $1 = $5040，远超调用本身的钱。**用完即删**是 Gemini 的铁律。
- **小于阈值静默失败**：低于 4096 token 不会报错，也不会真的写入 cache，调用照价收费。

价格表（[Gemini Developer API Pricing](https://ai.google.dev/gemini-api/docs/pricing)）：

| 模型 | 输入 | 输出 | 缓存读取 | 缓存存储 |
|---|---|---|---|---|
| Gemini 3 Pro Preview（≤200K ctx） | $0.75 / MTok | $4.50 / MTok | $0.075 / MTok | $1 / MTok·h |
| Gemini 3 Pro Preview（>200K ctx） | $2.70 / MTok | $16.20 / MTok | $0.27 / MTok | $1 / MTok·h |
| Gemini 3 Flash | $0.30 / MTok | $2.50 / MTok | $0.03 / MTok | $0.10 / MTok·h |

> 本文统一按 14 号文一致的 Gemini 3 Pro 等效价格 $1.0 / $4.0（含中转折扣后）做横评，便于跨篇对照。

### 3.4 智谱 BigModel：隐式 + 透明计费

智谱在 [上下文缓存官方文档](https://docs.bigmodel.cn/cn/guide/capabilities/cache) 给的设计是**纯隐式自动**：

- **自动识别**：基于"内容相似度"自动触发，无需任何 API 参数
- **完全透明**：响应里 `usage.prompt_tokens_details.cached_tokens` 直接告诉你命中了几个 token
- **覆盖全系**：GLM-5.2 / GLM-5.1 / GLM-5 / GLM-4.x 全部支持
- **缓存命中通常按标准价 50% 计费**（[官方文档原文](https://docs.bigmodel.cn/cn/guide/capabilities/cache)）

但是落到 GLM-5.x 的具体价格上，[卡码笔记 2026 年定价整理](https://notes.kamacoder.com/llm/intro/llm_pricing.html) 显示分了**短上下文 / 长上下文**两档：

| 上下文 | 标准输入 | 缓存命中 | 节省 |
|---|---|---|---|
| < 32K | ¥6 / MTok | ¥1.3 / MTok | 78% |
| ≥ 32K | ¥8 / MTok | ¥2 / MTok | 75% |

折算美元（汇率 7.0）：

- 短上下文：$0.86 input / $0.19 cached
- 长上下文：$1.14 input / $0.29 cached

本文统一按 14 号文一致的 **GLM-5.2 折扣价 $0.6 / $2.0 + cache_read $0.10**（约 input × 0.17）做横评，与官方公开价相比偏保守，便于把"国产平台经过聚合渠道后的实际价"摆进对比。

最小可用调用就是普通的 chat.completions（OpenAI 兼容协议）：

```python
{
  "model": "glm-5.2",
  "messages": [
    {"role": "system", "content": "<8000 token 系统提示>"},
    {"role": "user", "content": "用户实际提问"}
  ]
}
```

不可缓存或会破缓存的内容：

- **格式微差**：智谱明确写"轻微的格式差异可能影响缓存效果"——多一个空格、换行符不一样、JSON key 顺序不一样都会让 cache miss
- **缓存有合理时效性**：官方未公布精确 TTL，社区实测 10 分钟左右；过期后重新计算

### 3.5 DeepSeek：硬盘缓存 + 64 token 起

DeepSeek 在 [上下文硬盘缓存官方指南](https://api-docs.deepseek.com/zh-cn/guides/kv_cache/) 给的实现最特别：

- **硬盘 KV 落盘**：不像 Anthropic / OpenAI 把 KV cache 留在 GPU 显存，DeepSeek 把 KV 状态压缩后写到分布式硬盘阵列。这意味着**缓存几乎不收回**——官方说"几小时到几天"。
- **64 token 起步**：最小缓存粒度只有 64 token，远低于其它四家的 1024。短系统提示也能命中。
- **完全自动 + 无配置**：所有用户默认开启，没有 cache_control、没有 cachedContents
- **完全前缀匹配**：从第 0 个 token 开始要完全一致；中间开始的重复无法被命中

价格表（DeepSeek V3.2 当前，[官方 KV cache blog](https://api-docs.deepseek.com/zh-cn/news/news0802/)）：

| 字段 | 价格（每 MTok） |
|---|---|
| 缓存命中（prompt_cache_hit_tokens） | ¥0.1 ≈ $0.014 |
| 缓存未命中（prompt_cache_miss_tokens） | ¥1.0 ≈ $0.14（V3.2 实际折扣后 ≈ $0.07） |
| 输出 | ¥6.0 ≈ $0.86（折扣后 ≈ $1.10 含思考） |

V4 系（V4-Pro / V4-Flash）2026-05 永久降价后单价更低，本文按本系列基准型号 V3.2 计费。

最小调用：

```python
{
  "model": "deepseek-chat",
  "messages": [
    {"role": "system", "content": "<8000 token 系统提示>"},
    {"role": "user", "content": "用户实际提问"}
  ]
}
```

返回 `usage` 中：

```python
"usage": {
  "prompt_tokens": 8200,
  "prompt_cache_hit_tokens": 8000,
  "prompt_cache_miss_tokens": 200,
  "completion_tokens": 200
}
```

不可缓存或会破缓存的内容：

- **完全前缀匹配**：从第 0 个 token 开始；中间相同、开头不同照样 miss
- **请求间隔过长**：尽管"几小时到几天"，但官方明确**不保证 100% 命中**，是 best-effort
- **prompt 中的尾部空白也敏感**：哪怕系统提示尾部多一个换行符，都会 cache miss

## 四、命中机制差异：显式 vs 自动 vs 资源对象

把五家排成一个 2×2 矩阵，依据"是否需要用户主动声明"和"是否要管理资源生命周期"两个维度：

| | 自动触发 | 显式声明 |
|---|---|---|
| **无生命周期管理** | OpenAI GPT-5 / 智谱 GLM-5.2 / DeepSeek V3.2 | Anthropic Sonnet 4.5 / Fable 5（cache_control 标记） |
| **有生命周期管理** | Gemini 隐式（自动收回） | Gemini 显式 cachedContents（必须 delete） |

四象限对应四种工程姿态：

1. **OpenAI / GLM / DeepSeek：什么都不用做**
   只要保证你的 system prompt + few-shot 是完全静态的（没有 timestamp、user_id、动态 RAG 拼接），cache 就会自动生效。最大的工程任务是把"动态字段"挪到 messages 末尾。

2. **Anthropic：要标 cache_control，但只要标 1 次**
   必须在 prompt 构造时显式打标，但不需要管理 cache 资源 ID。打标位置决定缓存终点：标在 `system` 末尾就只缓存 system；标在 `messages[2]` 就缓存到第二条 user 之前。一次最多 4 个标记，多了报错。

3. **Gemini 隐式：自动 + 不可控**
   零代码改动，但 Google 不保证命中、不保证省钱比例。生产场景如果需要"可预期的省钱比例"——比如要拿到合规账单做 ROI 报告，必须用显式。

4. **Gemini 显式 cachedContents：要管 ID + 要管 TTL + 要管 delete**
   必须维护一个 `cache_id` 池子，应用生命周期内复用；用完必须主动 `client.caches.delete(name)`，否则按小时持续烧存储费。建议在配套服务里用一个 worker 跑 LRU + 定期清理。

工程上把这四种映射到代码里大概是这样：

```python
class CacheBackend:
    """五家 cache 的统一抽象."""

    def call(self, model, system_prompt, user_msg, output_max=2048):
        if model.startswith("claude"):
            # Anthropic：显式 cache_control
            return self._anthropic_call(system_prompt, user_msg, with_cache=True)
        elif model.startswith("gemini-explicit-"):
            # Gemini 显式：先 create，复用 cache_id
            cache_id = self._cache_pool.get_or_create(model, system_prompt)
            return self._gemini_call(cache_id, user_msg)
        else:
            # OpenAI / GLM / DeepSeek / Gemini 隐式：透明
            return self._auto_prefix_call(model, system_prompt, user_msg)
```

这是为什么很多团队最终选择**走聚合平台 + OpenAI 兼容协议**——它把"五家四种 API 形态"压平成一种调用方式，业务层不用关心底层是 Anthropic 在标 cache_control 还是 OpenAI 在自动前缀匹配。

## 五、实测一：长系统提示词冷启动 / 二轮命中

第一组实测：把 8000 token 系统提示拼好，第 1 次和第 2 次同样的 user 提问，看每家的实际计费回执 dict 长什么样、单次成本相差多少。

### 5.1 测试基线

- system_prompt：8000 token（一份典型客服 Bot instruction）
- user_prompt：200 token
- output：200 token
- 间隔：30 秒（< 5 min TTL，确保第 2 次命中）

### 5.2 第 1 次（冷启动）

| 模型 | 计费回执 dict（关键字段） | 单次成本 |
|---|---|---|
| Sonnet 4.5 | `{"input_tokens": 200, "cache_creation_input_tokens": 8000, "cache_read_input_tokens": 0, "output_tokens": 200}` | $0.0336 |
| Fable 5 | 同上结构 | $0.1120 |
| GPT-5 | `{"prompt_tokens": 8200, "completion_tokens": 200, "prompt_tokens_details": {"cached_tokens": 0}}` | $0.0123 |
| Gemini 3 Pro（显式） | `{"prompt_token_count": 200, "cached_content_token_count": 0, "candidates_token_count": 200}` + 一次性 create 成本 | $0.0090 |
| GLM-5.2 | `{"prompt_tokens": 8200, "prompt_tokens_details": {"cached_tokens": 0}, "completion_tokens": 200}` | $0.0053 |
| DeepSeek V3.2 | `{"prompt_tokens": 8200, "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 8200, "completion_tokens": 200}` | $0.0008 |

冷启动时，**Anthropic 是唯一一家比不开 cache 还贵**的——8000 token × $3.75/M = $0.030 多花 0.0006，因为 1.25× 写入溢价。其它四家冷启动等于不开 cache。

### 5.3 第 2 次（命中）

| 模型 | 计费回执 dict（关键字段） | 单次成本 | 第 2 次省比例 |
|---|---|---|---|
| Sonnet 4.5 | `{"input_tokens": 200, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 8000, "output_tokens": 200}` | $0.0060 | 78.3% |
| Fable 5 | 同上结构 | $0.0200 | 78.3% |
| GPT-5 | `{"prompt_tokens": 8200, "prompt_tokens_details": {"cached_tokens": 8064}}`（命中按 128 倍数） | $0.0033 | 73.4% |
| Gemini 3 Pro | `{"cached_content_token_count": 8000}` | $0.0019 | 79.2% |
| GLM-5.2 | `{"prompt_tokens_details": {"cached_tokens": 8000}}` | $0.0014 | 73.9% |
| DeepSeek V3.2 | `{"prompt_cache_hit_tokens": 8000, "prompt_cache_miss_tokens": 200}` | $0.0004 | 47.4% |

数据看下来三件事：

1. **第 2 次开始所有人都开始净赚**。除了 Anthropic 第 1 次稍亏，其它五家从第 1 次就持平或净赚（参考 §六 break-even 部分，所有家 break-even = 2 次）。
2. **省比例大致都在 70%~80% 区间，DeepSeek 因 input 已经够便宜显得"省得少"**。但绝对省钱额度还得看输入量级——同样省 70%，Fable 5 一次能省 $0.092，DeepSeek 只能省 $0.0004，差 230 倍。
3. **OpenAI 命中按 128 token 取整**——你拼了 8000 token 的前缀，实际命中的可能是 7936 或 8064（取决于 tokenizer 切分），剩下的几十个 token 走 input 价。

落到决策上：**Anthropic 的"高写入溢价 + 高读取折扣"模型适合长尾轮询型场景**（一段 cache 复用 100 次以上），不适合"一段 cache 复用 1~2 次就丢"的随机命中场景。其它四家则在所有场景下都是"开就有用"。

## 六、实测二：100 次连续轮询省钱比例

把场景拉满到 100 次连续轮询（间隔 30 秒，全部命中第 1 次写入的缓存）：

```python
s = Scenario(
    system_prompt_tokens=8000,
    user_tokens_per_call=200,
    output_tokens_per_call=200,
    num_calls=100,
    interval_minutes=0.5,
)
```

跑 [chapter-17/cache_bench.py](./chapters/chapter-17-prompt-cache/cache_bench.py) 的 `compare_all(s)`：

| 模型 | 无缓存$ | 开缓存$ | 省$ | 省比例 | 触发机制 |
|---|---|---|---|---|---|
| **Gemini 3 Pro** | 0.9000 | 0.1872 | 0.7128 | **79.2%** | cached_contents |
| **Sonnet 4.5** | 2.7600 | 0.6276 | 2.1324 | 77.3% | explicit_cache_control |
| **Fable 5** | 9.2000 | 2.0920 | 7.1080 | 77.3% | explicit_cache_control |
| **GLM-5.2** | 0.5320 | 0.1360 | 0.3960 | 74.4% | auto_prefix |
| **GPT-5** | 1.2250 | 0.3340 | 0.8910 | 72.7% | auto_prefix |
| **DeepSeek V3.2** | 0.0794 | 0.0350 | 0.0444 | 55.9% | disk_kv |

数据看下来三件事：

1. **省钱比例第一名是 Gemini**——79.2%，靠的是 input × 0.10 的高折扣比 + 写入零溢价。Anthropic 两兄弟紧随其后 77.3%（输出占比稍高拉低了总比例）。
2. **省钱绝对额度第一名是 Fable 5**——单次轮询省 $7.11，每天 24 轮就是 $170/天，一年 $62k 美金。这是为什么 Anthropic 把 cache_control 做成默认推荐方案：你账单越贵，cache 收益越大。
3. **DeepSeek 省钱比例最低 55.9%，但绝对账单最低 $0.035**——它的 input 已经便宜到 cache 优化的边际收益不大。换句话说："价格更低 vs 省钱比例更高"是两个不冲突但需要分开看的指标，企业拍板时看绝对账单更稳。

### 6.1 break-even：第几次轮询开始 cache 净回本

跑 `break_even(s, p)` 给每家：

| 模型 | break-even（次） | 解释 |
|---|---|---|
| Sonnet 4.5 | 2 | 第 1 次写入溢价 0.25× input × 8000，第 2 次省 0.90× input × 8000，2 次稳赚 |
| Fable 5 | 2 | 同上 |
| GPT-5 | 2 | 写入零溢价，第 1 次持平、第 2 次开始净赚 |
| Gemini 3 Pro | 2 | 同 GPT-5 |
| GLM-5.2 | 2 | 同 GPT-5 |
| DeepSeek V3.2 | 2 | 同 GPT-5 |

**结论是惊人的统一：所有 6 家都在第 2 次轮询时回本**——这意味着只要你的同一段前缀**有大于等于 2 次**的复用，开 cache 一定划算。这个结论应该刻在每个生产 Agent 的接入手册上。

唯一的例外条件：如果你的轮询间隔 > TTL（例如 5 分钟以上还在用 Anthropic 默认模式），cache 永远都在 miss，break-even 永远到不了——这就要切到下一节的 1h TTL 模式。

## 七、实测三：Anthropic 5min × N 续命 vs 1h 一把锁

这一节是 Anthropic 用户独享的——其它四家都没有"5min 还是 1h"的选择。但它非常重要，因为很多生产场景请求间隔不是 30 秒而是 6 分钟、15 分钟、半小时（典型如：用户对话间隔、定时报表生成、跨进程的 batch 任务）。

### 7.1 间隔 = 6 分钟（5min TTL 已失效）

```python
s = Scenario(
    system_prompt_tokens=8000, user_tokens_per_call=200,
    output_tokens_per_call=200, num_calls=100,
    interval_minutes=6.0,        # > 5 min default TTL
)
```

| 策略 | 写入次数 | 写入价 | 总成本 |
|---|---|---|---|
| `5m_renew`（默认 TTL） | 100 次（每次 miss） | $3.75/M | $3.36 |
| `1h`（扩展 TTL） | 1 次 | $6/M | **$0.65** |

**1h 模式比 5m 模式省 80.7%**。原因：5m TTL 下每次都 miss，相当于关 cache；1h TTL 下 6 分钟间隔远小于 60 分钟，整个 100 次轮询只需 1 次写入，写入价虽然 2× 但绝对量极小。

### 7.2 间隔 = 30 分钟

```python
s = Scenario(num_calls=100, interval_minutes=30.0)   # 间隔 30 min
```

总跨度 = 99 × 30 = 2970 分钟 ≈ 49.5 小时

| 策略 | 写入次数 | 总成本 | vs 不开 cache |
|---|---|---|---|
| `5m_renew` | 100 次 | $3.36 | -1.2% |
| `1h` | 50 次（每 60 min 一次重写） | $1.69 | -41.0% |
| 不开 cache | - | $2.76 | 0% |

5m 模式仅比无 cache 便宜 1.2%（写入溢价吃掉了大部分收益）；1h 模式仍能省 41%。**间隔 ≥ 5min 就必须切 1h，否则不如关掉**。

### 7.3 break-even 决策表

| 请求间隔 | 推荐 TTL | 理由 |
|---|---|---|
| < 5 min（连续对话、密集 polling） | 5min default | 1h 写入溢价划不来 |
| 5 ~ 15 min（普通 IDE 助手、Agent 工具循环） | 1h | 5min 已失效，1h 一次写入划算 |
| 15 ~ 60 min（定时巡检、半小时一报） | 1h | 同上 |
| > 60 min（每小时报表、夜间 batch） | 不开 cache | 1h TTL 也跨不过去，关掉省心 |

简单决策法（[Anthropic 官方建议总结](https://docs.claude.com/en/docs/build-with-claude/prompt-caching)）：**复用间隔短于 5 分钟选默认；5 分钟到 1 小时之间选 1h；超过 1 小时不要硬开 cache，cache 只会徒增写入费。**

## 八、实测四：Tool 定义可缓存性（衔接 16 号文）

Function Calling 时代，tools 定义往往比 system prompt 还长——20 个工具、每个工具 200 token 的 schema，加起来就 4000 token。这部分能不能缓存？

### 8.1 各家的 tools 缓存能力

| 模型 | 是否支持 tools 入 cache | 注意事项 |
|---|---|---|
| Anthropic | ✅ 支持 | tools 块在请求结构里位于 `system` 之前；cache_control 打在 tools 末尾的最后一个 tool 上即可缓存整个 tools 块 |
| OpenAI GPT-5 | ✅ 自动 | tools 是 messages 之前的稳定前缀，自动入 cache |
| Gemini | ✅ 显式支持 | `cachedContents.create()` 可以同时把 `tools` 一起塞进去（[Vertex AI 官方示例](https://ai.google.dev/gemini-api/docs/caching)） |
| GLM-5.2 | ✅ 自动 | tools 视为前缀的一部分，自动隐式 |
| DeepSeek V3.2 | ✅ 自动 | tools 也是从第 0 个 token 开始的前缀 |

注意 Anthropic 的细节：cache_control 必须打在 **tools 列表里某个具体 tool 的最后一个 input_schema 字段上**，不是直接打在 tools 数组上：

```python
{
  "model": "claude-sonnet-4-5",
  "tools": [
    {"name": "get_weather", "description": "...", "input_schema": {...}},
    {"name": "send_email",  "description": "...", "input_schema": {...},
     "cache_control": {"type": "ephemeral"}}     # 标在最后一个 tool 上
  ],
  "system": "你是一个助理",
  "messages": [...]
}
```

### 8.2 实测：20 个工具 × 100 次轮询

假设 tools 总共 4000 token，system prompt 4000 token，每次 user 200 + output 300（典型 Agent 场景）。

| 模型 | 无缓存（tools + system 都重复算） | 全开 cache（tools + system 一并缓存） | 省比例 |
|---|---|---|---|
| Sonnet 4.5 | $2.92 | $0.66 | 77.4% |
| GPT-5 | $1.32 | $0.33 | 75.0% |
| Gemini 3 Pro | $1.10 | $0.21 | 80.9% |
| GLM-5.2 | $0.62 | $0.14 | 77.4% |
| DeepSeek V3.2 | $0.105 | $0.040 | 61.9% |

把 tools 一起缓存几乎是"白送的"——它本身就是稳定的、不会每次变。**16 号文给 tools schema 优化的建议（精简描述、合并相似 tool、把例子放 system 而不是 description）和这一节的 cache 优化是叠加生效的**：精简后的 tools 更短 → 写入费更低；同时被 cache 后整体省钱比例还更高。

### 8.3 tools 缓存的两个坑

1. **tools 顺序变了 cache 就 miss**。哪怕只是把第 3 个 tool 和第 5 个 tool 互换位置，前缀哈希就变了——这是为什么生产环境的 tools 列表必须按字典序或固定顺序输出。
2. **某些 router 框架会在 tools 里塞 timestamp/version**。比如自动给每个 tool 加上 `"x-version": "1.2.3"` 用来灰度，这会让 cache 永远 miss。要么把 version 字段去掉，要么放到 user message 里去。

## 九、工程落地建议：三类典型场景接入路径

### 9.1 长系统提示场景（客服 Bot / RAG / 文档 Agent）

**特征**：system_prompt 5K~30K token，每天 1k~100k 次调用，用户输入间隔 < 1 分钟。

**推荐路径**：

- **国内合规优先**：GLM-5.2 隐式自动，零代码改动开 cache（参考 13 号文 GLM-5.2 接入）
- **海外能力优先**：Sonnet 4.5 + 显式 cache_control（默认 5min），冷启动写入溢价 1 次内回本
- **极致省钱**：DeepSeek V3.2，本身价格已经低到 $0.07/M，加 cache 后再省 80%

接入代码骨架：

```python
def build_system_prompt(user_role: str) -> list[dict]:
    """user_role 是动态的，但每次都是这几个固定值之一，因此可以拼成稳定前缀"""
    return [
        {
            "type": "text",
            "text": STATIC_INSTRUCTION + ROLE_TABLE[user_role] + RAG_BASE,
            "cache_control": {"type": "ephemeral"},   # Anthropic 标这里
        }
    ]
```

### 9.2 RAG 上下文场景（每次 query 拼检索结果）

**特征**：system_prompt 短（< 1K），但每次拼 5~10K token 的检索文档；不同 query 检索结果可能完全不同。

**推荐路径**：

- **检索结果稳定的子集**（如热点 FAQ、当前产品手册）：把这部分提到 system 末尾，让 cache 命中
- **检索结果完全动态**：cache 命中率会很低（< 10%），不建议开显式 cache；但 OpenAI / 智谱 / DeepSeek 的隐式 cache 反正不要钱，开着不亏
- **复用率分布**：用 [10 号文语义缓存](./10-语义缓存命中率工程实战.md) 的"前缀复用率监控"先量化你的实际命中率，再决定是否开显式

### 9.3 Few-shot 多示例场景（编程 Agent / 代码 review）

**特征**：固定 50~100 个 few-shot 示例，每次只换最后一段代码 / 代码片段。

**推荐路径**：

- **Few-shot 部分一定要放在 prompt 最前面**，且和 user 输入用明显分隔符隔开
- **Anthropic / GPT-5 / Gemini 都支持 100-shot**，每次命中能省 90%
- **DeepSeek 64 token 起步的优势在这里很明显**——单个 few-shot 只要几百 token 也能命中

```python
prompt = [
    {"role": "system", "content": INSTRUCTION},        # 几百 token
    {"role": "user", "content": EXAMPLES_BLOCK},       # 60K token，完全静态
    {"role": "assistant", "content": EXAMPLES_OUTPUT},
    # 上面这一对在 cache 范围内
    {"role": "user", "content": ACTUAL_USER_QUESTION}, # 变化部分，放最后
]
```

### 9.4 三种场景的 cache 投入产出比

| 场景 | 静态前缀占比 | 命中率（典型） | ROI |
|---|---|---|---|
| 长系统提示 + 短 user | 90%+ | 90%+ | ★★★★★（强烈推荐） |
| RAG 动态检索 | 20%~50% | 10%~30% | ★★（看具体业务） |
| Few-shot 编程 Agent | 95%+ | 85%+ | ★★★★★ |

## 十、避坑指南

四个真实在企业里踩过的 cache 坑：

### 坑一：cache_write 重复扣费

特别是 Anthropic：5min TTL 默认是"每次命中续命"，但**如果没命中（间隔超过 5 min），下次调用是新的 cache_write，又要扣 1.25×**。生产里如果你的请求间隔抖动很大（5 min ± 2 min），就会出现"绝大多数调用都在重新写 cache"的退化。监控指标必看 `cache_creation_input_tokens / cache_read_input_tokens` 的比例——理想态 > 50:1，低于 5:1 就是 cache 没真正起作用。

### 坑二：动态 timestamp 把 cache 全打穿

最常见的事故来源。常见把 `"现在时间是 2026-06-19 14:23:45"` 拼在 system prompt 开头，导致每次 cache 都失效。**永远把动态字段放到 user message 末尾**。如果业务真需要时间感知，可以拼成 `"今天是 2026-06-19"`（精确到天，缓存命中 24 小时）或 `"现在是上午"`（精确到时段）。

### 坑三：Gemini 显式 cache 不删，按小时持续烧钱

Gemini 显式 cachedContents 按 $1/MTok·h 收存储费——一段 30K token 的 cache 留 7 天 = $5040。**用完即删**：

```python
import atexit
cache = client.caches.create(...)
atexit.register(client.caches.delete, name=cache.name)
```

或者用一个独立的 cache pool worker：每隔 1 小时扫一遍所有 active cache，TTL 到期或一段时间无引用就 delete。

### 坑四：聚合平台 / 中转层把 cache 字段吃掉

部分聚合平台为了"统一 OpenAI 协议"会把 Anthropic 原生的 `cache_control` 字段或 Gemini 的 `cached_content` 字段在转发时丢弃，结果你以为开了 cache 实际还是按 input 价收。**接入聚合平台前必须确认它的 cache 透传能力**：拿一个简单的 8000 token 系统提示连测两次，看返回的 `usage` 里是否真有 `cache_read_input_tokens`。

## 十一、决策树 + 总结

把全文压缩成一棵决策树：

```
你的同一段前缀是否会被复用 ≥ 2 次？
├── 否 → 不开 cache（永远 break-even 不到）
└── 是 → 请求间隔多大？
        ├── < 5 min → 任意厂商 default 模式
        ├── 5 ~ 60 min → Anthropic 切 1h TTL；其它家照常 default
        └── > 60 min → 不开 cache（任何 TTL 都跨不过去）

你的厂商怎么选？
├── 国内合规且想"零代码改动开 cache" → GLM-5.2 / DeepSeek V3.2
├── 海外旗舰且 ROI 至上 → Anthropic Sonnet 4.5（中等价位）/ Fable 5（绝对省钱量大）
├── Agent / 长程任务 → GPT-5（90% off + 自动）
├── 多模态 / 大文档 → Gemini 3 Pro 显式 cachedContents（注意删 cache）
```

数据看下来，2026 年中 Prompt Caching 的状况是这样的：

1. **价格机制：所有家都在 break-even = 2 次**。只要复用 ≥ 2 次，开 cache 一定划算。这是过去一年最让人安心的趋势——不再需要复杂的 ROI 测算，开就对了。
2. **省钱比例：55%~80% 区间收敛**。Gemini / Anthropic / GLM 在 75%+，OpenAI 在 72%（GPT-5 90% off 折扣 + output 占比影响），DeepSeek 因 input 已极便宜显得 56%。
3. **中国企业接入视角**：合规/网络可达性方面，GLM-5.2、DeepSeek V3.2 是国内合规一线，cache 都是隐式自动；Anthropic / OpenAI / Gemini 走聚合平台时必须重点确认 cache 字段透传。
4. **计费颗粒度**：Anthropic 公开 `cache_creation_input_tokens` 和 `cache_read_input_tokens` 两个独立字段，对账最干净；Gemini 给 `cached_content_token_count`；OpenAI 给 `prompt_tokens_details.cached_tokens`；DeepSeek 给 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`；GLM 给 `prompt_tokens_details.cached_tokens`。**生产监控里必须落这个字段，否则你不知道 cache 到底有没有真正起效**。

**一句话总结**：

> 2026 年 Prompt Caching 已经从"高级优化"降级成"默认开关"——任何复用 ≥ 2 次的前缀都该开。但五家计费机制差异 5 个数量级，TTL 选错可能不省反贵。决策三步：先测前缀复用率，再选 TTL 档位，最后让监控指标盯死 hit / miss 比。

---

## 附录 A：完整 cache_bench.py 代码说明

详细代码见 [chapters/chapter-17-prompt-cache/](./chapters/chapter-17-prompt-cache/)，主要 API：

```python
from cache_bench import (
    PriceTable, PRICE_TABLES, Scenario,
    cost_no_cache, cost_with_cache, compare_all, break_even,
)

# 1. 自定义场景
s = Scenario(
    name="我的客服 Bot",
    system_prompt_tokens=12000,
    user_tokens_per_call=300,
    output_tokens_per_call=400,
    num_calls=500,
    interval_minutes=2.0,
)

# 2. 五家横评
for row in compare_all(s):
    print(f"{row['name']}: 省 ${row['savings_usd']} ({row['savings_pct']}%)")

# 3. break-even 分析
for key, p in PRICE_TABLES.items():
    print(f"{p.name}: {break_even(s, p)} 次")

# 4. Anthropic 5min vs 1h 对比
sonnet = PRICE_TABLES["anthropic_sonnet45"]
print(cost_with_cache(s, sonnet, ttl_strategy="5m_renew"))
print(cost_with_cache(s, sonnet, ttl_strategy="1h"))
```

run 出来的结果可直接接到企业的 ROI 评审表里。代码总长 280 行（含 docstring），完全标准库依赖。

## 附录 B：原始计费回执数据（来自 §五 实测）

第 1 次冷启动 + 第 2 次命中两轮的原始 dict（真实公开格式 + mock 字段对齐）：

```python
# Anthropic Sonnet 4.5 — 第 1 次
{
    "model": "claude-sonnet-4-5",
    "usage": {
        "input_tokens": 200,
        "cache_creation_input_tokens": 8000,
        "cache_read_input_tokens": 0,
        "output_tokens": 200,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 8000,
            "ephemeral_1h_input_tokens": 0
        }
    }
}
# 计费：8000/M × $3.75 + 200/M × $3 + 200/M × $15 = $0.0336

# OpenAI GPT-5 — 第 2 次
{
    "model": "gpt-5",
    "usage": {
        "prompt_tokens": 8200,
        "completion_tokens": 200,
        "prompt_tokens_details": {"cached_tokens": 8064}    # 128 倍数取整
    }
}
# 计费：8064/M × $0.125 + 136/M × $1.25 + 200/M × $10 = $0.0033

# Gemini 3 Pro 显式 — 第 2 次
{
    "model": "gemini-3-pro-preview",
    "usage_metadata": {
        "prompt_token_count": 200,
        "cached_content_token_count": 8000,
        "candidates_token_count": 200
    }
}
# 计费：8000/M × $0.10 + 200/M × $1.0 + 200/M × $4 = $0.0019

# 智谱 GLM-5.2 — 第 2 次
{
    "model": "glm-5.2",
    "usage": {
        "prompt_tokens": 8200,
        "completion_tokens": 200,
        "prompt_tokens_details": {"cached_tokens": 8000}
    }
}
# 计费：8000/M × $0.10 + 200/M × $0.6 + 200/M × $2 = $0.0014

# DeepSeek V3.2 — 第 2 次
{
    "model": "deepseek-chat",
    "usage": {
        "prompt_tokens": 8200,
        "prompt_cache_hit_tokens": 8000,
        "prompt_cache_miss_tokens": 200,
        "completion_tokens": 200
    }
}
# 计费：8000/M × $0.014 + 200/M × $0.07 + 200/M × $1.10 = $0.0004
```

## 附录 C：参考资料

- Anthropic Prompt Caching 官方文档：<https://docs.claude.com/en/docs/build-with-claude/prompt-caching>
- Anthropic Prompt Caching 发布博客：<https://www.claude.com/blog/prompt-caching>
- OpenAI Prompt Caching 指南：<https://platform.openai.com/docs/guides/prompt-caching>
- OpenAI GPT-5 launch（GPT-5 90% off 缓存）：<https://openai.com/index/introducing-gpt-5/>
- Google AI for Developers — Context Caching：<https://ai.google.dev/gemini-api/docs/caching>
- Google AI Studio — Pricing：<https://ai.google.dev/gemini-api/docs/pricing>
- 智谱 BigModel 上下文缓存文档：<https://docs.bigmodel.cn/cn/guide/capabilities/cache>
- DeepSeek 上下文硬盘缓存文档：<https://api-docs.deepseek.com/zh-cn/guides/kv_cache/>
- DeepSeek 硬盘缓存发布通告：<https://api-docs.deepseek.com/zh-cn/news/news0802/>
- LLM API Pricing Comparison 2025（intuitionlabs PDF 综述）：<https://intuitionlabs.ai/pdfs/llm-api-pricing-comparison-2025-openai-gemini-claude.pdf>
- Spring AI Anthropic Caching 实战总结：<https://spring.io/blog/2025/10/27/spring-ai-anthropic-prompt-caching-blog/>

> 所有价格与机制截至 2026-06-19；前沿厂商定价 2~4 周内可能更新，决策落地前请以官方控制台实时显示为准。

## 附录 D：更新记录

- **v1.0** 2026-06-19 初版发布

后续如发现事实性偏差，会以本附录追加形式同步修订。

---

**相关资源**：

- [模型广场](https://activity.ldzktoken.com/activity/index.html)：[https://activity.ldzktoken.com/activity/index.html](https://activity.ldzktoken.com/activity/index.html)
  小程序"点点词元" — 多模型统一调度平台，OpenAI 兼容协议，Anthropic兼容协议。
- [GitHub 配套源码](https://github.com/fangzehui/llm-tech-articles)：[https://github.com/fangzehui/llm-tech-articles](https://github.com/fangzehui/llm-tech-articles) （含本文用到的 Prompt Cache 计费比对脚本）

*本文价格、TTL、命中机制等数据来源于各厂商官方文档与公开博客，截至 2026-06-20；具体 SKU 与计费规则请以厂商控制台实时显示为准。所有成本估算均基于公开单价 + Mock 场景计算，不包含企业大客户协议、Batch API 折扣、Off-peak 折扣等。中国企业接入路径相关内容仅作技术参考，不构成法律意见，合规落地请咨询专业法务。如发现事实性错误，欢迎评论区指正，会在附录 D 以 errata 形式同步修订。*
