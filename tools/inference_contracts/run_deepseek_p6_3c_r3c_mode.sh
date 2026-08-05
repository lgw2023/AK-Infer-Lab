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
BASE_MODE_RUNNER=${P6_3C_R3C_BASE_MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_mode.sh}
CONTROLLER=${P6_3C_R3C_CONTROLLER:-${SCRIPT_DIR}/p6_3c_r3c_adaptive_scheduler.py}
SITECUSTOMIZE=${P6_3C_R3C_SITECUSTOMIZE:-${SCRIPT_DIR}/p6_3c_r3c_sitecustomize.py}

test -f "${BASE_MODE_RUNNER}"
test -f "${REPO_ROOT}/tools/inference_contracts/p6_3c_r3c_adaptive_scheduler.py"
test -f "${REPO_ROOT}/tools/inference_contracts/p6_3c_r3c_sitecustomize.py"

case "${POLICY_ID}" in
  off_b12288)
    test "${MODE}" = chunked_prefill_off
    MAX_NUM_BATCHED_TOKENS=12288
    POLICY_TYPE=static_off
    unset ACTIVE_CHUNK_TARGET
    ;;
  static_on_b8192)
    test "${MODE}" = chunked_prefill_on
    MAX_NUM_BATCHED_TOKENS=8192
    POLICY_TYPE=static_on
    unset ACTIVE_CHUNK_TARGET
    ;;
  adaptive_on_t2048)
    test "${MODE}" = chunked_prefill_on
    MAX_NUM_BATCHED_TOKENS=12288
    POLICY_TYPE=adaptive_on
    ACTIVE_CHUNK_TARGET=2048
    ;;
  adaptive_on_t4096)
    test "${MODE}" = chunked_prefill_on
    MAX_NUM_BATCHED_TOKENS=12288
    POLICY_TYPE=adaptive_on
    ACTIVE_CHUNK_TARGET=4096
    ;;
  adaptive_on_t8192)
    test "${MODE}" = chunked_prefill_on
    MAX_NUM_BATCHED_TOKENS=12288
    POLICY_TYPE=adaptive_on
    ACTIVE_CHUNK_TARGET=8192
    ;;
  *)
    echo "unsupported R3C policy: ${POLICY_ID}" >&2
    exit 64
    ;;
esac

export P6_3C_EXPERIMENT_LABEL=P6_3C_R3C
export P6_3C_MAX_MODEL_LEN=12288
export P6_3C_MAX_NUM_BATCHED_TOKENS=${MAX_NUM_BATCHED_TOKENS}
export P6_3C_MAX_NUM_SEQS=9
export P6_3C_SHARED_HYBRID_KV_REPAIR=1
export P6_3C_ATOMIC_PAIR_ADMISSION=0
export P6_3C_R3_REQUEST_MARKER=p6_3c_r3c_
export P6_3C_R3C_POLICY_ID=${POLICY_ID}
export P6_3C_R3C_POLICY_TYPE=${POLICY_TYPE}
export P6_3C_R3C_ADAPTIVE_CONTROLLER=${CONTROLLER}
export P6_3C_R3C_ADAPTIVE_SITECUSTOMIZE=${SITECUSTOMIZE}
export P6_3C_R3C_ACTIVE_CHUNK_TOKENS=${ACTIVE_CHUNK_TARGET:-4096}
export P6_3C_R3C_DECODE_QUANTUM_TOKENS=2

if test "${POLICY_TYPE}" = adaptive_on; then
  export P6_3C_R3C_ADAPTIVE_POLICY_ID=${POLICY_ID}
else
  unset P6_3C_R3C_ADAPTIVE_POLICY_ID
  # Passing an empty controller path keeps the static policies free of the
  # bootstrap hook while reusing the same base mode lifecycle implementation.
  export P6_3C_R3C_ADAPTIVE_CONTROLLER=
  export P6_3C_R3C_ADAPTIVE_SITECUSTOMIZE=
fi

if test "${P6_3C_R3C_MODE_AUDIT_ONLY:-0}" = 1; then
  printf 'lifecycle_id=%s\n' "${LIFECYCLE_ID}"
  printf 'track=%s\n' "${TRACK}"
  printf 'mode=%s\n' "${MODE}"
  printf 'policy_id=%s\n' "${POLICY_ID}"
  printf 'policy_type=%s\n' "${POLICY_TYPE}"
  printf 'max_model_len=12288\n'
  printf 'max_num_batched_tokens=%s\n' "${MAX_NUM_BATCHED_TOKENS}"
  printf 'max_num_seqs=9\n'
  printf 'adaptive_controller_enabled=%s\n' \
    "$([ "${POLICY_TYPE}" = adaptive_on ] && printf true || printf false)"
  printf 'active_chunk_target_tokens=%s\n' "${ACTIVE_CHUNK_TARGET:-none}"
  exit 0
fi

exec bash "${BASE_MODE_RUNNER}" \
  "${ARTIFACT_DIR}" "${LIFECYCLE_ID}" "${TRACK}" "${MODE}"
