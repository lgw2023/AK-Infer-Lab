#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k1a_r5_f1_r8_target_store_lineage_2026_0723
PARENT_ROOT=${P8_2_K1A_F1_R7_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh_2026_0723_run01}
COMMON_LIFECYCLE=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r8_target_store_lineage.py

configure_r8() {
  export P8_2_K1A_TASK_ID=${TASK_ID}
  export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R8
  export P8_2_K1A_EXECUTION_MODE=authorized_single_lifecycle_target_store_lineage
  export P8_2_K1A_F1_SCHEMA_TAG=p8_2_k1a_r5_f1_r8
  export P8_2_K1A_F1_GRADE_PREFIX=red_p8_2_k1a_r5_f1_r8
  export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_f1_r8_target_attributed_h2d_restore
  export P8_2_K1A_REQUEST_RUNNER=${REQUEST_RUNNER}
  export REQUEST_RUNNER=${REQUEST_RUNNER}
  export P8_2_K1A_ALLOW_PRESSURE_BEFORE_KEYSPACE_EXACT=1
  export P8_2_K1A_LOGICAL_KEYSPACE_DIAGNOSTICS=1
  export P8_2_K1A_TARGET_STORE_LINEAGE_DIAGNOSTICS=1
  export P8_2_K1A_REQUIRE_TARGET_STORE_LINEAGE=1
  export P8_2_K1A_REQUIRE_POST_ABORT_FRESH_REVALIDATION=1
  export P8_2_K1A_REQUIRE_LOGICAL_RESTORE_WINDOW_FOR_RESTORE=1
  export P8_2_K1A_RESULT_SUMMARY_TITLE='target-attributed D2H lineage and conditional H2D restore'
  export P8_2_K1A_CLAIM_BOUNDARY=accepted_capacity_single_lifecycle_target_store_lineage_physical_cpu_only_window_and_conditional_h2d_candidate_only
  export P8_2_K1A_STOP_ON_FIRST_CPU_TARGET_EVICTION=0
  export P8_2_K1A_REQUEST_ORDER=warmup,target_prime_capture_group_wrapped_keys_before_finish,pressure_01_trace_target_store_until_physical_cpu_only_then_abort,restore_follower_after_idle_physical_and_logical_revalidation
  export P8_2_K1A_SKIP_F1_R5_PARENT_PREFLIGHT=1
  export P8_2_K1A_REPO_FILE_LIST=benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r8_target_store_lineage_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r8_target_store_lineage.yaml:tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r8_target_store_lineage.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r8_target_store_lineage.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r8_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r8_target_store_lineage.py:benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
}

configure_r8

if test "${P8_2_K1A_LIFECYCLE_AUDIT_ONLY:-0}" = 1; then
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'parent_f1_r7_pressure_executed_without_trigger=true\n'
  printf 'accepted_capacity_invalidated=false\n'
  printf 'target_group_wrapped_keys_captured_before_finish=true\n'
  printf 'target_lazy_store_schedule_completion_attributed=true\n'
  printf 'zero_key_groups_counted_complete=false\n'
  printf 'physical_cpu_only_trigger_required=true\n'
  printf 'logical_restore_window_required_before_restore=true\n'
  printf 'pressure_context_tokens=36800\n'
  printf 'logical_target_block_count=128\n'
  printf 'request_retry_count_exact=0\n'
  printf 'capacity_or_context_change_authorized=false\n'
  P8_2_K1A_LIFECYCLE_AUDIT_ONLY=1 \
    bash "${COMMON_LIFECYCLE}" "${RESULT_DIR}"
  exit 0
fi

test -d "${PARENT_ROOT}"
python3 - "${PARENT_ROOT}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
expected = {
    "grading_summary.json": "fbe61292041d7902f7177cd9c71712a6aafa9b6bd5fe675dac803e89cdf9e023",
    "residency_gate_timeline.json": "e8e1f3b50e68a98cbd2a6673ee7cb15051b3659f6e757d9e2ef1c85d4fb16fe7",
    "transfer_trace_summary.json": "d06592e9609f29bf445de78f44de3a7ae2c45b4616ee9e7f8d010baadf93f560",
    "logical_keyspace_probe_diagnostic_summary.json": "c97a190c840e1b175ccd7ae66500c8f964ed27a1dd773390a5904745189efb2a",
    "resource_recovery_summary.json": "7999be2de5f4a90f99ecd7ab518ee92a297512e48e3f1f043ed503bd9de4f00c",
    "candidate_manifest.server_local.json": "ab04a826c07eb5ccaeed54048b3a74c086cc2c7b277fd6ac16d92e20a87528b7",
}
for name, digest in expected.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest

grading = json.loads((root / "grading_summary.json").read_text(encoding="utf-8"))
timeline = json.loads(
    (root / "residency_gate_timeline.json").read_text(encoding="utf-8")
)
transfer = json.loads(
    (root / "transfer_trace_summary.json").read_text(encoding="utf-8")
)
logical = json.loads(
    (root / "logical_keyspace_probe_diagnostic_summary.json").read_text(
        encoding="utf-8"
    )
)
recovery = json.loads(
    (root / "resource_recovery_summary.json").read_text(encoding="utf-8")
)
assert grading["server_grade"] == (
    "red_p8_2_k1a_r5_f1_r7_pressure_completed_without_trigger"
)
assert grading["operational_grade"] == "operational_recovery_clean"
assert grading["request_count"] == 3
assert grading["pressure_request_count_executed"] == 1
assert grading["required_restore_block_count"] == 128
assert timeline["terminal_decision"] == "pressure_completed_without_trigger"
assert timeline["pressure_abort_requested"] is False
assert timeline["restore_sent"] is False
assert transfer["d2h_store_complete"] is True
assert transfer["d2h_worker_count"] == 8
assert transfer["d2h_bytes_total"] == 4467519488
assert transfer["h2d_worker_count"] == 0
assert logical["probe_event_count"] == 134
assert logical["exact_probe_event_count"] == 0
assert logical["logical_restore_match_tokens_max"] == 0
assert recovery["resource_recovery_exact"] is True
assert recovery["stopped_card_ids"] == list(range(8))
assert recovery["restored_card_ids"] == list(range(8))
PY

exec bash "${COMMON_LIFECYCLE}" "${RESULT_DIR}"
