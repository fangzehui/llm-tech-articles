# Chapter 08 - 企业级 Token 配额管理 Demo

本目录是文章《[08 企业级 LLM Token 成本治理架构](../../08-企业级LLM-Token成本治理架构.md)》的配套示例代码。

## 核心概念

- **InMemoryRedis**：用纯内存实现 redis 命令的最小子集（`get` / `incrby` / `expire` / `ttl`）
  生产环境直接换成 redis-py，接口完全对得上
- **两段式记账**：先按估算值 `reserve`，调用结束后用真实 token 数 `commit` 回填差额
- **多维度配额**：按 `(tenant, day)`、`(tenant, month)` 双桶限额，并支持 80% 软警告

## 文件清单

| 文件 | 说明 |
|------|------|
| `quota_manager.py` | `InMemoryRedis` + `QuotaManager` |
| `requirements.txt` | 仅依赖标准库 |

## 快速开始

```bash
pip install -r requirements.txt
python quota_manager.py
```

## 接入真实 Redis 的改造点

```python
import redis
r = redis.Redis(host="localhost", port=6379, decode_responses=True)
qm = QuotaManager(r, QuotaPolicy(daily_token_limit=...))
```

只需把 `InMemoryRedis()` 换成 `redis.Redis(...)` 即可，剩余逻辑无需改。

## 配套文章

- [08-企业级LLM-Token成本治理架构.md](../../08-企业级LLM-Token成本治理架构.md)
