# Chapter 12 - 长程 Agent Checkpoint Demo

本目录是文章《[12 长程 Agent 容错 Checkpoint 与 Durable Execution](../../12-长程Agent容错_Checkpoint与Durable_Execution.md)》的配套示例代码。

## 核心概念

- **Replay Boundary**：每个 step 完成后才落 checkpoint，重启时从最近一个 succeeded step 之后继续
- **原子写**：先写 `.tmp`，再 `os.replace` rename，避免半截 JSON 文件
- **幂等续跑**：同一个 run_id 多次调用 `runner.run` 不会重复执行 succeeded step

## 文件清单

| 文件 | 说明 |
|------|------|
| `checkpoint_demo.py` | `CheckpointStore` + `DurableRunner` |
| `test_smoke.py` | pytest 风格的 4 个用例 |
| `requirements.txt` | 仅 pytest（运行测试时需要） |

## 快速开始

```bash
pip install -r requirements.txt
python checkpoint_demo.py            # 跑 demo，演示一次失败 + 续跑
pytest test_smoke.py -q              # 跑 smoke test
```

## 配套文章

- [12-长程Agent容错_Checkpoint与Durable_Execution.md](../../12-长程Agent容错_Checkpoint与Durable_Execution.md)
