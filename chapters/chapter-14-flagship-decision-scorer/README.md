# Chapter 14 - 旗舰大模型决策评分器

本目录是文章《[14 2026.6 旗舰大模型四强横评](../../14-2026.6_旗舰大模型四强横评.md)》的配套示例代码。

## 核心概念

- **四款旗舰建模**：GLM-5.2 / Claude Fable 5 / GPT-5 Preview / Gemini 3.0 Pro，每家给一份「能力 + 价格 + 合规 + SLA」画像
- **6 维加权打分**：编程 / Agent / 多模态 / 通用 / 价格 / 合规，权重由 `Scenario` 描述，业务方按场景调
- **合规与预算硬约束**：`require_cn_compliance=True` 或月度成本超预算时直接拦截，不参与排名
- **场景化推荐**：内置「业务流·客服 RAG」「研发·Agent 编程」「多模态·视频音频」三个示例场景，演示同一份模型表在不同场景下排名差异

## 文件清单

| 文件 | 说明 |
|------|------|
| `decision_scorer.py` | `ModelProfile` + `MODELS` + `Scenario` + `score_model` + `recommend` + 三个示例场景 |
| `test_smoke.py` | pytest 风格 7 个用例，覆盖注册表完整性 / 合规拦截 / 预算拦截 / 三场景推荐排名 |
| `requirements.txt` | 仅 pytest（运行测试时需要） |

## 快速开始

```bash
pip install -r requirements.txt
python decision_scorer.py            # 跑 demo，打印三个场景的推荐排名
pytest test_smoke.py -q              # 跑 smoke test
```

## 输出示意

```
=== 场景：业务流·客服RAG ===
  GLM-5.2              score= 86.7  cost=$220.0
  Claude Fable 5       合规不通过
  GPT-5 Preview        合规不通过
  Gemini 3.0 Pro       合规不通过

=== 场景：研发·Agent编程 ===
  Claude Fable 5       score= 79.x  cost=$xxx
  GPT-5 Preview        ...
```

## 配套文章

- [14-2026.6_旗舰大模型四强横评.md](../../14-2026.6_旗舰大模型四强横评.md)

## 数据声明

`MODELS` 中的能力分、价格、合规度、SLA 等级均为**示意数据**（综合自第 14 篇正文 § 三/四/五的整理），实际选型请以厂商最新官方公告与你自己的实测为准。
