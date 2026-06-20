# vLLM v0.23 vs SGLang vs TensorRT-LLM 三引擎企业自部署实测：吞吐 / 延迟 / 成本 / Agent 适配

> 自部署不是"省钱万能解"。三大主流引擎在 2026 年 6 月各自更新：vLLM v0.23 优化了 DeepSeek-V4 路径，SGLang 0.5.13 把多轮对话吞吐拉到新高，TensorRT-LLM 在 Blackwell 上把 FP8 推到了天花板。哪一款适合你？这篇做一次企业级横评。

## 一、引言：为什么 2026 中开始大量企业从 API 转向自部署

13 号文（《GLM-5.2 三通道实测》）和 14 号文（《2026.6 旗舰大模型四强横评》）解决的是"通过哪个云通道接入旗舰模型"的问题。但 2026 年 5 月开始，一个反向趋势在企业里加速：

- **API 价格被旗舰模型抬高**：Claude Fable 5 输出 $50/M，单月 10 亿 tokens 就是 $5 万。
- **DeepSeek-V4、Qwen3-Max、GLM-5.2 等开源旗舰模型质量已经能撑住 80% 业务流场景**：自部署的"产能瓶颈"被打开。
- **GB200 / B200 / H200 算力供给改善**：spot 实例 $2/hr 起，CPM（cost per million tokens）跌到 $0.15。

按 [GPU.NET 2026.06 实测](https://blog.gpu.net/posts/2026/june/new-blog-june09/) 的数据：

| 硬件 + 引擎 | 实例价 | 吞吐（70B 级） | CPM |
|---|---|---|---|
| H100 SXM + vLLM（17B 级） | $2.90/hr | 4,200 tok/s | $0.19 |
| H100 SXM + vLLM（70B FP8） | $2.90/hr | 1,500-2,500 tok/s | $0.32-0.54 |
| B200 spot + vLLM | $2.12/hr | 同档高 | **$0.15** |
| H200 SXM + 长上下文 | $2.60/hr | 比 H100 高 1.83-2.14× | $0.70 |

而 GLM-5.2 官方 API 价格 $0.6 + $2.0/M（输入 + 输出）——单从 token 单价看 **API 仍然便宜**，但企业一旦考虑：

1. **峰值并发 SLA 自主可控**（不被 API 配额掐脖子）；
2. **数据完全不出域**（合规、医疗、金融、政务硬要求）；
3. **场景化定制 LoRA / 微调**（API 通道不支持）；
4. **总规模 > 300M tokens / 月**（拐点之后自部署更便宜）；

自部署就成了"被迫选项"。问题在于：**vLLM、SGLang、TensorRT-LLM 三家主流引擎在 2026 年 6 月的能力差距，已经从"框架选型"变成了"百万级成本差"**。这篇做一次完整横评。

## 二、三引擎技术架构对比

三家走的是三条不同技术路线，理解架构就理解了性能差异从哪来。

### 2.1 vLLM：通用王者，PagedAttention 起家

- **核心技术**：PagedAttention（请求级 KV cache 分页）+ Continuous Batching（动态批处理）。
- **2026.06 v0.23 更新点**：DeepSeek-V4 1.6T MoE 路径优化、模型运行器 V2、Rust 前端、TransformerEngine v5 集成。
- **生态优势**：硬件支持广（NVIDIA / AMD / TPU / Trainium / Gaudi）、社区最大、Day 0 模型支持最快。
- **设计哲学**：**通用性优先**——单一抽象覆盖所有主流硬件，不为某一家硬件极致优化。

### 2.2 SGLang：Agent 时代新贵，RadixAttention 是杀手锏

- **核心技术**：RadixAttention（基于 radix tree 的跨请求 KV cache 复用）+ 零开销重叠调度（CPU/GPU 并行）+ 原生压缩 FSM（结构化输出）。
- **2026.06 0.5.13 更新点**：routing 预判、稀疏缓存、多轮对话场景吞吐 +65%，p99 延迟 -43%（数据来源：[MindLynx 实测](http://m.toutiao.com/group/7651802920437957154/)）。
- **生态优势**：在长共享前缀场景（多轮对话、Agent、RAG with system prompt）有断层优势。
- **设计哲学**：**为 LLM 程序优化**——把 Agent / 多轮 / 结构化输出作为一等公民，不是把它们当 vLLM 的"特殊用例"。

### 2.3 TensorRT-LLM：极致性能，硬件原生编译

- **核心技术**：AOT 编译 + 算子融合 + FP8/FP4 极致量化 + CUDA Graph。
- **2026 Blackwell 更新点**：B200 单卡 DeepSeek-R1（FP4）达 5,393 tok/s，相比 H100 提升 276%（数据来源：[CSDN Blackwell 实测](https://blog.csdn.net/weixin_35019679/article/details/155979650)）。
- **生态优势**：NVIDIA 硬件原生集成，FP8 / FP4 量化最深。
- **设计哲学**：**牺牲灵活性换极致性能**——绑定 CUDA / Hopper / Blackwell，编译时间换运行时性能。

### 2.4 一张图看懂三者定位

```
通用性 + Day 0 模型支持 ──────────────  vLLM
                                          ↓
长前缀复用 + Agent 优化  ──────────────  SGLang
                                          ↓
NVIDIA 硬件极致性能      ──────────────  TensorRT-LLM
```

## 三、性能横评：四场景 × 三引擎

测试基线（与社区主流 benchmark 对齐）：8×H200 SXM（141GB HBM3e/GPU），Llama-3.3-70B（4-bit GPTQ），混合工作负载。数据综合自 [掘金 vLLM/SGLang/TRT-LLM 横评](https://juejin.cn/post/7649934594186084392) 与 [aiwiki.ai/vllm](https://aiwiki.ai/wiki/vllm)。

### 3.1 吞吐量（tokens/s，越高越好）

| 工作负载 | vLLM v0.23 | SGLang 0.5.13 | TensorRT-LLM |
|---|---|---|---|
| Chat（32 并发） | 4,250 | 4,880 | **5,210** |
| RAG（16 并发，4K 上下文） | 2,200 | 2,310 | **2,480** |
| 批量摘要（16 请求） | 5,100 | 5,300 | **5,450** |
| 多轮对话（5 轮，前缀共享） | 3,200 | **8,100** | 4,800 |

**核心解读**：

- **TensorRT-LLM 在"独立请求"场景里有约 5%-22% 的吞吐优势**，但场景越简单优势越明显，场景越复杂优势越缩小。
- **SGLang 在"共享前缀"场景里有断层优势**——多轮对话从 vLLM 的 3200 tok/s 跳到 8100 tok/s，2.5 倍。这是 RadixAttention 的核心红利。
- **vLLM 综合表现"中庸"**：但生态、硬件覆盖、上手速度无人能敌。

### 3.2 延迟（512 token prompt）

| 引擎 | p50 TTFT | p99 TTFT | p50 TPOT | p99 TPOT |
|---|---|---|---|---|
| TensorRT-LLM | **75ms** | **118ms** | **7.6ms** | **12.4ms** |
| SGLang 0.5.13 | 79ms | 135ms | 7.9ms | 14.8ms |
| vLLM v0.23 | 88ms | 155ms | 8.5ms | 18.2ms |

**核心解读**：TTFT 维度 TRT-LLM 最优，但和 SGLang 差距已经压到 5%。**真正的延迟差距出现在 p99**——TRT-LLM 的尾延迟比 vLLM 低约 24%，这是企业 SLA 的关键指标。

### 3.3 显存占用（70B FP8 / 4-bit）

| 模型精度 | 显存 | 所需 GPU |
|---|---|---|
| Llama-3.3-70B BF16 | ~140GB | 8×H100（80GB） |
| Llama-3.3-70B FP8 | ~70GB | 4×H100 |
| Llama-3.3-70B INT4 (AWQ) | ~35GB | 2×H100 |

不同引擎在同一精度下的显存占用差异：TRT-LLM ≈ SGLang < vLLM（vLLM 通常多用 5-10GB 用于 PagedAttention 元数据）。

### 3.4 一句话定位

| 场景 | 第一选择 | 理由 |
|---|---|---|
| 7B-13B 小模型高频调用 | SGLang | +29% 吞吐优势（vs vLLM） |
| 70B+ 大模型独立请求 | TensorRT-LLM | FP8/FP4 极致 |
| 多轮对话 / Agent | **SGLang**（断层第一） | RadixAttention |
| 通用生产 / 跨硬件 | vLLM | 生态 + Day 0 |
| 国产硬件（Ascend / 海光） | vLLM | 硬件覆盖最广 |

## 四、成本测算：API vs 自部署的真实拐点

把 GLM-5.2 API 价（$0.6 + $2.0/M）和 Llama-3.3-70B 自部署成本对齐到 CPM：

### 4.1 自部署 CPM 计算公式

```
CPM = (实例小时单价 × 24 × 30) / (吞吐 × 86400 × 30 × 利用率) × 1,000,000
```

代入参数（H100 SXM @ $2.90/hr，70B FP8，吞吐 1,800 tok/s，利用率 60%）：

```
CPM = $2.90 × 720 / (1800 × 86400 × 30 × 0.6) × 1M
    = $2,088 / 2,799 M tokens
    ≈ $0.75/M
```

### 4.2 API vs 自部署 CPM 对比（70B 级）

| 方案 | 输入 CPM | 输出 CPM | 综合 CPM（4:1 输入输出） |
|---|---|---|---|
| GLM-5.2 API | $0.6 | $2.0 | $0.88 |
| 聚合平台中转（按官方价） | $0.6 | $2.0 | $0.88 |
| 自部署 H100 SXM + vLLM | - | - | $0.75 |
| 自部署 B200 spot + TRT-LLM | - | - | **$0.15** |
| 自部署 H100 SXM + SGLang（多轮） | - | - | **$0.30** |

### 4.3 拐点测算

假设企业月调用量 X（单位：M tokens），固定成本：

- 自部署：8×H200 集群租赁 ≈ $20,000/月（基础工程师工时另算）
- API：按上表 CPM 直接乘 X

**拐点公式**：`X × ($0.88 - $0.30) = $20,000` → **X ≈ 35,000 M tokens/月（350 亿 tokens/月）**

这个拐点对应的业务规模大概是：

- 一个月活 100 万的客服 SaaS 产品；
- 一个日均 1000 个 Agent 任务的企业自动化平台；
- 一家中型电商的全站智能问答 + 选品文案生成。

**90% 的企业达不到这个拐点**——所以"先 API、后自部署"几乎是默认路径，但部分对延迟、合规、定制化有硬要求的场景会提前自部署。

### 4.4 隐性成本不要忽略

自部署的 CPM 测算永远要把这三项加进去：

1. **GPU 利用率**：实测上线后利用率常年 30%-50%（流量不均）；不是 60%。
2. **Day N 运维**：模型升级、量化重训、监控告警、容错切换——平均 2 个全职工程师。
3. **冗余备份**：单点故障不可接受，最少 N+1 部署。

把这三项算进去，**70B 级 70% 中型企业的实际自部署 CPM 在 $0.6-$1.2/M**——和 API 单价交叉，所以"自部署一定省钱"是错觉。

## 五、部署难度：Day 0 vs Day N

| 维度 | vLLM | SGLang | TensorRT-LLM |
|---|---|---|---|
| 上手时间（首个模型 up） | 30 分钟 | 1 小时 | **1-3 天**（需编译） |
| 文档 / 示例完备度 | 极佳 | 良好 | 一般（NVIDIA 风格） |
| 模型兼容性 Day 0 | **极快**（DeepSeek-V4 当天） | 快 | 慢（等编译路径） |
| 生产 SLA 可靠性 | 高（经过最多生产验证） | 高 | 高 |
| 监控 / Tracing 集成 | OpenTelemetry 原生 | OpenTelemetry 原生 | Triton 集成 |
| 升级风险 | 中（API 偶尔 break） | 中 | 低（编译产物锁版本） |

**经验法则**：

- 团队 < 5 人 / 模型经常变 → **vLLM**。
- 团队 5-20 人 / 长程 Agent / 多轮对话为主 → **SGLang**。
- 团队 20+ 人 / 大模型 SaaS / 性能就是产品 → **TensorRT-LLM**。

## 六、Agent 适配性深度对比

13、14 号文最终都收敛到一个结论：**未来企业的 token 消耗 60% 以上来自 Agent 而不是普通对话**。Agent 工作负载的特征是：

- 系统提示词长（5K-20K tokens）；
- 多轮对话 / 工具调用频繁；
- 结构化输出（JSON Schema、function call）；
- 长程稳定性敏感（参考 12 号文 Checkpoint）。

### 6.1 系统提示词复用（前缀缓存）

| 引擎 | 命中策略 | 5K 系统提示 + 100 并发场景的吞吐增益 |
|---|---|---|
| vLLM | Block 级前缀缓存（默认 enable） | +40% |
| SGLang | RadixAttention（任意粒度） | **+250%** |
| TensorRT-LLM | KV cache reuse（编译时配置） | +60% |

### 6.2 结构化输出（JSON / Function Call）

| 引擎 | 实现 | 性能 |
|---|---|---|
| vLLM | Outlines 集成 | 中 |
| SGLang | 原生压缩 FSM + 并行 mask | **快**（约 vLLM 的 1.5-2×） |
| TensorRT-LLM | 受限（需要外部裁剪） | 一般 |

### 6.3 工具调用（Tool Call / Function Calling）

三家都通过 OpenAI 兼容接口提供 `tool_calls`，但**生产稳定性 SGLang ≥ vLLM > TRT-LLM**。SGLang 的 `function_call` 在长链路 Agent 下错误率最低（约 1.5%），vLLM 约 2.8%，TRT-LLM 约 4.2%（数据综合自社区报告）。

### 6.4 Agent 场景一句话推荐

> **Agent / 多轮 / 长程任务 → SGLang 第一选择，没有之一**。RadixAttention + 原生 FSM + 高稳定 tool_call 三件套是其它引擎短期内追不上的差距。

## 七、三档企业部署方案

按企业规模 + Token 量级，给三套可直接落地方案。

### 方案一：PoC 级（< 50M tokens / 月）

- **不要自部署**。
- 直接用 GLM-5.2 API 或聚合平台。
- 工程师专注业务逻辑，不要陷入推理引擎调优。

### 方案二：中规模生产（50M - 500M tokens / 月）

- **推荐**：单卡 / 双卡 H100，**vLLM v0.23**。
- 模型：GLM-5.2 / Qwen3-Max-Mini / Llama-3.3-70B FP8。
- 配套：K8s + HPA（基于 GPU 利用率自动伸缩）+ Prometheus + 容错降级到 API。
- 团队：1-2 人专职运维。

### 方案三：大规模平台（> 500M tokens / 月）

- **推荐**：8 卡 H200 / B200 集群，**SGLang（Agent / 多轮主场景）+ TensorRT-LLM（极致性能子集群）混合部署**。
- 模型：DeepSeek-V4 / GLM-5.2 / Llama-3.3-70B 多模型路由。
- 配套：分级路由（参考 9 号文）+ 语义缓存（参考 10 号文）+ 长程 Checkpoint（参考 12 号文）。
- 团队：5+ 人，含至少 1 名 GPU / CUDA 优化专家。

## 八、部署 YAML 实操

K8s 单 Pod 部署模板，三套都给：

### 8.1 vLLM v0.23 部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-llama3-70b
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: vllm
          image: vllm/vllm-openai:v0.23.0
          args:
            - "--model=/models/Llama-3.3-70B-Instruct-FP8"
            - "--tensor-parallel-size=4"
            - "--max-model-len=16384"
            - "--gpu-memory-utilization=0.92"
            - "--enable-prefix-caching"
            - "--max-num-seqs=64"
            - "--quantization=fp8"
          ports:
            - containerPort: 8000
          resources:
            limits:
              nvidia.com/gpu: "4"
          readinessProbe:
            httpGet: { path: /health, port: 8000 }
            initialDelaySeconds: 120
            periodSeconds: 10
```

### 8.2 SGLang 0.5.13 部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sglang-llama3-70b
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: sglang
          image: lmsysorg/sglang:v0.5.13-cu124
          args:
            - "python"
            - "-m"
            - "sglang.launch_server"
            - "--model-path=/models/Llama-3.3-70B-Instruct-FP8"
            - "--tp=4"
            - "--enable-radix-cache"
            - "--mem-fraction-static=0.85"
            - "--max-running-requests=128"
            - "--port=8000"
            - "--quantization=fp8"
          ports:
            - containerPort: 8000
          resources:
            limits:
              nvidia.com/gpu: "4"
```

### 8.3 TensorRT-LLM（Triton 后端）部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: trtllm-llama3-70b
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: triton
          image: nvcr.io/nvidia/tritonserver:24.05-trtllm-python-py3
          command: ["tritonserver"]
          args:
            - "--model-repository=/models/llama3-70b-trt"
            - "--http-port=8000"
            - "--allow-grpc=true"
            - "--grpc-port=8001"
          ports:
            - containerPort: 8000
            - containerPort: 8001
          resources:
            limits:
              nvidia.com/gpu: "4"
          # 注：TRT 引擎需提前 trtllm-build 编译并放入 model-repository
```

> 三套配置对应同样的 4×H100 70B FP8 部署，可以直接拿去 ApplyConfig + 调参。模型路径需要先下载到 `/models/`。

## 九、避坑指南

### 坑一：吞吐数字不能跨场景套用

社区 benchmark 多数是"单 prompt 独立请求"——和你真实业务（多轮 + RAG + tool call 混合）差距巨大。**永远跑自己业务流的 trace replay 测试**。

### 坑二：Day 0 模型支持差距很大

DeepSeek-V4 1.6T 在 vLLM / SGLang 当天就有可跑路径，TRT-LLM 用了 9 天才有完整编译路径（数据来源：[SemiAnalysis](https://newsletter.semianalysis.com/p/deepseekv4-16t-day-0-to-day-43-performance)）。如果你的业务依赖最新模型，TRT-LLM 不是首选。

### 坑三：FP8 量化精度损失场景化

代码生成、数学推理、长文档摘要场景对 FP8 精度损失敏感（约 1-3%），客服对话基本无感。**敏感场景上线前必跑离线 eval**——参考 1、6 号文评测体系。

### 坑四：监控体系跟不上

自部署的核心运维成本不在硬件，在监控。三件套必备：

- **GPU 利用率**（DCGM Exporter）
- **请求队列深度 + p99 延迟**（vLLM/SGLang/Triton 都暴露 Prometheus metrics）
- **OOM / KV cache 溢出告警**（必须前置告警，不能事后看）

### 坑五：忽略 SaaS 容错降级

自部署不是 100% 替代 API——**永远保留一条 API 容错通道**。当 GPU 节点故障 / 模型升级 / 流量暴涨时，自动 fallback 到 API（聚合平台或官方）能保证 SLA 不破。这是 4 号文（生产 LLM 高可用）的核心结论。

## 十、决策树 + 总结

```
月调用量 < 50M tokens？
├── 是 → 用 API / 聚合平台，不要自部署
└── 否 → 业务以 Agent / 多轮对话为主？
        ├── 是 → SGLang（70B+ 集群 / 4×H100 起）
        └── 否 → 单一通用业务流？
                 ├── 是 → vLLM v0.23（最稳，生态最好）
                 └── 否（极致性能 / 大规模 SaaS）→ TensorRT-LLM
```

**一句话总结**：

> 三引擎已经不是"性能差距"问题，而是"**场景适配 + 团队能力 + 模型生态**"三角的权衡。**默认起步 vLLM；Agent / 多轮场景升级 SGLang；极致性能场景叠加 TensorRT-LLM**——这是 2026 年中企业自部署最稳的三段式路径，配套 API 容错降级永远保留。

## 附录 A：参考资料

- vLLM 官方文档：[https://docs.vllm.ai](https://docs.vllm.ai)
- SGLang GitHub：[https://github.com/sgl-project/sglang](https://github.com/sgl-project/sglang)
- TensorRT-LLM GitHub：[https://github.com/NVIDIA/TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM)
- DeepSeek-V4 引擎横评（SemiAnalysis）：[https://newsletter.semianalysis.com/p/deepseekv4-16t-day-0-to-day-43-performance](https://newsletter.semianalysis.com/p/deepseekv4-16t-day-0-to-day-43-performance)
- vLLM vs SGLang vs TRT-LLM 横评（掘金）：[https://juejin.cn/post/7649934594186084392](https://juejin.cn/post/7649934594186084392)
- AI Inference 真实成本（GPU.NET）：[https://blog.gpu.net/posts/2026/june/new-blog-june09/](https://blog.gpu.net/posts/2026/june/new-blog-june09/)

> 注：以上资料截至 2026-06-19；推理引擎版本与 benchmark 数据迭代极快（vLLM 月度 release，SGLang 周度），决策落地前请以最新官方仓库与 release notes 为准。

## 附录 B：三引擎启动命令快查表

```bash
# vLLM v0.23（H100 ×4，70B FP8）
docker run --gpus all -p 8000:8000 \
  -v /models:/models \
  vllm/vllm-openai:v0.23.0 \
  --model /models/Llama-3.3-70B-Instruct-FP8 \
  --tensor-parallel-size 4 \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.92 \
  --enable-prefix-caching \
  --quantization fp8

# SGLang 0.5.13（H100 ×4，70B FP8）
docker run --gpus all -p 8000:8000 \
  -v /models:/models \
  lmsysorg/sglang:v0.5.13-cu124 \
  python -m sglang.launch_server \
  --model-path /models/Llama-3.3-70B-Instruct-FP8 \
  --tp 4 --enable-radix-cache \
  --mem-fraction-static 0.85 \
  --max-running-requests 128 \
  --quantization fp8 --port 8000

# TensorRT-LLM 编译 + 启动（H100 ×4，70B FP8）
# Step 1: 编译引擎（首次）
trtllm-build \
  --checkpoint_dir /models/llama3-70b-fp8/ \
  --output_dir /models/llama3-70b-trt/ \
  --gemm_plugin fp8 \
  --max_input_len 16384 --max_seq_len 32768 \
  --tp_size 4

# Step 2: Triton 启动
docker run --gpus all -p 8000:8000 -p 8001:8001 \
  -v /models:/models \
  nvcr.io/nvidia/tritonserver:24.05-trtllm-python-py3 \
  tritonserver \
  --model-repository=/models/llama3-70b-trt \
  --http-port=8000 --grpc-port=8001
```

## 附录 C：更新记录

- **v1.0** 2026-06-19 初版发布

后续如发现事实性偏差，会以本附录追加形式同步修订。

---

**相关资源**：

- [模型广场](https://activity.ldzktoken.com/activity/index.html)：[https://activity.ldzktoken.com/activity/index.html](https://activity.ldzktoken.com/activity/index.html)
  小程序"点点词元" — 多模型统一调度平台，OpenAI 兼容协议，Anthropic兼容协议。
- [GitHub 配套源码](https://github.com/fangzehui/llm-tech-articles)：[https://github.com/fangzehui/llm-tech-articles](https://github.com/fangzehui/llm-tech-articles) （含本文部署 YAML 与启动命令）

*本文性能数据综合自 vLLM / SGLang / TensorRT-LLM 官方发布、社区 benchmark 与企业生产实测，截至 2026-06-19；硬件价格、引擎版本、量化精度等可能在数周内更新，自部署落地前请以官方文档与最新 release notes 为准。CPM 测算公式可直接套用，但实际数字依赖企业自身利用率、运维成本与 SLA 设计。如发现事实性错误，欢迎评论区指正，会在附录 C 以 errata 形式同步修订。*
