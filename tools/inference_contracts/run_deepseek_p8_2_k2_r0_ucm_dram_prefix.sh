#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k2_r0_run04_fawa_posix_gc_geometry_2026_0729
RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.py
BASE_ENV_PREFIX=${BASE_ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
UCM_ENV_PREFIX=${UCM_ENV_PREFIX:?UCM_ENV_PREFIX is required}
PYTHON_BIN=${UCM_ENV_PREFIX}/bin/python
BASE_PLUGIN_ROOT=${BASE_ENV_PREFIX}/lib/python3.11/site-packages/vllm_ascend
MODEL_PATH=${MODEL_PATH:-/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp}
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-deepseek-v4-flash-w8a8-mtp}
SOURCE_PAYLOAD=${SOURCE_PAYLOAD:-${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json}
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-7000}
RUNTIME_DIR=${RESULT_DIR}/runtime
OVERLAY_ROOT=${RUNTIME_DIR}/overlay_root
UCM_LOG_DIR=${RUNTIME_DIR}/ucm_logs
UCM_STORAGE_ROOT=${RUNTIME_DIR}/ucm_posix_backend
UCM_CONFIG_FILE=${RUNTIME_DIR}/ucm_dram_first_config.yaml
SERVER_LOG=${RUNTIME_DIR}/vllm_server.log
MTP_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch
UCM_CACHE_BUFFER_GIB_PER_STORE=16
UCM_POSIX_TOTAL_CAPACITY_GIB=64
UCM_POSIX_DATA_DIR_SHARD_BYTES=2
server_pid=

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'execution_mode=authorized_single_lifecycle_fawa_posix_gc_geometry_repair_and_ucm_external_prefix_path\n'
  printf 'formal_model_lifecycle_count_exact=1\n'
  printf 'request_order=warmup_4k,prime_32k,follower_exact_32k\n'
  printf 'model_request_count_exact=3\n'
  printf 'request_retry_count_exact=0\n'
  printf 'internal_prefix_cache_enabled=false\n'
  printf 'ucm_connector=UCMConnector\n'
  printf 'ucm_store_pipeline=Cache|Posix\n'
  printf 'ucm_cache_buffer_capacity_gb_per_fawa_store=%s\n' \
    "${UCM_CACHE_BUFFER_GIB_PER_STORE}"
  printf 'ucm_posix_capacity_gb_before_fawa_split=%s\n' \
    "${UCM_POSIX_TOTAL_CAPACITY_GIB}"
  printf 'ucm_posix_capacity_gb_per_fawa_store_after_split=32\n'
  printf 'ucm_posix_data_dir_shard_bytes=%s\n' \
    "${UCM_POSIX_DATA_DIR_SHARD_BYTES}"
  printf 'ucm_posix_directory_shard_count=256\n'
  printf 'ucm_posix_gc_trigger_threshold_ratio=0.7\n'
  printf 'ucm_posix_gc_recycle_percent=0.1\n'
  printf 'run03_fa_block_size_bytes=3186688\n'
  printf 'run03_wa_block_size_bytes=6627328\n'
  printf 'configured_wa_cache_buffer_number=2592\n'
  printf 'required_buffer_number=2048\n'
  printf 'ucm_use_layerwise=true\n'
  printf 'ucm_enable_event_sync=true\n'
  printf 'ucm_enable_metrics=true\n'
  printf 'ucm_use_gdr=false\n'
  printf 'performance_benefit_required=false\n'
  printf 'unique_root_cause_required=false\n'
  printf 'result_transfer_authorized=true\n'
}

if test "${P8_2_K2_R0_LIFECYCLE_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test -d "${RESULT_DIR}"
test -x "${PYTHON_BIN}"
test -f "${RUNNER}"
test -f "${SOURCE_PAYLOAD}"
test -d "${BASE_PLUGIN_ROOT}"
test -f "${MTP_PATCH}"
mkdir -p "${RUNTIME_DIR}" "${OVERLAY_ROOT}" "${UCM_LOG_DIR}" "${UCM_STORAGE_ROOT}"

cleanup_lifecycle() {
  set +e
  if test -n "${server_pid}" && kill -0 "${server_pid}" 2>/dev/null; then
    kill -TERM -- "-${server_pid}" 2>/dev/null
    for _ in $(seq 1 60); do
      kill -0 "${server_pid}" 2>/dev/null || break
      sleep 2
    done
    if kill -0 "${server_pid}" 2>/dev/null; then
      kill -KILL -- "-${server_pid}" 2>/dev/null
    fi
  fi
}
trap cleanup_lifecycle EXIT INT TERM

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
CANN_GENERATED_PYTHONPATH=${PYTHONPATH:-}

command cp -a --no-preserve=ownership \
  "${BASE_PLUGIN_ROOT}" "${OVERLAY_ROOT}/vllm_ascend"
patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${MTP_PATCH}" \
  > "${RUNTIME_DIR}/mtp_patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${MTP_PATCH}" \
  > "${RUNTIME_DIR}/mtp_patch_apply.txt"
test "$(sha256sum "${OVERLAY_ROOT}/vllm_ascend/spec_decode/llm_base_proposer.py" | awk '{print $1}')" = \
  7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02

cat > "${UCM_CONFIG_FILE}" <<EOF
ucm_connectors:
  - ucm_connector_name: "UcmPipelineStore"
    ucm_connector_config:
      store_pipeline: "Cache|Posix"
      storage_backends: "${UCM_STORAGE_ROOT}"
      cache_buffer_capacity_gb: ${UCM_CACHE_BUFFER_GIB_PER_STORE}
      posix_capacity_gb: ${UCM_POSIX_TOTAL_CAPACITY_GIB}
      data_dir_shard_bytes: ${UCM_POSIX_DATA_DIR_SHARD_BYTES}
      posix_gc_trigger_threshold_ratio: 0.7
      posix_gc_recycle_percent: 0.1
      io_direct: false
      posix_io_engine: "psync"
      use_gdr: false
      store_health:
        enabled: true
enable_event_sync: true
enable_metrics: true
use_layerwise: true
enable_record_traces: false
use_lite: false
persist_token_threshold: 0
load_tokens_threshold: 2048
EOF

"${PYTHON_BIN}" "${RUNNER}" prepare \
  --source-payload "${SOURCE_PAYLOAD}" \
  --artifact-dir "${RESULT_DIR}" \
  --model-name "${SERVED_MODEL_NAME}"

export PYTHONPATH="${OVERLAY_ROOT}:${CANN_GENERATED_PYTHONPATH}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export ENABLE_UCM_PATCH=1
export UCM_ENGINE_TYPE=vllm-ascend.a2
export UCM_LOG_PATH="${UCM_LOG_DIR}"
export UCM_LOG_MAX_FILES=8
export UCM_LOG_MAX_SIZE=10485760
export UC_LOGGER_LEVEL=debug
export PYTHONHASHSEED=123456
export VLLM_CPU_AFFINITY=1
unset VLLM_PREFIX_CACHE_RETENTION_INTERVAL

KV_TRANSFER_CONFIG=$("${PYTHON_BIN}" - "${UCM_CONFIG_FILE}" <<'PY'
import json
import sys
print(json.dumps({
    "kv_connector": "UCMConnector",
    "kv_connector_module_path": "ucm.integration.vllm.ucm_connector",
    "kv_role": "kv_both",
    "kv_connector_extra_config": {"UCM_CONFIG_FILE": sys.argv[1]},
}, separators=(",", ":"), sort_keys=True))
PY
)

"${PYTHON_BIN}" - <<'PY' > "${RUNTIME_DIR}/ucm_import_probe.txt"
import importlib.metadata
import ucm
import vllm
import vllm_ascend
from ucm.integration.vllm.ucm_connector import UCMConnector
from vllm_ascend.distributed.kv_transfer.kv_pool.ucm_connector import UCMConnectorV1
print("uc_manager=" + importlib.metadata.version("uc-manager"))
print("vllm=" + importlib.metadata.version("vllm"))
print("vllm_ascend=" + importlib.metadata.version("vllm-ascend"))
print("ucm_module=" + str(ucm.__file__))
print("connector=" + UCMConnector.__name__)
print("ascend_wrapper=" + UCMConnectorV1.__name__)
PY

cmd=(
  "${PYTHON_BIN}" -m vllm.entrypoints.cli.main
  serve "${MODEL_PATH}"
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
  --no-enable-prefix-caching
  --kv-transfer-config "${KV_TRANSFER_CONFIG}"
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

setsid "${cmd[@]}" > "${SERVER_LOG}" 2>&1 &
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
  LC_ALL=C tail -n 160 "${SERVER_LOG}" | tail -c 12000 \
    > "${RUNTIME_DIR}/startup_failure_excerpt.txt"
  exit 2
fi

curl -fsS "http://${HOST}:${PORT}/metrics" \
  > "${RUNTIME_DIR}/live_metrics_preflight.prom"
grep -F 'vllm:num_requests_running' \
  "${RUNTIME_DIR}/live_metrics_preflight.prom" >/dev/null
grep -F 'vllm:num_requests_waiting' \
  "${RUNTIME_DIR}/live_metrics_preflight.prom" >/dev/null
grep -F 'ucm:' "${RUNTIME_DIR}/live_metrics_preflight.prom" >/dev/null

set +e
"${PYTHON_BIN}" "${RUNNER}" run \
  --artifact-dir "${RESULT_DIR}" \
  --base-url "http://${HOST}:${PORT}" \
  --server-pid "${server_pid}" \
  --server-log "${SERVER_LOG}"
run_exit=$?
set -e
printf '%s\n' "${run_exit}" > "${RUNTIME_DIR}/run_exit_code.txt"
exit "${run_exit}"
