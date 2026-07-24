#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k1a_r5_f1_r13_update_raise_geometry_2026_0724
PARENT_ROOT=${P8_2_K1A_F1_R12_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r12_hit_to_load_admission_2026_0724_run02}
COMMON_LIFECYCLE=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r13_update_raise_geometry.py

configure_r13() {
  export P8_2_K1A_TASK_ID=${TASK_ID}
  export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R13
  export P8_2_K1A_EXECUTION_MODE=authorized_single_lifecycle_update_raise_geometry
  export P8_2_K1A_F1_SCHEMA_TAG=p8_2_k1a_r5_f1_r13
  export P8_2_K1A_F1_GRADE_PREFIX=red_p8_2_k1a_r5_f1_r13
  export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_f1_r13_update_raise_geometry_and_attributed_h2d_restore
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
  export P8_2_K1A_RESULT_SUMMARY_TITLE='update_state_after_alloc raise exception and pairing geometry on the exact 16K window'
  export P8_2_K1A_CLAIM_BOUNDARY=accepted_capacity_single_lifecycle_update_raise_exception_and_pairing_geometry_discrimination_and_conditional_h2d_candidate_only
  export P8_2_K1A_STOP_ON_FIRST_CPU_TARGET_EVICTION=0
  export P8_2_K1A_REQUEST_ORDER=warmup,target_prime_capture_runtime_cache_stamp_keys,pressure_01_abort_on_exact_physical_window,post_abort_eagle_aware_logical_acceptance,restore_follower_with_update_raise_geometry_lineage
  export P8_2_K1A_SKIP_F1_R5_PARENT_PREFLIGHT=1
  export P8_2_K1A_REPO_FILE_LIST=benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r13_update_raise_geometry_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r13_update_raise_geometry.yaml:tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r13_update_raise_geometry.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r13_update_raise_geometry.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r13_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r13_update_raise_geometry.py:benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
}

configure_r13

if test "${P8_2_K1A_LIFECYCLE_AUDIT_ONLY:-0}" = 1; then
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'parent_f1_r12_update_raised=true\n'
  printf 'parent_f1_r12_restore_load_scheduled=false\n'
  printf 'accepted_capacity_invalidated=false\n'
  printf 'accepted_restore_match_tokens=16384\n'
  printf 'restore_shared_prefix_tokens=32768\n'
  printf 'eagle_aware_logical_lookup=1\n'
  printf 'hit_to_load_admission_lineage=1\n'
  printf 'update_raise_geometry_lineage=1\n'
  printf 'allocate_slots_observation_required=true\n'
  printf 'update_state_after_alloc_observation_required=true\n'
  printf 'update_raise_error_type_required=true\n'
  printf 'pairing_geometry_preflight_required=true\n'
  printf 'connector_load_meta_observation_required=true\n'
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
    "grading_summary.json": "b644f197ace6d9d4829831e1303fe4582a7eaf7f5d13be8c0d5ea60462b5ea8c",
    "residency_gate_timeline.json": "c1ff9de2492908418dd3468d42e79519226ceab87c1cb350158eaed57c65c62b",
    "h2d_trigger_summary.json": "f44aff05aefee6191ac7e8b644b639172a3dab48db2a18408646f7aa26fa7c0e",
    "transfer_trace_summary.json": "88fa66f31989bb5a0b958904b7599f2e9af5d8626600408af49ccb1c47f2da5c",
    "logical_keyspace_probe_diagnostic_summary.json": "0fa734a9fb284d9ebf344843565ca8b7591cac4248f008f8e2c224b3b2a97a45",
    "target_store_lineage_summary.json": "ee7fed15ef78ed503a50453cf93eddffbe57ba167075549db684a4f55eaf5ab0",
    "repair_diagnostic_summary.json": "459d0f9aa71587d5359a23aabdb44741d4b41195c6cd56a8e8775fc7d1ae1862",
    "resource_recovery_summary.json": "1af761a643b8ea42ea74f9a6b5f4a9baa7bed5a4aa895c421f090cd43da1df61",
    "candidate_manifest.server_local.json": "da2f19ee6a0e3d3b459110d5d7fefc77746fbde451989e2e467102e3f6528d3e",
}
for name, digest in expected.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest

grading = json.loads((root / "grading_summary.json").read_text(encoding="utf-8"))
h2d = json.loads((root / "h2d_trigger_summary.json").read_text(encoding="utf-8"))
transfer = json.loads(
    (root / "transfer_trace_summary.json").read_text(encoding="utf-8")
)
assert grading["server_grade"] == (
    "red_p8_2_k1a_r5_f1_r12_h2d_evidence_incomplete"
)
assert grading["operational_grade"] == "operational_recovery_clean"
assert grading["experimental_terminal"] == "restore_request_failure"
assert grading["restore_hit_to_load_gap_class"] == "update_raised"
assert h2d["restore_hit_to_load_gap_class"] == "update_raised"
assert h2d["restore_allocate_slots_ok"] is True
assert h2d["restore_update_after_alloc_called"] is True
assert h2d["restore_pending_non_null_block_count"] == 40
assert h2d["restore_num_new_tokens_at_alloc"] == 0
assert h2d["restore_load_scheduled"] is False
assert transfer["h2d_worker_count"] == 0
assert transfer["h2d_bytes_total"] == 0
assert transfer["d2h_store_complete"] is True
PY

exec bash "${COMMON_LIFECYCLE}" "${RESULT_DIR}"
