# 大河豚 TreeQuest 源码精读 + 四大 LLM 编排器选型实录：从 AB-MCTS 到正交叠加

> 2026 年 4 月 27 日，Sakana AI 发了一篇被 ICLR 2026 收的论文，把"用一个 7B 小模型指挥 GPT-5 + Claude Sonnet 4 + Gemini 2.5 Pro 接力解题"这件事做到了 AIME25 93.3%、GPQA-Diamond 87.5%、LiveCodeBench 83.93%，**平均每题只花 1820 个 token**（[Sakana 官博](https://sakana.ai/learning-to-orchestrate/)）。这件事在 LangChain / LangGraph 派的工程师圈里激起了一阵不小的波澜——因为这条路线既不是把 agent 串成图、也不是给模型加 tool call，它是回到了"在答案空间里做树搜索"这个被很多人觉得"太学术、上不了生产"的方向。两个月前的 2 月 6 日，Sakana 已经把它的基座算法 **AB-MCTS** 开源成了 [TreeQuest 0.3.2](https://pypi.org/project/treequest/)（Apache 2.0），代码不到 5000 行，README 上的 demo 是 20 行 Python——你 pip install 完今天下午就能跑起来。

这是一个值得正面看待的时点。本文给读者三件事：**一份 AB-MCTS 算法 + TreeQuest 源码的精读笔记**（前半，约一半篇幅）、**一张把 TreeQuest / OpenRouter / Vercel AI SDK / LangGraph 四家编排器叠在同一张表上的横评**（后半），以及**一套可以直接 fork 的最小可跑工具集**（[chapter-20-llm-orchestrator-treequest](https://github.com/LDZKKJ/llm-work/tree/main/chapters/chapter-20-llm-orchestrator-treequest)）。中间会反复强调一件事——**这 4 家不是"二选一"，而是 4 个正交层（路由 / 前端 / 状态机 / test-time compute），是叠着用的**。

## 一、现状：从单模型推理到"集体智能"的工程切换点

先把 2024 年底到现在的关键事件拉一根时间线，可以看到"编排"这个词在 19 个月里是怎么从"工程师的随手脚本"变成"独立的产品形态"的：

| 时间 | 事件 | 工程意义 |
|---|---|---|
| 2025-03-06 | **AB-MCTS 论文上线 arXiv**（[2503.04412](https://arxiv.org/abs/2503.04412)，*Wider or Deeper? Scaling LLM Inference-Time Compute with Adaptive Branching Tree Search*） | 第一次把"该深挖还是该换模型"形式化为搜索决策 |
| 2025-07-01 | Sakana AI 在[官方博客](https://sakana.ai/ab-mcts/)发布 AB-MCTS 全文 + ARC-AGI-2 实证 | 把 o4-mini Pass@250 从 23% 拉到 27.5%，多 LLM 接力 >30% |
| 2025-10-24 | 论文 v4 版定稿，**NeurIPS 2025 Spotlight** 接收 | 算法层从"团队工程实践"升级为"学界共识" |
| 2026-02-06 | **TreeQuest v0.3.2 上 PyPI**（Apache 2.0） | 普通 Python 工程师可以 ``pip install treequest`` 直接试 |
| 2026-04-27 | Sakana 发布 [Conductor 论文](https://sakana.ai/learning-to-orchestrate/)，**ICLR 2026** 接收 | 用 RL 训了一个 7B Qwen2.5 当"指挥家"，自动决定子任务拆分与 worker 分配 |
| 2026-04~05 | 商用产品 **Sakana Fugu**（fugu-mini / fugu-ultra，OpenAI 兼容 API）进入 beta | 编排能力第一次以一等 API 的方式被卖 |
| 2026-05~06 | **Sakana Marlin**（B2B 深度研究 Agent）开放，¥9,800/任务、¥150,000/月起 | 多 Agent 编排进入企业服务的"按任务计费"档位 |
| 2026-06-12 | OpenRouter 把 BYOK 升级为"前 100 万次免费 + 5%"（[官方教程](https://openrouter.ai/blog/tutorials/how-to-get-the-lowest-cost-llm-inference-on-openrouter/)） | 路由层进一步弱化"加价"标签，强化"开发者代理"定位 |

把这些事件叠在一起看，结论很直接：**单模型推理时代的边际收益正在迅速衰减，而"多模型 × 推理时算力 × 编排器"这条复合路线正在补上这块缺口**。我倾向的判断是，2026 下半年的工程命题不再是"我们选哪个旗舰模型"，而是"我们用哪一套编排器去把多家模型组织起来"——这是产品和成本结构的双重转折。

值得提醒的一件事：**Sakana 这一系列的核心论点不是"小模型能打大模型"，而是"协调好的多模型组合能稳定打过任何单家旗舰"**——Conductor 论文里那个 7B 模型并不真正解题，它只决定"哪一步该让谁来做、给他看哪些前序输出"，真正干活的还是 GPT-5、Claude、Gemini（[andrew.ooo 横评](https://andrew.ooo/answers/sakana-rl-conductor-vs-langgraph-vs-crewai-orchestration-may-2026/)）。把这条主线吃透，能解释为什么本文后半段说"OpenRouter 不会被 TreeQuest 替代、TreeQuest 也不会被 LangGraph 替代"——它们在解决的根本是不同抽象层级的问题。

## 二、AB-MCTS 算法直觉：把"深 vs 宽"变成搜索决策

要看懂 TreeQuest，先得理解它脚下的算法 AB-MCTS 解决的是什么问题。

传统的推理时扩展只有两条路。**第一条**是"深"——也叫 Sequential Refinement，让模型反复 refine 一个答案。这条路怕的是首答跑偏，后面所有 refine 都在错的方向上做局部优化。**第二条**是"宽"——也叫 Repeated Sampling 或 Best-of-N，同一个 prompt 反复采样 N 次取最好。这条路怕的是好答案没有人继续优化，而坏答案占走了预算。AB-MCTS 的核心见解非常朴素：**这两件事在工程上从来不该是二选一的，而应该是"每一步动态决定"——具体到当前已经探出来的搜索树，下一步是该继续往一个有希望的节点上挖、还是从父节点重新起一个新候选**（[官博解释](https://sakana.ai/ab-mcts/)）。

把这件事形式化一下：搜索过程是一棵树，每个节点是某次 LLM 调用产生的候选答案，节点的边权是某种"成功概率后验"。每一步算法在树上做三个决定——

1. **Go Deeper**：选一个已有节点，让某个 LLM 在它的基础上 refine 一版；
2. **Go Wider**：从该节点的父节点重新生成一个新候选（同样的上下文，但不同的 sample 路径）；
3. **Multi-LLM 扩展**：决定让"哪家 LLM"来执行这次生成——o4-mini、Gemini 2.5 Pro、DeepSeek-R1 之间分配预算。

三个决定共用一个机制——**Thompson Sampling**。Thompson Sampling 是多臂老虎机问题里最经典的解法之一：每个候选维护一个 Beta 后验 Beta(α, β)，每次决策从所有候选的 Beta 里各采一个值，挑值最大的那个；当某个候选不断"成功"（生成的子节点 score 高于阈值）就 α+1，反之 β+1。这个机制的妙处是**早期天然均匀探索**（先验 α=β=1 时 Beta(1,1) = Uniform）、**后期收敛到经验最优**——既不会一头扎进局部最优、又不会浪费预算在已经证明很烂的分支上。

在数学上，AB-MCTS 把 Thompson Sampling 同时用在两个尺度：**节点尺度**（哪个父节点值得扩展）和 **LLM 尺度**（哪家模型胜率最高）。算法层还有两个变种——AB-MCTS-A 用节点级聚合的简化 Beta 维护后验，AB-MCTS-M 用 PyMC 跑混合贝叶斯模型，更精细但更慢（[arXiv v4](https://arxiv.org/abs/2503.04412v4)）。这两个变种在 TreeQuest 里都有实现，工程默认推 -A 版。

这个算法直觉决定了它最适合什么任务：**有显式打分函数 + 任务难、单次正确率低、但有多个独立解法路径**——典型场景是 ARC-AGI 这类抽象推理、Olympiad 级数学、SWE-Bench 级代码、ML 模型超参调优。Sakana 的 ARC-AGI-2 实证给了一组很扎眼的数据：o4-mini 单跑 Pass@250 是 23%，AB-MCTS 单 LLM 拉到 **27.5%**，开 Multi-LLM（o4-mini + Gemini 2.5 Pro + DeepSeek-R1 三家轮流采样）拉到 **>30%**，且出现了"o4-mini 答错→DeepSeek-R1 或 Gemini 接力改对"的真实数据点（[neurohive.io 复盘](https://neurohive.io/en/frameworks/treequest-framework-adaptive-llm-teams-outperform-individual-models-by-30/)）。**多 LLM 不只是叠 +30% 的边际收益，它还把"单家模型的盲点"系统性消除**——这是单模型反复采样永远做不到的事。

反过来讲，AB-MCTS 不适合什么任务也很清楚：**没有显式打分函数**（聊天 / 创意写作 / 客服 Bot——你没法给"这条回复有多好"打 0-1 标量分）、**单模型已经够好**（简单分类 / 信息抽取——多调几次纯粹浪费 token）、**实时延迟敏感**（流式 chat / 自动补全——50-250 次调用根本等不起）。这条边界后面在第七章会展开成一个选型 playbook。

还有一个常被忽略的工程细节：AB-MCTS 的"score 必须是 [0,1] 标量"是它最大的限制。真实任务里写一个稳定的 evaluator 比写算法本身更难——单元测试通过率、judge 模型评分、code-exec 是否成功，每一种都需要在 ``generate_fn`` 里自己实现。TreeQuest 把这件事做成了"用户协议"而不是"框架提供"——这是它和 LangGraph 哲学不同的第一处分野（**LangGraph 选择给你 ``StateGraph + checkpoint`` 一整套抽象，TreeQuest 选择只给你搜索算法，evaluator 自己写**）。这件事的工程含义是：用 TreeQuest 的项目，前两周大部分时间花在"怎么把任务输出翻译成 [0,1] 分"，而不是花在算法调参上。

## 三、TreeQuest 源码精读：核心类与三动作的状态机

把 TreeQuest 的源码摊开来看，主结构非常薄——核心就是 `Node` / `algorithm.step()` / `top_k()` / `render()` 四件事。下面是把官方实现按教学口径浓缩过一遍的最小可读版本（完整版在 [treequest_minimal.py](https://github.com/LDZKKJ/llm-work/tree/main/chapters/chapter-20-llm-orchestrator-treequest/treequest_minimal.py)）：

```python
# treequest_minimal.py（节选）
@dataclass
class Node:
    state: Any                          # 候选答案（任意 Python 对象）
    score: float                        # [0, 1] 外部反馈分
    llm: str                            # 由哪个 LLM 生成
    parent: Optional["Node"] = None
    children: List["Node"] = field(default_factory=list)
    wins: int = 1                       # Beta(α, β) 先验从 α=1 开始
    losses: int = 1                     # β=1 → Beta(1,1) = Uniform

    def update(self, success: bool) -> None:
        if success: self.wins += 1
        else:       self.losses += 1
```

节点结构里值得多说一句的是 `state: Any`——TreeQuest 不假设 state 长什么样。它可以是字符串答案（数学题）、代码字符串（编程题）、JSON 工作流（多 agent）、甚至 ``PIL.Image``（多模态任务）。这种"状态结构无关"是它能塞进任意场景的关键。score 必须是浮点 [0,1]，但 state 怎么序列化、怎么 hash、怎么对比相似度——一律由用户在 generate_fn 里自定义。

接下来是 Thompson 采样——AB-MCTS 的灵魂：

```python
# treequest_minimal.py（节选）
def thompson_pick(candidates: List[Node], rng: random.Random) -> Node:
    """从每个候选的 Beta(wins, losses) 里采一个值，取最大者。"""
    best, best_v = None, -1.0
    for c in candidates:
        v = rng.betavariate(c.wins, c.losses)   # Python 标准库自带 Beta
        if v > best_v:
            best, best_v = c, v
    return best
```

短短 6 行，但工程上有 3 个细节值得注意：第一，`random.betavariate(α, β)` 是标准库自带的，**不需要 NumPy / PyMC 任何重依赖**——这是 TreeQuest 能做到"纯 Python 库"的根本原因。第二，先验从 α=β=1 而不是 α=β=0 开始——这避免了零样本节点采到 0/0 这种数学奇点。第三，**这个函数同时被用在"选父节点"和"选 LLM"两个维度上**——把同一个采样原语在两个尺度上复用，是 AB-MCTS 算法的最大简洁性。

`step()` 函数是整个算法的状态机，下面这版是教学口径的伪码，省略了批量并发与 checkpoint：

```python
# treequest_minimal.py（节选，伪码版）
def step(self, tree: Node, generate_fns: Dict[str, GenerateFn], rng) -> Node:
    # 1) 跨 LLM 选谁来生成
    chosen_llm = thompson_pick_llm(tree._llm_stats, rng)
    gen_fn = generate_fns[chosen_llm]

    # 2) 选父节点（root + 所有已存在节点 → root 即"全新起头"，其它即"refine"）
    all_nodes = _all_nodes(tree)
    parent = thompson_pick(all_nodes, rng)

    # 3) 生成新候选并挂到父节点下
    new_state, new_score = gen_fn(parent.state if parent is not tree else None)
    new_node = Node(state=new_state, score=new_score,
                    llm=chosen_llm, parent=parent)
    parent.children.append(new_node)

    # 4) 回传成败（典型 MCTS backup + 更新该 LLM 的全局胜率）
    success = new_score >= self.config.success_threshold
    cur = new_node.parent
    while cur is not None:
        cur.update(success); cur = cur.parent
    w, l = tree._llm_stats[chosen_llm]
    tree._llm_stats[chosen_llm] = (w + int(success), l + int(not success))
    return tree
```

把这 20 行读完，AB-MCTS 的三动作就清楚了——**Go Deeper / Go Wider / Multi-LLM 不是三个不同的代码分支，而是同一个采样动作在不同候选上的具体体现**：

- 当 Thompson 选到 root 节点 → 等价于 `parent_state=None`，gen_fn 从空起头，**这就是 Go Wider**（开新分支）；
- 当 Thompson 选到一个深度 d≥1 的节点 → gen_fn 拿到 `parent_state`，对其 refine，**这就是 Go Deeper**；
- LLM 维度的 Thompson 把"哪家模型胜率更高"用同一个机制学出来，**这就是 Multi-LLM 自适应**。

**算法对工程师来说最反直觉的一点**：三件事用同一套 Beta 后验维护，意味着**当某条深路径连续几步都失败时，整个分支的"胜率"会被压低，下一次 Thompson 自然会偏向其它分支**——这是它和"硬编码深度上限"、"硬编码每个 LLM 配额"完全不同的工程哲学。**它把"调度策略"放进了概率模型里，而不是放进 if-else 里**。这对运维的工程师太重要了：调一个 Thompson Sampling 出问题，你只需要看 (wins, losses) 的演化；调一个 if-else 出问题，你需要重读整个调度代码。

把这套结构再往前看一步——TreeQuest 的官方实现还在这层之上做了两件工程化加固：(1) **`ask_batch / tell` 两阶段拆解**让多个 LLM 调用可以并发发出，再异步把 score 回填——这是真实场景跑 250 次调用必备的吞吐量优化；(2) **内建 checkpointing**让一棵跑到一半的搜索树可以 pickle 出去、过几小时再 resume——对昂贵的 ARC-AGI 求解尤其重要。我们这版教学实现把这两件事简化掉了，但工程读者真要上生产请直接用官方 [SakanaAI/treequest](https://github.com/SakanaAI/treequest) 而不是这版精读版。

值得多提一句的是 TreeQuest 的"算法-provider 解耦"哲学。源码里**完全没有任何 OpenAI / Anthropic / Gemini 的 SDK 依赖**——`generate_fns` 是一个 `Callable` 协议，你给什么就调什么。**TreeQuest 把"模型怎么调"留给了 OpenRouter，把"agent 怎么走"留给了 LangGraph，把"前端怎么对接"留给了 Vercel AI SDK，自己只做"搜索算法 + 后验维护"这一层最薄但最难做对的事**——这是后半章"四家正交叠加"论点的基础。

## 四、200 行 Python 跑通一个最小 demo

我把 `treequest_minimal.py` 攒到了 ~250 行，加上一个不需要外网的"伪数学题"任务——3 个 fake LLM 协作把 ``answer`` 逼近 ``target=42``，每个 LLM 行为不同：

```python
# treequest_minimal.py 自带 demo（节选）
def _build_demo_generators(target: int = 42):
    """构造 3 个"假 LLM"，模拟真实多模型的差异：
    - o4_mini_like：起步好但 20% 概率跑偏；
    - gemini_like：refine 强，父节点 score 高时进一步提升；
    - deepseek_like：30% 概率 one-shot 命中，70% 乱跑。
    """
    def _score(answer): return max(0.0, 1.0 - abs(answer - target) / 100.0)

    def o4_mini_like(parent_state):
        if parent_state is None:   base = target + rng.randint(-30, 30)
        else:                       base = parent_state + rng.randint(-15, 15)
        if rng.random() < 0.2:     base += rng.randint(-50, 50)
        return base, _score(base)
    # gemini_like、deepseek_like 类似…

    return {"o4_mini_like": o4_mini_like, "gemini_like": gemini_like,
            "deepseek_like": deepseek_like}

# 跑 30 步搜索
algo = ABMCTS(ABMCTSConfig(budget=30, success_threshold=0.9, seed=42))
fns = _build_demo_generators(target=42)
best, trace = algo.run(fns)
print(f"best: state={best.state} score={best.score:.3f} by={best.llm}")
```

实际跑出来的结果（[配套仓库](https://github.com/LDZKKJ/llm-work/tree/main/chapters/chapter-20-llm-orchestrator-treequest)里 ``python treequest_minimal.py`` 一行即可复现）：

```
>>> TreeQuest minimal demo：3 个伪 LLM 协作求 target=42
[best] state=42 score=1.000 by=deepseek_like
[best] depth=4 路径=o4_mini_like → gemini_like → o4_mini_like → deepseek_like

[trace 前 10 步]
  step= 1  best=0.910  by=o4_mini_like   n_nodes=1
  step= 2  best=0.910  by=o4_mini_like   n_nodes=2
  step= 3  best=0.940  by=gemini_like    n_nodes=3
  step= 4  best=0.940  by=gemini_like    n_nodes=4
  ...
  step=10  best=0.990  by=deepseek_like  n_nodes=10
```

注意几件事：第一，**最佳节点的路径是 `o4_mini_like → gemini_like → o4_mini_like → deepseek_like` 这种异构接力**——没有任何一家 LLM 独立把这一步做到 1.0，是多家在树上博弈的结果。第二，**深度 4 的搜索树是从一个"o4_mini 起头 → gemini 改进 → o4_mini 再改 → deepseek 一锤定音"的真实接力链**——这就是 Sakana 在 ARC-AGI-2 上观察到的同款现象，只不过在伪数学题上规模小很多。第三，前 10 步的 ``best_score`` 是单调上升的——这是 Thompson Sampling 收敛性的可视化体现，跟蒙特卡洛搜索的统计单调性吻合（[arXiv v4 第 4 节](https://arxiv.org/abs/2503.04412v4)）。

把同样的代码改成调真实 LLM（比如通过 OpenRouter 同时挂 o4-mini、Gemini 2.5 Pro、DeepSeek-R1），只需要替换 ``_build_demo_generators`` 里三个函数的实现——HTTP 调用 + 评分函数 + 异常重试就够了。其它部分（``Node`` / ``thompson_pick`` / ``step`` / ``top_k``）一行不用动。这就是 TreeQuest "算法-provider 解耦"在工程上的红利：**你换 LLM、换 provider、换评分器，搜索算法本身都不需要改**。

我故意没让这个 demo 用 ARC-AGI 真数据集——一是配置复杂、二是评分器要自己实现 grid 比对、三是真要用 ARC-AGI-2 请直接用 Sakana 官方仓库 [SakanaAI/ab-mcts-arc2](https://github.com/SakanaAI/ab-mcts-arc2) 跑。我们这版 demo 的目标只是让工程师在 10 分钟内"读懂代码 + 看见接力 + 改一行就接真 LLM"。

`tests/test_treequest.py` 里还放了 9 个 pytest 用例：单元测试覆盖 ``Node`` 基础操作、Thompson 大样本收敛、单 LLM 单调性、多 LLM 提升、成本曲线单调、break-even 判别、4 风格调用次数差异、样本任务可加载、文本树渲染冒烟。`pytest tests/ -v` 全绿大约 2 秒。这里有一个工程小坑值得分享：``test_ab_mcts_multi_llm`` 里我加了一个 ``容忍 0.05 噪声``的断言（"多 LLM 不应明显比只用 noisy 差"），这是因为 Thompson Sampling 在小 budget 下存在偶发"运气差"窗口——**这正是 AB-MCTS 在 ARC-AGI 上需要 Pass@250 而不是 Pass@10 的统计原因**。生产里跑这种算法不要在小 budget 下做 A/B，至少 100 次以上才稳定。

## 五、Benchmark 实证与 test-time compute 的经济学

把 demo 跑通只是第一步，真正决定"AB-MCTS 值不值得上生产"的是**它的 Pass@K 曲线和成本曲线的斜率比**。Sakana 官方在 ARC-AGI-2 上给了一组数据，我把它转写成"每多花一次 LLM 调用，准确率边际收益是多少"的视角：

| Setup | LLM 调用预算 | ARC-AGI-2 Pass | 边际成本（vs 上一档）|
|---|---:|---:|---|
| o4-mini Repeated Sampling | 250 | 23% | 基线 |
| AB-MCTS-A 单 LLM (o4-mini) | 250 | **27.5%** | 同等 token，纯算法收益 +4.5% |
| AB-MCTS Multi-LLM (3 家) | 250 | **>30%** | 同等 token + 3 家轮采，再 +2.5%~3% |

数据源：[Sakana 官博](https://sakana.ai/ab-mcts/) + [neurohive.io 复盘](https://neurohive.io/en/frameworks/treequest-framework-adaptive-llm-teams-outperform-individual-models-by-30/)。Sakana 公开的解读特别值得引用——**"o4-mini Repeated Sampling 已经把单 LLM 反复采样的潜力榨干，AB-MCTS 多出的 4.5%-7% 是搜索算法本身的贡献，不是模型变强带来的"**。这件事在工程上意味着：**如果你已经花了一笔 token 在 Best-of-N 上，AB-MCTS 是一个"免费的"+5% 升级**——前提是你能写出 [0,1] 评分函数。

把这条曲线放进**经济学**视角看更扎眼。配套仓库的 ``cost_analyzer.py`` 跑了一个最简版 Pass@K 模型——假设每次调用独立解出的概率是 p_single，那么 **Pass@K = 1 - (1-p_single)^K**，预算成本 **Cost = K × token_per_call × price**。三档典型模型（cheap = DeepSeek-V4-Flash 量级、mid = Gemini 3 Pro 量级、flagship = Claude Opus 4.8 量级）跑出来的曲线长这样：

| 模型档 | p_single | 单次成本 | K=4 Pass | K=8 Pass | K=16 Pass | K=16 总成本 |
|---|---:|---:|---:|---:|---:|---:|
| cheap | 0.30 | $0.000364 | 0.760 | 0.942 | 0.997 | $0.0058 |
| mid | 0.45 | $0.00420 | 0.908 | 0.992 | 1.000 | $0.0672 |
| flagship | 0.55 | $0.0500 | 0.959 | 0.998 | 1.000 | $0.800 |

读这张表的方式不是"哪家最强"，而是"**要把准确率打到 95%，最便宜的路径是什么**"——

- 用 flagship 模型单跑：p_single=0.55 永远到不了 95%，需要 K=4 次（**$0.20**）才能凑到 95.9%；
- 用 mid 模型：K=4 次（**$0.0168**）就能到 90.8%，K=8 次（**$0.034**）到 99.2%；
- 用 cheap 模型：K=8 次（**$0.003**）到 94.2%，K=16 次（**$0.006**）到 99.7%——**比 flagship 单跑便宜 33×，准确率反而高 3.8 个百分点**。

**这是 AB-MCTS 经济学的核心——花更多 token 走"廉价多次采样"路径，在大多数任务上比"旗舰单跑"更便宜达到同等准确率上限**。这条结论我们在 [18 号文 OpenRouter 周榜](../18-OpenRouter周榜实证_国产大模型选型决策.md)里其实已经隐约推导过——DeepSeek-V4-Flash 五连冠的根本原因之一就是开发者用脚投票出来的"廉价多采样"路径。**AB-MCTS 把这条经济学从开发者直觉拉到了形式化的算法层面**，更进一步——它用 Multi-LLM Thompson 把"多次采样" 升级成"多家模型轮采"，覆盖了单家模型的盲点。

但要注意几件让这套经济学不立刻成立的工程因素：

**第一，评分器的成本不能忽略**。Pass@K 假设你能廉价地知道"这次答得对不对"——对 ARC-AGI（有标准答案）、数学题（可数值比对）、代码题（可单元测试）成立，但对"客户邮件回复"、"营销文案"这种**无 ground truth** 的任务，评分器本身要用另一个 LLM 跑（叫 LLM-as-Judge），**Judge 调用的 token 成本同样要算进 K**，整体经济性会被压扁。

**第二，边际收益递减来得很快**。同一张表里 K=8 到 K=16 在 cheap 档只提升 5.5 个百分点（94.2% → 99.7%），花的 token 翻倍。**实际工程里 K 通常停在 8-32 之间**，再往上的边际收益不值得（除非你在做 Olympiad 这种"刷分"场景）。

**第三，并发与延迟约束**。AB-MCTS 是顺序算法——后一步依赖前一步的 score 来做 Thompson——并发度受限于 ``ask_batch`` 批量大小（官方推荐 ≤5）。**如果你需要 P99 < 5 秒的响应**，AB-MCTS 几乎肯定要让位给 LangGraph 的并发 supervisor 或 Vercel AI SDK 的 streamText。

**第四，缓存与去重**。生产里多次 LLM 调用大概率会撞到同一个 sub-prompt（尤其是 refine 路径），prompt cache 命中率显著影响真实成本——这部分在 [17 号文 Prompt Caching 成本实测](../17-Prompt_Caching成本实测横评.md)里有完整推演，与本文 AB-MCTS 的成本模型可以叠加使用。

把上面四条合起来给一个工程经验法则：**当任务有显式打分函数 + 单模型 p_single 在 [0.2, 0.6] 区间 + 可容忍 P99 ≥ 10 秒 + budget 在 8-32 调用之间**，AB-MCTS 几乎是无脑赚的——其它情况下要算具体账。

## 六、商业化阶梯：从 TreeQuest 到 Conductor、Fugu、Marlin

把 Sakana 的产品线摊开看，是一个非常清晰的"从开源算法到企业服务"的阶梯：

| 层级 | 产品 | 形态 | 价格 | 适合谁 |
|---|---|---|---|---|
| L1 开源算法库 | **TreeQuest** | `pip install treequest` Python 库 | $0（Apache 2.0），只付底层 LLM token | 想自己写评分器、有工程团队、需要可控的研究/中型企业 |
| L2 新一代编排算法 | **Conductor / TRINITY** | 论文 + 模型（ICLR 2026） | $0（学术开源），私有数据训练 RL Conductor 需自研 | 有 RL 训练能力的大企业、研究院 |
| L3 商用 API | **Sakana Fugu**（fugu-mini 🐟 / fugu-ultra 🐡） | OpenAI 兼容 API（beta） | 订阅 + Pay-as-you-go，国际定价未公开，需申请（[fugu-beta](https://sakana.ai/fugu-beta/)） | 不想自建编排栈、需要"上来就能用"的产品团队 |
| L4 B2B 深研 Agent | **Sakana Marlin** | 企业级"100 页研究报告 + PPT"型 Agent | ¥9,800/任务；Pro ¥150,000/月（2,000 credits）；Team ¥400,000/月（6,000 credits）（[tradepoint.io 报道](https://tradepoint.io/sakana-ai-commercializes-ab-mcts-in-sakana-marlin-an-enterprise-agent-generating-up-to-100-page-research-reports-with-slides/)） | 受监管行业的合规调研、投行、咨询、政策研究 |

L1 → L4 这条阶梯反映了一个非常直白的工程命题：**你愿意把多少抽象层让出去、换多少价钱回来**。

- 用 **TreeQuest** 你自己写评分器、自己接 LLM、自己处理 backoff，但每个 ARC-AGI 求解只付 ~$0.20-0.30 的 o4-mini 量级 token 费——**整体单次任务 50-250 倍于普通 chat 的成本，是"用得起 vs 用不起"的分水岭**。
- 用 **Conductor** 你不用自己设计调度策略，但要训练一个 7B 路由模型——AIME25 93.3%、GPQA-Diamond 87.5%、LiveCodeBench 83.93% 的成绩、平均 1820 token/题（基线 MoA 是 11203 token/题，**省 6 倍**）（[halmob.com](https://halmob.com/blog/sakana-conductor-multi-agent-orchestration)、[sakana.ai 官博](https://sakana.ai/learning-to-orchestrate/)）——但 RL 训练本身的算力门槛把这条路圈在了大企业 / 研究院。
- 用 **Fugu** 你只发一个 OpenAI 协议请求，但价格未公开、需要申请、且暂时是 black-box——和"自建 LangGraph + 多 LLM" 形成直接的 vs 关系，[andrew.ooo 的横评](https://andrew.ooo/answers/sakana-rl-conductor-vs-langgraph-vs-crewai-orchestration-may-2026/)给了一句非常精准的评价：**"Conductor is transparent-to-the-task, opaque-to-the-engineer"**（任务结果可解释，但工程师看不到内部决策）。
- 用 **Marlin** 你只发"我想要 100 页关于半导体行业的研究报告"，¥9,800 一次起跳——这个价格在受监管行业（金融 / 法律 / 咨询）的语境下其实是"便宜的"：一份初级分析师月薪是 ¥15,000-25,000，一份咨询公司白皮书外采价是 ¥50,000-200,000。**Marlin 的卖点不是单 token 便宜，而是"以一份白皮书的价格换一份白皮书"**。

**值得展开的一点是 Conductor 的"反直觉决策"**：[Sakana 官博](https://sakana.ai/learning-to-orchestrate/)的演示里有一个被反复引用的现象——面对简单事实性问题，Conductor 一步搞定，直接 query 1 个模型；但面对复杂编程问题，它会**自发**生成一个 "planner → coder → verifier" 三级流水线，让 Gemini 2.5 Pro 做规划、Claude 细化方案、GPT-5 写最终代码——**没有任何一行硬编码 "if 是编程任务 then 用流水线" 的规则**。这种 emergent behavior 是 RL 训练 + 端到端 reward 的产物——它训出来的不仅仅是"如何选模型"，而是"如何在自然语言里写出一个 prompt engineering 流水线"。

**为什么这件事重要**：传统 LangChain/LangGraph 是"工程师写流水线"，Conductor 是"模型学会写流水线"——前者上限受限于工程师的认知边界，后者上限受限于 RL 训练的探索能力。我倾向的判断是，**未来 12 个月里"工程师手写流水线"会继续占主流（鲁棒 + 可审计），但"学到的流水线"会在高价值 / 高难度任务上系统性胜出**——这是 Sakana 这条路线的真正价值，也是为什么 LangGraph 派工程师在评论 Conductor 时会用上"分水岭"这样的词。

从工程视角再补一句：**Sakana 这套商业化阶梯刚好把"工程师 / 产品团队 / 业务部门 / 终端客户"四种买方都覆盖到了**——L1 给工程师、L3 给产品团队、L4 给业务部门、L2 留给研究院和大企业。这是一个非常完整的商业产品矩阵，也是它能在"算法开源 + 论文发表"之外把整套体系做成可持续业务的关键。但作为读者你不必每一层都买——本文剩下的篇幅就是教你"该买哪一层"。

---

## 七、4 大编排器横评：正交而非替代

到这里为止本文的前半结束，主线是"AB-MCTS 算法 + TreeQuest 源码 + 经济学"这条深度路线。后半切到一个更广的命题：**TreeQuest 不是孤立存在的，它要和 OpenRouter、Vercel AI SDK、LangGraph 这三家在工程师的工具箱里共存**。

让我先破一个非常常见的误解：**这 4 家不是互相替代的关系**。在中文社区的讨论里我经常看到"OpenRouter vs LangGraph 怎么选"、"Vercel AI SDK 能不能替代 LangChain"、"TreeQuest 是不是 LangGraph 的升级版"——所有这些问题都建立在"二选一"的预设上，**但真实工程里它们解决的根本是不同抽象层级的问题**：

- **OpenRouter = 模型路由层**——解决"我有 100 个 model，怎么用一个 key、一个 URL、一套计费来切换"，对应 ISO 7 层网络模型里的"transport"——只关心数据从 A 到 B；
- **Vercel AI SDK = 前端 streaming 套件**——解决"我前端怎么把 token 流式渲染、怎么把 tool call 串到 UI、怎么管理 chat 历史"，对应"presentation"层；
- **LangGraph = agent 状态机运行时**——解决"我有 5 个 agent、要走一个 planner → executor → verifier → human-in-loop → retry 的图，状态要 checkpoint、要时间旅行"，对应"session"层；
- **TreeQuest = test-time compute 引擎**——解决"我这个难任务，怎么花更多 token 换更高准确率上限"，对应"application"层。

**4 个抽象层级，4 个分工，1 个工程师栈**。一个真实的生产架构很可能长这样：

> 用户 → Vercel AI SDK 前端流式 → LangGraph 编排 agent 图 → 在 LangGraph 的某个 node 内部嵌一段 TreeQuest 跑难推理 → TreeQuest 通过 OpenRouter 调底层 5 家模型 → 结果回流 LangGraph 的 state → 流式返回前端

这是"4 家正交叠加"的具体样貌，也是这一章后面所有分论的基础。把它记牢之后，下面这张大表就好看了：

### 7.1 横评大表

| 维度 | **TreeQuest** | **OpenRouter** | **Vercel AI SDK** | **LangGraph** |
|---|---|---|---|---|
| 定位 | 多 LLM 树搜索 / 推理增强 | LLM 路由网关 | TS/JS 统一 SDK + UI hooks | 有状态 Agent 图运行时 |
| 编程模型 | Python 库 + ``Callable`` 协议 | OpenAI 协议代理 | ``streamText / generateObject`` | ``StateGraph + nodes`` |
| 抽象层级 | application（test-time compute） | transport（路由） | presentation（前端） | session（状态机） |
| 语言 | Python ≥ 3.11 | 任意 HTTP | TypeScript 优先 | Python + TypeScript |
| 多模型协作 | **AB-MCTS + Thompson 采样**（并行试错） | 单请求自动选 1 个 | ``prepareStep`` 跨 step 切模型 | 节点级任意 LLM；supervisor 多 agent |
| Tool calling | 用户在 ``generate_fn`` 内自实现 | 透传上游 | 一等公民 ``tools + stepCountIs`` | 一等公民，可在节点里写 |
| 状态 / Memory | 搜索树 + 内建 checkpoint | 无 | 无内建（自管 chat history） | **核心卖点**：checkpointer + 时间旅行 + thread |
| 流式 / SSE | 节点级（拿到一个就 yield） | SSE 透传 | ``streamText / useChat`` 一等公民 | token 级 + 中间步骤事件 |
| 可观测 | 内建 D3 HTML 树渲染 | dashboard + spend logs | 自接 OTel | LangSmith（付费） |
| 部署复杂度 | 进程内库（最低） | SaaS（最低） | 嵌 Next.js / Node.js | Self-host / Cloud / BYOC |
| 主打场景 | ARC / Olympiad / SWE-Bench / ML 调参 | 多模型切换 / 价格优化 / failover | Chat UI / 流式 / 内容生成 | 复杂多 agent / HITL / 长程任务 |
| License | Apache 2.0 | 商业服务 | MIT（[官方仓库](https://github.com/vercel/ai)） | MIT（[官方仓库](https://github.com/langchain-ai/langgraph)） |
| 定价 | $0（仅付底层 token） | 充值 5.5% / BYOK 5%（首 1M req/月免费，[OpenRouter 教程](https://openrouter.ai/blog/tutorials/how-to-get-the-lowest-cost-llm-inference-on-openrouter/)） | MIT 免费，直付 token | 自托管 MIT 免费 / Cloud 按 $0.001/node + trace $0.50/1k（[LangGraph Pricing](https://www.langchain.com/pricing-langgraph-platform)） |

这张表读起来最容易跑偏的两件事，我先在这里提前拆掉——

第一，**"定价"那一行不是越便宜越好**。TreeQuest $0 的代价是 50-250 倍 LLM token 调用；LangGraph 自托管免费但 Cloud 按 node 计费——node 数量在长程 agent 里会非常多。**这一行只能横向对比同档投入，不能纵向比谁更便宜**。

第二，**"多模型协作"那一列里**，OpenRouter 的"单请求选 1 个"和 TreeQuest 的"AB-MCTS"是两种完全不同语义的"多模型"。OpenRouter 的"多"是**横向比价 / failover**（这次用 DeepSeek、下次用 Claude），TreeQuest 的"多"是**纵向接力**（同一道题让 3 家轮采，互相接住对方的盲点）。把两者混为一谈是中文社区最常见的错误——上面已有 [andrew.ooo 横评](https://andrew.ooo/answers/sakana-rl-conductor-vs-langgraph-vs-crewai-orchestration-may-2026/) 在 May 2026 那篇文里详细拆过。

### 7.2 用配套源码把这张表跑成数据

光看表不够直观。配套仓库的 [multi_orchestrator_compare.py](https://github.com/LDZKKJ/llm-work/tree/main/chapters/chapter-20-llm-orchestrator-treequest) 实现了 4 种风格在同一个 fake LLM 池上各跑一遍，30 trials 的均值结果：

```
>>> 4 风格横评（n_trials=30, budget=12）
style             score_mean  score_p90   calls   tokens   cost(USD)
----------------------------------------------------------------------
openrouter        0.490       0.591        1.0     1920  0.00276
vercel_ai_sdk     0.539       0.634        2.0     3000  0.00852
langgraph         0.613       0.686        3.5     6373  0.01122
treequest         0.970       1.000       12.0    20833  0.04394
```

**读法**：

- 从 OpenRouter 到 TreeQuest，调用次数从 **1 → 12**，单任务 cost 从 **$0.003 → $0.044**（~16 倍），但 score_mean 从 **0.49 → 0.97**（+96% 准确率提升）；
- LangGraph 单次任务用 3.5 次调用打到 0.61 分，对应"中等难度任务的工程合理点"——大多数生产 agent 落在这个档位；
- Vercel AI SDK 2 次调用 0.54 分则是"前端流式 + 必要时切高端模型"的最小工程组合；
- TreeQuest 的 0.97 不是"它最强"，而是"它**愿意花最多 token 换最高质量上限**"——其它三家不能选这个模式，并不是因为它们能力不够，而是它们的设计初衷不是 test-time compute 而是别的层。

**这张数据再次印证了"正交而非替代"**——如果你在 chat / 自动补全 / 客服 Bot 场景，TreeQuest 的 16× 成本绝对不划算；如果你在 ARC / Olympiad / SWE-Bench 场景，OpenRouter 单跑的 0.49 分根本进不了门。**选谁不取决于"哪家最好"，取决于"你的任务在哪个抽象层"**。

## 八、四家分论：什么时候选谁

### 8.1 OpenRouter——模型路由层的事实标准

**心智模型**：把它想成"AI 时代的 Cloudflare"——你不会让一个 SaaS 直连 origin，你会让它走 Cloudflare；你也不会让一个 Agent 直连 OpenAI，你会让它走 OpenRouter。

**什么时候选它**：

1. 你有 ≥3 家上游模型要切换（DeepSeek + Claude + Gemini + ...），不想为每家维护一份 API key + 重试逻辑；
2. 你要做 failover——一家超时 / 限流 / 报 5xx 时自动切到另一家；
3. 你要做价格路由——业务流量按"廉价模型优先"、批处理走 :nitro / :floor 变种、个别请求走 BYOK；
4. 你需要一个统一计费 / spend log，方便给业务部门做账。

**OpenRouter 在 2026 上半年做对的 3 件事**：一是把"BYOK 前 100 万次免费 + 5% 超量"做成标准条款（[官方教程](https://openrouter.ai/blog/tutorials/how-to-get-the-lowest-cost-llm-inference-on-openrouter/)），让中型团队几乎"白嫖"路由能力；二是把 :free / :nitro / :floor 变种做成开发者直觉，一句话切换"低成本 / 最快 / 最便宜"路由（[klymentiev.com 解析](https://klymentiev.com/blog/openrouter-free-tier)）；三是把"周榜"做成开发者社区指标——18 号文已详细拆过 OpenRouter 周榜怎么读，比官方 benchmark 更接近真实工作负载。

**OpenRouter 在 2026 不该选它的 3 种场景**：第一，你的合规要求数据不能出公网代理——这种情况下要么 BYOK 直连、要么用 Azure / Bedrock 私有路由。第二，你的业务在 OpenRouter 不覆盖的小众模型上跑（一些区域性中文模型、自部署微调模型）。第三，你需要的不是路由而是 test-time compute——OpenRouter 一次只选一家，不会做接力。

### 8.2 Vercel AI SDK——前端 streaming 的事实标准

**心智模型**：把它想成"AI 时代的 React Server Components"——它把"流式 token + tool call + chat history + multi-step"这套现代 LLM 应用前端的最佳实践打包成了一个 SDK，让 Next.js / React / SvelteKit / Vue 应用接 LLM 像写 ``fetch`` 一样自然。

**什么时候选它**：

1. 你的产品是 Web 应用 / Chat 应用 / 内容生成器，需要把模型输出**流式**呈现给用户；
2. 你需要把 tool call 串到 UI（"AI 正在调用搜索…""AI 找到 3 条结果""AI 总结中…"），而不是等到最后一次性出来；
3. 你需要 ``streamText`` + ``stepCountIs`` 这种"模型自己决定走几步、什么时候 stop"的循环；
4. 你的团队是 TypeScript 工程师为主，不想在前端写 Python。

**Vercel AI SDK 的核心抽象**是 ``streamText`` / ``streamObject`` / ``generateText`` 三件套，加上 ``tools + stepCountIs`` 的多步循环、``prepareStep`` 的 step 间切模型能力。**它的设计哲学是"前端友好"**——你不需要理解 LangGraph 的 StateGraph、不需要写 Python、不需要部署一个 agent 运行时，你只需要在 Next.js 的 API route 里写一行 ``streamText({ model, messages, tools })``，前端用 ``useChat`` hook 渲染。这条路线对 90% 的"对话 / 内容生成 / 简单 agent" 场景已经够用。

**Vercel AI SDK 不该选它的场景**：第一，你需要长程状态、checkpoint、时间旅行——这是 LangGraph 的本职。第二，你的 agent 走多 agent supervisor 模式——SDK 的 ``stepCountIs`` 只是单链多步，不是多 agent。第三，你需要在 Python 后端做编排——SDK 的官方实现是 TypeScript 一等公民（[官方仓库](https://github.com/vercel/ai)）。

### 8.3 LangGraph——agent 状态机的事实标准

**心智模型**：把它想成"AI 时代的 Kubernetes"——你不会用 systemd 跑 100 个微服务，你会用 K8s；你也不会用 if-else 写一个 5 节点 agent，你会用 LangGraph。

**什么时候选它**：

1. 你的 agent 有 ≥3 个节点（planner / executor / verifier / human-in-loop / retry），状态要在节点间流动；
2. 你需要 checkpoint——长任务能断点续跑、能"时间旅行"回到第 3 步重新决策；
3. 你需要 human-in-the-loop——在某个节点中断、等人工审批、再继续；
4. 你需要可观测——LangSmith 把每个节点、每次调用、每次状态变更都记录下来。

**LangGraph 的核心抽象**是 ``StateGraph(State)`` + ``add_node`` / ``add_edge``，加上 ``checkpointer`` + ``thread_id`` 让一个 agent 实例可以挂起 / 恢复 / 分叉。**它的设计哲学是"agent 即状态机"**——把 LLM 调用、tool call、retry、HITL 全部抽象成"图上的节点 + 边的条件"，让复杂 agent 的逻辑可读、可测、可回放。

**LangGraph 在 2026 上半年做对的事**：第一是把 checkpoint + 时间旅行做成一等公民——这一点在长程 agent 容错上至关重要，[12 号文](../12-长程Agent容错_Checkpoint与Durable_Execution.md)有详细推演。第二是把 supervisor 模式做成内置——一个"主管 agent" 调度多个 "worker agent" 的拓扑模板可以一行代码挂上。第三是 LangSmith 把 trace 做成"图上每个节点 + 每条边"可视化，比传统 OTel 看 LLM 调用直观得多。

**LangGraph 不该选它的场景**：第一，你的任务是"难推理但简单工作流"（典型 ARC / Olympiad）——这种场景的关键不是状态机复杂度而是 test-time compute，应该选 TreeQuest。第二，你只是想做一个 chat 应用——LangGraph 的抽象在这里是过度工程化。第三，你的团队没有 Python——LangGraph 主力是 Python，TS 版本能力差一档。

### 8.4 TreeQuest——test-time compute 的事实标准

**心智模型**：把它想成"AI 时代的并发计算"——同样 30 秒里，单线程跑出来的答案 vs 32 线程协作跑出来的答案，后者的质量上限是前者达不到的；TreeQuest 在 token / 准确率维度做同一件事。

**什么时候选它**：

1. 你的任务有显式 [0,1] 评分函数——单元测试通过率、judge 分、ARC grid 比对都行；
2. 你的任务单次正确率 p_single 在 [0.2, 0.6] 之间——太低（<0.2）多次采样也救不回来，太高（>0.6）没必要；
3. 你能容忍 P99 ≥ 10 秒延迟——AB-MCTS 是顺序算法，并发受限；
4. 你的预算允许 8-32 倍于普通 chat 的 token 消耗。

**TreeQuest 的核心抽象**是 ``ABMCTSA() / ABMCTSM()`` + ``init_tree`` + ``step`` + ``top_k``，加上 generate_fn 作为 ``Callable[[parent_state], (state, score)]`` 协议。**它的设计哲学是"算法-provider 解耦"**——把搜索算法本身做到极简极薄，把 LLM 调用、评分器实现、并发管理全部留给用户。这是它和 LangGraph / Vercel AI SDK 哲学最不同的一处——它不试图给你"一整套抽象"，只给你"一个搜索器"。

**TreeQuest 在 2026 上半年做对的事**：第一是 PyPI 上线 v0.3.2（Feb 6）让普通 Python 工程师能 `pip install` 试。第二是把 ARC-AGI-2 Pass@250 23% → >30% 的实证写进官博，让"AB-MCTS 不只是论文里的"得到了开发者圈广泛背书。第三是把 Multi-LLM 接力的现象学（"o4-mini 错→DeepSeek 接力对"）做成 demo 截图——这个画面比任何论文都更能说服工程师"多模型协作"是真有用的事。

**TreeQuest 不该选它的场景**：第一，没评分函数的任务（chat / 创意 / 客服）——本文第二章已展开，这是它最大的限制。第二，实时任务（自动补全 / 流式 chat）——AB-MCTS 顺序性 + 50-250 次调用根本等不起。第三，你已经用得起 Conductor / Fugu——L3 商用 API 比自托管 TreeQuest 更省心，不过价格未公开，按 use case 算账。

---

## 九、组合食谱：3 个真实场景的"该叠哪几家"

回到本文一开始的论点——**4 家正交叠加**。下面给 3 个真实工程场景的选型 playbook，每个都是"叠几家"而不是"选一家"。

### 场景 A：受监管行业的"AI 知识库 Chat + 合规审批"

**典型业务**：金融 / 法律 / 医疗的内部知识库 Chat，用户问"客户 X 的 KYC 文件齐了吗"、"这份合同 A 条款合不合规"。

**选型 playbook**：
- **前端层**：**Vercel AI SDK** 的 ``useChat`` + ``streamText``，流式响应给业务用户；
- **状态机层**：**LangGraph** 的 ``StateGraph(planner → retriever → answerer → compliance_checker → human_approve)``，敏感问题进 HITL 由合规人员审核；
- **路由层**：**OpenRouter** BYOK 模式，把企业 Azure OpenAI / 私有 DeepSeek 部署挂上去，统一计费 + 审计；
- **难推理层**：**不需要 TreeQuest**——本场景大多是检索 + 简单总结，p_single >> 0.6，多次采样浪费 token。

### 场景 B：研发团队的"代码生成 / SWE-Bench 级修 bug agent"

**典型业务**：基于代码仓库的自动 PR 生成、bug 修复、refactor 建议。

**选型 playbook**：
- **前端层**：**Vercel AI SDK** 在 IDE 插件 / Web UI 里流式渲染 diff；
- **状态机层**：**LangGraph** 的 ``StateGraph(read_code → plan_change → write_patch → run_tests → reflect)``，``reflect`` 节点根据测试失败回退到 ``write_patch``；
- **难推理层**：在 ``write_patch`` 这个 node 内部嵌一段 **TreeQuest** AB-MCTS——把"测试通过率"当 evaluator，让 Gemini 2.5 Pro / Claude Sonnet 4 / DeepSeek-V4-Pro 三家轮采 patch，跑 budget=16 次取最优；
- **路由层**：**OpenRouter** 兜底——TreeQuest 的 ``generate_fn`` 通过 OpenRouter 一个 key 调三家模型，少维护 3 套 SDK。

这种叠法是 TreeQuest 的"高价值嵌入点"——只在最难的那一步用 AB-MCTS，其它步骤继续走简单的 single-call，整体 token 成本可控。

### 场景 C：B2B 深度研究 / 调研报告自动生成

**典型业务**：投行 / 咨询 / 研究院的"给我一份关于半导体行业的 100 页报告"。

**选型 playbook**（两条路）：

**路径 1：自建栈**
- **状态机层**：**LangGraph** 的 ``StateGraph(scope → multi_search → outline → section_writer × N → reviewer → composer)``，N 个 section 并行走；
- **难推理层**：每个 section_writer 内部用 **TreeQuest** AB-MCTS 跑 budget=24，evaluator 是 judge LLM 打"逻辑性 + 数据准确性 + 引用充分性"分；
- **路由层**：**OpenRouter** 调 5-8 家底层 LLM；
- **前端层**：**Vercel AI SDK** 把生成过程流式给业务用户看。

**路径 2：直接买 Sakana Marlin**
- ¥9,800/任务，跳过整套自建栈。Pro ¥150,000/月 + Team ¥400,000/月起，按调研频次算 break-even：当每月调研量 ≥ 15 次时 Pro 比按次便宜，≥ 40 次时 Team 划算。

我倾向的判断是：**当调研量 < 5 次/月、且报告标准化程度高（行业研究、市场分析）**，直接买 Marlin；**当调研量 ≥ 10 次/月、且每份报告内容定制化强（律所判例分析、医院特定病种研究）**，自建栈更划算——自建栈的边际单次成本会随调用量摊薄到 $50-200/份，比 Marlin ¥9,800 便宜 2-3 个量级。

## 十、开放问题：12 个月后这 4 层会被打通还是更分化

写到这里把本文主线再收一次——**4 家不是替代关系，4 家是 4 个正交层（路由 / 前端 / 状态机 / test-time compute）；选型不是"选谁"，是"叠哪几家"**。这条主线适用于 2026 上半年这个时点，但要预测 12 个月后还成不成立，**我倾向的判断是 4 层会同时朝两个方向走**：

**第一个方向是"被打通"**——头部厂商会越来越倾向于把 4 层并入一站式产品。OpenAI 的 Responses API + Tools + 流式响应已经在做"路由 + 前端 streaming + tool call"三层合一；Anthropic 的 Computer Use + Tool Use 在做"状态机 + tool call"两层合一；Sakana Fugu / Conductor 在做"路由 + 状态机 + test-time compute"三层合一。如果你是大厂的产品，叠 4 个 OSS 工具的工程成本最终会输给"一个 SDK 走天下"——这是平台层的自然收敛。

**第二个方向是"更分化"**——开源社区会反向把每一层做得更深更专。LangGraph 0.3 推出 functional API、Subgraph、Send/Command API；Vercel AI SDK 5 推出 UIMessageStream + Agent loop；OpenRouter 推出 :nitro / :floor / BYOK 三种路由变种；TreeQuest 推出 AB-MCTS-M（PyMC 混合贝叶斯版）+ checkpointing + 多模态 state——**每一层的边界都在被推开**，"4 家叠加"的工程价值反而会随着每层做深而提升。

我倾向的最终判断是：**未来 12 个月里"大厂一站式 vs 开源叠加"会形成 70:30 的市场分布**——70% 的应用（标准 chat / 标准 agent / 简单 tool use）会被"一站式"吃掉，30% 的高价值 / 高定制化 / 高合规场景留给"4 家叠加"。**TreeQuest 这条 test-time compute 路线刚好坐在那 30% 的核心位置**——任何依赖"显式打分 + 多模型接力 + 算力换质量上限"的场景，单一厂商的封装做不深，必须留给开源工具叠加。

但所有预测都建立在一个前提之上——**算力价格继续每年掉一半的速度**。如果 2027 价格曲线反转向上，"test-time compute 经济学"会被推翻，4 家正交叠加的故事就要重写。工程师在做 2026 选型时能做的是把架构做"可替换"：把 TreeQuest 嵌在 LangGraph 的一个 node 里，比把整个 agent 重写成 TreeQuest 容易回滚很多。

> 留一个开放问题给读者带走：**当 4 大编排器在 2027 年都被某个大厂打包进了"一站式 Agent API"，工程师还需不需要懂 AB-MCTS 这种底层算法？** 我倾向的判断是——会变成像今天的"GC 算法"那样：**99% 的工程师只需要会用，但当那 1% 出问题（OOM / Pause time / 难推理任务死锁）时，懂底层的人值钱 100 倍**。AB-MCTS 不会变成"过时知识"，它会变成"工程师从 P5 升 P7 的分水岭知识"。欢迎在评论区聊聊你们的真实选型路径。

---

## 配套资源

- **模型广场**（一站式调用 OpenAI/Anthropic/Gemini/DeepSeek/Qwen 等主流模型）：https://activity.ldzktoken.com/activity/index.html
- **本文配套源码**（LLM 编排器工具集：TreeQuest 最小实现 + 4 风格横评 + 成本曲线）：https://github.com/LDZKKJ/llm-work/tree/main/chapters/chapter-20-llm-orchestrator-treequest
