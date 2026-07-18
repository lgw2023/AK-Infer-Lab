#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export P8_2_K1A_TASK_ID=p8_2_k1a_r3_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0718
export P8_2_K1A_EXECUTION_MODE=authorized_accepted_capacity_single_lifecycle_six_request_mechanism
export P8_2_K1A_CPU_BYTES_TO_USE=3444834304
export P8_2_K1A_CPU_BYTES_TO_USE_PER_RANK=430604288
export P8_2_K1A_HOST_MEM_AVAILABLE_MIN=412316860416
export P8_2_K1A_EXPECTED_COMMAND_SHA256=418d2796ec2dd15ab7504c264a6635a50d064cb7b6425f809cbfba550d2f5bb0
export P8_2_K1A_REPO_FILE_LIST=benchmarks/deepseek_v4_flash/p8_2_k1a_simple_cpu_offload_feasibility_audit.yaml:benchmarks/deepseek_v4_flash/p8_2_k1a_r3_formal_lifecycle_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r3_simple_cpu_offload_store_restore.yaml:tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh:tools/inference_contracts/run_deepseek_p8_2_k1a_r3_simple_cpu_offload.sh:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r3_simple_cpu_offload_store_restore
export P8_2_K1A_NO_SUCCESS_GRADE=red_p8_2_k1a_r3_no_success
export P8_2_K1A_PARTIAL_GRADE=yellow_p8_2_k1a_r3_partial
export P8_2_K1A_STORE_ONLY_GRADE=yellow_p8_2_k1a_r3_store_only_no_restore
export P8_2_K1A_EVIDENCE_INCOMPLETE_GRADE=red_p8_2_k1a_r3_transfer_evidence_incomplete

if test "${P8_2_K1A_MODE_AUDIT_ONLY:-0}" = 1; then
  exec bash "${SCRIPT_DIR}/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh" "$1"
fi
exec bash "${SCRIPT_DIR}/run_deepseek_p8_2_k1a_simple_cpu_offload.sh" "$1"
