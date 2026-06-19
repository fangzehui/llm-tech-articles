# Chapter 04 - LLM 高可用三件套 Demo

本目录是文章《[04 生产环境 LLM 高可用方案](../../04-生产环境LLM高可用方案.md)》的配套示例代码。

## 核心概念

- **`with_timeout`**：单次调用硬超时（线程实现，避免无限等待）
- **`with_retry`**：指数退避 + 抖动，命中指定异常类型才重试
- **`CircuitBreaker`**：closed → open → half_open 三态熔断器，避免雪崩

三者组合后，业务函数即可获得「单点故障不传播 + 偶发抖动自动恢复」的能力。

## 文件清单

| 文件 | 说明 |
|------|------|
| `ha_demo.py` | 三个原语 + 组合用法 |
| `requirements.txt` | 仅依赖标准库 |

## 快速开始

```bash
pip install -r requirements.txt
python ha_demo.py
```

## 配套文章

- [04-生产环境LLM高可用方案.md](../../04-生产环境LLM高可用方案.md)
