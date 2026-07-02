# Chapter 24 - MCP 生态 12 个月观察工具集

本目录是文章《[MCP 生态 12 个月观察：从协议诞生到企业接入指南](../../任务产物/MCP生态12个月观察.md)》的配套示例代码。

## 项目介绍

从 Anthropic 2024-11-25 开源 MCP 至今，生态完成了从"实验协议"到"Agent 事实标准"的跃迁。这套工具集给企业负责人一份可直接用起来的三件套：

- **`mcp_registry_scanner.py`**：扫描官方/自建 Registry 快照，自动把 Server 按 `devtool / database / saas / cloud` 四大类分桶，产出 Top-N 报告和 CSV，用于内部准入评估；
- **`mcp_client_matrix.py`**：把公开信息汇总成"客户端 × 能力 × 传输"三维矩阵，支持按 capability/transport/kind 反查，输出 Markdown 表可直接贴进技术选型文档；
- **`mcp_adoption_analyzer.py`**：企业 MCP 接入 5 维（Auth / Permission / Observability / Registry / Governance）成熟度评估器，纯规则打分器，输出总分 + 等级（L0-L5）+ 瓶颈维度 + 下一步建议。

> ⚠️ 本仓库定位是**工程参考 + 决策工具**：数据是内置样本 + 公开信息汇总，不代表任何厂商的 SLA 承诺；打分模型是一个可读的启发式框架，具体权重请按内部治理调整。

## 文件清单

| 文件 | 说明 |
|------|------|
| `mcp_registry_scanner.py` | Registry 快照扫描 + 类别打标 + Top-N + CSV 导出 |
| `mcp_client_matrix.py` | 11 家主流 MCP 客户端的能力/传输/配置路径矩阵（可查询、可导出） |
| `mcp_adoption_analyzer.py` | 5 维度打分 + L0-L5 分级 + 瓶颈识别 + 下一步建议 |
| `data/registry_snapshot.json` | 16 条覆盖四大类的样本 Registry 记录 |
| `tests/test_smoke.py` | 18 个 pytest 冒烟用例（含 CLI 参数化） |
| `requirements.txt` | 仅需 pytest，脚本本身零外部依赖 |

## 三个工具与文章章节的对应关系

| 文章章节 | 工具 | 关键接口 |
|---------|------|---------|
| 三、生态全景之服务器分类 | `mcp_registry_scanner` | `classify()` / `category_stats()` / `render_report()` |
| 三、生态全景之客户端矩阵 | `mcp_client_matrix` | `CLIENT_MATRIX` / `find_clients_by_capability()` / `render_markdown_table()` |
| 四、企业接入的三大痛点 | `mcp_adoption_analyzer` | `AdoptionSurvey` / `analyze()` / `AdoptionReport` |

## 安装步骤

```bash
cd chapters/chapter-25-mcp-ecosystem-observation
pip install -r requirements.txt   # 仅 pytest 必装
```

## 一行 Demo

```bash
# 1) 扫描内置 Registry 样本
python mcp_registry_scanner.py

# 2) 只看 devtool 类 Server 并导出 CSV
python mcp_registry_scanner.py --category devtool --csv /tmp/mcp_devtool.csv

# 3) 打印客户端矩阵（Markdown）
python mcp_client_matrix.py --format markdown

# 4) 查询哪些客户端支持 elicitation 能力
python mcp_client_matrix.py --capability elicitation

# 5) 企业接入成熟度评估（内置 demo profile）
python mcp_adoption_analyzer.py --demo

# 6) 冒烟测试
pytest tests/ -v
```

## 输出示意

```
$ python mcp_registry_scanner.py
MCP Registry Snapshot Report
----------------------------------------
Total servers scanned : 16
Category distribution :
  - devtool  :    4 ( 25.0%)
  - database :    3 ( 18.8%)
  - saas     :    4 ( 25.0%)
  - cloud    :    3 ( 18.8%)
  - other    :    2 ( 12.5%)
Top publishers        :
  - io.github.modelcontextprotocol: 2
  - com.linear               : 1
  ...
```

```
$ python mcp_adoption_analyzer.py --demo
MCP Enterprise Adoption Report
========================================
Total score : 12 / 25
Level       : L2 (试点小流量)

Dimension breakdown:
  - auth          3/5  ( 60.0%)
  - permission    3/5  ( 60.0%)
  - observability 0/5  (  0.0%)
  ...
Bottlenecks : observability
Next steps :
  → Day 1 就把 OTel Instrumentation 加进 Gateway，session ID → trace ID 建立映射
```

```
$ pytest tests/ -v
tests/test_smoke.py::test_registry_snapshot_loadable                    PASSED
tests/test_smoke.py::test_registry_classification_covers_four_buckets   PASSED
tests/test_smoke.py::test_registry_filter_and_report                    PASSED
tests/test_smoke.py::test_registry_csv_export                           PASSED
tests/test_smoke.py::test_client_matrix_has_official_players            PASSED
tests/test_smoke.py::test_client_matrix_filter_by_capability            PASSED
tests/test_smoke.py::test_client_matrix_filter_by_transport             PASSED
tests/test_smoke.py::test_client_matrix_render_markdown_and_json        PASSED
tests/test_smoke.py::test_adoption_empty_survey_is_l0                   PASSED
tests/test_smoke.py::test_adoption_demo_profile_is_l3_plus              PASSED
tests/test_smoke.py::test_adoption_full_score_is_l5                     PASSED
tests/test_smoke.py::test_adoption_report_serializable                  PASSED
tests/test_smoke.py::test_main_cli_runs[mcp_registry_scanner-argv0]     PASSED
tests/test_smoke.py::test_main_cli_runs[mcp_registry_scanner-argv1]     PASSED
tests/test_smoke.py::test_main_cli_runs[mcp_client_matrix-argv2]        PASSED
tests/test_smoke.py::test_main_cli_runs[mcp_client_matrix-argv3]        PASSED
tests/test_smoke.py::test_main_cli_runs[mcp_adoption_analyzer-argv4]    PASSED
tests/test_smoke.py::test_main_cli_runs[mcp_adoption_analyzer-argv5]    PASSED
========================== 18 passed in 4.31s ==========================
```

## 数据声明

- `data/registry_snapshot.json` 是**内置样本**（16 条），选取原则是"覆盖四大类别 + 覆盖国内外厂商"，命名格式与 [官方 Registry](https://registry.modelcontextprotocol.io/) 保持一致，方便替换为真实快照。
- `mcp_client_matrix` 的数据基线整理自公开来源（截至 2026 年年中）：
  - Claude Desktop / Code、Cursor、Windsurf、Zed、Cline、Continue —— IDE 官方文档
  - ChatGPT Developer Mode —— OpenAI Responses API 公告（2025-05）+ InfoQ 报道（2025-10）
  - Microsoft 365 Copilot MCP —— devblogs.microsoft.com（2025-12 GA）
  - Gemini Code Assist / CLI —— developers.google.cn
- 打分模型的分档参考了 Anthropic 2025-11-25 规范中的"Security and Enterprise Features"，以及 arxiv:2605.22333 对真实 remote MCP 服务器 OAuth 缺陷的实测。

## 配套文章

- [MCP 生态 12 个月观察：从协议诞生到企业接入指南](../../任务产物/MCP生态12个月观察.md)
- 上一章 Chapter 19（[MCP 企业接入实战](../chapter-19-mcp-enterprise-toolkit/README.md)）提供的 Gateway + OAuth Middleware + Observability 可直接与本工具集拼接：**19 章解决"怎么接"，24 章解决"接得怎么样、缺什么"**。
- **模型广场**（支持 MCP 协议的主流模型一站式调用）：https://activity.ldzktoken.com/activity/index.html
