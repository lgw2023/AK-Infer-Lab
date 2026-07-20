#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TASK_ID=p8_2_k1a_r4_store_only_refinalization_and_trace_attribution_2026_0720
MANIFEST_ROOT=${P8_2_K1A_R4_MANIFEST_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_2026_0720_run01}
RAW_RESULT_ROOT=${P8_2_K1A_R4_RAW_RESULT_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r2_r1_r1_r1_deepseek_v4_flash_causal_exception_replay_2026_0720_run01}
VLLM_ROOT=${P8_2_K1A_R4_VLLM_ROOT:-/data/node0_disk1/vllm-0.22.1/vllm}
MANAGER_SHA256=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
BLOCK_POOL_SHA256=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283

if [[ "${P8_2_K1A_R4_AUDIT_ONLY:-0}" == 1 ]]; then
  printf '%s\n' \
    "task_id=${TASK_ID}" \
    "execution_mode=authorized_read_only_offline_store_only_refinalization_trace_attribution_and_source_semantics" \
    "parent_manifest_sha256=6463f2f13e5c7149e6fcbb502caad5edfce1f9b7d82c16c74a72babd64035498" \
    "parent_payload_file_count=21" \
    "parent_payload_total_bytes=41185" \
    "parent_server_grade=red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete" \
    "expected_refinalized_grade=yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_store_only_no_restore" \
    "manager_sha256=${MANAGER_SHA256}" \
    "block_pool_sha256=${BLOCK_POOL_SHA256}" \
    "npu_execution_authorized=false" \
    "model_requests_authorized=false" \
    "result_transfer_authorized=true" \
    "next_task_authorized=false"
  exit 0
fi

if [[ $# -ne 1 ]]; then
  echo "usage: $0 RESULT_ROOT" >&2
  exit 2
fi

RESULT_ROOT=$1
test ! -e "${RESULT_ROOT}"
test -f "${MANIFEST_ROOT}/candidate_manifest.server_local.json"
test -d "${RAW_RESULT_ROOT}/runtime/offload_trace"
test -f "${RAW_RESULT_ROOT}/modes/prefix_cache_on/raw_request_results.jsonl"
test -f "${VLLM_ROOT}/v1/simple_kv_offload/manager.py"
test -f "${VLLM_ROOT}/v1/core/block_pool.py"
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
  --result-root "${RESULT_ROOT}"
