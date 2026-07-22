#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
TASK_ID=p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722
SHARED_MODE_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
SHARED_MODE_PATCH_SHA256=5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'lifecycle_role=request_local_progress_calibration\n'
  printf 'calibration_only=true\n'
  printf 'pressure_context_tokens=131072\n'
  printf 'pressure_request_count_max=1\n'
  printf 'request_count_min=3\n'
  printf 'request_count_max=3\n'
  printf 'request_local_pressure_observer=true\n'
  printf 'shared_diagnostic_mode=0660_task_local_overlay\n'
  printf 'restore_request_authorized=false\n'
  printf 'request_retry_count=0\n'
}

if test "${P8_2_K1A_F1_R1_CALIBRATION_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test "$(sha256sum "${SHARED_MODE_PATCH}" | awk '{print $1}')" = \
  "${SHARED_MODE_PATCH_SHA256}"

export P8_2_K1A_TASK_ID=${TASK_ID}
export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R1-CALIBRATION
export P8_2_K1A_EXECUTION_MODE=authorized_single_request_local_progress_calibration_lifecycle
export P8_2_K1A_CALIBRATION_ONLY=1
export P8_2_K1A_ENABLE_REQUEST_LOCAL_PRESSURE_OBSERVER=1
export P8_2_K1A_PRESSURE_CONTEXT_TOKENS=131072
export P8_2_K1A_PRESSURE_REQUEST_COUNT_MAX=1
export P8_2_K1A_REQUEST_COUNT_MIN=3
export P8_2_K1A_REQUEST_COUNT_MAX=3
export P8_2_K1A_REQUEST_ORDER=warmup,target_prime,pressure_01_no_restore
export P8_2_K1A_DIAGNOSTIC_MODE_PATCH=${SHARED_MODE_PATCH}
export P8_2_K1A_DIAGNOSTIC_MODE_PATCH_SHA256=${SHARED_MODE_PATCH_SHA256}
export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_f1_r1_calibration_capture
export P8_2_K1A_NO_SUCCESS_GRADE=red_p8_2_k1a_r5_f1_r1_calibration_no_success
export P8_2_K1A_CPU_TARGET_LOST_GRADE=yellow_p8_2_k1a_r5_f1_r1_calibration_target_lost_after_capture
export P8_2_K1A_PARTIAL_GRADE=yellow_p8_2_k1a_r5_f1_r1_calibration_window_not_reached
export P8_2_K1A_EVIDENCE_INCOMPLETE_GRADE=red_p8_2_k1a_r5_f1_r1_calibration_evidence_incomplete

exec bash "${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh" "$1"
