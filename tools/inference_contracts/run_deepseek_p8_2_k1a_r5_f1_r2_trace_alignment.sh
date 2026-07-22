#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
TASK_ID=p8_2_k1a_r5_f1_r2_trace_alignment_2026_0722
ANALYZER=${SCRIPT_DIR}/p8_2_k1a_r5_f1_r2_trace_alignment.py
RESULT_ROOT=$1

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'execution_mode=authorized_server_local_read_only_trace_alignment_no_npu\n'
  printf 'npu_execution_authorized=false\n'
  printf 'vllm_server_start_authorized=false\n'
  printf 'model_requests_authorized=false\n'
  printf 'keep_alive_action=leave_running\n'
  printf 'context_change_authorized=false\n'
  printf 'pressure_search_or_sweep_authorized=false\n'
  printf 'result_transfer_authorized=true\n'
  printf 'transfer_method_selected=false\n'
  printf 'next_task_authorized=false\n'
}

if test "${P8_2_K1A_F1_R2_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

: "${P8_2_K1A_F1_R2_CALIBRATION_ROOT:?calibration root is required}"
: "${P8_2_K1A_F1_R2_CALIBRATION_ANALYSIS_ROOT:?calibration analysis root is required}"
: "${P8_2_K1A_F1_R2_L2_ROOT:?fixed L2 root is required}"
test -f "${ANALYZER}"
test -d "${P8_2_K1A_F1_R2_CALIBRATION_ROOT}"
test -d "${P8_2_K1A_F1_R2_CALIBRATION_ANALYSIS_ROOT}"
test -d "${P8_2_K1A_F1_R2_L2_ROOT}"
test ! -e "${RESULT_ROOT}"

python3 "${ANALYZER}" analyze \
  --calibration-root "${P8_2_K1A_F1_R2_CALIBRATION_ROOT}" \
  --calibration-analysis-root "${P8_2_K1A_F1_R2_CALIBRATION_ANALYSIS_ROOT}" \
  --l2-root "${P8_2_K1A_F1_R2_L2_ROOT}" \
  --output-dir "${RESULT_ROOT}"

cat "${RESULT_ROOT}/task_grade.txt"
