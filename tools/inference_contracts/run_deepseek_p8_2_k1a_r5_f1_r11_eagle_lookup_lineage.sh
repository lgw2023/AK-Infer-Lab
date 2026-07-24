#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_2026_0723
PARENT_ROOT=${P8_2_K1A_F1_R10_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r10_cache_stamp_lineage_2026_0723_run01}
COMMON_LIFECYCLE=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.py

configure_r11() {
  export P8_2_K1A_TASK_ID=${TASK_ID}
  export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R11
  export P8_2_K1A_EXECUTION_MODE=authorized_single_lifecycle_eagle_lookup_lineage
  export P8_2_K1A_F1_SCHEMA_TAG=p8_2_k1a_r5_f1_r11
  export P8_2_K1A_F1_GRADE_PREFIX=red_p8_2_k1a_r5_f1_r11
  export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_f1_r11_eagle_aware_logical_hit_and_attributed_h2d_restore
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
  export P8_2_K1A_RESULT_SUMMARY_TITLE='EAGLE-aware logical lookup over the exact 16K physical window'
  export P8_2_K1A_CLAIM_BOUNDARY=accepted_capacity_single_lifecycle_eagle_aware_lookup_lineage_legacy_boundary_comparison_and_conditional_h2d_candidate_only
  export P8_2_K1A_STOP_ON_FIRST_CPU_TARGET_EVICTION=0
  export P8_2_K1A_REQUEST_ORDER=warmup,target_prime_capture_runtime_cache_stamp_keys,pressure_01_abort_on_exact_physical_window,post_abort_compare_legacy_and_eagle_aware_lookup,restore_follower_only_after_physical_and_eagle_aware_logical_acceptance
  export P8_2_K1A_SKIP_F1_R5_PARENT_PREFLIGHT=1
  export P8_2_K1A_REPO_FILE_LIST=benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.yaml:tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r11_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.py:benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
}

configure_r11

if test "${P8_2_K1A_LIFECYCLE_AUDIT_ONLY:-0}" = 1; then
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'parent_f1_r10_physical_window_exact=true\n'
  printf 'accepted_capacity_invalidated=false\n'
  printf 'accepted_restore_match_tokens=16384\n'
  printf 'restore_shared_prefix_tokens=32768\n'
  printf 'eagle_aware_logical_lookup=1\n'
  printf 'legacy_capped_probe_retained=true\n'
  printf 'per_attention_group_lookup_lineage_required=true\n'
  printf 'logical_probe_source_independent_from_target_lineage=true\n'
  printf 'runtime_dependency_mutation_authorized=false\n'
  printf 'fixed_pressure_must_execute_after_cache_stamp_lineage=true\n'
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
    "grading_summary.json": "75747dfbad514b7da6b925a3fc586313858ebecf7237c6294d3350f39e63b268",
    "residency_gate_timeline.json": "1fe69786191371be0017b6942dacd1117172cf7b1f1b4120fedcbe842fc4b889",
    "target_store_lineage_summary.json": "23e9d7e6ebee999eb1ad7e299fa160d6dd8737b9bbf31665c9282d07aa763cb6",
    "logical_keyspace_probe_diagnostic_summary.json": "efb7d4ae48b37fcbf6b619bd477a90337b3d67e0793dfd0c9b75e7332f2c3e17",
    "transfer_trace_summary.json": "e829673f21eab07af6f6a50d6a9bc9e25c8668561bade8b0a083fdcc3d5b3d77",
    "repair_diagnostic_summary.json": "459d0f9aa71587d5359a23aabdb44741d4b41195c6cd56a8e8775fc7d1ae1862",
    "resource_recovery_summary.json": "02715a7e142a53be15f8ff236c253fc12a233ce582e057998e529e53c148ded8",
    "candidate_manifest.server_local.json": "5067ac9f22f70eec8caf807189fb3f8f9ef6cab3c78588c53ee1d822268078a1",
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
logical = json.loads(
    (root / "logical_keyspace_probe_diagnostic_summary.json").read_text(
        encoding="utf-8"
    )
)
transfer = json.loads(
    (root / "transfer_trace_summary.json").read_text(encoding="utf-8")
)
repair = json.loads(
    (root / "repair_diagnostic_summary.json").read_text(encoding="utf-8")
)
recovery = json.loads(
    (root / "resource_recovery_summary.json").read_text(encoding="utf-8")
)
assert grading["server_grade"] == (
    "red_p8_2_k1a_r5_f1_r10_logical_restore_hit_incomplete_after_physical_window"
)
assert grading["operational_grade"] == "operational_recovery_clean"
assert grading["request_count"] == 3
assert grading["pressure_request_count_executed"] == 1
assert grading["required_restore_block_count"] == 128
assert grading["physical_cpu_only_window_event_count"] == 8
assert timeline["post_abort_gate"]["logical_restore_match_tokens"] == 0
assert timeline["post_abort_gate"]["restore_allowed"] is False
assert lineage["target_store_lineage_capture_exact"] is True
assert lineage["target_store_key_count"] == 40
assert lineage["target_store_completed_key_count_max"] == 40
assert lineage["target_gpu_evicted_key_count"] == 40
assert lineage["target_cpu_evicted_key_count"] == 0
assert lineage["physical_cpu_only_window_event_count"] == 8
assert logical["probe_event_count"] == 0
assert transfer["d2h_store_complete"] is True
assert transfer["d2h_worker_count"] == 8
assert transfer["d2h_bytes_total"] == 2206846976
assert transfer["h2d_worker_count"] == 0
assert repair["manager_eagle_propagation_ok"] is True
assert repair["eagle_manager_count_max"] == 2
assert repair["lcm_block_sizes"] == [16384]
assert recovery["resource_recovery_exact"] is True
assert recovery["stopped_card_ids"] == list(range(8))
assert recovery["restored_card_ids"] == list(range(8))
PY

exec bash "${COMMON_LIFECYCLE}" "${RESULT_DIR}"
