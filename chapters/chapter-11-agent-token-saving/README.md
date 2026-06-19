# Chapter 11 - Agent Token 降本 4 条工程路径 Demo

本目录是文章《[11 Agent Token 降 75% 4 条工程路径](../../11-Agent_Token降75%_4条工程路径.md)》的配套示例代码。

## 核心概念

| 路径 | 类 / 模块 | 关键想法 |
|------|----------|---------|
| 路径 1 执行链路裁剪 | `PathCut` | 高置信度时跳 replan / 子任务少时跳反思 |
| 路径 2 上下文压缩 | `ContextCompressor` | 滑动窗口 + tool 结果截断 |
| 路径 3 模型分级路由 | `TierDispatch` | 按 subtask 类型选 small / mid / flagship |
| 路径 4 Prompt Cache | `PromptCache` | 模拟 prefix caching，高频前缀只算一份 |

四条路径都是**乘性叠加**：单独任何一条只能省几个百分点，组合起来才有量级差距。

## 文件清单

| 文件 | 说明 |
|------|------|
| `agent_demo.py` | 4 个工具类 + `run_agent` 主循环 |
| `requirements.txt` | 仅依赖标准库 |

## 快速开始

```bash
pip install -r requirements.txt
python agent_demo.py
```

## 配套文章

- [11-Agent_Token降75%_4条工程路径.md](../../11-Agent_Token降75%_4条工程路径.md)
