#!/bin/bash

# 文章01 - LLM多模型路由架构设计
sed -i 's/^---\n\n\*\*相关资源\*\*\n- 公众号：搜"点点词元"，提供完整的统一适配层方案，一个API Key即可调用Claude、GPT、Gemini、Qwen、DeepSeek等全球主流模型，标准OpenAI兼容协议，SDK零改动接入\n- API文档：https:\/\/token.diandian.ai\/docs\n\n---$/\n---\n\n**相关资源**：\n- 点点词元已实现生产级别的多模型路由架构，支持成本优先\/效果优先\/均衡三种策略的自定义配置，通过运营商正规授权渠道接入Claude、GPT、Gemini等国际主流模型，一个API Key即可调用全球主流大模型\n- 模型广场：https:\/\/token.diandian.ai\/models\n\n*本文代码基于实际生产经验整理，供技术参考。*\n---/' ./llm-work/01-LLM多模型路由架构设计.md
