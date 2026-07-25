#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_2026_0725
PARENT_ROOT=${P8_2_K1A_F1_R13_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r13_update_raise_geometry_2026_0724_run01}
COMMON_LIFECYCLE=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.py

configure_r14() {
  export P8_2_K1A_TASK_ID=${TASK_ID}
  export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R14
  export P8_2_K1A_EXECUTION_MODE=authorized_single_lifecycle_compress_aware_pairing_repair
  export P8_2_K1A_F1_SCHEMA_TAG=p8_2_k1a_r5_f1_r14
  export P8_2_K1A_F1_GRADE_PREFIX=red_p8_2_k1a_r5_f1_r14
  export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_and_attributed_h2d_restore
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
  export P8_2_K1A_RESULT_SUMMARY_TITLE='task-local compress-aware pairing repair on the exact 16K window'
  export P8_2_K1A_CLAIM_BOUNDARY=accepted_capacity_single_lifecycle_task_local_compress_aware_pairing_repair_and_conditional_h2d_candidate_only
  export P8_2_K1A_STOP_ON_FIRST_CPU_TARGET_EVICTION=0
  export P8_2_K1A_REQUEST_ORDER=warmup,target_prime_capture_runtime_cache_stamp_keys,pressure_01_abort_on_exact_physical_window,post_abort_eagle_aware_logical_acceptance,restore_follower_with_compress_aware_pairing_repair
  export P8_2_K1A_SKIP_F1_R5_PARENT_PREFLIGHT=1
  export P8_2_K1A_REPO_FILE_LIST=benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.yaml:tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r14_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.py:benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
}

configure_r14

if test "${P8_2_K1A_LIFECYCLE_AUDIT_ONLY:-0}" = 1; then
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'parent_f1_r13_index_error_gpu_cpu_pairing=true\n'
  printf 'parent_f1_r13_restore_load_scheduled=false\n'
  printf 'accepted_capacity_invalidated=false\n'
  printf 'accepted_restore_match_tokens=16384\n'
  printf 'restore_shared_prefix_tokens=32768\n'
  printf 'eagle_aware_logical_lookup=1\n'
  printf 'hit_to_load_admission_lineage=1\n'
  printf 'update_raise_geometry_lineage=1\n'
  printf 'compress_aware_pairing_repair=1\n'
  printf 'repair_enable_env=P8_2_K1A_ENABLE_COMPRESS_AWARE_PAIRING_REPAIR\n'
  printf 'repair_requires_exact_manager_sha=true\n'
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
    "grading_summary.json": "ae89aa2e9c0373aa74a528ec732d8d12ebcc9e03d55e06d418aeb3e122b0a9a9",
    "residency_gate_timeline.json": "09904e8e605fd9112a9e55c9c6bdf53c79ce2e1c7d98ae2230f42f80271dbfa9",
    "h2d_trigger_summary.json": "98e0cbca45929b8e67cfc5655c0a1afe7623c50316937479d5413d667023ba4d",
    "transfer_trace_summary.json": "0463048453bec7813268e8f2891a001621c079cddbe93d6b9e7956861451fff1",
    "logical_keyspace_probe_diagnostic_summary.json": "77fbcf4290fe9a8bd76b227cc373d60687e229f3118b3a1635573e10ca0e31c1",
    "target_store_lineage_summary.json": "61530a2c3fc20a57fd94922f1629b73e26b562085cea83371a4755b8a0b75515",
    "repair_diagnostic_summary.json": "459d0f9aa71587d5359a23aabdb44741d4b41195c6cd56a8e8775fc7d1ae1862",
    "resource_recovery_summary.json": "f64373b464356cdaae72dac2e645971c48c5df986b9eb4046195af031f0218ad",
    "candidate_manifest.server_local.json": "248655f8bfce690f0d2c19a01a1fb8b2a0be699377541f7d55542dd0098bdf4b",
}
for name, digest in expected.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest

grading = json.loads((root / "grading_summary.json").read_text(encoding="utf-8"))
h2d = json.loads((root / "h2d_trigger_summary.json").read_text(encoding="utf-8"))
transfer = json.loads(
    (root / "transfer_trace_summary.json").read_text(encoding="utf-8")
)
assert grading["server_grade"] == (
    "red_p8_2_k1a_r5_f1_r13_h2d_evidence_incomplete"
)
assert grading["operational_grade"] == "operational_recovery_clean"
assert grading["experimental_terminal"] == "restore_request_failure"
assert grading["restore_hit_to_load_gap_class"] == "update_raised"
assert grading["restore_update_raise_subclass"] == "index_error_gpu_cpu_pairing"
assert h2d["restore_update_raise_subclass"] == "index_error_gpu_cpu_pairing"
assert h2d["restore_first_pairing_overflow_group_index"] == 0
assert h2d["restore_first_overflow_needed_index"] == 96
assert h2d["restore_first_overflow_gpu_len"] == 32
assert h2d["restore_num_cached_fa_blocks"] == 0
assert h2d["restore_load_scheduled"] is False
assert transfer["h2d_worker_count"] == 0
assert transfer["h2d_bytes_total"] == 0
assert transfer["d2h_store_complete"] is True
PY

exec bash "${COMMON_LIFECYCLE}" "${RESULT_DIR}"
