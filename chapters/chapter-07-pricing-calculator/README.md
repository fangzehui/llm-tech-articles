# Chapter 07 - 大模型价格计算器 Demo

本目录是文章《[07 大模型 API 价格全景图 2026.6](../../07-大模型API价格全景图2026.6.md)》的配套示例代码。

## 核心概念

- **统一口径**：所有价格统一换算到 `USD per 1,000,000 tokens`，避免人民币 / 美金 / 字符 / token 混乱
- **业务画像 → 月度成本**：从 `WorkloadProfile`（输入/输出 token + 日均请求数）反推每月账单
- **多模型对比 + 排序**：一次输入 12 款模型同时算账

## 数据声明

`pricing_data.json` 中的单价是占位示意数据，实际请以厂商最新官方公告为准。

## 文件清单

| 文件 | 说明 |
|------|------|
| `pricing_calculator.py` | `WorkloadProfile` + `estimate_monthly_cost` |
| `pricing_data.json` | 12 款模型的占位价格表 |
| `requirements.txt` | 仅依赖标准库 |

## 快速开始

```bash
pip install -r requirements.txt
python pricing_calculator.py
```

## 配套文章

- [07-大模型API价格全景图2026.6.md](../../07-大模型API价格全景图2026.6.md)
