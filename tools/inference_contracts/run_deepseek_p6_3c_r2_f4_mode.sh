#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
BASE_MODE_RUNNER=${P6_3C_R2_F4_BASE_MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r2_mode.sh}
test -f "${BASE_MODE_RUNNER}"

export P6_3C_EXPERIMENT_LABEL=P6_3C_R2_F4
export P6_3C_ATOMIC_PAIR_ADMISSION=1
export P6_3C_ATOMIC_PAIR_REQUEST_PREFIX=p6_3c_r2_f4
export P6_3C_ATOMIC_PAIR_TIMEOUT_SECONDS=30
export P6_3C_ATOMIC_PAIR_ADMISSION_MODULE=p6_3c_r2_f4_atomic_pair_admission
export P6_3C_ATOMIC_PAIR_ENGINE_MARKER=_p6_3c_r2_f4_atomic_pair_installed
export P6_3C_ATOMIC_PAIR_PROC_MARKER=_p6_3c_r2_f4_atomic_pair_timeout_handler_installed
export P6_3C_ATOMIC_PAIR_ADMISSION_CONTROLLER=${SCRIPT_DIR}/p6_3c_r2_f4_atomic_pair_admission.py
export P6_3C_ATOMIC_PAIR_ADMISSION_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r2_f4_atomic_pair_admission_overlay.patch
export REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r2_f4_atomic_pair_admission.py

exec bash "${BASE_MODE_RUNNER}" "$@"
