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
VLLM_BIN=${VLLM_BIN:-${ENV_PREFIX}/bin/vllm}
BASE_PLUGIN_ROOT=${BASE_PLUGIN_ROOT:-${ENV_PREFIX}/lib/python3.11/site-packages/vllm_ascend}
BASE_VLLM_ROOT=${BASE_VLLM_ROOT:-${ENV_PREFIX}/lib/python3.11/site-packages/vllm}
BASE_PROPOSER=${BASE_PROPOSER:-${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py}
BASE_VLLM_SINGLE=${BASE_VLLM_ROOT}/v1/core/single_type_kv_cache_manager.py
BASE_VLLM_COORDINATOR=${BASE_VLLM_ROOT}/v1/core/kv_cache_coordinator.py
BASE_ASCEND_COORDINATOR=${BASE_PLUGIN_ROOT}/patch/platform/patch_kv_cache_coordinator.py
BASE_ASCEND_INTERFACE=${BASE_PLUGIN_ROOT}/patch/platform/patch_kv_cache_interface.py
MODEL_PATH=${MODEL_PATH:-/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp}
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-deepseek-v4-flash-w8a8-mtp}
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-7000}
SOURCE_PAYLOAD=${SOURCE_PAYLOAD:-${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json}
RUNTIME_IMPL=${RUNTIME_IMPL:-${REPO_ROOT}/tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py}
RUNTIME_LOADER=${RUNTIME_LOADER:-${REPO_ROOT}/tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py}
MTP_PATCH=${MTP_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch}
HYBRID_PATCH=${HYBRID_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch}
DEFERRED_PATCH=${DEFERRED_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch}
BASELINE_CONTRACT=${BASELINE_CONTRACT:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/p8/p8_official_mtp_observe_matrix_contract.yaml}
WORKLOAD=${WORKLOAD:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p8_1_r1_vllm_ascend_official_mtp_observe_only_matrix.yaml}
PREPARER=${PREPARER:-${REPO_ROOT}/tools/inference_contracts/prepare_deepseek_p8_1_r1_observe_matrix.py}
FINALIZER=${FINALIZER:-${REPO_ROOT}/tools/inference_contracts/finalize_deepseek_p8_1_r1_observe_only_matrix.py}
RUNTIME_DIR=${RESULT_DIR}/runtime
PREPARED_DIR=${RESULT_DIR}/prepared_requests
SLOT_ROOT=${RESULT_DIR}/request_slots
OVERLAY_ROOT=${RUNTIME_DIR}/overlay_root
DIAGNOSTIC_PATH=${RUNTIME_DIR}/hybrid_kv_runtime_diagnostic.jsonl
TRACE_ID=trace_p8_matrix_0001
SESSION_ID=session_p8_matrix_0001
EXPECTED_SERVER_COMMAND_SHA256=370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19
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

if test "${P8_1_R1_AUDIT_ONLY:-0}" = 1; then
  printf '%q ' "${cmd[@]}"
  printf '\n'
  exit 0
fi

cd "${REPO_ROOT}"

if test -e "${RESULT_DIR}"; then
  echo "result directory already exists: ${RESULT_DIR}" >&2
  exit 65
fi
mkdir -p "${RUNTIME_DIR}" "${SLOT_ROOT}"

stop_server() {
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
}
trap stop_server EXIT

test "$(sha256sum "${SOURCE_PAYLOAD}" | awk '{print $1}')" = 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
test "$(stat -c '%s' "${SOURCE_PAYLOAD}")" = 19487
test "$(git -C /data/node0_disk1/vllm-0.22.1 rev-parse HEAD)" = 0decac0d96c42b49572498019f0a0e3600f50398

"${PYTHON_BIN}" "${PREPARER}" \
  --source-payload "${SOURCE_PAYLOAD}" \
  --output-dir "${PREPARED_DIR}" \
  --model-name "${SERVED_MODEL_NAME}" \
  > "${RUNTIME_DIR}/preparer_stdout.json"

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
CANN_GENERATED_PYTHONPATH=${PYTHONPATH:-}

mkdir -p "${OVERLAY_ROOT}"
cp -a --no-preserve=ownership "${BASE_PLUGIN_ROOT}" "${OVERLAY_ROOT}/vllm_ascend"
cp "${RUNTIME_IMPL}" "${OVERLAY_ROOT}/p6_3b_hybrid_kv_runtime_impl.py"
cp "${RUNTIME_LOADER}" "${OVERLAY_ROOT}/p6_3b_r2_hybrid_kv_runtime_patch.py"
OVERLAY_PROPOSER=${OVERLAY_ROOT}/vllm_ascend/spec_decode/llm_base_proposer.py
OVERLAY_ASCEND_COORDINATOR=${OVERLAY_ROOT}/vllm_ascend/patch/platform/patch_kv_cache_coordinator.py
OVERLAY_ASCEND_INTERFACE=${OVERLAY_ROOT}/vllm_ascend/patch/platform/patch_kv_cache_interface.py

test "$(stat -c '%s' "${BASE_VLLM_SINGLE}")" = 53714
test "$(sha256sum "${BASE_VLLM_SINGLE}" | awk '{print $1}')" = d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1
test "$(stat -c '%s' "${BASE_VLLM_COORDINATOR}")" = 25255
test "$(sha256sum "${BASE_VLLM_COORDINATOR}" | awk '{print $1}')" = a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89
test "$(stat -c '%s' "${BASE_ASCEND_COORDINATOR}")" = 23103
test "$(sha256sum "${BASE_ASCEND_COORDINATOR}" | awk '{print $1}')" = dc65ed2adbb05ea52d9e891f648b62a5391eb41b2a6b262b71d40efe31effe20
test "$(stat -c '%s' "${BASE_ASCEND_INTERFACE}")" = 11819
test "$(sha256sum "${BASE_ASCEND_INTERFACE}" | awk '{print $1}')" = a4969e2c1b2ebde9a3c5a4d02df5175879fb56ea43322869871a3868ec1981b2
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
test "$(sha256sum "${RUNTIME_IMPL}" | awk '{print $1}')" = 6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c
test "$(sha256sum "${RUNTIME_LOADER}" | awk '{print $1}')" = 9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631
test "$(sha256sum "${MTP_PATCH}" | awk '{print $1}')" = 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
test "$(sha256sum "${HYBRID_PATCH}" | awk '{print $1}')" = cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e
test "$(sha256sum "${DEFERRED_PATCH}" | awk '{print $1}')" = ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b

patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${MTP_PATCH}" > "${RUNTIME_DIR}/mtp_patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${MTP_PATCH}" > "${RUNTIME_DIR}/mtp_patch_apply.txt"
patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${HYBRID_PATCH}" > "${RUNTIME_DIR}/hybrid_patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${HYBRID_PATCH}" > "${RUNTIME_DIR}/hybrid_patch_apply.txt"
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
test "$(sha256sum "${OVERLAY_PROPOSER}" | awk '{print $1}')" = 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
test "$(sha256sum "${OVERLAY_ASCEND_COORDINATOR}" | awk '{print $1}')" = a1ed9c82e308608cd20965a49baa29a3e95d723248fff699fd83dfb3caf10250
test "$(sha256sum "${OVERLAY_ASCEND_INTERFACE}" | awk '{print $1}')" = 524c933ef17806ecba0634804bc562de1f69dc095fe1346e2edd0103845bfa75

"${PYTHON_BIN}" - "${RUNTIME_DIR}/repair_identity.json" <<'PY'
import json
import pathlib
import sys

identity = {
    "runtime_impl": "6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c",
    "deferred_loader": "9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631",
    "mtp_patch": "75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1",
    "hybrid_patch": "cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e",
    "deferred_patch": "ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b",
    "overlay_proposer": "7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02",
    "overlay_ascend_coordinator": "a1ed9c82e308608cd20965a49baa29a3e95d723248fff699fd83dfb3caf10250",
    "overlay_ascend_interface": "524c933ef17806ecba0634804bc562de1f69dc095fe1346e2edd0103845bfa75",
}
pathlib.Path(sys.argv[1]).write_text(
    json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

export PYTHONPATH="${OVERLAY_ROOT}:${CANN_GENERATED_PYTHONPATH}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
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
unset VLLM_PREFIX_CACHE_RETENTION_INTERVAL
printf '%s\n' explicitly_unset > "${RUNTIME_DIR}/effective_retention_interval.txt"
export P6_3B_R2_ENABLE_HYBRID_KV_PATCH=1
export P6_3B_R2_HYBRID_KV_DIAGNOSTIC_PATH="${DIAGNOSTIC_PATH}"

"${PYTHON_BIN}" -c 'import vllm_ascend.patch.platform.patch_kv_cache_interface; import p6_3b_r2_hybrid_kv_runtime_patch as patch; assert patch.PATCH_INSTALLED; assert all(patch.require_ascend_manager_resolution().values())' \
  > "${RUNTIME_DIR}/runtime_patch_self_test.txt" 2>&1
printf '%s\n' pass > "${RUNTIME_DIR}/source_gate_status.txt"

printf '%q ' "${cmd[@]}" > "${RUNTIME_DIR}/server_command.txt"
printf '\n' >> "${RUNTIME_DIR}/server_command.txt"
test "$(sha256sum "${RUNTIME_DIR}/server_command.txt" | awk '{print $1}')" = "${EXPECTED_SERVER_COMMAND_SHA256}"

"${PYTHON_BIN}" - "${RESULT_DIR}" "${BASELINE_CONTRACT}" "${WORKLOAD}" "${PREPARER}" "${FINALIZER}" <<'PY'
import hashlib
import importlib.metadata
import json
import pathlib
import sys

artifact_dir = pathlib.Path(sys.argv[1])
baseline = pathlib.Path(sys.argv[2])
workload = pathlib.Path(sys.argv[3])
preparer = pathlib.Path(sys.argv[4])
finalizer = pathlib.Path(sys.argv[5])

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

record = {
    "task_id": "p8_1_r1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0717",
    "parent_task_id": "p8_1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0716",
    "vllm": importlib.metadata.version("vllm"),
    "vllm_ascend": importlib.metadata.version("vllm-ascend"),
    "vllm_commit": "0decac0d96c42b49572498019f0a0e3600f50398",
    "vllm_ascend_commit": "5f6faa0cb8830f667266f3b8121cd1383606f2a1",
    "baseline_contract_sha256": digest(baseline),
    "workload_sha256": digest(workload),
    "preparer_sha256": digest(preparer),
    "finalizer_sha256": digest(finalizer),
    "generated_content_retained": False,
    "generated_token_ids_retained": False,
    "request_bodies_remain_server_local": True,
}
(artifact_dir / "environment_and_hashes.json").write_text(
    json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

setsid "${cmd[@]}" > "${RUNTIME_DIR}/vllm_server.log" 2>&1 &
server_pid=$!
printf '%s\n' "${server_pid}" > "${RUNTIME_DIR}/server_pid.txt"
"${PYTHON_BIN}" - \
  "${RUNTIME_DIR}/server_command.txt" \
  "/proc/${server_pid}/cmdline" \
  "${RUNTIME_DIR}/resolved_prefix_cache_config.json" <<'PY'
import json
import shlex
import sys
import time
from pathlib import Path

command_path, process_path, output_path = sys.argv[1:]
expected_flag = "--enable-prefix-caching"
opposite_flag = "--no-enable-prefix-caching"
server_args = shlex.split(Path(command_path).read_text(encoding="utf-8"))
process_args = []
for _ in range(100):
    process_args = [
        value.decode("utf-8", errors="replace")
        for value in Path(process_path).read_bytes().split(b"\0")
        if value
    ]
    if expected_flag in process_args:
        break
    time.sleep(0.05)
evidence = {
    "resolved_enable_prefix_caching": True,
    "resolution_basis": "explicit_cli_flag_and_live_process_cmdline",
    "server_command_has_expected_flag": expected_flag in server_args,
    "process_cmdline_has_expected_flag": expected_flag in process_args,
    "opposite_flag_absent": (
        opposite_flag not in server_args and opposite_flag not in process_args
    ),
}
Path(output_path).write_text(
    json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
assert all(
    evidence[key]
    for key in (
        "resolved_enable_prefix_caching",
        "server_command_has_expected_flag",
        "process_cmdline_has_expected_flag",
        "opposite_flag_absent",
    )
)
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
  printf '%s\n' 'red_p8_1_r1_server_not_ready' > "${RESULT_DIR}/first_failure_excerpt.txt"
  exit 2
fi

curl -fsS "http://${HOST}:${PORT}/metrics" > "${RUNTIME_DIR}/metrics_preflight.prom"
for metric in \
  vllm:prefix_cache_queries \
  vllm:prefix_cache_hits \
  vllm:spec_decode_num_drafts_total \
  vllm:spec_decode_num_draft_tokens_total \
  vllm:spec_decode_num_accepted_tokens_total \
  vllm:num_requests_running \
  vllm:num_requests_waiting
do
  grep -F "${metric}" "${RUNTIME_DIR}/metrics_preflight.prom" >/dev/null
done

: > "${RESULT_DIR}/runtime_observations.jsonl"
completed_requests=0
while IFS=$'\t' read -r slot_id request_id input_tokens expected_hits body_path; do
  slot_dir=${SLOT_ROOT}/${slot_id}
  mkdir -p "${slot_dir}"
  test "${expected_hits}" -ge 0
  if curl -fsS --max-time 5 "http://${HOST}:${PORT}/health" >/dev/null; then
    printf '%s\n' true > "${slot_dir}/health_before.txt"
  else
    printf '%s\n' false > "${slot_dir}/health_before.txt"
    printf 'slot=%s health_before=false\n' "${slot_id}" > "${RESULT_DIR}/first_failure_excerpt.txt"
    exit 3
  fi
  curl -fsS "http://${HOST}:${PORT}/metrics" > "${slot_dir}/metrics_before.prom"
  if ! "${PYTHON_BIN}" -m tools.ak_state_runtime.cli collect-vllm-ascend-observations \
    --endpoint "http://${HOST}:${PORT}/v1/completions" \
    --metrics-url "http://${HOST}:${PORT}/metrics" \
    --request-payload "${body_path}" \
    --observations-output "${slot_dir}/runtime_observations.jsonl" \
    --request-result-output "${slot_dir}/request_result.json" \
    --metrics-output "${slot_dir}/prefix_cache_metrics.json" \
    --transfer-availability-output "${slot_dir}/transfer_availability.json" \
    --expected-prompt-tokens "${input_tokens}" \
    --trace-id trace_p8_matrix_0001 \
    --request-id "${request_id}" \
    --session-id session_p8_matrix_0001 \
    --timeout-seconds 7200 \
    --metrics-settle-seconds 15 \
    > "${slot_dir}/collector_stdout.json"
  then
    printf 'slot=%s collector_failed_no_retry\n' "${slot_id}" > "${RESULT_DIR}/first_failure_excerpt.txt"
    exit 4
  fi
  curl -fsS "http://${HOST}:${PORT}/metrics" > "${slot_dir}/metrics_after.prom"
  if curl -fsS --max-time 5 "http://${HOST}:${PORT}/health" >/dev/null; then
    printf '%s\n' true > "${slot_dir}/health_after.txt"
  else
    printf '%s\n' false > "${slot_dir}/health_after.txt"
    printf 'slot=%s health_after=false\n' "${slot_id}" > "${RESULT_DIR}/first_failure_excerpt.txt"
    exit 5
  fi
  cat "${slot_dir}/runtime_observations.jsonl" >> "${RESULT_DIR}/runtime_observations.jsonl"
  completed_requests=$((completed_requests + 1))
done < <(
  "${PYTHON_BIN}" - "${PREPARED_DIR}/request_body_manifest.json" "${PREPARED_DIR}" <<'PY'
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
prepared_dir = pathlib.Path(sys.argv[2])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
for row in manifest["records"]:
    print(
        row["slot_id"],
        row["request_id"],
        row["input_tokens"],
        row["expected_prefix_hit_tokens"],
        prepared_dir / row["body_relative_path"],
        sep="\t",
    )
PY
)
test "${completed_requests}" -eq 6

"${PYTHON_BIN}" - "${RESULT_DIR}" <<'PY'
import json
import math
import pathlib
import re
import sys

artifact_dir = pathlib.Path(sys.argv[1])
manifest = json.loads(
    (artifact_dir / "prepared_requests/request_body_manifest.json").read_text(encoding="utf-8")
)
metric_names = {
    "vllm:spec_decode_num_drafts_total": "num_drafts",
    "vllm:spec_decode_num_draft_tokens_total": "num_draft_tokens",
    "vllm:spec_decode_num_accepted_tokens_total": "num_accepted_tokens",
    "vllm:num_requests_running": "running",
    "vllm:num_requests_waiting": "waiting",
}
pattern = re.compile(r"^([^\s{]+)(?:\{[^}]*\})?\s+([-+0-9.eE]+)(?:\s+\d+)?$")

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def parse_metrics(path):
    values = {key: 0.0 for key in metric_names.values()}
    counts = {key: 0 for key in metric_names.values()}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match is None or match.group(1) not in metric_names:
            continue
        key = metric_names[match.group(1)]
        value = float(match.group(2))
        if not math.isfinite(value):
            raise SystemExit(f"non-finite metric: {line}")
        values[key] += value
        counts[key] += 1
    if any(count == 0 for count in counts.values()):
        raise SystemExit(f"missing matrix metric in {path}")
    return values

request_rows = []
prefix_rows = []
mtp_rows = []
queue_rows = []
transfer_rows = []
for plan in manifest["records"]:
    slot_id = plan["slot_id"]
    slot_dir = artifact_dir / "request_slots" / slot_id
    request = load_json(slot_dir / "request_result.json")
    request.update(
        {
            "slot_id": slot_id,
            "request_id": plan["request_id"],
            "input_tokens_expected": plan["input_tokens"],
            "request_body_sha256": plan["request_body_sha256"],
        }
    )
    request_rows.append(request)
    prefix = load_json(slot_dir / "prefix_cache_metrics.json")
    prefix_rows.append(
        {
            "slot_id": slot_id,
            "request_id": plan["request_id"],
            "expected_hits": plan["expected_prefix_hit_tokens"],
            "delta": prefix["delta"],
        }
    )
    before = parse_metrics(slot_dir / "metrics_before.prom")
    after = parse_metrics(slot_dir / "metrics_after.prom")
    delta = {
        key: after[key] - before[key]
        for key in ("num_drafts", "num_draft_tokens", "num_accepted_tokens")
    }
    mtp_rows.append(
        {
            "slot_id": slot_id,
            "request_id": plan["request_id"],
            "before": {key: before[key] for key in delta},
            "after": {key: after[key] for key in delta},
            "delta": delta,
            "counter_continuity": all(after[key] >= before[key] for key in delta),
        }
    )
    queue_rows.append(
        {
            "slot_id": slot_id,
            "request_id": plan["request_id"],
            "health_before": (slot_dir / "health_before.txt").read_text().strip() == "true",
            "health_after": (slot_dir / "health_after.txt").read_text().strip() == "true",
            "running_before": before["running"],
            "waiting_before": before["waiting"],
            "running_after": after["running"],
            "waiting_after": after["waiting"],
        }
    )
    transfer = load_json(slot_dir / "transfer_availability.json")
    transfer.update({"slot_id": slot_id, "request_id": plan["request_id"]})
    transfer_rows.append(transfer)

outputs = {
    "request_matrix_summary.json": {
        "request_count": len(request_rows),
        "requests": request_rows,
        "claim_boundary": "request_correctness_and_trace_order_only_not_performance",
    },
    "prefix_cache_metrics_summary.json": {
        "request_count": len(prefix_rows),
        "requests": prefix_rows,
        "claim_boundary": "token_counter_proxy_only_not_object_bytes_or_performance",
    },
    "mtp_metrics_summary.json": {
        "request_count": len(mtp_rows),
        "requests": mtp_rows,
        "claim_boundary": "per_request_mtp_activity_continuity_only",
    },
    "queue_health_summary.json": {
        "request_count": len(queue_rows),
        "requests": queue_rows,
    },
    "transfer_availability_summary.json": {
        "request_count": len(transfer_rows),
        "requests": transfer_rows,
        "synthetic_transfer_forbidden": True,
    },
}
for name, record in outputs.items():
    (artifact_dir / name).write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
PY

"${PYTHON_BIN}" -m tools.ak_state_runtime.cli build-vllm-ascend-observe-bundle \
  --source "${RESULT_DIR}/runtime_observations.jsonl" \
  --output "${RESULT_DIR}/observe_only_bundle" \
  --baseline-contract "${BASELINE_CONTRACT}" \
  --model-id deepseek-ai/DeepSeek-V4-Flash-w8a8-mtp \
  > "${RUNTIME_DIR}/bundle_stdout.json"

"${PYTHON_BIN}" -m tools.ak_state_runtime.cli build-vllm-ascend-observe-bundle \
  --source "${RESULT_DIR}/runtime_observations.jsonl" \
  --output "${RESULT_DIR}/observe_only_replay_bundle" \
  --baseline-contract "${BASELINE_CONTRACT}" \
  --model-id deepseek-ai/DeepSeek-V4-Flash-w8a8-mtp \
  > "${RUNTIME_DIR}/replay_bundle_stdout.json"

"${PYTHON_BIN}" - "${RESULT_DIR}" <<'PY'
import hashlib
import json
import pathlib
import sys

artifact_dir = pathlib.Path(sys.argv[1])
first = artifact_dir / "observe_only_bundle"
second = artifact_dir / "observe_only_replay_bundle"
first_files = {path.relative_to(first).as_posix(): path for path in first.rglob("*") if path.is_file()}
second_files = {path.relative_to(second).as_posix(): path for path in second.rglob("*") if path.is_file()}
names = sorted(set(first_files) | set(second_files))
mismatches = []
hashes = {}
for name in names:
    left = first_files.get(name)
    right = second_files.get(name)
    left_hash = hashlib.sha256(left.read_bytes()).hexdigest() if left else None
    right_hash = hashlib.sha256(right.read_bytes()).hexdigest() if right else None
    hashes[name] = {"first": left_hash, "replay": right_hash}
    if left_hash != right_hash:
        mismatches.append(name)
record = {
    "deterministic": not mismatches and set(first_files) == set(second_files),
    "compared_file_count": len(names),
    "mismatches": mismatches,
    "file_hashes": hashes,
    "claim_boundary": "same_source_same_contract_offline_replay_determinism",
}
(artifact_dir / "replay_determinism.json").write_text(
    json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

stop_server
trap - EXIT
set +e
"${PYTHON_BIN}" "${FINALIZER}" --artifact-dir "${RESULT_DIR}" > "${RUNTIME_DIR}/finalizer_stdout.json"
finalizer_exit=$?
set -e

candidate_files=(
  result_summary.md
  environment_and_hashes.json
  body_relationship_summary.json
  repair_diagnostic_summary.json
  request_matrix_summary.json
  prefix_cache_metrics_summary.json
  mtp_metrics_summary.json
  queue_health_summary.json
  transfer_availability_summary.json
  replay_determinism.json
  join_coverage.json
  trace_summary.json
  grading_inputs.json
  cleanup_status.txt
  first_failure_excerpt.txt
)
printf 'path\tbytes\tsha256\tsensitivity\n' > "${RESULT_DIR}/delivery_candidates.tsv"
candidate_total=0
for relative_path in "${candidate_files[@]}"; do
  bytes=$(stat -c '%s' "${RESULT_DIR}/${relative_path}")
  digest=$(sha256sum "${RESULT_DIR}/${relative_path}" | awk '{print $1}')
  printf '%s\t%s\t%s\t%s\n' "${relative_path}" "${bytes}" "${digest}" operational_metadata >> "${RESULT_DIR}/delivery_candidates.tsv"
  candidate_total=$((candidate_total + bytes))
done
test "${candidate_total}" -le 71680
printf '%s\n' "${candidate_total}" > "${RESULT_DIR}/candidate_total_bytes.txt"
exit "${finalizer_exit}"
