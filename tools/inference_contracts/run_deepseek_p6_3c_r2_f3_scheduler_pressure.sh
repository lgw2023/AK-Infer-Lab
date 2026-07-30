#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BASE_EXPERIMENT=${P6_3C_R2_F3_BASE_EXPERIMENT:-${SCRIPT_DIR}/run_deepseek_p6_3c_r2_scheduler_pressure.sh}
test -f "${BASE_EXPERIMENT}"

export P6_3C_TASK_ID=p6_3c_r2_f3_chunked_prefill_atomic_pair_admission_2026_0730_run01
export P6_3C_REQUEST_ID_PREFIX=p6_3c_r2_f3
export P6_3C_ATOMIC_PAIR_ADMISSION=1
export P6_3C_ATOMIC_PAIR_REQUEST_PREFIX=p6_3c_r2_f3
export P6_3C_ATOMIC_PAIR_TIMEOUT_SECONDS=30
export REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r2_f3_atomic_pair_admission.py
export MODE_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r2_f3_mode.sh

exec bash "${BASE_EXPERIMENT}" "$1"
