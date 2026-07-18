#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

RESULT_DIR=$1
TASK_ID=${P8_2_K1A_TASK_ID:-p8_2_k1a_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0717}
CPU_BYTES_TO_USE=${P8_2_K1A_CPU_BYTES_TO_USE:-274877906944}
CPU_BYTES_TO_USE_PER_RANK=${P8_2_K1A_CPU_BYTES_TO_USE_PER_RANK:-34359738368}
HOST_MEM_AVAILABLE_MIN=${P8_2_K1A_HOST_MEM_AVAILABLE_MIN:-412316860416}
REPO_FILE_LIST=${P8_2_K1A_REPO_FILE_LIST:-benchmarks/deepseek_v4_flash/p8_2_k1a_simple_cpu_offload_feasibility_audit.yaml:benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_simple_cpu_offload_store_restore.yaml:tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py:tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh:benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch}
REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
ENV_PREFIX=${ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
PYTHON_BIN=${PYTHON_BIN:-${ENV_PREFIX}/bin/python}
VLLM_BIN=${VLLM_BIN:-${ENV_PREFIX}/bin/vllm}
BASE_PLUGIN_ROOT=${BASE_PLUGIN_ROOT:-${ENV_PREFIX}/lib/python3.11/site-packages/vllm_ascend}
BASE_VLLM_ROOT=${BASE_VLLM_ROOT:-/data/node0_disk1/vllm-0.22.1/vllm}
BASE_PROPOSER=${BASE_PROPOSER:-${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py}
BASE_VLLM_SINGLE=${BASE_VLLM_ROOT}/v1/core/single_type_kv_cache_manager.py
BASE_VLLM_COORDINATOR=${BASE_VLLM_ROOT}/v1/core/kv_cache_coordinator.py
BASE_ASCEND_COORDINATOR=${BASE_PLUGIN_ROOT}/patch/platform/patch_kv_cache_coordinator.py
BASE_ASCEND_INTERFACE=${BASE_PLUGIN_ROOT}/patch/platform/patch_kv_cache_interface.py
MODEL_PATH=${MODEL_PATH:-/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp}
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-deepseek-v4-flash-w8a8-mtp}
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-7000}
REQUEST_RUNNER=${REQUEST_RUNNER:-${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py}
AUDITOR=${AUDITOR:-${REPO_ROOT}/tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py}
OBSERVER=${OBSERVER:-${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py}
RUNTIME_IMPL=${RUNTIME_IMPL:-${REPO_ROOT}/tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py}
RUNTIME_LOADER=${RUNTIME_LOADER:-${REPO_ROOT}/tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py}
MTP_PATCH=${MTP_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch}
HYBRID_PATCH=${HYBRID_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch}
DEFERRED_PATCH=${DEFERRED_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch}
OBSERVER_PATCH=${OBSERVER_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch}
RUNTIME_DIR=${RESULT_DIR}/runtime
OVERLAY_ROOT=${RUNTIME_DIR}/overlay_root
DIAGNOSTIC_PATH=${RUNTIME_DIR}/hybrid_kv_runtime_diagnostic.jsonl
TRACE_DIR=${RUNTIME_DIR}/offload_trace
KV_TRANSFER_JSON=$(printf '{"kv_connector":"SimpleCPUOffloadConnector","kv_role":"kv_both","kv_connector_extra_config":{"cpu_bytes_to_use":%s,"cpu_bytes_to_use_per_rank":%s,"lazy_offload":false}}' "${CPU_BYTES_TO_USE}" "${CPU_BYTES_TO_USE_PER_RANK}")
EXPECTED_COMMAND_SHA256=${P8_2_K1A_EXPECTED_COMMAND_SHA256:-d4222bef3a1c39dd38297b0523b9df54e3f3cef3ff67e4b970e6fce3f95708a5}
server_pid=

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
  --kv-transfer-config "${KV_TRANSFER_JSON}"
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

audit_contract() {
  local rendered
  printf -v rendered '%q ' "${cmd[@]}"
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'lifecycle_count=1\n'
  printf 'request_count=6\n'
  printf 'kv_connector=SimpleCPUOffloadConnector\n'
  printf 'cpu_bytes_to_use=%s\n' "${CPU_BYTES_TO_USE}"
  printf 'cpu_bytes_to_use_per_rank=%s\n' "${CPU_BYTES_TO_USE_PER_RANK}"
  printf 'lazy_offload=false\n'
  printf 'observer_mode=observe_only_no_decision_or_copy_mutation\n'
  printf 'server_command=%s\n' "${rendered% }"
}

if test "${P8_2_K1A_MODE_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

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
  if curl -fsS --max-time 2 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
    cleanup=incomplete
  fi
  printf '%s\n' "${cleanup}" > "${RESULT_DIR}/cleanup_status.txt"
  if test -f "${RESULT_DIR}/host_memory_summary.json"; then
    "${PYTHON_BIN}" - "${RESULT_DIR}/host_memory_summary.json" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
value = json.loads(path.read_text(encoding="utf-8"))
meminfo = {}
for line in Path("/proc/meminfo").read_text().splitlines():
    key, raw = line.split(":", 1)
    meminfo[key] = int(raw.strip().split()[0]) * 1024
value["post_cleanup_mem_available_bytes"] = meminfo["MemAvailable"]
value["post_cleanup_swap_used_bytes"] = meminfo["SwapTotal"] - meminfo["SwapFree"]
path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  fi
}
trap cleanup_mode EXIT

test -f "${RESULT_DIR}/run_plan.json"
test -f "${RESULT_DIR}/request_body_manifest.json"
test ! -e "${RUNTIME_DIR}"
mkdir -p "${RUNTIME_DIR}" "${OVERLAY_ROOT}" "${TRACE_DIR}"

"${PYTHON_BIN}" - "${RESULT_DIR}/host_memory_summary.json" "${CPU_BYTES_TO_USE}" "${CPU_BYTES_TO_USE_PER_RANK}" "${HOST_MEM_AVAILABLE_MIN}" <<'PY'
import json
from pathlib import Path
import sys

output = Path(sys.argv[1])
cpu_total, cpu_per_rank, minimum = map(int, sys.argv[2:])
meminfo = {}
for line in Path("/proc/meminfo").read_text().splitlines():
    key, raw = line.split(":", 1)
    meminfo[key] = int(raw.strip().split()[0]) * 1024
value = {
    "configured_cpu_tier_bytes_total": cpu_total,
    "configured_cpu_tier_bytes_per_rank": cpu_per_rank,
    "preflight_mem_available_bytes": meminfo["MemAvailable"],
    "preflight_swap_used_bytes": meminfo["SwapTotal"] - meminfo["SwapFree"],
    "required_mem_available_bytes_min": minimum,
    "preflight_gate_ok": (
        meminfo["MemAvailable"] >= minimum
        and meminfo["SwapTotal"] == meminfo["SwapFree"]
    ),
}
output.write_text(
    json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
assert value["preflight_gate_ok"]
PY

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
CANN_GENERATED_PYTHONPATH=${PYTHONPATH:-}

test "$(stat -c '%s' "${BASE_VLLM_SINGLE}")" = 53714
test "$(sha256sum "${BASE_VLLM_SINGLE}" | awk '{print $1}')" = d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1
test "$(stat -c '%s' "${BASE_VLLM_COORDINATOR}")" = 25255
test "$(sha256sum "${BASE_VLLM_COORDINATOR}" | awk '{print $1}')" = a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89
test "$(sha256sum "${BASE_ASCEND_COORDINATOR}" | awk '{print $1}')" = dc65ed2adbb05ea52d9e891f648b62a5391eb41b2a6b262b71d40efe31effe20
test "$(sha256sum "${BASE_ASCEND_INTERFACE}" | awk '{print $1}')" = a4969e2c1b2ebde9a3c5a4d02df5175879fb56ea43322869871a3868ec1981b2
test "$(sha256sum "${RUNTIME_IMPL}" | awk '{print $1}')" = 6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c
test "$(sha256sum "${RUNTIME_LOADER}" | awk '{print $1}')" = 9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631
test "$(sha256sum "${MTP_PATCH}" | awk '{print $1}')" = 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
test "$(sha256sum "${HYBRID_PATCH}" | awk '{print $1}')" = cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e
test "$(sha256sum "${DEFERRED_PATCH}" | awk '{print $1}')" = ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b
test "$(sha256sum "${OBSERVER_PATCH}" | awk '{print $1}')" = 5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6

cp -a --no-preserve=ownership "${BASE_PLUGIN_ROOT}" "${OVERLAY_ROOT}/vllm_ascend"
cp "${RUNTIME_IMPL}" "${OVERLAY_ROOT}/p6_3b_hybrid_kv_runtime_impl.py"
cp "${RUNTIME_LOADER}" "${OVERLAY_ROOT}/p6_3b_r2_hybrid_kv_runtime_patch.py"
cp "${OBSERVER}" "${OVERLAY_ROOT}/p8_2_k1a_simple_cpu_offload_observer.py"
patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${MTP_PATCH}" > "${RUNTIME_DIR}/mtp_patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${MTP_PATCH}" > "${RUNTIME_DIR}/mtp_patch_apply.txt"
patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${HYBRID_PATCH}" > "${RUNTIME_DIR}/hybrid_patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${HYBRID_PATCH}" > "${RUNTIME_DIR}/hybrid_patch_apply.txt"
if patch -l -p1 -d "${OVERLAY_ROOT}" --dry-run < "${DEFERRED_PATCH}" > "${RUNTIME_DIR}/deferred_patch_dry_run.txt" 2>&1; then
  patch -l -p1 -d "${OVERLAY_ROOT}" < "${DEFERRED_PATCH}" > "${RUNTIME_DIR}/deferred_patch_apply.txt"
  printf '%s\n' patch_l > "${RUNTIME_DIR}/deferred_patch_method.txt"
else
  (
    cd "${OVERLAY_ROOT}"
    GIT_DIR=/dev/null git apply --check --ignore-whitespace "${DEFERRED_PATCH}"
    GIT_DIR=/dev/null git apply --ignore-whitespace "${DEFERRED_PATCH}"
  ) > "${RUNTIME_DIR}/deferred_patch_apply.txt" 2>&1
  printf '%s\n' git_apply_ignore_whitespace > "${RUNTIME_DIR}/deferred_patch_method.txt"
fi
patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${OBSERVER_PATCH}" > "${RUNTIME_DIR}/observer_patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${OBSERVER_PATCH}" > "${RUNTIME_DIR}/observer_patch_apply.txt"

OVERLAY_PROPOSER=${OVERLAY_ROOT}/vllm_ascend/spec_decode/llm_base_proposer.py
OVERLAY_ASCEND_COORDINATOR=${OVERLAY_ROOT}/vllm_ascend/patch/platform/patch_kv_cache_coordinator.py
OVERLAY_ASCEND_INTERFACE=${OVERLAY_ROOT}/vllm_ascend/patch/platform/patch_kv_cache_interface.py
OVERLAY_CONNECTOR_INIT=${OVERLAY_ROOT}/vllm_ascend/distributed/kv_transfer/__init__.py
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
test "$(sha256sum "${OVERLAY_PROPOSER}" | awk '{print $1}')" = 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
test "$(sha256sum "${OVERLAY_ASCEND_COORDINATOR}" | awk '{print $1}')" = a1ed9c82e308608cd20965a49baa29a3e95d723248fff699fd83dfb3caf10250
test "$(sha256sum "${OVERLAY_ASCEND_INTERFACE}" | awk '{print $1}')" = 524c933ef17806ecba0634804bc562de1f69dc095fe1346e2edd0103845bfa75
test "$(stat -c '%s' "${OVERLAY_CONNECTOR_INIT}")" = 3483
test "$(sha256sum "${OVERLAY_CONNECTOR_INIT}" | awk '{print $1}')" = 8cf8a4f34f599562f6333c4fad565af7012e14993beefef84c8d831715b8be0b

export PYTHONPATH="${OVERLAY_ROOT}:${CANN_GENERATED_PYTHONPATH}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export P6_3B_R2_ENABLE_HYBRID_KV_PATCH=1
export P6_3B_R2_HYBRID_KV_DIAGNOSTIC_PATH="${DIAGNOSTIC_PATH}"
unset VLLM_PREFIX_CACHE_RETENTION_INTERVAL

"${PYTHON_BIN}" -c 'import vllm_ascend.patch.platform.patch_kv_cache_interface; import p6_3b_r2_hybrid_kv_runtime_patch as repair; assert repair.PATCH_INSTALLED; assert all(repair.require_ascend_manager_resolution().values()); from vllm_ascend.distributed.kv_transfer import register_connector; register_connector(); from vllm.distributed.kv_transfer.kv_connector.factory import KVConnectorFactory; cls = KVConnectorFactory.get_connector_class_by_name("SimpleCPUOffloadConnector"); assert cls.__name__ == "AscendSimpleCPUOffloadConnector"' > "${RUNTIME_DIR}/runtime_patch_self_test.txt" 2>&1
printf '%s\n' pass > "${RUNTIME_DIR}/source_gate_status.txt"
export P8_2_K1A_TRANSFER_TRACE_DIR="${TRACE_DIR}"

printf '%q ' "${cmd[@]}" > "${RUNTIME_DIR}/server_command.txt"
printf '\n' >> "${RUNTIME_DIR}/server_command.txt"
command_sha256=$(sha256sum "${RUNTIME_DIR}/server_command.txt" | awk '{print $1}')
printf '%s\n' "${command_sha256}" > "${RUNTIME_DIR}/server_command_sha256.txt"
test "${command_sha256}" = "${EXPECTED_COMMAND_SHA256}"

"${PYTHON_BIN}" - "${RESULT_DIR}/environment_and_hashes.json" "${REPO_ROOT}" "${command_sha256}" "${TASK_ID}" "${CPU_BYTES_TO_USE}" "${CPU_BYTES_TO_USE_PER_RANK}" "${REPO_FILE_LIST}" <<'PY'
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

output, root, command_sha, task_id, cpu_total, cpu_per_rank, relative_list = sys.argv[1:]
root = Path(root)
relative_paths = tuple(relative_list.split(":"))
value = {
    "task_id": task_id,
    "vllm": importlib.metadata.version("vllm"),
    "vllm_ascend": importlib.metadata.version("vllm-ascend"),
    "vllm_commit": "0decac0d96c42b49572498019f0a0e3600f50398",
    "vllm_ascend_commit": "5f6faa0cb8830f667266f3b8121cd1383606f2a1",
    "server_command_sha256": command_sha,
    "cpu_bytes_to_use": int(cpu_total),
    "cpu_bytes_to_use_per_rank": int(cpu_per_rank),
    "repo_file_sha256": {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in relative_paths
    },
    "generated_content_retained": False,
    "generated_token_ids_retained": False,
    "request_bodies_remain_server_local": True,
}
Path(output).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

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
  LC_ALL=C tail -n 120 "${RUNTIME_DIR}/vllm_server.log" | tail -c 8192 > "${RESULT_DIR}/first_failure_excerpt.txt"
  exit 2
fi

curl -fsS "http://${HOST}:${PORT}/metrics" > "${RUNTIME_DIR}/live_metrics_preflight.prom"
for metric in \
  vllm:num_requests_running \
  vllm:num_requests_waiting \
  vllm:prefix_cache_queries \
  vllm:prefix_cache_hits \
  vllm:spec_decode_num_drafts_total \
  vllm:spec_decode_num_draft_tokens_total \
  vllm:spec_decode_num_accepted_tokens_total
do
  grep -F "${metric}" "${RUNTIME_DIR}/live_metrics_preflight.prom" >/dev/null
done

"${PYTHON_BIN}" - "${RUNTIME_DIR}/server_command.txt" "/proc/${server_pid}/cmdline" "${RUNTIME_DIR}/vllm_server.log" "${TRACE_DIR}" "${RESULT_DIR}/connector_resolution_summary.json" "${KV_TRANSFER_JSON}" <<'PY'
import json
from pathlib import Path
import shlex
import sys

command_path, process_path, log_path, trace_dir, output_path, expected_json = sys.argv[1:]
server_args = shlex.split(Path(command_path).read_text(encoding="utf-8"))
process_args = [
    value.decode("utf-8", errors="replace")
    for value in Path(process_path).read_bytes().split(b"\0")
    if value
]
expected = json.loads(expected_json)
def value_after(values, flag):
    return values[values.index(flag) + 1] if values.count(flag) == 1 else None
server_config = json.loads(value_after(server_args, "--kv-transfer-config"))
process_config = json.loads(value_after(process_args, "--kv-transfer-config"))
log = Path(log_path).read_text(encoding="utf-8", errors="replace")
observer_rows = []
for path in Path(trace_dir).glob("trace.*.jsonl"):
    observer_rows.extend(
        json.loads(line) for line in path.read_text().splitlines() if line
    )
value = {
    "expected_config": expected,
    "server_command_config": server_config,
    "process_cmdline_config": process_config,
    "server_command_explicit_once": server_args.count("--kv-transfer-config") == 1,
    "process_cmdline_explicit_once": process_args.count("--kv-transfer-config") == 1,
    "ascend_connector_log_present": "AscendSimpleCPUOffloadConnector" in log,
    "npu_worker_log_present": "SimpleCPUOffloadNPUWorker" in log,
    "observer_installed_event_count": sum(
        row.get("event") == "observer_installed" for row in observer_rows
    ),
}
extra = expected["kv_connector_extra_config"]
value["cpu_bytes_to_use"] = extra["cpu_bytes_to_use"]
value["cpu_bytes_to_use_per_rank"] = extra["cpu_bytes_to_use_per_rank"]
value["resolved_cpu_capacity_exact"] = all((
    server_config == expected,
    process_config == expected,
    extra["cpu_bytes_to_use"] == extra["cpu_bytes_to_use_per_rank"] * 8,
))
value["resolved_connector_exact"] = all((
    server_config == expected,
    process_config == expected,
    value["server_command_explicit_once"],
    value["process_cmdline_explicit_once"],
    value["ascend_connector_log_present"],
    value["npu_worker_log_present"],
    value["observer_installed_event_count"] > 0,
    value["resolved_cpu_capacity_exact"],
))
Path(output_path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
assert value["resolved_connector_exact"]
PY

set +e
"${PYTHON_BIN}" "${REQUEST_RUNNER}" execute \
  --artifact-dir "${RESULT_DIR}" \
  --base-url "http://${HOST}:${PORT}" \
  --server-pid "${server_pid}"
run_exit=$?
set -e
printf '%s\n' "${run_exit}" > "${RUNTIME_DIR}/request_run_exit_code.txt"

"${PYTHON_BIN}" - "${DIAGNOSTIC_PATH}" "${RESULT_DIR}/repair_diagnostic_summary.json" <<'PY'
import json
from pathlib import Path
import sys
from tools.inference_contracts.run_deepseek_p6_3b_r1_hybrid_kv_repair import summarize_hybrid_diagnostics

source, output = map(Path, sys.argv[1:])
rows = [json.loads(line) for line in source.read_text().splitlines() if line]
summary = summarize_hybrid_diagnostics(rows, require_deferred_install=True)
output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
exit "${run_exit}"
