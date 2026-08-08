#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
SHARED_REPO_ROOT=${P6_3C_SHARED_REPO_ROOT:-${REPO_ROOT}}
BASE_SERVER_TASK=${P6_3C_R3E_F1_BASE_SERVER_TASK:-${SCRIPT_DIR}/run_deepseek_p6_3c_r2_server_task.sh}
test -f "${BASE_SERVER_TASK}"

export REPO_ROOT
export ENV_PREFIX=${P6_3C_ENV_PREFIX:-${SHARED_REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
export SOURCE_PAYLOAD=${P6_3C_SOURCE_PAYLOAD:-${SHARED_REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json}
unset BASE_PLUGIN_ROOT BASE_VLLM_ROOT

export P6_3C_TASK_ID=p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01
export P6_3C_REPORT_PREFIX=P6_3C_R3E_F1
export P6_3C_EXPERIMENT_LABEL=P6_3C_R3E_F1
export P6_3C_WORKLOAD_RELATIVE_PATH=benchmarks/deepseek_v4_flash/workloads/p6_3c_r3e_f1_request_scoped_profile_completion.yaml
export P6_3C_REQUEST_ID_PREFIX=p6_3c_r3e_f1
export P6_3C_ATOMIC_PAIR_ADMISSION=0
export P6_3C_R3_REQUEST_MARKER=p6_3c_r3e_f1_
export P6_3C_SHARED_HYBRID_KV_REPAIR=1
export P6_3C_ACL_GRAPH_COMPAT=1
export RUNTIME_LOADER=${SCRIPT_DIR}/p6_3c_r3d_hybrid_kv_runtime_patch.py
export P6_3C_EXPECTED_MODEL_LIFECYCLES=2
export P6_3C_EXPECTED_ENGINE_REQUESTS=20
export P6_3C_EXPECTED_HTTP_REQUESTS=6
export P6_3C_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r3e_f1_profile_completion.py
export P6_3C_EXPERIMENT=${SCRIPT_DIR}/run_deepseek_p6_3c_r3e_f1_experiment.sh
export P6_3C_R3E_F1_CONTROLLER=${SCRIPT_DIR}/p6_3c_r3d_persistent_scheduler.py
export P6_3C_R3E_F1_SITECUSTOMIZE=${SCRIPT_DIR}/p6_3c_r3d_sitecustomize.py
export P6_3C_R3E_SOURCE_RESULT=${P6_3C_R3E_SOURCE_RESULT:-/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_2026_0808_attempt_03/p6_3c_r3e_mixed_step_latency_floor_attribution_2026_0808_run01}
export REQUEST_RUNNER=${P6_3C_RUNNER}
export MODE_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r3e_f1_mode.sh
export OBSERVER=${SCRIPT_DIR}/p6_3c_r3_decode_resident_observer.py
export OBSERVER_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch

if test "${P6_3C_SERVER_TASK_AUDIT_ONLY:-${P6_3C_R1_SERVER_TASK_AUDIT_ONLY:-0}}" != 1; then
  if pgrep -af '[v]llm.*serve' >/dev/null; then
    echo "another vLLM serving process is active; R3E-F1 will not stop cards or compete for NPU memory" >&2
    pgrep -af '[v]llm.*serve' >&2 || true
    exit 2
  fi
  test -x "${ENV_PREFIX}/bin/python"
  "${ENV_PREFIX}/bin/python" "${P6_3C_RUNNER}" validate-source \
    --source-r3e-result "${P6_3C_R3E_SOURCE_RESULT}"
fi

exec bash "${BASE_SERVER_TASK}" "$@"
