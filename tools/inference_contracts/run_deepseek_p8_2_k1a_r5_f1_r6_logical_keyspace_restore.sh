#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723
F1_R5_ROOT=${P8_2_K1A_F1_R5_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r5_effective_restore_contract_2026_0722_run01}
REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.py
SHARED_MODE_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
SHARED_MODE_PATCH_SHA256=5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'execution_mode=authorized_single_lifecycle_logical_keyspace_restore\n'
  printf 'parent_f1_r5_keyspace_probe_invalid=true\n'
  printf 'accepted_capacity_invalidated=false\n'
  printf 'npu_execution_authorized=true\n'
  printf 'logical_target_block_count=128\n'
  printf 'logical_restore_match_tokens=16384\n'
  printf 'hash_block_size_tokens=128\n'
  printf 'runtime_pool_key_count_fixed=false\n'
  printf 'runtime_cpu_coordinator_lookup_required=true\n'
  printf 'runtime_lookup_observe_only=true\n'
  printf 'same_capacity_and_context=true\n'
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

if test "${P8_2_K1A_F1_R6_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test ! -e "${RESULT_DIR}"
test -f "${REQUEST_RUNNER}"
test -f "${SHARED_MODE_PATCH}"
test "$(sha256sum "${SHARED_MODE_PATCH}" | awk '{print $1}')" = \
  "${SHARED_MODE_PATCH_SHA256}"
test -d "${F1_R5_ROOT}"

python3 - "${F1_R5_ROOT}" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
expected = {
    "grading_summary.json": "62eb1cf78270c163a4bc861b21c20bbd165161f2172118928294403c5e61a806",
    "h2d_trigger_summary.json": "79214a8ee8c226fae23acf36da482636d8976638e5e2dc96c5050cf41c4ac3aa",
    "residency_gate_timeline.json": "6c44139c0f6500af5e09f7de67efc7a619cb856f52a70ec13755f4363e561dca",
    "resource_recovery_summary.json": "237bcf8456cc9269bd182efeb34d27e3b71b6c9e07563ba8ad4aa7dcf750a429",
    "candidate_manifest.server_local.json": "9d820400ef21df57f67540946b2b17917bae1c3949613c1057c661596f274c4e",
}
for name, digest in expected.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest

grading = json.loads((root / "grading_summary.json").read_text(encoding="utf-8"))
timeline = json.loads(
    (root / "residency_gate_timeline.json").read_text(encoding="utf-8")
)
recovery = json.loads(
    (root / "resource_recovery_summary.json").read_text(encoding="utf-8")
)
assert grading["server_grade"] == "red_p8_2_k1a_r5_f1_r5_cleanup_or_recovery_incomplete"
assert grading["required_restore_block_count"] == 128
assert timeline["terminal_decision"] == "pressure_completed_without_trigger"
near_miss = timeline["inflight_trigger_state"]["best_restore_eligibility_near_miss"]
assert near_miss["request_hash_candidate_count"] == 128
assert near_miss["cpu_target_block_count"] == 0
assert near_miss["gpu_target_block_count"] == 0
assert near_miss["restore_group_rows"][0]["cpu_block_count"] == 64
assert near_miss["restore_group_rows"][1]["cpu_block_count"] == 2
assert recovery["restart_exit_code"] == 0
assert recovery["same_card_set_restored"] is True
assert recovery["all_eight_npu_healthy"] is True
assert recovery["keep_alive_marker_count"] == 0

with (root / "request_summary.tsv").open(encoding="utf-8", newline="") as handle:
    requests = list(csv.DictReader(handle, delimiter="\t"))
assert len(requests) == 3
assert all(
    row["status"] == "success"
    and row["http_status"] == "200"
    and row["saw_done"] == "True"
    for row in requests
)
PY

export P8_2_K1A_TASK_ID=${TASK_ID}
export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R6
export P8_2_K1A_EXECUTION_MODE=authorized_single_lifecycle_logical_keyspace_restore
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
export P8_2_K1A_REQUEST_ORDER=warmup,target_prime,pressure_01_abort_on_exact_logical_restore_eligibility,restore_follower_after_idle
export P8_2_K1A_DIAGNOSTIC_MODE_PATCH=${SHARED_MODE_PATCH}
export P8_2_K1A_DIAGNOSTIC_MODE_PATCH_SHA256=${SHARED_MODE_PATCH_SHA256}
export P8_2_K1A_REQUEST_RUNNER=${REQUEST_RUNNER}
export REQUEST_RUNNER=${REQUEST_RUNNER}
export P8_2_K1A_H2D_RESIDENCY_OBSERVER=${SCRIPT_DIR}/p8_2_k1a_h2d_residency_observer.py
export P8_2_K1A_EXPECTED_COMMAND_SHA256=89a9a105da5a04a3207c638b6999858ed32bff0f438c2cfb617b03905d1efe2f
export P8_2_K1A_REPO_FILE_LIST=benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r6_logical_keyspace_restore_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r6_logical_keyspace_restore.yaml:tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.py:benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
export P8_2_K1A_RESULT_TRANSFER_AUTHORIZED=true
export P8_2_K1A_DEFER_FINALIZE=1

if test "${P8_2_K1A_MODE_AUDIT_ONLY:-0}" = 1; then
  exec bash "${SCRIPT_DIR}/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh" "${RESULT_DIR}"
fi
exec bash "${SCRIPT_DIR}/run_deepseek_p8_2_k1a_simple_cpu_offload.sh" "${RESULT_DIR}"
