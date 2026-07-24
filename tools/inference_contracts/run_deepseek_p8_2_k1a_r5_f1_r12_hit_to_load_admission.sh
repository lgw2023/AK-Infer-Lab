#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k1a_r5_f1_r12_hit_to_load_admission_2026_0724
PARENT_ROOT=${P8_2_K1A_F1_R11_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_2026_0723_run01}
COMMON_LIFECYCLE=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r12_hit_to_load_admission.py

configure_r12() {
  export P8_2_K1A_TASK_ID=${TASK_ID}
  export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R12
  export P8_2_K1A_EXECUTION_MODE=authorized_single_lifecycle_hit_to_load_admission
  export P8_2_K1A_F1_SCHEMA_TAG=p8_2_k1a_r5_f1_r12
  export P8_2_K1A_F1_GRADE_PREFIX=red_p8_2_k1a_r5_f1_r12
  export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_f1_r12_hit_to_load_admission_and_attributed_h2d_restore
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
  export P8_2_K1A_RESULT_SUMMARY_TITLE='CPU-hit to H2D-load admission lineage on the exact 16K window'
  export P8_2_K1A_CLAIM_BOUNDARY=accepted_capacity_single_lifecycle_cpu_hit_to_load_admission_discrimination_and_conditional_h2d_candidate_only
  export P8_2_K1A_STOP_ON_FIRST_CPU_TARGET_EVICTION=0
  export P8_2_K1A_REQUEST_ORDER=warmup,target_prime_capture_runtime_cache_stamp_keys,pressure_01_abort_on_exact_physical_window,post_abort_eagle_aware_logical_acceptance,restore_follower_with_hit_to_load_admission_lineage
  export P8_2_K1A_SKIP_F1_R5_PARENT_PREFLIGHT=1
  export P8_2_K1A_REPO_FILE_LIST=benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r12_hit_to_load_admission_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r12_hit_to_load_admission.yaml:tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r12_hit_to_load_admission.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r12_hit_to_load_admission.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r12_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r12_hit_to_load_admission.py:benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
}

configure_r12

if test "${P8_2_K1A_LIFECYCLE_AUDIT_ONLY:-0}" = 1; then
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'parent_f1_r11_cpu_hit_exact=true\n'
  printf 'parent_f1_r11_restore_load_scheduled=false\n'
  printf 'accepted_capacity_invalidated=false\n'
  printf 'accepted_restore_match_tokens=16384\n'
  printf 'restore_shared_prefix_tokens=32768\n'
  printf 'eagle_aware_logical_lookup=1\n'
  printf 'hit_to_load_admission_lineage=1\n'
  printf 'allocate_slots_observation_required=true\n'
  printf 'update_state_after_alloc_observation_required=true\n'
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
    "grading_summary.json": "78be6275a0142918aff454bbda91e6bdcb359b20cdea6adefe31798c75fea633",
    "residency_gate_timeline.json": "8e29e91836490c80e932f19c0aced534e659454fded42abc04f351b27c18f5a9",
    "h2d_trigger_summary.json": "c11b92b1af91759feedafbb697a58aaf0d7c4f2d5f8bbeaedf4781619b602d39",
    "transfer_trace_summary.json": "9fe1cf8ff256d6cb120f3d7babec72527da8a90df03130651ae7a2cdf62b0d4f",
    "logical_keyspace_probe_diagnostic_summary.json": "cfbabbcbf74602ad60f20c1a6e20874a0a8bdb0ff150cdec263f0fd842a8dc15",
    "target_store_lineage_summary.json": "d2b7f24a5f885f6026692badf590107b2b8082c40bff63edb13d60953e077343",
    "repair_diagnostic_summary.json": "459d0f9aa71587d5359a23aabdb44741d4b41195c6cd56a8e8775fc7d1ae1862",
    "resource_recovery_summary.json": "7374e1763cf2f20793c66865a31f860fe6040888319af1f433d69cc6eae234a6",
    "candidate_manifest.server_local.json": "bb04845f8e16a9acc8fd7f4f445b2c115a9124469e234ef00a3b3dbb6fa9827d",
}
for name, digest in expected.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest

grading = json.loads((root / "grading_summary.json").read_text(encoding="utf-8"))
timeline = json.loads(
    (root / "residency_gate_timeline.json").read_text(encoding="utf-8")
)
h2d = json.loads((root / "h2d_trigger_summary.json").read_text(encoding="utf-8"))
transfer = json.loads(
    (root / "transfer_trace_summary.json").read_text(encoding="utf-8")
)
logical = json.loads(
    (root / "logical_keyspace_probe_diagnostic_summary.json").read_text(
        encoding="utf-8"
    )
)
lineage = json.loads(
    (root / "target_store_lineage_summary.json").read_text(encoding="utf-8")
)
recovery = json.loads(
    (root / "resource_recovery_summary.json").read_text(encoding="utf-8")
)
assert grading["server_grade"] == (
    "red_p8_2_k1a_r5_f1_r11_h2d_evidence_incomplete"
)
assert grading["operational_grade"] == "operational_recovery_clean"
assert grading["experimental_terminal"] == "restore_request_failure"
assert grading["request_count"] == 4
assert grading["pressure_request_count_executed"] == 1
assert grading["required_restore_block_count"] == 128
assert timeline["post_abort_gate"]["logical_restore_window_exact"] is True
assert timeline["post_abort_gate"]["restore_allowed"] is True
assert timeline["restore_sent"] is True
assert h2d["restore_cpu_hit_exact"] is True
assert h2d["restore_load_scheduled"] is False
assert h2d["h2d_restore_mechanism_candidate"] is False
assert transfer["restore_cpu_hit_tokens_max"] == 16384
assert transfer["restore_load_scheduled_count"] == 0
assert transfer["h2d_worker_count"] == 0
assert transfer["h2d_bytes_total"] == 0
assert transfer["d2h_store_complete"] is True
assert transfer["d2h_worker_count"] == 8
assert transfer["d2h_bytes_total"] == 2206846976
assert logical["probe_event_count"] == 152
assert lineage["target_store_lineage_capture_exact"] is True
assert lineage["target_store_key_count"] == 40
assert lineage["target_store_completed_key_count_max"] == 40
assert lineage["target_gpu_evicted_key_count"] == 40
assert lineage["target_cpu_evicted_key_count"] == 0
assert recovery["resource_recovery_exact"] is True
assert recovery["stopped_card_ids"] == list(range(8))
assert recovery["restored_card_ids"] == list(range(8))
PY

exec bash "${COMMON_LIFECYCLE}" "${RESULT_DIR}"
