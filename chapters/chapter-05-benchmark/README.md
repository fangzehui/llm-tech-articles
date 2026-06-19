# Chapter 05 - 主流大模型横评 Demo

本目录是文章《[05 2026 主流大模型 API 横评](../../05-2026主流大模型API横评.md)》的配套示例代码。

## 核心概念

- **结构化评测**：以 `BenchCase` + `BenchResult` dataclass 描述用例与结果
- **多模型并跑**：对同一组 prompt 在多个 mock 客户端上跑一遍，收集延迟与 token 数
- **聚合统计**：按模型给出 P50/P95 延迟、平均 token 用量、成功率

## 数据声明

`prompts.json` 是 6 条**示意用例**，并不是任何官方 benchmark 子集。  
真实横评的延迟数字会因网络、地域、具体 prompt 而变化，**实际数据请以厂商公告与你自己的实测为准**。

## 文件清单

| 文件 | 说明 |
|------|------|
| `benchmark_runner.py` | 评测脚本主入口 |
| `prompts.json` | 6 条评测用例 |
| `requirements.txt` | 仅依赖标准库 |

## 快速开始

```bash
pip install -r requirements.txt
python benchmark_runner.py
# 加 --dump 参数可以打印每条 case 的 raw 结果
python benchmark_runner.py --dump
```

## 配套文章

- [05-2026主流大模型API横评.md](../../05-2026主流大模型API横评.md)
