#!/usr/bin/env bash
# 跑一遍所有 chapter demo 的 import 自检.
#
# 用法：
#   bash run_all_smoke.sh
#
# 结果：每个 chapter 一条 PASS / FAIL 行，最后给出汇总。
# 退出码：全部通过=0，否则=1。

set -u

cd "$(dirname "$0")"

PASS=0
FAIL=0
FAILED_LIST=()

declare -a CASES=(
    "chapter-01-multi-model-router|router_demo"
    "chapter-02-token-cost|cost_tracker"
    "chapter-03-unified-adapter|openai_adapter"
    "chapter-04-ha-pattern|ha_demo"
    "chapter-05-benchmark|benchmark_runner"
    "chapter-06-domestic-benchmark|domestic_benchmark"
    "chapter-07-pricing-calculator|pricing_calculator"
    "chapter-08-quota-manager|quota_manager"
    "chapter-09-tier-router|tier_router"
    "chapter-10-semantic-cache|semantic_cache"
    "chapter-11-agent-token-saving|agent_demo"
    "chapter-12-checkpoint-recovery|checkpoint_demo"
)

echo "==> 开始 import 自检（共 ${#CASES[@]} 个 chapter）"

for entry in "${CASES[@]}"; do
    chapter="${entry%%|*}"
    module="${entry##*|}"
    pushd "$chapter" >/dev/null 2>&1 || {
        echo "  [FAIL] $chapter (目录不存在)"
        FAIL=$((FAIL + 1))
        FAILED_LIST+=("$chapter")
        continue
    }
    if python -c "import $module" 2>/dev/null; then
        echo "  [PASS] $chapter -> $module"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $chapter -> $module"
        # 出错时再跑一遍并打出错误，方便排查
        python -c "import $module" 2>&1 | sed 's/^/         /'
        FAIL=$((FAIL + 1))
        FAILED_LIST+=("$chapter")
    fi
    popd >/dev/null 2>&1
done

echo
echo "==> 汇总: PASS=${PASS}, FAIL=${FAIL}"
if [ "$FAIL" -gt 0 ]; then
    echo "    失败章节: ${FAILED_LIST[*]}"
    exit 1
fi
exit 0
