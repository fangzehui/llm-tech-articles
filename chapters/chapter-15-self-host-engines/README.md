# Chapter 15 - vLLM / SGLang / TensorRT-LLM 三引擎自部署

本目录是文章《[15 vLLM v0.23 vs SGLang vs TensorRT-LLM 三引擎自部署横评](../../15-vLLM_SGLang_TensorRT-LLM_三引擎自部署横评.md)》的配套部署清单与压测脚本。

## 三引擎一句话定位

- **vLLM v0.23**：通用生产首选，Day 0 模型支持最快，30 分钟可起首个 70B FP8 服务
- **SGLang 0.5.13**：Agent / 多轮对话场景断层第一（RadixAttention 让多轮对话吞吐 +250%）
- **TensorRT-LLM**：极致性能场景的天花板（B200 + FP4 单卡 5,393 tok/s），但需要 1-3 天编译路径

## 文件清单

| 文件 | 说明 |
|------|------|
| `deploy/vllm-deployment.yaml` | vLLM v0.23 K8s Deployment + Service（4×H100 / 70B FP8） |
| `deploy/sglang-deployment.yaml` | SGLang 0.5.13 K8s Deployment + Service（启用 RadixCache + FP8） |
| `deploy/triton-deployment.yaml` | TensorRT-LLM via Triton K8s Deployment + Service（HTTP 8000 + gRPC 8001） |
| `bench/run_bench.sh` | 三引擎本机 docker 启动模板 + 一键 OpenAI 兼容 API 压测 |
| `test_smoke.sh` | YAML 解析 + bash 语法校验 + 子命令用法测试 |

## 快速开始

### 1. 部署到 K8s

三个 YAML 都对位 4×H100 SXM / 70B FP8 模型，可独立 apply：

```bash
kubectl apply -f deploy/vllm-deployment.yaml      # 通用首选
kubectl apply -f deploy/sglang-deployment.yaml    # Agent / 多轮场景
kubectl apply -f deploy/triton-deployment.yaml    # 极致性能（需提前 trtllm-build 引擎）
```

> 模型路径默认通过 `hostPath: /models` 挂载，生产建议改成 PVC（Ceph/NFS/CSI）.

### 2. 本机 docker 启动（无 K8s 环境）

```bash
bash bench/run_bench.sh vllm     # 启动 vLLM 容器
bash bench/run_bench.sh sglang   # 启动 SGLang 容器
bash bench/run_bench.sh trtllm   # 编译 TRT 引擎 + 启动 Triton
```

### 3. 压测

服务起在 `:8000` 后：

```bash
bash bench/run_bench.sh bench    # 32 并发 × 50 轮 OpenAI 兼容 chat completions
```

> 真实压测建议改用 `vllm benchmark_serving.py` 或 `genai-perf`，本脚本只是快查模板.

### 4. 验证 YAML 与脚本可解析

```bash
bash test_smoke.sh
```

会跑三件事：

1. `python -c 'yaml.safe_load_all(...)'` 校验 3 个 YAML 都能正确解析且包含 `Deployment / apps/v1`
2. `bash -n bench/run_bench.sh` 校验脚本无语法错误
3. 子命令容错：无参数 / 未知子命令必须以非 0 退出

## 配套文章

- [15-vLLM_SGLang_TensorRT-LLM_三引擎自部署横评.md](../../15-vLLM_SGLang_TensorRT-LLM_三引擎自部署横评.md)

## 数据声明

YAML 中的镜像版本、参数（如 `gpu-memory-utilization=0.92`、`mem-fraction-static=0.85`）来自第 15 篇正文 § 8 的部署模板。**真实落地前请以官方仓库 release notes 为准**——vLLM 月度 release，SGLang 周度 release，TensorRT-LLM 季度 release，参数语义可能微调。
