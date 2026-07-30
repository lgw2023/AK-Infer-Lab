#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BASE_MODE_RUNNER=${P6_3C_R2_F3_BASE_MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r2_mode.sh}
test -f "${BASE_MODE_RUNNER}"

export P6_3C_EXPERIMENT_LABEL=P6_3C_R2_F3
export P6_3C_ATOMIC_PAIR_ADMISSION=1
export P6_3C_ATOMIC_PAIR_REQUEST_PREFIX=p6_3c_r2_f3
export P6_3C_ATOMIC_PAIR_TIMEOUT_SECONDS=30
export REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r2_f3_atomic_pair_admission.py

exec bash "${BASE_MODE_RUNNER}" "$@"
