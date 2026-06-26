# Chapter 22 - Agent AI 三大黄金赛道场景评估器

本目录是文章《[22 Agent AI 落地的三大黄金赛道](../../22-Agent_AI落地的三大黄金赛道.md)》的配套示例代码。

## 项目介绍

把"企业服务 / 工业制造 / 具身智能"三个 Agent AI 落地赛道做成一个**最小可读的场景打分器**：从五个维度（市场规模 / 技术成熟度 / 付费意愿 / 投资回报周期 / 准入门槛）量化每个场景，输出"赛道 ROI 排行 + 单场景 ROI 估算"。

- **`main.py`**：定义 `Scenario` / `roi_score()` / `rank_scenarios()`，覆盖 6 个具体落地场景（代码开发 Agent、合同审查 Agent、发酵罐 AI、整车质检 AI、分拣机器人、人形机器人）；
- **`tests/test_main.py`**：3 个 pytest 用例覆盖 ROI 单调性、排序稳定性和回收期推导。

## 安装步骤

```bash
cd chapters/chapter-22-agent-ai-vertical
pip install -r requirements.txt
python main.py
pytest tests/ -v
```

## 输出示意

```
>>> Agent AI 三大黄金赛道 - 场景 ROI 排行
scenario              vertical          market  maturity  willing_pay  payback  roi_score  payback(月)
------------------------------------------------------------------------------------------------------
代码开发 Agent          企业服务-通用       0.90    0.85       0.90       0.95      0.890         6
合同审查 Agent          企业服务-法律       0.70    0.85       0.95       0.90      0.840         8
发酵罐 AI Agent        工业-生物化工       0.65    0.80       0.85       0.90      0.795         9
整车质检 AI Agent      工业-汽车制造       0.75    0.80       0.80       0.85      0.795        10
分拣机器人 Agent       具身-物流仓储       0.85    0.75       0.75       0.80      0.790        12
人形机器人 Agent       具身-通用工厂       0.95    0.55       0.60       0.50      0.660        24
```

## 配套文章

- [22-Agent_AI落地的三大黄金赛道.md](../../22-Agent_AI落地的三大黄金赛道.md)
- **模型广场**（一站式调用 OpenAI / Anthropic / Gemini / DeepSeek / Qwen 等主流模型）：https://activity.ldzktoken.com/activity/index.html
