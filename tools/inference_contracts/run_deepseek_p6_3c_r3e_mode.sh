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
BASE_MODE_RUNNER=${P6_3C_R3E_BASE_MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_mode.sh}
CONTROLLER=${P6_3C_R3E_CONTROLLER:-${SCRIPT_DIR}/p6_3c_r3d_persistent_scheduler.py}
SITECUSTOMIZE=${P6_3C_R3E_SITECUSTOMIZE:-${SCRIPT_DIR}/p6_3c_r3d_sitecustomize.py}

test "${TRACK}" = mechanism
test "${MODE}" = chunked_prefill_on
test -f "${BASE_MODE_RUNNER}"
test -f "${CONTROLLER}"
test -f "${SITECUSTOMIZE}"

case "${POLICY_ID}" in
  admission_on_t4096)
    PRESSURE_SCOPE=admission_only
    ACTIVE_CHUNK_TARGET=4096
    ;;
  persistent_on_t1024)
    PRESSURE_SCOPE=persistent_prefill
    ACTIVE_CHUNK_TARGET=1024
    ;;
  persistent_on_t128)
    PRESSURE_SCOPE=persistent_prefill
    ACTIVE_CHUNK_TARGET=128
    ;;
  *)
    echo "unsupported R3E policy: ${POLICY_ID}" >&2
    exit 64
    ;;
esac

case "${LIFECYCLE_ID}" in
  host_01|host_02|host_03)
    DIAGNOSTIC_MSPROF=0
    EVIDENCE_TRACK=host_timing
    ;;
  profile_01|profile_02)
    DIAGNOSTIC_MSPROF=1
    EVIDENCE_TRACK=diagnostic_msprof
    ;;
  *)
    echo "unsupported R3E lifecycle: ${LIFECYCLE_ID}" >&2
    exit 64
    ;;
esac

export P6_3C_EXPERIMENT_LABEL=P6_3C_R3E
export P6_3C_MAX_MODEL_LEN=12288
export P6_3C_MAX_NUM_BATCHED_TOKENS=12288
export P6_3C_MAX_NUM_SEQS=9
export P6_3C_SHARED_HYBRID_KV_REPAIR=1
export P6_3C_ACL_GRAPH_COMPAT=1
export RUNTIME_LOADER=${RUNTIME_LOADER:-${SCRIPT_DIR}/p6_3c_r3d_hybrid_kv_runtime_patch.py}
export P6_3C_ATOMIC_PAIR_ADMISSION=0
export P6_3C_R3_REQUEST_MARKER=p6_3c_r3e_
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
export P6_3C_DIAGNOSTIC_MSPROF=${DIAGNOSTIC_MSPROF}
export P6_3C_MSPROF_STORAGE_LIMIT=4096
if test "${DIAGNOSTIC_MSPROF}" = 1; then
  export P6_3C_MSPROF_OUTPUT_ROOT="${ARTIFACT_DIR}/lifecycles/${LIFECYCLE_ID}/runtime/msprof"
else
  unset P6_3C_MSPROF_OUTPUT_ROOT
fi

if test "${P6_3C_R3E_MODE_AUDIT_ONLY:-0}" = 1; then
  printf 'lifecycle_id=%s\n' "${LIFECYCLE_ID}"
  printf 'track=%s\n' "${TRACK}"
  printf 'mode=%s\n' "${MODE}"
  printf 'policy_id=%s\n' "${POLICY_ID}"
  printf 'pressure_scope=%s\n' "${PRESSURE_SCOPE}"
  printf 'active_chunk_target_tokens=%s\n' "${ACTIVE_CHUNK_TARGET}"
  printf 'evidence_track=%s\n' "${EVIDENCE_TRACK}"
  printf 'diagnostic_msprof=%s\n' "${DIAGNOSTIC_MSPROF}"
  printf 'max_model_len=12288\n'
  printf 'max_num_batched_tokens=12288\n'
  printf 'max_num_seqs=9\n'
  exit 0
fi

bash "${BASE_MODE_RUNNER}" \
  "${ARTIFACT_DIR}" "${LIFECYCLE_ID}" "${TRACK}" "${MODE}"

if test "${DIAGNOSTIC_MSPROF}" = 1; then
  test -d "${P6_3C_MSPROF_OUTPUT_ROOT}"
  find "${P6_3C_MSPROF_OUTPUT_ROOT}" -type f -print \
    > "${ARTIFACT_DIR}/lifecycles/${LIFECYCLE_ID}/runtime/msprof_output_files.txt"
  test -s "${ARTIFACT_DIR}/lifecycles/${LIFECYCLE_ID}/runtime/msprof_output_files.txt"
fi
