#!/usr/bin/env bash
# 第 15 篇配套：vLLM / SGLang / TensorRT-LLM 三引擎本机 docker 启动 + 一键压测脚本.
#
# 数据均来自正文 § 七 / § 8（部署 YAML 实操）和附录 B（启动命令快查表）.
# 脚本 **不会** 在没有 NVIDIA GPU 的机器上跑通；用作可对照的命令模板.
#
# 用法：
#     bash run_bench.sh vllm        # 启动 vLLM 容器
#     bash run_bench.sh sglang      # 启动 SGLang 容器
#     bash run_bench.sh trtllm      # 编译 TRT 引擎并启动 Triton
#     bash run_bench.sh bench       # 对已经在 :8000 提供 OpenAI 兼容 API 的引擎跑压测

set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/models}"
MODEL_NAME="${MODEL_NAME:-Llama-3.3-70B-Instruct-FP8}"
TP="${TP:-4}"
MAX_LEN="${MAX_LEN:-16384}"

start_vllm() {
    echo "[vllm] launching vllm/vllm-openai:v0.23.0 with TP=${TP} ..."
    docker run --gpus all -p 8000:8000 \
        -v "${MODEL_DIR}:/models" \
        vllm/vllm-openai:v0.23.0 \
        --model "/models/${MODEL_NAME}" \
        --tensor-parallel-size "${TP}" \
        --max-model-len "${MAX_LEN}" \
        --gpu-memory-utilization 0.92 \
        --enable-prefix-caching \
        --quantization fp8
}

start_sglang() {
    echo "[sglang] launching lmsysorg/sglang:v0.5.13-cu124 with TP=${TP} ..."
    docker run --gpus all -p 8000:8000 \
        -v "${MODEL_DIR}:/models" \
        lmsysorg/sglang:v0.5.13-cu124 \
        python -m sglang.launch_server \
        --model-path "/models/${MODEL_NAME}" \
        --tp "${TP}" --enable-radix-cache \
        --mem-fraction-static 0.85 \
        --max-running-requests 128 \
        --quantization fp8 --port 8000
}

start_trtllm() {
    echo "[trtllm] step 1/2: compile engine via trtllm-build ..."
    trtllm-build \
        --checkpoint_dir "${MODEL_DIR}/llama3-70b-fp8/" \
        --output_dir "${MODEL_DIR}/llama3-70b-trt/" \
        --gemm_plugin fp8 \
        --max_input_len "${MAX_LEN}" --max_seq_len $((MAX_LEN * 2)) \
        --tp_size "${TP}"
    echo "[trtllm] step 2/2: launching tritonserver ..."
    docker run --gpus all -p 8000:8000 -p 8001:8001 \
        -v "${MODEL_DIR}:/models" \
        nvcr.io/nvidia/tritonserver:24.05-trtllm-python-py3 \
        tritonserver \
        --model-repository=/models/llama3-70b-trt \
        --http-port=8000 --grpc-port=8001
}

run_bench() {
    # 极简压测：32 并发 × 50 轮，prompt 固定 512 token 量级，统计端到端 p50/p99.
    # 真实压测请用 vllm benchmark_serving.py / genai-perf 等专业工具.
    if ! command -v hey >/dev/null 2>&1; then
        echo "[bench] 'hey' not installed; install via 'go install github.com/rakyll/hey@latest'" >&2
        exit 1
    fi
    PROMPT='{"model":"'"${MODEL_NAME}"'","messages":[{"role":"user","content":"hello"}],"max_tokens":128}'
    hey -n 50 -c 32 -m POST -T application/json -d "${PROMPT}" \
        http://127.0.0.1:8000/v1/chat/completions
}

case "${1:-}" in
    vllm)   start_vllm   ;;
    sglang) start_sglang ;;
    trtllm) start_trtllm ;;
    bench)  run_bench    ;;
    *)
        echo "usage: $0 {vllm|sglang|trtllm|bench}" >&2
        exit 1
        ;;
esac
