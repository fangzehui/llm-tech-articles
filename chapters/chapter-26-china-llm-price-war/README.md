# Chapter 26 - 国产大模型价格战复盘工具集（2024-2026）

本目录是文章《[国产大模型价格战复盘 2024-2026：24 个月里，谁在裸泳，谁在赚安静的钱](../../llm-work/26-国产大模型价格战复盘_2024-2026.md)》的配套示例代码。

## 项目介绍

从 2024-05-11 智谱打响第一枪、到 2025-02-26 DeepSeek 用错峰优惠定义全球价格锚、再到 2026-Q2 主流国产模型稳定在"输入 0.5-4 元/M、输出 2-16 元/M"档位，24 个月的价格战沉淀出三件可复用工具：

- **`src/price_timeline.py`**：24 个月价格战关键节点数据集（15+ 条 PriceEvent），支持按厂商 / 冲击波筛选、JSON 导出、Markdown 渲染；
- **`src/cost_compare.py`**：6 家主流国产模型 2026-Q2 月账单对比脚本，支持排名、Markdown 渲染，一行代码代入自家 token 消耗和缓存命中率；
- **`src/pricing_sensitivity.py`**：定价可持续性判定器（真降本 vs 烧钱补贴），支持有效单价 / 毛利率计算。

> ⚠️ 本仓库定位是**工程参考 + 决策工具**：所有价格数据均为 2026-Q2 公开定价页快照 + 权威媒体报道汇总，不代表任何厂商 SLA 承诺或商业推荐；具体价格档位与折扣规则请以各家官方定价页实时显示为准。

## 文件清单

| 文件 | 说明 |
|------|------|
| `src/price_timeline.py` | 15+ 条价格战关键节点 + 按厂商/冲击波筛选 + JSON / Markdown 导出 |
| `src/cost_compare.py`   | 6 家主流模型月账单对比 + 排序 + Markdown 表 |
| `src/pricing_sensitivity.py` | 有效单价 + 可持续性判定 + 毛利率 + 内置 3 个样本场景 |
| `data/price_snapshot_2026q2.json` | 6 家模型价格快照（对应 `MODELS_2026Q2`） |
| `data/timeline_events.json` | 时间线元数据（冲击波定义与数据源说明） |
| `tests/test_smoke.py` | 20 条 pytest 冒烟用例（覆盖三个模块 + 集成交叉验证） |
| `requirements.txt` | 仅需 pytest，脚本零外部依赖 |

## 三个工具与文章章节的对应关系

| 文章章节 | 工具 | 关键接口 |
|---------|------|---------|
| 二、24 个月完整时间线 | `price_timeline` | `TIMELINE` / `events_by_wave()` / `render_markdown_table()` |
| 四、成本视角：真降本 vs 烧钱换量 | `pricing_sensitivity` | `is_sustainable_cut()` / `margin_ratio()` / `analyze()` |
| 六、可复现的成本对比表 | `cost_compare` | `MODELS_2026Q2` / `monthly_cost()` / `rank_by_cost()` |

## 安装步骤

```bash
cd chapters/chapter-26-china-llm-price-war
pip install -r requirements.txt   # 仅 pytest 必装
```

## 一行 Demo

```bash
# 1) 打印 24 个月价格战时间线统计
python -m src.price_timeline

# 2) 6 家模型月账单对比（默认场景：月 10 亿输入 + 3 亿输出、缓存命中率 50%）
python -m src.cost_compare

# 3) 定价可持续性判定（内置 3 个样本）
python -m src.pricing_sensitivity

# 4) 冒烟测试
pytest tests/ -v
```

## 数据来源

时间线与价格数据均来自公开权威媒体与厂商官方公告，主要包括：

- 新华网、新华社经济参考报、每日经济新闻、21 世纪经济报道、新京报贝壳财经、36 氪、腾讯新闻、证券时报、Forbes China
- 火山引擎、阿里云百炼、百度智能云千帆、腾讯云、DeepSeek、Moonshot 各家官方定价页与技术博客
- arXiv 论文（DeepSeek-V3 技术报告 2412.19437）

## 相关章节

- [chapter-17-prompt-cache](../chapter-17-prompt-cache/)：Prompt Caching 成本实测横评，与本章第四节 KV Cache 优化呼应
- [chapter-11-agent-token-saving](../chapter-11-agent-token-saving/)：Agent Token 降 75% 的 4 条工程路径，与本章 Agent 平台成本压力呼应
- [chapter-25-mcp-ecosystem-observation](../chapter-25-mcp-ecosystem-observation/)：MCP 生态 12 个月观察，价格战的下一个战场

## License

MIT
