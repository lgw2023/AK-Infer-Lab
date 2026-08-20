#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
SHARED_REPO_ROOT=${P6_3C_SHARED_REPO_ROOT:-${REPO_ROOT}}
BASE_SERVER_TASK=${P6_3C_R3E_F2_BASE_SERVER_TASK:-${SCRIPT_DIR}/run_deepseek_p6_3c_r2_server_task.sh}
LAYOUT_RESOLVER=${P6_3C_LAYOUT_RESOLVER:-${SCRIPT_DIR}/resolve_p6_3c_runtime_layout.py}
S0_SMOKE=${P6_3C_R3E_F2_S0_SMOKE:-${SCRIPT_DIR}/smoke_p6_3c_r3e_f2_dependency_marker.py}
TASK_ID=p6_3c_r3e_f2_request_scoped_dependency_marker_canary_2026_0820

test -f "${BASE_SERVER_TASK}"
test -f "${LAYOUT_RESOLVER}"
test -f "${S0_SMOKE}"

export REPO_ROOT
export ENV_PREFIX=${P6_3C_ENV_PREFIX:-${SHARED_REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
export SOURCE_PAYLOAD=${P6_3C_SOURCE_PAYLOAD:-${SHARED_REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json}
unset BASE_PLUGIN_ROOT BASE_VLLM_ROOT

export P6_3C_TASK_ID=${TASK_ID}
export P6_3C_REPORT_PREFIX=P6_3C_R3E_F2
export P6_3C_EXPERIMENT_LABEL=P6_3C_R3E_F2
export P6_3C_WORKLOAD_RELATIVE_PATH=benchmarks/deepseek_v4_flash/workloads/p6_3c_r3e_f2_request_scoped_dependency_marker_canary.yaml
export P6_3C_REQUEST_ID_PREFIX=p6_3c_r3e_f2
export P6_3C_ATOMIC_PAIR_ADMISSION=0
export P6_3C_R3_REQUEST_MARKER=p6_3c_r3e_f2_
export P6_3C_SHARED_HYBRID_KV_REPAIR=1
export P6_3C_ACL_GRAPH_COMPAT=1
export RUNTIME_LOADER=${SCRIPT_DIR}/p6_3c_r3d_hybrid_kv_runtime_patch.py
export P6_3C_EXPECTED_MODEL_LIFECYCLES=3
export P6_3C_EXPECTED_ENGINE_REQUESTS=30
export P6_3C_EXPECTED_HTTP_REQUESTS=9
export P6_3C_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r3e_f2_dependency_marker_canary.py
export P6_3C_EXPERIMENT=${SCRIPT_DIR}/run_deepseek_p6_3c_r3e_f2_experiment.sh
export REQUEST_RUNNER=${P6_3C_RUNNER}
export MODE_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r3e_f2_mode.sh
export OBSERVER=${SCRIPT_DIR}/p6_3c_r3e_f2_dependency_marker.py
export OBSERVER_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch
export P6_3C_R3E_F2_CONTROLLER=${SCRIPT_DIR}/p6_3c_r3d_persistent_scheduler.py
export P6_3C_R3E_F2_SITECUSTOMIZE=${SCRIPT_DIR}/p6_3c_r3d_sitecustomize.py

if test "${P6_3C_SERVER_TASK_AUDIT_ONLY:-${P6_3C_R1_SERVER_TASK_AUDIT_ONLY:-0}}" = 1; then
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'S0_npu_used=false\n'
  printf 'S0_keep_alive_action=left_running\n'
  printf 'S1_S2_npu_card_ids=0,1,2,3,4,5,6,7\n'
  printf 'conditional_model_lifecycles=1_if_S1_negative_or_3_if_S1_positive\n'
  printf 'result_transfer_authorized=true\n'
  P6_3C_AUDIT_ONLY=1 bash "${P6_3C_EXPERIMENT}" "/audit/${TASK_ID}"
  exit 0
fi

test -x "${ENV_PREFIX}/bin/python"
preflight_root=$(mktemp -d /tmp/p6_3c_r3e_f2_s0.XXXXXX)
cleanup_preflight() {
  case "${preflight_root}" in
    /tmp/p6_3c_r3e_f2_s0.*) rm -rf -- "${preflight_root}" ;;
    *) echo "refusing to remove unexpected S0 path: ${preflight_root}" >&2 ;;
  esac
}
trap cleanup_preflight EXIT

layout_json=${preflight_root}/runtime_layout.json
layout_shell=${preflight_root}/runtime_layout.env
"${ENV_PREFIX}/bin/python" "${LAYOUT_RESOLVER}" \
  --expected-env-prefix "${ENV_PREFIX}" \
  --output "${layout_json}" \
  --shell-output "${layout_shell}"
# shellcheck disable=SC1090
. "${layout_shell}"

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u

s0_evidence=${preflight_root}/s0_source_import_smoke.json
PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}" \
PYTHONNOUSERSITE=1 \
P6_3C_R3E_F2_ENABLED=1 \
  "${PYTHON_BIN}" "${S0_SMOKE}" --output "${s0_evidence}"
test -s "${s0_evidence}"
export P6_3C_R3E_F2_S0_EVIDENCE=${s0_evidence}

bash "${BASE_SERVER_TASK}" "$@"
