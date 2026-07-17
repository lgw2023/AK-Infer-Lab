#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

RESULT_DIR=$1
REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
ENV_PREFIX=${ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
PYTHON_BIN=${PYTHON_BIN:-${ENV_PREFIX}/bin/python}
TASK_ID=p8_2_k0_deepseek_v4_flash_order_balanced_prefix_cache_baseline_2026_0717
SOURCE_PAYLOAD=${SOURCE_PAYLOAD:-${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json}
MODEL_NAME=${MODEL_NAME:-deepseek-v4-flash-w8a8-mtp}
MODE_RUNNER=${MODE_RUNNER:-${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k0_mode.sh}
REQUEST_RUNNER=${REQUEST_RUNNER:-${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k0_order_balanced_prefix_baseline.py}
BASE_VLLM_ROOT=${BASE_VLLM_ROOT:-/data/node0_disk1/vllm-0.22.1/vllm}
export BASE_VLLM_ROOT REQUEST_RUNNER

append_no_proxy() {
  local value=$1
  local host
  for host in 127.0.0.1 localhost; do
    case ",${value}," in
      *",${host},"*) ;;
      *) value=${value:+${value},}${host} ;;
    esac
  done
  printf '%s' "${value}"
}
export no_proxy="$(append_no_proxy "${no_proxy:-}")"
export NO_PROXY="$(append_no_proxy "${NO_PROXY:-}")"

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'lifecycle_01\tpair_01\tfirst\tprefix_cache_off\n'
  printf 'lifecycle_02\tpair_01\tsecond\tprefix_cache_on\n'
  printf 'lifecycle_03\tpair_02\tfirst\tprefix_cache_on\n'
  printf 'lifecycle_04\tpair_02\tsecond\tprefix_cache_off\n'
  printf 'lifecycle_count=4\n'
  printf 'request_count=20\n'
  printf 'measured_request_count=12\n'
  printf 'matched_measured_pair_count=6\n'
  printf 'base_vllm_root=%s\n' "${BASE_VLLM_ROOT}"
  printf 'prefix_cache_off_server_command_sha256=def3dd8bf71ee4cac1922b0d4fa14321e1df5369fd8a5997771d00f3be6418ea\n'
  printf 'prefix_cache_on_server_command_sha256=370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19\n'
}

if test "${P8_2_K0_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test ! -e "${RESULT_DIR}"
test -f "${SOURCE_PAYLOAD}"
test "$(stat -c '%s' "${SOURCE_PAYLOAD}")" = 19487
test "$(sha256sum "${SOURCE_PAYLOAD}" | awk '{print $1}')" = 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
test -f "${MODE_RUNNER}"
test -f "${REQUEST_RUNNER}"
test -d "${BASE_VLLM_ROOT}"

"${PYTHON_BIN}" "${REQUEST_RUNNER}" prepare \
  --source-payload "${SOURCE_PAYLOAD}" \
  --artifact-dir "${RESULT_DIR}" \
  --model-name "${MODEL_NAME}"

run_exit=0
while IFS=$'\t' read -r lifecycle_id pair_id pair_position mode; do
  lifecycle_dir=${RESULT_DIR}/lifecycles/${lifecycle_id}
  printf '%s\t%s\t%s\t%s\n' \
    "${lifecycle_id}" "${pair_id}" "${pair_position}" "${mode}" \
    >> "${RESULT_DIR}/executed_lifecycle_schedule.tsv"
  set +e
  bash "${MODE_RUNNER}" "${lifecycle_dir}" "${mode}"
  lifecycle_exit=$?
  set -e
  if test "${lifecycle_exit}" -ne 0; then
    run_exit=${lifecycle_exit}
    break
  fi
done <<'EOF'
lifecycle_01	pair_01	first	prefix_cache_off
lifecycle_02	pair_01	second	prefix_cache_on
lifecycle_03	pair_02	first	prefix_cache_on
lifecycle_04	pair_02	second	prefix_cache_off
EOF

set +e
"${PYTHON_BIN}" "${REQUEST_RUNNER}" finalize --artifact-dir "${RESULT_DIR}"
finalize_exit=$?
set -e
if test "${run_exit}" -ne 0; then
  exit "${run_exit}"
fi
exit "${finalize_exit}"
