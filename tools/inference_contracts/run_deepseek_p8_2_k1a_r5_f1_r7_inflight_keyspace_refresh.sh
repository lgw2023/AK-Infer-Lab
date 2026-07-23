#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh_2026_0723
PARENT_ROOT=${P8_2_K1A_F1_R6_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723_run01}
COMMON_LIFECYCLE=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.py

configure_r7() {
  export P8_2_K1A_TASK_ID=${TASK_ID}
  export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R7
  export P8_2_K1A_EXECUTION_MODE=authorized_single_lifecycle_inflight_keyspace_refresh
  export P8_2_K1A_F1_SCHEMA_TAG=p8_2_k1a_r5_f1_r7
  export P8_2_K1A_F1_GRADE_PREFIX=red_p8_2_k1a_r5_f1_r7
  export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_f1_r7_inflight_keyspace_h2d_restore
  export P8_2_K1A_REQUEST_RUNNER=${REQUEST_RUNNER}
  export REQUEST_RUNNER=${REQUEST_RUNNER}
  export P8_2_K1A_ALLOW_PRESSURE_BEFORE_KEYSPACE_EXACT=1
  export P8_2_K1A_LOGICAL_KEYSPACE_DIAGNOSTICS=1
  export P8_2_K1A_REQUIRE_POST_ABORT_FRESH_REVALIDATION=1
  export P8_2_K1A_RESULT_SUMMARY_TITLE='in-flight keyspace refresh and conditional restore'
  export P8_2_K1A_STOP_ON_FIRST_CPU_TARGET_EVICTION=0
  export P8_2_K1A_REQUEST_ORDER=warmup,target_prime,pressure_01_refresh_until_exact_then_abort,restore_follower_after_idle_and_retained_key_revalidation
  export P8_2_K1A_SKIP_F1_R5_PARENT_PREFLIGHT=1
  export P8_2_K1A_REPO_FILE_LIST=benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.yaml:tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r7_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.py:benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
}

configure_r7

if test "${P8_2_K1A_LIFECYCLE_AUDIT_ONLY:-0}" = 1; then
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'parent_f1_r6_prepressure_circular_wait=true\n'
  printf 'accepted_capacity_invalidated=false\n'
  printf 'pressure_before_keyspace_exact_allowed=1\n'
  printf 'pressure_progress_runtime_keyspace_refresh_required=true\n'
  printf 'logical_keyspace_diagnostics=1\n'
  printf 'post_abort_fresh_revalidation_required=true\n'
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
    "grading_summary.json": "6c25e21e022de71319eab54d954fa803eb8d725e197e30e517bf11c1a92091f5",
    "residency_gate_timeline.json": "982bdc2d191929e1b369d872262db4fe8be58af0fa6eb5fe1c42cef2b5ebc7d9",
    "transfer_trace_summary.json": "602bd438fdb2300032912b991c4b12d11e2222a9a9bf9b7fe49ec0e0172c8971",
    "resource_recovery_summary.json": "c0c64cbc9c81080e1e5604277e3b2f7843f9272958f48c7ddea237d04734abd3",
    "candidate_manifest.server_local.json": "103557a871bf863d8eb2ed221a85fe650fa9444aa86263702318cb591a01829f",
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
recovery = json.loads(
    (root / "resource_recovery_summary.json").read_text(encoding="utf-8")
)
assert grading["server_grade"] == "red_p8_2_k1a_r5_f1_r6_h2d_evidence_incomplete"
assert grading["operational_grade"] == "operational_recovery_clean"
assert grading["request_count"] == 2
assert grading["pressure_request_count_executed"] == 0
assert grading["required_restore_block_count"] == 128
assert timeline["terminal_decision"] == "target_capture_unobservable_before_pressure"
assert timeline["initial_gate"]["d2h_store_complete_before_pressure"] is True
assert timeline["restore_sent"] is False
assert transfer["d2h_store_complete"] is True
assert transfer["d2h_worker_count"] == 8
assert transfer["h2d_worker_count"] == 0
assert recovery["resource_recovery_exact"] is True
assert recovery["stopped_card_ids"] == list(range(8))
assert recovery["restored_card_ids"] == list(range(8))
PY

exec bash "${COMMON_LIFECYCLE}" "${RESULT_DIR}"
