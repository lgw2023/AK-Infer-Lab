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
TASK_ID=p8_2_k1a_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0717
SOURCE_PAYLOAD=${SOURCE_PAYLOAD:-${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json}
MODEL_NAME=${MODEL_NAME:-deepseek-v4-flash-w8a8-mtp}
MODE_RUNNER=${MODE_RUNNER:-${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh}
REQUEST_RUNNER=${REQUEST_RUNNER:-${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py}
export REQUEST_RUNNER

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
  printf 'execution_mode=authorized_simple_cpu_offload_single_lifecycle_six_request_mechanism\n'
  printf 'lifecycle_count=1\n'
  printf 'request_count=6\n'
  printf 'request_order=warmup,prime,pressure,restore_follower,repeat_follower,isolated_control\n'
  printf 'server_command_sha256=d4222bef3a1c39dd38297b0523b9df54e3f3cef3ff67e4b970e6fce3f95708a5\n'
  printf 'npu_execution_authorized=true\n'
  printf 'next_task_authorized=false\n'
}

if test "${P8_2_K1A_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test ! -e "${RESULT_DIR}"
test -f "${SOURCE_PAYLOAD}"
test "$(stat -c '%s' "${SOURCE_PAYLOAD}")" = 19487
test "$(sha256sum "${SOURCE_PAYLOAD}" | awk '{print $1}')" = 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
test -f "${MODE_RUNNER}"
test -f "${REQUEST_RUNNER}"

"${PYTHON_BIN}" "${REQUEST_RUNNER}" prepare \
  --source-payload "${SOURCE_PAYLOAD}" \
  --artifact-dir "${RESULT_DIR}" \
  --model-name "${MODEL_NAME}"

set +e
bash "${MODE_RUNNER}" "${RESULT_DIR}"
mode_exit=$?
"${PYTHON_BIN}" "${REQUEST_RUNNER}" finalize --artifact-dir "${RESULT_DIR}"
finalize_exit=$?
set -e
printf '%s\n' "${mode_exit}" > "${RESULT_DIR}/mode_exit_code.txt"
printf '%s\n' "${finalize_exit}" > "${RESULT_DIR}/finalize_exit_code.txt"
if test "${mode_exit}" -ne 0; then
  exit "${mode_exit}"
fi
exit "${finalize_exit}"
