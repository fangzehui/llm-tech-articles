# Chapter 18 - OpenRouter 周榜抓取 + 选型信号分析

本目录是文章《[18 OpenRouter 周榜深读：连续 8 周中国超美国，企业 LLM 选型的信号与噪音](../../18-OpenRouter周榜实证_国产大模型选型决策.md)》的配套示例代码。

## 项目介绍

把 OpenRouter 每周公布的全球大模型调用量榜单做成一个**可订阅、可打分、可写周报**的小型监控管道，
覆盖从「抓取 → 解析 → 信号评分 → 报告 → 可视化」的完整链路。代码全部用标准库 + `matplotlib` + `pytest`，
没有 SDK 绑定，方便嵌入企业内部的模型评估系统。

## 核心概念

- **`WeekSnapshot`**：一周完整快照，统一描述 Top10 模型 / Top10 厂商 / 中美双边总量 / 历史趋势，下游所有模块的输入。
- **5 维度打分模型**：`call_volume_trend` / `price_trend` / `ecosystem_maturity` / `capability_match` / `substitutability`，每个维度 0-100，加权汇总后落到 `shortlist / trial / watch` 三档推荐。
- **能力卡（`CapabilityCard`）**：模型的**静态事实**（上下文长度 / 是否支持 thinking / 工具调用 / 价格），独立于周榜，便于按周更新。
- **三层抓取**：远端 API → 本地 sample JSON → 直接传 dict 构造，CI 友好。

## 文件清单

| 文件 | 说明 |
|------|------|
| `weekly_tracker.py` | `WeekSnapshot` / `ModelRow` / `VendorRow` + 抓取与解析 |
| `signal_analyzer.py` | `ScenarioProfile` + `CapabilityCard` + 5 维度打分模型 |
| `report_generator.py` | `full()` / `brief()` 两档 markdown 周报 |
| `visualize.py` | `draw_top_models_bar()` + `draw_weekly_trend()` |
| `data/sample_weekly.json` | 2026-06-15 ~ 21（W25）真实快照示例数据 |
| `tests/test_tracker.py` | pytest 风格 11 个用例：抓取、解析、信号、周报、可视化各覆盖 |
| `tests/conftest.py` | 共享 fixture：`snapshot` + `default_scenario` |
| `requirements.txt` | requests / pandas / matplotlib / pytest |

## 安装步骤

```bash
cd chapters/chapter-18-openrouter-weekly-tracker
pip install -r requirements.txt
```

## 一行 Demo

```bash
python weekly_tracker.py        # 打印本期 Top10 + 中美对比
python signal_analyzer.py       # 跑 5 维度打分 demo
python report_generator.py      # 输出完整周报 Markdown
python visualize.py             # 在 ./out 下生成 top_models.png 与 trend_v4_flash.png
pytest tests/ -v                # smoke test 全绿
```

## 输出示意

```
==== 场景：高频对话 + 工具调用，预算敏感 ====
模型                  厂商         综合    推荐
DeepSeek-V4-Flash     DeepSeek     84.5   shortlist
Xiaomi MiMo-V2.5      Xiaomi       82.1   shortlist
DeepSeek-V4-Pro       DeepSeek     78.4   trial
Qwen3.6 Plus          Alibaba      72.8   trial
GLM-5.2               Zhipu        69.1   trial
MiniMax M3            MiniMax      67.3   trial
...
```

## 数据声明

`data/sample_weekly.json` 中：
- **核心宏观数据**（全球总量 46.7T / 中国 18.81T / 美国 5.76T / DeepSeek-V4-Flash 4.94T / MiMo-V2.5 3.94T / MiniMax M3 3.77T / Hy3 preview 3.63T / Claude Opus 4.8 1.69T） 来自 OpenRouter 官方 rankings，经《每日经济新闻》于 2026-06-22 汇总发布，多源核验一致；
- **Top10 的 5-10 名、Top10 品牌的 2-10 名**：由于公开来源仅完整披露前 4 名与品牌榜首位，2-10 名数据是本仓库基于"中国总量 - 已披露模型 + 各厂商品牌份额"自洽估算，**仅用于 demo 与单测**，正文中标注为"区间估值"，请勿当作精确数据引用；
- **DeepSeek-V4-Flash 历史趋势**：来自正观新闻、东方财富等多家媒体周报的接续数据。

生产环境请把 `data/sample_weekly.json` 接到你监控到的 OpenRouter 内部 stats endpoint，
并在 `signal_analyzer.DEFAULT_CAPABILITY_CARDS` 里同步最新的能力卡。

## 配套文章

- [18-OpenRouter周榜实证_国产大模型选型决策.md](../../18-OpenRouter周榜实证_国产大模型选型决策.md)
- 模型广场（一站式调用本期榜上 DeepSeek-V4-Flash / 小米 MiMo / Claude / GPT 等）：https://activity.ldzktoken.com/activity/index.html
