#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 5; then
  echo "usage: $0 ARTIFACT_DIR LIFECYCLE_ID TRACK MODE POLICY_ID" >&2
  exit 64
fi

ARTIFACT_DIR=$1
LIFECYCLE_ID=$2
TRACK=$3
MODE=$4
POLICY_ID=$5
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BASE_MODE_RUNNER=${P6_3C_R3E_F1_BASE_MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_mode.sh}
CONTROLLER=${P6_3C_R3E_F1_CONTROLLER:-${SCRIPT_DIR}/p6_3c_r3d_persistent_scheduler.py}
SITECUSTOMIZE=${P6_3C_R3E_F1_SITECUSTOMIZE:-${SCRIPT_DIR}/p6_3c_r3d_sitecustomize.py}

test "${TRACK}" = mechanism
test "${MODE}" = chunked_prefill_on
test -f "${BASE_MODE_RUNNER}"
test -f "${CONTROLLER}"
test -f "${SITECUSTOMIZE}"

case "${LIFECYCLE_ID}:${POLICY_ID}" in
  profile_f1_01:admission_on_t4096)
    PRESSURE_SCOPE=admission_only
    ACTIVE_CHUNK_TARGET=4096
    ;;
  profile_f1_02:persistent_on_t128)
    PRESSURE_SCOPE=persistent_prefill
    ACTIVE_CHUNK_TARGET=128
    ;;
  *)
    echo "unsupported R3E-F1 lifecycle/policy: ${LIFECYCLE_ID}/${POLICY_ID}" >&2
    exit 64
    ;;
esac

export P6_3C_EXPERIMENT_LABEL=P6_3C_R3E_F1
export P6_3C_MAX_MODEL_LEN=12288
export P6_3C_MAX_NUM_BATCHED_TOKENS=12288
export P6_3C_MAX_NUM_SEQS=9
export P6_3C_SHARED_HYBRID_KV_REPAIR=1
export P6_3C_ACL_GRAPH_COMPAT=1
export RUNTIME_LOADER=${RUNTIME_LOADER:-${SCRIPT_DIR}/p6_3c_r3d_hybrid_kv_runtime_patch.py}
export P6_3C_ATOMIC_PAIR_ADMISSION=0
export P6_3C_R3_REQUEST_MARKER=p6_3c_r3e_f1_
export P6_3C_R3D_POLICY_ID=${POLICY_ID}
export P6_3C_R3D_POLICY_TYPE=adaptive_on
export P6_3C_R3D_PRESSURE_SCOPE=${PRESSURE_SCOPE}
export P6_3C_R3D_ACTIVE_CHUNK_TOKENS=${ACTIVE_CHUNK_TARGET}
export P6_3C_R3D_DECODE_QUANTUM_TOKENS=2
export P6_3C_R3C_ADAPTIVE_CONTROLLER=${CONTROLLER}
export P6_3C_R3C_ADAPTIVE_SITECUSTOMIZE=${SITECUSTOMIZE}
export P6_3C_ADAPTIVE_CONTROLLER_OVERLAY_MODULE=p6_3c_r3d_persistent_scheduler
export P6_3C_R3C_ACTIVE_CHUNK_TOKENS=${ACTIVE_CHUNK_TARGET}
export P6_3C_R3C_DECODE_QUANTUM_TOKENS=2
export P6_3C_R3C_ADAPTIVE_POLICY_ID=${POLICY_ID}

# F1 profiles only the measured staged-arrival trial. The server starts
# normally, completes its warmup, then the request driver calls vLLM's
# /start_profile and /stop_profile endpoints around the measured trial.
export P6_3C_DIAGNOSTIC_MSPROF=0
export P6_3C_TORCH_PROFILE_API=1
export P6_3C_PROFILE_API_ENABLED=1
export P6_3C_TORCH_PROFILER_DIR="${ARTIFACT_DIR}/lifecycles/${LIFECYCLE_ID}/runtime/torch_profiler"

if test "${P6_3C_R3E_F1_MODE_AUDIT_ONLY:-0}" = 1; then
  printf 'lifecycle_id=%s\n' "${LIFECYCLE_ID}"
  printf 'track=%s\n' "${TRACK}"
  printf 'mode=%s\n' "${MODE}"
  printf 'policy_id=%s\n' "${POLICY_ID}"
  printf 'pressure_scope=%s\n' "${PRESSURE_SCOPE}"
  printf 'active_chunk_target_tokens=%s\n' "${ACTIVE_CHUNK_TARGET}"
  printf 'profiler_backend=vllm_torch_profile_api\n'
  printf 'profile_window=after_warmup_to_measured_trial_completion\n'
  printf 'model_loading_profiled=false\n'
  printf 'max_model_len=12288\n'
  printf 'max_num_batched_tokens=12288\n'
  printf 'max_num_seqs=9\n'
  exit 0
fi

bash "${BASE_MODE_RUNNER}" \
  "${ARTIFACT_DIR}" "${LIFECYCLE_ID}" "${TRACK}" "${MODE}"

test -d "${P6_3C_TORCH_PROFILER_DIR}"
find "${P6_3C_TORCH_PROFILER_DIR}" -type f -print \
  > "${ARTIFACT_DIR}/lifecycles/${LIFECYCLE_ID}/runtime/torch_profiler_output_files.txt"
test -s "${ARTIFACT_DIR}/lifecycles/${LIFECYCLE_ID}/runtime/torch_profiler_output_files.txt"
