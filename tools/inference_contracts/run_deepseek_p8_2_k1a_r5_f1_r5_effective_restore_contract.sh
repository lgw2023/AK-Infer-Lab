#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k1a_r5_f1_r5_effective_restore_contract_2026_0722
F1_R4_ROOT=${P8_2_K1A_F1_R4_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_2026_0722_run01}
REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.py
SHARED_MODE_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
SHARED_MODE_PATCH_SHA256=5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'execution_mode=authorized_single_lifecycle_effective_restore_contract\n'
  printf 'parent_f1_r4_runtime_contract_invalid=true\n'
  printf 'accepted_capacity_invalidated=false\n'
  printf 'npu_execution_authorized=true\n'
  printf 'effective_target_block_count=128\n'
  printf 'restore_match_tokens=16384\n'
  printf 'block_size_tokens=128\n'
  printf 'restore_target_geometry_exact=true\n'
  printf 'target_capture_source_and_count_required=true\n'
  printf 'group_capture_geometry_required=true\n'
  printf 'same_card_set_recovery_driver_required=true\n'
  printf 'structured_resource_recovery_artifact_required=true\n'
  printf 'pressure_context_tokens=36800\n'
  printf 'formal_model_lifecycle_count_exact=1\n'
  printf 'model_request_count_max=4\n'
  printf 'pressure_request_count_exact=1\n'
  printf 'request_retry_count_exact=0\n'
  printf 'capacity_search_authorized=false\n'
  printf 'context_change_authorized=false\n'
  printf 'result_transfer_authorized=true\n'
  printf 'transfer_method_selected=false\n'
  printf 'automatic_transfer_allowed=false\n'
  printf 'next_task_authorized=false\n'
}

if test "${P8_2_K1A_F1_R5_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test ! -e "${RESULT_DIR}"
test -f "${REQUEST_RUNNER}"
test -f "${SHARED_MODE_PATCH}"
test "$(sha256sum "${SHARED_MODE_PATCH}" | awk '{print $1}')" = \
  "${SHARED_MODE_PATCH_SHA256}"
test -d "${F1_R4_ROOT}"

python3 - "${F1_R4_ROOT}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
expected = {
    "grading_summary.json": "b84df30aed30cd50374cd9c8a18ce5ae6bc878643dbf4955f32602ac6d416cba",
    "h2d_trigger_summary.json": "4b47a03bcda1cdc32beab382a22e03cd1ea3753b5bca21924cdfe64e56f3e47a",
    "residency_gate_timeline.json": "234b3799f77035902cb0b39bdfd62a3dabc918adf46864ba22aed75cf15d6164",
    "candidate_manifest.server_local.json": "a69a426b8ae323129ea9ecf20ea5410b24da7b61ff062102ccb44006b4215bba",
}
for name, digest in expected.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
grading = json.loads((root / "grading_summary.json").read_text(encoding="utf-8"))
timeline = json.loads(
    (root / "residency_gate_timeline.json").read_text(encoding="utf-8")
)
assert grading["server_grade"] == "red_p8_2_k1a_r5_f1_r4_cleanup_or_recovery_incomplete"
assert grading["required_restore_block_count"] == 128
assert timeline["terminal_decision"] == "pressure_completed_without_trigger"
assert timeline["initial_gate"]["target_block_count"] == 64
assert timeline["inflight_trigger_state"]["best_restore_eligibility_near_miss"][
    "target_block_count"
] == 64
PY

export P8_2_K1A_TASK_ID=${TASK_ID}
export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R5
export P8_2_K1A_EXECUTION_MODE=authorized_single_lifecycle_effective_restore_contract
export P8_2_K1A_CPU_BYTES_TO_USE=3444834304
export P8_2_K1A_CPU_BYTES_TO_USE_PER_RANK=430604288
export P8_2_K1A_HOST_MEM_AVAILABLE_MIN=412316860416
export P8_2_K1A_LAZY_OFFLOAD=true
export P8_2_K1A_ENABLE_H2D_RESIDENCY_OBSERVER=1
export P8_2_K1A_ENABLE_REQUEST_LOCAL_PRESSURE_OBSERVER=1
export P8_2_K1A_H2D_TARGET_BLOCK_COUNT=128
export P8_2_K1A_RESTORE_MATCH_TOKENS=16384
export P8_2_K1A_BLOCK_SIZE_TOKENS=128
export P8_2_K1A_REQUIRE_RESTORE_GROUP_ELIGIBILITY=1
export P8_2_K1A_STOP_ON_FIRST_CPU_TARGET_EVICTION=0
export P8_2_K1A_PRESSURE_CONTEXT_TOKENS=36800
export P8_2_K1A_PRESSURE_REQUEST_COUNT_MAX=1
export P8_2_K1A_REQUEST_COUNT_MIN=3
export P8_2_K1A_REQUEST_COUNT_MAX=4
export P8_2_K1A_REQUEST_ORDER=warmup,target_prime,pressure_01_abort_on_full_restore_eligibility,restore_follower_after_idle
export P8_2_K1A_DIAGNOSTIC_MODE_PATCH=${SHARED_MODE_PATCH}
export P8_2_K1A_DIAGNOSTIC_MODE_PATCH_SHA256=${SHARED_MODE_PATCH_SHA256}
export P8_2_K1A_REQUEST_RUNNER=${REQUEST_RUNNER}
export REQUEST_RUNNER=${REQUEST_RUNNER}
export P8_2_K1A_H2D_RESIDENCY_OBSERVER=${SCRIPT_DIR}/p8_2_k1a_h2d_residency_observer.py
export P8_2_K1A_EXPECTED_COMMAND_SHA256=89a9a105da5a04a3207c638b6999858ed32bff0f438c2cfb617b03905d1efe2f
export P8_2_K1A_REPO_FILE_LIST=benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r5_effective_restore_contract_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r5_effective_restore_contract.yaml:tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.py:benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
export P8_2_K1A_RESULT_TRANSFER_AUTHORIZED=true
export P8_2_K1A_DEFER_FINALIZE=1

if test "${P8_2_K1A_MODE_AUDIT_ONLY:-0}" = 1; then
  exec bash "${SCRIPT_DIR}/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh" "${RESULT_DIR}"
fi
exec bash "${SCRIPT_DIR}/run_deepseek_p8_2_k1a_simple_cpu_offload.sh" "${RESULT_DIR}"
