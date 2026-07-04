# Chapter 27 - 2026 上半年国产大模型 API 稳定性红黑榜工具集

本目录是文章《[2026 上半年国产大模型 API 稳定性红黑榜：9 家 90 天错误率 / P99 延迟 / 限流恢复实测](../../27-2026上半年国产大模型API稳定性红黑榜.md)》的配套示例代码。

## 项目介绍

从 2025-01-27 DeepSeek R1 那次全网热搜，到 2026 上半年 9 家国产大模型 API 陆续经历跨区路由抖动、429 限流未预告调整、依赖组件故障——**能力对齐之后，稳定性成了大模型 API 选型的最后一根标尺**。这套工具集把文章中的三段核心代码整理成可直接跑的模块 + pytest：

- **`src/error_rate_windower.py`**：90 天错误率窗口统计器。给一批已知的故障事件（开始时间、结束时间、影响面 ratio），滑动窗口计算加权错误率、逐 API 汇总、逐窗口趋势。
- **`src/fallback_router.py`**：熔断降级路由 dataclass。主-备-备2 顺序，支持"连续失败次数"+"P99 延迟上限"双触发的熔断器。
- **`src/multi_api_scheduler.py`**：多 API 冗余调度器。三维打分（可靠性 × 延迟 × 成本）× 三档任务级别（CRITICAL / STANDARD / BATCH），把选型决策显式化。

> ⚠️ 本仓库定位是**工程参考 + 决策工具**：所有事件数据均为公开 status 页与社区反馈聚合，不代表任何厂商 SLA 承诺或商业推荐；具体故障恢复时间与限流配额请以各家官方 status 页与运维公告实时显示为准。

## 文件清单

| 文件 | 说明 |
|------|------|
| `src/error_rate_windower.py` | 90 天错误率窗口统计 + 逐 API rollup + 滚动窗口序列 |
| `src/fallback_router.py`     | ProviderHealth / FallbackRule / choose_provider 熔断降级路由 |
| `src/multi_api_scheduler.py` | 9 家 API 三档任务级别评分 + Top-N 决策 |
| `data/incidents_2026h1.json` | 6 起公开事件样本（对应文章 90 天窗口） |
| `tests/test_smoke.py`        | 18 条 pytest 冒烟用例（覆盖三个模块） |
| `requirements.txt`           | 仅需 pytest，脚本零外部依赖 |

## 三个工具与文章章节的对应关系

| 文章章节 | 工具 | 关键接口 |
|---------|------|---------|
| 四、代码 1：错误率窗口统计器 | `error_rate_windower` | `Incident` / `error_rate_in_window()` / `rolling_error_rate()` / `api_level_rollup()` |
| 五、代码 2：熔断降级路由 | `fallback_router` | `ProviderHealth` / `FallbackRule` / `choose_provider()` |
| 六、代码 3：多 API 冗余调度 | `multi_api_scheduler` | `ProviderProfile` / `TaskTier` / `rank_providers()` / `top_n_for_tier()` |

## 安装步骤

```bash
cd chapters/chapter-27-llm-api-stability-report
pip install -r requirements.txt
```

## 一行 Demo

```bash
# 1) 错误率窗口统计器：内置 3 起样本事件，输出 API 级 rollup
python -m src.error_rate_windower

# 2) 熔断降级路由：模拟主 API 连续失败后自动切备份
python -m src.fallback_router

# 3) 多 API 冗余调度：三档任务级别各输出 Top-3
python -m src.multi_api_scheduler

# 4) 冒烟测试全绿
pytest tests/ -v
```

## 数据来源

红黑榜与事件数据来源于以下公开渠道，均可通过 URL 追溯：

- DeepSeek：[api-status.deepseek.com](https://api-status.deepseek.com/)
- 火山引擎 / 豆包：[status.volcengine.com](https://status.volcengine.com/)
- 阿里云百炼 / 通义：[status.aliyun.com](https://status.aliyun.com/)
- 腾讯云 / 混元：[status.cloud.tencent.com](https://status.cloud.tencent.com/)
- 百度智能云千帆：[cloud.baidu.com/support/notice](https://cloud.baidu.com/support/notice)
- 第三方压测参考：[artificialanalysis.ai](https://artificialanalysis.ai/)
- 社区反馈：V2EX / Reddit r/LocalLLaMA / GitHub 各官方 SDK 仓库 issue

## 相关章节

- [chapter-04-ha-pattern](../chapter-04-ha-pattern/)：生产环境 LLM 高可用方案，与本章"熔断降级路由"呼应
- [chapter-01-multi-model-router](../chapter-01-multi-model-router/)：LLM 多模型路由架构设计，与本章"多 API 冗余调度"呼应
- [chapter-26-china-llm-price-war](../chapter-26-china-llm-price-war/)：国产大模型价格战复盘 2024-2026，与本章"能力对齐后拼稳定性"衔接
- [chapter-12-checkpoint-recovery](../chapter-12-checkpoint-recovery/)：长程 Agent 容错，与本章"客户端 SDK 智能重试"展望呼应

## License

MIT
