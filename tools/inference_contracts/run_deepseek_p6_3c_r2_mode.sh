#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BASE_MODE_RUNNER=${P6_3C_R2_BASE_MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_mode.sh}
test -f "${BASE_MODE_RUNNER}"

export P6_3C_EXPERIMENT_LABEL=${P6_3C_EXPERIMENT_LABEL:-P6_3C_R2}
export P6_3C_MAX_MODEL_LEN=12288
export P6_3C_MAX_NUM_BATCHED_TOKENS=12288
export P6_3C_MAX_NUM_SEQS=2
export P6_3C_SHARED_HYBRID_KV_REPAIR=1
export REQUEST_RUNNER=${REQUEST_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r2_scheduler_pressure.py}

exec bash "${BASE_MODE_RUNNER}" "$@"
