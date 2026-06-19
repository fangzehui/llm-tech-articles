# Chapter 02 - Token 成本追踪 Demo

本目录是文章《[02 Token 成本优化实战](../../02-Token成本优化实战.md)》的配套示例代码。

## 核心概念

- **Token 计数**：优先使用 tiktoken 精确计数，缺包时回退到字符 + 中文比例估算
- **多模型单价表**：输入价 / 输出价分开计算
- **用量分组聚合**：支持按 `model` 或业务 `tag` 分组，方便做月度成本复盘

## 文件清单

| 文件 | 说明 |
|------|------|
| `cost_tracker.py` | `count_tokens` + `CostTracker` 主类 |
| `requirements.txt` | 可选依赖 tiktoken |

## 快速开始

```bash
# 1. 安装依赖（tiktoken 可选，不装也能跑）
pip install -r requirements.txt

# 2. 跑 demo
python cost_tracker.py

# 3. 在你自己代码里使用
python -c "from cost_tracker import CostTracker; t=CostTracker(); t.record('gpt-pro', 'hello', 'world'); print(t.total_cost_usd())"
```

## 数据声明

`MODEL_PRICING_USD_PER_M` 中的单价仅作演示，实际请以厂商最新公告为准。

## 配套文章

- [02-Token成本优化实战.md](../../02-Token成本优化实战.md)
