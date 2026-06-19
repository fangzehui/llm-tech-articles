# Chapter 10 - 语义缓存 Demo

本目录是文章《[10 语义缓存命中率工程实战](../../10-语义缓存命中率工程实战.md)》的配套示例代码。

## 核心概念

- **embedding + 余弦相似度**：用向量距离判断"语义近似"，比 hash key 命中率高一个量级
- **阈值是工程问题**：低了误命中、高了纯 miss，需要 ROC 校准
- **LRU + TTL**：避免缓存无限膨胀 + 让数据有"保质期"

## 文件清单

| 文件 | 说明 |
|------|------|
| `semantic_cache.py` | `SemanticCache` + `CachedLLM` |
| `requirements.txt` | 仅依赖标准库 |

## 关于 embedding 的简化

为了让 demo **完全脱网可跑**，本目录用了 hashing-trick 实现的极轻量 embedding。
生产请替换成 sentence-transformers / BGE / OpenAI text-embedding-3 等真实模型，
接口 `hashing_embed(text) -> list[float]` 直接替换即可。

## 快速开始

```bash
pip install -r requirements.txt
python semantic_cache.py
```

## 配套文章

- [10-语义缓存命中率工程实战.md](../../10-语义缓存命中率工程实战.md)
