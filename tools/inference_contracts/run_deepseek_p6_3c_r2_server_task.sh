#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BASE_SERVER_TASK=${P6_3C_R2_BASE_SERVER_TASK:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_server_task.sh}
test -f "${BASE_SERVER_TASK}"

if test "${P6_3C_SERVER_TASK_AUDIT_ONLY:-${P6_3C_R1_SERVER_TASK_AUDIT_ONLY:-0}}" != 1; then
  ENV_PREFIX=${ENV_PREFIX:-/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
  BASE_PLUGIN_ROOT=${BASE_PLUGIN_ROOT:-/data/node0_disk1/vllm-ascend-0.22.1rc1/vllm_ascend}
  BASE_VLLM_ROOT=${BASE_VLLM_ROOT:-/data/node0_disk1/vllm-0.22.1/vllm}
  source_gate=(
    "${ENV_PREFIX}/lib/python3.11/site-packages/vllm/v1/core/single_type_kv_cache_manager.py:d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1"
    "${ENV_PREFIX}/lib/python3.11/site-packages/vllm/v1/core/kv_cache_coordinator.py:a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89"
    "${BASE_PLUGIN_ROOT}/patch/platform/patch_kv_cache_coordinator.py:dc65ed2adbb05ea52d9e891f648b62a5391eb41b2a6b262b71d40efe31effe20"
    "${BASE_PLUGIN_ROOT}/patch/platform/patch_kv_cache_interface.py:a4969e2c1b2ebde9a3c5a4d02df5175879fb56ea43322869871a3868ec1981b2"
    "${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py:0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb"
    "${BASE_PLUGIN_ROOT}/distributed/kv_transfer/__init__.py:dc693fd52eb44921e731b69021388ecc186f4e5fa5eca3b28fc1963661e355d1"
    "${BASE_VLLM_ROOT}/v1/core/sched/scheduler.py:41ff2e524c90d9aa72b72cd77492eb62ee2a729a773bd8233e970f39abbb5983"
  )
  for entry in "${source_gate[@]}"; do
    source_path=${entry%:*}
    expected_sha256=${entry##*:}
    test -f "${source_path}"
    test "$(sha256sum "${source_path}" | awk '{print $1}')" = \
      "${expected_sha256}"
  done
fi

export P6_3C_TASK_ID=p6_3c_r2_chunked_prefill_capacity_calibrated_2026_0729_run01
export P6_3C_REPORT_PREFIX=P6_3C_R2
export P6_3C_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r2_scheduler_pressure.py
export P6_3C_EXPERIMENT=${SCRIPT_DIR}/run_deepseek_p6_3c_r2_scheduler_pressure.sh

exec bash "${BASE_SERVER_TASK}" "$@"
