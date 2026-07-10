# Developer to Server

## 当前任务：P5 DeepSeek-V4-Flash W8A8-MTP 八卡拉起与 128K Context Ladder Smoke

任务 ID：

```text
p5_deepseek_v4_flash_8card_128k_smoke_2026_0710
```

目标：在昇腾服务器宿主机 conda 环境中，使用 vLLM-Ascend 参考参数拉起 `DeepSeek-V4-Flash-w8a8-mtp` 八卡推理服务，并逐档验证 `4096 -> 32768 -> 65536 -> 98304 -> 131072` 输入上下文，每档固定输出 `64 tokens`。本轮 P5 已不再是纯文件 readiness；metadata、runtime 版本、8 卡健康只是前置检查。P5 仍是 smoke，不是 P6 benchmark，不输出 compute-bound、memory-bound、HBM bottleneck、scheduler-bound 或优化收益归因。

核心模型路径：

```text
W8A8_MTP_MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
HF_SOURCE_MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash
```

核心参考参数必须优先尝试：

```text
--max-model-len 135168
--tensor-parallel-size 8
--enable-expert-parallel
--quantization ascend
--enable-prefix-caching
--enable-chunked-prefill
--speculative-config '{"num_speculative_tokens": 1, "method": "mtp"}'
```

## 必须回答

1. 使用服务器本地 `git pull-remote` / `server_local/git_pull_remote_wins.sh` 同步后 commit 是什么？
2. `tests/inference_contracts` 是否通过？
3. W8A8-MTP 路径是否存在，且是否有 `70` 个 canonical `quant_model_weights-*.safetensors` 分片？
4. HF source checkpoint 路径是否存在，且是否有 `46` 个 canonical `model-*.safetensors` 分片？
5. 宿主机 runtime 版本是否记录到：Python、CANN、torch、torch_npu、vLLM、vLLM-Ascend？
6. `npu-smi` 是否能看到 `8` 张 NPU？
7. 首轮含 MTP、`max_num_seqs=16` 的参考参数是否能启动并通过 `/health`？
8. 若首轮不能启动，是否按固定顺序降级：`max_num_seqs 16 -> 4 -> 1`，仍失败才关闭 MTP？
9. 每个已启动 profile 中，context ladder 的最高成功输入长度是多少？
10. 是否至少有一个八卡 DeepSeek 请求成功？目标是否达到 `131072 input + 64 output`？
11. 每个成功请求是否生成固定 `64` tokens？如不一致，请记录实际值和 finish reason。
12. 是否生成 TTFT、TPOT、E2E/client wall、output tokens/s、server stats 摘要、HBM used/free 小表？
13. 最终 P5 状态是 `green`、`yellow` 还是 `red`？
14. 是否遵守邮件正文和每个附件均不超过 70KB，且 raw logs / generated text / 大产物留在服务器？

## 状态分级

- `green`：参考参数包含 MTP，八卡 server ready，且 `131072 input + 64 output` 成功。
- `yellow`：八卡 server ready 且至少一个请求成功，但降低了 `max_num_seqs`、关闭了 MTP，或最高成功输入长度低于 `131072`；只能称 `degraded_smoke`。
- `red`：八卡 server 不能 ready，或没有任何请求成功；回传首个失败命令、错误摘要和服务器 artifact path。

## 执行边界

允许：

- 使用服务器当前宿主机 conda 环境，不使用容器。
- 使用服务器本地 `git pull-remote` / `server_local/git_pull_remote_wins.sh` 同步到远端代码。
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`。
- source `/usr/local/Ascend/nnal/atb/set_env.sh`。
- 使用当前环境已有 `vllm`、`vllm_ascend`、`transformers`、`torch_npu`、`npu-smi`。
- 启动 `vllm serve` 回环 OpenAI API server。
- 采集小摘要、TSV/JSON、命令、exit code、server log excerpt、NPU HBM snapshot。

禁止：

- 不安装、升级、卸载或修复任何包。
- 不创建新 conda 环境。
- 不改 driver、CANN、apt、dpkg、NPU runtime、vLLM 或 vLLM-Ascend 源码。
- 不运行 msprof，不做 request-device aggregate。
- 不运行 P6 controlled benchmark、prefix/chunked/MTP A/B 或并发压测。
- 不把降级启动写成 official baseline。
- 不回传 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。
- 不回传 raw server log、完整 generated text、raw memory samples、大 zip、大 TSV/JSON 或完整实验目录。
- 不输出 compute-bound、memory-bound、HBM bottleneck、scheduler-bound、prefix-cache benefit、MTP benefit 或硬件优化收益归因。

## 建议执行命令

在服务器上执行：

```bash
set -u

cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_8card_128k_smoke_2026_0710
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
SUMMARY_DIR="${ARTIFACT_DIR}/summary"
PYTHON_BIN="${PYTHON_BIN:-/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab/bin/python}"
W8A8_MTP_MODEL_PATH="${W8A8_MTP_MODEL_PATH:-/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp}"
HF_SOURCE_MODEL_PATH="${HF_SOURCE_MODEL_PATH:-/data/node0_disk1/Public/DeepSeek-V4-Flash}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-7000}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-dsv4}"

mkdir -p "${ARTIFACT_DIR}" "${SUMMARY_DIR}"

if [ -x server_local/git_pull_remote_wins.sh ]; then
  server_local/git_pull_remote_wins.sh > "${ARTIFACT_DIR}/git_pull.log" 2>&1
else
  git pull --ff-only > "${ARTIFACT_DIR}/git_pull.log" 2>&1
fi
git_pull_exit_code=$?
echo "${git_pull_exit_code}" > "${ARTIFACT_DIR}/git_pull_exit_code.txt"

{
  echo "run_id=${RUN_ID}"
  echo "commit=$(git rev-parse HEAD)"
  echo "timestamp=$(date -Is)"
  echo "PYTHON_BIN=${PYTHON_BIN}"
  echo "W8A8_MTP_MODEL_PATH=${W8A8_MTP_MODEL_PATH}"
  echo "HF_SOURCE_MODEL_PATH=${HF_SOURCE_MODEL_PATH}"
  echo "HOST=${HOST}"
  echo "PORT=${PORT}"
  echo "SERVED_MODEL_NAME=${SERVED_MODEL_NAME}"
  echo "target_context_ladder=4096,32768,65536,98304,131072"
  echo "output_tokens=64"
  echo "max_model_len=135168"
  echo "policy=p5_smoke_no_bottleneck_claim"
  echo "git_pull_exit_code=${git_pull_exit_code}"
} > "${ARTIFACT_DIR}/run_context.txt"

set +u
source /usr/local/Ascend/cann-9.0.0/set_env.sh 2>/dev/null || true
source /usr/local/Ascend/nnal/atb/set_env.sh 2>/dev/null || true
set -u

export ASCEND_RT_VISIBLE_DEVICES="${ASCEND_RT_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"
export VLLM_USE_V1="${VLLM_USE_V1:-1}"
export VLLM_PLUGINS=ascend
export VLLM_WORKER_MULTIPROC_METHOD="${VLLM_WORKER_MULTIPROC_METHOD:-spawn}"
export LD_PRELOAD="/usr/lib/aarch64-linux-gnu/libjemalloc.so.2:${LD_PRELOAD:-}"
export OMP_PROC_BIND=false
export OMP_NUM_THREADS=8
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export ACL_OP_INIT_MODE=1
export VLLM_ASCEND_ENABLE_FLASHCOMM1=1
export USE_MULTI_GROUPS_KV_CACHE=1
export TASK_QUEUE_ENABLE=1
export HCCL_OP_EXPANSION_MODE=AIV
export HCCL_BUFFSIZE=512
export USE_MULTI_BLOCK_POOL=1

sysctl -w vm.swappiness=0 > "${ARTIFACT_DIR}/sysctl.log" 2>&1 || true
sysctl -w kernel.numa_balancing=0 >> "${ARTIFACT_DIR}/sysctl.log" 2>&1 || true
sysctl kernel.sched_migration_cost_ns=50000 >> "${ARTIFACT_DIR}/sysctl.log" 2>&1 || true

"${PYTHON_BIN}" -m pytest tests/inference_contracts -q \
  > "${ARTIFACT_DIR}/pytest.log" 2>&1
pytest_exit_code=$?
echo "${pytest_exit_code}" > "${ARTIFACT_DIR}/pytest_exit_code.txt"

"${PYTHON_BIN}" - <<'PY' "${ARTIFACT_DIR}" "${W8A8_MTP_MODEL_PATH}" "${HF_SOURCE_MODEL_PATH}"
import csv
import json
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
w8a8 = Path(sys.argv[2])
hf = Path(sys.argv[3])

def json_keys(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}
    return {
        "model_type": data.get("model_type", ""),
        "architectures": ",".join(data.get("architectures", []) or []),
        "max_position_embeddings": data.get("max_position_embeddings", ""),
        "num_hidden_layers": data.get("num_hidden_layers", ""),
        "n_routed_experts": data.get("n_routed_experts", ""),
        "num_experts_per_tok": data.get("num_experts_per_tok", ""),
    }

rows = []
for label, root, shard_pattern, expected in [
    ("w8a8_mtp", w8a8, "quant_model_weights-*.safetensors", 70),
    ("hf_source", hf, "model-*.safetensors", 46),
]:
    canonical_shards = sorted(p for p in root.glob(shard_pattern) if not p.name.startswith("._"))
    index_files = sorted(p.name for p in root.glob("*.index.json") if not p.name.startswith("._"))
    required = ["config.json", "generation_config.json", "tokenizer.json", "tokenizer_config.json"]
    if label == "w8a8_mtp":
        required.extend(["quant_model_description.json", "quant_model_weights.safetensors.index.json"])
    if label == "hf_source":
        required.append("model.safetensors.index.json")
    row = {
        "label": label,
        "path": str(root),
        "exists": str(root.exists()).lower(),
        "canonical_shard_count": len(canonical_shards),
        "expected_shard_count": expected,
        "shard_count_ok": str(len(canonical_shards) == expected).lower(),
        "index_files": ",".join(index_files),
        "missing_required": ",".join(name for name in required if not (root / name).exists()),
    }
    row.update(json_keys(root / "config.json"))
    rows.append(row)

with (artifact_dir / "model_path_metadata.tsv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
PY

"${PYTHON_BIN}" - <<'PY' "${ARTIFACT_DIR}"
import csv
import importlib.metadata as metadata
import platform
import subprocess
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])

def pkg(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "missing"

rows = [
    {"name": "python", "value": platform.python_version()},
    {"name": "torch", "value": pkg("torch")},
    {"name": "torch_npu", "value": pkg("torch-npu")},
    {"name": "vllm", "value": pkg("vllm")},
    {"name": "vllm_ascend", "value": pkg("vllm-ascend")},
]

try:
    import torch_npu  # noqa: F401
    rows.append({"name": "torch_npu_import", "value": "ok"})
except Exception as exc:
    rows.append({"name": "torch_npu_import", "value": f"failed:{type(exc).__name__}:{exc}"})

for cmd_name, cmd in [
    ("npu_smi_path", ["bash", "-lc", "command -v npu-smi || true"]),
    ("cann_version_file", ["bash", "-lc", "cat ${ASCEND_HOME_PATH:-/usr/local/Ascend/cann-9.0.0}/version.info 2>/dev/null | head -20 || true"]),
]:
    value = subprocess.run(cmd, text=True, capture_output=True).stdout.strip().replace("\n", " | ")
    rows.append({"name": cmd_name, "value": value})

with (artifact_dir / "runtime_versions.tsv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=["name", "value"], delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
PY

npu-smi info > "${ARTIFACT_DIR}/npu_smi_info.txt" 2>&1 || true
npu-smi info -t usages > "${ARTIFACT_DIR}/npu_smi_usage_before.txt" 2>&1 || true

VLLM_BIN="${VLLM_BIN:-$(dirname "${PYTHON_BIN}")/vllm}"
if [ ! -x "${VLLM_BIN}" ]; then
  VLLM_BIN="$(command -v vllm || true)"
fi
echo "VLLM_BIN=${VLLM_BIN}" > "${ARTIFACT_DIR}/vllm_bin.txt"

wait_health() {
  local base_url="$1"
  local timeout_sec="$2"
  "${PYTHON_BIN}" - "$base_url" "$timeout_sec" <<'PY'
import sys
import time
import urllib.request

base = sys.argv[1].rstrip("/")
timeout = float(sys.argv[2])
deadline = time.monotonic() + timeout
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(base + "/health", timeout=5) as resp:
            if resp.status == 200:
                sys.exit(0)
    except Exception:
        pass
    time.sleep(5)
sys.exit(1)
PY
}

run_ladder_client() {
  local base_url="$1"
  local profile_dir="$2"
  "${PYTHON_BIN}" - "$base_url" "${SERVED_MODEL_NAME}" "${W8A8_MTP_MODEL_PATH}" "${profile_dir}" <<'PY'
import csv
import json
import sys
import time
import urllib.request
from pathlib import Path
from statistics import median

from transformers import AutoTokenizer

base_url = sys.argv[1].rstrip("/")
served_model_name = sys.argv[2]
model_path = sys.argv[3]
profile_dir = Path(sys.argv[4])

contexts = [4096, 32768, 65536, 98304, 131072]
output_tokens = 64
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

def token_ids_for(label, min_tokens):
    ids = []
    block = 0
    while len(ids) < min_tokens:
        block += 1
        text = "\n".join([
            f"### DeepSeek P5 context ladder block {label} {block:06d}",
            "This deterministic text is used only for a fixed-output smoke request.",
            "It must not be interpreted as workload content or generated result evidence.",
            "Fields: request_id phase timestamp_ns input_tokens output_tokens rss pss hbm.",
        ])
        encoded = tokenizer(text, add_special_tokens=False).input_ids
        if encoded and isinstance(encoded[0], list):
            encoded = encoded[0]
        ids.extend(encoded)
    return ids[:min_tokens]

def stream_request(prompt, context_tokens):
    payload = {
        "model": served_model_name,
        "prompt": prompt,
        "max_tokens": output_tokens,
        "temperature": 0.0,
        "stream": True,
        "min_tokens": output_tokens,
        "ignore_eos": True,
    }
    req = urllib.request.Request(
        base_url + "/v1/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    start = time.perf_counter_ns()
    first = 0
    end = start
    text_chunks = []
    finish_reason = ""
    error = ""
    try:
        with urllib.request.urlopen(req, timeout=7200) as resp:
            http_status = resp.status
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                event = json.loads(data)
                for choice in event.get("choices", []):
                    chunk = choice.get("text") or ""
                    if chunk:
                        if not first:
                            first = time.perf_counter_ns()
                        text_chunks.append(chunk)
                    if choice.get("finish_reason"):
                        finish_reason = str(choice.get("finish_reason"))
        end = time.perf_counter_ns()
        generated_text = "".join(text_chunks)
        generated_ids = tokenizer(generated_text, add_special_tokens=False).input_ids
        if generated_ids and isinstance(generated_ids[0], list):
            generated_ids = generated_ids[0]
        generated_count = len(generated_ids)
        status = "success" if http_status == 200 and generated_count == output_tokens else "failed"
    except Exception as exc:
        http_status = 0
        generated_count = 0
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        end = time.perf_counter_ns()
    ttft_us = (first - start) / 1000 if first else 0
    client_wall_us = (end - start) / 1000
    tpot_us = ((end - first) / 1000 / (generated_count - 1)) if first and generated_count > 1 else 0
    return {
        "context_tokens": context_tokens,
        "max_new_tokens": output_tokens,
        "status": status,
        "http_status": http_status,
        "generated_token_count": generated_count,
        "finish_reason": finish_reason,
        "ttft_us": round(ttft_us, 3),
        "tpot_us": round(tpot_us, 3),
        "client_wall_us": round(client_wall_us, 3),
        "output_tokens_per_s": round(generated_count / (client_wall_us / 1_000_000), 6) if client_wall_us else 0,
        "error": error,
        "policy": "p5_smoke_client_timing_no_bottleneck_claim",
    }

rows = []
for context in contexts:
    ids = token_ids_for(f"context_{context}", context)
    prompt = tokenizer.decode(ids, skip_special_tokens=False)
    rows.append(stream_request(prompt, context))

with (profile_dir / "request_ladder.tsv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

success_contexts = [int(row["context_tokens"]) for row in rows if row["status"] == "success"]
result = {
    "status": "success" if success_contexts else "failed",
    "highest_success_context_tokens": max(success_contexts) if success_contexts else 0,
    "target_context_tokens": 131072,
    "output_tokens": output_tokens,
    "all_rows": rows,
    "policy": "p5_smoke_no_bottleneck_claim",
}
(profile_dir / "ladder_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

stop_profile() {
  local profile_dir="$1"
  if [ -f "${profile_dir}/server_pid.txt" ]; then
    local pid
    pid="$(cat "${profile_dir}/server_pid.txt")"
    kill "-${pid}" >/dev/null 2>&1 || kill "${pid}" >/dev/null 2>&1 || true
    sleep 5
  fi
}

run_profile() {
  local profile_name="$1"
  local max_num_seqs="$2"
  local mtp_mode="$3"
  local profile_dir="${ARTIFACT_DIR}/${profile_name}"
  mkdir -p "${profile_dir}"

  local cmd=(
    "${VLLM_BIN}" serve "${W8A8_MTP_MODEL_PATH}"
    --safetensors-load-strategy prefetch
    --max-model-len 135168
    --max-num-batched-tokens 4096
    --served-model-name "${SERVED_MODEL_NAME}"
    --gpu-memory-utilization 0.92
    --max-num-seqs "${max_num_seqs}"
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
    --additional-config '{"enable_cpu_binding":true,"multistream_overlap_shared_expert":false}'
    --compilation-config '{"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[2,4,6,8,10,12,14,16,18,20,22,24,32,36,40]}'
    --model-loader-extra-config '{"enable_multithread_load":true,"num_threads":16}'
  )
  if [ "${mtp_mode}" = "mtp_on" ]; then
    cmd+=(--speculative-config '{"num_speculative_tokens": 1, "method": "mtp"}')
  fi

  printf '%q ' "${cmd[@]}" > "${profile_dir}/server_command.txt"
  printf '\n' >> "${profile_dir}/server_command.txt"
  npu-smi info -t usages > "${profile_dir}/npu_smi_usage_before_start.txt" 2>&1 || true

  set +e
  setsid "${cmd[@]}" > "${profile_dir}/vllm_server.log" 2>&1 &
  local server_pid=$!
  echo "${server_pid}" > "${profile_dir}/server_pid.txt"
  wait_health "http://${HOST}:${PORT}" 1800
  local ready_exit_code=$?
  echo "${ready_exit_code}" > "${profile_dir}/server_ready_exit_code.txt"
  npu-smi info -t usages > "${profile_dir}/npu_smi_usage_after_start.txt" 2>&1 || true

  if [ "${ready_exit_code}" -eq 0 ]; then
    run_ladder_client "http://${HOST}:${PORT}" "${profile_dir}" \
      > "${profile_dir}/ladder_client.log" 2>&1
    echo "$?" > "${profile_dir}/ladder_client_exit_code.txt"
  else
    echo "server_not_ready" > "${profile_dir}/ladder_client_exit_code.txt"
  fi

  npu-smi info -t usages > "${profile_dir}/npu_smi_usage_after_ladder.txt" 2>&1 || true
  stop_profile "${profile_dir}"
  set -u
}

set +e
run_profile reference_mtp_maxseq16 16 mtp_on

if ! grep -q '"highest_success_context_tokens": 131072' "${ARTIFACT_DIR}/reference_mtp_maxseq16/ladder_result.json" 2>/dev/null; then
  run_profile degraded_mtp_maxseq4 4 mtp_on
fi
if ! grep -q '"highest_success_context_tokens": 131072' "${ARTIFACT_DIR}/degraded_mtp_maxseq4/ladder_result.json" 2>/dev/null \
  && ! grep -q '"highest_success_context_tokens": 131072' "${ARTIFACT_DIR}/reference_mtp_maxseq16/ladder_result.json" 2>/dev/null; then
  run_profile degraded_mtp_maxseq1 1 mtp_on
fi
if ! grep -q '"highest_success_context_tokens": 131072' "${ARTIFACT_DIR}/degraded_mtp_maxseq1/ladder_result.json" 2>/dev/null \
  && ! grep -q '"highest_success_context_tokens": 131072' "${ARTIFACT_DIR}/degraded_mtp_maxseq4/ladder_result.json" 2>/dev/null \
  && ! grep -q '"highest_success_context_tokens": 131072' "${ARTIFACT_DIR}/reference_mtp_maxseq16/ladder_result.json" 2>/dev/null; then
  run_profile degraded_no_mtp_maxseq1 1 mtp_off
fi
set -u

"${PYTHON_BIN}" - <<'PY' "${ARTIFACT_DIR}"
import csv
import json
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
profiles = [
    ("reference_mtp_maxseq16", 16, True),
    ("degraded_mtp_maxseq4", 4, True),
    ("degraded_mtp_maxseq1", 1, True),
    ("degraded_no_mtp_maxseq1", 1, False),
]

rows = []
best = {"profile": "", "highest": 0, "mtp": False, "max_num_seqs": 0}
any_ready = False
for name, max_num_seqs, mtp in profiles:
    root = artifact_dir / name
    if not root.exists():
        continue
    ready = (root / "server_ready_exit_code.txt").read_text(encoding="utf-8", errors="replace").strip() if (root / "server_ready_exit_code.txt").exists() else "missing"
    any_ready = any_ready or ready == "0"
    result_path = root / "ladder_result.json"
    highest = 0
    request_status = "not_run"
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        highest = int(result.get("highest_success_context_tokens") or 0)
        request_status = result.get("status", "missing")
    if highest > best["highest"]:
        best = {"profile": name, "highest": highest, "mtp": mtp, "max_num_seqs": max_num_seqs}
    rows.append({
        "profile": name,
        "max_num_seqs": max_num_seqs,
        "mtp_enabled": str(mtp).lower(),
        "server_ready_exit_code": ready,
        "request_status": request_status,
        "highest_success_context_tokens": highest,
        "server_command": str(root / "server_command.txt"),
        "server_log": str(root / "vllm_server.log"),
    })

if best["highest"] >= 131072 and best["mtp"] and best["max_num_seqs"] == 16:
    grade = "green"
elif any_ready and best["highest"] > 0:
    grade = "yellow"
else:
    grade = "red"

summary = {
    "run_id": artifact_dir.name,
    "p5_grade": grade,
    "best_profile": best["profile"],
    "highest_success_context_tokens": best["highest"],
    "target_context_tokens": 131072,
    "policy": "p5_smoke_no_bottleneck_claim",
    "benchmark_claim": False,
}
(artifact_dir / "p5_result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

with (artifact_dir / "profile_summary.tsv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["profile"], delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

lines = ["path\tsize_bytes\tmail_ok"]
for rel in [
    "run_context.txt",
    "git_pull_exit_code.txt",
    "pytest_exit_code.txt",
    "model_path_metadata.tsv",
    "runtime_versions.tsv",
    "npu_smi_info.txt",
    "p5_result.json",
    "profile_summary.tsv",
]:
    path = artifact_dir / rel
    if path.exists():
        lines.append(f"{path}\t{path.stat().st_size}\t{str(path.stat().st_size <= 70 * 1024).lower()}")
for root in artifact_dir.glob("*"):
    if root.is_dir() and root.name != "summary":
        for rel in ["server_ready_exit_code.txt", "server_command.txt", "ladder_result.json", "request_ladder.tsv"]:
            path = root / rel
            if path.exists():
                lines.append(f"{path}\t{path.stat().st_size}\t{str(path.stat().st_size <= 70 * 1024).lower()}")
(artifact_dir / "mail_attachment_candidates.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")

brief = [
    "## p5_result",
    json.dumps(summary, ensure_ascii=False, indent=2),
    "",
    "## profile_summary",
]
brief.extend("\t".join(str(row.get(key, "")) for key in rows[0].keys()) for row in rows[:0])
for row in rows:
    brief.append(json.dumps(row, ensure_ascii=False))
(artifact_dir / "mail_summary.txt").write_text("\n".join(brief) + "\n", encoding="utf-8")
PY
```

## 回传要求

请邮件正文直接回答“必须回答”里的 14 个问题，并附上 70KB 内小文件。优先附件：

```text
run_context.txt
model_path_metadata.tsv
runtime_versions.tsv
npu_smi_info.txt
p5_result.json
profile_summary.tsv
mail_attachment_candidates.tsv
mail_summary.txt
*/server_ready_exit_code.txt
*/server_command.txt
*/ladder_result.json
*/request_ladder.tsv
```

不要作为附件回传：

```text
raw vllm_server.log
generated text
raw npu-smi time series beyond small snapshots
raw profiler output
large zip
full artifact directory
```

如果某个小文件超过 70KB，请不要附原文件，改在正文中摘录关键行并保留服务器路径。
