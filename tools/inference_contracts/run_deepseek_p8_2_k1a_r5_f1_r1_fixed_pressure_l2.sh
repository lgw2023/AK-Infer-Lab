#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

case "${P8_2_K1A_FIXED_PRESSURE_CONTEXT_TOKENS:-}" in
  ''|*[!0-9]*)
    echo "P8_2_K1A_FIXED_PRESSURE_CONTEXT_TOKENS must be a positive integer" >&2
    exit 64
    ;;
esac
if test "${P8_2_K1A_FIXED_PRESSURE_CONTEXT_TOKENS}" -le 0; then
  echo "fixed pressure context must be positive" >&2
  exit 64
fi
if test -z "${P8_2_K1A_F1_R1_ANALYSIS_ROOT:-}"; then
  echo "P8_2_K1A_F1_R1_ANALYSIS_ROOT is required" >&2
  exit 64
fi

python3 - \
  "${P8_2_K1A_F1_R1_ANALYSIS_ROOT}" \
  "${P8_2_K1A_FIXED_PRESSURE_CONTEXT_TOKENS}" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
context = int(sys.argv[2])
ready = "candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure"
assert (root / "task_grade.txt").read_text().strip() == ready
grading = json.loads((root / "grading_summary.json").read_text())
candidate = json.loads((root / "pressure_candidate.json").read_text())
assert grading["server_grade"] == ready
assert grading["formal_fixed_l2_candidate_allowed"] is True
assert candidate["candidate_is_fixed_not_search"] is True
assert candidate["formal_fixed_l2_candidate_allowed"] is True
assert candidate["candidate_uses_request_local_progress"] is True
assert candidate["candidate_uses_gpu_free_pool_delta"] is False
assert candidate["candidate_pressure_context_tokens"] == context
assert candidate["candidate_output_tokens"] == 64
PY

printf 'offline_ready_grade_verified=true\n'
printf 'fixed_pressure_context_tokens=%s\n' \
  "${P8_2_K1A_FIXED_PRESSURE_CONTEXT_TOKENS}"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export P8_2_K1A_TASK_ID=p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722
export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R1-L2
export P8_2_K1A_EXECUTION_MODE=authorized_one_fixed_non_search_request_local_pressure_h2d_trigger_lifecycle
export P8_2_K1A_PRESSURE_CONTEXT_TOKENS=${P8_2_K1A_FIXED_PRESSURE_CONTEXT_TOKENS}
export P8_2_K1A_PRESSURE_REQUEST_COUNT_MAX=1
export P8_2_K1A_REQUEST_COUNT_MIN=3
export P8_2_K1A_REQUEST_COUNT_MAX=4
export P8_2_K1A_REQUEST_ORDER=warmup,target_prime,fixed_pressure,restore_follower_if_trigger
export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_f1_r1_fixed_pressure_h2d_trigger
export P8_2_K1A_NO_SUCCESS_GRADE=red_p8_2_k1a_r5_f1_r1_fixed_pressure_no_success
export P8_2_K1A_CPU_TARGET_LOST_GRADE=red_p8_2_k1a_r5_f1_r1_fixed_pressure_target_lost
export P8_2_K1A_PARTIAL_GRADE=red_p8_2_k1a_r5_f1_r1_fixed_pressure_trigger_not_reached
export P8_2_K1A_EVIDENCE_INCOMPLETE_GRADE=red_p8_2_k1a_r5_f1_r1_fixed_pressure_evidence_incomplete

exec bash "${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh" "$1"
