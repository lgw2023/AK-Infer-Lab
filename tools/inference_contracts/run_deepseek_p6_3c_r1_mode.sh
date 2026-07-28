#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 4; then
  echo "usage: $0 ARTIFACT_DIR LIFECYCLE_ID TRACK MODE" >&2
  exit 64
fi

ARTIFACT_DIR=$1
LIFECYCLE_ID=$2
TRACK=$3
MODE=$4
case "${TRACK}:${MODE}" in
  mechanism:chunked_prefill_off|mechanism:chunked_prefill_on|\
  performance:chunked_prefill_off|performance:chunked_prefill_on) ;;
  *) echo "unsupported track/mode: ${TRACK}/${MODE}" >&2; exit 64 ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
ENV_PREFIX=${ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
PYTHON_BIN=${PYTHON_BIN:-${ENV_PREFIX}/bin/python}
VLLM_BIN=${VLLM_BIN:-${ENV_PREFIX}/bin/vllm}
BASE_PLUGIN_ROOT=${BASE_PLUGIN_ROOT:-${ENV_PREFIX}/lib/python3.11/site-packages/vllm_ascend}
BASE_VLLM_ROOT=${BASE_VLLM_ROOT:-/data/node0_disk1/vllm-0.22.1/vllm}
BASE_PROPOSER=${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py
BASE_CONNECTOR_INIT=${BASE_PLUGIN_ROOT}/distributed/kv_transfer/__init__.py
BASE_SCHEDULER=${BASE_VLLM_ROOT}/v1/core/sched/scheduler.py
MODEL_PATH=${MODEL_PATH:-/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp}
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-deepseek-v4-flash-w8a8-mtp}
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-7000}
REQUEST_RUNNER=${REQUEST_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_scheduler_pressure.py}
ARGV_IDENTITY=${ARGV_IDENTITY:-${SCRIPT_DIR}/canonicalize_server_argv.py}
MTP_PATCH=${MTP_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch}
OBSERVER=${OBSERVER:-${SCRIPT_DIR}/p6_3c_r1_scheduler_observer.py}
OBSERVER_PATCH=${OBSERVER_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch}
LIFECYCLE_DIR=${ARTIFACT_DIR}/lifecycles/${LIFECYCLE_ID}
RUNTIME_DIR=${LIFECYCLE_DIR}/runtime
OVERLAY_ROOT=${RUNTIME_DIR}/overlay_root
TRACE_DIR=${RUNTIME_DIR}/scheduler_trace
server_pid=

cmd=(
  "${VLLM_BIN}" serve "${MODEL_PATH}"
  --safetensors-load-strategy prefetch
  --max-model-len 69632
  --max-num-batched-tokens 69632
  --served-model-name "${SERVED_MODEL_NAME}"
  --gpu-memory-utilization 0.92
  --max-num-seqs 2
  --data-parallel-size 1
  --tensor-parallel-size 8
  --enable-expert-parallel
  --quantization ascend
  --host "${HOST}"
  --port "${PORT}"
  --block-size 128
)
case "${MODE}" in
  chunked_prefill_off) cmd+=(--no-enable-chunked-prefill) ;;
  chunked_prefill_on) cmd+=(--enable-chunked-prefill) ;;
esac
cmd+=(
  --no-enable-prefix-caching
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
  printf 'lifecycle_id=%s\n' "${LIFECYCLE_ID}"
  printf 'track=%s\n' "${TRACK}"
  printf 'mode=%s\n' "${MODE}"
  printf 'max_model_len=69632\n'
  printf 'max_num_batched_tokens=69632\n'
  printf 'max_num_seqs=2\n'
  printf 'prefix_cache=false\n'
  printf 'observer=%s\n' "$([ "${TRACK}" = mechanism ] && printf enabled || printf disabled)"
  printf 'profiler=disabled\n'
  printf 'request_retry_count=0\n'
  "${PYTHON_BIN}" "${ARGV_IDENTITY}" -- "${cmd[@]}" |
    sed 's/^/server_argv_sha256=/'
}

if test "${P6_3C_R1_MODE_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test -d "${ARTIFACT_DIR}"
test ! -e "${LIFECYCLE_DIR}"
test -x "${PYTHON_BIN}"
test -x "${VLLM_BIN}"
test -f "${REQUEST_RUNNER}"
test -f "${ARGV_IDENTITY}"
test -f "${MTP_PATCH}"
test -f "${OBSERVER}"
test -f "${OBSERVER_PATCH}"
test -f "${BASE_PROPOSER}"
test -f "${BASE_CONNECTOR_INIT}"
test -f "${BASE_SCHEDULER}"
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = \
  0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
test "$(sha256sum "${BASE_CONNECTOR_INIT}" | awk '{print $1}')" = \
  dc693fd52eb44921e731b69021388ecc186f4e5fa5eca3b28fc1963661e355d1
test "$(sha256sum "${BASE_SCHEDULER}" | awk '{print $1}')" = \
  41ff2e524c90d9aa72b72cd77492eb62ee2a729a773bd8233e970f39abbb5983

cleanup_mode() {
  local cleanup=clean
  trap - EXIT INT TERM
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
    wait "${server_pid}" 2>/dev/null
  fi
  if test -n "${server_pid}" && kill -0 "${server_pid}" 2>/dev/null; then
    cleanup=incomplete
  fi
  if curl -fsS --max-time 2 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
    cleanup=incomplete
  fi
  printf '%s\n' "${cleanup}" > "${LIFECYCLE_DIR}/cleanup_status.txt"
}
trap cleanup_mode EXIT INT TERM

mkdir -p "${RUNTIME_DIR}" "${OVERLAY_ROOT}"
set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
CANN_GENERATED_PYTHONPATH=${PYTHONPATH:-}

cp -a --no-preserve=ownership "${BASE_PLUGIN_ROOT}" "${OVERLAY_ROOT}/vllm_ascend"
patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${MTP_PATCH}" \
  > "${RUNTIME_DIR}/mtp_patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${MTP_PATCH}" \
  > "${RUNTIME_DIR}/mtp_patch_apply.txt"
test "$(sha256sum "${OVERLAY_ROOT}/vllm_ascend/spec_decode/llm_base_proposer.py" | awk '{print $1}')" = \
  7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02

if test "${TRACK}" = mechanism; then
  cp "${OBSERVER}" "${OVERLAY_ROOT}/p6_3c_r1_scheduler_observer.py"
  patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${OBSERVER_PATCH}" \
    > "${RUNTIME_DIR}/observer_patch_dry_run.txt"
  patch -p1 -d "${OVERLAY_ROOT}" < "${OBSERVER_PATCH}" \
    > "${RUNTIME_DIR}/observer_patch_apply.txt"
  mkdir -p "${TRACE_DIR}"
else
  test ! -e "${OVERLAY_ROOT}/p6_3c_r1_scheduler_observer.py"
fi

export PYTHONPATH="${OVERLAY_ROOT}:${CANN_GENERATED_PYTHONPATH}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export P6_3C_R1_MODE="${MODE}"
export P6_3C_R1_TRACK="${TRACK}"
if test "${TRACK}" = mechanism; then
  export P6_3C_R1_SCHEDULER_TRACE_DIR="${TRACE_DIR}"
  "${PYTHON_BIN}" - <<'PY' > "${RUNTIME_DIR}/observer_self_test.txt" 2>&1
from vllm_ascend.distributed.kv_transfer import register_connector
register_connector()
from vllm.v1.core.sched.scheduler import Scheduler
assert Scheduler._p6_3c_r1_observer_installed is True
print("pass")
PY
else
  unset P6_3C_R1_SCHEDULER_TRACE_DIR
fi

printf '%q ' "${cmd[@]}" > "${RUNTIME_DIR}/server_command.txt"
printf '\n' >> "${RUNTIME_DIR}/server_command.txt"
"${PYTHON_BIN}" "${ARGV_IDENTITY}" \
  --output "${RUNTIME_DIR}/server_argv.json" -- "${cmd[@]}" \
  > "${RUNTIME_DIR}/server_argv_sha256.txt"

setsid "${cmd[@]}" > "${RUNTIME_DIR}/vllm_server.log" 2>&1 &
server_pid=$!
printf '%s\n' "${server_pid}" > "${RUNTIME_DIR}/server_pid.txt"

"${PYTHON_BIN}" - \
  "${MODE}" "${TRACK}" \
  "${RUNTIME_DIR}/server_command.txt" \
  "/proc/${server_pid}/cmdline" \
  "${RUNTIME_DIR}/resolved_scheduler_config.json" <<'PY'
import json
import shlex
import sys
import time
from pathlib import Path

mode, track, command_path, process_path, output_path = sys.argv[1:]
expected_enabled = mode == "chunked_prefill_on"
expected_flag = (
    "--enable-chunked-prefill"
    if expected_enabled
    else "--no-enable-chunked-prefill"
)
opposite_flag = (
    "--no-enable-chunked-prefill"
    if expected_enabled
    else "--enable-chunked-prefill"
)
server_args = shlex.split(Path(command_path).read_text(encoding="utf-8"))
process_args = []
for _ in range(200):
    try:
        process_args = [
            value.decode("utf-8", errors="replace")
            for value in Path(process_path).read_bytes().split(b"\0")
            if value
        ]
    except OSError:
        process_args = []
    if expected_flag in process_args:
        break
    time.sleep(0.05)

def value_after(flag):
    index = server_args.index(flag)
    return int(server_args[index + 1])

evidence = {
    "mode": mode,
    "track": track,
    "resolved_enable_chunked_prefill": expected_enabled,
    "resolved_enable_prefix_caching": False,
    "max_model_len": value_after("--max-model-len"),
    "max_num_batched_tokens": value_after("--max-num-batched-tokens"),
    "max_num_seqs": value_after("--max-num-seqs"),
    "observer_enabled": track == "mechanism",
    "profiler_enabled": False,
    "resolution_basis": "explicit_cli_flags_and_live_process_cmdline",
    "server_command_has_expected_flag": expected_flag in server_args,
    "server_command_has_opposite_flag": opposite_flag in server_args,
    "process_cmdline_has_expected_flag": expected_flag in process_args,
    "process_cmdline_has_opposite_flag": opposite_flag in process_args,
    "prefix_cache_off_explicit": "--no-enable-prefix-caching" in server_args,
    "prefix_cache_on_absent": "--enable-prefix-caching" not in server_args,
}
Path(output_path).write_text(
    json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
assert evidence["max_model_len"] == 69632
assert evidence["max_num_batched_tokens"] == 69632
assert evidence["max_num_seqs"] == 2
assert evidence["server_command_has_expected_flag"]
assert not evidence["server_command_has_opposite_flag"]
assert evidence["process_cmdline_has_expected_flag"]
assert not evidence["process_cmdline_has_opposite_flag"]
assert evidence["prefix_cache_off_explicit"]
assert evidence["prefix_cache_on_absent"]
PY

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
  printf '%s\n' "${LIFECYCLE_ID}:server_not_ready" \
    > "${ARTIFACT_DIR}/first_failure_excerpt.txt"
  exit 2
fi

curl -fsS "http://${HOST}:${PORT}/metrics" > "${RUNTIME_DIR}/metrics_preflight.prom"
for metric in \
  vllm:spec_decode_num_drafts_total \
  vllm:spec_decode_num_draft_tokens_total \
  vllm:spec_decode_num_accepted_tokens_total \
  vllm:num_requests_running \
  vllm:num_requests_waiting
do
  grep -F "${metric}" "${RUNTIME_DIR}/metrics_preflight.prom" >/dev/null
done

set +e
"${PYTHON_BIN}" "${REQUEST_RUNNER}" run-mode \
  --artifact-dir "${ARTIFACT_DIR}" \
  --lifecycle-dir "${LIFECYCLE_DIR}" \
  --base-url "http://${HOST}:${PORT}" \
  --server-pid "${server_pid}" \
  --track "${TRACK}" \
  --mode "${MODE}"
run_exit=$?
set -e
printf '%s\n' "${run_exit}" > "${LIFECYCLE_DIR}/lifecycle_exit_code.txt"
exit "${run_exit}"
