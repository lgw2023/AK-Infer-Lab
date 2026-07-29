#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BASE_SERVER_TASK=${P6_3C_R2_F2_BASE_SERVER_TASK:-${SCRIPT_DIR}/run_deepseek_p6_3c_r2_server_task.sh}
test -f "${BASE_SERVER_TASK}"

export REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
export ENV_PREFIX=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
unset BASE_PLUGIN_ROOT BASE_VLLM_ROOT
export P6_3C_TASK_ID=p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_2026_0730_run01
export P6_3C_REPORT_PREFIX=P6_3C_R2_F2
export P6_3C_EXPERIMENT_LABEL=P6_3C_R2_F2
export P6_3C_WORKLOAD_RELATIVE_PATH=benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f2_loopback_proxy_safe_matched_ab.yaml

exec bash "${BASE_SERVER_TASK}" "$@"
