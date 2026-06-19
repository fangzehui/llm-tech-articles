# Chapter 06 - 国产大模型 OpenAI 兼容 client Demo

本目录是文章《[06 国产大模型横评 2026 年中](../../06-国产大模型横评2026年中.md)》的配套示例代码。

## 核心概念

- **OpenAI 兼容协议作为最大公约数**：6 家国产主流厂商都提供 OpenAI 兼容 endpoint
- **VendorEndpoint registry**：把 base_url / 默认模型 / 备注集中管理
- **mock 模式 + 真实模式双轨**：脱网可跑 demo，正式接入时把 `_real_call` 替换为 `openai.OpenAI(base_url=...)`

## 数据声明

`vendors.yml` 与代码内 registry 中 base_url、模型名摘自各厂商公开文档，**实际请以厂商最新官方文档为准**。本目录不附带任何 benchmark 评分，原因是不同 case 的横评数据极易过期。

## 文件清单

| 文件 | 说明 |
|------|------|
| `domestic_benchmark.py` | `DomesticLLMClient` + 厂商注册表 |
| `vendors.yml` | 等价的 YAML 注册表 |
| `requirements.txt` | 可选 PyYAML 依赖 |

## 快速开始

```bash
pip install -r requirements.txt
python domestic_benchmark.py
python domestic_benchmark.py --dump   # 输出 JSON 注册表
```

## 配套文章

- [06-国产大模型横评2026年中.md](../../06-国产大模型横评2026年中.md)
