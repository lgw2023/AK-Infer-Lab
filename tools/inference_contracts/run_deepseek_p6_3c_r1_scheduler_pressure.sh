#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

RESULT_DIR=$1
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
ENV_PREFIX=${ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
PYTHON_BIN=${PYTHON_BIN:-${ENV_PREFIX}/bin/python}
SOURCE_PAYLOAD=${SOURCE_PAYLOAD:-${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json}
MODEL_NAME=${MODEL_NAME:-deepseek-v4-flash-w8a8-mtp}
REQUEST_RUNNER=${REQUEST_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_scheduler_pressure.py}
MODE_RUNNER=${MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_mode.sh}

audit_contract() {
  printf 'task_id=p6_3c_r1_chunked_prefill_scheduler_pressure_2026_0728_run01\n'
  printf 'model_lifecycle_count_exact=6\n'
  printf 'engine_request_count_exact=90\n'
  printf 'batched_http_call_count_exact=48\n'
  printf 'request_retry_count_exact=0\n'
  printf 'mechanism_observer=read_only\n'
  printf 'performance_observer=disabled\n'
  printf 'profiler=disabled_all_tracks\n'
  printf 'performance_order=chunked_prefill_off,chunked_prefill_on,chunked_prefill_on,chunked_prefill_off\n'
  while IFS=$'\t' read -r track lifecycle_id pair_id pair_position mode; do
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "${track}" "${lifecycle_id}" "${pair_id}" "${pair_position}" "${mode}"
    P6_3C_R1_MODE_AUDIT_ONLY=1 \
      bash "${MODE_RUNNER}" \
      /audit/p6_3c_r1 "${lifecycle_id}" "${track}" "${mode}"
  done <<'EOF'
mechanism	mechanism_01	mechanism_pair	first	chunked_prefill_off
mechanism	mechanism_02	mechanism_pair	second	chunked_prefill_on
performance	performance_01	pair_01	first	chunked_prefill_off
performance	performance_02	pair_01	second	chunked_prefill_on
performance	performance_03	pair_02	first	chunked_prefill_on
performance	performance_04	pair_02	second	chunked_prefill_off
EOF
}

if test "${P6_3C_R1_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test ! -e "${RESULT_DIR}"
test -x "${PYTHON_BIN}"
test -f "${SOURCE_PAYLOAD}"
test "$(stat -c '%s' "${SOURCE_PAYLOAD}")" = 19487
test "$(sha256sum "${SOURCE_PAYLOAD}" | awk '{print $1}')" = \
  48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
test -f "${REQUEST_RUNNER}"
test -f "${MODE_RUNNER}"

"${PYTHON_BIN}" "${REQUEST_RUNNER}" prepare \
  --source-payload "${SOURCE_PAYLOAD}" \
  --artifact-dir "${RESULT_DIR}" \
  --model-name "${MODEL_NAME}"

printf 'track\tlifecycle_id\tpair_id\tpair_position\tmode\n' \
  > "${RESULT_DIR}/executed_lifecycle_schedule.tsv"
run_exit=0
while IFS=$'\t' read -r track lifecycle_id pair_id pair_position mode; do
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "${track}" "${lifecycle_id}" "${pair_id}" "${pair_position}" "${mode}" \
    >> "${RESULT_DIR}/executed_lifecycle_schedule.tsv"
  set +e
  bash "${MODE_RUNNER}" \
    "${RESULT_DIR}" "${lifecycle_id}" "${track}" "${mode}"
  lifecycle_exit=$?
  set -e
  if test "${lifecycle_exit}" -ne 0; then
    run_exit=${lifecycle_exit}
    break
  fi
done <<'EOF'
mechanism	mechanism_01	mechanism_pair	first	chunked_prefill_off
mechanism	mechanism_02	mechanism_pair	second	chunked_prefill_on
performance	performance_01	pair_01	first	chunked_prefill_off
performance	performance_02	pair_01	second	chunked_prefill_on
performance	performance_03	pair_02	first	chunked_prefill_on
performance	performance_04	pair_02	second	chunked_prefill_off
EOF

exit "${run_exit}"
