#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
SHARED_REPO_ROOT=${P6_3C_SHARED_REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
BASE_SERVER_TASK=${P6_3C_R3A_BASE_SERVER_TASK:-${SCRIPT_DIR}/run_deepseek_p6_3c_r2_server_task.sh}
test -f "${BASE_SERVER_TASK}"

export REPO_ROOT
export ENV_PREFIX=${P6_3C_ENV_PREFIX:-${SHARED_REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
export SOURCE_PAYLOAD=${P6_3C_SOURCE_PAYLOAD:-${SHARED_REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json}
unset BASE_PLUGIN_ROOT BASE_VLLM_ROOT
export P6_3C_TASK_ID=p6_3c_r3a_decode_resident_admission_cliff_2026_0803_run01
export P6_3C_REPORT_PREFIX=P6_3C_R3A
export P6_3C_EXPERIMENT_LABEL=P6_3C_R3A
export P6_3C_WORKLOAD_RELATIVE_PATH=benchmarks/deepseek_v4_flash/workloads/p6_3c_r3a_decode_resident_admission_cliff_matched_ab.yaml
export P6_3C_REQUEST_ID_PREFIX=p6_3c_r3a
export P6_3C_ATOMIC_PAIR_ADMISSION=0
export P6_3C_R3_REQUEST_MARKER=p6_3c_r3a_
export P6_3C_EXPECTED_MODEL_LIFECYCLES=6
export P6_3C_EXPECTED_ENGINE_REQUESTS=682
export P6_3C_EXPECTED_HTTP_REQUESTS=136
export OBSERVER=${SCRIPT_DIR}/p6_3c_r3_decode_resident_observer.py
export REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r3a_decode_resident.py
export MODE_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r3a_mode.sh
export P6_3C_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r3a_decode_resident.py
export P6_3C_EXPERIMENT=${SCRIPT_DIR}/run_deepseek_p6_3c_r3a_experiment.sh

exec bash "${BASE_SERVER_TASK}" "$@"
