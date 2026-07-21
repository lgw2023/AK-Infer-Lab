#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
TASK_ID=p8_2_k1a_r5_f1_pressure_window_conditional_l2_2026_0721
PARENT_ROOT=${P8_2_K1A_R5_F1_PARENT_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721_run01}
RAW_RESULT_ROOT=${P8_2_K1A_R5_F1_RAW_RESULT_ROOT:-${PARENT_ROOT}}
VLLM_ROOT=${P8_2_K1A_R5_F1_VLLM_ROOT:-/data/node0_disk1/vllm-0.22.1/vllm}
MANAGER_SOURCE=${P8_2_K1A_R5_F1_MANAGER_SOURCE:-${VLLM_ROOT}/v1/simple_kv_offload/manager.py}
BLOCK_POOL_SOURCE=${P8_2_K1A_R5_F1_BLOCK_POOL_SOURCE:-${VLLM_ROOT}/v1/core/block_pool.py}
ANALYZER=${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_r5_f1_pressure_window.py
RESULT_ROOT=${1:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_pressure_window_2026_0721_run01}

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'offline_first=true\n'
  printf 'npu_execution_authorized=conditional\n'
  printf 'formal_model_lifecycle_count_max=1\n'
  printf 'pressure_request_count_exact=1\n'
  printf 'request_count_min=3\n'
  printf 'request_count_max=4\n'
  printf 'request_count_exact_if_trigger_observed=4\n'
  printf 'terminal_pre_restore_request_count=3\n'
  printf 'request_retry_count=0\n'
  printf 'capacity_search_authorized=false\n'
  printf 'result_transfer_authorized=true\n'
  printf 'transfer_method_selected=false\n'
  printf 'next_task_authorized=false\n'
}

if test "${P8_2_K1A_R5_F1_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test ! -e "${RESULT_ROOT}"
test -f "${ANALYZER}"
test -f "${PARENT_ROOT}/candidate_manifest.server_local.json"
test "$(sha256sum "${PARENT_ROOT}/candidate_manifest.server_local.json" | awk '{print $1}')" = 1209e22dc67aa1c15e80efcd26b453d7303665a5cd1a982ca2c41152334bb022
test "$(sha256sum "${MANAGER_SOURCE}" | awk '{print $1}')" = fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
test "$(sha256sum "${BLOCK_POOL_SOURCE}" | awk '{print $1}')" = 36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283

python3 "${ANALYZER}" analyze \
  --parent-package "${PARENT_ROOT}" \
  --raw-result-root "${RAW_RESULT_ROOT}" \
  --manager-source "${MANAGER_SOURCE}" \
  --block-pool-source "${BLOCK_POOL_SOURCE}" \
  --output-dir "${RESULT_ROOT}"

python3 - "${RESULT_ROOT}" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
manifest = json.loads((root / "candidate_manifest.server_local.json").read_text())
grading = json.loads((root / "grading_summary.json").read_text())
assert manifest["payload_file_count"] == 8
assert manifest["payload_total_bytes"] + (root / "candidate_manifest.server_local.json").stat().st_size <= 71680
assert manifest["generated_content_retained"] is False
assert manifest["token_ids_retained"] is False
assert manifest["raw_hash_values_retained"] is False
assert manifest["result_transfer_authorized"] is True
assert manifest["transfer_method_selected"] is False
assert grading["server_grade"] in {
    "blocked_p8_2_k1a_r5_f1_no_exact_pressure_window",
    "candidate_ready_p8_2_k1a_r5_f1_exact_pressure_window",
}
PY
