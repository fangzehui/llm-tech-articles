# GLM-5.2 三通道智能路由器

本目录是技术文章 [《13-GLM-5.2 三通道实测：企业接入决策报告》](../../13-GLM-5.2_三通道实测_企业接入决策报告.md) 附录 B 承诺的"完整可跑配套源码"。第 7.5 节给的 ~50 行核心骨架在这里被扩展成了一个最小可用的生产参考实现，覆盖：

- **三通道 Provider 抽象**：智谱开放平台 / 国家超算互联网（SCNet）/ 自部署 vLLM-SGLang，OpenAI 兼容协议
- **主备容灾路由**：priority / cost 两种 fallback 策略 + circuit breaker（半开探测自动恢复）
- **三档 profile**：`realtime`（低延迟）/ `batch`（批量成本最优）/ `longctx`（超长上下文）
- **可观测性**：Prometheus 指标（latency / qps / error_rate / fallback_count / circuit_open）+ /status 调试端点
- **OpenAI 兼容协议**：FastAPI 实现 `/v1/chat/completions`，可作为 LLM 网关直接接业务
- **配套压测 / 评测脚本**：bench/ 与 eval/ 各一份，输出 JSON + Markdown

---

## 1. 快速开始

三步起步：

```bash
# 1. 准备凭据
cp .env.example .env
vim .env                      # 填入 ZHIPU_API_KEY / SCNET_API_KEY / SELFHOST_*

# 2. 选 profile（默认 realtime）
export ROUTER_PROFILE=profile_realtime  # 或 profile_batch / profile_longctx

# 3. 拉起最小栈
docker compose up -d

# 验证
curl http://localhost:8000/healthz
curl http://localhost:8000/status
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"你好"}]}'
```

启动后默认暴露：

| 服务 | 端口 | 用途 |
|------|------|------|
| router | 8000 | OpenAI 兼容 API、`/metrics`、`/status` |
| prometheus | 9090 | 指标抓取与查询 |
| grafana | 3000 | 可视化看板（默认 admin / admin） |

如果只想本地跑路由器（不要 docker）：

```bash
pip install -r requirements.txt
ROUTER_CONFIG=configs/profile_realtime.yml python router.py
```

---

## 2. Profile 配置说明

三种 profile 的设计对位文章第 6 章决策树：

| Profile | 适用场景 | 主通道 | 备通道 | 兜底 | fallback_strategy |
|---------|----------|--------|--------|------|-------------------|
| `realtime` | 交互式对话、实时问答、Agent 主线 | 智谱官方 | SCNet | 自部署 | priority |
| `batch` | 离线批处理、内容审核、大规模标注 | SCNet | 自部署 | 智谱官方 | cost |
| `longctx` | 100K-1M token 长文档 / 代码库审计 | 自部署 | SCNet | 智谱官方 | priority |

切换方式：

```bash
# 方式 1：环境变量
ROUTER_CONFIG=configs/profile_batch.yml python router.py

# 方式 2：docker-compose
ROUTER_PROFILE=profile_longctx docker compose up -d
```

YAML 字段含义：

```yaml
providers:
  - name: zhipu                  # zhipu | scnet | self
    base_url: ...                # OpenAI 兼容根路径，不含 /chat/completions
    api_key_env: ZHIPU_API_KEY   # 从该环境变量读 token
    model_alias: glm-5.2         # 通道侧的真实模型名
    priority: 10                 # priority 策略下数字越小越优先
    weight: 1.0                  # 预留权重位（后续支持 weighted）
    timeout_s: 15.0              # 单次请求超时
    cost_per_million_tokens: 22  # cost 策略下用于排序，单位元/百万 token
    enabled: true

router:
  fallback_strategy: priority    # priority | cost
  circuit_breaker:
    failure_threshold: 0.5       # success_rate 跌破即熔断
    cooldown_s: 60               # 熔断窗口
    half_open_success_rate: 0.8  # 半开恢复初值
    smoothing_alpha: 0.1         # EMA 平滑系数

observability:
  health_check_interval_s: 30
  health_check_timeout_s: 5.0
```

---

## 3. 压测脚本

```bash
# TTFT / 端到端延迟（短/中/长 prompt × P50/P95）
python bench/run_latency.py --base-url http://localhost:8000 --runs 50

# QPS / 成功率（多并发档）
python bench/run_throughput.py --base-url http://localhost:8000 \
    --concurrencies 1 4 16 64 --duration 30
```

输出在 `bench/results_latency.{json,md}` 与 `bench/results_throughput.{json,md}`。原文表格的指标采集就是同一套脚本，可直接复现。

---

## 4. 回归评测

```bash
# 准备数据集（按 eval/datasets/README.md 自行下载）
ls eval/datasets/gsm8k_test.jsonl eval/datasets/humaneval_test.jsonl

# 仅用前 20 条样本做快速烟囱测试
python eval/run_eval.py --base-url http://localhost:8000 --benchmark gsm8k --limit 20
python eval/run_eval.py --base-url http://localhost:8000 --benchmark humaneval --limit 20
```

完整 HumanEval 严肃评测请配合官方沙箱执行；本脚本只做"代码块是否正确生成"的烟囱判定。

---

## 5. 单元测试

```bash
pip install -r requirements.txt
pytest tests/ -v
```

8 个用例覆盖：provider 选择、fallback 触发、circuit breaker 开断与恢复、metrics 暴露、OpenAI 协议兼容性、错误请求处理。所有用例通过 mock provider 实现，不依赖真实 API Key。

---

## 6. 工程取舍说明

承接文章第 7.5 节的设计取舍，这里再补四点本仓库的实现选择：

1. **健康检查用后台 task 而不是同步阻塞**——避免 health check 自身的网络抖动放大到主链路；
2. **circuit breaker 用 EMA 而不是滑动窗口**——内存占用 O(1)，对突发抖动有平滑作用；半开恢复初值取 0.8 是给恢复中的通道试探机会但不放全量；
3. **profile 用 YAML 而不是代码常量**——改 fallback 链不用发版，符合"配置 ≠ 代码"的工程纪律；
4. **指标按 `profile × channel × outcome` 切片**——这三维度缺哪一个都会让线上排查"拍脑袋"，文章第 8 章第 5 条已经强调过。

---

## 7. 目录结构

```
routes/glm-5.2-tri-channel/
├── README.md                  # 本文件
├── router.py                  # 核心路由器（FastAPI app）
├── configs/
│   ├── profile_realtime.yml   # 低延迟优先
│   ├── profile_batch.yml      # 批量成本最优
│   └── profile_longctx.yml    # 超长上下文
├── bench/
│   ├── run_latency.py         # 延迟压测
│   ├── run_throughput.py      # 吞吐压测
│   └── prompts/               # 短/中/长 prompt 样本
├── eval/
│   ├── run_eval.py            # GSM8K / HumanEval 快速回归
│   └── datasets/README.md     # 数据集获取说明
├── tests/
│   └── test_router.py         # 8 个 pytest 用例
├── docker-compose.yml         # router + prometheus + grafana
├── prometheus.yml             # Prometheus 抓取配置
├── Dockerfile                 # python:3.11-slim
├── requirements.txt           # 锁版本依赖
├── .env.example               # 环境变量样例
└── .gitignore
```

---

## 8. 许可与归属

源码采用 MIT 许可（见仓库根 LICENSE）。

配套文章：[13-GLM-5.2 三通道实测：企业接入决策报告](../../13-GLM-5.2_三通道实测_企业接入决策报告.md)
