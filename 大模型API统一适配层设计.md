文件名：大模型API统一适配层设计.md

markdown
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
# 大模型API统一适配层设计：告别多平台注册与多Key管理
| 字节火山 | Doubao-Seed-2.0-pro | API Key | OpenAI兼容 |
每个平台都有：
- 独立的注册流程和审批机制
- 不同的计费体系和账单管理
- 各异的接口格式和错误码定义
- 各自的安全策略和限流规则
### 代码耦合的代价
如果你的代码直接调用各平台SDK：
```python
# 噩梦般的代码结构
class AIManager:
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_KEY"))
        self.anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_KEY"))
        self.google_client = genai.GenerativeModel(...)
        self.qwen_client = OpenAI(api_key=os.getenv("DASHSCOPE_KEY"), base_url="...")
        # ... 每加一个平台就要加一堆配置
    
    async def chat(self, model: str, prompt: str):
        if model.startswith("gpt-"):
            response = self.openai_client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        elif model.startswith("claude-"):
            response = self.anthropic_client.messages.create(
                model=model, messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        elif model.startswith("gemini-"):
            response = self.google_client.generate_content(prompt)
            return response.text
        # ... if-else 越写越长

这种模式的问题：

代码耦合严重：业务逻辑和模型调用强绑定
切换成本高：换个模型要改大量代码
测试困难：无法mock不同模型的响应
扩展性差：每加一个模型都要修改主类

OpenAI兼容协议设计

解决这个问题的核心思路是：让所有模型都"说"同一种语言。

OpenAI的API格式已经成为事实上的行业标准。大多数国内模型平台（Qwen、DeepSeek、豆包等）都提供了OpenAI兼容模式。对于国际模型（Claude、Gemini），我们可以通过适配层进行格式转换。

统一请求格式

python
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from enum import Enum
class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
class ChatCompletionRequest(BaseModel):
    """统一请求格式（兼容OpenAI API）"""
    model: str = Field(description="模型标识符")
    messages: List[ChatMessage] = Field(description="对话消息列表")
    
    # 可选参数
    temperature: Optional[float] = Field(default=0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=4096, ge=1)
    top_p: Optional[float] = Field(default=1.0, ge=0, le=1)
    frequency_penalty: Optional[float] = Field(default=0.0, ge=-2, le=2)
    presence_penalty: Optional[float] = Field(default=0.0, ge=-2, le=2)
    stop: Optional[Union[str, List[str]]] = None
    stream: bool = Field(default=False)
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    
    # 扩展字段
    extra_params: Optional[Dict[str, Any]] = Field(default_factory=dict)

统一响应格式

python
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
class UsageInfo(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
class ChatMessageResponse(BaseModel):
    role: str = "assistant"
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessageResponse
    finish_reason: Optional[str] = None
class ChatCompletionResponse(BaseModel):
    """统一响应格式"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: UsageInfo
    service_tier: Optional[str] = None
    
    # 扩展字段
    system_fingerprint: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "chatcmpl-123",
                "object": "chat.completion",
                "created": 1677652288,
                "model": "gpt-5.4",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "回答内容"
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150
                }
            }
        }

统一代理层实现

架构设计

plaintext
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
┌─────────────────────────────────────────────────────────────────┐
│                        客户端                                   │
│              (OpenAI SDK / HTTP Client)                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     统一代理层                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ 路由分发器  │  │ 格式转换器  │  │ 认证管理器  │             │
│  │             │→→│             │→→│             │             │
│  │ 模型→Provider│  │ OpenAI←→各 │  │ Key轮询/配额 │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ 限流器      │  │ 监控日志    │  │ 错误重试    │             │
│  │             │  │             │  │             │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Provider A     │ │  Provider B     │ │  Provider C     │
│  OpenAI格式     │ │  Anthropic格式  │ │  百度/谷歌格式 │
│  gpt-5.4等      │ │  claude系列    │ │  各厂商SDK    │
└─────────────────┘ └─────────────────┘ └─────────────────┘

核心代码实现

python
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
import httpx
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
import json
@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    supports_stream: bool = True
    timeout: int = 120
class BaseProvider(ABC):
    """模型提供商基类"""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.client = httpx.AsyncClient(

统一路由分发器

python
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
from typing import Dict
class ModelRouter:
    """模型路由：根据模型名分发到对应Provider"""
    
    def __init__(self):
        self.providers: Dict[str, BaseProvider] = {}
        self.default_provider: Optional[BaseProvider] = None
        
        # 模型到Provider的映射
        self.model_mapping = {
            # OpenAI
            "gpt-5.4": "openai",
            "gpt-5.4-mini": "openai",
            # Anthropic (通过合规渠道)
            "claude-sonnet-4-6": "anthropic",
            "claude-4-haiku": "anthropic",
            # Google (通过合规渠道)
            "gemini-3-pro": "google",

使用示例

python
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
import os
# 创建代理实例
proxy = UnifiedLLMProxy()
# 配置Provider（通过合规渠道获取国际模型API Key）
proxy.setup_providers({
    "openai": ProviderConfig(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key=os.getenv("OPENAI_API_KEY")
    ),
    # Anthropic Claude（通过运营商正规授权渠道）
    "anthropic": ProviderConfig(
        name="anthropic", 
        base_url="https://api.anthropic.com",
        api_key=os.getenv("ANTHROPIC_API_KEY")  # 合规渠道获取
    ),
    "qwen": ProviderConfig(
        name="qwen",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key=os.getenv("DASHSCOPE_KEY")
    ),
})
# 统一调用 - 代码完全相同，只需改model参数
async def main():
    request = ChatCompletionRequest(
        model="claude-sonnet-4-6",  # 切换模型只需改这里
        messages=[{"role": "user", "content": "解释一下量子计算"}],
        temperature=0.7,
        max_tokens=1000
    )
    
    response = await proxy.chat_completions(request, api_key="your-unified-key")
    print(response.choices[0].message.content)

合规渠道的价值

通过统一的适配层结合合规渠道，可以获得以下优势：

一个Key调所有模型：无需管理多个平台账号，一个统一API Key访问全球主流模型
代码零改动：使用OpenAI SDK，通过模型名切换，无需修改业务代码
合规保障：通过运营商正规授权渠道获取国际模型访问权限
成本可控：统一计量计费，支持按模型、按时段的成本分析

相关资源：

点点词元提供完整的统一适配层方案，一个API Key即可调用Claude、GPT、Gemini、Qwen、DeepSeek等全球主流模型，标准OpenAI兼容协议，SDK零改动接入
API文档：https://token.diandian.ai/docs

本文代码基于实际生产经验整理，供技术参考。

plaintext
1
2
3
4
5
---
这是第3篇的内容。GitHub第5篇上传完了吗？还是需要先补第3篇？
