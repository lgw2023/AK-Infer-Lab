#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k1a_r5_f1_r9_effective_group_geometry_2026_0723
PARENT_ROOT=${P8_2_K1A_F1_R8_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r8_target_store_lineage_2026_0723_run01}
COMMON_LIFECYCLE=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r9_effective_group_geometry.py

configure_r9() {
  export P8_2_K1A_TASK_ID=${TASK_ID}
  export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R9
  export P8_2_K1A_EXECUTION_MODE=authorized_single_lifecycle_effective_group_geometry
  export P8_2_K1A_F1_SCHEMA_TAG=p8_2_k1a_r5_f1_r9
  export P8_2_K1A_F1_GRADE_PREFIX=red_p8_2_k1a_r5_f1_r9
  export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_f1_r9_logical_128_block_target_attributed_h2d_restore
  export P8_2_K1A_REQUEST_RUNNER=${REQUEST_RUNNER}
  export REQUEST_RUNNER=${REQUEST_RUNNER}
  export P8_2_K1A_ALLOW_PRESSURE_BEFORE_KEYSPACE_EXACT=1
  export P8_2_K1A_LOGICAL_KEYSPACE_DIAGNOSTICS=1
  export P8_2_K1A_TARGET_STORE_LINEAGE_DIAGNOSTICS=1
  export P8_2_K1A_REQUIRE_TARGET_STORE_LINEAGE=1
  export P8_2_K1A_REQUIRE_EFFECTIVE_GROUP_GEOMETRY=1
  export P8_2_K1A_REQUIRE_POST_ABORT_FRESH_REVALIDATION=1
  export P8_2_K1A_REQUIRE_LOGICAL_RESTORE_WINDOW_FOR_RESTORE=1
  export P8_2_K1A_RESULT_SUMMARY_TITLE='logical 128-block target over runtime effective-group geometry'
  export P8_2_K1A_CLAIM_BOUNDARY=accepted_capacity_single_lifecycle_runtime_effective_group_geometry_logical_128_block_window_and_conditional_h2d_candidate_only
  export P8_2_K1A_STOP_ON_FIRST_CPU_TARGET_EVICTION=0
  export P8_2_K1A_REQUEST_ORDER=warmup,target_prime_capture_effective_group_keys,pressure_01_trace_logical_128_block_window_then_abort,restore_follower_after_idle_physical_and_logical_revalidation
  export P8_2_K1A_SKIP_F1_R5_PARENT_PREFLIGHT=1
  export P8_2_K1A_REPO_FILE_LIST=benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r9_effective_group_geometry_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r9_effective_group_geometry.yaml:tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r9_effective_group_geometry.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r9_effective_group_geometry.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r9_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r9_effective_group_geometry.py:benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
}

configure_r9

if test "${P8_2_K1A_LIFECYCLE_AUDIT_ONLY:-0}" = 1; then
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'parent_f1_r8_geometry_contract_red_accepted=true\n'
  printf 'accepted_capacity_invalidated=false\n'
  printf 'logical_target_block_count=128\n'
  printf 'runtime_effective_group_geometry_required=true\n'
  printf 'physical_fa_key_count_fixed=false\n'
  printf 'target_group_wrapped_keys_captured_before_finish=true\n'
  printf 'target_lazy_store_schedule_completion_attributed=true\n'
  printf 'zero_key_groups_counted_complete=false\n'
  printf 'fixed_pressure_must_execute_after_geometry_capture=true\n'
  printf 'logical_restore_window_required_before_restore=true\n'
  printf 'pressure_context_tokens=36800\n'
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
    "grading_summary.json": "896bfcd9d8722d398b5ee34a5730839b5c6028fd9f23d176d8cb3fb8dcb1f8a7",
    "residency_gate_timeline.json": "7e2752bf178d7fa37ea5de29c4fa65f5ac7495f4dcd93a4ad0fc18c337080884",
    "target_store_lineage_summary.json": "0c38987f4c9469989d64fb9713fb6d3558df56105e179efc0068466f199d155b",
    "transfer_trace_summary.json": "2898cf42a8f44462220466a10192edfbf45775282e9060aa6829228dfe5f1876",
    "resource_recovery_summary.json": "e0ebfe458b8d9129465d872c0bb213e7d034bcacd3d5d468bfb4048040c27f4c",
    "candidate_manifest.server_local.json": "a8b1154213cbac77d1cd5892dedcb726f881168d31e7cb43edf4a7df962e393c",
}
for name, digest in expected.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest

grading = json.loads((root / "grading_summary.json").read_text(encoding="utf-8"))
timeline = json.loads(
    (root / "residency_gate_timeline.json").read_text(encoding="utf-8")
)
lineage = json.loads(
    (root / "target_store_lineage_summary.json").read_text(encoding="utf-8")
)
transfer = json.loads(
    (root / "transfer_trace_summary.json").read_text(encoding="utf-8")
)
recovery = json.loads(
    (root / "resource_recovery_summary.json").read_text(encoding="utf-8")
)
assert grading["server_grade"] == (
    "red_p8_2_k1a_r5_f1_r8_target_store_lineage_unobservable_before_pressure"
)
assert grading["operational_grade"] == "operational_recovery_clean"
assert grading["request_count"] == 2
assert grading["pressure_request_count_executed"] == 0
assert grading["required_restore_block_count"] == 128
assert timeline["terminal_decision"] == (
    "target_store_lineage_unobservable_before_pressure"
)
assert lineage["target_fa_key_count"] == 64
assert lineage["target_store_key_count"] == 66
assert lineage["restore_group_capture_rows"][0][
    "effective_block_size_tokens"
] == 128
assert transfer["d2h_store_complete"] is True
assert transfer["d2h_worker_count"] == 8
assert transfer["d2h_bytes_total"] == 2206846976
assert transfer["h2d_worker_count"] == 0
assert recovery["resource_recovery_exact"] is True
assert recovery["stopped_card_ids"] == list(range(8))
assert recovery["restored_card_ids"] == list(range(8))
PY

exec bash "${COMMON_LIFECYCLE}" "${RESULT_DIR}"
