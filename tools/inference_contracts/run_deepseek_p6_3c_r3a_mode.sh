#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
BASE_MODE_RUNNER=${P6_3C_R3A_BASE_MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_mode.sh}
test -f "${BASE_MODE_RUNNER}"

export P6_3C_EXPERIMENT_LABEL=P6_3C_R3A
export P6_3C_MAX_MODEL_LEN=12288
export P6_3C_MAX_NUM_BATCHED_TOKENS=12288
export P6_3C_MAX_NUM_SEQS=9
export P6_3C_SHARED_HYBRID_KV_REPAIR=1
export P6_3C_ATOMIC_PAIR_ADMISSION=0
export P6_3C_R3_REQUEST_MARKER=p6_3c_r3a_
export OBSERVER=${SCRIPT_DIR}/p6_3c_r3_decode_resident_observer.py
export REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r3a_decode_resident.py

exec bash "${BASE_MODE_RUNNER}" "$@"
