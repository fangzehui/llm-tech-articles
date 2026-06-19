# Chapter 09 - 分级路由 Demo

本目录是文章《[09 分级路由策略实战](../../09-分级路由策略实战.md)》的配套示例代码。

## 核心概念

- **三档定档**：small / mid / flagship，每档配 1~N 个候选模型
- **三类触发**：显式 hint > 关键词命中 > token 长度兜底
- **配置驱动**：路由规则放在 `tier_config.yml`，业务方可改配置不动代码

## 文件清单

| 文件 | 说明 |
|------|------|
| `tier_router.py` | `TierRouter` + `RequestProfile` |
| `tier_config.yml` | 档位配置 |
| `requirements.txt` | 可选 PyYAML |

## 快速开始

```bash
pip install -r requirements.txt
python tier_router.py
```

无 PyYAML 时会自动 fallback 到 `default_tiers()`，仍然可跑。

## 配套文章

- [09-分级路由策略实战.md](../../09-分级路由策略实战.md)
