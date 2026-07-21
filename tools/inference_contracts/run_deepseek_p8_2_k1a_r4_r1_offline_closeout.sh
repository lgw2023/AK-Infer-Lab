#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TASK_ID=p8_2_k1a_r4_r1_store_only_source_semantics_replay_2026_0721
PARENT_R4_RESULT_ROOT=${P8_2_K1A_R4_R1_PARENT_R4_RESULT_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r4_store_only_refinalization_and_trace_attribution_2026_0720_run01}
MANIFEST_ROOT=${P8_2_K1A_R4_R1_MANIFEST_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_2026_0720_run01}
RAW_RESULT_ROOT=${P8_2_K1A_R4_R1_RAW_RESULT_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r2_r1_r1_r1_deepseek_v4_flash_causal_exception_replay_2026_0720_run01}
VLLM_ROOT=${P8_2_K1A_R4_R1_VLLM_ROOT:-/data/node0_disk1/vllm-0.22.1/vllm}
MANAGER_SHA256=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
BLOCK_POOL_SHA256=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
CANDIDATE_GRADE=candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout
BLOCKED_GRADE=blocked_p8_2_k1a_r4_r1_offline_closeout_gate

if [[ "${P8_2_K1A_R4_R1_AUDIT_ONLY:-0}" == 1 ]]; then
  printf '%s\n' \
    "task_id=${TASK_ID}" \
    "execution_mode=authorized_read_only_r4_parent_validation_and_same_evidence_offline_source_semantics_replay" \
    "parent_r4_grade=blocked_p8_2_k1a_r4_offline_closeout_gate" \
    "expected_dequeue_method=popleft_n" \
    "expected_candidate_grade=${CANDIDATE_GRADE}" \
    "npu_execution_authorized=false" \
    "keep_alive_stop_authorized=false" \
    "vllm_server_start_authorized=false" \
    "model_requests_authorized=false" \
    "result_transfer_authorized=true" \
    "transfer_method_selected=false" \
    "next_task_authorized=false"
  exit 0
fi

if [[ $# -ne 1 ]]; then
  echo "usage: $0 RESULT_ROOT" >&2
  exit 2
fi

RESULT_ROOT=$1
test ! -e "${RESULT_ROOT}"
test -f "${PARENT_R4_RESULT_ROOT}/candidate_manifest.server_local.json"
test -f "${MANIFEST_ROOT}/candidate_manifest.server_local.json"
test -d "${RAW_RESULT_ROOT}/runtime/offload_trace"
test -f "${RAW_RESULT_ROOT}/modes/prefix_cache_on/raw_request_results.jsonl"
test -f "${VLLM_ROOT}/v1/simple_kv_offload/manager.py"
test -f "${VLLM_ROOT}/v1/core/block_pool.py"

python3 - "${PARENT_R4_RESULT_ROOT}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
manifest = json.loads(
    (root / "candidate_manifest.server_local.json").read_text(encoding="utf-8")
)
assert manifest["payload_file_count"] == 9
assert manifest["payload_total_bytes"] == 27943
assert manifest["generated_content_retained"] is False
assert manifest["token_ids_retained"] is False
for row in manifest["files"]:
    path = root / row["relative_path"]
    assert path.is_file()
    assert path.stat().st_size == row["bytes"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
    assert row["sensitivity"] == (
        "bounded_operational_metadata_no_content_or_token_ids"
    )
grading = json.loads((root / "grading_summary.json").read_text(encoding="utf-8"))
assert grading["task_grade"] == "blocked_p8_2_k1a_r4_offline_closeout_gate"
assert grading["store_only_refinalization_accepted"] is True
assert grading["trace_attribution_gate"] == "pass"
assert grading["source_semantics_gate"] == "fail"
source = json.loads(
    (root / "source_semantics/cpu_tier_source_semantics.json").read_text(
        encoding="utf-8"
    )
)
assert source["block_pool_hash_exact"] is True
assert source["cpu_pool_allocation_may_evict_cached_hash_entry"] is False
PY

mkdir -p "${RESULT_ROOT}/source_semantics"

export P8_2_K1A_STORE_ONLY_GRADE=yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_store_only_no_restore
export P8_2_K1A_CPU_BYTES_TO_USE=3444834304
export P8_2_K1A_CPU_BYTES_TO_USE_PER_RANK=430604288

python3 "${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py" \
  refinalize-bounded \
  --source-dir "${MANIFEST_ROOT}" \
  --output-dir "${RESULT_ROOT}/refinalization"

python3 "${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_trace_attribution.py" \
  trace-attribution \
  --source-result-dir "${RAW_RESULT_ROOT}" \
  --output-dir "${RESULT_ROOT}/trace_attribution"

python3 "${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_trace_attribution.py" \
  source-audit \
  --vllm-root "${VLLM_ROOT}" \
  --output "${RESULT_ROOT}/source_semantics/cpu_tier_source_semantics.json" \
  --expected-manager-sha256 "${MANAGER_SHA256}" \
  --expected-block-pool-sha256 "${BLOCK_POOL_SHA256}"

python3 "${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_trace_attribution.py" \
  finalize-closeout \
  --result-root "${RESULT_ROOT}" \
  --task-id "${TASK_ID}" \
  --candidate-green-grade "${CANDIDATE_GRADE}" \
  --blocked-grade "${BLOCKED_GRADE}"

python3 - "${RESULT_ROOT}" "${TASK_ID}" "${CANDIDATE_GRADE}" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
task_id = sys.argv[2]
candidate_grade = sys.argv[3]
grading = json.loads((root / "grading_summary.json").read_text(encoding="utf-8"))
source = json.loads(
    (root / "source_semantics/cpu_tier_source_semantics.json").read_text(
        encoding="utf-8"
    )
)
manifest = json.loads(
    (root / "candidate_manifest.server_local.json").read_text(encoding="utf-8")
)
assert grading["task_id"] == task_id
assert grading["task_grade"] == candidate_grade
assert source["source_semantics_gate"] == "pass"
assert source["free_block_queue_dequeue_method"] == "popleft_n"
assert source["capacity_churn_hypothesis_supported"] is True
assert source["pressure_evicted_prime_from_cpu_tier_proven"] is False
assert source["h2d_absence_cause_proven_as_unique"] is False
assert manifest["payload_file_count"] == 9
assert manifest["manifest_is_transfer_control_file"] is True
assert manifest["transfer_file_count_including_manifest"] == 10
PY
