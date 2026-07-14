#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 2; then
  echo "usage: $0 RESULT_DIR CELL_ID" >&2
  exit 64
fi

RESULT_DIR=$1
CELL_ID=$2
REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
ENV_PREFIX=${ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
PYTHON_BIN=${PYTHON_BIN:-${ENV_PREFIX}/bin/python}
VLLM_BIN=${VLLM_BIN:-${ENV_PREFIX}/bin/vllm}
BASE_PLUGIN_ROOT=${BASE_PLUGIN_ROOT:-${ENV_PREFIX}/lib/python3.11/site-packages/vllm_ascend}
BASE_PROPOSER=${BASE_PROPOSER:-${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py}
MODEL_PATH=${MODEL_PATH:-/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp}
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-deepseek-v4-flash-w8a8-mtp}
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-7000}
RUNNER_PATH=${RUNNER_PATH:-${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_2_profiled_evidence.py}
PATCH_PATH=${PATCH_PATH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch}
CELL_DIR=${RESULT_DIR}/source/${CELL_ID}
RUNTIME_DIR=${CELL_DIR}/runtime
OVERLAY_ROOT=${RUNTIME_DIR}/overlay_root
server_pid=

mkdir -p "${RUNTIME_DIR}" "${CELL_DIR}/raw_metrics" "${CELL_DIR}/raw_memory"

cleanup_cell() {
  local cleanup=clean
  if test -n "${server_pid}" && kill -0 "${server_pid}" 2>/dev/null; then
    kill -TERM -- "-${server_pid}" 2>/dev/null || true
    for _ in $(seq 1 60); do
      kill -0 "${server_pid}" 2>/dev/null || break
      sleep 2
    done
    if kill -0 "${server_pid}" 2>/dev/null; then
      kill -KILL -- "-${server_pid}" 2>/dev/null || true
    fi
  fi
  if test -n "${server_pid}" && kill -0 "${server_pid}" 2>/dev/null; then
    cleanup=incomplete
  fi
  printf '%s\n' "${cleanup}" > "${CELL_DIR}/cleanup_status.txt"
}
trap cleanup_cell EXIT

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
CANN_GENERATED_PYTHONPATH=${PYTHONPATH:-}

mkdir -p "${OVERLAY_ROOT}"
cp -a "${BASE_PLUGIN_ROOT}" "${OVERLAY_ROOT}/vllm_ascend"
OVERLAY_PROPOSER=${OVERLAY_ROOT}/vllm_ascend/spec_decode/llm_base_proposer.py
patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${PATCH_PATH}" > "${RUNTIME_DIR}/patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${PATCH_PATH}" > "${RUNTIME_DIR}/patch_apply.txt"
test "$(sha256sum "${OVERLAY_PROPOSER}" | awk '{print $1}')" = 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb

export PYTHONPATH="${OVERLAY_ROOT}:${CANN_GENERATED_PYTHONPATH}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7

cmd=(
  "${VLLM_BIN}" serve "${MODEL_PATH}"
  --safetensors-load-strategy prefetch
  --max-model-len 135168
  --max-num-batched-tokens 4096
  --served-model-name "${SERVED_MODEL_NAME}"
  --gpu-memory-utilization 0.92
  --max-num-seqs 1
  --data-parallel-size 1
  --tensor-parallel-size 8
  --enable-expert-parallel
  --quantization ascend
  --host "${HOST}"
  --port "${PORT}"
  --block-size 128
  --enable-chunked-prefill
  --enable-prefix-caching
  --tokenizer-mode deepseek_v4
  --tool-call-parser deepseek_v4
  --enable-auto-tool-choice
  --reasoning-parser deepseek_v4
  --async-scheduling
  --additional-config '{"enable_flashcomm1":true,"enable_dsa_cp":true,"enable_cpu_binding":true,"multistream_overlap_shared_expert":false}'
  --model-loader-extra-config '{"enable_multithread_load":true,"num_threads":16}'
  --compilation-config '{"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[2,4,6,8,10,12,14,16,18,20,22,24,32,36,40]}'
  --speculative-config '{"method":"mtp","num_speculative_tokens":1}'
)
printf '%q ' "${cmd[@]}" > "${RUNTIME_DIR}/server_command.txt"
printf '\n' >> "${RUNTIME_DIR}/server_command.txt"
sha256sum "${RUNTIME_DIR}/server_command.txt" > "${RUNTIME_DIR}/server_command_sha256.txt"
test "$(awk '{print $1}' "${RUNTIME_DIR}/server_command_sha256.txt")" = 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19

setsid "${cmd[@]}" > "${RUNTIME_DIR}/vllm_server.log" 2>&1 &
server_pid=$!
printf '%s\n' "${server_pid}" > "${RUNTIME_DIR}/server_pid.txt"
ready_exit=1
for _ in $(seq 1 180); do
  kill -0 "${server_pid}" 2>/dev/null || break
  if curl -fsS --max-time 5 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
    ready_exit=0
    break
  fi
  sleep 10
done
printf '%s\n' "${ready_exit}" > "${RUNTIME_DIR}/server_ready_exit_code.txt"
test "${ready_exit}" -eq 0

curl -fsS "http://${HOST}:${PORT}/metrics" > "${RUNTIME_DIR}/live_metrics_preflight.prom"
for metric_name in \
  'vllm:spec_decode_num_drafts_total' \
  'vllm:spec_decode_num_draft_tokens_total' \
  'vllm:spec_decode_num_accepted_tokens_total' \
  'vllm:num_requests_running' \
  'vllm:num_requests_waiting'; do
  grep -F "${metric_name}" "${RUNTIME_DIR}/live_metrics_preflight.prom" >/dev/null
done

set +e
"${PYTHON_BIN}" "${RUNNER_PATH}" run-cell \
  --artifact-dir "${RESULT_DIR}" \
  --cell-id "${CELL_ID}" \
  --base-url "http://${HOST}:${PORT}" \
  --server-pid "${server_pid}" \
  --sample-interval-seconds 1.0
run_exit=$?
set -e
printf '%s\n' "${run_exit}" > "${CELL_DIR}/run_cell_exit_code.txt"
exit "${run_exit}"
