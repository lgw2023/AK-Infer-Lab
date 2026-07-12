# Developer to Server

## 当前唯一任务：P8.1 vLLM-Ascend observe-only tracer bullet

```text
task_id: p8_1_deepseek_v4_flash_vllm_ascend_observe_only_trace_2026_0712
execution_codebase: main-readonly
```

本轮只验证一个问题：在已经成功的 DeepSeek-V4-Flash W8A8、no-MTP、TP8+EP、`FULL_DECODE_ONLY`、单个 `4096+64` 请求 cell 上，新的纯观测采集器能否输出有界 JSONL，并经真实 `VllmAscendAdapter` 生成严格 observe-only bundle。

用户已授权本任务使用：

```text
ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
```

成功只表示 adapter tracer bullet 在这个精确 degraded cell 上通过；不表示 MTP、128K、P6 性能、Prefix Cache 收益、KV transfer、offload 或 placement mutation 已验证。

本轮只发送一个 streaming 请求。禁止第二个请求、eager fallback、MTP、context ladder、并发、profiler、性能归因、runtime/source/site-packages patch、环境升级、checkpoint 修改、payload 留存或移动、synthetic transfer 和任何未确认的结果传输。

## 1. 已知基线与固定边界

前序任务 `p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712` 已完成：

- vLLM `0.22.1` / vLLM-Ascend `0.22.1rc1`；
- W8A8 checkpoint `/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp`；
- NPU 0-7、TP8+EP、`--quantization ascend`、no-MTP；
- `max_model_len=135168`、`max_num_batched_tokens=4096`、`max_num_seqs=1`；
- `FULL_DECODE_ONLY` graph server ready；
- 一个预验证的 4096-token payload 完成 HTTP 200、64 output tokens、`finish_reason=length`；
- payload 为 `19487 bytes`，SHA-256 为 `48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1`。

P8 baseline 已冻结为 `frozen_degraded`，只打开 `open_observe_only` gate。adapter 和本轮 collector 都不得 import `vllm`、`vllm_ascend`、`torch` 或 `torch_npu`；运行模型的 server 进程仍使用固定 runtime 环境，两者不要混淆。

Prefix Cache 只采集 `/metrics` 中 `vllm:prefix_cache_queries` / `vllm:prefix_cache_hits` 的请求前后 token-counter delta。该 proxy 的 object bytes 必须为 null，不能解释为 cache object 大小、命中收益或性能结论。若本 tracer bullet 没有原生 bounded transfer event source，必须报告 `unavailable`，不得制造 transfer event。

## 2. 完整同步远程 main 与安全门

服务器主镜像 tracked 文件只读；只允许由 `origin/main` 快进更新。结果只写 Git 忽略的 `server_local/<task_id>/`。不得修改工作记录、handoff、代码或其他 tracked 文件，不得 restore/reset/stash，不得 commit 或 push 任何分支/tag/remote，也不得操作 server-local worktree 分支。

```bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p8_1_deepseek_v4_flash_vllm_ascend_observe_only_trace_2026_0712
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
PYTHON_BIN="${ENV_PREFIX}/bin/python"
VLLM_BIN="${ENV_PREFIX}/bin/vllm"
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
SERVED_MODEL_NAME=deepseek-v4-flash-w8a8-mtp
HOST=127.0.0.1
PORT=7000
PAYLOAD_PATH="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json"

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
grep -F "task_id: ${TASK_ID}" "${REPO_ROOT}/通信模块/docs/developer-to-server.md"

test ! -e "${RESULT_DIR}"
mkdir -p "${RESULT_DIR}"
git -C "${REPO_ROOT}" rev-parse HEAD > "${RESULT_DIR}/git_head.txt"
git -C "${REPO_ROOT}" rev-parse origin/main > "${RESULT_DIR}/origin_main.txt"
git -C "${REPO_ROOT}" rev-list --left-right --count HEAD...origin/main \
  > "${RESULT_DIR}/ahead_behind.txt"
git -C "${REPO_ROOT}" status --porcelain --untracked-files=no \
  > "${RESULT_DIR}/tracked_status_before.txt"
```

任一条件失败立即标记 `blocked_repo` 并停止。不得自行清理或选择 ours/theirs。完整同步后若任务 ID 已变化，也必须停止并重新读取新任务。

## 3. payload、工具链与 runtime 预检

先验证前序 payload 精确复用，不得重新 tokenize、改写或复制生成新 prompt：

```bash
test -f "${PAYLOAD_PATH}"
test "$(stat -c '%s' "${PAYLOAD_PATH}")" = 19487
test "$(sha256sum "${PAYLOAD_PATH}" | awk '{print $1}')" = \
  48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
printf '%s\n' "${PAYLOAD_PATH}" > "${RESULT_DIR}/payload_path.txt"
stat -c '%s' "${PAYLOAD_PATH}" > "${RESULT_DIR}/payload_bytes.txt"
sha256sum "${PAYLOAD_PATH}" > "${RESULT_DIR}/payload_sha256.txt"
```

在不启动 NPU server 时先运行 adapter/collector 定向测试：

```bash
cd "${REPO_ROOT}"
export PYTHONNOUSERSITE=1
unset PYTHONPATH
"${PYTHON_BIN}" -m pytest \
  tests/ak_state_runtime/test_vllm_ascend_observer.py \
  tests/ak_state_runtime/test_vllm_ascend_adapter.py -q \
  > "${RESULT_DIR}/adapter_tests_stdout.txt" \
  2> "${RESULT_DIR}/adapter_tests_stderr.txt"
```

随后只读核对固定 runtime：

```bash
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
unset PYTHONPATH
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
CANN_GENERATED_PYTHONPATH="${PYTHONPATH:-}"
printf '%s\n' "${CANN_GENERATED_PYTHONPATH}" \
  > "${RESULT_DIR}/cann_generated_pythonpath.txt"

export PYTHONPATH="${CANN_GENERATED_PYTHONPATH}"
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7

"${PYTHON_BIN}" - "${RESULT_DIR}/environment.json" <<'PY'
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path

import torch
import torch_npu  # noqa: F401
import vllm
import vllm_ascend

output = Path(sys.argv[1])
source = Path("/data/node0_disk1/vllm-0.22.1")

def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(source), *args], text=True
    ).strip()

result = {
    "python": ".".join(map(str, sys.version_info[:3])),
    "torch": torch.__version__,
    "torch_npu": importlib.metadata.version("torch-npu"),
    "vllm": vllm.__version__,
    "vllm_ascend": importlib.metadata.version("vllm-ascend"),
    "vllm_root": str(Path(vllm.__file__).resolve().parent),
    "vllm_ascend_root": str(Path(vllm_ascend.__file__).resolve().parent),
    "vllm_source_commit": git("rev-parse", "HEAD"),
    "vllm_source_clean": not bool(git("status", "--porcelain")),
    "vllm_plugins": os.environ.get("VLLM_PLUGINS", ""),
    "visible_devices": os.environ.get("ASCEND_RT_VISIBLE_DEVICES", ""),
    "acl_origin": "",
    "acl_rt_memcpy_imported": False,
}
try:
    import acl
    from acl.rt import memcpy  # noqa: F401
    result["acl_origin"] = str(Path(acl.__file__).resolve())
    result["acl_rt_memcpy_imported"] = True
except Exception as exc:
    result["acl_error"] = f"{type(exc).__name__}: {exc}"

expected_plugins = (
    "ascend,ascend_kv_connector,ascend_model_loader,"
    "ascend_service_profiling,ascend_model"
)
checks = {
    "python": result["python"] == "3.11.15",
    "torch": result["torch"] == "2.10.0+cpu",
    "torch_npu": result["torch_npu"] == "2.10.0",
    "vllm": str(result["vllm"]).startswith("0.22.1"),
    "vllm_ascend": result["vllm_ascend"] == "0.22.1rc1",
    "vllm_root": result["vllm_root"] == "/data/node0_disk1/vllm-0.22.1/vllm",
    "vllm_source_commit": result["vllm_source_commit"] == "0decac0d96c42b49572498019f0a0e3600f50398",
    "vllm_source_clean": result["vllm_source_clean"] is True,
    "plugins": result["vllm_plugins"] == expected_plugins,
    "visible_devices": result["visible_devices"] == "0,1,2,3,4,5,6,7",
    "acl_origin": result["acl_origin"].startswith("/usr/local/Ascend/"),
    "acl_rt_memcpy": result["acl_rt_memcpy_imported"] is True,
}
result["checks"] = checks
result["preflight_ok"] = all(checks.values())
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
raise SystemExit(0 if result["preflight_ok"] else 1)
PY
```

任何 payload、定向测试、版本、import root、source commit/clean、五插件、ACL 或可见设备不匹配都标记 `blocked_preflight`，禁止启动 server。不得改环境来让门通过。

## 4. 八卡资源硬门

```bash
npu-smi info > "${RESULT_DIR}/npu_smi_before.txt" 2>&1 || true
npu-smi info -t usages > "${RESULT_DIR}/npu_usage_before.txt" 2>&1 || true
ss -ltnp > "${RESULT_DIR}/listening_ports_before.txt" 2>&1 || true

RESOURCE_GATE=not_confirmed
# 只有人工确认 NPU 0-7 全部 Health=OK、无不明进程、空闲，且 127.0.0.1:7000 未占用后，才可把上行改为 pass。
printf '%s\n' "${RESOURCE_GATE}" > "${RESULT_DIR}/resource_gate.txt"
test "${RESOURCE_GATE}" = pass
```

任一卡不健康、忙碌、存在归属不明进程或端口冲突，都标记 `blocked_resource` 并停止。不得终止、暂停或影响非本任务进程；历史清理授权不能复用。

## 5. 启动唯一允许的固定 no-MTP server

```bash
SERVER_DIR="${RESULT_DIR}/server"
mkdir -p "${SERVER_DIR}"
SERVER_PID=""

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
)

printf '%q ' "${cmd[@]}" > "${SERVER_DIR}/server_command.txt"
printf '\n' >> "${SERVER_DIR}/server_command.txt"
setsid "${cmd[@]}" > "${SERVER_DIR}/vllm_server.log" 2>&1 &
SERVER_PID=$!
printf '%s\n' "${SERVER_PID}" > "${SERVER_DIR}/server_pid.txt"

READY_EXIT=1
for _ in $(seq 1 180); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    break
  fi
  if curl -fsS --max-time 5 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
    READY_EXIT=0
    break
  fi
  sleep 10
done
printf '%s\n' "${READY_EXIT}" > "${SERVER_DIR}/server_ready_exit_code.txt"
```

不得加 `--enforce-eager` 或 `--speculative-config`，不得修改 graph sizes、TP/EP、DSA-CP、`max_num_seqs` 或其他参数。未 ready 则标记 `red_server_not_ready`，直接进入清理；禁止第二个 profile。

## 6. 单请求观测与 observe-only bundle

仅当 `READY_EXIT=0` 时执行一次 collector：

```bash
set +e
"${PYTHON_BIN}" -m tools.ak_state_runtime.cli collect-vllm-ascend-observations \
  --endpoint "http://${HOST}:${PORT}/v1/completions" \
  --metrics-url "http://${HOST}:${PORT}/metrics" \
  --request-payload "${PAYLOAD_PATH}" \
  --observations-output "${RESULT_DIR}/runtime_observations.jsonl" \
  --request-result-output "${RESULT_DIR}/request_result.json" \
  --metrics-output "${RESULT_DIR}/prefix_cache_metrics.json" \
  --transfer-availability-output "${RESULT_DIR}/transfer_availability.json" \
  --timeout-seconds 900 \
  --metrics-settle-seconds 15 \
  > "${RESULT_DIR}/collector_stdout.txt" \
  2> "${RESULT_DIR}/collector_stderr.txt"
COLLECT_EXIT=$?
set -e
printf '%s\n' "${COLLECT_EXIT}" > "${RESULT_DIR}/collector_exit_code.txt"
```

collector 失败则标记 `red_observation_collection` 并直接清理；不得修改 JSONL、补造事件或发送第二个请求。

只有 collector 成功才构建 bundle：

```bash
set +e
"${PYTHON_BIN}" -m tools.ak_state_runtime.cli build-vllm-ascend-observe-bundle \
  --source "${RESULT_DIR}/runtime_observations.jsonl" \
  --output "${RESULT_DIR}/observe_only_bundle" \
  --baseline-contract benchmarks/deepseek_v4_flash/p8/p8_baseline_contract.yaml \
  --model-id deepseek-ai/DeepSeek-V4-Flash-w8a8-mtp \
  > "${RESULT_DIR}/bundle_stdout.txt" \
  2> "${RESULT_DIR}/bundle_stderr.txt"
BUNDLE_EXIT=$?
set -e
printf '%s\n' "${BUNDLE_EXIT}" > "${RESULT_DIR}/bundle_exit_code.txt"
```

只有 bundle command 成功才执行最终契约核对：

```bash
set +e
"${PYTHON_BIN}" - "${RESULT_DIR}" <<'PY' \
  > "${RESULT_DIR}/bundle_validation_stdout.txt" \
  2> "${RESULT_DIR}/bundle_validation_stderr.txt"
import json
import sys
from pathlib import Path

import yaml

root = Path(sys.argv[1])
bundle = root / "observe_only_bundle"

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

request = read_json(root / "request_result.json")
metrics = read_json(root / "prefix_cache_metrics.json")
transfer = read_json(root / "transfer_availability.json")
source_events = read_jsonl(root / "runtime_observations.jsonl")
events = read_jsonl(bundle / "state_events.jsonl")
objects = read_jsonl(bundle / "state_objects.jsonl")
decisions = read_jsonl(bundle / "placement_decisions.jsonl")
validation = read_json(bundle / "validation_report.json")
manifest = yaml.safe_load((bundle / "manifest.yaml").read_text(encoding="utf-8"))

assert request["status"] == "success"
assert request["http_status"] == 200
assert request["prompt_tokens"] == 4096
assert request["generated_token_count"] == 64
assert request["streamed_token_count"] == 64
assert request["finish_reason"] == "length"
assert request["generated_text_retained"] is False
assert request["token_ids_retained"] is False
assert metrics["delta"]["queries"] > 0
assert metrics["claim_boundary"] == "token_counters_only_not_object_bytes_or_performance"
assert transfer["status"] == "unavailable"
assert transfer["event_emitted"] is False
assert len(source_events) == 4
assert sum(event["event_type"] == "request_stage" for event in source_events) == 3
assert sum(event["object_type"] == "prefix_block" for event in source_events) == 1
assert all("payload" not in event and "payload_ref" not in event for event in source_events)
assert len(events) == 4
assert len(objects) == 1
assert len(decisions) == 1
assert objects[0]["payload_ref"] is None
assert decisions[0]["execution_mode"] == "observe_only"
assert decisions[0]["action"] == "no_op"
assert decisions[0]["executed"] is False
assert decisions[0]["execution_result"] == "skipped"
assert validation["trace_validation_errors"] == 0
assert validation["errors"] == []
assert manifest["claim_level"] == "selected_workload_observe_only_candidate"
assert manifest["provenance_mode"] == "bounded_server_observation"
assert manifest["server_validated"] is False
assert manifest["emitted_event_count"] == 4
assert manifest["state_object_count"] == 1
assert manifest["placement_decision_count"] == 1
assert manifest["trace_validation_errors"] == 0

summary = {
    "status": "pass",
    "request_stage_event_count": 3,
    "prefix_proxy_object_count": 1,
    "placement_decision_count": 1,
    "trace_validation_errors": 0,
    "server_validated_manifest_value": False,
}
(root / "bundle_acceptance.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False))
PY
VALIDATION_EXIT=$?
set -e
printf '%s\n' "${VALIDATION_EXIT}" > "${RESULT_DIR}/bundle_validation_exit_code.txt"
```

`manifest.server_validated` 必须保持 `false`，直到外部开发机收到并复核新结果；服务器不得自行改为 true。bundle 或契约核对失败标记 `red_bundle_validation`，不得手工修文件重试。

## 7. 有界证据、清理与分级

无论成功失败，都只清理本任务记录的 server process group：

```bash
grep -nE 'Loading model weights took|Loading weights took|Directly load the compiled graph|Saved compiled graph to cache|Application startup complete|GET /health|POST /v1/completions|Traceback|ERROR|Error|Exception|Assertion|unsupported|not supported|OutOfMemory|OOM|HCCL|positions_cpu' \
  "${SERVER_DIR}/vllm_server.log" | head -n 280 \
  > "${SERVER_DIR}/server_excerpt.txt" || true

npu-smi info -t usages > "${RESULT_DIR}/npu_usage_after_request.txt" 2>&1 || true

if [ -n "${SERVER_PID:-}" ] && kill -0 "${SERVER_PID}" 2>/dev/null; then
  kill -- "-${SERVER_PID}" >/dev/null 2>&1 || kill "${SERVER_PID}" >/dev/null 2>&1 || true
  sleep 10
fi

npu-smi info > "${RESULT_DIR}/npu_smi_after.txt" 2>&1 || true
npu-smi info -t usages > "${RESULT_DIR}/npu_usage_after.txt" 2>&1 || true
ss -ltnp > "${RESULT_DIR}/listening_ports_after.txt" 2>&1 || true
git -C "${REPO_ROOT}" status --porcelain --untracked-files=no \
  > "${RESULT_DIR}/tracked_status_after.txt"
test ! -s "${RESULT_DIR}/tracked_status_after.txt"
```

分级：

- `green_observe_only_adapter_on_frozen_degraded_cell`：server ready，唯一请求精确 `4096+64`，Prefix counter proxy 可用，4-event JSONL、1 object、1 no-op decision、0 validation errors 全通过；
- `red_observation_collection`：server ready，但唯一 streaming 请求、usage/token IDs 或 Prefix counter 观测失败；
- `red_bundle_validation`：观测成功，但 adapter/bundle/acceptance 失败；
- `red_server_not_ready`：固定 server 未 ready；
- `blocked_repo` / `blocked_preflight` / `blocked_resource`：对应硬门失败。

任一结果都必须报告首次失败阶段。失败不得即兴重试第二次请求、第二个 server profile 或修改 runtime/collector。

## 8. 结果摘要与传输等待门

在 `${RESULT_DIR}/result_summary.md` 中记录：

- task ID、Git HEAD/origin/ahead-behind、tracked 状态和完整同步方式；
- payload 原路径、bytes、SHA-256；
- adapter tests、环境版本/import roots/source commit/clean、ACL、五插件；
- NPU 0-7 与端口资源门；
- 完整 shell-escaped server command、ready/collector/bundle/validation exit；
- request HTTP/prompt/output/streamed tokens/finish reason，且没有留存生成文本或 token IDs；
- Prefix query/hit before/after/delta，并明确只是 token-counter proxy；
- transfer availability 与没有 synthetic event；
- events/objects/decisions 数量、所有 decision `executed=false`、所有 payload ref 为 null、trace validation errors；
- bundle manifest 的 claim/provenance 与 `server_validated=false`；
- 首错、最终 grade、进程清理、NPU/端口恢复、raw server log 路径；
- 明确本轮不是 P6 benchmark，不验证 MTP、128K、性能、真实 transfer/offload 或 placement mutation。

生成 `${RESULT_DIR}/delivery_candidates.tsv`，每行：

```text
path    size_bytes    sha256    sensitivity    email_feasible    upload_api_feasible    server_local_feasible    recommended_method    reason
```

小候选优先包含：

```text
result_summary.md
git_head.txt
origin_main.txt
ahead_behind.txt
payload_path.txt
payload_bytes.txt
payload_sha256.txt
environment.json
adapter_tests_stdout.txt
resource_gate.txt
server/server_command.txt
server/server_ready_exit_code.txt
server/server_excerpt.txt
collector_exit_code.txt
request_result.json
prefix_cache_metrics.json
transfer_availability.json
runtime_observations.jsonl
bundle_exit_code.txt
bundle_validation_exit_code.txt
bundle_acceptance.json
observe_only_bundle/manifest.yaml
observe_only_bundle/validation_report.json
observe_only_bundle/state_events.jsonl
observe_only_bundle/state_objects.jsonl
observe_only_bundle/placement_decisions.jsonl
tracked_status_after.txt
```

每个候选必须小于 70KB。`request_payload.json`、raw `vllm_server.log`、完整 NPU SMI、模型和整个目录保持 server-local，不列为默认传输候选。`delivery_candidates.tsv` 不得自引用自身最终 size/SHA；完成后在任务会话外单独报告其精确 bytes/SHA-256。

本轮是新的结果范围，尚未获得 `email`、`upload-api` 或 `server-local` 的传输选择。结果生成后，只在当前任务会话报告完整候选包的精确路径、逐文件 bytes、SHA-256、敏感性、三种可用方式和一个推荐方式及理由，然后暂停。

确认前禁止发送邮件、附件、upload-api 请求或任何状态正文；不得沿用历史 `upload-api` 选择。任何传输失败都必须停止并请求新的明确选择，不得自动重试、改名、缩扩范围、补发邮件或切换渠道。

## 9. 完成边界

- 成功后停止，不自动进入真实 KV move、offload、placement policy、MTP、128K 或 P6。
- 服务器不得修改 `p8_baseline_contract.yaml`，不得把 manifest 的 `server_validated` 改为 true。
- 不提交或 push server runtime artifact；所有结果先留在 `server_local/<task_id>/`。
- 外部开发机收到获批结果后再决定是否关闭 P8.1 gate 和下一轮任务。
