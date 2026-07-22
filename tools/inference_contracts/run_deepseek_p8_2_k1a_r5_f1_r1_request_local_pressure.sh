#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
TASK_ID=p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722
ANALYSIS_MODE=${P8_2_K1A_F1_R1_ANALYSIS_MODE:-parent_legacy}
SOURCE_RESULT_ROOT=${P8_2_K1A_F1_R1_SOURCE_RESULT_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721_run01}
TRACE_DIR=${P8_2_K1A_F1_R1_TRACE_DIR:-${SOURCE_RESULT_ROOT}/runtime/offload_trace}
ANALYZER=${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_r5_f1_r1_request_local_pressure.py
RESULT_ROOT=${1:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722_run01}

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'offline_first=true\n'
  printf 'analysis_mode=%s\n' "${ANALYSIS_MODE}"
  printf 'npu_execution_authorized=conditional\n'
  printf 'formal_model_lifecycle_count_max=2\n'
  printf 'calibration_lifecycle_count_max=1\n'
  printf 'fixed_l2_lifecycle_count_max=1\n'
  printf 'pressure_request_count_exact=1\n'
  printf 'request_count_min=3\n'
  printf 'request_count_max=4\n'
  printf 'request_count_exact_if_trigger_observed=4\n'
  printf 'terminal_pre_restore_request_count=3\n'
  printf 'request_retry_count=0\n'
  printf 'net_gpu_free_delta_may_unlock_l2=false\n'
  printf 'capacity_search_authorized=false\n'
  printf 'result_transfer_authorized=true\n'
  printf 'transfer_method_selected=false\n'
  printf 'next_task_authorized=false\n'
}

if test "${P8_2_K1A_F1_R1_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

case "${ANALYSIS_MODE}" in
  parent_legacy|calibration) ;;
  *)
    echo "P8_2_K1A_F1_R1_ANALYSIS_MODE must be parent_legacy or calibration" >&2
    exit 64
    ;;
esac

test ! -e "${RESULT_ROOT}"
test -f "${ANALYZER}"
test -d "${TRACE_DIR}"
test -d "${SOURCE_RESULT_ROOT}"

python3 "${ANALYZER}" analyze \
  --source-result-root "${SOURCE_RESULT_ROOT}" \
  --trace-dir "${TRACE_DIR}" \
  --analysis-mode "${ANALYSIS_MODE}" \
  --output-dir "${RESULT_ROOT}"

python3 - "${RESULT_ROOT}" "${ANALYSIS_MODE}" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
mode = sys.argv[2]
manifest = json.loads((root / "candidate_manifest.server_local.json").read_text())
grading = json.loads((root / "grading_summary.json").read_text())
assert manifest["payload_file_count"] == 6
assert manifest["payload_total_bytes"] + (
    root / "candidate_manifest.server_local.json"
).stat().st_size <= 71680
assert manifest["generated_content_retained"] is False
assert manifest["token_ids_retained"] is False
assert manifest["request_ids_retained"] is False
assert manifest["raw_hash_values_retained"] is False
assert manifest["result_transfer_authorized"] is True
assert manifest["transfer_method_selected"] is False
assert grading["analysis_mode"] == mode
assert grading["server_grade"] in {
    "candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure",
    "candidate_requires_p8_2_k1a_r5_f1_r1_instrumented_calibration",
    "blocked_p8_2_k1a_r5_f1_r1_request_local_pressure_gate",
}
if mode == "parent_legacy":
    assert grading["server_grade"] != (
        "candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure"
    ) or grading["formal_fixed_l2_candidate_allowed"] is True
PY
