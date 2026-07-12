# Developer to Server

## 当前任务：DeepSeek-V4-Flash W8A8 八卡 no-MTP tokenizer MRO 单请求重试

任务 ID：

```text
p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712
```

继续使用用户已授权的设备范围：

```text
ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
```

本轮只回答一个问题：把上轮过严的 tokenizer 顶层类名断言改为 DSV4 backend MRO 校验后，已能 ready 的 W8A8、TP8+EP、no-MTP、`FULL_DECODE_ONLY` graph server 能否完成一个 `4096 input + 64 output` 请求。

只允许一个 profile：

```text
base_no_mtp_graph_maxseq1_tokenizer_mro_fixed
```

禁止 eager fallback、MTP、context ladder、P6、profiler、offload、并发、性能归因、config/checkpoint patch、site-packages patch、环境升级或重建。

## 1. 上轮结果与本轮唯一变量

上轮任务 `p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_retry_v0221rc1_2026_0712` 结果为：

```text
red_client_tokenizer_class_assertion
```

已知事实：

- `DeepseekV4Tokenizer.from_pretrained(local_files_only=True)` 成功返回 `CachedDSV4TokenizersBackend`；
- runtime MRO 含 `DSV4TokenizersBackend`；
- 已生成恰好 4096 个 token ID，范围 `16..90868`，全部小于 tokenizer size `129283`；
- handoff 的 `type(tokenizer).__name__.startswith("DSV4")` 与 vLLM `get_cached_tokenizer()` 增加 `Cached` 前缀的固定语义冲突；
- 断言发生在 `tokenizer_preflight.json` 和 `request_payload.json` 写入之前；
- 按硬门正确停止，server、形式化 runtime/resource gate、NPU 0-7 和 HTTP 请求均未执行；
- 前一轮 no-MTP graph server-ready 证据不变，本轮不重新解释为新的 server 结果。

模型对象仍是同一 W8A8 70 分片、约 `279.41 GiB` checkpoint；本轮不修改、转换或重新选择模型。

证据边界：上轮已收到 tokenizer diagnostic，可直接核对 runtime class、MRO 和 4096-token 范围；但 payload 文件、server 日志和 request 结果均未生成。前一轮全 rank graph-ready 仍是服务器摘要证据。本轮必须把 tokenizer preflight、graph-ready 和 request result 的小证据一并留存。

本轮唯一变量是客户端 tokenizer runtime identity 断言：

```text
保留: vllm.tokenizers.deepseek_v4.DeepseekV4Tokenizer
删除: 顶层 runtime class 必须 startswith("DSV4")
改为: runtime MRO 至少一个 class name startswith("DSV4")
禁止: transformers.AutoTokenizer
```

服务器 runtime、模型、设备、TP/EP、graph、`max_num_seqs=1`、`--quantization ascend`、插件与 CANN/ATB 路径全部保持不变。

## 2. Git 同步和禁止项

1. 完整同步远程 `main`，不要只 cherry-pick 单个提交。
2. 重新打开拉取后的本文档，只执行本任务 ID。
3. 执行前记录 server-local `HEAD`、`origin/main`、ahead/behind 和 working-tree clean 状态。
4. 不修改 vLLM、vLLM-Ascend、checkpoint、conda 环境、CANN/ATB、系统路径或服务器 Git 历史。
5. 禁止主动终止、暂停或影响任何非本任务进程。

## 3. 固定路径与环境

```bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712
ARTIFACT_DIR="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/${TASK_ID}"
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
PYTHON_BIN="${ENV_PREFIX}/bin/python"
VLLM_BIN="${ENV_PREFIX}/bin/vllm"
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
SERVED_MODEL_NAME=deepseek-v4-flash-w8a8-mtp
HOST=127.0.0.1
PORT=7000

mkdir -p "${ARTIFACT_DIR}"
cd "${REPO_ROOT}"

export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
unset PYTHONPATH
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
CANN_GENERATED_PYTHONPATH="${PYTHONPATH:-}"
printf '%s\n' "${CANN_GENERATED_PYTHONPATH}" > "${ARTIFACT_DIR}/cann_generated_pythonpath.txt"

export PYTHONPATH="${CANN_GENERATED_PYTHONPATH}"
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
```

必须保留 source CANN/ATB 生成的 `PYTHONPATH`，不允许 source 后再 unset，不允许加入 project overlay 或 `sitecustomize`。

## 4. 非 NPU server 预检：DeepSeek-V4 tokenizer 与 4096-token payload

本步必须在启动 vLLM server 之前执行。它只读本地 tokenizer 文件并生成 token ID payload，不加载模型权重，不初始化 NPU runtime。

```bash
set +e
"${PYTHON_BIN}" - "${MODEL_PATH}" "${ARTIFACT_DIR}" <<'PY'
import hashlib
import importlib.metadata
import inspect
import json
import sys
from pathlib import Path

from vllm.tokenizers.deepseek_v4 import DeepseekV4Tokenizer

model_path = Path(sys.argv[1])
artifact_dir = Path(sys.argv[2])
payload_path = artifact_dir / "request_payload.json"
result_path = artifact_dir / "tokenizer_preflight.json"

tokenizer = DeepseekV4Tokenizer.from_pretrained(
    str(model_path),
    local_files_only=True,
)

ids: list[int] = []
block = 0
while len(ids) < 4096:
    block += 1
    text = (
        f"DeepSeek P5 tokenizer retry block {block:07d}. "
        "Synthetic smoke input with no private or generated content.\n"
    )
    ids.extend(tokenizer.encode(text, add_special_tokens=False))

prompt_ids = ids[:4096]
tokenizer_size = len(tokenizer)
tokenizer_runtime_class = type(tokenizer).__name__
tokenizer_runtime_mro = [cls.__name__ for cls in type(tokenizer).__mro__]
dsv4_backend_mro = [name for name in tokenizer_runtime_mro if name.startswith("DSV4")]
tokenizer_module_path = str(Path(inspect.getfile(DeepseekV4Tokenizer)).resolve())
assert len(prompt_ids) == 4096
assert all(isinstance(token_id, int) for token_id in prompt_ids)
assert all(0 <= token_id < tokenizer_size for token_id in prompt_ids)
assert dsv4_backend_mro
assert tokenizer_module_path == "/data/node0_disk1/vllm-0.22.1/vllm/tokenizers/deepseek_v4.py"

payload = {
    "model": "deepseek-v4-flash-w8a8-mtp",
    "prompt": prompt_ids,
    "max_tokens": 64,
    "min_tokens": 64,
    "ignore_eos": True,
    "temperature": 0.0,
    "stream": True,
    "stream_options": {"include_usage": True},
}
payload_bytes = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
payload_path.write_bytes(payload_bytes)

result = {
    "status": "pass",
    "tokenizer_loader": "vllm.tokenizers.deepseek_v4.DeepseekV4Tokenizer",
    "tokenizer_runtime_class": tokenizer_runtime_class,
    "tokenizer_runtime_mro": tokenizer_runtime_mro,
    "dsv4_backend_mro": dsv4_backend_mro,
    "tokenizer_module_path": tokenizer_module_path,
    "transformers_version": importlib.metadata.version("transformers"),
    "local_files_only": True,
    "prompt_token_count": len(prompt_ids),
    "tokenizer_size": tokenizer_size,
    "min_token_id": min(prompt_ids),
    "max_token_id": max(prompt_ids),
    "request_payload_bytes": len(payload_bytes),
    "request_payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
    "npu_server_started": False,
}
result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
PY
CLIENT_PREFLIGHT_EXIT=$?
set -e
printf '%s\n' "${CLIENT_PREFLIGHT_EXIT}" > "${ARTIFACT_DIR}/client_preflight_exit_code.txt"
```

硬门：

- `client_preflight_exit_code.txt` 必须为 `0`；
- `tokenizer_preflight.json.status` 必须为 `pass`；
- `prompt_token_count` 必须恰好为 `4096`；
- tokenizer module path 必须精确来自固定 vLLM `v0.22.1` 源码；
- runtime MRO 必须至少包含一个类名以 `DSV4` 开头；顶层 runtime class 允许是 `CachedDSV4TokenizersBackend`，不得再要求其以 `DSV4` 开头；
- payload SHA-256 和 bytes 必须记录；
- 本步失败则标记 `red_client_tokenizer_preflight`，立即停止，禁止启动 vLLM server。

不允许改用 `AutoTokenizer`，不允许通过改 `config.json`、`rope_scaling`、transformers 版本或 checkpoint 来让预检通过。

## 5. runtime/import 与八卡资源门

预检通过后，用现有命令只读核对：

- Python `3.11.15`；
- torch `2.10.0+cpu`；
- torch-npu `2.10.0`；
- vLLM `0.22.1`，import root `/data/node0_disk1/vllm-0.22.1/vllm`；
- vLLM source commit `0decac0d96c42b49572498019f0a0e3600f50398` 且 clean；
- vLLM-Ascend `0.22.1rc1`；
- `acl` origin 位于 `/usr/local/Ascend/`，parent process 可 import `acl.rt.memcpy`；
- 模型 70 个连续分片、权重 bytes `300013759966`；
- 完整五插件值与第 3 节一致。

执行：

```bash
set +e
"${PYTHON_BIN}" - "${MODEL_PATH}" "${ARTIFACT_DIR}/preflight.json" <<'PY'
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

model = Path(sys.argv[1])
output = Path(sys.argv[2])
source = Path("/data/node0_disk1/vllm-0.22.1")
expected_plugins = (
    "ascend,ascend_kv_connector,ascend_model_loader,"
    "ascend_service_profiling,ascend_model"
)
shards = sorted(model.glob("quant_model_weights-*-of-00070.safetensors"))

def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(source), *args], text=True
    ).strip()

errors: list[str] = []
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
    "canonical_shard_count": len(shards),
    "weight_bytes": sum(path.stat().st_size for path in shards),
    "vllm_plugins": os.environ.get("VLLM_PLUGINS", ""),
    "pythonpath": os.environ.get("PYTHONPATH", ""),
    "required_files": {
        name: (model / name).is_file()
        for name in [
            "config.json", "generation_config.json", "tokenizer.json",
            "tokenizer_config.json", "quant_model_description.json",
            "quant_model_weights.safetensors.index.json",
        ]
    },
    "acl_origin": "",
    "acl_rt_memcpy_imported": False,
}

try:
    import acl
    from acl.rt import memcpy  # noqa: F401
    result["acl_origin"] = str(Path(acl.__file__).resolve())
    result["acl_rt_memcpy_imported"] = True
except Exception as exc:
    errors.append(f"acl_import:{type(exc).__name__}:{exc}")

checks = {
    "python": result["python"] == "3.11.15",
    "torch": result["torch"] == "2.10.0+cpu",
    "torch_npu": result["torch_npu"] == "2.10.0",
    "vllm": str(result["vllm"]).startswith("0.22.1"),
    "vllm_ascend": result["vllm_ascend"] == "0.22.1rc1",
    "vllm_root": result["vllm_root"] == "/data/node0_disk1/vllm-0.22.1/vllm",
    "vllm_source_commit": result["vllm_source_commit"] == "0decac0d96c42b49572498019f0a0e3600f50398",
    "vllm_source_clean": result["vllm_source_clean"] is True,
    "shard_count": result["canonical_shard_count"] == 70,
    "weight_bytes": result["weight_bytes"] == 300013759966,
    "required_files": all(result["required_files"].values()),
    "plugins": result["vllm_plugins"] == expected_plugins,
    "acl_origin": result["acl_origin"].startswith("/usr/local/Ascend/"),
    "acl_rt_memcpy": result["acl_rt_memcpy_imported"] is True,
}
errors.extend(name for name, passed in checks.items() if not passed)
result["checks"] = checks
result["errors"] = errors
result["preflight_ok"] = not errors
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
raise SystemExit(0 if result["preflight_ok"] else 1)
PY
PRECHECK_EXIT=$?
set -e
printf '%s\n' "${PRECHECK_EXIT}" > "${ARTIFACT_DIR}/precheck_exit_code.txt"
```

任一不匹配则 `blocked_preflight`，不启动服务。

再记录：

```bash
npu-smi info > "${ARTIFACT_DIR}/npu_smi_before.txt" 2>&1 || true
npu-smi info -t usages > "${ARTIFACT_DIR}/npu_usage_before.txt" 2>&1 || true
ss -ltnp > "${ARTIFACT_DIR}/listening_ports_before.txt" 2>&1 || true

RESOURCE_GATE=not_confirmed
# 只有人工确认 NPU 0-7 全部 Health=OK、无不明进程、空闲且 127.0.0.1:7000 未占用后，才可改为 pass。
printf '%s\n' "${RESOURCE_GATE}" > "${ARTIFACT_DIR}/resource_gate.txt"
```

若发现任意卡被占用、不健康、存在归属不明进程或端口冲突，写 `blocked_resource` 并停止。不得复用任何历史一次性进程清理授权。

## 6. 唯一允许的 no-MTP graph server

只有第 4、5 节全部通过后才执行。

```bash
PROFILE_DIR="${ARTIFACT_DIR}/base_no_mtp_graph_maxseq1_tokenizer_mro_fixed"
mkdir -p "${PROFILE_DIR}"

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

printf '%q ' "${cmd[@]}" > "${PROFILE_DIR}/server_command.txt"
printf '\n' >> "${PROFILE_DIR}/server_command.txt"

setsid "${cmd[@]}" > "${PROFILE_DIR}/vllm_server.log" 2>&1 &
SERVER_PID=$!
printf '%s\n' "${SERVER_PID}" > "${PROFILE_DIR}/server_pid.txt"

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
printf '%s\n' "${READY_EXIT}" > "${PROFILE_DIR}/server_ready_exit_code.txt"
```

不得加 `--enforce-eager`，不得加 `--speculative-config`，不得修改 graph capture sizes、`max_num_seqs`、TP/EP、DSA-CP 或其他 runtime 参数。

若 server 未 ready，写 `red_server_not_ready`，保留首错后停止；禁止转 eager。

## 7. 只发送一个已预验证 payload

仅当 `READY_EXIT=0` 时执行：

```bash
set +e
"${PYTHON_BIN}" - "http://${HOST}:${PORT}" "${ARTIFACT_DIR}/request_payload.json" "${PROFILE_DIR}" <<'PY' \
  > "${PROFILE_DIR}/request_client.log" 2>&1
import json
import sys
import time
import urllib.request
from pathlib import Path

base = sys.argv[1].rstrip("/")
payload_path = Path(sys.argv[2])
profile_dir = Path(sys.argv[3])
payload = json.loads(payload_path.read_text(encoding="utf-8"))

assert isinstance(payload.get("prompt"), list)
assert len(payload["prompt"]) == 4096
assert payload.get("max_tokens") == 64
assert payload.get("min_tokens") == 64

request = urllib.request.Request(
    base + "/v1/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    method="POST",
)

start = time.perf_counter_ns()
first = 0
http_status = 0
prompt_tokens = 0
completion_tokens = 0
finish_reason = ""
error = ""

try:
    with urllib.request.urlopen(request, timeout=900) as response:
        http_status = int(response.status)
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            event = json.loads(data)
            usage = event.get("usage") or {}
            prompt_tokens = max(prompt_tokens, int(usage.get("prompt_tokens") or 0))
            completion_tokens = max(completion_tokens, int(usage.get("completion_tokens") or 0))
            for choice in event.get("choices", []):
                if choice.get("text") and not first:
                    first = time.perf_counter_ns()
                if choice.get("finish_reason"):
                    finish_reason = str(choice["finish_reason"])
except Exception as exc:
    error = f"{type(exc).__name__}: {exc}"

end = time.perf_counter_ns()
success = http_status == 200 and prompt_tokens == 4096 and completion_tokens == 64
result = {
    "status": "success" if success else "failed",
    "http_status": http_status,
    "prompt_tokens": prompt_tokens,
    "requested_output_tokens": 64,
    "generated_token_count": completion_tokens,
    "finish_reason": finish_reason,
    "ttft_us": round((first - start) / 1000, 3) if first else 0.0,
    "client_wall_us": round((end - start) / 1000, 3),
    "error": error,
    "claim_boundary": "p5_failure_isolation_smoke_not_benchmark",
}
(profile_dir / "request_result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(result, ensure_ascii=False))
raise SystemExit(0 if success else 1)
PY
REQUEST_EXIT=$?
set -e
printf '%s\n' "${REQUEST_EXIT}" > "${PROFILE_DIR}/request_client_exit_code.txt"
```

不保存完整生成文本；只保存 token count、finish reason、HTTP 状态和仅供 smoke 的 client timing。

## 8. 有界证据、分级与清理

```bash
grep -nE 'Loading model weights took|Loading weights took|Saved compiled graph to cache|Application startup complete|GET /health|Traceback|ERROR|Error|Exception|Assertion|unsupported|not supported|OutOfMemory|OOM|HCCL|positions_cpu' \
  "${PROFILE_DIR}/vllm_server.log" | head -n 260 > "${PROFILE_DIR}/graph_ready_and_failure_excerpt.txt" || true

npu-smi info -t usages > "${PROFILE_DIR}/npu_usage_after_request.txt" 2>&1 || true

if [ -f "${PROFILE_DIR}/server_pid.txt" ]; then
  OWN_PID="$(cat "${PROFILE_DIR}/server_pid.txt")"
  kill -- "-${OWN_PID}" >/dev/null 2>&1 || kill "${OWN_PID}" >/dev/null 2>&1 || true
  sleep 10
fi

npu-smi info > "${ARTIFACT_DIR}/npu_smi_after.txt" 2>&1 || true
npu-smi info -t usages > "${ARTIFACT_DIR}/npu_usage_after.txt" 2>&1 || true
ss -ltnp > "${ARTIFACT_DIR}/listening_ports_after.txt" 2>&1 || true
```

只能终止本任务记录的 `SERVER_PID` / process group。清理后必须报告 NPU 0-7 和 7000 端口是否恢复。

分级：

- `yellow_no_mtp_graph_request_success`：client preflight 通过、server ready、HTTP 200、`prompt_tokens=4096`、`generated_token_count=64`；
- `red_client_tokenizer_preflight`：专用 tokenizer 或 payload gate 在 server 启动前失败；
- `red_server_not_ready`：preflight/resource 通过但相同 graph server 未 ready；
- `red_request_runtime`：server ready 但唯一请求未完成精确 `4096+64`；
- `blocked_preflight` / `blocked_resource`：对应硬门未通过。

任何 yellow 都只验证当前 no-MTP graph cell；MTP、128K ladder、P6 和性能仍未验证。

## 9. 结果摘要与传输等待门

服务器本地生成：

```text
${ARTIFACT_DIR}/result_summary.md
${ARTIFACT_DIR}/delivery_candidates.tsv
${ARTIFACT_DIR}/task_status.txt
```

`result_summary.md` 必须回答：

- task ID、Git 三方状态与完整同步方式；
- 环境/import roots/source commit/clean；
- tokenizer loader/runtime class/runtime MRO/匹配的 DSV4 backend/module path、prompt token count、token ID range、payload bytes/SHA-256 和 preflight exit；
- 八卡资源门、ACL origin、五插件；
- 完整 shell-escaped server command、ready/request exit；
- 8 worker weight-load、graph cache/startup/health 有界证据；
- HTTP status、prompt/output tokens、finish reason 和仅供 smoke 的 client timing；
- 首错阶段、最终 grade、进程清理、NPU/端口恢复；
- raw log server-local 路径；
- 明确“P5 failure-isolation smoke，不是 P6 benchmark；no-MTP 成功不代表 MTP 或 128K 已验证”。

`delivery_candidates.tsv` 每行列出：

```text
path    size_bytes    sha256    sensitivity    email_feasible    upload_api_feasible    recommended_method    reason
```

候选小文件优先包含：

```text
result_summary.md
preflight.json
client_preflight_exit_code.txt
tokenizer_preflight.json
git_head.txt
resource_gate.txt
task_status.txt
base_no_mtp_graph_maxseq1_tokenizer_mro_fixed/server_command.txt
base_no_mtp_graph_maxseq1_tokenizer_mro_fixed/server_ready_exit_code.txt
base_no_mtp_graph_maxseq1_tokenizer_mro_fixed/request_client_exit_code.txt
base_no_mtp_graph_maxseq1_tokenizer_mro_fixed/request_result.json
base_no_mtp_graph_maxseq1_tokenizer_mro_fixed/request_client.log
base_no_mtp_graph_maxseq1_tokenizer_mro_fixed/graph_ready_and_failure_excerpt.txt
```

`request_payload.json`、raw `vllm_server.log`、完整 NPU SMI、模型、生成文本和整个目录保持 server-local，不列为默认传输候选。

`delivery_candidates.tsv` 是控制清单，不得把自身列入自身表格并预填自身最终 size/SHA-256。表格完成后，再在当前任务会话中用 `stat` 和 `sha256sum` 报告该控制文件的最终 bytes/SHA-256；若用户批准传输清单，再把这个会话外报告的最终值纳入确认范围。

本轮是新的结果范围，尚未获得 `email`、`upload-api` 或 `server-local` 选择。生成摘要和候选清单后，只在当前任务会话报告每个候选的精确路径、bytes、SHA-256、敏感性、可用方式和一个推荐方式，然后暂停。

确认前禁止发送邮件、附件、upload-api 预检或上传，也禁止测试邮件或状态正文先行。任何传输失败都停止并重新请求选择，不自动重试、改名、扩展范围、补发邮件或切换渠道。

## 10. 完成边界

- 成功只把 P5 记为 no-MTP yellow，并给开发机提供是否冻结该 baseline cell 的证据。
- 不自动进入 P6，不自动创建或启用 P8 adapter；这些由开发机根据回传另行决定。
- 失败时按上述首错分类停止，不即兴尝试第二个 profile。
- 不提交 server runtime artifact，除非后续任务明确指定小文件归档范围。
