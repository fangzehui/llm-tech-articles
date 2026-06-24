# Chapter 20 - LLM 编排器选型工具集

本目录是文章《[20 大河豚 TreeQuest 源码精读 + 四大 LLM 编排器选型实录](../../20-TreeQuest源码精读_四大LLM编排器选型实录.md)》的配套示例代码。

## 项目介绍

把 2026 年 6 月这个时点上"LLM 编排器选型"这件事拆成两半：前半把 **Sakana TreeQuest / AB-MCTS** 的核心算法用最小可读的 Python 重写一遍——节点结构、Thompson 采样、三动作 step()、Multi-LLM 接力——共 ~250 行代码，方便照着改；后半把 **OpenRouter / Vercel AI SDK / LangGraph / TreeQuest** 四种风格用同一个 Fake LLM 池跑一遍，输出"调用次数 × token × 成本 × 准确率"的横评表，证明 4 家是正交的、可叠加使用。

- **`treequest_minimal.py`**：AB-MCTS 教学实现（``Node`` / ``ABMCTS.step`` / ``thompson_pick`` / 文本树渲染），全部用标准库；
- **`multi_orchestrator_compare.py`**：4 风格各跑一遍并输出 ``RunResult`` 横评，关键看 ``calls`` / ``tokens`` / ``cost`` / ``final_score`` 四个轴；
- **`cost_analyzer.py`**：``Pass@K`` 成本曲线 + 廉价 vs 旗舰 break-even 判别 + Multi-LLM 预算分配；
- **`tests/test_treequest.py`**：9 个 pytest 用例覆盖核心模块（节点 / Thompson / 单 LLM / Multi-LLM / 成本曲线 / break-even / 4 风格 / sample tasks / 渲染）。

> ⚠️ 本仓库定位是**工程参考 + 教学实现**而非生产级 SDK。生产部署请直接用官方 [SakanaAI/treequest](https://github.com/SakanaAI/treequest)（Apache 2.0），本仓库的 ``treequest_minimal.py`` 是"读懂原理 + 调试自家任务"的最小骨架。

## 文件清单

| 文件 | 说明 |
|------|------|
| `treequest_minimal.py` | ``Node`` / ``ABMCTS`` / ``thompson_pick`` / ``render_text_tree`` + 自带 demo |
| `multi_orchestrator_compare.py` | ``FakeWorker`` + ``run_openrouter_style`` / ``run_vercel_ai_sdk_style`` / ``run_langgraph_style`` / ``run_treequest_style`` + ``benchmark`` |
| `cost_analyzer.py` | ``ModelPrice`` / ``cost_curve`` / ``break_even_budget`` / ``multi_llm_pass_at_budget`` |
| `tests/test_treequest.py` | 9 个 pytest 用例（节点 / 采样 / 单多 LLM / 成本曲线 / break-even / 4 风格 / 样本 / 渲染） |
| `tests/conftest.py` | ``rng`` / ``simple_generators`` / ``sample_tasks`` 共享 fixture |
| `data/sample_tasks.json` | 3 类 demo 任务（ARC 风格 / 数学题 / 代码题），用于本地评分 |
| `requirements.txt` | 仅 ``pytest`` 必装，其它 ``openai`` / ``matplotlib`` 全是可选；通过 try/except 守卫退化 |

## 4 风格的"心智模型一句话"

| 风格 | 关键代码入口 | 调用次数 | 主打场景 |
|------|-------------|---------|---------|
| **OpenRouter**（模型路由） | `run_openrouter_style` | 1 | 多模型切换、价格优化、failover |
| **Vercel AI SDK**（前端 streaming） | `run_vercel_ai_sdk_style` | 2 | Chat UI、流式响应、用户感知延迟 |
| **LangGraph**（agent 状态机） | `run_langgraph_style` | 3-4 | 复杂多 agent、HITL、checkpoint |
| **TreeQuest**（test-time compute） | `run_treequest_style` | N=12-250 | 难推理（ARC/Olympiad/SWE-Bench） |

## 安装步骤

```bash
cd chapters/chapter-20-llm-orchestrator-treequest
pip install -r requirements.txt   # 实际只需要 pytest
```

> 即便只装了 ``pytest``，整个 ``tests/`` 也能完整跑过——所有强依赖都做了 ``try/except`` 守卫。

## 一行 Demo

```bash
# 1) 跑 AB-MCTS 最小 demo（伪数学题，3 个 fake LLM）
python treequest_minimal.py

# 2) 跑 4 风格横评（30 trials × 4 styles）
python multi_orchestrator_compare.py

# 3) 跑成本-准确率曲线 + 廉价 vs 旗舰 break-even
python cost_analyzer.py

# 4) smoke test 全绿
pytest tests/ -v
```

## 输出示意

### `python multi_orchestrator_compare.py`

```
>>> 4 风格横评（n_trials=30, budget=12）
style             score_mean  score_p90   calls   tokens   cost(USD)
----------------------------------------------------------------------
openrouter        0.490       0.591        1.0     1920  0.00276
vercel_ai_sdk     0.539       0.634        2.0     3000  0.00852
langgraph         0.613       0.686        3.5     6373  0.01122
treequest         0.970       1.000       12.0    20833  0.04394
```

**读法**：从 OpenRouter 到 TreeQuest，调用次数从 1 → 12，单任务 cost 从 $0.003 → $0.044（~16×），但 score_mean 从 0.49 → 0.97（**+96% 准确率提升**）。这正是 test-time compute 的核心经济学——花更多 token，换更高 Pass@1 上限。

### `python cost_analyzer.py`

```
>>> 单模型成本-准确率曲线（k=1..32）
模型=cheap  p_single=0.3  单次成本=$0.00036
    k    pass@k   cost(USD)      边际/+1%
    1     0.300     0.00036  $  0.00001
    2     0.510     0.00073  $  0.00002
    4     0.760     0.00146  $  0.00003
    8     0.942     0.00291  $  0.00008
   16     0.997     0.00582  $  0.00054
   32     1.000     0.01165  $  0.01758

>>> 给定 target_pass=0.85，廉价 vs 旗舰 谁更便宜？
  target=0.7    K_cheap=  4  K_flag=  2  cost_cheap=$0.0015  cost_flag=$0.1000  cheaper=cheap
  target=0.85   K_cheap=  6  K_flag=  3  cost_cheap=$0.0022  cost_flag=$0.1500  cheaper=cheap
  target=0.95   K_cheap=  9  K_flag=  4  cost_cheap=$0.0033  cost_flag=$0.2000  cheaper=cheap
```

**读法**：在 demo 价格 + 单次正确率假设下，"廉价模型 × 多次采样"在三档目标准确率上都比"旗舰单跑"更便宜——这正是 OpenRouter 周榜上 DeepSeek-V4-Flash 五连冠的成本逻辑（[18 号文](../../18-OpenRouter周榜实证_国产大模型选型决策.md)有详细推导）。

### `pytest tests/ -v`

```
tests/test_treequest.py::test_node_basic_ops PASSED                      [ 11%]
tests/test_treequest.py::test_thompson_pick_converges PASSED             [ 22%]
tests/test_treequest.py::test_ab_mcts_single_llm PASSED                  [ 33%]
tests/test_treequest.py::test_ab_mcts_multi_llm PASSED                   [ 44%]
tests/test_treequest.py::test_cost_curve_monotone PASSED                 [ 55%]
tests/test_treequest.py::test_break_even_cheap_vs_flagship PASSED        [ 66%]
tests/test_treequest.py::test_orchestrator_compare_dimensions PASSED     [ 77%]
tests/test_treequest.py::test_sample_tasks_loadable PASSED               [ 88%]
tests/test_treequest.py::test_render_text_tree_smoke PASSED              [100%]

============================== 9 passed in 1.84s ===============================
```

## 真实复现路径（接真实 LLM）

最小工作量是替换 `multi_orchestrator_compare.FakeWorker.invoke()`：

```python
# 把 FakeWorker.invoke 改成真实 LLM 调用
import openai
client = openai.OpenAI(base_url="https://openrouter.ai/api/v1",
                       api_key=os.environ["OPENROUTER_API_KEY"])

def invoke(self, parent_state, rng):
    resp = client.chat.completions.create(
        model=self.name,   # 例如 "deepseek/deepseek-chat" / "google/gemini-2.5-pro"
        messages=[{"role": "user", "content": str(parent_state or "你的任务...")}],
    )
    answer = resp.choices[0].message.content
    score = your_evaluator(answer)   # 0-1 评分函数自己写
    return (answer, score), score
```

把 ``treequest_minimal.ABMCTS`` 跑起来不需要任何额外改动，因为 ``generate_fns`` 是协议而不是绑定具体厂商。**模型广场入口在文末**。

## 数据声明

- ``sample_tasks.json`` 三类任务（ARC 风格栅格 / 两步代数 / 字符串去重代码）都是教学样本，未对接真实 ARC-AGI 数据集；生产级评测请用 [SakanaAI/ab-mcts-arc2](https://github.com/SakanaAI/ab-mcts-arc2) 官方仓库。
- ``cost_analyzer._demo_models`` 的价格量级取自 2026-06 公开定价，仅作教学示例，并非选型推荐。
- 单元测试不依赖任何真实 LLM 端点，方便嵌入 CI。

## 配套文章

- [20-TreeQuest源码精读_四大LLM编排器选型实录.md](../../20-TreeQuest源码精读_四大LLM编排器选型实录.md)
- **模型广场**（一站式调用 OpenAI / Anthropic / Gemini / DeepSeek / Qwen / MiMo 等主流模型）：https://activity.ldzktoken.com/activity/index.html
