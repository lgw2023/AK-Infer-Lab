#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k1a_r5_f1_r15_restore_step_lineage_2026_0725
PARENT_ROOT=${P8_2_K1A_F1_R14_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_2026_0725_run01}
COMMON_LIFECYCLE=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r15_restore_step_lineage.py

configure_r15() {
  export P8_2_K1A_TASK_ID=${TASK_ID}
  export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R15
  export P8_2_K1A_EXECUTION_MODE=authorized_single_lifecycle_restore_step_lineage
  export P8_2_K1A_F1_SCHEMA_TAG=p8_2_k1a_r5_f1_r15
  export P8_2_K1A_F1_GRADE_PREFIX=red_p8_2_k1a_r5_f1_r15
  export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_f1_r15_restore_step_lineage_and_attributed_h2d_restore
  export P8_2_K1A_REQUEST_RUNNER=${REQUEST_RUNNER}
  export REQUEST_RUNNER=${REQUEST_RUNNER}
  export P8_2_K1A_TARGET_CACHE_STAMP_LINEAGE=1
  export P8_2_K1A_EAGLE_AWARE_LOGICAL_LOOKUP=1
  export P8_2_K1A_RESTORE_SHARED_PREFIX_TOKENS=32768
  export P8_2_K1A_ALLOW_IDENTICAL_TARGET_RESTORE_BODIES=1
  export P8_2_K1A_ALLOW_PRESSURE_BEFORE_KEYSPACE_EXACT=1
  export P8_2_K1A_LOGICAL_KEYSPACE_DIAGNOSTICS=1
  export P8_2_K1A_TARGET_STORE_LINEAGE_DIAGNOSTICS=1
  export P8_2_K1A_REQUIRE_TARGET_STORE_LINEAGE=1
  export P8_2_K1A_REQUIRE_EFFECTIVE_GROUP_GEOMETRY=1
  export P8_2_K1A_REQUIRE_POST_ABORT_FRESH_REVALIDATION=1
  export P8_2_K1A_REQUIRE_LOGICAL_RESTORE_WINDOW_FOR_RESTORE=1
  export P8_2_K1A_HIT_TO_LOAD_ADMISSION_LINEAGE=1
  export P8_2_K1A_UPDATE_RAISE_GEOMETRY_LINEAGE=1
  export P8_2_K1A_ENABLE_COMPRESS_AWARE_PAIRING_REPAIR=1
  export P8_2_K1A_RESTORE_STEP_LINEAGE=1
  export P8_2_K1A_RESULT_SUMMARY_TITLE='restore allocate/update/load step lineage and H2D path attribution on the exact 16K window'
  export P8_2_K1A_CLAIM_BOUNDARY=accepted_capacity_single_lifecycle_restore_allocate_update_load_step_lineage_and_h2d_path_attribution_and_conditional_h2d_candidate_only
  export P8_2_K1A_STOP_ON_FIRST_CPU_TARGET_EVICTION=0
  export P8_2_K1A_REQUEST_ORDER=warmup,target_prime_capture_runtime_cache_stamp_keys,pressure_01_abort_on_exact_physical_window,post_abort_eagle_aware_logical_acceptance,restore_follower_with_step_lineage_attribution
  export P8_2_K1A_SKIP_F1_R5_PARENT_PREFLIGHT=1
  export P8_2_K1A_REPO_FILE_LIST=benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r15_restore_step_lineage_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r15_restore_step_lineage.yaml:tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r15_restore_step_lineage.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r15_restore_step_lineage.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r15_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r15_restore_step_lineage.py:benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
}

configure_r15

if test "${P8_2_K1A_LIFECYCLE_AUDIT_ONLY:-0}" = 1; then
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'parent_f1_r14_restore_request_completed=true\n'
  printf 'parent_f1_r14_repair_skipped_last_decode=true\n'
  printf 'parent_f1_r14_load_scheduled=true\n'
  printf 'restore_step_lineage=1\n'
  printf 'physical_fa_cpu_only_gate=1\n'
  printf 'compress_aware_pairing_repair=1\n'
  printf 'accepted_capacity_invalidated=false\n'
  printf 'accepted_restore_match_tokens=16384\n'
  printf 'restore_shared_prefix_tokens=32768\n'
  printf 'eagle_aware_logical_lookup=1\n'
  printf 'hit_to_load_admission_lineage=1\n'
  printf 'update_raise_geometry_lineage=1\n'
  printf 'allocate_slots_observation_required=true\n'
  printf 'update_state_after_alloc_observation_required=true\n'
  printf 'connector_load_meta_observation_required=true\n'
  printf 'task_local_observer_behavioral_repair_authorized=true\n'
  printf 'site_packages_edit_authorized=false\n'
  printf 'runtime_dependency_mutation_authorized=false\n'
  printf 'logical_restore_window_required_before_restore=true\n'
  printf 'pressure_context_tokens=36800\n'
  printf 'request_retry_count_exact=0\n'
  printf 'capacity_or_context_change_authorized=false\n'
  printf 'server_side_code_edit_authorized=false\n'
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
    "grading_summary.json": "403b5fc007fbec07628319d46af50c4ecd6314eec39fda8f2fad39ed9189526b",
    "residency_gate_timeline.json": "78ba2fa1c27bdbb4a6512b852e1029d4acd9cf4fc2cdb127297f103bb26e7370",
    "h2d_trigger_summary.json": "eab6d7161dfda5373bc5c20cfcb0efb38adbc6a10b7be29e7723fc2b944b15cd",
    "transfer_trace_summary.json": "1266033f325bb8a1571dd46c563fd28feeb0753fb2b01439dc0830808f93c983",
    "logical_keyspace_probe_diagnostic_summary.json": "8b997ae5e0b8ddc1c9f13791888c27eebd4a6ae1b10a7f21de155908ae8dc8bf",
    "target_store_lineage_summary.json": "5f0dcd40353412ea2d232332ba0aa9e3103c1a0bb35e6dbd4b01e2c4267b3d93",
    "repair_diagnostic_summary.json": "459d0f9aa71587d5359a23aabdb44741d4b41195c6cd56a8e8775fc7d1ae1862",
    "resource_recovery_summary.json": "aaf96cd771158866c72d4a2a6e3fa3f3242838c2cef0fe14dd42e043292f17ba",
    "candidate_manifest.server_local.json": "c739ce99cf7038f80cf0867787a2f850f7909e9306476a61956764abc926208a",
}
for name, digest in expected.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest

grading = json.loads((root / "grading_summary.json").read_text(encoding="utf-8"))
h2d = json.loads((root / "h2d_trigger_summary.json").read_text(encoding="utf-8"))
transfer = json.loads(
    (root / "transfer_trace_summary.json").read_text(encoding="utf-8")
)
assert grading["server_grade"] == (
    "red_p8_2_k1a_r5_f1_r14_h2d_evidence_incomplete"
)
assert grading["operational_grade"] == "operational_recovery_clean"
assert grading["experimental_terminal"] == "restore_request_completed"
assert grading["restore_hit_to_load_gap_class"] == "load_scheduled"
assert h2d["restore_pairing_repair_applied"] is False
assert h2d["restore_pairing_repair_skip_reason"] == (
    "frozen_geometry_not_index_overflow"
)
assert h2d["restore_num_external_tokens_at_alloc"] == 0
assert h2d["restore_num_new_tokens_at_alloc"] == 2
assert h2d["restore_load_scheduled"] is True
assert h2d["restore_entered_reqs_to_load"] is False
assert transfer["h2d_worker_count"] == 8
assert transfer["h2d_bytes_total"] == 1076510720
assert transfer["d2h_store_complete"] is True
PY

exec bash "${COMMON_LIFECYCLE}" "${RESULT_DIR}"
