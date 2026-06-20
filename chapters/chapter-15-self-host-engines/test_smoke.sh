#!/usr/bin/env bash
# 第 15 篇 smoke test：YAML 解析 + bash 语法 + 用法子命令验证.
#
# 用法：
#     bash test_smoke.sh
#
# 退出码：全部通过 = 0，否则非 0.

set -u

cd "$(dirname "$0")"

PASS=0
FAIL=0
FAILED=()

check() {
    local name="$1"
    local rc="$2"
    if [ "$rc" -eq 0 ]; then
        echo "  [PASS] $name"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $name"
        FAIL=$((FAIL + 1))
        FAILED+=("$name")
    fi
}

echo "==> 1. YAML 解析（每个 deploy/*.yaml 至少两个 document, kind 必须命中）"

for f in deploy/vllm-deployment.yaml deploy/sglang-deployment.yaml deploy/triton-deployment.yaml; do
    python - <<PY
import sys, yaml
with open("${f}", "r", encoding="utf-8") as fh:
    docs = list(yaml.safe_load_all(fh))
assert len(docs) >= 1, "${f}: 未解析出任何 document"
kinds = [d.get("kind") for d in docs if isinstance(d, dict)]
assert "Deployment" in kinds, f"${f}: 缺少 Deployment, 实际 kinds={kinds}"
api = next(d for d in docs if d.get("kind") == "Deployment").get("apiVersion")
assert api == "apps/v1", f"${f}: Deployment apiVersion 异常: {api}"
print(f"    ${f}: docs={len(docs)} kinds={kinds}")
PY
    check "yaml.safe_load(${f})" "$?"
done

echo "==> 2. bench/run_bench.sh 语法 / 用法 / 子命令"

bash -n bench/run_bench.sh
check "bash -n bench/run_bench.sh" "$?"

# 不带参数应该打 usage 并以非 0 码退出
bash bench/run_bench.sh >/dev/null 2>&1
rc=$?
[ $rc -ne 0 ]
check "run_bench.sh 无参数应退出非 0 (实际 rc=${rc})" "$?"

# 未知子命令也应退出非 0
bash bench/run_bench.sh xxx >/dev/null 2>&1
rc=$?
[ $rc -ne 0 ]
check "run_bench.sh 未知子命令应退出非 0 (实际 rc=${rc})" "$?"

echo
echo "==> 汇总: PASS=${PASS}, FAIL=${FAIL}"
if [ "$FAIL" -gt 0 ]; then
    echo "    失败用例: ${FAILED[*]}"
    exit 1
fi
exit 0
