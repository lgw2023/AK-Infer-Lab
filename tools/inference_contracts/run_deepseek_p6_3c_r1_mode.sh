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
BASE_VLLM_SINGLE=${ENV_PREFIX}/lib/python3.11/site-packages/vllm/v1/core/single_type_kv_cache_manager.py
BASE_VLLM_COORDINATOR=${ENV_PREFIX}/lib/python3.11/site-packages/vllm/v1/core/kv_cache_coordinator.py
BASE_ASCEND_COORDINATOR=${BASE_PLUGIN_ROOT}/patch/platform/patch_kv_cache_coordinator.py
BASE_ASCEND_INTERFACE=${BASE_PLUGIN_ROOT}/patch/platform/patch_kv_cache_interface.py
MODEL_PATH=${MODEL_PATH:-/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp}
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-deepseek-v4-flash-w8a8-mtp}
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-7000}
REQUEST_RUNNER=${REQUEST_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_scheduler_pressure.py}
ARGV_IDENTITY=${ARGV_IDENTITY:-${SCRIPT_DIR}/canonicalize_server_argv.py}
MTP_PATCH=${MTP_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch}
OBSERVER=${OBSERVER:-${SCRIPT_DIR}/p6_3c_r1_scheduler_observer.py}
OBSERVER_PATCH=${OBSERVER_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch}
STARTUP_SUMMARY_RUNNER=${STARTUP_SUMMARY_RUNNER:-${SCRIPT_DIR}/p6_3c_startup_resource_summary.py}
RUNTIME_IMPL=${RUNTIME_IMPL:-${SCRIPT_DIR}/p6_3b_r1_hybrid_kv_runtime_patch.py}
RUNTIME_LOADER=${RUNTIME_LOADER:-${SCRIPT_DIR}/p6_3b_r2_hybrid_kv_runtime_patch.py}
HYBRID_PATCH=${HYBRID_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch}
DEFERRED_PATCH=${DEFERRED_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch}
EXPERIMENT_LABEL=${P6_3C_EXPERIMENT_LABEL:-P6_3C_R1}
MAX_MODEL_LEN=${P6_3C_MAX_MODEL_LEN:-69632}
MAX_NUM_BATCHED_TOKENS=${P6_3C_MAX_NUM_BATCHED_TOKENS:-69632}
MAX_NUM_SEQS=${P6_3C_MAX_NUM_SEQS:-2}
SHARED_HYBRID_KV_REPAIR=${P6_3C_SHARED_HYBRID_KV_REPAIR:-0}
LIFECYCLE_DIR=${ARTIFACT_DIR}/lifecycles/${LIFECYCLE_ID}
RUNTIME_DIR=${LIFECYCLE_DIR}/runtime
OVERLAY_ROOT=${RUNTIME_DIR}/overlay_root
TRACE_DIR=${RUNTIME_DIR}/scheduler_trace
HYBRID_DIAGNOSTIC_PATH=${RUNTIME_DIR}/hybrid_kv_runtime_diagnostic.jsonl
server_pid=

cmd=(
  "${VLLM_BIN}" serve "${MODEL_PATH}"
  --safetensors-load-strategy prefetch
  --max-model-len "${MAX_MODEL_LEN}"
  --max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS}"
  --served-model-name "${SERVED_MODEL_NAME}"
  --gpu-memory-utilization 0.92
  --max-num-seqs "${MAX_NUM_SEQS}"
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
  printf 'experiment_label=%s\n' "${EXPERIMENT_LABEL}"
  printf 'track=%s\n' "${TRACK}"
  printf 'mode=%s\n' "${MODE}"
  printf 'max_model_len=%s\n' "${MAX_MODEL_LEN}"
  printf 'max_num_batched_tokens=%s\n' "${MAX_NUM_BATCHED_TOKENS}"
  printf 'max_num_seqs=%s\n' "${MAX_NUM_SEQS}"
  printf 'prefix_cache=false\n'
  printf 'shared_hybrid_kv_repair=%s\n' "${SHARED_HYBRID_KV_REPAIR}"
  printf 'observer=%s\n' "$([ "${TRACK}" = mechanism ] && printf enabled || printf disabled)"
  printf 'profiler=disabled\n'
  printf 'request_retry_count=0\n'
  "${PYTHON_BIN}" "${ARGV_IDENTITY}" -- "${cmd[@]}" |
    sed 's/^/server_argv_sha256=/'
}

if test "${P6_3C_MODE_AUDIT_ONLY:-${P6_3C_R1_MODE_AUDIT_ONLY:-0}}" = 1; then
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
test -f "${STARTUP_SUMMARY_RUNNER}"
test -f "${BASE_PROPOSER}"
test -f "${BASE_CONNECTOR_INIT}"
test -f "${BASE_SCHEDULER}"
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = \
  0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
test "$(sha256sum "${BASE_CONNECTOR_INIT}" | awk '{print $1}')" = \
  dc693fd52eb44921e731b69021388ecc186f4e5fa5eca3b28fc1963661e355d1
test "$(sha256sum "${BASE_SCHEDULER}" | awk '{print $1}')" = \
  41ff2e524c90d9aa72b72cd77492eb62ee2a729a773bd8233e970f39abbb5983
case "${SHARED_HYBRID_KV_REPAIR}" in
  0) ;;
  1)
    test -f "${RUNTIME_IMPL}"
    test -f "${RUNTIME_LOADER}"
    test -f "${HYBRID_PATCH}"
    test -f "${DEFERRED_PATCH}"
    test "$(sha256sum "${BASE_VLLM_SINGLE}" | awk '{print $1}')" = \
      d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1
    test "$(sha256sum "${BASE_VLLM_COORDINATOR}" | awk '{print $1}')" = \
      a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89
    test "$(sha256sum "${BASE_ASCEND_COORDINATOR}" | awk '{print $1}')" = \
      dc65ed2adbb05ea52d9e891f648b62a5391eb41b2a6b262b71d40efe31effe20
    test "$(sha256sum "${BASE_ASCEND_INTERFACE}" | awk '{print $1}')" = \
      a4969e2c1b2ebde9a3c5a4d02df5175879fb56ea43322869871a3868ec1981b2
    ;;
  *) echo "unsupported shared hybrid-KV repair control" >&2; exit 64 ;;
esac

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

if test "${SHARED_HYBRID_KV_REPAIR}" = 1; then
  cp "${RUNTIME_IMPL}" "${OVERLAY_ROOT}/p6_3b_hybrid_kv_runtime_impl.py"
  cp "${RUNTIME_LOADER}" "${OVERLAY_ROOT}/p6_3b_r2_hybrid_kv_runtime_patch.py"
  patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${HYBRID_PATCH}" \
    > "${RUNTIME_DIR}/hybrid_patch_dry_run.txt"
  patch -p1 -d "${OVERLAY_ROOT}" < "${HYBRID_PATCH}" \
    > "${RUNTIME_DIR}/hybrid_patch_apply.txt"
  if patch -l -p1 -d "${OVERLAY_ROOT}" --dry-run < "${DEFERRED_PATCH}" \
    > "${RUNTIME_DIR}/deferred_patch_dry_run.txt" 2>&1; then
    patch -l -p1 -d "${OVERLAY_ROOT}" < "${DEFERRED_PATCH}" \
      > "${RUNTIME_DIR}/deferred_patch_apply.txt"
    printf '%s\n' patch_l > "${RUNTIME_DIR}/deferred_patch_method.txt"
  else
    (
      cd "${OVERLAY_ROOT}"
      GIT_DIR=/dev/null git apply --check --ignore-whitespace "${DEFERRED_PATCH}"
      GIT_DIR=/dev/null git apply --ignore-whitespace "${DEFERRED_PATCH}"
    ) > "${RUNTIME_DIR}/deferred_patch_apply.txt" 2>&1
    printf '%s\n' git_apply_ignore_whitespace \
      > "${RUNTIME_DIR}/deferred_patch_method.txt"
  fi
  test "$(sha256sum "${OVERLAY_ROOT}/vllm_ascend/patch/platform/patch_kv_cache_coordinator.py" | awk '{print $1}')" = \
    a1ed9c82e308608cd20965a49baa29a3e95d723248fff699fd83dfb3caf10250
  test "$(sha256sum "${OVERLAY_ROOT}/vllm_ascend/patch/platform/patch_kv_cache_interface.py" | awk '{print $1}')" = \
    524c933ef17806ecba0634804bc562de1f69dc095fe1346e2edd0103845bfa75
  {
    printf 'runtime_impl\t%s\n' "$(sha256sum "${RUNTIME_IMPL}" | awk '{print $1}')"
    printf 'deferred_loader\t%s\n' "$(sha256sum "${RUNTIME_LOADER}" | awk '{print $1}')"
    printf 'hybrid_patch\t%s\n' "$(sha256sum "${HYBRID_PATCH}" | awk '{print $1}')"
    printf 'deferred_patch\t%s\n' "$(sha256sum "${DEFERRED_PATCH}" | awk '{print $1}')"
    printf 'overlay_ascend_coordinator\t%s\n' \
      "$(sha256sum "${OVERLAY_ROOT}/vllm_ascend/patch/platform/patch_kv_cache_coordinator.py" | awk '{print $1}')"
    printf 'overlay_ascend_interface\t%s\n' \
      "$(sha256sum "${OVERLAY_ROOT}/vllm_ascend/patch/platform/patch_kv_cache_interface.py" | awk '{print $1}')"
  } > "${LIFECYCLE_DIR}/repair_identity.tsv"
else
  printf 'shared_hybrid_kv_repair\tdisabled\n' \
    > "${LIFECYCLE_DIR}/repair_identity.tsv"
fi

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
if test -v VLLM_PREFIX_CACHE_RETENTION_INTERVAL; then
  printf '%s\n' set > "${RUNTIME_DIR}/inherited_retention_interval_presence.txt"
else
  printf '%s\n' unset > "${RUNTIME_DIR}/inherited_retention_interval_presence.txt"
fi
unset VLLM_PREFIX_CACHE_RETENTION_INTERVAL
printf '%s\n' explicitly_unset > "${RUNTIME_DIR}/effective_retention_interval.txt"

if test "${SHARED_HYBRID_KV_REPAIR}" = 1; then
  if ! P6_3B_R2_ENABLE_HYBRID_KV_PATCH=1 \
    P6_3B_R2_HYBRID_KV_DIAGNOSTIC_PATH="${HYBRID_DIAGNOSTIC_PATH}" \
    "${PYTHON_BIN}" -c \
    'import vllm_ascend.patch.platform.patch_kv_cache_interface; import p6_3b_r2_hybrid_kv_runtime_patch as patch; assert patch.PATCH_INSTALLED; assert all(patch.require_ascend_manager_resolution().values())' \
    > "${RUNTIME_DIR}/hybrid_kv_runtime_patch_self_test.txt" 2>&1; then
    {
      printf '%s\n' "${LIFECYCLE_ID}:hybrid_kv_runtime_patch_self_test_failed"
      tail -c 4096 "${RUNTIME_DIR}/hybrid_kv_runtime_patch_self_test.txt"
    } > "${ARTIFACT_DIR}/first_failure_excerpt.txt"
    exit 2
  fi
fi

if test "${TRACK}" = mechanism; then
  export P6_3C_R1_SCHEDULER_TRACE_DIR="${TRACE_DIR}"
  if ! "${PYTHON_BIN}" - <<'PY' > "${RUNTIME_DIR}/observer_self_test.txt" 2>&1
from vllm_ascend.distributed.kv_transfer import register_connector
register_connector()
from vllm.v1.core.sched.scheduler import Scheduler
assert Scheduler._p6_3c_r1_observer_installed is True
print("pass")
PY
  then
    {
      printf '%s\n' "${LIFECYCLE_ID}:observer_self_test_failed"
      tail -c 4096 "${RUNTIME_DIR}/observer_self_test.txt"
    } > "${ARTIFACT_DIR}/first_failure_excerpt.txt"
    exit 2
  fi
else
  unset P6_3C_R1_SCHEDULER_TRACE_DIR
fi

printf '%q ' "${cmd[@]}" > "${RUNTIME_DIR}/server_command.txt"
printf '\n' >> "${RUNTIME_DIR}/server_command.txt"
"${PYTHON_BIN}" "${ARGV_IDENTITY}" \
  --output "${RUNTIME_DIR}/server_argv.json" -- "${cmd[@]}" \
  > "${RUNTIME_DIR}/server_argv_sha256.txt"

if test "${SHARED_HYBRID_KV_REPAIR}" = 1; then
  P6_3B_R2_ENABLE_HYBRID_KV_PATCH=1 \
  P6_3B_R2_HYBRID_KV_DIAGNOSTIC_PATH="${HYBRID_DIAGNOSTIC_PATH}" \
    setsid "${cmd[@]}" > "${RUNTIME_DIR}/vllm_server.log" 2>&1 &
else
  setsid "${cmd[@]}" > "${RUNTIME_DIR}/vllm_server.log" 2>&1 &
fi
server_pid=$!
printf '%s\n' "${server_pid}" > "${RUNTIME_DIR}/server_pid.txt"

"${PYTHON_BIN}" - \
  "${MODE}" "${TRACK}" \
  "${MAX_MODEL_LEN}" "${MAX_NUM_BATCHED_TOKENS}" "${MAX_NUM_SEQS}" \
  "${SHARED_HYBRID_KV_REPAIR}" \
  "${RUNTIME_DIR}/server_command.txt" \
  "/proc/${server_pid}/cmdline" \
  "${RUNTIME_DIR}/resolved_scheduler_config.json" <<'PY'
import json
import shlex
import sys
import time
from pathlib import Path

(
    mode,
    track,
    expected_max_model_len,
    expected_max_num_batched_tokens,
    expected_max_num_seqs,
    shared_hybrid_kv_repair,
    command_path,
    process_path,
    output_path,
) = sys.argv[1:]
expected_max_model_len = int(expected_max_model_len)
expected_max_num_batched_tokens = int(expected_max_num_batched_tokens)
expected_max_num_seqs = int(expected_max_num_seqs)
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
    "shared_hybrid_kv_repair_enabled": shared_hybrid_kv_repair == "1",
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
assert evidence["max_model_len"] == expected_max_model_len
assert evidence["max_num_batched_tokens"] == expected_max_num_batched_tokens
assert evidence["max_num_seqs"] == expected_max_num_seqs
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
"${PYTHON_BIN}" "${STARTUP_SUMMARY_RUNNER}" \
  --log "${RUNTIME_DIR}/vllm_server.log" \
  --output "${RUNTIME_DIR}/startup_resource_summary.json" \
  --failure-excerpt "${LIFECYCLE_DIR}/startup_failure_excerpt.txt" \
  --expected-max-model-len "${MAX_MODEL_LEN}" \
  --expected-max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS}" \
  --expected-max-num-seqs "${MAX_NUM_SEQS}" \
  --server-ready-exit-code "${ready_exit}"
if test "${ready_exit}" -ne 0; then
  {
    printf '%s\n' "${LIFECYCLE_ID}:server_not_ready"
    cat "${LIFECYCLE_DIR}/startup_failure_excerpt.txt"
  } > "${ARTIFACT_DIR}/first_failure_excerpt.txt"
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
