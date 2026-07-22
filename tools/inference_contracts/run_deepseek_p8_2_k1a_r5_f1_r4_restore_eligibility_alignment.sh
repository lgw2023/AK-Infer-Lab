#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_2026_0722
F1_R3_ROOT=${P8_2_K1A_F1_R3_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722_run01}
REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py
SHARED_MODE_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
SHARED_MODE_PATCH_SHA256=5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'execution_mode=authorized_single_lifecycle_full_restore_eligibility_alignment\n'
  printf 'parent_f1_r3_grade=red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete\n'
  printf 'npu_execution_authorized=true\n'
  printf 'accepted_cpu_blocks_per_rank=128\n'
  printf 'required_restore_block_count=128\n'
  printf 'restore_match_tokens_required=16384\n'
  printf 'legacy_64_block_subset_authorizes_restore=false\n'
  printf 'all_kv_groups_required=true\n'
  printf 'pressure_context_tokens=36800\n'
  printf 'capacity_change_authorized=false\n'
  printf 'full_request_window_watch_required=true\n'
  printf 'formal_model_lifecycle_count_exact=1\n'
  printf 'model_request_count_exact=4\n'
  printf 'completed_request_count_exact=3\n'
  printf 'intentional_pressure_abort_count_exact=1\n'
  printf 'request_retry_count_exact=0\n'
  printf 'result_transfer_authorized=true\n'
  printf 'transfer_method_selected=false\n'
  printf 'next_task_authorized=false\n'
}

if test "${P8_2_K1A_F1_R4_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test ! -e "${RESULT_DIR}"
test -f "${REQUEST_RUNNER}"
test -f "${SHARED_MODE_PATCH}"
test "$(sha256sum "${SHARED_MODE_PATCH}" | awk '{print $1}')" = \
  "${SHARED_MODE_PATCH_SHA256}"
test -d "${F1_R3_ROOT}"
test -f "${F1_R3_ROOT}/grading_summary.json"
test -f "${F1_R3_ROOT}/candidate_manifest.server_local.json"

python3 - "${F1_R3_ROOT}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
expected = {
    "grading_summary.json": "14d761452ea7f2c2b6259a441fb3995d336bbf9bb8e605045c114095a9f0988e",
    "h2d_trigger_summary.json": "ac14adbba9b80e459c42e4113343be90aa836e533dd56c9812f7727706c82e39",
    "residency_gate_timeline.json": "494cee6c1cbe51957c5d45956a1389c266fcfe533fccefdd5abc5a18fb72e350",
    "candidate_manifest.server_local.json": "4299261a926e342366ce841684c48c083f62259e153ff67038359fe81b438371",
}
for name, digest in expected.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
grading = json.loads((root / "grading_summary.json").read_text(encoding="utf-8"))
assert grading["server_grade"] == "red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete"
assert grading["pressure_context_tokens"] == 36800
assert grading["window_valid_after_abort"] is True
assert grading["h2d_restore_mechanism_candidate"] is False
PY

export P8_2_K1A_TASK_ID=${TASK_ID}
export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R4
export P8_2_K1A_EXECUTION_MODE=authorized_single_lifecycle_full_restore_eligibility_alignment
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
export P8_2_K1A_REQUEST_COUNT_MIN=4
export P8_2_K1A_REQUEST_COUNT_MAX=4
export P8_2_K1A_REQUEST_ORDER=warmup,target_prime,pressure_01_abort_on_full_restore_eligibility,restore_follower_after_idle
export P8_2_K1A_DIAGNOSTIC_MODE_PATCH=${SHARED_MODE_PATCH}
export P8_2_K1A_DIAGNOSTIC_MODE_PATCH_SHA256=${SHARED_MODE_PATCH_SHA256}
export P8_2_K1A_REQUEST_RUNNER=${REQUEST_RUNNER}
export REQUEST_RUNNER=${REQUEST_RUNNER}
export P8_2_K1A_H2D_RESIDENCY_OBSERVER=${SCRIPT_DIR}/p8_2_k1a_h2d_residency_observer.py
export P8_2_K1A_EXPECTED_COMMAND_SHA256=89a9a105da5a04a3207c638b6999858ed32bff0f438c2cfb617b03905d1efe2f
export P8_2_K1A_REPO_FILE_LIST=benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.yaml:tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py:tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py:benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
export P8_2_K1A_RESULT_TRANSFER_AUTHORIZED=true
export P8_2_K1A_DEFER_FINALIZE=1

if test "${P8_2_K1A_MODE_AUDIT_ONLY:-0}" = 1; then
  exec bash "${SCRIPT_DIR}/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh" "${RESULT_DIR}"
fi
exec bash "${SCRIPT_DIR}/run_deepseek_p8_2_k1a_simple_cpu_offload.sh" "${RESULT_DIR}"
