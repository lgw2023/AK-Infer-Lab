#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

RESULT_DIR=$1
MODE=prefix_cache_on
REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
ENV_PREFIX=${ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
PYTHON_BIN=${PYTHON_BIN:-${ENV_PREFIX}/bin/python}
VLLM_BIN=${VLLM_BIN:-${ENV_PREFIX}/bin/vllm}
BASE_VLLM_ROOT=${BASE_VLLM_ROOT:-${ENV_PREFIX}/lib/python3.11/site-packages/vllm}
BASE_PLUGIN_ROOT=${BASE_PLUGIN_ROOT:-${ENV_PREFIX}/lib/python3.11/site-packages/vllm_ascend}
BASE_PROPOSER=${BASE_PROPOSER:-${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py}
BASE_VLLM_SINGLE=${BASE_VLLM_ROOT}/v1/core/single_type_kv_cache_manager.py
BASE_VLLM_COORDINATOR=${BASE_VLLM_ROOT}/v1/core/kv_cache_coordinator.py
BASE_ASCEND_COORDINATOR=${BASE_PLUGIN_ROOT}/patch/platform/patch_kv_cache_coordinator.py
MODEL_PATH=${MODEL_PATH:-/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp}
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-deepseek-v4-flash-w8a8-mtp}
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-7000}
REQUEST_RUNNER=${REQUEST_RUNNER:-${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_3b_prefix_cache_ab.py}
RUNTIME_PATCH=${RUNTIME_PATCH:-${REPO_ROOT}/tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py}
MTP_PATCH=${MTP_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch}
HYBRID_PATCH=${HYBRID_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch}
MODE_DIR=${RESULT_DIR}/modes/${MODE}
RUNTIME_DIR=${MODE_DIR}/runtime
OVERLAY_ROOT=${RUNTIME_DIR}/overlay_root
DIAGNOSTIC_PATH=${RUNTIME_DIR}/hybrid_kv_runtime_diagnostic.jsonl
server_pid=

cleanup_mode() {
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
  printf '%s\n' "${cleanup}" > "${MODE_DIR}/cleanup_status.txt"
}
trap cleanup_mode EXIT

mkdir -p "${RUNTIME_DIR}" "${MODE_DIR}/raw_metrics" "${OVERLAY_ROOT}"
set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
CANN_GENERATED_PYTHONPATH=${PYTHONPATH:-}

test "$(stat -c '%s' "${BASE_VLLM_SINGLE}")" = 53714
test "$(sha256sum "${BASE_VLLM_SINGLE}" | awk '{print $1}')" = d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1
test "$(stat -c '%s' "${BASE_VLLM_COORDINATOR}")" = 25255
test "$(sha256sum "${BASE_VLLM_COORDINATOR}" | awk '{print $1}')" = a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89
test "$(stat -c '%s' "${BASE_ASCEND_COORDINATOR}")" = 23103
test "$(sha256sum "${BASE_ASCEND_COORDINATOR}" | awk '{print $1}')" = dc65ed2adbb05ea52d9e891f648b62a5391eb41b2a6b262b71d40efe31effe20
test "$(sha256sum "${RUNTIME_PATCH}" | awk '{print $1}')" = 6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c
test "$(sha256sum "${HYBRID_PATCH}" | awk '{print $1}')" = cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e

cp -a "${BASE_PLUGIN_ROOT}" "${OVERLAY_ROOT}/vllm_ascend"
cp "${RUNTIME_PATCH}" "${OVERLAY_ROOT}/sitecustomize.py"
patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${MTP_PATCH}" > "${RUNTIME_DIR}/mtp_patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${MTP_PATCH}" > "${RUNTIME_DIR}/mtp_patch_apply.txt"
patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${HYBRID_PATCH}" > "${RUNTIME_DIR}/hybrid_patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${HYBRID_PATCH}" > "${RUNTIME_DIR}/hybrid_patch_apply.txt"
OVERLAY_PROPOSER=${OVERLAY_ROOT}/vllm_ascend/spec_decode/llm_base_proposer.py
OVERLAY_ASCEND_COORDINATOR=${OVERLAY_ROOT}/vllm_ascend/patch/platform/patch_kv_cache_coordinator.py
test "$(sha256sum "${OVERLAY_PROPOSER}" | awk '{print $1}')" = 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
test "$(sha256sum "${OVERLAY_ASCEND_COORDINATOR}" | awk '{print $1}')" = a1ed9c82e308608cd20965a49baa29a3e95d723248fff699fd83dfb3caf10250

export PYTHONPATH="${OVERLAY_ROOT}:${CANN_GENERATED_PYTHONPATH}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
if test -v VLLM_PREFIX_CACHE_RETENTION_INTERVAL; then
  printf '%s\n' set > "${RUNTIME_DIR}/inherited_retention_interval_presence.txt"
else
  printf '%s\n' unset > "${RUNTIME_DIR}/inherited_retention_interval_presence.txt"
fi
unset VLLM_PREFIX_CACHE_RETENTION_INTERVAL
printf '%s\n' explicitly_unset > "${RUNTIME_DIR}/effective_retention_interval.txt"

P6_3B_R1_ENABLE_HYBRID_KV_PATCH=1 \
P6_3B_R1_HYBRID_KV_DIAGNOSTIC_PATH="${DIAGNOSTIC_PATH}" \
"${PYTHON_BIN}" -c 'import sitecustomize; assert sitecustomize.PATCH_INSTALLED' \
  > "${RUNTIME_DIR}/runtime_patch_self_test.txt" 2>&1
printf '%s\n' pass > "${RUNTIME_DIR}/source_gate_status.txt"

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
sha256sum "${RUNTIME_DIR}/server_command.txt" > "${MODE_DIR}/server_command_sha256.txt"
test "$(awk '{print $1}' "${MODE_DIR}/server_command_sha256.txt")" = 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19

P6_3B_R1_ENABLE_HYBRID_KV_PATCH=1 \
P6_3B_R1_HYBRID_KV_DIAGNOSTIC_PATH="${DIAGNOSTIC_PATH}" \
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
if test "${ready_exit}" -ne 0; then
  printf '%s\n' "${MODE}:server_not_ready" > "${MODE_DIR}/first_failure_excerpt.txt"
  exit 2
fi

curl -fsS "http://${HOST}:${PORT}/metrics" > "${RUNTIME_DIR}/live_metrics_preflight.prom"
grep -F 'vllm:num_requests_running' "${RUNTIME_DIR}/live_metrics_preflight.prom" >/dev/null
grep -F 'vllm:num_requests_waiting' "${RUNTIME_DIR}/live_metrics_preflight.prom" >/dev/null
grep -F 'vllm:spec_decode_num_drafts_total' "${RUNTIME_DIR}/live_metrics_preflight.prom" >/dev/null
grep -F 'vllm:spec_decode_num_draft_tokens_total' "${RUNTIME_DIR}/live_metrics_preflight.prom" >/dev/null
grep -F 'vllm:spec_decode_num_accepted_tokens_total' "${RUNTIME_DIR}/live_metrics_preflight.prom" >/dev/null
grep -E 'vllm:prefix_cache_queries(_total)?' "${RUNTIME_DIR}/live_metrics_preflight.prom" >/dev/null
grep -E 'vllm:prefix_cache_hits(_total)?' "${RUNTIME_DIR}/live_metrics_preflight.prom" >/dev/null

set +e
"${PYTHON_BIN}" "${REQUEST_RUNNER}" run-mode \
  --artifact-dir "${RESULT_DIR}" \
  --base-url "http://${HOST}:${PORT}" \
  --server-pid "${server_pid}" \
  --mode "${MODE}"
run_exit=$?
set -e
printf '%s\n' "${run_exit}" > "${MODE_DIR}/run_exit_code.txt"
exit "${run_exit}"
