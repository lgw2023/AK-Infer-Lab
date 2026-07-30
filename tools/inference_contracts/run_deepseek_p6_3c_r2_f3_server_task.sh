#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BASE_SERVER_TASK=${P6_3C_R2_F3_BASE_SERVER_TASK:-${SCRIPT_DIR}/run_deepseek_p6_3c_r2_server_task.sh}
test -f "${BASE_SERVER_TASK}"

export REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
export ENV_PREFIX=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
unset BASE_PLUGIN_ROOT BASE_VLLM_ROOT
export P6_3C_TASK_ID=p6_3c_r2_f3_chunked_prefill_atomic_pair_admission_2026_0730_run01
export P6_3C_REPORT_PREFIX=P6_3C_R2_F3
export P6_3C_EXPERIMENT_LABEL=P6_3C_R2_F3
export P6_3C_WORKLOAD_RELATIVE_PATH=benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f3_atomic_pair_admission_matched_ab.yaml
export P6_3C_REQUEST_ID_PREFIX=p6_3c_r2_f3
export P6_3C_ATOMIC_PAIR_ADMISSION=1
export P6_3C_ATOMIC_PAIR_REQUEST_PREFIX=p6_3c_r2_f3
export P6_3C_ATOMIC_PAIR_TIMEOUT_SECONDS=30
export P6_3C_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r2_f3_atomic_pair_admission.py
export P6_3C_EXPERIMENT=${SCRIPT_DIR}/run_deepseek_p6_3c_r2_f3_scheduler_pressure.sh

exec bash "${BASE_SERVER_TASK}" "$@"
