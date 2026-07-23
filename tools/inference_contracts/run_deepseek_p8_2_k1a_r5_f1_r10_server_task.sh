#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TASK_ID=p8_2_k1a_r5_f1_r10_cache_stamp_lineage_2026_0723

export P8_2_K1A_TASK_ID=${TASK_ID}
export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R10
export P8_2_K1A_EXECUTION_MODE=authorized_single_lifecycle_cache_stamp_lineage
export P8_2_K1A_LIFECYCLE_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.sh
export P8_2_K1A_REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.py

if test "${P8_2_K1A_F1_R10_SERVER_TASK_AUDIT_ONLY:-0}" = 1; then
  export P8_2_K1A_SERVER_TASK_AUDIT_ONLY=1
fi

exec bash "${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh" "$1"
