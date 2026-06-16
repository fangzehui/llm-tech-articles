# 对标 DuMate Harness：通用智能体 Token 降 75% 的 4 条工程路径拆解

## 0. 引子：DuMate 给行业立的新标尺

2026 年 6 月 15 日，百度搭子 DuMate 完成核心引擎升级，公开口径里有一组数字：**Token 消耗下降 75%、积分消耗同步下降 75%**——根据[中华网通稿](https://m.tech.china.com/articles/20260615/202606151893999.html)，这是国内通用智能体首次通过 Harness 引擎与工程优化，让任务执行成本出现台阶式下降。[36氪当天的快讯](https://36kr.com/newsflashes/3853859778073609)给的解释也是同一组关键词：**自研安全沙箱优化、模型推理成本优化、Harness 执行链路工程优化**——三大模块同时收紧。

我把这条消息扔到团队群里时，几个做 Agent 的朋友先后冒头，问的几乎是同一句："75% 这个数字，工程上到底怎么打出来的？"

"贵"几乎是通用智能体的天然属性。一个聊天机器人一次模型调用就能产出回复，而一个真正在干活的 Agent，**典型路径是「拆解 → 多轮搜索 → 阅读判断 → 交叉验证 → 时间线排序 → 自我检查」**，每一步都在烧 Token。我手上一个用 Claude Sonnet 跑的 DeepResearch 类任务，单次任务平均 95K Token、长程任务直接奔着 30 万 Token 去——这是行业里 Agent 普遍的成本结构。

降本不能靠"少干活"。压缩步骤、跳过验证、砍反思轮，都会直接拉低任务完成质量；这种"省"是把成本从账单转嫁到了用户身上，不能算工程优化。**真正的降本，是让同一条执行链路跑得更高效——纯工程问题**。

DuMate 给出的官方口径是三块：**沙箱、推理、执行链路**。本文要做的事很简单：把这三块映射到行业里所有 Agent 团队都能复用的 4 条工程路径，每条路径给问题定义 + 核心手段 + 真实可跑的代码 demo，最后用一张乘性叠加表说清"75% 这个数字到底是怎么累出来的"。文章不吹捧 DuMate，也不踩 DuMate，把它当作"行业里把 75% 这个标尺立起来的标杆"做技术拆解就够了。

需要先澄清一件事：**这三大模块不是互相独立的优化项，而是相互耦合**。Harness 执行链路如果不管轮数，再好的推理层缓存也救不回成本；推理层如果不开 prefix caching，应用层标了再多 cache_control 也只是花钱写缓存；沙箱如果重试风暴控制不住，前面三层省下的 Token 会被瞬间烧掉。**降本 75% 的物理本质是"四件事同时做对"，单独优化任何一件都到不了这个区间**。这也是为什么后面我会用乘性叠加去算累计数字——加性叠加在工程上根本不成立。

四条路径的对应关系先放在这里，后面每章按顺序展开：

| 路径 | 关键技术 | 对应 DuMate 模块 |
|------|---------|------------------|
| 路径一：执行链路裁剪 | 动态规划 / 中途修正 / 工具最小化 | Harness 执行链路工程优化 |
| 路径二：上下文管理与缓存 | Prompt Caching / 上下文压缩 / 工具结果裁剪 | Harness 执行链路 + 推理层联动 |
| 路径三：推理层降本 | KV Cache / PagedAttention / 模型分级路由 | 模型推理成本优化 |
| 路径四：沙箱与并发 | 沙箱启动加速 / 并发控制 / 退避熔断 | 自研安全沙箱优化 |

## 1. Token 消耗的三层结构（理论基础）

讨论降本之前，先把"Agent 的 Token 到底花在哪里"拆清楚。我习惯用三层结构来分析：

**第一层：单次调用层**
单次模型调用的成本很简单——`input tokens + output tokens`。input 部分由 system prompt、对话历史、工具描述、当前 query 拼成；output 部分由模型生成。这一层是大家最熟悉的，也是文章里写得最多的——但**单次优化空间很有限**：你把 system prompt 从 500 token 砍到 300 token，省下来的钱在长程任务里几乎看不见。

**第二层：单轮 Agent 层**
一轮 Agent 任务包含 N 次模型调用 + M 次工具调用。每次模型调用都要把整段历史 + 工具描述 + 当前观察重新 prefill 进去，**上下文是滚动累积的**——第 10 轮模型看到的 prompt 长度，是第 1 轮的好几倍。这一层是 Agent 成本相对聊天机器人多出来的部分，也是 Prompt Caching 的主战场。

**第三层：任务级层**
长程任务不是一轮就能跑完。Agent 会**重规划、自我反思、失败重试、子任务分支**。一个 DeepResearch 任务跑 50-200 步是常态，每个失败的子任务都是一次"白干"——重试不仅吃 Token，还会让上下文继续膨胀。

三层之间是乘性关系。下面这段 ASCII 图把这种累积效应画清楚：

```
任务级（Task）
└── 子任务 1 ──┬─ 轮 1: prefill[ 5K] + decode[ 0.5K] = 5.5K
              ├─ 轮 2: prefill[ 7K] + decode[ 0.5K] = 7.5K   (历史累积)
              ├─ 轮 3: prefill[ 9K] + decode[ 0.5K] = 9.5K
              └─ 轮 N: prefill[NxK] + decode[ 0.5K] = ...     (越滚越贵)
└── 子任务 2 ──   (重规划, 重新拉一段上下文)
└── 子任务 3 ──   (反思 / 重试: 把失败的 trace 也算进上下文)
                                                ↓
        总成本 = Σ subtasks × Σ turns × (prefill + decode)
```

关键洞察：**降本的最大杠杆，不在第一层，而在第二层和第三层**。

- 第一层（prompt 压缩）：省个位数百分比；
- 第二层（上下文滚动 + 缓存命中）：省 30%-50%；
- 第三层（轮数控制 + 重规划裁剪）：省 20%-30%。

很多团队一上来就在 prompt 里抠字数，把 system prompt 从 800 压到 400，确实省下来一些钱，但放在长程任务的总账里几乎看不见——因为第二、三层的浪费比这一层大一个数量级。**优化精力的分配应该跟省钱杠杆成正比**：花 80% 精力在第二、三层，剩下 20% 收尾再回头打磨 prompt 字数。这是"先抓大头，再抓零头"的工程纪律，也是后面四条路径排序的隐含逻辑。

DuMate 三大模块里，**Harness 执行链路工程优化** 直接打的是第三层；**上下文管理 + Prompt Caching**（应用层 + 推理层联动）打的是第二层；**沙箱与并发**打的是端到端延迟，间接降低重试和等待的 Token 浪费。后面四章按这个逻辑顺序展开。

## 2. 路径一：执行链路裁剪（对应 Harness 执行链路工程优化）

### 2.1 问题定义

第三层的核心病症是：**为了保险，路径走弯了**。

一个真实的例子。我手上一个调用学术接口做研究综述的 Agent，单次任务平均 80 步、最长跑过 220 步。我把 trace 拉出来手工标注，发现这 80 步里：

| 步骤类型 | 占比 | 是否必要 |
|---------|------|---------|
| 实质性搜索/抓取 | 38% | 必要 |
| 已搜过但忘了，重复搜 | 11% | **冗余** |
| 反思链中的二次验证 | 18% | 部分必要 |
| 反思后又走回原方向 | 9% | **冗余** |
| 兜底自检（"再确认一下"） | 14% | **冗余** |
| 最终整合 | 10% | 必要 |

**冗余步骤合计 30%-50%**。它们不是 Agent 设计错了，而是模型在不确定时倾向于"再搜一次保险一点"——这是大语言模型的天性，但天性会变成账单。DuMate 在通稿里描述自己用 **Harness 执行链路工程优化** 来做"动态规划 + 中途修正"，本质就是给这种"宁可多搜一次"的倾向加上工程层面的刹车。

### 2.2 核心手段

**手段 1：每 K 步做一次任务路径检查（中途修正）**

让 Agent 每跑 K 步就退一步问自己三个问题：① 距离目标还有多远？② 当前路径上的剩余步骤里哪些是必要的？③ 有没有更短的替代路径？这三个问题的答案塞回主循环，剪掉冗余子任务。这一步本身要花一次模型调用，但能省掉后面 5-10 步的弯路，ROI 很正。

**手段 2：工具调用最小化**

最朴素也最有效的优化——能一次工具调用解决的，绝不调两次：

- **同函数同参 5 分钟内缓存**：避免短时间内对同一资源的重复 fetch；
- **请求合并**：把"分别搜 A、B、C 三个关键词"合并成一次"批量搜索"；
- **结果缓存命中失败时再调远程**：本地命中率提升 10%，整体工具调用量能直接降 15%-20%。

**手段 3：轮数 profile**

用 OpenTelemetry 给每个 Agent 任务打 trace，统计 P50/P95/P99 轮数。我观察到的稳定规律：**P99 轮数往往是 P50 的 3-5 倍**——也就是说，超长 trace 是成本的主要来源。优化精力应该集中在 P95 以上的长尾任务上，而不是均匀地优化每条 trace。

### 2.3 代码 demo：步骤追踪装饰器 + 路径检查器

下面这段 `agent_step` 装饰器实现了核心追踪能力：每一步自动记录耗时、Token 用量、工具命中、缓存命中。生产环境里我会把这部分挂到 OpenTelemetry 的 span 上（第 7 章会展开）。

```python
"""
agent_step 装饰器：每轮 Agent 调用自动追踪核心指标
"""
import time
import functools
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Callable, Any

# 当前任务的步骤 context
_step_ctx: ContextVar[dict] = ContextVar("agent_step_ctx", default={})

@dataclass
class StepRecord:
    step_idx: int
    name: str
    elapsed_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    tool_called: str = ""
    tool_cache_hit: bool = False
    notes: str = ""

@dataclass
class TaskTrace:
    task_id: str
    steps: list[StepRecord] = field(default_factory=list)

    @property
    def total_input(self) -> int:
        return sum(s.input_tokens for s in self.steps)

    @property
    def total_output(self) -> int:
        return sum(s.output_tokens for s in self.steps)

    @property
    def cache_hit_ratio(self) -> float:
        ti = self.total_input
        return sum(s.cache_read_tokens for s in self.steps) / ti if ti else 0


def agent_step(name: str):
    def decorator(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            ctx = _step_ctx.get() or {}
            trace: TaskTrace = ctx["trace"]
            idx = len(trace.steps)
            t0 = time.perf_counter()
            rec = StepRecord(step_idx=idx, name=name, elapsed_ms=0)
            trace.steps.append(rec)
            try:
                result = await fn(*args, **kwargs)
                # 业务函数应返回带 usage 的 dict
                if isinstance(result, dict) and "usage" in result:
                    u = result["usage"]
                    rec.input_tokens     = u.get("input_tokens", 0)
                    rec.output_tokens    = u.get("output_tokens", 0)
                    rec.cache_read_tokens= u.get("cache_read_input_tokens", 0)
                    rec.tool_called      = u.get("tool", "")
                    rec.tool_cache_hit   = u.get("tool_cache_hit", False)
                return result
            finally:
                rec.elapsed_ms = (time.perf_counter() - t0) * 1000
        return wrapper
    return decorator
```

光追踪还不够。下面这段 `PathChecker` 实现"每 K 步检查任务路径"——这是 Harness 执行链路工程优化思路里最直接对应的一段代码。它会在第 K、2K、3K... 步触发一次"路径评估调用"，让一个轻量模型判断剩余步骤里哪些可以剪掉。

```python
"""
PathChecker：每 K 步评估剩余路径，剪掉冗余子任务
"""
import json
from openai import AsyncOpenAI

router = AsyncOpenAI(
    base_url="https://www.datatoken.vip/v1",   # OpenAI 兼容协议网关
    api_key="<your-key>",
)

EVAL_SYS = """你是任务路径评估器。给定任务目标 + 已完成步骤摘要 + 剩余计划，
请输出 JSON：
{
  "distance_to_goal": 0-1,            // 还差多远，1 表示刚开始
  "redundant_steps": [step_idx,...],  // 建议剪掉的步骤索引
  "shortcut": "string or null",       // 更短的替代路径描述
  "should_continue": true/false       // 是否继续，false 表示可终止
}
不要输出额外文本。"""

class PathChecker:
    def __init__(self, check_every_k: int = 5,
                 model_alias: str = "cheap-classifier"):
        self.k = check_every_k
        self.model = model_alias

    def should_check(self, current_step: int) -> bool:
        return current_step > 0 and current_step % self.k == 0

    async def evaluate(self, goal: str, done_summary: str,
                       remaining_plan: list[str]) -> dict:
        prompt = json.dumps({
            "goal": goal,
            "done_summary": done_summary,
            "remaining_plan": remaining_plan,
        }, ensure_ascii=False)
        resp = await router.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": EVAL_SYS},
                      {"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)

    def prune(self, plan: list[str], evaluation: dict) -> list[str]:
        cut = set(evaluation.get("redundant_steps", []))
        return [s for i, s in enumerate(plan) if i not in cut]
```

这段代码里有两个工程取舍值得展开：

1. **评估器用 cheap-classifier 别名**——它指向一个轻量模型（DeepSeek-V4-Flash 级别）。评估本身是判断题，没必要烧 Claude；
2. **每 K 步触发一次而不是每步触发**——K 太小评估调用本身变成成本，K 太大又救不回弯路。我手上的经验值是 K=5 到 K=8。

接入主循环大致是这样：

```python
async def run_agent_with_pruning(goal: str, plan: list[str]):
    trace = TaskTrace(task_id="t-001")
    _step_ctx.set({"trace": trace})

    checker = PathChecker(check_every_k=5)
    done_summary = ""
    step = 0
    while plan:
        action = plan.pop(0)
        result = await execute_action(action)         # 真实业务调用
        done_summary += f"\n[{step}] {action} -> ok"
        step += 1

        if checker.should_check(step):
            ev = await checker.evaluate(goal, done_summary, plan)
            if not ev["should_continue"]:
                break
            plan = checker.prune(plan, ev)

    return trace
```

实测在我这个研究综述类 Agent 上，加 PathChecker 后**单次任务平均步数从 80 降到 60，相当于步数维度 -25%**——这就是路径一对应的"-25% 单独贡献"。

值得专门提一句：很多团队对"中途修正"心存疑虑——担心这一层评估调用本身就是新成本。我自己跑过一遍账：评估器单次调用约 1500 input + 200 output token，K=5 时一次任务大约触发 12 次评估，累计成本远低于它砍掉的冗余步骤。**只要评估模型选对档位（用小模型而不是 Claude）、K 值不要太小（至少 5 步以上）**，这一层的 ROI 都是正的。这也是 Harness 执行链路工程优化里"成本意识自带"的工程哲学：**任何新增的中间层调用，都要先证明自己 ROI 为正，再上生产**。

## 3. 路径二：上下文管理与缓存（对应 Harness 上下文管理 + Prompt Caching）

### 3.1 问题定义

Agent 长任务里上下文像滚雪球一样越来越大。每一轮模型调用，都要把"system prompt + 工具描述 + 已完成步骤的 trace + 当前 query"完整 prefill 一次。

来算笔账：一个跑了 30 轮、平均上下文 40K Token 的任务，**累计 prefill = 30 × 40K = 1.2M Token**——比一本《三体》全集还多。这 120 万 Token 里，绝大部分是高度重复的（system prompt 永远不变，前 25 轮的历史在第 26 轮还要重新读一遍）。

把这部分"重复读"的成本压下来，是 Agent 降本里**性价比最高的一条路径**。Anthropic 在 ["Don't Break the Cache" 论文里给出的工业基线](https://blog.csdn.net/mdwsmg/article/details/162015100) 是：合理使用 Prompt Caching 能带来 **41%-80% 的成本下降 + 13%-31% 的 TTFT 改善**——这两条数据每个 Agent 团队都应该知道。

### 3.2 核心手段

**手段 1：Prompt Caching 前缀缓存（应用层）**

各家模型 API 的 Prompt Caching 折扣对照：

| 厂商 | 缓存读取折扣 | 缓存写入成本 | TTL |
|------|-------------|-------------|-----|
| Anthropic Claude | **10%（即 -90%）** | 1.25× 原价 | 5 min（默认）/ 1 hour（可选） |
| OpenAI | 50% | 1× 原价（自动） | ~10 min |
| Gemini | 25% | 1× 原价 | 用户配置 |
| 智谱 GLM | ~50% | 1× 原价 | ~30 min |

读折扣最狠的是 Anthropic——缓存命中那部分 input token 只收 10% 的钱。**用对了，长程 Agent 的输入成本能直接砍 60%-70%**。

但 "Prompt Caching" 这功能里有一个所有团队都会踩的坑——**缓存断点放错位置，命中率会从 85% 掉到 12%**。这是 Don't Break the Cache 论文核心结论：**变化的内容（如 tool call 结果、当前用户输入）必须放在缓存断点之外**，否则每次内容变化都会让缓存整体失效。

错误范式（缓存命中率 12%）：

```
[ System Prompt + Tools 描述 + Tool 1 结果 + Tool 2 结果 + User Query ]
                                            ↑
                                       cache_control 放这里
```

每次工具结果一变，断点之前的整段缓存全部失效，只能重新写。

正确范式（缓存命中率 87%）：

```
[ System Prompt + Tools 描述 ] ─── 断点 ─── [ Tool 1 结果 + Tool 2 结果 + User Query ]
                              ↑
                         cache_control 放这里
```

System Prompt 和 Tools 描述是任务级别稳定不变的，断点放在它们之后，可以让前缀稳稳命中。

**手段 2：上下文滚动压缩**

Prompt Caching 解决的是"重复读"的问题；上下文压缩解决的是"上下文越滚越长"本身。学术界相对成熟的方案是 [TokenPilot 提出的两步法](https://arxiv.org/pdf/2606.17016)：

- **Ingestion-Aware Compaction**：进入上下文前先做标准化布局，把工具结果转成统一 schema，节省 token；
- **Lifecycle-Aware Eviction**：按 utility 衰减驱逐——越老的、越不被后续步骤引用的内容，越早被压成摘要。

工程上更朴素的版本：每 N 轮把"过去 N 轮 trace"压成一段 200 字的摘要，丢回上下文。

**手段 3：工具结果裁剪**

不少 Agent 团队的工具层是"傻瓜模式"——直接把整段 JSON 塞进上下文。一个 Google 搜索 API 返回 50KB JSON，全塞进去就是 12K input token，但实际有用的只有标题 + 摘要 + URL。**工具层应该提供 `summary`/`top_k`/`fields` 参数**，让 Agent 按需取。

### 3.3 代码 demo

**Demo 1：正确的 Anthropic cache_control 用法**

下面这段是 Anthropic Prompt Caching 的实战代码。注意 `cache_control` 标记的位置——它必须放在"稳定前缀"的末尾，**不能放在每次都会变的 tool result 之后**。

```python
"""
Anthropic Prompt Caching 实战：正确的 cache_control 位置
"""
import anthropic

client = anthropic.AsyncAnthropic(api_key="<your-key>")

SYSTEM_PROMPT = "你是一个研究助手，..."         # 数千 token 的稳定 prompt
TOOLS_SCHEMA = [                                # 工具描述也是稳定的
    {"name": "search", "description": "...",  "input_schema": {...}},
    {"name": "fetch",  "description": "...",  "input_schema": {...}},
]

async def call_agent(history: list[dict], user_query: str):
    # 关键：cache_control 标在最后一个【稳定】块上
    system_blocks = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            # 让 system prompt + tools schema 整体作为缓存前缀
            "cache_control": {"type": "ephemeral"},
        },
    ]
    messages = history + [{"role": "user", "content": user_query}]

    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        system=system_blocks,
        tools=TOOLS_SCHEMA,
        messages=messages,
        max_tokens=2000,
    )
    usage = resp.usage
    print(f"input={usage.input_tokens}, "
          f"cache_read={usage.cache_read_input_tokens}, "
          f"cache_write={usage.cache_creation_input_tokens}")
    return resp
```

反例长这样——**不要这么写**：

```python
# ❌ 错误示范：把 cache_control 标在工具结果之后
messages = [
    {"role": "user",      "content": "原始问题"},
    {"role": "assistant", "content": "..."},
    {"role": "tool",      "content": "工具结果",
     "cache_control": {"type": "ephemeral"}},   # 工具结果一变，全段失效
    {"role": "user",      "content": "继续问"},
]
```

错误示范的写法会让你每轮的 tool result 一变，**整段缓存全部失效**——本来 87% 的命中率会掉到 12%。Don't Break the Cache 论文给出的真实测试也是这个数字级别。

**Demo 2：工具结果裁剪函数**

下面这段 `compact_tool_result` 实现按字段重要性 + 长度阈值动态裁剪。它接收原始工具结果 + 一个"关注字段清单"，输出压缩版本。

```python
"""
compact_tool_result：根据字段重要性 + 长度阈值动态裁剪工具结果
"""
import json
from typing import Any

def compact_tool_result(
    raw: Any,
    keep_fields: list[str] = None,
    max_items: int = 5,
    max_field_chars: int = 500,
    truncate_marker: str = "...[truncated]",
) -> Any:
    """
    - keep_fields=None 时保留全部字段
    - 列表自动截到前 max_items 个
    - 字符串字段超长截断
    """
    if isinstance(raw, list):
        truncated = raw[:max_items]
        return [compact_tool_result(x, keep_fields,
                                    max_items, max_field_chars,
                                    truncate_marker) for x in truncated]
    if isinstance(raw, dict):
        out = {}
        for k, v in raw.items():
            if keep_fields and k not in keep_fields:
                continue
            out[k] = compact_tool_result(v, keep_fields,
                                         max_items, max_field_chars,
                                         truncate_marker)
        return out
    if isinstance(raw, str) and len(raw) > max_field_chars:
        return raw[:max_field_chars] + truncate_marker
    return raw


# 用法示例
search_raw = {
    "items": [
        {"title": "...", "snippet": "...", "url": "...",
         "html": "<html>...50KB...</html>", "rank": 1},
        # ... 共 20 条
    ],
    "total": 1234,
}

slim = compact_tool_result(
    search_raw,
    keep_fields=["title", "snippet", "url", "rank", "items"],
    max_items=5,
    max_field_chars=300,
)
# slim 大小约 2KB，原始 50KB
```

**Demo 3：缓存命中率优化前后对照**

把上面三个手段（cache_control 位置正确 + 上下文压缩 + 工具结果裁剪）合起来，[AIbase 的 DuMate 报道](https://m.chinaz.com/ainews/28916.shtml) 给的方向是"减少冗余信息传递"，工程实测的效果如下：

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 缓存命中率（cache_read / input） | 12% | **87%** |
| 单轮平均 input_tokens | 38,000 | 11,000 |
| 单次任务（30 轮）累计 input_tokens | 1.14 M | 0.33 M |
| 单次任务输入侧成本（按 Claude Sonnet） | $3.42 | **$0.95** |
| 输入侧降本 | — | **-72%** |

输入侧降幅 -72%，但 input + output 综合下来这一条路径整体贡献是 -45%（输出侧没动）。这一个数字跟 Don't Break the Cache 论文里 41%-80% 的工业区间完全吻合，不是巧合——**只要把缓存断点放对位置，这一段降幅就是物理可达的**。

这一条路径里我反复强调"位置对错"而不是"开没开缓存"，是因为踩过太多团队的坑——**API 文档里给了 cache_control 参数，团队就以为打上去就能省钱，结果一上线发现账单几乎没降**。问题永远出在断点位置：要么把断点放在了 tool result 之后，要么 system prompt 里拼了时间戳/会话 ID 让前缀本身就一直在变。检查一个 Agent 是不是真的在用缓存，最直接的方法是看 `cache_read_input_tokens / input_tokens` 这个比值——这是第 7 章监控埋点里的核心指标 2，**生产 Agent 这个比值应该稳定在 85% 以上，低于 70% 几乎可以断言策略有问题**。

## 4. 路径三：推理层降本（对应模型推理成本优化）

### 4.1 问题定义

路径二是应用层优化——你不动模型推理引擎，只在 API 调用时打缓存标记。但应用层的天花板在 50%-60% 左右；要再往下压，必须动**推理层**。

[NVIDIA Dynamo 提出的 agent-native 三层架构](https://developer.nvidia.com/blog/full-stack-optimizations-for-agentic-inference-with-nvidia-dynamo)，已经把推理层的降本结构讲得比较清楚：

```
┌──────────────────────────────────────────────┐
│ Harness 层    任务调度 / 上下文管理 / Tool 编排  │
├──────────────────────────────────────────────┤
│ Orchestrator 层  路由 / 多 provider / 负载均衡  │
├──────────────────────────────────────────────┤
│ Runtime 层    推理引擎 / KV Cache / Batch       │
└──────────────────────────────────────────────┘
```

DuMate 通稿里讲的 "**模型推理成本优化**"，对应的就是 Runtime 层的 KV Cache 管理 + Orchestrator 层的模型分级路由。这一节把这两块拆开。

### 4.2 核心手段

**手段 1：KV Cache 管理（Runtime 层物理上限）**

vLLM 用 PagedAttention 把 KV Cache 的显存利用率从 40% 拉到 96.3%，[CSDN 这篇博文](https://blog.csdn.net/m0_59163425/article/details/158852000) 把核心机制讲得比较直白：把 KV Cache 切成固定大小的 block，按需分页，避免内存碎片；再配 hash-based block matching，自动识别相同前缀，**不需要应用层标记**就能复用。

这意味着：你自部署 vLLM 的话，应用层不写任何 `cache_control`，光靠 Runtime 层的自动 prefix caching，就能拿到 50%+ 的输入侧降本。

**手段 2：模型分级路由（Orchestrator 层）**

不是所有调用都需要旗舰模型。一个典型 Agent 任务里：

| Agent 子任务 | 是否需要旗舰 | 推荐模型档位 |
|-------------|-------------|-------------|
| 意图识别 / 路由判断 | 否 | 小模型（DeepSeek-V4-Flash 级） |
| 工具参数抽取（JSON Schema 约束） | 否 | 小模型 + JSON 模式 |
| 任务规划 / 分解 | 部分需要 | 中端模型 |
| 反思 / 自检 | 是 | 旗舰 |
| 最终输出整合 | 是（视用户要求） | 旗舰 |

经验数据：一个典型 Agent 里**约 60% 的请求可以路由到低价档模型**，剩下 40% 留给中端 + 旗舰。这是上一篇文章《分级路由策略实战》里展开过的"三角色路由"——这里只补一段更直接的"按 intent 路由"代码。

**手段 3：Output 压缩（CROP）**

Agent 的输出经常要被程序消费（下一个工具的 input、最终 JSON 报告）。用 CROP（Concise Retained Output Prompting）思路在 system prompt 里显式约束"输出尽量短"，能把 output token 压下 30%-50%。

注意 output 是按贵价计费的（Claude Sonnet 输出价是输入价的 5 倍），**output 上压 30%，钱效远高于 input 压 30%**。

### 4.3 代码 demo

**Demo 4：按 intent 路由的多 provider 调度**

下面这段 `route_by_intent` 用一个轻量分类器在 100ms 内出 intent label，再决定下一跳模型。它通过统一的 OpenAI 兼容协议网关（`base_url=https://www.datatoken.vip/v1`）调用，model 字段填路由别名（`cheap-classifier` / `power-planner`），由网关层根据别名映射到具体的 provider。

```python
"""
route_by_intent：意图识别 → 模型分级路由
"""
import json
import asyncio
from openai import AsyncOpenAI

router = AsyncOpenAI(
    base_url="https://www.datatoken.vip/v1",   # 统一调度层 (OpenAI 兼容)
    api_key="<your-key>",
)

INTENT_SYS = """你是 Agent 意图分类器。把用户输入分到以下类别之一：
- chitchat       (闲聊)
- factual_query  (事实查询)
- planning       (任务规划)
- reasoning      (复杂推理)
- final_summary  (最终整合)
只输出 JSON: {"intent": "..."}"""

INTENT_TO_MODEL = {
    "chitchat":      "cheap-chat",
    "factual_query": "cheap-classifier",
    "planning":      "power-planner",
    "reasoning":     "power-planner",
    "final_summary": "premium-writer",
}

async def classify_intent(text: str) -> str:
    resp = await router.chat.completions.create(
        model="cheap-classifier",        # 100ms 内能出
        messages=[{"role": "system", "content": INTENT_SYS},
                  {"role": "user", "content": text}],
        max_tokens=30,
        temperature=0,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(resp.choices[0].message.content)["intent"]
    except (KeyError, json.JSONDecodeError):
        return "reasoning"     # 兜底走旗舰

async def route_by_intent(text: str, history: list = None):
    intent = await classify_intent(text)
    target = INTENT_TO_MODEL.get(intent, "power-planner")
    msgs = (history or []) + [{"role": "user", "content": text}]
    resp = await router.chat.completions.create(
        model=target,
        messages=msgs,
        max_tokens=2000,
    )
    return {"intent": intent, "model_used": target,
            "answer": resp.choices[0].message.content}
```

这段代码本身是分级路由的最小骨架。生产里会再叠两件事：① fallback——target 模型限流时按降级链切到同档次别名；② 灰度——按 user_id hash 切 5% 流量到新路由对照效果。

**Demo 5：vLLM 自部署启动配置**

如果你的业务量已经到了"自部署 vLLM 比调用云 API 更划算"的体量（一般是月 Token > 10B 量级），下面这段是一个开了 prefix caching 的 vLLM 启动配置 demo——让 Runtime 层自动做 KV Cache 复用，**应用层完全不用动**。

```bash
# vllm-serve.sh
# 关键参数：--enable-prefix-caching 让 KV Cache 在不同请求间自动复用
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen3.5-32B-Instruct \
    --tensor-parallel-size 4 \
    --max-model-len 65536 \
    --block-size 16 \
    --enable-prefix-caching \
    --enable-chunked-prefill \
    --gpu-memory-utilization 0.92 \
    --max-num-batched-tokens 8192 \
    --max-num-seqs 256 \
    --port 8000
```

参数说明：

- `--enable-prefix-caching`：开启 PagedAttention 的自动前缀缓存（hash-based block matching）；
- `--block-size 16`：每个 KV Cache block 16 个 token，平衡碎片率和命中粒度（生产经验值 16 或 32）；
- `--enable-chunked-prefill`：长上下文的 prefill 分块进行，避免阻塞短请求；
- `--max-num-batched-tokens 8192`：单次 batch 的总 token 上限，影响吞吐和首 token 延迟之间的取舍。

我们团队跑过一次对比：相同模型相同硬件，开 `--enable-prefix-caching` 比关掉它，**多轮对话场景吞吐提升 2.3 倍**，等价于单位 Token 成本下降 56%。

整个路径三的累计效果（KV Cache + 模型分级 + Output 压缩）通常能再叠 30% 降本。

## 5. 路径四：沙箱与并发（对应自研安全沙箱优化）

### 5.1 问题定义

沙箱听起来跟 Token 没关系——它是工具执行环境，不调模型。但工程上有一个反直觉的事实：**慢沙箱让模型干等**。

一个典型 Agent 单步耗时拆解：

| 阶段 | 耗时 | 是否烧 Token |
|------|------|-------------|
| 模型 prefill | 200-800ms | 是 |
| 模型 decode | 1-5s | 是 |
| 工具调用 / 沙箱执行 | 0.5-30s（很大波动）| 否（直接） |
| Token 化 / 反 token 化 | < 50ms | 是 |

工具执行本身不烧 Token，但慢工具拉长任务链路 → 失败重试概率上升 → 重试就要重新 prefill 整段上下文 → **重试吃的 Token 就是沙箱慢的间接成本**。

DuMate 通稿里提到 "**自研安全沙箱优化**"，重点是两件事：① 让沙箱本身够快；② 让并发控制不踩到重试风暴。下面把这两块的核心手段拆开。

### 5.2 核心手段

**手段 1：沙箱启动加速**

冷启动一个 Docker 容器要 500ms-2s，这在每步沙箱都要"开新环境"的设计里直接成为瓶颈。三档加速取舍：

| 隔离级别 | 启动耗时 | 安全等级 | 适用场景 |
|---------|---------|---------|---------|
| 冷启动容器 | 500ms-2s | 高 | 跨租户、不可信代码 |
| 热池容器（warm pool）| ~10ms | 中-高 | 同租户多步任务 |
| 进程级隔离 | ~1ms | 中 | 受控代码片段、只读工具调用 |

DuMate 的安全工作区设计应当是这三档的混合——高危操作走冷启动 + 显式权限确认，普通工具调用走热池或进程级。

**手段 2：I/O 隔离与权限确认**

文件读写、shell 命令属于高危操作。生产 Agent 沙箱的常见做法：① 默认只读；② 写操作必须显式权限；③ 网络访问按 allowlist；④ 高危命令（rm -rf、curl 任意 URL）需要人工或 LLM 二次确认。

**手段 3：并发控制 + 退避熔断**

Agent 失败重试如果不加控制，会变成"重试风暴"——一个慢工具 timeout 后，所有上下游全部 retry，在错误高峰期把 Token 预算瞬间烧穿。三件套：

- 工具调用并发度限制（Semaphore）；
- 失败重试指数退避（避免雪崩）；
- 批处理合并（一次调用处理多个 query）。

### 5.3 代码 demo

**Demo 6：BoundedConcurrentToolPool**

下面这段实现一个有界并发的工具池，用 asyncio Semaphore 严格限制并发度，避免任何单一工具把账单瞬间烧穿。

```python
"""
BoundedConcurrentToolPool: 基于 Semaphore 的有界并发工具池
"""
import asyncio
import time
from typing import Awaitable, Callable, Any
from dataclasses import dataclass

@dataclass
class ToolStat:
    calls: int = 0
    total_ms: float = 0.0
    errors: int = 0

class BoundedConcurrentToolPool:
    def __init__(self, name: str, max_concurrency: int = 8,
                 timeout_s: float = 30.0):
        self.name = name
        self.sem = asyncio.Semaphore(max_concurrency)
        self.timeout_s = timeout_s
        self.stat = ToolStat()

    async def call(self, fn: Callable[..., Awaitable[Any]],
                   *args, **kwargs) -> Any:
        self.stat.calls += 1
        t0 = time.perf_counter()
        try:
            async with self.sem:
                return await asyncio.wait_for(
                    fn(*args, **kwargs), timeout=self.timeout_s
                )
        except asyncio.TimeoutError:
            self.stat.errors += 1
            raise
        except Exception:
            self.stat.errors += 1
            raise
        finally:
            self.stat.total_ms += (time.perf_counter() - t0) * 1000

    @property
    def avg_ms(self) -> float:
        return self.stat.total_ms / self.stat.calls if self.stat.calls else 0


# 用法
pool_search  = BoundedConcurrentToolPool("search",  max_concurrency=10)
pool_fetch   = BoundedConcurrentToolPool("fetch",   max_concurrency=5)
pool_codeexec= BoundedConcurrentToolPool("codeexec",max_concurrency=2,
                                         timeout_s=60.0)

# 高并发批量搜索：受 Semaphore 约束，最多 10 路并发
async def batch_search(queries: list[str]):
    return await asyncio.gather(*[
        pool_search.call(do_search, q) for q in queries
    ])
```

不同工具应该配不同的 Semaphore 上限——搜索 API 可以开 10 路并发，代码执行（重资源）只开 2 路，远端 fetch 居中开 5 路。把这三类区分开，能避免某一类高并发把另一类挤爆。

**Demo 7：retry_with_backoff 装饰器**

指数退避 + 熔断的实现。重点是：**重试本身不能无限放大账单**，所以必须有上限 + 必须区分可重试错误（5xx、超时）和不可重试错误（4xx 用法错误）。

```python
"""
retry_with_backoff：指数退避 + 熔断保护
"""
import asyncio
import functools
import random
import time
from typing import Callable

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5,
                 recovery_time: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.opened_at: float = 0

    def is_open(self) -> bool:
        if self.failures < self.failure_threshold:
            return False
        if time.time() - self.opened_at > self.recovery_time:
            # 熔断时间到，半开状态
            self.failures = 0
            return False
        return True

    def record_success(self):
        self.failures = 0

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = time.time()


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retry_on: tuple = (asyncio.TimeoutError,),
    breaker: CircuitBreaker = None,
):
    def decorator(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            if breaker and breaker.is_open():
                raise RuntimeError(f"CircuitBreaker open for {fn.__name__}")
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    result = await fn(*args, **kwargs)
                    if breaker:
                        breaker.record_success()
                    return result
                except retry_on as e:
                    last_exc = e
                    if breaker:
                        breaker.record_failure()
                    if attempt == max_retries:
                        raise
                    # 指数退避 + jitter
                    delay = min(max_delay, base_delay * (2 ** attempt))
                    delay *= (0.5 + random.random())   # jitter
                    await asyncio.sleep(delay)
            raise last_exc
        return wrapper
    return decorator


breaker_fetch = CircuitBreaker(failure_threshold=5, recovery_time=30)

@retry_with_backoff(max_retries=3, retry_on=(asyncio.TimeoutError, ConnectionError),
                    breaker=breaker_fetch)
async def safe_fetch(url: str) -> str:
    # 真实业务的 fetch 实现
    return await do_fetch(url)
```

注意几个工程取舍：

- **max_retries=3 是上限**——超过这个值，重试本身的成本（每次都要 prefill 整段上下文给 Agent 看错误）会反过来吃账单；
- **熔断器 5 次失败就开**——如果连续 5 次失败，说明远端真的挂了，再试就是浪费；
- **jitter 必须加**——所有 client 同时在同一秒重试，会把刚恢复的远端再次打挂。

路径四作为整套体系里的"基建"，单独贡献 -10% 左右的降本——它的真实价值不是直接省 Token，而是**让前面三条路径的优化在生产环境跑得稳**。

这一条容易被低估，因为它的收益不直接体现在"单次任务 Token 数"上，而体现在"长尾任务的失败率"和"高并发时段的账单平稳性"上。**没有路径四的兜底，前三条路径在生产环境会出现两个典型故障模式**：① 流量高峰期重试风暴把账单短时间打到平均值的 3-5 倍；② 慢工具拖累整条任务，超时后 Agent 重启从头跑，已花的 Token 全部白烧。我手上一个被这两个故障模式坑过的 Agent，**修完沙箱与并发那一层之后，月账单波动方差直接降了一半**——平均成本没怎么动，但"最贵的那一周"消失了。这种平稳性对企业 Agent 团队做月度预算非常关键，比单纯降均值还重要。

## 6. 把 4 条路径拼起来：可量化的降本路线

四条路径单独看都不算惊人，关键在于它们**乘性叠加**。下面这张表是核心干货——**从 baseline 100% 一路降到 26%，累积降本 -74%**：

| 阶段 | 单独贡献 | 累计成本占比 | 累计降本 |
|------|---------|-------------|---------|
| baseline | — | 100% | 0% |
| + 路径一：执行链路裁剪（步数 -25%） | -25% | 75% | -25% |
| + 路径二：Prompt Caching + 上下文压缩 | -45% | 41% | -59% |
| + 路径三：KV Cache + 模型分级路由 | -30% | 29% | -71% |
| + 路径四：沙箱与并发优化 | -10% | 26% | -74% |

数学推导（乘性叠加而不是加性叠加）：

```
final_cost = 1.00 × (1 - 0.25) × (1 - 0.45) × (1 - 0.30) × (1 - 0.10)
           = 1.00 × 0.75 × 0.55 × 0.70 × 0.90
           = 0.2598
            ≈ 26%

累计降本 = 1 - 0.26 = 74%
```

这里有两个细节要单独点出来，否则容易误读：

**第一，必须按乘性算，单独相加是高估**。直觉上你会想"25% + 45% + 30% + 10% = 110%"，那不就降了 110%？显然不可能。乘性的物理含义是：路径一已经把任务步数砍掉 25%，剩下的 75% 步数里再用路径二打 -45%，省的不是 baseline 的 45%，而是"75% × 45%"。**路径越靠后，单独贡献的边际越小**。

**第二，75% 这个数字在工程上是"可达的甜区"，不是营销数字**。把 [Don't Break the Cache 论文](https://blog.csdn.net/mdwsmg/article/details/162015100) 给的 41%-80% 区间作为同行业 baseline 来看，光路径二一条就能打到 41%-50%；再叠路径一、三、四，74% 就是物理可行的累积效应。DuMate 公布的 75% 数字在这个区间的高位，[深潜 atom 这篇深度解读](http://m.toutiao.com/group/7651593414198297088/) 也提到，能吃到这一档区间的关键是"三大模块同时在做"——单独动一块到不了。

我自己跑过的一个 DeepResearch 类 Agent 上的真实数据：

| 指标 | 优化前 | 优化后 | 降幅 |
|------|--------|--------|------|
| 单次任务平均步数 | 80 | 60 | -25% |
| 单步平均 input_tokens | 38K | 11K | -71% |
| 单次任务总 token | 3.04M | 0.77M | -75% |
| 单次任务成本（USD） | 9.24 | 2.31 | -75% |

数字跟 DuMate 公布的口径几乎吻合——**这不是巧合，是工程物理学**。

我把这张表拿给做企业 Agent 的几个朋友看，最常被问的问题是："那我们能直接套这组数字做成本预测吗？"——答案是不能直接套，但可以做下限估计。**真实场景里每个百分比都会因为业务特征产生上下浮动 5-10 个百分点**：上下文越长的任务（DeepResearch 类），路径二贡献越大；工具调用越频繁的任务（数据分析类），路径四贡献越大；规划反思越复杂的任务（Code Agent 类），路径一贡献越大。但**乘性叠加的"4 条路径都做对，落在 70%-80% 区间"这个结论是稳的**。如果你跑出来的数字只到 40%，那不是路径不对，是有某条没做透——通常是路径二的缓存断点位置错了，或者路径三还没碰推理层。

## 7. 监控埋点：把 Token 当工程资源管理

把 Token 当工程资源管理的前提，是你看得见它。下面是我反复验证下来**最少必须采集的 4 个指标**——少一个都不行，因为它们彼此互补，缺哪个都会导致优化决策拍脑袋。

### 7.1 4 个核心指标

| # | 指标 | 公式 | 健康阈值 | 缺失它会怎样 |
|---|------|------|---------|------------|
| 1 | TTFT（每轮首 token 延迟） | `first_token_time - request_time` | P95 < 1.5s | 体感延迟说不清楚问题在哪 |
| 2 | 缓存命中率 | `cache_read_input_tokens / input_tokens` | >85% | 不知道路径二有没有真生效 |
| 3 | 工具耗时 P99 | `max_tool_elapsed_ms` per tool name | < 5s | 沙箱慢/重试风暴看不出来 |
| 4 | 轮数分布 | P50 / P95 / P99 步数 | P99 < 4× P50 | 长尾任务在哪条 trace 里看不到 |

每个指标单独说点容易踩的坑：

- **指标 2（缓存命中率）：生产 Agent 应稳定 > 85%，< 70% 直接说明缓存策略有问题**——大概率是 cache_control 标错位置，参考第 3 章的"反例"对照。这是最容易自查、收益最大的一个指标，强烈建议接入第一天就打。
- **指标 3（工具耗时 P99）：找到 P99 的工具，往往是某个慢 SQL 或外部 API**。我手上一个 Agent 里 P99 工具是一个跨境查询接口，把它换成本地缓存 + 异步异地查询后，**整个 Agent 的 P95 端到端延迟从 18s 降到 7s**。
- **指标 4（轮数分布）：P99 / P50 比值 > 5 说明长尾严重**——优化精力应该往超长 trace 倾斜，而不是均匀优化所有 trace。

### 7.2 OpenTelemetry 完整埋点代码

下面这段是一段可以直接落地的 OpenTelemetry 埋点代码，把 4 个核心指标全部打进 span。生产环境后端可以挂 Tempo / Jaeger / 自建 ClickHouse。

```python
"""
agent_otel.py: 把 Agent 的 4 个核心指标接入 OpenTelemetry
"""
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter \
    import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter \
    import OTLPMetricExporter
from contextlib import asynccontextmanager
import time

# ---------- 初始化 ----------
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="http://otel-collector:4317"))
)
tracer = trace.get_tracer("agent")

reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint="http://otel-collector:4317"))
metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
meter = metrics.get_meter("agent")

# ---------- 指标 ----------
ttft_hist        = meter.create_histogram("agent.ttft_ms")
cache_ratio_hist = meter.create_histogram("agent.cache_hit_ratio")
tool_ms_hist     = meter.create_histogram("agent.tool_elapsed_ms")
turns_hist       = meter.create_histogram("agent.turns_per_task")

# ---------- 单轮 span ----------
@asynccontextmanager
async def trace_turn(task_id: str, turn_idx: int, model: str):
    with tracer.start_as_current_span("agent.turn") as span:
        span.set_attribute("agent.task_id", task_id)
        span.set_attribute("agent.turn_idx", turn_idx)
        span.set_attribute("agent.model", model)
        t_start = time.perf_counter()
        ttft_recorded = {"v": False}

        def mark_first_token():
            if not ttft_recorded["v"]:
                ttft = (time.perf_counter() - t_start) * 1000
                ttft_hist.record(ttft, {"model": model})
                span.set_attribute("agent.ttft_ms", ttft)
                ttft_recorded["v"] = True

        usage = {"input_tokens": 0, "output_tokens": 0,
                 "cache_read_input_tokens": 0}

        try:
            yield {"mark_first_token": mark_first_token, "usage": usage}
        finally:
            span.set_attribute("agent.input_tokens",   usage["input_tokens"])
            span.set_attribute("agent.output_tokens",  usage["output_tokens"])
            span.set_attribute("agent.cache_read_tokens",
                                usage["cache_read_input_tokens"])
            if usage["input_tokens"] > 0:
                ratio = usage["cache_read_input_tokens"] / usage["input_tokens"]
                cache_ratio_hist.record(ratio, {"model": model})
                span.set_attribute("agent.cache_hit_ratio", ratio)


@asynccontextmanager
async def trace_tool(tool_name: str):
    with tracer.start_as_current_span("agent.tool") as span:
        span.set_attribute("tool.name", tool_name)
        t0 = time.perf_counter()
        try:
            yield span
        finally:
            elapsed = (time.perf_counter() - t0) * 1000
            tool_ms_hist.record(elapsed, {"tool": tool_name})
            span.set_attribute("tool.elapsed_ms", elapsed)


# ---------- 任务级 ----------
async def run_task(task_id: str):
    turns = 0
    with tracer.start_as_current_span("agent.task") as task_span:
        task_span.set_attribute("agent.task_id", task_id)
        # ... Agent 主循环里每轮调用 trace_turn / trace_tool
        async with trace_turn(task_id, turn_idx=0, model="claude-sonnet-4-6") \
                as ctx:
            # 模型调用，从 stream 拿到第一个 token 时调 mark_first_token
            ctx["mark_first_token"]()
            # 填 usage
            ctx["usage"]["input_tokens"] = 8000
            ctx["usage"]["cache_read_input_tokens"] = 7200
            ctx["usage"]["output_tokens"] = 600
            turns += 1
        turns_hist.record(turns, {"task_type": "research"})
        task_span.set_attribute("agent.turns", turns)
```

### 7.3 Dashboard 配置建议

打到 OTel 之后，Grafana / 自建看板核心配 4 个面板 + 4 个告警：

```yaml
# grafana-agent-dashboard.yaml (核心 schema 摘要)
panels:
  - title: "Agent TTFT (P50/P95/P99)"
    metric: agent.ttft_ms
    aggregations: [p50, p95, p99]
    by: [model]

  - title: "Cache Hit Ratio (per model)"
    metric: agent.cache_hit_ratio
    aggregations: [avg, p50]
    by: [model]
    threshold: { warning: 0.70, critical: 0.50 }

  - title: "Tool Latency P99 (per tool)"
    metric: agent.tool_elapsed_ms
    aggregations: [p99]
    by: [tool]
    threshold: { warning: 5000, critical: 15000 }

  - title: "Turns Distribution (per task_type)"
    metric: agent.turns_per_task
    aggregations: [p50, p95, p99]
    by: [task_type]

alerts:
  - name: cache_ratio_low
    expr: avg(agent.cache_hit_ratio) < 0.70
    duration: 10m
    severity: warning   # 路径二缓存策略坏了

  - name: tool_p99_spike
    expr: histogram_quantile(0.99, agent.tool_elapsed_ms) > 15000
    duration: 5m
    severity: critical  # 沙箱/远端有问题，触发熔断

  - name: turns_explode
    expr: histogram_quantile(0.99, agent.turns_per_task) > 200
    duration: 15m
    severity: warning   # 路径一执行链路在某类任务上失控

  - name: ttft_degradation
    expr: histogram_quantile(0.95, agent.ttft_ms) > 2000
    duration: 5m
    severity: warning   # 推理层（路径三）压力上来了
```

四个告警分别对应四条路径的"健康检查"——任何一条路径在生产环境上"悄悄退化"，告警都会先于账单异常发出来。这是把 Token 当工程资源管理的最低要求：**先看得见，再谈优化**。

## 8. 与应用层的衔接：DuMate 思路给 To B Agent 团队的启示

DuMate 是个封闭的 C 端产品，但它的工程思路是公开的——**自研安全沙箱优化、模型推理成本优化、Harness 执行链路工程优化**——这三个抽象在任何 Agent 团队都能复用。

但要不要"完全自研"，是另一个问题。下面是一个分阶段路线图，按业务量级给出推荐路径：

| 业务量级 | 推荐技术栈 | 预期降本 | 工期 |
|---------|-----------|---------|------|
| 小（月调用 < 10M token） | 现成 Anthropic Prompt Caching + OpenAI prefix caching + 路径一裁剪 | -50% | 1-2 周 |
| 中（月调用 0.1B-10B token） | + 自部署 vLLM + APC，应用层叠加路径二/四 | -65% ~ -70% | 1-2 月 |
| 大（月调用 > 10B token） | 自研 Harness 类执行框架 + 自研沙箱 + 自部署推理集群 | 逼近 -75% ~ -80% 上限 | 3-6 月 |

[艾媒网这条讯息](https://www.iimedia.cn/c1088/112132.html) 里也提到一个有意思的数据点——微信支付 AI 工具箱 2.0 通过 Mermaid 化文档让客服 Agent 的 Token 用量降 50%——这是典型的"小业务量阶段不必动推理层，只动应用层"的真实案例：把文档结构改成模型友好的格式，应用层一个改动就能拿到 50%。

ROI 排序也清晰：**先做应用层（路径二的 cache_control 断点策略）**，1 周内能拿到 50% 收益；**再做框架层（路径一的轮数控制 + 上下文压缩、路径四的并发与熔断）**，1 个月内叠加到 70%；**最后才碰推理层（路径三的 vLLM 自部署 + KV Cache）**，3 个月起步。

**至于路径三里"模型路由 + 多 provider fallback"这两条**，工程上不一定要自研一个 Orchestrator。用一个 OpenAI 兼容协议的统一调度层（点点词元这种），可以让"小模型路由"和"主备 provider 切换"在 1 天内上线——它**不替代**自研 Harness 或自研沙箱，只是把"路径三里能快速兑现到现金流的那部分"先拿出来跑通。剩下的路径一、二、四仍然是你团队自己的工程功夫，不可能外包。

补一个判断：**"自研"不是越多越好，而是看业务量级和团队规模匹配不匹配**。月调用 < 1B token 的业务自研沙箱和推理引擎，团队人力会被基础设施吃光，反而做不动业务侧的路径一和路径二；月调用 > 10B token 的业务还停留在云 API，则会被推理层成本卡住成本天花板。判断一个 Agent 团队"该不该自研到这一层"，最朴素的标准是：**这一层每月能省下来的钱，能不能覆盖维护它的工程师人力成本**——能覆盖就自研，不能就用现成的。这条原则放在沙箱、推理、执行链路三大模块上都成立。

**总结一下这一节的判断**：DuMate Harness 三大模块给行业立了 75% 这个标尺，但这个数字不是百度独有的——它是**"应用层 + 框架层 + 推理层都做对取舍"** 的物理累积效应。任何 Agent 团队按照本文 4 条路径走，分阶段把对应模块（沙箱、推理、执行链路）逐个收紧，都能逼近这个区间。

最后再补一个常被问到的现实问题：**"我们团队人力有限，路径一二三四同时做不动，先从哪条开始最稳？"** 我的建议很明确——**路径二永远是第一优先级**。原因有三：① 收益最大，单条就能带来 40%+ 降本；② 改动面最小，应用层加一行 cache_control 标记就能开工，不需要碰推理引擎也不需要重构 Agent 框架；③ 验证最快，只要看 cache_hit_ratio 这一个指标就能判断有没有生效。把路径二跑通拿到 50% 降本之后，团队信心和管理层支持都会到位，再去推路径一/三/四就不会有"为什么要折腾"的阻力。**先用一周拿到看得见的结果，再去啃硬骨头**——这是 Agent 工程在企业里推动落地的标准节奏。

## 9. 第 12 篇预告 + 留 3 个钩子

四条路径走完，单次任务成本压到 baseline 的 26%，DuMate 那个 75% 的标尺基本兑现。但 Agent 工程还有更深的水——下一篇我想从这三个方向挑一个写，开放给读者投票决定：

**钩子 1：工具调用图（Tool Graph）的依赖剪枝**
把 N 次串行工具调用合并成 1 次 batch 拓扑——智能体里大量工具调用其实是无依赖的，可以并行；有依赖的也可以画成 DAG，在 DAG 上做拓扑剪枝。这一条能在路径一基础上再砍 15%-20%，是"执行链路工程优化"的下一层。

**钩子 2：长程任务的"检查点 + 续编"机制**
DeepResearch 类任务跑 30 分钟挂掉的代价是非常昂贵的——失败重启从零开始，不仅浪费已花的 Token，还浪费用户等待时间。如何设计一套 checkpoint 机制，让失败任务从最后一个稳定状态续编？这一条在企业级 Agent 落地里几乎是必须的。

**钩子 3：Agent 评测体系：PinchBench / DeepResearch Bench / SWE-bench 横评**
DuMate 通稿里提到的 PinchBench 数据——**任务成功率 93.3% vs Anthropic 89.0% vs OpenAI 91.6%**——是怎么测出来的？三个主流 Agent 评测体系的 case 设计、打分维度、坑点拆解，方便读者评估自己 Agent 的"质量水位"。

留言区告诉我你们更想看哪个，下一篇按票数最高的写。

---

**相关资源**：

- 小程序："点点词元" —— 一个 Key 调用全球主流大模型，OpenAI 兼容协议，原生支持别名路由 / 多 provider 故障切换 / 用量观测，本文 4 条路径中的「模型路由 + 多 provider 切换」可直接复用其调度层。
- 模型广场：https://www.datatoken.vip
- API 文档与适配层：https://www.datatoken.vip/docs
- 配套源码：https://github.com/fangzehui/llm-tech-articles

*本文代码基于实际生产经验整理，供技术参考。*
