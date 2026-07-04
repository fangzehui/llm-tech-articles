# Chapter 28 · DeepSeek-V3.2 二五折半年记 配套源码

半年（2025-09-29 至 2026-07-04）DeepSeek-V3.2 二五折档实测场景成本对齐工具集。

## 内容

- `src/scenario_scorer.py` — 4 维评分卡场景打分器（成本敏感度 / 上下文密度 / 质量容忍度 / 时延容忍度）
- `src/cost_quality_curve.py` — 主流四家 cost-per-quality 曲线绘制 + 2026-H1 快照
- `src/tier_router.py` — 多档 DeepSeek 路由伪代码（V3.2 二五折档 / V3 主档 / R1 推理档）+ 预算敏感度参数
- `tests/test_smoke.py` — 18+ 用例覆盖三段代码的核心路径与边界

## 快速开始

```bash
pip install -r requirements.txt
pytest -q tests/
```

## 数据日期

数据源截至 2026-07-04；DeepSeek 官方定价、Artificial Analysis 榜单、社区开发者反馈聚合。
定价与场景适配变化较快，请以 [DeepSeek 官方定价页](https://api-docs.deepseek.com/quick_start/pricing) 实时显示为准。

## License

MIT
