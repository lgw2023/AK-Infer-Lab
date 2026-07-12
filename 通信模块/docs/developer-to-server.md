# Developer to Server

## 当前唯一任务：P6.0 no-MTP degraded baseline stabilization

```text
task_id: p6_0_deepseek_v4_flash_w8a8_no_mtp_degraded_stabilization_2026_0713
execution_codebase: main-readonly
ASCEND_RT_VISIBLE_DEVICES: 0,1,2,3,4,5,6,7
```

本轮正式回到 P5→P6/P7→P8 主线。此前 P8.1 observe-only handoff 尚未下发、尚未执行，现已延后为 preflight；不得执行 P8 observer、adapter 或 bundle。

P5 已有 1 次 W8A8、no-MTP、TP8+EP、`FULL_DECODE_ONLY`、`4096+64` 成功。本轮只再执行 2 个相互独立、参数完全相同的 fresh server lifecycle，每个 lifecycle 只发送 1 个相同请求。若两次均成功，则连同 P5 既有成功形成连续 3 次证据，把该 cell 固结为 `yellow_degraded_baseline_stabilized`。这仍不是 official MTP baseline，也不是 P6.1 性能结果。

禁止 MTP、128K/context ladder、eager fallback、并发、warmup/额外请求、profiler、性能归因、offload、placement mutation、runtime/source/site-packages/environment/checkpoint 修改，以及自动进入 P6.1、P8.1。任一新 lifecycle 失败立即停止，不得调参重试。

## 1. 固定基线

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
request: 4096 input token IDs + fixed 64 output tokens
prior accepted success: 1
new fresh lifecycles: 2
requests per lifecycle: 1
```

固定 payload：

```text
path: 工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json
bytes: 19487
sha256: 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
```

## 2. 完整同步 main 与只读安全门

必须完整 fast-forward 同步远程 `main`；不能只拉或 cherry-pick 某个提交。同步全部代码不代表执行全部内容，执行范围只取同步后本文件的当前 task。

服务器主镜像 tracked 文件只读。结果只写 Git 忽略的 `server_local/<task_id>/`。不得修改 tracked 文件，不得 restore/reset/stash，不得 commit 或 push，不得操作 server-local worktree 分支，不得自行选择 ours/theirs。

```bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p6_0_deepseek_v4_flash_w8a8_no_mtp_degraded_stabilization_2026_0713
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
git -C "${REPO_ROOT}" rev-list --left-right --count HEAD...origin/main > "${RESULT_DIR}/ahead_behind.txt"
git -C "${REPO_ROOT}" status --porcelain --untracked-files=no > "${RESULT_DIR}/tracked_status_before.txt"
```

任一条件失败标记 `blocked_repo` 并停止。同步后若 task ID 变化，必须停止并重新读取本文件。

## 3. payload 与 runtime 精确预检

不得重新 tokenize、复制改写 payload 或改变请求字段。

```bash
test -f "${PAYLOAD_PATH}"
test "$(stat -c '%s' "${PAYLOAD_PATH}")" = 19487
test "$(sha256sum "${PAYLOAD_PATH}" | awk '{print $1}')" = 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
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

payload_path = Path(sys.argv[1])
output = Path(sys.argv[2])
source = Path("/data/node0_disk1/vllm-0.22.1")
payload = json.loads(payload_path.read_text(encoding="utf-8"))

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

任何 payload、版本、import root、source commit/clean、五插件、ACL 或可见设备不匹配都标记 `blocked_preflight`，禁止启动 server。不得修改环境来让门通过。

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

## 5. 两个独立 fresh lifecycle

以下命令数组必须逐字复用两次，不得添加 `--enforce-eager`、`--speculative-config` 或修改任何参数。

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

run_lifecycle() {
  local run_id="$1"
  local run_dir="${RESULT_DIR}/lifecycle_${run_id}"
  local server_pid=""
  local ready_exit=1
  mkdir -p "${run_dir}"

  printf '%q ' "${cmd[@]}" > "${run_dir}/server_command.txt"
  printf '\n' >> "${run_dir}/server_command.txt"
  sha256sum "${run_dir}/server_command.txt" > "${run_dir}/server_command_sha256.txt"
  cp "${RESULT_DIR}/environment.json" "${run_dir}/environment.json"
  sha256sum "${run_dir}/environment.json" > "${run_dir}/environment_sha256.txt"
  sha256sum "${PAYLOAD_PATH}" > "${run_dir}/payload_sha256.txt"

  setsid "${cmd[@]}" > "${run_dir}/vllm_server.log" 2>&1 &
  server_pid=$!
  printf '%s\n' "${server_pid}" > "${run_dir}/server_pid.txt"

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
  printf '%s\n' "${ready_exit}" > "${run_dir}/server_ready_exit_code.txt"

  if [ "${ready_exit}" -eq 0 ]; then
    set +e
    "${PYTHON_BIN}" - "${PAYLOAD_PATH}" "${run_dir}/request_result.json" <<'PY'
import json
import sys
import time
import urllib.request
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
payload["stream"] = True
payload["stream_options"] = {"include_usage": True}
payload["return_token_ids"] = True
request = urllib.request.Request(
    "http://127.0.0.1:7000/v1/completions",
    data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    method="POST",
)
start_ns = time.monotonic_ns()
first_token_ns = 0
end_ns = 0
streamed_token_count = 0
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
                end_ns = time.monotonic_ns()
                break
            if not data:
                continue
            chunk = json.loads(data)
            if chunk.get("error"):
                raise RuntimeError(str(chunk["error"]))
            for choice in chunk.get("choices") or []:
                token_ids = choice.get("token_ids") or []
                if token_ids:
                    if first_token_ns == 0:
                        first_token_ns = time.monotonic_ns()
                    streamed_token_count += len(token_ids)
                if choice.get("finish_reason") is not None:
                    finish_reason = str(choice["finish_reason"])
            usage = chunk.get("usage")
            if isinstance(usage, dict):
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")
except Exception as exc:
    error = f"{type(exc).__name__}: {exc}"
    if end_ns == 0:
        end_ns = time.monotonic_ns()

checks = {
    "http_status": status == 200,
    "saw_done": saw_done,
    "prompt_tokens": prompt_tokens == 4096,
    "completion_tokens": completion_tokens == 64,
    "streamed_token_count": streamed_token_count == 64,
    "finish_reason": finish_reason == "length",
    "first_token_seen": first_token_ns > start_ns,
}
record = {
    "status": "success" if all(checks.values()) else "error",
    "http_status": status,
    "prompt_tokens": prompt_tokens,
    "generated_token_count": completion_tokens,
    "streamed_token_count": streamed_token_count,
    "finish_reason": finish_reason,
    "request_start_ns": start_ns,
    "first_token_ns": first_token_ns,
    "request_end_ns": end_ns,
    "checks": checks,
    "error": error,
    "generated_text_retained": False,
    "token_ids_retained": False,
    "claim_boundary": "p6_0_stabilization_diagnostic_timing_not_performance",
}
Path(sys.argv[2]).write_text(
    json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
raise SystemExit(0 if record["status"] == "success" else 1)
PY
    request_exit=$?
    set -e
  else
    request_exit=90
  fi
  printf '%s\n' "${request_exit}" > "${run_dir}/request_exit_code.txt"

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
  npu-smi info > "${run_dir}/npu_smi_after.txt" 2>&1 || true
  npu-smi info -t usages > "${run_dir}/npu_usage_after.txt" 2>&1 || true
  ss -ltnp > "${run_dir}/listening_ports_after.txt" 2>&1 || true
  if ss -ltn | awk '{print $4}' | grep -Eq '(^|:)7000$'; then
    printf '%s\n' port_7000_still_listening > "${run_dir}/cleanup_status.txt"
    return 91
  fi
  printf '%s\n' clean > "${run_dir}/cleanup_status.txt"

  test "${ready_exit}" -eq 0
  test "${request_exit}" -eq 0
}

run_lifecycle 1
run_lifecycle 2
```

必须先完整清理 lifecycle 1 的本任务进程、确认端口释放，再启动 lifecycle 2。若 lifecycle 1 失败，不得执行 lifecycle 2。若本任务进程组经 TERM 后未退出，可以 KILL 该已记录的本任务 process group；不得清理任何其他 PID。

## 6. 一致性验收与分级

```bash
test "$(awk '{print $1}' "${RESULT_DIR}/lifecycle_1/server_command_sha256.txt")" =      "$(awk '{print $1}' "${RESULT_DIR}/lifecycle_2/server_command_sha256.txt")"
test "$(awk '{print $1}' "${RESULT_DIR}/lifecycle_1/environment_sha256.txt")" =      "$(awk '{print $1}' "${RESULT_DIR}/lifecycle_2/environment_sha256.txt")"
test "$(awk '{print $1}' "${RESULT_DIR}/lifecycle_1/payload_sha256.txt")" =      "$(awk '{print $1}' "${RESULT_DIR}/lifecycle_2/payload_sha256.txt")"

"${PYTHON_BIN}" - "${RESULT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
runs = []
for run_id in (1, 2):
    run_dir = root / f"lifecycle_{run_id}"
    request = json.loads((run_dir / "request_result.json").read_text(encoding="utf-8"))
    runs.append({
        "run_id": run_id,
        "server_ready_exit_code": int((run_dir / "server_ready_exit_code.txt").read_text().strip()),
        "request_exit_code": int((run_dir / "request_exit_code.txt").read_text().strip()),
        "request_status": request["status"],
        "http_status": request["http_status"],
        "prompt_tokens": request["prompt_tokens"],
        "generated_token_count": request["generated_token_count"],
        "streamed_token_count": request["streamed_token_count"],
        "finish_reason": request["finish_reason"],
        "cleanup_status": (run_dir / "cleanup_status.txt").read_text().strip(),
    })

success = all(
    item["server_ready_exit_code"] == 0
    and item["request_exit_code"] == 0
    and item["request_status"] == "success"
    and item["http_status"] == 200
    and item["prompt_tokens"] == 4096
    and item["generated_token_count"] == 64
    and item["streamed_token_count"] == 64
    and item["finish_reason"] == "length"
    and item["cleanup_status"] == "clean"
    for item in runs
)
summary = {
    "task_id": "p6_0_deepseek_v4_flash_w8a8_no_mtp_degraded_stabilization_2026_0713",
    "prior_accepted_successes": 1,
    "new_fresh_lifecycles": 2,
    "new_successful_lifecycles": sum(item["request_status"] == "success" for item in runs),
    "consecutive_successes_total": 3 if success else 1 + sum(item["request_status"] == "success" for item in runs),
    "command_drift_count": 0 if success else None,
    "environment_drift_count": 0 if success else None,
    "payload_drift_count": 0 if success else None,
    "runs": runs,
    "grade": "yellow_degraded_baseline_stabilized" if success else "red_degraded_stabilization",
    "official_baseline": False,
    "p6_1_performance_validated": False,
    "mtp_validated": False,
    "context_128k_validated": False,
}
(root / "repeat_results.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
raise SystemExit(0 if success else 1)
PY
```

分级只有：

- `yellow_degraded_baseline_stabilized`：两个新 fresh lifecycle 都 ready、各自唯一 `4096+64` 成功、清理完成，且 command/environment/payload 无漂移；连同前序 P5 成功共连续 3 次。
- `red_degraded_stabilization`：任一 lifecycle 的 ready、请求、固定 token、finish reason、清理或一致性失败。
- `blocked_repo` / `blocked_preflight` / `blocked_resource`：对应硬门失败。

成功仍只能称“no-MTP degraded baseline 已稳定化”，不得称 official baseline、MTP/128K/P6.1 性能已验证。

## 7. 结果摘要、候选清单与传输暂停门

生成 `${RESULT_DIR}/result_summary.md`，必须包含：

- task ID、服务器 Git HEAD、runtime/source commits、模型路径、NPU 范围；
- 前序 P5 成功证据与两个新 fresh lifecycle 的 ready/request/cleanup 结果；
- 两次 command/environment/payload SHA-256 一致性；
- 每次 `4096+64`、HTTP 200、`finish_reason=length` 和客户端退出码；
- 第一失败点（若有）、最终 grade；
- 明确本轮不是 P6.1 benchmark，不验证 MTP、128K、profiler、P8.1 或任何优化收益；
- raw server log 的 server-local 路径，不把 raw log 列入外发候选。

候选外发文件仅允许以下小文件，且单文件与完整集合都必须不超过 70KB：

```text
result_summary.md
repeat_results.json
environment.json
payload_sha256.txt
lifecycle_1/server_command_sha256.txt
lifecycle_1/request_result.json
lifecycle_1/cleanup_status.txt
lifecycle_2/server_command_sha256.txt
lifecycle_2/request_result.json
lifecycle_2/cleanup_status.txt
```

生成 `${RESULT_DIR}/delivery_candidates.tsv`，每行记录相对路径、bytes、SHA-256、敏感性。再生成 `${RESULT_DIR}/transfer_preflight.md`，明确：

```text
summary_path: <绝对路径>
attachment_scope: <上述精确列表>
total_bytes: <精确值>
set_sha256: <对候选 path/bytes/hash 清单计算的 SHA-256>
sensitivity: internal_runtime_diagnostics_no_token_or_generated_text
available_methods: email, upload-api, server-local
recommended_method: upload-api
recommendation_reason: one_named_multi_file_session_preserves_the_exact_small_package_and_hashes
selected_method: none
transfer_status: waiting_for_user_choice
```

当前未选择 `email`、`upload-api` 或 `server-local`。完成后只保留 server-local 结果并停止；禁止发送邮件、附件、upload-api 请求或状态正文，不得沿用历史传输选择。任何未来传输失败都必须停止并取得新的明确选择，不能自动重试或切换渠道。

## 8. 完成边界

- 成功或失败后都停止，不自动进入 P6.1、P8.1、MTP 修复或 128K ladder。
- 不提交或 push 服务器 runtime artifact，不修改主镜像 tracked 文件。
- raw server log、NPU 快照和其他大文件只保留在 `server_local/<task_id>/`。
- 服务器只执行本任务；同步 `main` 拉下来的其他代码不构成执行授权。
