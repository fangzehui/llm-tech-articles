# Chapter 01 - 多模型路由器 Demo

本目录是文章《[01 LLM 多模型路由架构设计](../../01-LLM多模型路由架构设计.md)》的配套示例代码。

## 核心概念

- **多模型路由**：让一份业务代码可以无感切换 GPT / Claude / Qwen 等多家模型
- **路由策略**：在成本、质量、综合三种打分函数之间挑出最佳候选
- **主备切换 + 冷却**：调用失败时自动切到下一个候选，并把坏节点放入冷却池避免反复踩雷

注意：本 demo 重点演示"概念可跑"，生产级请求重试、限流、观测请参见仓库的 `routes/` 目录。

## 文件清单

| 文件 | 说明 |
|------|------|
| `router_demo.py` | 主入口，含 `MultiModelRouter` 与 3 个 mock provider |
| `requirements.txt` | 依赖（demo 仅依赖标准库） |

## 快速开始

```bash
# 1. 安装依赖（实际仅用到标准库 + 公共 mock_llm，无第三方）
pip install -r requirements.txt

# 2. 直接跑 demo
python router_demo.py

# 3. 在 REPL 里玩一下
python -c "from router_demo import build_demo_router; print(build_demo_router('cost_first').chat([{'role':'user','content':'hi'}]))"
```

## 输出示意

```
[cost_first]    -> qwen/qwen-mock     | [qwen/qwen-mock] echo: ...
[quality_first] -> openai/gpt-mock    | [openai/gpt-mock] echo: ...
[balanced]      -> qwen/qwen-mock     | [qwen/qwen-mock] echo: ...
```

## 配套文章

- [01-LLM多模型路由架构设计.md](../../01-LLM多模型路由架构设计.md)
