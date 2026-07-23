#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k1a_r5_f1_r10_cache_stamp_lineage_2026_0723
PARENT_ROOT=${P8_2_K1A_F1_R9_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r9_effective_group_geometry_2026_0723_run01}
COMMON_LIFECYCLE=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.py

configure_r10() {
  export P8_2_K1A_TASK_ID=${TASK_ID}
  export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R10
  export P8_2_K1A_EXECUTION_MODE=authorized_single_lifecycle_cache_stamp_lineage
  export P8_2_K1A_F1_SCHEMA_TAG=p8_2_k1a_r5_f1_r10
  export P8_2_K1A_F1_GRADE_PREFIX=red_p8_2_k1a_r5_f1_r10
  export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_f1_r10_cache_stamp_lineage_attributed_h2d_restore
  export P8_2_K1A_REQUEST_RUNNER=${REQUEST_RUNNER}
  export REQUEST_RUNNER=${REQUEST_RUNNER}
  export P8_2_K1A_TARGET_CACHE_STAMP_LINEAGE=1
  export P8_2_K1A_ALLOW_PRESSURE_BEFORE_KEYSPACE_EXACT=1
  export P8_2_K1A_LOGICAL_KEYSPACE_DIAGNOSTICS=1
  export P8_2_K1A_TARGET_STORE_LINEAGE_DIAGNOSTICS=1
  export P8_2_K1A_REQUIRE_TARGET_STORE_LINEAGE=1
  export P8_2_K1A_REQUIRE_EFFECTIVE_GROUP_GEOMETRY=1
  export P8_2_K1A_REQUIRE_POST_ABORT_FRESH_REVALIDATION=1
  export P8_2_K1A_REQUIRE_LOGICAL_RESTORE_WINDOW_FOR_RESTORE=1
  export P8_2_K1A_RESULT_SUMMARY_TITLE='logical 128-block target from runtime cache-stamp lineage'
  export P8_2_K1A_CLAIM_BOUNDARY=accepted_capacity_single_lifecycle_runtime_cache_stamp_lineage_logical_128_block_window_and_conditional_h2d_candidate_only
  export P8_2_K1A_STOP_ON_FIRST_CPU_TARGET_EVICTION=0
  export P8_2_K1A_REQUEST_ORDER=warmup,target_prime_capture_runtime_cache_stamp_keys,pressure_01_trace_logical_128_block_window_then_abort,restore_follower_after_idle_physical_and_logical_revalidation
  export P8_2_K1A_SKIP_F1_R5_PARENT_PREFLIGHT=1
  export P8_2_K1A_REPO_FILE_LIST=benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r10_cache_stamp_lineage_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r10_cache_stamp_lineage.yaml:tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r10_server_task.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.py:benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
}

configure_r10

if test "${P8_2_K1A_LIFECYCLE_AUDIT_ONLY:-0}" = 1; then
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'parent_f1_r9_runtime_geometry_red_accepted=true\n'
  printf 'accepted_capacity_invalidated=false\n'
  printf 'logical_target_block_count=128\n'
  printf 'target_lineage_capture_boundary=runtime_gpu_block_pool_cache_full_blocks\n'
  printf 'runtime_sparse_block_mask_is_authoritative=true\n'
  printf 'request_finish_null_block_table_used_for_lineage=false\n'
  printf 'unobserved_or_partial_group_fails_closed=true\n'
  printf 'fully_scanned_zero_cacheable_group_not_applicable=true\n'
  printf 'progressive_target_keys_feed_lazy_store_attribution=true\n'
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
    "grading_summary.json": "04e87d5a5d3a1ada5dccf2925a5860cca4a6f83cbd7f5e0f925444eb4cba4f82",
    "residency_gate_timeline.json": "b918ec163720ce73e679db0be48cb48d87530200c199e93f1e0a9dedb79d8b4f",
    "target_store_lineage_summary.json": "14e1a18b24947bd8b02c849b3eefa42fa1597f740bf54153d74b1c42cc6c087c",
    "transfer_trace_summary.json": "aa94e2a9019749ec1fad01fc17fb210811c2af1c8d9f563c2e2d9295716ff8bb",
    "resource_recovery_summary.json": "65eb3136c608ef59c9def9a20a214e6cd6e835c565ab2fa1c1488b22b0a79ac1",
    "candidate_manifest.server_local.json": "8e08ee3d52ee2770f2795fe9588d420dedd5f9659663e1f5e8d22ec75ac2f2af",
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
    "red_p8_2_k1a_r5_f1_r9_target_store_lineage_unobservable_before_pressure"
)
assert grading["operational_grade"] == "operational_recovery_clean"
assert grading["request_count"] == 2
assert grading["pressure_request_count_executed"] == 0
assert grading["required_restore_block_count"] == 128
assert timeline["terminal_decision"] == (
    "target_store_lineage_unobservable_before_pressure"
)
assert lineage["target_fa_key_count"] == 32
assert lineage["target_store_key_count"] == 33
assert lineage["restore_group_applicable_count"] == 6
assert all(
    row["captured_block_count"] == 0
    for row in lineage["restore_group_capture_rows"][2:]
)
assert transfer["d2h_store_complete"] is True
assert transfer["d2h_worker_count"] == 8
assert transfer["d2h_bytes_total"] == 2206846976
assert transfer["h2d_worker_count"] == 0
assert recovery["resource_recovery_exact"] is True
assert recovery["stopped_card_ids"] == list(range(8))
assert recovery["restored_card_ids"] == list(range(8))
PY

exec bash "${COMMON_LIFECYCLE}" "${RESULT_DIR}"
