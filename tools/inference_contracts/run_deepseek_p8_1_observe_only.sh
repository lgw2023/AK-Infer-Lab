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
BASE_PROPOSER=${BASE_PROPOSER:-${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py}
MODEL_PATH=${MODEL_PATH:-/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp}
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-deepseek-v4-flash-w8a8-mtp}
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-7000}
SOURCE_PAYLOAD=${SOURCE_PAYLOAD:-${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json}
PATCH_PATH=${PATCH_PATH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch}
BASELINE_CONTRACT=${BASELINE_CONTRACT:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/p8/p8_official_mtp_baseline_contract.yaml}
FINALIZER=${FINALIZER:-${REPO_ROOT}/tools/inference_contracts/finalize_deepseek_p8_1_observe_only.py}
RUNTIME_DIR=${RESULT_DIR}/runtime
OVERLAY_ROOT=${RUNTIME_DIR}/overlay_root
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

if test "${P8_1_AUDIT_ONLY:-0}" = 1; then
  printf '%q ' "${cmd[@]}"
  printf '\n'
  exit 0
fi

if test -e "${RESULT_DIR}"; then
  echo "result directory already exists: ${RESULT_DIR}" >&2
  exit 65
fi
mkdir -p "${RUNTIME_DIR}"

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
test "$(sha256sum "${PATCH_PATH}" | awk '{print $1}')" = 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
test "$(git -C /data/node0_disk1/vllm-0.22.1 rev-parse HEAD)" = 0decac0d96c42b49572498019f0a0e3600f50398

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
CANN_GENERATED_PYTHONPATH=${PYTHONPATH:-}

mkdir -p "${OVERLAY_ROOT}"
cp -a --no-preserve=ownership "${BASE_PLUGIN_ROOT}" "${OVERLAY_ROOT}/vllm_ascend"
OVERLAY_PROPOSER=${OVERLAY_ROOT}/vllm_ascend/spec_decode/llm_base_proposer.py
patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${PATCH_PATH}" > "${RUNTIME_DIR}/patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${PATCH_PATH}" > "${RUNTIME_DIR}/patch_apply.txt"
test "$(sha256sum "${OVERLAY_PROPOSER}" | awk '{print $1}')" = 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02

export PYTHONPATH="${OVERLAY_ROOT}:${CANN_GENERATED_PYTHONPATH}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7

printf '%q ' "${cmd[@]}" > "${RUNTIME_DIR}/server_command.txt"
printf '\n' >> "${RUNTIME_DIR}/server_command.txt"
test "$(sha256sum "${RUNTIME_DIR}/server_command.txt" | awk '{print $1}')" = "${EXPECTED_SERVER_COMMAND_SHA256}"

"${PYTHON_BIN}" - "${RESULT_DIR}" "${REPO_ROOT}" "${BASELINE_CONTRACT}" "${FINALIZER}" <<'PY'
import hashlib
import importlib.metadata
import json
import pathlib
import sys

artifact_dir = pathlib.Path(sys.argv[1])
repo_root = pathlib.Path(sys.argv[2])
baseline = pathlib.Path(sys.argv[3])
finalizer = pathlib.Path(sys.argv[4])

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

record = {
    "task_id": "p8_1_deepseek_v4_flash_official_mtp_observe_only_trace_2026_0716",
    "vllm": importlib.metadata.version("vllm"),
    "vllm_ascend": importlib.metadata.version("vllm-ascend"),
    "vllm_commit": "0decac0d96c42b49572498019f0a0e3600f50398",
    "vllm_ascend_commit": "5f6faa0cb8830f667266f3b8121cd1383606f2a1",
    "baseline_contract_sha256": digest(baseline),
    "finalizer_sha256": digest(finalizer),
    "workload_sha256": digest(repo_root / "benchmarks/deepseek_v4_flash/workloads/p8_1_vllm_ascend_official_mtp_observe_only_adapter_smoke.yaml"),
    "generated_content_retained": False,
    "token_ids_retained": False,
}
(artifact_dir / "environment_and_hashes.json").write_text(
    json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
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
  printf '%s\n' 'red_p8_1_official_mtp_server_not_ready' > "${RESULT_DIR}/first_failure_excerpt.txt"
  exit 2
fi

curl -fsS "http://${HOST}:${PORT}/metrics" > "${RUNTIME_DIR}/metrics_before.prom"
for metric in \
  vllm:prefix_cache_queries \
  vllm:prefix_cache_hits \
  vllm:spec_decode_num_drafts_total \
  vllm:spec_decode_num_draft_tokens_total \
  vllm:spec_decode_num_accepted_tokens_total \
  vllm:num_requests_running \
  vllm:num_requests_waiting
do
  grep -F "${metric}" "${RUNTIME_DIR}/metrics_before.prom" >/dev/null
done

"${PYTHON_BIN}" -m tools.ak_state_runtime.cli collect-vllm-ascend-observations \
  --endpoint "http://${HOST}:${PORT}/v1/completions" \
  --metrics-url "http://${HOST}:${PORT}/metrics" \
  --request-payload "${SOURCE_PAYLOAD}" \
  --observations-output "${RESULT_DIR}/runtime_observations.jsonl" \
  --request-result-output "${RESULT_DIR}/request_result.json" \
  --metrics-output "${RESULT_DIR}/prefix_cache_metrics.json" \
  --transfer-availability-output "${RESULT_DIR}/transfer_availability.json" \
  --timeout-seconds 7200 \
  --metrics-settle-seconds 15 \
  > "${RUNTIME_DIR}/collector_stdout.json"

curl -fsS "http://${HOST}:${PORT}/metrics" > "${RUNTIME_DIR}/metrics_after.prom"
"${PYTHON_BIN}" - "${RUNTIME_DIR}/metrics_before.prom" "${RUNTIME_DIR}/metrics_after.prom" "${RESULT_DIR}/mtp_metrics.json" <<'PY'
import json
import math
import pathlib
import re
import sys

names = {
    "vllm:spec_decode_num_drafts_total": "num_drafts",
    "vllm:spec_decode_num_draft_tokens_total": "num_draft_tokens",
    "vllm:spec_decode_num_accepted_tokens_total": "num_accepted_tokens",
}
pattern = re.compile(r"^([^\s{]+)(?:\{[^}]*\})?\s+([-+0-9.eE]+)(?:\s+\d+)?$")

def parse(path):
    values = {value: 0.0 for value in names.values()}
    counts = {value: 0 for value in names.values()}
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match is None or match.group(1) not in names:
            continue
        key = names[match.group(1)]
        value = float(match.group(2))
        if not math.isfinite(value):
            raise SystemExit(f"non-finite metric: {line}")
        values[key] += value
        counts[key] += 1
    if any(count == 0 for count in counts.values()):
        raise SystemExit(f"missing MTP metrics in {path}")
    return values

before = parse(sys.argv[1])
after = parse(sys.argv[2])
delta = {key: after[key] - before[key] for key in before}
record = {
    "before": before,
    "after": after,
    "delta": delta,
    "counter_continuity": all(after[key] >= before[key] for key in before),
    "claim_boundary": "mtp_activity_continuity_only_not_acceptance_rate_or_performance",
}
pathlib.Path(sys.argv[3]).write_text(
    json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

"${PYTHON_BIN}" -m tools.ak_state_runtime.cli build-vllm-ascend-observe-bundle \
  --source "${RESULT_DIR}/runtime_observations.jsonl" \
  --output "${RESULT_DIR}/observe_only_bundle" \
  --baseline-contract "${BASELINE_CONTRACT}" \
  --model-id deepseek-ai/DeepSeek-V4-Flash-w8a8-mtp \
  > "${RUNTIME_DIR}/bundle_stdout.json"

stop_server
trap - EXIT
"${PYTHON_BIN}" "${FINALIZER}" --artifact-dir "${RESULT_DIR}" > "${RUNTIME_DIR}/finalizer_stdout.json"

candidate_files=(
  result_summary.md
  environment_and_hashes.json
  request_result.json
  prefix_cache_metrics.json
  transfer_availability.json
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
