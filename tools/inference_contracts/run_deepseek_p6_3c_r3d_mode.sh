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
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
BASE_MODE_RUNNER=${P6_3C_R3D_BASE_MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_mode.sh}
CONTROLLER=${P6_3C_R3D_CONTROLLER:-${SCRIPT_DIR}/p6_3c_r3d_persistent_scheduler.py}
SITECUSTOMIZE=${P6_3C_R3D_SITECUSTOMIZE:-${SCRIPT_DIR}/p6_3c_r3d_sitecustomize.py}

test -f "${BASE_MODE_RUNNER}"
test -f "${CONTROLLER}"
test -f "${SITECUSTOMIZE}"

case "${POLICY_ID}" in
  off_b12288)
    test "${MODE}" = chunked_prefill_off
    POLICY_TYPE=static_off
    PRESSURE_SCOPE=none
    ACTIVE_CHUNK_TARGET=none
    ;;
  admission_on_t4096)
    test "${MODE}" = chunked_prefill_on
    POLICY_TYPE=adaptive_on
    PRESSURE_SCOPE=admission_only
    ACTIVE_CHUNK_TARGET=4096
    ;;
  persistent_on_t128|persistent_on_t256|persistent_on_t512|persistent_on_t1024)
    test "${MODE}" = chunked_prefill_on
    POLICY_TYPE=adaptive_on
    PRESSURE_SCOPE=persistent_prefill
    ACTIVE_CHUNK_TARGET=${POLICY_ID##*t}
    ;;
  *)
    echo "unsupported R3D policy: ${POLICY_ID}" >&2
    exit 64
    ;;
esac

export P6_3C_EXPERIMENT_LABEL=P6_3C_R3D
export P6_3C_MAX_MODEL_LEN=12288
export P6_3C_MAX_NUM_BATCHED_TOKENS=12288
export P6_3C_MAX_NUM_SEQS=9
export P6_3C_SHARED_HYBRID_KV_REPAIR=1
export P6_3C_ACL_GRAPH_COMPAT=1
export RUNTIME_LOADER=${RUNTIME_LOADER:-${SCRIPT_DIR}/p6_3c_r3d_hybrid_kv_runtime_patch.py}
export P6_3C_ATOMIC_PAIR_ADMISSION=0
export P6_3C_R3_REQUEST_MARKER=p6_3c_r3d_
export P6_3C_R3D_POLICY_ID=${POLICY_ID}
export P6_3C_R3D_POLICY_TYPE=${POLICY_TYPE}
export P6_3C_R3D_PRESSURE_SCOPE=${PRESSURE_SCOPE}
export P6_3C_R3D_ACTIVE_CHUNK_TOKENS=$([ "${ACTIVE_CHUNK_TARGET}" = none ] && printf 512 || printf '%s' "${ACTIVE_CHUNK_TARGET}")
export P6_3C_R3D_DECODE_QUANTUM_TOKENS=2

# The audited base lifecycle runner retains historical R3C environment names.
# Point those compatibility hooks at the new R3D module without renaming the
# published source inside the overlay.
export P6_3C_R3C_ADAPTIVE_CONTROLLER=${CONTROLLER}
export P6_3C_R3C_ADAPTIVE_SITECUSTOMIZE=${SITECUSTOMIZE}
export P6_3C_ADAPTIVE_CONTROLLER_OVERLAY_MODULE=p6_3c_r3d_persistent_scheduler
export P6_3C_R3C_ACTIVE_CHUNK_TOKENS=${P6_3C_R3D_ACTIVE_CHUNK_TOKENS}
export P6_3C_R3C_DECODE_QUANTUM_TOKENS=2

if test "${POLICY_TYPE}" = adaptive_on; then
  export P6_3C_R3C_ADAPTIVE_POLICY_ID=${POLICY_ID}
else
  unset P6_3C_R3C_ADAPTIVE_POLICY_ID
  export P6_3C_R3C_ADAPTIVE_CONTROLLER=
  export P6_3C_R3C_ADAPTIVE_SITECUSTOMIZE=
fi

if test "${P6_3C_R3D_MODE_AUDIT_ONLY:-0}" = 1; then
  printf 'lifecycle_id=%s\n' "${LIFECYCLE_ID}"
  printf 'track=%s\n' "${TRACK}"
  printf 'mode=%s\n' "${MODE}"
  printf 'policy_id=%s\n' "${POLICY_ID}"
  printf 'policy_type=%s\n' "${POLICY_TYPE}"
  printf 'max_model_len=12288\n'
  printf 'max_num_batched_tokens=12288\n'
  printf 'max_num_seqs=9\n'
  printf 'acl_graph_compat=1\n'
  printf 'pressure_scope=%s\n' "${PRESSURE_SCOPE}"
  printf 'active_chunk_target_tokens=%s\n' "${ACTIVE_CHUNK_TARGET}"
  printf 'adaptive_controller_enabled=%s\n' \
    "$([ "${POLICY_TYPE}" = adaptive_on ] && printf true || printf false)"
  exit 0
fi

exec bash "${BASE_MODE_RUNNER}" \
  "${ARTIFACT_DIR}" "${LIFECYCLE_ID}" "${TRACK}" "${MODE}"
