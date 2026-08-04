#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 5; then
  echo "usage: $0 ARTIFACT_DIR LIFECYCLE_ID TRACK MODE MAX_NUM_BATCHED_TOKENS" >&2
  exit 64
fi

ARTIFACT_DIR=$1
LIFECYCLE_ID=$2
TRACK=$3
MODE=$4
MAX_NUM_BATCHED_TOKENS=$5
case "${MODE}:${MAX_NUM_BATCHED_TOKENS}" in
  chunked_prefill_off:12288|\
  chunked_prefill_on:2048|chunked_prefill_on:4096|\
  chunked_prefill_on:6144|chunked_prefill_on:8192|\
  chunked_prefill_on:12288) ;;
  *)
    echo "unsupported R3B mode/budget: ${MODE}/${MAX_NUM_BATCHED_TOKENS}" >&2
    exit 64
    ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BASE_MODE_RUNNER=${P6_3C_R3B_BASE_MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_mode.sh}
test -f "${BASE_MODE_RUNNER}"

export P6_3C_EXPERIMENT_LABEL=P6_3C_R3B
export P6_3C_MAX_MODEL_LEN=12288
export P6_3C_MAX_NUM_BATCHED_TOKENS=${MAX_NUM_BATCHED_TOKENS}
export P6_3C_MAX_NUM_SEQS=9
export P6_3C_SHARED_HYBRID_KV_REPAIR=1
export P6_3C_ATOMIC_PAIR_ADMISSION=0
export P6_3C_R3_REQUEST_MARKER=p6_3c_r3b_
export OBSERVER=${SCRIPT_DIR}/p6_3c_r3_decode_resident_observer.py
export REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r3b_chunk_budget.py

exec bash "${BASE_MODE_RUNNER}" \
  "${ARTIFACT_DIR}" "${LIFECYCLE_ID}" "${TRACK}" "${MODE}"
