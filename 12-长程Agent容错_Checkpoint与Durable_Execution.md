# 长程 Agent 容错设计：从 Checkpoint 到 Durable Execution 的工程实践

> 当一次 Agent 任务跑两个小时、烧掉几十次 LLM 调用、写过磁盘、调过外部 API，Worker 重启那一瞬间，你希望发生什么？

短回答：**从最近一次 checkpoint 恢复，已完成的副作用不要再触发，未完成的步骤继续往下走。**

长回答就是这篇文章要讲的事情——从 Replay Boundary 第一性原理出发，拆解 LangGraph、Temporal、Anthropic Claude Managed Agents、Microsoft Durable Task 这四个主流方案的工程做法，再到 Idempotency Key、Fork & Replay 这些容易被忽视、但真出事时救命的细节。

文中代码全部基于真实可跑的形态精简过，省略了 import 和异常处理细节，但语义保持完整。读者最好把每一段当成一个小型的工程参考实现，而不是脱敏过的伪码。

---

## 第 1 章：长程 Agent 的容错鸿沟

过去十年互联网工程师的容错肌肉记忆，是围绕**单次 RPC 思维**建起来的：一次 HTTP 请求 50 毫秒返回，超时就重试三次，重试还失败就 fallback 或者降级。这套打法到今天的长程 Agent 上完全失灵。

一个写得稍微复杂一点的 Agent 任务，会有这样的形态：

```
t = 0s     用户提交"帮我把这个 monorepo 升级到 Node 22"
t = 12s    Agent 读 README 和 package.json
t = 47s    Agent 起 sandbox，跑 npm test 建立 baseline
t = 3m20s  Agent 调 LLM 规划升级路径（一次 plan）
t = 8m15s  Agent 改 47 个文件
t = 14m02s Agent 跑测试，挂了 3 个
t = 22m47s Agent 修测试 + 二次跑测试
t = 31m10s Agent 写 PR 描述并提交
```

整整三十分钟，跨越十几次 LLM 调用、几十次工具调用、一个常驻 sandbox、磁盘上几百 KB 的 patch。中间任何一秒都可能出事——Worker 节点被 K8s 驱逐、某次 LLM 调用 timeout 重试三次仍失败、git push 卡在 TLS 握手——而**整个会话是有状态的**，不能像一个 HTTP 请求那样无脑重试。

把崩盘场景拆成三类，方便后面对症下药：

| 故障类型 | 典型场景 | 状态丢失风险 |
|---------|---------|------------|
| Worker 重启 | K8s 驱逐 / 部署滚动 / OOM | 内存里所有上下文 |
| LLM 接口异常 | 429 限流 / 502 / read timeout | 当次调用未持久化 |
| 工具网络抖动 | API 慢 / DNS 故障 / 跨区延迟 | 调用结果可能已生效但未记录 |

如果你选择最朴素的"出错就从头跑一遍"，至少要付三笔账。

第一笔是 **Token 全部重烧**。Plan 阶段已经花掉的 8000 input + 1200 output，再来一次。如果失败发生在任务尾段，重跑等于把前面所有 LLM 调用全部双倍消耗——单次任务成本被放大到原来的两倍三倍是常态，长任务更夸张。

第二笔是 **副作用重复触发**。第一次跑里已经 `git push` 的 commit、已经发出去的 webhook、已经写进数据库的订单记录，全部会重来一份。客户多收一张发票、Slack 频道连发两条同样的告警、邮件用户被 cc 两遍——这些不是程序员的浪漫，而是会真出事故的故障。

第三笔是 **用户体验断裂**。用户不知道现在是从头跑还是接着跑，三十分钟前那条进度条凭空消失。在面向终端用户的产品里，这种"Agent 自己也不记得自己干过什么"的体感，是杀死信任最快的方式。

这件事不只是工程直觉，业界态度已经表得很明确。OpenAI 主管 App Infrastructure 的 VP 在 2025 年与 Temporal 合作官宣中给了一句被反复引用的判断——"Durable Execution is a core requirement for modern AI systems"——参见 [Temporal × OpenAI Agents SDK GA 公告](https://temporal.io/blog/introducing-temporal-and-agentic-sandboxes-openai-agents-sdk)。这句话翻译成工程语言就是：把可恢复执行从"高级特性"重新分类到"基础设施"。

Anthropic 在 2026 年 4 月公开 beta 的 Claude Managed Agents，把设计目标直接写成"任务可以从分钟级跑到小时级，网络断开后自动从 checkpoint 恢复"，这是一个全托管 runtime 对长程容错的官方答卷。Microsoft 在 2026 年 4 月更新 Durable Task for AI Agents 文档时，把生产环境最常见的三道坎浓缩成 **rate limiting、network timeout、system crash**——任何想把 Agent 从 demo 推到生产的团队都绕不过这三道坎。

剩下的章节都是在回答同一个问题：**我们到底应该把状态切在哪一刀上，让恢复变成可能？**

为了让"代价"不是抽象数字，先看一张同样一个 Agent 任务在不同容错策略下的累计成本对照（按一次完整执行链路估算，仅用于直观对比，不代表任何具体厂商定价）：

| 策略 | 平均失败次数 | LLM 调用浪费倍数 | 累计 token 成本 | 累计副作用风险 | 用户体验 |
|------|-------------|-----------------|---------------|--------------|---------|
| 无容错（出错即从头跑） | 0.8 / 任务 | 1.8 倍 | 100% | 高 | 经常断 |
| 仅 L1 对话恢复 | 0.5 / 任务 | 1.4 倍 | 78% | 中 | 偶尔断 |
| L1+L2+L3 三层完整 | 0.2 / 任务 | 1.05 倍 | 60% | 低 | 几乎无感 |
| 全托管 runtime | 0.1 / 任务 | 1.02 倍 | 58% + 平台 fee | 极低 | 无感 |

成本下降的主因不是 token 单价变化，而是**失败重试时浪费的 token 总量**——容错越完整，已经花掉的 token 就越能继续利用。

---

## 第 2 章：第一性原理——Replay Boundary

容错系统设计里有一条第一性原理：**先想清楚什么能重放、什么不能重放**。

把代码切成两半：

- **可重放纯逻辑（pure / deterministic）**：相同输入永远得到相同输出，不修改任何外部世界。例如解析 JSON、构造 prompt、决定下一步该调用哪个工具。
- **不可重放副作用（side-effectful / non-deterministic）**：调 LLM、写文件、发 HTTP、读时钟、读随机数、订阅消息——重做一次结果可能不一样，或者会触发现实世界的二次变更。

这条边界叫 **Replay Boundary**。Temporal 把它编码成 Workflow / Activity 二分法，是当前 durable execution 领域最干净的抽象之一：

```
┌────────────────────────────────────────────┐
│       Workflow（确定性 / 可重放）           │
│  ─ 解析输入                                 │
│  ─ 决定调用顺序                             │
│  ─ 拼 prompt                                │
│  ─ 累加状态                                 │
│  ─ await activity_result                    │
│  禁止：time.now() / random() / 直接 RPC      │
└──────────────┬─────────────────────────────┘
               │ 通过 schedule_activity 跨界
               ▼
┌────────────────────────────────────────────┐
│       Activity（非确定性 / 真做事）          │
│  ─ 调 LLM API                               │
│  ─ 跑 shell / 执行 SQL                       │
│  ─ 发 HTTP / 写 S3                           │
│  ─ 读时钟 / 取随机数                         │
│  完成后输出会写入事件历史，下次 replay 跳过  │
└────────────────────────────────────────────┘
```

理解这条边界，先看一段**反例**。下面这种写法在 Temporal Workflow 里会直接被运行时拒绝执行，但在不少自研 Agent loop 里非常常见：

```python
# ✗ 反例：Workflow 主循环里直接调 LLM
@workflow.defn
class ResearchAgent:
    @workflow.run
    async def run(self, topic: str) -> str:
        history = []
        for step in range(10):
            # 直接在 workflow 里 await 一个 HTTP 调用
            # 重启后回放时，这次调用会重新发出
            # 而事件历史里没有它的"已完成"记录
            response = await openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": topic}],
            )
            history.append(response.choices[0].message.content)
            if "DONE" in response.choices[0].message.content:
                break
        return "\n".join(history)
```

问题在哪？Workflow 重启后，runtime 会从事件历史一条条回放，重建状态。Workflow 代码本身被假定为**纯函数**——同样的输入和事件序列，必须得到同样的执行路径。但 LLM 调用不是纯函数：第一次返回"继续搜索"、回放时可能返回"已经够了"，状态分叉、断言爆炸，整个回放机制崩溃。

正确写法是把所有副作用拆进 Activity：

```python
# ✓ 正例：把 LLM 调用包成 Activity
@activity.defn
async def call_llm(messages: list[dict]) -> str:
    """非确定的副作用，结果会写进事件历史。"""
    response = await openai.chat.completions.create(
        model="gpt-4o",
        messages=messages,
    )
    return response.choices[0].message.content


@workflow.defn
class ResearchAgent:
    @workflow.run
    async def run(self, topic: str) -> str:
        history = []
        for step in range(10):
            content = await workflow.execute_activity(
                call_llm,
                args=[[{"role": "user", "content": topic}]],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            history.append(content)
            if "DONE" in content:
                break
        return "\n".join(history)
```

差别就在第一次 `call_llm` 完成时，结果会写进事件历史。回放时 workflow 引擎看到这条 `ActivityCompleted` 事件，直接把缓存值返回给 workflow，不再发起真正的 LLM 调用。Workflow 主体仍然是纯函数，状态不会分叉。

记住这张清单——**只要踩到任何一条，就必须放进 Activity（或等价的"边界外"调用）**：

- 调用 LLM、向量库、外部 API
- 执行 shell、跑 sandbox、操作 git
- 读写文件、对象存储、数据库
- `time.now()`、`uuid4()`、`random()`
- 订阅消息队列、发邮件、发 webhook

LangGraph 把这条边界画在**节点**层面：每个 node 的入口和出口都是 checkpoint 持久化点，节点内部允许做副作用，但节点本身要能在崩溃后基于上一个 checkpoint 重新进入。Anthropic Claude Managed Agents 把边界画在 **session-hour** 计费颗粒上：sandbox 内任何副作用都通过 platform 提供的工具调用 API 走，平台负责持久化和回放。Microsoft Durable Task 走的是 fan-out / fan-in 的 task graph 模型，但本质同样是 Replay Boundary。

四套方案、四种不同的语义包装，但核心抽象只有一个——**把代码切成两半，一半负责思考、一半负责动手**。这条边界画清楚之后，下面所有章节就只是在讨论"具体怎么落地、状态存哪、key 怎么设计"这些工程问题。

实战中最容易踩坑的反而不是前面那些显式的副作用，而是一些看起来人畜无害的写法。例如在 workflow 里写 `if datetime.now().hour > 18:`，或者用 `random.choice(strategies)` 来挑当前轮的策略——这两种调用都隐含了非确定性，replay 时第一次走 if 分支、第二次走 else 分支，整个事件历史会和实际重放路径对不上。Temporal 的 SDK 会在静态扫描阶段直接报错；其他不那么严格的 runtime 上，这种坑往往要到上线半个月之后某次重启时才暴露。把"工作流里只允许出现纯逻辑"这条规则写进团队的 lint 规范，是比事后调试便宜得多的工程动作。

---

## 第 3 章：三层状态的持久化策略

长程 Agent 的状态比传统 workflow 要复杂得多，至少要拆成三层来管：

```
┌─────────────────────────────────────────────────┐
│  L1  Conversation State                          │
│      ─ messages 数组                             │
│      ─ system prompt 版本                        │
│      ─ 模型选择 / temperature                    │
│      ─ 用户 metadata                             │
└─────────────────────────────────────────────────┘
              ▲ 引用
┌─────────────────────────────────────────────────┐
│  L2  Tool State                                  │
│      ─ tool call 输入参数                        │
│      ─ tool call 输出结果                        │
│      ─ idempotency key                           │
│      ─ 重试次数 / 错误堆栈                        │
└─────────────────────────────────────────────────┘
              ▲ 描述
┌─────────────────────────────────────────────────┐
│  L3  Sandbox State                               │
│      ─ filesystem snapshot                       │
│      ─ env vars / secrets ref                    │
│      ─ 进程句柄 / port mapping                   │
│      ─ container image digest                    │
└─────────────────────────────────────────────────┘
```

**L1（Conversation State）**最小、变化最频繁。常见三种持久化策略：

- **Append-only**：每条消息直接 append 到 log，恢复时全量加载。简单但长会话内存会膨胀。
- **增量 snapshot**：每 N 条消息做一次快照，恢复时加载最近 snapshot + 增量 log。LangGraph PostgresSaver 走的就是这种。
- **每 N 轮快照 + 摘要压缩**：超过窗口时把早期消息 LLM 摘要压成一段，再存。Claude Managed Agents 的 long-context 行为本质上就是这套。

实战中常见误区是**只存 messages 不存 system prompt 版本**——一旦上线之后调过一次 system prompt，旧 session 恢复时就会用新 prompt 配合旧消息，行为会出现微妙的漂移。把 prompt 版本号一起持久化是更稳妥的做法。

**L2（Tool State）**是事故真凶最常出现的层。一次 `git_push` 的 tool call，正确做法是把**输入参数、输出结果、idempotency key、重试次数**全量记录下来，下次回放时基于 idempotency key 直接命中缓存返回，不重发副作用。如果只记输出不记输入，回放时就无从判断"这次工具调用是不是幂等命中"，等于把幂等性从代码里硬挖掉。

**L3（Sandbox State）**最重也最贵。filesystem snapshot 的常见做法：

- **OverlayFS / btrfs snapshot**：copy-on-write 文件系统，秒级快照。
- **tar + 增量 patch**：每个 checkpoint 存一个 tar，再加上自上次 checkpoint 的 diff。
- **CRIU 进程级快照**：连进程内存一起冻结，但跨架构迁移困难。

实战经验是哪一种都不完美——OverlayFS 速度快但跨节点迁移难，tar 通用但每次写盘重，CRIU 进程级保留运行态但对内核版本敏感。比较稳妥的折中是"应用级状态用 PostgreSQL 持久化，sandbox 文件系统用 OverlayFS 快照，进程态尽量不依赖运行时内存"——把状态尽量从进程里挤出来，是让 sandbox 容易复制、容易迁移的根本手段。

接着是后端选型，这是被问得最多的问题：

| 后端 | 适用场景 | 写延迟 | 成本特征 | 失效风险 |
|------|---------|-------|---------|---------|
| MemorySaver | 开发 / 单元测试 | <1ms | 0 | 进程重启即丢 |
| SQLite | 单机低并发 / 边缘部署 | 1-5ms | 磁盘 IO | 跨机不可共享 |
| PostgreSQL | 生产多租户 / 一致性强 | 5-20ms | DB 实例 + 连接池 | 长事务热点 |
| Redis | 高吞吐短生命周期 | <1ms | 内存为主 | 落盘策略需谨慎 |
| S3 / GCS | 历史归档 / 大附件 | 50-500ms | 极低 / 按用量 | 不适合热路径 |

实战经验是**分层使用**：热数据放 Redis（最近 5 分钟内活跃 session 的 working memory），温数据放 PostgreSQL（事件历史 + tool state），冷数据归档到 S3（关闭超过 24 小时的 session 整体打包）。Anthropic Claude Managed Agents 内部据现有公开材料推断也是类似分层；Temporal 的 history persistence 默认走 Cassandra / PostgreSQL，archival 走 S3。

[Zylos 关于 durable execution agent runtimes 的对比研究](https://zylos.ai/research/2026-04-24-durable-execution-agent-runtimes) 给了一份 2026 年的 runtime 横评，结论之一就是"L1+L2+L3 三层都管的 runtime，比只管 L1 的高一个量级"。这个判断非常准确——只在对话层做 checkpoint，等于完全不管工具的副作用幂等，也不管 sandbox 文件系统恢复，看起来"能恢复对话"但其实只恢复了三分之一。

实际选型时还有一个常被忽视的维度：**checkpoint 写入频率**。写得太频繁，单 session 平均要承担几百次小写，对 PostgreSQL 是 IO 灾难；写得太稀疏，恢复粒度变粗，重做的部分就更多。一个折中策略是按"语义事件"写——LLM 调用前后、工具调用前后、节点切换时，这些是天然的语义边界。其他时间不写。把 checkpoint 写入做成异步刷盘（先写内存，N 个 checkpoint 后批量落库），还能进一步把 P99 写延迟从十几毫秒压到一毫秒以内。

---

## 第 4 章：Checkpoint 模式 1——LangGraph PostgresSaver 实战

LangGraph 是 LangChain 团队 2024 年推出的 graph-based agent runtime，走的是**节点边界 = replay 边界**这条线。开发体验偏轻量，特别适合从 LangChain 已有代码升级到长程 Agent。

先看最小可运行的 PostgresSaver 配置：

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from typing import TypedDict, Annotated
import operator

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]  # reducer 自动累加
    plan: str
    files_changed: list[str]
    tests_passed: bool

DB_URI = "postgresql://agent:secret@db.internal:5432/checkpoints?sslmode=require"
checkpointer = PostgresSaver.from_conn_string(DB_URI)
checkpointer.setup()  # 建表 + 索引，幂等
```

`PostgresSaver.setup()` 会创建三张表：`checkpoints`、`checkpoint_blobs`、`checkpoint_writes`。`checkpoints` 表的主键是 `(thread_id, checkpoint_ns, checkpoint_id)`，对长程 Agent 意味着——**`thread_id` 就是任务的全局唯一标识**，设计时应当把它和业务系统的 task_id 强绑定，而不是用临时 UUID。

接下来是节点函数和图结构。每个 node 入口和出口都会写一次 checkpoint：

```python
def plan_node(s: AgentState) -> AgentState:
    plan = llm.invoke(f"为以下任务做计划: {s['messages'][-1]}")
    return {"plan": plan, "messages": [{"role": "assistant", "content": plan}]}

def edit_node(s: AgentState) -> AgentState:
    return {"files_changed": apply_patches_from_plan(s["plan"])}

def test_node(s: AgentState) -> AgentState:
    return {"tests_passed": run_pytest()}

def fix_node(s: AgentState) -> AgentState:
    fix = llm.invoke(f"测试失败，请修复: {s['plan']}")
    return {"plan": fix, "messages": [{"role": "assistant", "content": fix}]}

def review_node(s: AgentState) -> AgentState:
    review = llm.invoke(f"对修改进行 self-review: {s['files_changed']}")
    return {"messages": [{"role": "assistant", "content": review}]}

g = StateGraph(AgentState)
for name, fn in [("plan", plan_node), ("edit", edit_node), ("test", test_node),
                 ("fix", fix_node), ("review", review_node)]:
    g.add_node(name, fn)
g.set_entry_point("plan")
g.add_edge("plan", "edit")
g.add_edge("edit", "test")
g.add_conditional_edges(
    "test",
    lambda s: "review" if s["tests_passed"] else "fix",
    {"review": "review", "fix": "fix"},
)
g.add_edge("fix", "test")
g.add_edge("review", END)

graph = g.compile(checkpointer=checkpointer)
```

接下来看**中断恢复**——这是 LangGraph 设计里最优雅的一段。第一次启动和恢复使用同一个 API：

```python
config = {"configurable": {"thread_id": "pr-review-2026-04-29-7"}}

# 首次启动
result = graph.invoke(
    {"messages": [{"role": "user", "content": "审查 PR #482"}]},
    config=config,
)

# 如果 worker 在 test_node 跑到一半被驱逐——
# 重新调度到新 worker 上时，传 None 即可继续：
result = graph.invoke(None, config=config)
```

LangGraph 会查 `checkpoints` 表里 `thread_id="pr-review-2026-04-29-7"` 的最新一条记录，把状态加载回来，从最近成功完成的节点的下一条边开始重放。已经写入的 `plan` 不会重新生成，已经修改的文件不会再次 patch。

但有个**节点内幂等**的责任在用户身上——如果 `edit_node` 跑到一半挂掉（已经改了 30 个文件，剩 17 个没动），LangGraph 不会从"第 31 个文件"接着跑，而是会**整个重跑 `edit_node`**。这意味着 `apply_patches_from_plan` 必须自己实现幂等：要么基于 file hash 跳过已修改文件，要么把 patch 做成原子事务（比如先写到临时分支，整体成功后再 merge）。这条原则在做 LangGraph 设计评审时一定要明确写进 checklist——节点切得越细，节点内逻辑越简单，幂等责任就越容易兑现。

[CallSphere 关于 LangGraph Checkpointer 在生产环境实践](https://callsphere.ai/blog/langgraph-checkpointer-durable-resumable-agents) 给了一段精炼的总结："节点边界 = 持久化边界，节点内部副作用必须幂等"——这句话值得贴在 PR review checklist 里。

实战中还有一条容易被忽视的细节：**节点的颗粒度直接决定了恢复时的浪费规模**。把一个节点写得过粗（比如把 plan、edit、test 全塞在一个 node 里），任何一处崩溃都会把前面已经做过的事重做一遍；写得过细（每行都拆成节点），checkpoint 表又会爆炸式增长，PostgreSQL 的写压力顶不住。常见的折中标准是：**每个节点的预期执行时间在 30 秒到 5 分钟之间**——既不会让恢复浪费太多，也不会把 checkpoint 频率推到数据库压力红线。

LangGraph 还内置了 **Time Travel** 和 **Interrupt** 两套机制，能力非常强：

```python
# 列出某 thread 的所有历史 checkpoint
history = list(graph.get_state_history(config))

# 从中间某个 checkpoint 派一个新分支
fork_config = {"configurable": {
    "thread_id": "pr-review-2026-04-29-7",
    "checkpoint_id": history[3].config["configurable"]["checkpoint_id"],
}}
result = graph.invoke({"messages": [{"role": "user", "content": "改保守方案"}]}, fork_config)

# 在写文件前停住，等人审
graph_with_interrupt = g.compile(checkpointer=checkpointer, interrupt_before=["edit"])
```

这两个能力在第 8 章会专门展开。在工程实践里，Time Travel 配合 Interrupt 可以撑起一类很特别的产品形态——**人在环路中的 Agent**：Agent 推进到关键决策点先停住，等人确认或者修正参数后再继续。这种形态在合规要求高的场景（金融审批、医疗诊断辅助、代码 deploy）几乎是刚需。

LangGraph 的工程定位很清晰：**单进程内的 graph 编排 + 持久化插件**。如果你的 Agent 不需要跨服务编排、不需要严格的 SLA、对 LangChain 生态友好，PostgresSaver 已经能解决八成问题。但如果你要跨多个 worker、多个数据中心、和现有 BPM 系统对接——下一章的 Temporal 是更稳妥的选择。

---

## 第 5 章：Checkpoint 模式 2——Temporal Workflow + Activity 拆分

Temporal 是从 Uber Cadence 演化而来的开源 durable execution 平台，2026 年初 Multi-Region Replication GA、官方给到 99.99% SLA。2026 年 3 月与 OpenAI Agents SDK 完成深度集成，[Temporal × OpenAI 官宣公告](https://temporal.io/blog/introducing-temporal-and-agentic-sandboxes-openai-agents-sdk) 是这一年里 agent infrastructure 领域最重要的几个里程碑之一。

Temporal 的核心抽象就是上一章讲的 Workflow（确定性）+ Activity（非确定性）二分。但它在工程化上做了非常多脏活——事件历史、版本化、多语言 SDK、可视化、Replay 调试器——把 durable execution 做成一个工程师真的敢往生产部署的形态。

下面用一个完整的研究 Agent 演示，三个步骤：search → analyze → write_report。先看 activities 这一侧（副作用全部在这一层）：

```python
from temporalio import activity
from datetime import timedelta

@activity.defn
async def web_search(query: str, max_results: int = 10) -> list[dict]:
    """调外部搜索 API，结果可能因时间变化。"""
    activity.heartbeat(f"searching: {query}")
    results = await search_provider.search(query, k=max_results)
    return [{"url": r.url, "title": r.title, "snippet": r.snippet} for r in results]

@activity.defn
async def llm_analyze(query: str, sources: list[dict]) -> dict:
    """让 LLM 分析搜索结果，提取关键论点。"""
    response = await llm_client.chat(
        model="claude-sonnet-4",
        messages=build_analyze_prompt(query, sources),
    )
    return {"key_points": response.parse_json(), "tokens": response.usage}

@activity.defn
async def llm_write_report(query: str, analysis: dict) -> str:
    response = await llm_client.chat(
        model="claude-opus-4",
        messages=build_report_prompt(query, analysis),
    )
    return response.text

@activity.defn
async def upload_to_s3(report: str, key: str) -> str:
    await s3_client.put_object(Bucket="agent-reports", Key=key, Body=report)
    return s3_client.generate_presigned_url(
        "get_object", Params={"Bucket": "agent-reports", "Key": key}
    )
```

再看 workflow 这一侧（纯逻辑、确定性）：

```python
from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta

@workflow.defn
class ResearchWorkflow:
    @workflow.run
    async def run(self, query: str) -> str:
        sources = await workflow.execute_activity(
            web_search, args=[query, 10],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=30),
                maximum_attempts=5,
                non_retryable_error_types=["ValueError"],
            ),
        )
        await workflow.wait_condition(lambda: len(sources) > 0)

        analysis = await workflow.execute_activity(
            llm_analyze, args=[query, sources],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        report = await workflow.execute_activity(
            llm_write_report, args=[query, analysis],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        # workflow.now() 是确定的，replay 时返回原值
        report_key = f"reports/{workflow.now().isoformat()}-{workflow.info().workflow_id}.md"
        return await workflow.execute_activity(
            upload_to_s3, args=[report, report_key],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )
```

启动 worker 是几行常规代码：`Client.connect` 拿到 client，`Worker(client, task_queue=..., workflows=[ResearchWorkflow], activities=[...])` 注册后 `worker.run()` 就跑起来了。触发任务用 `client.start_workflow(ResearchWorkflow.run, query, id="...", task_queue="research-agents")` 拿到 handle，再 `await handle.result()` 等结果，整体形态和写一段普通的 async 函数没本质差异。

回到容错——**worker 在 `llm_analyze` 跑到一半被驱逐时会发生什么**？

第一步：Temporal 服务端检测到 worker heartbeat 丢失（默认 60 秒超时）。
第二步：该 activity task 被重新放回 task queue。
第三步：任意一个空闲 worker pickup 这个 task，重跑 `llm_analyze`。
第四步：重跑成功后写入事件历史。
第五步：Workflow 主体感知到 activity 完成，继续往下走 `llm_write_report`。

**已完成的 `web_search` 不会重跑**——因为它的输出已经在事件历史里。如果整个 worker 都挂了，连 workflow 任务也被 reschedule，新 worker 会从事件历史的第一条开始 replay，replay 到 `web_search` 时直接读缓存，replay 到 `llm_analyze` 时发现没完成才真正发起调用。

这就是 Temporal 模型的迷人之处：**Workflow 代码看起来像同步的、像顺序的、像没有任何容错代码——但底层引擎在每一个 await 点都做了 checkpoint**。开发者写的是业务逻辑，runtime 给的是工业级 durability。

99.99% SLA 折成单年是 52.6 分钟不可用，对绝大多数 Agent 业务足够。Multi-Region Replication GA 之后，活动 cluster 整个挂掉时，请求会自动切到备份 region 继续 replay，对长程任务尤其重要——一个跑了两小时的 Agent 不会因为单 region 故障重头来。

[Zylos 关于 agent workflow orchestration patterns 的研究](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns) 把 Temporal 模式归到"trust in event sourcing"这一派，和 LangGraph 的"trust in checkpointing"形成互补。两者并非二选一——业内常见做法是上层用 LangGraph 做 graph 编排，底层关键节点用 Temporal Activity 包一层，把图状态语义和事件溯源能力一起拿到。

---

## 第 6 章：Anthropic Claude Managed Agents 内置 Checkpoint 拆解

Anthropic 在 2026 年 4 月 8 日公开 beta 的 Claude Managed Agents 是一个**全托管 agent runtime**——你不再自己管 worker、不再自己写 checkpoint、不再自己跑 sandbox，平台把这一切打包成一组 SDK 原语。

它的核心设计是三大能力的组合，缺一不可：

```
┌─ Claude Managed Agents ────────────────┐
│  ① sandboxed execution                 │
│     每 session 独立 sandbox / 文件隔离   │
│     网络出站默认走白名单                 │
│  ② automatic checkpointing             │
│     工具调用前后自动 snapshot            │
│     网络断开后从 checkpoint 自动恢复     │
│     idle 期间不计费                      │
│  ③ scoped permissions                  │
│     工具粒度 ACL                        │
│     网络出站域名白名单                   │
│     文件系统挂载点限制                   │
└────────────────────────────────────────┘
```

计费模型也直白：

- **Token 标准价**：和直接调 Claude API 一致，不打折也不加价。
- **Session-Hour**：$0.08 / session-hour，**仅在 session 处于"活动"状态时计费**，idle（等待用户输入、等待外部 webhook）期间不计费。
- 任务设计目标：分钟到小时级，长任务相对自建 sandbox 在运维成本上有优势。

来看一段完整的 Python SDK 用法。下面这段代码涵盖创建 session、提交任务、网络断开、resume from checkpoint、追加新任务的完整链路：

```python
from anthropic import Anthropic
import time

client = Anthropic()

# 1. 创建 managed agent session（含权限和 sandbox 配置）
session = client.beta.managed_agents.sessions.create(
    model="claude-sonnet-4-5",
    name="repo-upgrade-2026-04-29",
    permissions={
        "tools": ["bash", "file_edit", "git"],
        "network_allowlist": ["registry.npmjs.org", "github.com", "api.github.com"],
        "filesystem_mounts": [
            {"path": "/workspace", "mode": "rw"},
            {"path": "/etc", "mode": "ro"},
        ],
    },
    sandbox={"image": "anthropic/agent-node22:latest", "cpu": 2, "memory_gb": 4},
)

# 2. 提交第一个任务
turn1 = client.beta.managed_agents.sessions.runs.create(
    session_id=session.id,
    input=[{"role": "user", "content": "把 /workspace 升级到 Node 22 后提 PR"}],
)
print(f"run_id: {turn1.id}, checkpoint_id: {turn1.checkpoint_id}")

# 3. 模拟网络中断 60 秒，客户端这一侧 lost connection
time.sleep(60)

# 4. 重新连接，查询当前状态
state = client.beta.managed_agents.sessions.retrieve(session.id)
# 状态: running / paused_idle / paused_checkpoint / completed / failed

# 5. 如果 paused_checkpoint，主动 resume
if state.status == "paused_checkpoint":
    client.beta.managed_agents.sessions.resume(
        session_id=session.id,
        from_checkpoint=state.last_checkpoint_id,
    )

# 6. 追加新任务，session 上下文继承
turn2 = client.beta.managed_agents.sessions.runs.create(
    session_id=session.id,
    input=[{"role": "user", "content": "PR 里再加一段 CHANGELOG.md"}],
)

# 7. 流式读取事件
for event in client.beta.managed_agents.sessions.runs.stream(
    session_id=session.id, run_id=turn2.id,
):
    if event.type == "tool_call":
        print(f"  tool: {event.tool}")
    elif event.type == "checkpoint_created":
        print(f"  ✓ checkpoint {event.checkpoint_id}")

client.beta.managed_agents.sessions.close(session.id)
```

工程上几个值得注意的点：

**checkpoint 是显式 ID**。每个 `tool_call` 完成后会拿到一个 `checkpoint_id`，客户端可以记下来用来 fork（参见第 8 章），也可以用来 time travel。这一点和 LangGraph 的"内部递增 ID"不一样——Anthropic 把 checkpoint 当作一等公民暴露给开发者，意味着客户端有能力做更细粒度的状态管理。

**idle 不计费**。这意味着你可以让一个 session 等用户审批好几个小时——比如 PR 审查 Agent 在 `git push` 前停下来等人 review，这段等待时间只有 token 没花，session-hour 不计——**前提**是 sandbox 进入 idle 状态而非 active execution。这条规则对面向终端用户、有大量"等审"环节的产品形态非常友好。

**permission 是一等公民**。`network_allowlist` 不是建议，是硬约束；Agent 试图访问 allowlist 之外的域名会直接报错，连 LLM 都看不到响应——这是和自建 sandbox 最大的区别之一。Microsoft Durable Task for AI Agents 在 [官方文档](https://learn.microsoft.com/azure/durable-task/sdks/durable-task-for-ai-agents) 里给的设计建议也是类似——"工具调用 + 权限 + 持久化"应当是一组原子能力。

[ClaudeLab 的 Managed Agents 实战指南](https://claudelab.net/en/articles/api-sdk/claude-managed-agents-complete-guide-2026) 给了一个观察：从 2026 年起，**Sandbox + Checkpoint + Permission 打包成单一原语**会成为大部分 agent platform 的标准动作。Anthropic 走在前面，OpenAI 走 Temporal 集成路线，Microsoft 走 Durable Task 路线，但抽象指向同一件事——开发者不应该自己实现 checkpoint。

工程启示也清楚：

- 如果你的 Agent 重度依赖 Anthropic 模型，且不需要跨 cloud 编排，Managed Agents 几乎可以省掉所有自建运维。
- 如果你需要混合多家模型 / 跨 cloud / 接现有 BPM 系统，仍然回到 Temporal + 自建 sandbox 路线。
- 中间地带是把 Managed Agents 当作"强力 Activity"用——Temporal Workflow 调度多个 Managed Agents session 完成一个大任务的不同子目标。

具体到团队迁移成本，这里有一个常被低估的现实：**自建 Agent runtime 的运维负担在长任务场景下是非线性增长的**。短任务可能只需要一台 worker 配一个数据库就够；任务一旦拉到一小时以上，就要面对 sandbox image 缓存、状态存储分层、跨 region 容灾、版本升级回滚这些课题。全托管 runtime 的价值不在于功能强、而在于**把运维复杂度抹平**——团队规模小或 Agent 不是核心竞争力的产品，把这部分外包给平台，把工程精力投回业务逻辑，是一个更经济的选择。这不是说自建一定亏、托管一定赚，而是要用业务规模和 SLA 要求倒推合理的边界。

---

## 第 7 章：Idempotency Key 与重复触发防护

Replay 和 Retry 解决的是"状态如何恢复"，但留下了另一个问题：**重做一次的副作用怎么办**？

举个具体场景：Agent 调用 `create_invoice` 工具开了一张 1000 元的发票，平台返回 200，但响应在网络抖动里丢了，Agent 这边 timeout，重试逻辑触发，第二次调用又开了一张 1000 元的发票——客户多收了一张。

这不是 Agent 独有的问题。Stripe 早在 2016 年就把 [Idempotency-Key header 模型](https://docs.stripe.com/api/idempotent_requests) 做成业内幂等标准：每个会改变状态的 API 请求带一个 client 生成的 unique key，服务端基于这个 key 做去重，相同 key 的重复请求返回首次结果而不重新执行。

长程 Agent 里幂等需要做三层：

```
L3 业务系统原生（最强保证）  Stripe / 内部 ledger 服务的 idempotency-key
L2 应用层 cache（最常见兜底） Redis / Memcached 装饰器统一处理
L1 API gateway（粗粒度）      Kong / Envoy / 自研网关层默认要求带 key
```

最常用的是 L2——一个**幂等中间件装饰器**，包在所有副作用工具上。下面是一段完整可跑的实现：

```python
import asyncio, hashlib, json, functools
from typing import Callable, Any
import redis.asyncio as redis

REDIS = redis.Redis.from_url("redis://cache.internal:6379/0", decode_responses=True)

class PermanentError(Exception):
    """业务层判断为不可重试的错误，例如参数非法。"""

def _normalize(v: Any) -> Any:
    if hasattr(v, "isoformat"): return v.isoformat()
    if hasattr(v, "__dict__"):
        return {k: _normalize(getattr(v, k)) for k in v.__dict__}
    return v

def _stable_hash(*args, **kwargs) -> str:
    """对参数做稳定序列化 + sha256，得到与调用顺序无关的 key。"""
    payload = {
        "args": [_normalize(a) for a in args],
        "kwargs": {k: _normalize(v) for k, v in sorted(kwargs.items())},
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

def idempotent(namespace: str, ttl_seconds: int = 86400, key_builder=None):
    def deco(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            key_part = key_builder(*args, **kwargs) if key_builder else _stable_hash(*args, **kwargs)
            cache_key = f"idem:{namespace}:{key_part}"

            # 1. 查缓存
            cached = await REDIS.get(cache_key)
            if cached is not None:
                payload = json.loads(cached)
                if payload["status"] == "ok":
                    return payload["result"]
                if payload["status"] == "fail" and payload.get("permanent"):
                    raise RuntimeError(payload["error"])

            # 2. 标记 in-flight，防止并发重复触发
            lock_key = f"{cache_key}:lock"
            if not await REDIS.set(lock_key, "1", nx=True, ex=300):
                # 其他实例正在跑，轮询等待
                for _ in range(60):
                    cached = await REDIS.get(cache_key)
                    if cached is not None:
                        return json.loads(cached)["result"]
                    await asyncio.sleep(0.5)
                raise TimeoutError("waiting for in-flight idempotent call")

            # 3. 真正执行并写缓存
            try:
                result = await fn(*args, **kwargs)
                await REDIS.set(
                    cache_key,
                    json.dumps({"status": "ok", "result": result}, default=str),
                    ex=ttl_seconds,
                )
                return result
            except PermanentError as e:
                await REDIS.set(
                    cache_key,
                    json.dumps({"status": "fail", "error": str(e), "permanent": True}),
                    ex=ttl_seconds,
                )
                raise
            finally:
                await REDIS.delete(lock_key)
        return wrapper
    return deco
```

使用起来非常清爽：

```python
@idempotent(namespace="invoice", ttl_seconds=7 * 86400)
async def create_invoice(customer_id: str, amount: float, currency: str = "CNY") -> dict:
    response = await billing_api.post("/invoices", json={
        "customer": customer_id, "amount": amount, "currency": currency,
    })
    if response.status_code == 400:
        raise PermanentError(response.text)
    return response.json()


# 自定义 key——基于业务主键，而不是全量参数
@idempotent(
    namespace="git_push",
    ttl_seconds=3600,
    key_builder=lambda repo, branch, **_: f"{repo}@{branch}",
)
async def git_push(repo: str, branch: str, commit_sha: str) -> dict:
    return await git_api.push(repo, branch, commit_sha)
```

设计幂等 key 是个有讲究的活。两条经验：

**基于全量入参 hash**：适合无明显业务主键的工具，比如 LLM 调用、`web_search`。优点是天然唯一；缺点是入参里任何无关字段（trace_id、timestamp）变化都会导致 cache miss。所以 `_normalize` 里要把这些字段先剥掉。

**基于业务主键 hash**：适合有明确语义的副作用，比如 `git_push(repo, branch)` 的语义就是"把当前 HEAD 推到 repo:branch"，commit_sha 反而不该进 key——同一 branch 一秒内连推两次本来就不该重复触发。

还有一个 idle TTL 过期的陷阱。Agent 任务跑了 25 小时（超过默认 24 小时 TTL），最后一步重试时缓存已经过期，于是真的发了第二次副作用。三个对策：

1. **TTL 大于业务最大任务时长**：电商场景一般 7 天起步，金融对账场景甚至要拉到 30 天。
2. **持久化层兜底**：除了 Redis，业务侧（DB / 业务系统的 idempotency-key 接口）也存一份。Stripe 的 idempotency-key 默认保留 24 小时，做大额业务时一定要确认这个数字。
3. **过期前续期**：长任务 worker 在每次 heartbeat 时把它已经写过的 idempotency key TTL 都续一遍。

最后一条经验来自真实事故复盘：**幂等机制本身也要有可观测性**。当 cache hit 命中时，应该打一条带 namespace 和 cache key 的 metric；当 in-flight 锁等待发生时，应该单独打另一条。否则一旦发生大面积幂等异常（比如 Redis 实例切换导致全部 key 丢失），监控系统看到的只是工具调用次数翻倍，而不会知道这背后其实是幂等失效。把这层观测加上之后，事故定位时间从几小时压到几分钟。

---

## 第 8 章：Fork & Replay——长程任务的高级能力

Checkpoint 的能力一旦做扎实，会衍生出一组之前不敢想的玩法——**Fork**、**Time Travel**、**Eval Replay**。这些不是炫技，是真把长程 Agent 工程价值放大的杠杆。

### Fork Session

从某个 checkpoint 拉一条新分支出来，独立演化。形态上就像 git 分支：

```
原 session ──t0 plan──t1 search──t2 analyze ⚡崩溃
                          │
                          ├──→ fork-A: t1' search (换数据源) → t2' analyze
                          └──→ fork-B: t1'' search → t2'' analyze (换模型)
```

三大典型用途：

- **A/B 测试**：从同一个 plan checkpoint fork 两条分支，一条用 Claude 一条用 GPT，看哪条最终报告质量更高。
- **失败重试**：在 `analyze` 步骤崩溃后，fork 一条新分支换个 prompt 重试，原分支保留以便事后调查。
- **跨 backend 迁移**：从 Docker sandbox fork 一条分支到 Daytona 或 E2B，用于成本优化或区域合规。

下面是一段 Temporal 风格的 fork 实现，借助 Workflow Update 在不重启 workflow 的情况下做状态迁移：

```python
from temporalio import workflow
from dataclasses import dataclass

@dataclass
class ForkRequest:
    from_checkpoint_id: str
    new_session_id: str
    target_backend: str
    overrides: dict

@workflow.defn
class AgentSessionWorkflow:
    def __init__(self):
        self.checkpoints: list[dict] = []
        self.current_state: dict = {}

    @workflow.run
    async def run(self, init: dict) -> dict:
        self.current_state = init
        await workflow.wait_condition(lambda: self._is_done())
        return self.current_state

    @workflow.update
    async def fork_session(self, req: ForkRequest) -> str:
        snapshot = next(
            (cp for cp in self.checkpoints if cp["id"] == req.from_checkpoint_id),
            None,
        )
        if snapshot is None:
            raise ValueError(f"checkpoint {req.from_checkpoint_id} not found")

        # 1. 把 sandbox snapshot 转移到新 backend
        new_sandbox = await workflow.execute_activity(
            migrate_sandbox,
            args=[snapshot["sandbox_snapshot"], req.target_backend],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # 2. 启动 child workflow，继承父 session 的消息和 sandbox
        child = await workflow.start_child_workflow(
            AgentSessionWorkflow.run,
            args=[{
                "session_id": req.new_session_id,
                "parent_checkpoint_id": req.from_checkpoint_id,
                "messages": snapshot["messages"],
                "sandbox": new_sandbox,
                **req.overrides,
            }],
            id=req.new_session_id,
        )
        return child.id

    @workflow.signal
    async def checkpoint_created(self, cp: dict):
        self.checkpoints.append(cp)
```

跨 backend 迁移时还有一层很现实的工程问题——**模型调用层的兼容性**。原 session 在 Docker 里用 `OPENAI_BASE_URL` 指向某个 gateway，prompt 习惯、function calling 格式、stop tokens 都是基于那一套调出来的。fork 到新 backend 时如果模型调用层不兼容，等于要重写 prompt 重做评测。在 Fork 跨 backend 迁移时，OpenAI 兼容协议层（如 datatoken.vip 这种别名路由 + 多 provider 故障切换）能让新 backend 直接复用旧 session 的模型调用习惯，避免 prompt 重写。具体怎么选不展开，思路在那里。

### Time Travel

时光机式回放——回到某个历史 checkpoint，**改一处人工反馈或者参数**，让 Agent 接着这条新分支跑。LangGraph 的实现已经在第 4 章看过：

```python
history = list(graph.get_state_history(config))
# 假设倒数第 3 个 checkpoint 是 plan_node 输出后
target = history[2]

# 改 plan，重新进入下一个节点
graph.update_state(
    target.config,
    values={"plan": "保守方案：只升级到 Node 20，不动 Node 22"},
)
result = graph.invoke(None, target.config)
```

实战里 time travel 最大用途是**对昨天的失败做事后干预**——昨天某个用户的任务在 step 8 卡住了，今天工程师查清楚原因后，从 step 7 的 checkpoint 注入修正、重新跑后 8 步，对用户来说就像没失败过。这个能力在 SaaS 形态的 Agent 产品里，等同于多了一条"客服干预通道"。

### Eval Replay

把生产 checkpoint 灌进评测管线——这是一个被低估的杀手级能力。

```python
async def replay_checkpoint_for_eval(
    checkpoint_id: str,
    new_model: str,
    eval_metrics: list[Callable],
) -> dict:
    """从 checkpoint 起跑相同的剩余步骤，用新模型，记录指标。"""
    cp = await checkpoint_store.get(checkpoint_id)

    state = cp.state.copy()
    state["model"] = new_model

    # dry_run sandbox：只读 fs，外部 API 走 mock
    sandbox = await create_eval_sandbox(snapshot=cp.sandbox_snapshot, dry_run=True)

    result = await graph.invoke(
        None,
        {"configurable": {
            "thread_id": f"eval-{checkpoint_id}",
            "checkpoint_id": checkpoint_id,
        }},
    )

    return {m.__name__: m(result, state) for m in eval_metrics}
```

它的工程价值：

- **真分布**：评测样本是真实生产 checkpoint，覆盖了所有边角 case。
- **零打扰**：dry_run sandbox 屏蔽副作用，不会真的 push 代码 / 发邮件。
- **回归测试**：每次模型升级前，把过去 1 周生产 checkpoint 跑一遍，比较关键指标。

[Zylos 的 durable execution 研究](https://zylos.ai/research/2026-04-24-durable-execution-agent-runtimes) 专门讨论了 eval replay 在 2026 年的兴起，结论是"checkpoint 不只是容错产物，也是评测黄金资产"。这个判断在过去半年已经被多家头部 Agent 团队的工程实践验证——把生产 checkpoint 当作评测黄金集，比手工标注的评测集真实得多，也廉价得多。

把 Fork、Time Travel、Eval Replay 三件事放在一起看，会发现它们共享同一个底层假设——**checkpoint 是一等公民**。一旦 checkpoint 不只是用于容错恢复，而是可以被任意取出、传递、变形、重放，整个 Agent 系统就从"运行时"升级成了"可探索的状态空间"。这种从一维线性执行升维到多分支可视化执行的能力，是长程 Agent 区别于传统 RPA 流程最关键的工程红利。

---

## 第 9 章：选型矩阵——什么场景选什么

把前面 8 章的方案放在一张表里：

| 场景 | 推荐方案 | 关键理由 |
|------|---------|---------|
| 单进程开发 / Demo | LangGraph + MemorySaver | 零配置，几行代码起步 |
| 中等规模 + LangChain 生态 | LangGraph + PostgresSaver | 上手快，社区成熟，已有 LangChain 代码可直接升级 |
| 重度副作用 / 跨服务编排 | Temporal | 99.99% SLA，Multi-Region Replication，Workflow/Activity 模型工业级成熟 |
| 全托管 + Anthropic 模型为主 | Claude Managed Agents | 免运维，Sandbox+Checkpoint+Permission 打包，idle 不计费 |
| Azure 生态 + .NET/Java 团队 | Microsoft Durable Task for AI Agents | 多语言 SDK，与 Microsoft Agent Framework / LangChain 集成原生 |
| Cloudflare 边缘 / 低延迟 | Cloudflare Workflows + AWS Lambda Durable Functions | 与边缘 runtime 原生集成，长 suspension 友好 |

> AWS Lambda Durable Functions 在 2025 年 12 月 launch，覆盖 steps / waits / checkpoints / replay / retries / long suspensions 一整套能力，对原本就重度使用 Lambda 的团队是相对自然的过渡。

接下来用三个真实业务场景做推演，把表里的字搬到落地决策里。

### 场景 A：电商客服 Agent

业务画像：

- 单次会话平均 8-15 轮，少数复杂会话 30+ 轮
- 工具：订单查询、退货发起、优惠券派发、人工转接
- 副作用密集：退货会动库存、派券会改账户余额
- SLA：用户体感 <2s 响应，会话整体不允许丢失

选型推演：

- LangGraph + PostgresSaver 应付得了对话轮次和图编排，但**退货 / 派券**这种重副作用工具需要严格幂等保证 + 跨服务事务。
- 理想架构是 **LangGraph 上层 + Temporal 下层**：LangGraph 管对话图状态，每个副作用工具实际调用走 Temporal Activity，由 Temporal 提供 retry / timeout / 幂等保证。
- 退货 / 派券这两个工具底层调用业务系统时，再叠一层 Stripe-style idempotency-key（第 7 章）。

技术栈：LangGraph (PostgresSaver) → Temporal Activity → 业务系统（自带 idempotency）。

### 场景 B：代码 PR 审查 Agent

业务画像：

- 单次任务 5-30 分钟，重 sandbox（git clone + 编译 + 测试）
- 工具：git、文件读写、shell、LLM 大量调用
- 副作用：最终阶段会 push 评论 / approve / request changes
- SLA：单 PR 任务允许偶发失败重跑，但**不能写错评论**

选型推演：

- 重 sandbox + 长任务是 Claude Managed Agents 的甜点场景，特别是它的 idle 不计费可以把"等用户审"那段时间成本压到 token 自己。
- 如果团队愿意接受被 Anthropic 模型绑定，直接用 Managed Agents + 业务系统 webhook 就够了。
- 如果团队需要混合多模型，回到 Temporal Workflow + 自建 sandbox（Daytona / E2B / 自研 K8s sandbox）。

技术栈（路线 A）：Claude Managed Agents 作为唯一 runtime + GitHub Actions webhook 触发。
技术栈（路线 B）：Temporal Workflow + Daytona Sandbox + 多模型 gateway。

### 场景 C：长跑研究 Agent

业务画像：

- 单次任务 1-3 小时，工具：搜索、爬虫、文档解析、LLM 链式推理
- 副作用偏轻（主要是 S3 写报告、发邮件通知）
- 经常需要中途人工反馈（"换个角度再做一版"）
- SLA：失败重跑成本极高，必须支持中断恢复 + Time Travel

选型推演：

- LangGraph 的 Time Travel + Interrupt 在这个场景非常贴合——人工反馈正是 Interrupt 的设计目标。
- 单纯 LangGraph + PostgresSaver 跑 3 小时任务也能扛得住，前提是节点数据量不要爆炸。
- 配套上加一套 eval replay（第 8 章）做模型升级回归测试。

技术栈：LangGraph (PostgresSaver + Interrupt + Time Travel) + S3 报告归档 + 周度 eval replay 管线。

三个场景三种选型，没有"哪个最好"，只有"哪个最贴合约束"。这也是 [Microsoft Durable Task 文档](https://learn.microsoft.com/azure/durable-task/sdks/durable-task-for-ai-agents) 在开篇就强调的——"不要用一个 framework 解决所有 agent durability 问题，按业务约束分层选择"。把选型决策落到具体的业务画像和 SLA 约束上，比讨论"哪个 framework 更先进"要务实得多。

落到团队层面，还有一条非技术、但同等重要的经验：**容错方案的选型一定要和团队的工程文化匹配**。习惯写状态机的团队上手 Temporal 几乎没门槛；习惯写 prompt 链的团队从 LangGraph 起步会更顺；缺乏运维资源的小团队直接用全托管 runtime 是最务实的选择。技术选型的本质从来不只是"哪个工具最强"，而是"哪个工具能让团队在六个月后仍然愿意维护它"。这条原则套在 durable execution 选型上一样适用。

---

## 第 10 章：下一篇钩子（3 选 1，让读者投票）

到这里，长程 Agent 容错的工程主线已经走完一遍。下一篇打算挑一个邻近主题继续展开，三个候选——欢迎在评论区告诉我哪个最想看：

### 钩子 1：Tool Graph 剪枝

长程 Agent 平均挂 32 个工具：搜索、爬虫、文件、shell、git、邮件、Slack、Jira、CRM、内部 RPC……每次 LLM 调用都把全部 tool description 塞进 system prompt，光描述就能吃掉 4k input token。

实战做法是**按上下文动态剪枝**——根据当前任务阶段（planning / searching / writing），只暴露 20% 相关工具，其他 80% 屏蔽。剪枝信号来源：用户 query 分类、最近 3 轮 tool call 历史、工具调用图谱（tool graph）。预期效果：4k → 800 token 的 tool description 开销，**约 80% 上下文压缩**，单次 LLM 调用 input cost 同比下降，长会话累计能省一截。这一篇会拆 HuggingFace Smolagents 工具集成和 OpenAI Agents SDK tool spec 的设计差异，给一份生产级剪枝实现。

### 钩子 2：Agent 评测体系横评

主流四套：

- **PinchBench**：MCP 工具调用准确率
- **DeepResearch Bench**：多轮研究任务完成度
- **SWE-bench**：代码修复实际 PR pass rate
- **GAIA**：综合性 agent benchmark

每套侧重维度不同——指令跟随 / 工具选择 / 长程规划 / 代码理解 / 多模态。下一篇会把同一个 Agent 在四套 benchmark 上跑一遍，给一份"哪个 benchmark 测哪类能力"的工程指南，并讨论怎么基于第 8 章的 eval replay 思路，把生产 checkpoint 灌进评测管线，做到**生产分布 = 评测分布**。参考阅读：[CSDN 上一篇关于 Agent 评测体系的整理](https://blog.csdn.net/qq_73472828/article/details/160726069) 给了几张对比表，可以预读。

### 钩子 3：Tracing 与回放系统设计

OpenTelemetry → LangSmith → Langfuse → Helicone，可观测性栈在 2026 年已经卷到第三代。下一篇拆三件事：

- **Tracing schema**：Agent span 怎么定义（task / turn / tool_call / llm_call 四级）
- **采样策略**：长程任务 100% 采样会爆 storage，怎么按 task complexity 自适应采样
- **回放系统**：把 trace 当成 checkpoint 的副本——一套 trace 既能用于 debug，也能用于 eval replay，省掉双轨维护

会顺手聊一下 OpenAI Responses API 内置的 tracing 模型与 LangSmith / Langfuse 的协议差异。

三选一，告诉我你的偏好。读者反馈最高的那条会先排进下一篇日程，欢迎留言，把你最想看的钩子和正在踩的坑一起贴出来——真实场景往往比抽象议题更值得被深入讨论。

---

**相关资源**：

- 小程序："点点词元" —— 一个 Key 调用全球主流大模型，OpenAI 兼容协议，原生支持别名路由 / 多 provider 故障切换 / 用量观测，本文 Fork & Replay 章节中的「跨 backend 迁移时模型调用层抽象」可直接复用其调度层。
- 模型广场：https://www.datatoken.vip
- API 文档与适配层：https://www.datatoken.vip/docs
- 配套源码：https://github.com/fangzehui/llm-tech-articles

*本文代码基于实际生产经验整理，供技术参考。*
