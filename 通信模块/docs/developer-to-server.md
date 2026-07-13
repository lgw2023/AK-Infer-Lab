# Developer to Server

## 当前唯一任务：P6.1 no-MTP minimal unprofiled control

```text
task_id: p6_1_deepseek_v4_flash_w8a8_no_mtp_minimal_unprofiled_control_2026_0713
execution_codebase: main-readonly
ASCEND_RT_VISIBLE_DEVICES: 0,1,2,3,4,5,6,7
claim_boundary: p6_1_minimal_unprofiled_control_only
```

P6.0 任务 `p6_0_deepseek_v4_flash_w8a8_no_mtp_degraded_stabilization_2026_0713` 已完成：两个新 fresh lifecycle 均完成唯一 `4096+64` 请求，连同前序 P5 共 3 次连续成功，等级为 `yellow_degraded_baseline_stabilized`。

本轮只在该完全冻结的 no-MTP cell 上建立一个最小 unprofiled 性能对照：一个 fresh server lifecycle，先发 1 个固定 warmup，再串行发 3 个 measured `4096+64+c1` 请求。warmup 不进入统计；3 个 measured 样本只报原始值和 min/median/max，`report_p95_p99: false`，原因为 `n3_is_insufficient`。

这不是完整 P6.1 pilot/matrix，也不是 official MTP baseline。禁止额外 context、并发、256-token output、MTP、128K ladder、eager fallback、profiler、offload、placement mutation、P8.1，runtime/source/site-packages/environment/checkpoint 修改。任一 warmup 或 measured 请求失败即停，不补跑、不删除 outlier、不调参。成功或失败后都不得自动进入 MTP 修复；下一任务必须等待用户再次确认。

## 1. 固定基线与计量口径

```text
model: /data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
runtime: vLLM 0.22.1+empty / vLLM-Ascend 0.22.1rc1
NPU: 0,1,2,3,4,5,6,7
parallelism: TP8 + EP
quantization: ascend
MTP: disabled
cudagraph: FULL_DECODE_ONLY
max_model_len: 135168
max_num_batched_tokens: 4096
max_num_seqs: 1
server lifecycles: 1
WARMUP_REQUESTS=1
MEASURED_REQUESTS=3
CONCURRENCY=1
request: 4096 input token IDs + fixed 64 output tokens
```

固定 payload：

```text
path: 工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json
bytes: 19487
sha256: 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
```

指标必须使用 client `time.monotonic_ns()`：

```text
TTFT = first_token_ns - request_start_ns
TPOT = (last_token_ns - first_token_ns) / (completion_tokens - 1)
ITL  = 相邻 token_arrival_ns 之差
E2EL = request_end_ns - request_start_ns
decode_tokens_per_second = (completion_tokens - 1) / decode_elapsed_seconds
request_output_tokens_per_second = completion_tokens / E2EL_seconds
```

为了保证 ITL 语义，每个 token-bearing SSE chunk 必须恰好包含 1 个 `token_id`，并记录 64 个 `token_arrival_ns`。若 chunk 合并了多个 token，本轮标记 `blocked_measurement_semantics` 并停止；不用同一时间戳伪造 token 级 ITL。

## 2. 完整同步 main 与只读安全门

必须完整 fast-forward 同步远程 `main`；不能只拉或 cherry-pick 某个提交。同步全部代码不代表执行全部内容，执行范围只取同步后本文件的当前 task。

服务器两套代码工作区必须严格分离：

- 主镜像 `/data/node0_disk1/liguowei/AK-Infer-Lab`，分支 `main`：本轮唯一读取与执行输入，`execution_codebase=main-readonly`；tracked 文件全部只读，结果只写 Git 忽略的 `server_local/<task_id>/`。
- 服务器专属 worktree `/data/node0_disk1/liguowei/AK-Infer-Lab-server-local`，分支 `server-local/runtime-adaptations`：本轮只读记录拓扑身份，本轮不得进入该目录执行代码，不得 checkout、merge、commit、push 或改写文件。不得运行 `通信模块/server_local_git_sync.sh`。

不得把 `REPO_ROOT` 切到第二套 worktree，不得从第二套 import 或启动 vLLM。不得 restore/reset/stash，不得 commit 或 push，不得自行选择 ours/theirs。

```bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
SERVER_LOCAL_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab-server-local
SERVER_LOCAL_BRANCH=server-local/runtime-adaptations
TASK_ID=p6_1_deepseek_v4_flash_w8a8_no_mtp_minimal_unprofiled_control_2026_0713
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"
P6_0_RESULT_DIR="${REPO_ROOT}/server_local/p6_0_deepseek_v4_flash_w8a8_no_mtp_degraded_stabilization_2026_0713"
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
PYTHON_BIN="${ENV_PREFIX}/bin/python"
VLLM_BIN="${ENV_PREFIX}/bin/vllm"
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
SERVED_MODEL_NAME=deepseek-v4-flash-w8a8-mtp
HOST=127.0.0.1
PORT=7000
WARMUP_REQUESTS=1
MEASURED_REQUESTS=3
CONCURRENCY=1
PAYLOAD_PATH="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json"

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
grep -F "task_id: ${TASK_ID}" "${REPO_ROOT}/通信模块/docs/developer-to-server.md"

test ! -e "${RESULT_DIR}"
mkdir -p "${RESULT_DIR}"
test "$(git -C "${SERVER_LOCAL_ROOT}" rev-parse --is-inside-work-tree)" = true
test "$(git -C "${SERVER_LOCAL_ROOT}" branch --show-current)" = "${SERVER_LOCAL_BRANCH}"
git -C "${REPO_ROOT}" rev-parse HEAD > "${RESULT_DIR}/git_head.txt"
git -C "${REPO_ROOT}" rev-parse origin/main > "${RESULT_DIR}/origin_main.txt"
git -C "${REPO_ROOT}" rev-list --left-right --count HEAD...origin/main > "${RESULT_DIR}/ahead_behind.txt"
git -C "${REPO_ROOT}" status --porcelain --untracked-files=no > "${RESULT_DIR}/tracked_status_before.txt"
git -C "${SERVER_LOCAL_ROOT}" rev-parse HEAD > "${RESULT_DIR}/server_local_head_observed.txt"
git -C "${SERVER_LOCAL_ROOT}" status --porcelain --untracked-files=no > "${RESULT_DIR}/server_local_tracked_status_observed.txt"
```

任一条件失败标记 `blocked_repo` 并停止。同步后若 task ID 变化，必须停止并重新读取本文件。

## 3. payload、runtime 与 P6.0 provenance 预检

不得重新 tokenize、复制改写 payload 或改变请求字段。

```bash
test -f "${PAYLOAD_PATH}"
test "$(stat -c '%s' "${PAYLOAD_PATH}")" = 19487
test "$(sha256sum "${PAYLOAD_PATH}" | awk '{print $1}')" = 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
test -f "${P6_0_RESULT_DIR}/repeat_results.json"
test -f "${P6_0_RESULT_DIR}/lifecycle_1/server_command_sha256.txt"
"${PYTHON_BIN}" - "${P6_0_RESULT_DIR}/repeat_results.json" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["grade"] == "yellow_degraded_baseline_stabilized"
assert result["new_successful_lifecycles"] == 2
assert result["consecutive_successes_total"] == 3
assert result["official_baseline"] is False
PY

printf '%s\n' "${PAYLOAD_PATH}" > "${RESULT_DIR}/payload_path.txt"
stat -c '%s' "${PAYLOAD_PATH}" > "${RESULT_DIR}/payload_bytes.txt"
sha256sum "${PAYLOAD_PATH}" > "${RESULT_DIR}/payload_sha256.txt"

cd "${REPO_ROOT}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
unset PYTHONPATH
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
CANN_GENERATED_PYTHONPATH="${PYTHONPATH:-}"
export PYTHONPATH="${CANN_GENERATED_PYTHONPATH}"
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7

"${PYTHON_BIN}" - "${PAYLOAD_PATH}" "${RESULT_DIR}/environment.json" <<'PY'
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

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
output = Path(sys.argv[2])
source = Path("/data/node0_disk1/vllm-0.22.1")

def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()

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
    "payload_prompt_tokens": len(payload.get("prompt", [])),
    "payload_model": payload.get("model"),
    "payload_max_tokens": payload.get("max_tokens"),
    "payload_min_tokens": payload.get("min_tokens"),
    "payload_ignore_eos": payload.get("ignore_eos"),
    "payload_temperature": payload.get("temperature"),
}
try:
    import acl
    from acl.rt import memcpy  # noqa: F401
    result["acl_origin"] = str(Path(acl.__file__).resolve())
    result["acl_rt_memcpy_imported"] = True
except Exception as exc:
    result["acl_origin"] = ""
    result["acl_rt_memcpy_imported"] = False
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
    "payload_prompt_tokens": result["payload_prompt_tokens"] == 4096,
    "payload_model": result["payload_model"] == "deepseek-v4-flash-w8a8-mtp",
    "payload_max_tokens": result["payload_max_tokens"] == 64,
    "payload_min_tokens": result["payload_min_tokens"] == 64,
    "payload_ignore_eos": result["payload_ignore_eos"] is True,
    "payload_temperature": result["payload_temperature"] == 0.0,
}
result["checks"] = checks
result["preflight_ok"] = all(checks.values())
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
raise SystemExit(0 if result["preflight_ok"] else 1)
PY

sha256sum "${RESULT_DIR}/environment.json" > "${RESULT_DIR}/environment_sha256.txt"
```

任一 payload、P6.0 grade、版本、import root、source commit/clean、五插件、ACL 或可见设备不匹配都标记 `blocked_preflight` 并停止。不得修改环境来让门通过。

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

## 5. 单一 server lifecycle：1 warmup + 3 measured

以下 server command 必须与 P6.0 完全一致。不得添加 `--enforce-eager`、`--speculative-config` 或修改任何参数。
输出 JSON 中 warmup 记录必须包含 `"phase": "warmup"`，三个计量记录必须包含 `"phase": "measured"`。

```bash
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

printf '%q ' "${cmd[@]}" > "${RESULT_DIR}/server_command.txt"
printf '\n' >> "${RESULT_DIR}/server_command.txt"
sha256sum "${RESULT_DIR}/server_command.txt" > "${RESULT_DIR}/server_command_sha256.txt"
test "$(awk '{print $1}' "${RESULT_DIR}/server_command_sha256.txt")" = \
     "$(awk '{print $1}' "${P6_0_RESULT_DIR}/lifecycle_1/server_command_sha256.txt")"

setsid "${cmd[@]}" > "${RESULT_DIR}/vllm_server.log" 2>&1 &
server_pid=$!
printf '%s\n' "${server_pid}" > "${RESULT_DIR}/server_pid.txt"

ready_exit=1
for _ in $(seq 1 180); do
  if ! kill -0 "${server_pid}" 2>/dev/null; then
    break
  fi
  if curl -fsS --max-time 5 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
    ready_exit=0
    break
  fi
  sleep 10
done
printf '%s\n' "${ready_exit}" > "${RESULT_DIR}/server_ready_exit_code.txt"

client_exit=90
if [ "${ready_exit}" -eq 0 ]; then
  curl -fsS --max-time 10 "http://${HOST}:${PORT}/metrics" > "${RESULT_DIR}/server_metrics_before.prom" || true
  set +e
  "${PYTHON_BIN}" - "${PAYLOAD_PATH}" "${RESULT_DIR}" "${WARMUP_REQUESTS}" "${MEASURED_REQUESTS}" "${CONCURRENCY}" <<'PY'
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

payload_path = Path(sys.argv[1])
result_dir = Path(sys.argv[2])
warmup_requests = int(sys.argv[3])
measured_requests = int(sys.argv[4])
concurrency = int(sys.argv[5])
assert warmup_requests == 1
assert measured_requests == 3
assert concurrency == 1

base_payload = json.loads(payload_path.read_text(encoding="utf-8"))
base_payload["stream"] = True
base_payload["stream_options"] = {"include_usage": True}
base_payload["return_token_ids"] = True

def run_request(phase: str, request_index: int) -> dict:
    request = urllib.request.Request(
        "http://127.0.0.1:7000/v1/completions",
        data=json.dumps(base_payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    request_start_ns = time.monotonic_ns()
    token_arrival_ns = []
    token_chunk_widths = []
    request_end_ns = 0
    prompt_tokens = None
    completion_tokens = None
    finish_reason = ""
    saw_done = False
    error = None
    status = 0
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            status = response.status
            if status != 200:
                raise RuntimeError(f"HTTP status {status}")
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    saw_done = True
                    request_end_ns = time.monotonic_ns()
                    break
                if not data:
                    continue
                chunk = json.loads(data)
                if chunk.get("error"):
                    raise RuntimeError(str(chunk["error"]))
                for choice in chunk.get("choices") or []:
                    token_ids = choice.get("token_ids") or []
                    if token_ids:
                        now_ns = time.monotonic_ns()
                        token_chunk_widths.append(len(token_ids))
                        if len(token_ids) == 1:
                            token_arrival_ns.append(now_ns)
                    if choice.get("finish_reason") is not None:
                        finish_reason = str(choice["finish_reason"])
                usage = chunk.get("usage")
                if isinstance(usage, dict):
                    prompt_tokens = usage.get("prompt_tokens")
                    completion_tokens = usage.get("completion_tokens")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if request_end_ns == 0:
            request_end_ns = time.monotonic_ns()

    exact_token_arrivals = (
        completion_tokens == 64
        and len(token_arrival_ns) == 64
        and token_chunk_widths == [1] * 64
    )
    streamed_token_count = sum(token_chunk_widths)
    checks = {
        "http_status": status == 200,
        "saw_done": saw_done,
        "prompt_tokens": prompt_tokens == 4096,
        "completion_tokens": completion_tokens == 64,
        "streamed_token_count": streamed_token_count == 64,
        "finish_reason": finish_reason == "length",
        "exact_token_arrival_timestamps": exact_token_arrivals,
    }
    success = all(checks.values())
    record = {
        "phase": phase,
        "request_index": request_index,
        "status": "success" if success else "error",
        "http_status": status,
        "prompt_tokens": prompt_tokens,
        "generated_token_count": completion_tokens,
        "streamed_token_count": streamed_token_count,
        "finish_reason": finish_reason,
        "request_start_ns": request_start_ns,
        "token_arrival_ns": token_arrival_ns,
        "request_end_ns": request_end_ns,
        "token_chunk_widths": token_chunk_widths,
        "checks": checks,
        "error": error,
        "generated_text_retained": False,
        "token_ids_retained": False,
    }
    if exact_token_arrivals and request_end_ns > token_arrival_ns[-1]:
        first_token_ns = token_arrival_ns[0]
        last_token_ns = token_arrival_ns[-1]
        itl_ms = [
            (right - left) / 1_000_000
            for left, right in zip(token_arrival_ns, token_arrival_ns[1:])
        ]
        decode_elapsed_s = (last_token_ns - first_token_ns) / 1_000_000_000
        e2el_s = (request_end_ns - request_start_ns) / 1_000_000_000
        record["metrics"] = {
            "ttft_ms": (first_token_ns - request_start_ns) / 1_000_000,
            "tpot_ms": (last_token_ns - first_token_ns) / 63 / 1_000_000,
            "itl_ms": itl_ms,
            "itl_min_ms": min(itl_ms),
            "itl_median_ms": statistics.median(itl_ms),
            "itl_max_ms": max(itl_ms),
            "e2el_ms": e2el_s * 1000,
            "decode_tokens_per_second": 63 / decode_elapsed_s,
            "request_output_tokens_per_second": 64 / e2el_s,
        }
    return record

warmup = run_request("warmup", 1)
measured = []
first_failure_point = None
if warmup["status"] != "success":
    first_failure_point = (
        "warmup_measurement_semantics"
        if not warmup["checks"]["exact_token_arrival_timestamps"]
        and all(value for key, value in warmup["checks"].items() if key != "exact_token_arrival_timestamps")
        else "warmup_request"
    )
else:
    for request_index in range(1, measured_requests + 1):
        record = run_request("measured", request_index)
        measured.append(record)
        if record["status"] != "success":
            first_failure_point = (
                f"measured_request_{request_index}_measurement_semantics"
                if not record["checks"]["exact_token_arrival_timestamps"]
                and all(
                    value
                    for key, value in record["checks"].items()
                    if key != "exact_token_arrival_timestamps"
                )
                else f"measured_request_{request_index}"
            )
            break

success = warmup["status"] == "success" and len(measured) == 3 and all(
    record["status"] == "success" for record in measured
)
result = {
    "task_id": "p6_1_deepseek_v4_flash_w8a8_no_mtp_minimal_unprofiled_control_2026_0713",
    "claim_boundary": "p6_1_minimal_unprofiled_control_only",
    "warmup": warmup,
    "measured": measured,
    "first_failure_point": first_failure_point,
    "success": success,
}
(result_dir / "control_results.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

summary = {
    "task_id": result["task_id"],
    "grade": (
        "yellow_degraded_minimal_unprofiled_control_measured"
        if success
        else (
            "blocked_measurement_semantics"
            if first_failure_point and first_failure_point.endswith("measurement_semantics")
            else "red_minimal_unprofiled_control"
        )
    ),
    "baseline_grade": "yellow_degraded_baseline_stabilized",
    "warmup_requests": 1,
    "measured_requests_planned": 3,
    "measured_requests_successful": sum(r["status"] == "success" for r in measured),
    "first_failure_point": first_failure_point,
    "report_p95_p99": False,
    "tail_percentile_reason": "n3_is_insufficient",
    "outlier_removal": False,
    "official_baseline": False,
    "mtp_validated": False,
    "context_128k_validated": False,
    "full_p6_1_matrix_validated": False,
}
if success:
    for metric in (
        "ttft_ms",
        "tpot_ms",
        "e2el_ms",
        "decode_tokens_per_second",
        "request_output_tokens_per_second",
    ):
        values = [record["metrics"][metric] for record in measured]
        summary[metric] = {
            "raw": values,
            "min": min(values),
            "median": statistics.median(values),
            "max": max(values),
        }
(result_dir / "control_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
raise SystemExit(0 if success else 1)
PY
  client_exit=$?
  set -e
  curl -fsS --max-time 10 "http://${HOST}:${PORT}/metrics" > "${RESULT_DIR}/server_metrics_after.prom" || true
fi
printf '%s\n' "${client_exit}" > "${RESULT_DIR}/client_exit_code.txt"

if kill -0 "${server_pid}" 2>/dev/null; then
  kill -TERM -- "-${server_pid}" 2>/dev/null || true
  for _ in $(seq 1 60); do
    kill -0 "${server_pid}" 2>/dev/null || break
    sleep 2
  done
fi
if kill -0 "${server_pid}" 2>/dev/null; then
  kill -KILL -- "-${server_pid}" 2>/dev/null || true
fi
wait "${server_pid}" 2>/dev/null || true

sleep 10
npu-smi info > "${RESULT_DIR}/npu_smi_after.txt" 2>&1 || true
npu-smi info -t usages > "${RESULT_DIR}/npu_usage_after.txt" 2>&1 || true
ss -ltnp > "${RESULT_DIR}/listening_ports_after.txt" 2>&1 || true
if ss -ltn | awk '{print $4}' | grep -Eq '(^|:)7000$'; then
  printf '%s\n' port_7000_still_listening > "${RESULT_DIR}/cleanup_status.txt"
else
  printf '%s\n' clean > "${RESULT_DIR}/cleanup_status.txt"
fi
```

warmup 成功后只能执行 3 个 measured 请求。任一 measured 失败时 Python client 必须立即停止循环；不得为凑齐 3 个成功样本而补跑。server 清理只能作用于本任务记录的 process group，不得清理其他 PID。

## 6. 结果摘要、分级与传输暂停门

生成 `${RESULT_DIR}/result_summary.md`，必须包含：

- task ID、服务器 Git HEAD、runtime/source commits、模型路径、NPU 范围；
- P6.0 `yellow_degraded_baseline_stabilized` provenance 与 command/payload SHA-256；
- server ready、warmup 和三个 measured 请求的退出码与 token-control 结果；
- measured 三个样本的 TTFT/TPOT/ITL/E2EL 与两种 throughput 原始值、min/median/max；
- `report_p95_p99: false`、`n3_is_insufficient`、`outlier_removal: false`；
- 第一失败点（若有）、cleanup、最终 grade；
- 明确本轮只是 no-MTP minimal control，不验证 official MTP/128K/full P6.1/P8.1/优化收益；
- raw server log 和 Prometheus 快照的 server-local 路径，不把它们列入外发候选。

候选外发文件只允许以下小文件，单文件和完整集合都必须不超过 70KB：

```text
result_summary.md
control_summary.json
control_results.json
environment.json
payload_sha256.txt
server_command_sha256.txt
cleanup_status.txt
```

生成 `${RESULT_DIR}/delivery_candidates.tsv`，每行记录相对路径、bytes、SHA-256、敏感性。`delivery_candidates.tsv` 不得自引用自身的最终 size/hash。再生成 `${RESULT_DIR}/transfer_preflight.md`，明确：

```text
summary_path: <绝对路径>
attachment_scope: <上述精确 7 个文件>
total_bytes: <精确值>
set_sha256: <对候选 path/bytes/hash 清单计算的 SHA-256>
sensitivity: internal_unprofiled_timing_no_token_or_generated_text
available_methods: email, upload-api, server-local
recommended_method: upload-api
recommendation_reason: one_named_multi_file_session_preserves_the_exact_small_package_and_hashes
selected_method: none
transfer_status: waiting_for_user_choice
```

当前未选择 `email`、`upload-api` 或 `server-local`。完成后只保留 server-local 结果并停止；禁止发送邮件、附件、upload-api 请求或状态正文，不得沿用历史传输选择。

在生成 `result_summary.md`、`delivery_candidates.tsv` 和 `transfer_preflight.md` 后执行最终硬验收。该区块只对成功 grade 返回 0；失败或 blocked 结果仍应保留已生成的小型摘要，但不得通过此验收。

```bash
test "$(<"${RESULT_DIR}/server_ready_exit_code.txt")" = 0
test "$(<"${RESULT_DIR}/client_exit_code.txt")" = 0
test "$(<"${RESULT_DIR}/cleanup_status.txt")" = clean
test -f "${RESULT_DIR}/result_summary.md"
test -f "${RESULT_DIR}/delivery_candidates.tsv"
test -f "${RESULT_DIR}/transfer_preflight.md"

"${PYTHON_BIN}" - "${RESULT_DIR}/control_summary.json" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert summary["grade"] == "yellow_degraded_minimal_unprofiled_control_measured"
assert summary["measured_requests_successful"] == 3
assert summary["report_p95_p99"] is False
assert summary["tail_percentile_reason"] == "n3_is_insufficient"
assert summary["outlier_removal"] is False
PY

candidates=(
  result_summary.md
  control_summary.json
  control_results.json
  environment.json
  payload_sha256.txt
  server_command_sha256.txt
  cleanup_status.txt
)
total_bytes=0
for relative_path in "${candidates[@]}"; do
  test -f "${RESULT_DIR}/${relative_path}"
  file_bytes="$(stat -c '%s' "${RESULT_DIR}/${relative_path}")"
  test "${file_bytes}" -le 71680
  total_bytes=$((total_bytes + file_bytes))
done
test "${total_bytes}" -le 71680
```

最终分级：

- `yellow_degraded_minimal_unprofiled_control_measured`：server ready、warmup 成功、3 个 measured 请求全部 token-control 成立、每个都有 64 个精确 token arrival 时间戳且 cleanup=`clean`。
- `red_minimal_unprofiled_control`：server ready、warmup、任一 measured 请求、token-control 或 cleanup 失败。
- `blocked_measurement_semantics`：SSE chunk 合并 token，无法产生真实 token 级 ITL。
- `blocked_repo` / `blocked_preflight` / `blocked_resource`：对应硬门失败。

## 7. 完成边界

- 成功或失败后都停止，不得自动进入 MTP 修复、完整 P6.1、128K、profiler 或 P8.1。
- 不提交或 push 服务器 runtime artifact，不修改主镜像 tracked 文件。
- 不进入或改写 `/data/node0_disk1/liguowei/AK-Infer-Lab-server-local`，不操作 `server-local/runtime-adaptations`，不运行 server-local Git 同步脚本。
- raw server log、Prometheus 快照、NPU 快照和其他大文件只保留在 `server_local/<task_id>/`。
- 服务器只执行本任务；同步 `main` 拉下的其他代码不构成执行授权。
