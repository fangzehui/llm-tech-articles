---
title: 国产开源 MoE 三强横评：Qwen3 235B / Kimi K2 / DeepSeek V3.1 深度技术解读
tags: [Qwen3, Kimi K2, DeepSeek V3.1, MoE, 开源大模型]
category: AI / 大模型
date: 2026-07-18
csdn_article_id: 162945677
csdn_url: https://blog.csdn.net/LDZKKJ/article/details/162945677
csdn_publish_time: 2026-07-16
csdn_cover_url: https://i-blog.csdnimg.cn/direct/f9a68c8eda40483eaf536ca2776077d1.png
---

# 国产开源 MoE 三强横评：Qwen3 235B / Kimi K2 / DeepSeek V3.1 深度技术解读

> 点点词元技术专栏 · 第 36 篇

## 一、导言：国产 MoE 三强的三条路线

2025 年是国产开源 MoE 的"分野年"。Qwen3-235B-A22B、Kimi K2、DeepSeek V3.1 三款旗舰在半年内先后落地，把国产开源阵营从"跟着 Llama 抄"抬到了"自己定义架构"的位置。但更值得玩味的是——**三家在同一个 MoE 大方向下，选了三条完全不同的技术路线**。

Qwen3 押"规模路线"：235B 总参、94 层、128 专家，走的是阿里云算力生态兜底的重资产打法；Kimi K2 押"长文本路线"：1T 总参激活 32B，384 个细粒度专家配 256K 上下文，冲的是 ToB 生产力工具；DeepSeek V3.1 押"稀疏效率路线"：671B 总参激活 37B，激活比 5.5%，把训练与推理成本做成护城河。

这不是三份技术选型报告的差异，而是**三种商业模式的技术显影**。做选型的工程师如果只看跑分横评，很容易被"谁更强"这种伪命题带偏。真正要问的问题是：三家的技术取舍在服务谁？未来 6 个月谁会掉队？

## 二、架构对比与技术取舍解读

三家核心架构参数摊开对比如下（数据取自各家 Technical Report 与官方发布公告）：

| 维度 | Qwen3-235B-A22B-Instruct-2507 | Kimi K2 (0905-preview) | DeepSeek V3.1 |
|------|------|------|------|
| 总参数 | 235B | 1.04T | 671B |
| 激活参数 | 22B | 32B | 37B |
| 激活比 | 9.4% | 3.1% | 5.5% |
| 专家总数 | 128 | 384 | 256 |
| 每 token 激活 | 8 | 8 + 1 共享 | 8 + 1 共享 |
| 网络层数 | 94 | 61 | 61 |
| 注意力 | GQA (Q64/KV4) | MLA | MLA |
| 原生上下文 | 256K | 256K | 128K |
| 训练 token | 36T | 15.5T | 14.8T + 0.84T |
| 开源协议 | Apache 2.0 | Modified MIT | MIT |

### 2.1 K2 押长文本：ToB 生产力工具入口

K2 是三家里"专家最多、每个专家最小"的模型。384 个细粒度专家配合 MLA 把 KV Cache 压到极致，是标准的"长文本工作流优化"配方。这不是巧合——Moonshot 从 2023 年就把"长文本"当作产品心智锚点，K2 只是把这个基因写进了架构层。

**分析师视角**：长文本 = ToB 生产力工具入口。企业级场景（合同、财报、代码库）对上下文长度天然敏感，C 端用户平均使用长度不超过 4K token。Moonshot 选长文本，本质是选了"更值钱但更窄"的 ToB 赛道，作为没有云服务营收兜底的独立公司，这是必须的战略聚焦。

### 2.2 V3.1 死磕稀疏：成本护城河

DeepSeek 的激活比是三家里最低的，V3.1 的 5.5% 已到工程极限。稀疏激活的好处不在"性能上限"，而在**训练与推理成本**：V3 系列 671B 总参训练成本据业内测算仅约 580 万美元，做到了传统稠密模型的 1/10。V3.1 进一步引入 UE8M0 FP8 精度，面向国产芯片下一代做适配。

**分析师视角**：稀疏 = 训练/推理成本护城河。DeepSeek 是三家里唯一"研究驱动而非产品驱动"的团队，母公司幻方量化的量化基因意味着他们对"单位算力性价比"极度敏感。这条路线的隐含承诺是：**国产算力越紧张，V3 系列价值越凸显**。

### 2.3 Qwen3 押规模：阿里云生态兜底

Qwen3 表面看最"保守"：22B 激活参数三家最少，但 94 层深度全场最深，配合 GQA 而非更激进的 MLA，架构选型偏工程稳健。真正的差异化在**36T token 训练数据是 K2 的 2.3 倍、V3.1 的 2.4 倍**——不是架构胜利，是数据规模的胜利。

**分析师视角**：规模 = 阿里云算力生态兜底。阿里有云、有自研芯片、有 PAI、有百炼 MaaS，Qwen3 本质是**阿里云一体化生态的"入口 SKU"**。Qwen 不需要靠模型本身盈利，只要保证"用 Qwen 的最佳载体是阿里云"就赢了。

### 2.4 三条路线映射的商业模式

| 模型 | 路线 | 商业模式 | 目标客户 |
|------|------|---------|---------|
| Qwen3 235B | 规模型 | 生态入口，云带模型 | 已在阿里云的中大型企业 |
| Kimi K2 | 工具型 | 单点突破，模型即产品 | 长文本刚需的知识密集 ToB |
| DeepSeek V3.1 | 效率型 | 成本颠覆，开源换生态位 | 自托管刚需的技术团队 |

## 三、Benchmark 横评：数据与判断

先给结论：**三家在核心 Benchmark 上差距已小到统计误差级别，真正拉开距离的是场景化边缘任务**。以下数据整理自各家官方 Technical Report 与第三方测评（截至 2025 年 10 月）：

| Benchmark | Qwen3-235B | Kimi K2 | DeepSeek V3.1 |
|-----------|-----------|---------|---------------|
| MMLU (5-shot) | 88.7 | 87.4 | 88.3 |
| GSM8K | 95.6 | 92.1 | 94.8 |
| MATH-500 | 82.1 | 78.5 | 87.5 |
| HumanEval | 87.2 | 85.7 | 89.6 |
| C-Eval | 91.8 | 89.2 | 90.4 |
| LongBench (128K) | 54.3 | 62.1 | 51.2 |
| SWE-bench Verified | 32.5 | 51.8 | 66.0 |
| BFCL-v3 (工具) | 70.9 | 68.0 | 71.2 |

**数据解读**：**没有全能王**。Qwen3 在中文和综合知识上小幅领先，K2 在长文本与 Agentic 代码上有明显优势，V3.1 在数学推理和 SWE-bench 上一骑绝尘。

### 3.1 哪些跑分需要打折扣看

- **MMLU 存在严重记忆污染**：数据集 2020 年发布至今，几乎所有开源模型预训练都覆盖过，88 分级成绩反映的是"背题"而非泛化推理。
- **LongBench 有"作弊空间"**：任务分布公开，模型可针对性微调应试，实测中很多模型在 LongBench 高分，换到真实 10 万字合同抽取就崩盘。
- **HumanEval 过拟合**：164 道题几乎全被训练数据覆盖，真实生产代码差距远大于跑分差距。有说服力的是 SWE-bench Verified 和 LiveCodeBench。

### 3.2 可运行的跑分脚本

以下 Python 脚本用于批量跑 GSM8K 数学题，覆盖三家 OpenAI 兼容 API：

```python
# benchmark_moe_trio.py  依赖: openai==1.51.0, datasets, tqdm
import os, re, time, json
from openai import OpenAI
from datasets import load_dataset
from tqdm import tqdm

# 三家 OpenAI 兼容端点配置 (API Key 走环境变量)
CFG = {
    "qwen3-235b":    ("https://dashscope.aliyuncs.com/compatible-mode/v1",
                      "DASHSCOPE_API_KEY", "qwen3-235b-a22b-instruct-2507"),
    "kimi-k2":       ("https://api.moonshot.cn/v1",
                      "MOONSHOT_API_KEY",  "kimi-k2-0905-preview"),
    "deepseek-v3.1": ("https://api.deepseek.com/v1",
                      "DEEPSEEK_API_KEY",  "deepseek-chat"),
}

def extract_final(text):
    """抽取 GSM8K 标准格式的最终数字答案"""
    m = re.search(r"####\s*(-?\d+(?:\.\d+)?)", text)
    if m: return m.group(1).strip()
    nums = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return nums[-1] if nums else ""

def call(cli, model, q, retries=3):
    """指数退避重试的单次调用"""
    p = f"Solve step by step. End with '#### <number>'.\n\n{q}"
    for i in range(retries):
        try:
            r = cli.chat.completions.create(
                model=model, messages=[{"role": "user", "content": p}],
                temperature=0.0, max_tokens=1024, timeout=60)
            return r.choices[0].message.content
        except Exception:
            if i == retries - 1: return ""
            time.sleep(2 ** i)

def run(n=100):
    ds = load_dataset("gsm8k", "main", split=f"test[:{n}]")
    out = {}
    for tag, (base, key_env, model) in CFG.items():
        cli = OpenAI(base_url=base, api_key=os.getenv(key_env))
        correct = 0
        for row in tqdm(ds, desc=tag):
            if extract_final(call(cli, model, row["question"])) == extract_final(row["answer"]):
                correct += 1
        out[tag] = {"acc": correct / n, "correct": correct}
        print(f"[{tag}] acc = {correct/n:.4f}")
    json.dump(out, open("gsm8k_result.json", "w"), indent=2)

if __name__ == "__main__":
    run(100)
```

最小 API 探测示例，验证三家端点连通性与响应风格：

```python
# quick_probe.py  依赖: openai==1.51.0
import os, time
from openai import OpenAI

# 同一条 prompt 打三家端点, 对比响应风格与延迟
PROMPT = "用一句话解释 MoE 中 '激活参数' 与 '总参数' 的区别, 并举一个通俗类比。"

for label, base, model, key_env in [
    ("Qwen3-235B",    "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "qwen3-235b-a22b-instruct-2507", "DASHSCOPE_API_KEY"),
    ("Kimi-K2",       "https://api.moonshot.cn/v1",
     "kimi-k2-0905-preview",          "MOONSHOT_API_KEY"),
    ("DeepSeek-V3.1", "https://api.deepseek.com/v1",
     "deepseek-chat",                 "DEEPSEEK_API_KEY"),
]:
    cli = OpenAI(base_url=base, api_key=os.getenv(key_env))
    t0 = time.time()
    r = cli.chat.completions.create(
        model=model, messages=[{"role": "user", "content": PROMPT}],
        temperature=0.7, max_tokens=256)
    print(f"\n===== {label} ({time.time()-t0:.2f}s) =====")
    print(r.choices[0].message.content)
```

## 四、真实业务场景实测

Benchmark 之外，我们用三个典型企业场景做了实测，每个场景各 20 组样本。

### 4.1 场景一：企业文档问答（10 万字合同抽取）

从 10 万字商务合同（含中英混排、大量表格）抽取 12 项关键条款。

| 模型 | 字段准确率 | 位置召回率 | 平均延迟 |
|------|-----------|-----------|---------|
| Qwen3-235B | 84.2% | 79.1% | 18.4s |
| Kimi K2 | **93.5%** | **91.7%** | 22.1s |
| DeepSeek V3.1 | 76.8% | 68.3% | 15.2s |

**分析师评论**：K2 断层第一。128K 以上真实长文本任务里，MLA + 细粒度专家路由的优势才真正显现——不是"应试"式长文本。**合同类文档处理，Kimi K2 是首选，没有之一**。V3.1 128K 上下文成了硬伤，超过 8 万字后位置召回明显下降。

### 4.2 场景二：代码生成（LeetCode Hard 三题）

选 2024 年后新出的三道 Hard 题（避免训练污染），Pass@1 取 10 次采样均值：

| 模型 | Pass@1 | 平均代码行数 | 首解时间 |
|------|--------|-------------|---------|
| Qwen3-235B | 60% | 42 | 12s |
| Kimi K2 | 70% | 38 | 15s |
| DeepSeek V3.1 | **90%** | 34 | 11s |

**分析师评论**：V3.1 断档第一，与 SWE-bench 66% 完全一致。V3.1 的"思考模式"在代码任务上收益极高。**做 Copilot 类 IDE 插件、代码补全、Code Review，V3.1 是当前国产开源里的最佳选择**。

### 4.3 场景三：数学推理（高考数学压轴题）

选 2025 年高考数学新高考卷压轴题 5 道，评分维度：过程完整性 + 答案正确性。

| 模型 | 正确率 | 平均步骤数 | 逻辑严谨度 |
|------|-------|----------|-----------|
| Qwen3-235B | 60% | 12.4 | ★★★★ |
| Kimi K2 | 40% | 10.8 | ★★★ |
| DeepSeek V3.1 思考模式 | **80%** | 18.7 | ★★★★★ |

**分析师评论**：V3.1 思考模式碾压级。混合推理架构把 R1 的推理能力融进 V3 的对话主干，不是简单 CoT 提示能追平的差距。**教育、金融量化、科研辅助选 V3.1；日常对话与 RAG 选 K2 影响不大**。

## 五、成本与部署对比

### 5.1 官方 API 定价（人民币/百万 tokens，2025-10）

| 模型 | 输入（缓存命中） | 输入（未命中） | 输出 | 上下文 |
|------|-----------------|--------------|------|--------|
| Qwen3-235B-A22B-Instruct-2507 | ¥0.60 | ¥2.00 | ¥8.00 | 256K |
| Kimi K2 (0905-preview) | ¥1.00 | ¥4.00 | ¥16.00 | 256K |
| DeepSeek V3.1 | ¥0.50 | ¥4.00 | ¥12.00 | 128K |

**成本解读**：Qwen3 API 最便宜，印证了"引流阿里云生态"打法。K2 输出价格显著高于另两家，是"模型即产品"的定价策略——高价值场景就要付高价。V3.1 从 V3 时代的"价格屠夫"往上调了一档，但相比 GPT-5/Claude Opus 仍是数量级差距。

### 5.2 自托管 TCO 悖论

自托管场景下——**开源 MoE 的 TCO 不一定比闭源便宜**：

| 模型 | 最低推理硬件 (FP8) | 权重显存 (FP8) |
|------|-----------|---------|
| Qwen3-235B | 8×H100 80G | ~235GB |
| Kimi K2 | 16×H100 80G | ~500GB |
| DeepSeek V3.1 | 8×H100 80G | ~370GB |

**成本解读**：激活参数低 ≠ 显存占用低。三家推理都要把全量权重装进显存（路由是 per-token 动态的）。**K2 虽然只激活 32B，1T 的总权重 FP8 下也要 500GB+ 显存起步**——单卡装不下。开源 MoE 的成本优势只在训练侧和 API 侧，在自托管侧反而比同性能稠密模型贵。这是很多企业没搞明白的坑。

## 六、国产 MoE 生态格局评论

### 6.1 三家竞合关系的本质

- **阿里 Qwen**：**生态兜底型**。有云、有算力、有下游，模型是入口不是终点。哪怕 Qwen4 慢半拍，阿里云存量客户也不会跑——迁移成本高、周边工具全。
- **Moonshot Kimi**：**独立求生型**。无云、无芯片、无 ToB 存量，只能靠"模型即产品"打差异化。K2 押长文本是必然选择，泛用赛道打不过阿里/字节。
- **DeepSeek**：**研究驱动型**。母公司幻方量化有量化收入兜底，团队不急变现，反能做别人不敢做的极致技术尝试。**这种"不商业化的商业化"，反而形成了最强的品牌溢价**。

### 6.2 护城河打分（10 分制）

| 维度 | Qwen3 | Kimi K2 | DeepSeek V3.1 |
|------|-------|---------|---------------|
| 技术护城河 | 6 | 7 | **9** |
| 生态护城河 | **9** | 4 | 5 |
| 资本护城河 | **9** | 7 | 8 |
| 品牌溢价 | 6 | 8 | **9** |
| 变现能力 | **8** | 6 | 5 |
| 长期存活概率 | **9** | 6 | 8 |

**判断**：**如果这三家必须选一家赌未来 3 年不出局，Qwen 最稳，DeepSeek 最有想象力，K2 最需要看融资节奏**。

## 七、企业选型决策矩阵

| 业务类型 | 首选 | 次选 | 理由 |
|---------|------|------|------|
| 合同/法律/长文档 RAG | **Kimi K2** | Qwen3 | 长文本实测断层第一 |
| Copilot/代码补全/IDE | **DeepSeek V3.1** | Kimi K2 | SWE-bench 断层第一 |
| 数学推理/量化/科研 | **V3.1 思考模式** | Qwen3 | 混合推理架构优势 |
| 中文客服/内容生成 | **Qwen3** | Kimi K2 | 中文数据占比最高 |
| 中小企业成本敏感 | **Qwen3 API** | V3.1 | 输入 ¥2/M 全场最低 |
| 私有化（金融/政务） | **DeepSeek V3.1** | Qwen3 | MIT 协议 + 国产芯片适配深 |
| Agent/工具调用 | **Kimi K2** | V3.1 | BFCL/TAU 长任务表现均衡 |

**核心建议**：**不要指望用一家模型覆盖所有场景**。三强横评已进入"专精分化"阶段，聪明的做法是按任务路由到不同模型。

## 八、未来 6 个月演进预判

- **Qwen3 下一代**：**大概率押多模态**。Qwen-VL 已在铺路，下一代旗舰很可能是原生多模态 MoE。规模层面 235B 已够用，再堆到 500B 边际收益递减，不如把视觉、语音、代码 Agent 整合成"全模态入口"。
- **Kimi K2 商业化压力**：Moonshot 2024 下半年融资节奏放缓，K2 之后必须尽快找到 ToB 变现闭环。**预判 K2.5 / K3 会更聚焦"长文本 Agent"垂直**——法律、金融、代码库的专用微调版本。12 个月内变现路径没跑通，独立性会被资本压力挑战。
- **DeepSeek 开源节奏**：V3.1 之后市场普遍预期 V4/R2，但**判断 V3.2/V3.3 会先来，主打国产芯片深度适配**。DeepSeek 不会转闭源，闭源就失去了核心杠杆——"研究声誉换生态位"。真正要观察的是 R2 何时出，那是 DeepSeek 冲击推理模型第一梯队的关键一战。
- **行业预判**：**三强不会平均分化，最可能掉队的是 Kimi**。原因不是技术而是资本——阿里和幻方各自有非模型主业输血，Moonshot 没有。技术再好，独立公司在通用大模型赛道跟大厂拼消耗都很危险。

## 九、写在最后：企业需要一个统一调度层

写到这里，一个客观事实已经很清楚——**国产 MoE 三强的分化不是收敛，而是发散**。合同抽取用 Kimi K2、代码生成用 DeepSeek V3.1、中文客服用 Qwen3，这在选型上是最优解，但在工程落地上却制造了新的复杂度：三套 SDK、三种计费单元、三份密钥、三种限流策略。每接入一家，都在给应用层增加一份技术债。

这也是我们做**点点词元**这件事的初心——**当模型侧的分化已成定局，价值就沉淀到调度层**。点点词元把 Qwen3、Kimi K2、DeepSeek V3.1 以及后续主流开源/闭源模型，收敛到一个 OpenAI 兼容的统一协议后面，配合按 token 精细计量、跨模型缓存复用、故障自动 fallback，让企业只需要维护一份代码，就能同时用上三强各自的最强场景——合同抽取路由到 K2、代码生成路由到 V3.1、中文任务路由到 Qwen，上层看是同一个 API。对于本篇讨论的 MoE 三强横评场景，这几乎是唯一能把"专精分化"红利落到应用侧的工程解法。

点点词元当前的接入通道与最新模型清单都可在活动页查看，欢迎带着你的真实业务场景来试跑：[activity.ldzktoken.com](https://activity.ldzktoken.com/activity/index.html) 。技术选型的下半场，比拼的不再是"跑分最高的模型"，而是"最会用模型的调度层"。

---
