#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
TASK_ID=p8_2_k1a_r5_f0_h2d_trigger_feasibility_2026_0721
EXECUTION_MODE=authorized_read_only_r4_r1_r2_source_observer_and_trigger_feasibility_no_npu
READY_GRADE=candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility
R4_R1_ROOT=${P8_2_K1A_R5_F0_R4_R1_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r4_r1_store_only_source_semantics_replay_2026_0721_run01}
R2_ROOT=${P8_2_K1A_R5_F0_R2_ROOT:-${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_dual_track_k1a_r2_rendezvous_and_p8_3_i0_r1_taxonomy_2026_0717_run01/p8_2_k1a_r2_geometry_and_allocator}
GEOMETRY_SUMMARY=${P8_2_K1A_R5_F0_GEOMETRY_SUMMARY:-${R2_ROOT}/k1a_r2_geometry_summary.json}
RENDEZVOUS_SUMMARY=${P8_2_K1A_R5_F0_RENDEZVOUS_SUMMARY:-${R2_ROOT}/geometry_probe/runtime/geometry/geometry.rendezvous.complete.json}
ALLOCATOR_SUMMARY=${P8_2_K1A_R5_F0_ALLOCATOR_SUMMARY:-${R2_ROOT}/pinned_allocator_envelope_summary.json}
VLLM_ROOT=${P8_2_K1A_R5_F0_VLLM_ROOT:-/data/node0_disk1/vllm-0.22.1/vllm}
MANAGER_SOURCE=${P8_2_K1A_R5_F0_MANAGER_SOURCE:-${VLLM_ROOT}/v1/simple_kv_offload/manager.py}
BLOCK_POOL_SOURCE=${P8_2_K1A_R5_F0_BLOCK_POOL_SOURCE:-${VLLM_ROOT}/v1/core/block_pool.py}
ANALYZER=${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_h2d_trigger_feasibility.py
OBSERVER=${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py
RESULT_ROOT=${1:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f0_h2d_trigger_feasibility_2026_0721_run01}

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'execution_mode=%s\n' "${EXECUTION_MODE}"
  printf 'npu_execution_authorized=false\n'
  printf 'keep_alive_stop_authorized=false\n'
  printf 'vllm_server_start_authorized=false\n'
  printf 'model_requests_authorized=false\n'
  printf 'formal_model_lifecycle_count=0\n'
  printf 'model_request_count=0\n'
  printf 'gpu_blocks_per_rank=5048\n'
  printf 'cpu_blocks_per_rank=128\n'
  printf 'target_prefix_tokens=8192\n'
  printf 'pressure_context_tokens=131072\n'
  printf 'pressure_request_count_candidate=5\n'
  printf 'formal_h2d_trigger_lifecycle_allowed=false\n'
  printf 'result_transfer_authorized=true\n'
  printf 'transfer_method_selected=false\n'
  printf 'next_task_authorized=false\n'
}

if test "${P8_2_K1A_R5_F0_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test ! -e "${RESULT_ROOT}"
test -f "${ANALYZER}"
test -f "${OBSERVER}"
test -f "${R4_R1_ROOT}/candidate_manifest.server_local.json"
test "$(sha256sum "${R4_R1_ROOT}/candidate_manifest.server_local.json" | awk '{print $1}')" = 008f753135f087201c0e8f0f53662dede1124691a2a551064f89e65a7a23ddde
test "$(sha256sum "${GEOMETRY_SUMMARY}" | awk '{print $1}')" = 8430730a583371ebdcc1cb35ff80903376a007cb3f2645ce6a55114bdb9ea6d1
test "$(sha256sum "${RENDEZVOUS_SUMMARY}" | awk '{print $1}')" = fa258790475303b88a41d4e3f2db684a41a79026b22d434ba9827f0275280796
test "$(sha256sum "${ALLOCATOR_SUMMARY}" | awk '{print $1}')" = 99f997a66cb14aeaf1941d34c525729c70dcda0569d45c465a0f1c7f55dfc6b2
test "$(sha256sum "${MANAGER_SOURCE}" | awk '{print $1}')" = fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
test "$(sha256sum "${BLOCK_POOL_SOURCE}" | awk '{print $1}')" = 36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283

python3 "${ANALYZER}" analyze \
  --r4-r1-root "${R4_R1_ROOT}" \
  --geometry-summary "${GEOMETRY_SUMMARY}" \
  --rendezvous-summary "${RENDEZVOUS_SUMMARY}" \
  --allocator-summary "${ALLOCATOR_SUMMARY}" \
  --manager-source "${MANAGER_SOURCE}" \
  --block-pool-source "${BLOCK_POOL_SOURCE}" \
  --gpu-blocks-per-rank 5048 \
  --output-dir "${RESULT_ROOT}"

test "$(cat "${RESULT_ROOT}/task_grade.txt")" = "${READY_GRADE}"
python3 - "${RESULT_ROOT}/candidate_manifest.server_local.json" <<'PY'
import json
from pathlib import Path
import sys

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert manifest["payload_file_count"] == 8
assert manifest["payload_total_bytes"] <= 71680
assert manifest["generated_content_retained"] is False
assert manifest["token_ids_retained"] is False
assert manifest["result_transfer_authorized"] is True
assert manifest["transfer_method_selected"] is False
PY
