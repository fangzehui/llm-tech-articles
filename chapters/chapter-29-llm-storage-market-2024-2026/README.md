# chapter-29-llm-storage-market-2024-2026

配套源码：《大模型时代存储市场复盘 2024-2026》

## 目录结构
```
chapter-29-llm-storage-market-2024-2026/
├── README.md
├── requirements.txt
├── src/
│   ├── kv_cache_tiered_storage.py       # KV-Cache 分层落盘策略
│   ├── checkpoint_cost_calculator.py     # 训练 checkpoint 分层存储成本计算器
│   └── embedding_cache_model.py          # 向量库 embedding cache 命中率成本模型
└── tests/
    ├── test_kv_cache_tiered_storage.py
    ├── test_checkpoint_cost_calculator.py
    └── test_embedding_cache_model.py
```

## 三段代码对应正文场景
| 段 | 源码 | 正文场景 |
|---|---|---|
| 1 | `src/kv_cache_tiered_storage.py` | 推理 KV-Cache 三层调度（HBM/温 NVMe/冷对象存储） |
| 2 | `src/checkpoint_cost_calculator.py` | 训练 checkpoint 分层归档账单（标准/低频/归档/深归档） |
| 3 | `src/embedding_cache_model.py` | RAG 向量库 embedding cache 命中率对总成本的边际影响 |

## 一键复现
```bash
pip install -r requirements.txt
pytest tests/ -v
```

## 定价参考（2026-07-06 截至）
- 阿里云 OSS 中国大陆刊例：标准 0.09 元/GB/月、低频 0.07 元/GB/月、归档 0.03 元/GB/月
- 腾讯云 COS 中国大陆刊例：标准 0.08 元起/GB/月、深度归档 0.01 元起/GB/月
- AWS S3 US East：Standard $0.023/GB/月、Deep Archive $0.00099/GB/月
- Pinecone Serverless：$0.33/GB/月 存储、$0.33/百万读单元
