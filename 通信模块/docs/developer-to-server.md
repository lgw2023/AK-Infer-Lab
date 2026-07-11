# Developer to Server

## 当前任务：DeepSeek-V4-Flash W8A8-MTP 八卡启动与 Context Ladder

任务 ID：

```text
p5_deepseek_v4_flash_w8a8_8card_context_smoke_v0221rc1_2026_0712
```

用户已明确授权本轮设备范围：

```text
ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
```

本轮只执行 P5 smoke：在现有 vLLM `0.22.1+empty` / vLLM-Ascend `0.22.1rc1` 独立环境中，以 W8A8-MTP checkpoint、TP8+EP、`--quantization ascend` 运行 `vllm serve`，并顺序验证：

```text
4096 -> 32768 -> 65536 -> 98304 -> 131072 input tokens
每档固定输出 64 tokens
```

本轮不是 P6 benchmark，不运行 profiler、offload、并发压测、A/B 或瓶颈归因。

## 1. 已知结论与本轮对象

唯一执行模型：

```text
/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
70 个 quant_model_weights-*.safetensors
总权重 300013759966 bytes，约 279.41 GiB
```

历史 mixed FP8+FP4 checkpoint `/data/node0_disk1/Public/DeepSeek-V4-Flash` 已退出执行，只保留诊断 inventory。禁止启动、适配、转换或作为 fallback。

上轮已证明目标 0.22.1rc1 栈的 Ascend model route、allocator redirect 和 CANN ACL 路径可用。必须保留两项已验证修正：

```text
VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
先清理旧 PYTHONPATH，再 source CANN/ATB；source 后不得再次清空其生成的 PYTHONPATH
```

禁止退回 `VLLM_PLUGINS=ascend` 单值，也禁止在 source 后 `unset PYTHONPATH`。

## 2. 完整同步远程 main

```bash
set -euo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab

if [ -x server_local/git_pull_remote_wins.sh ]; then
  server_local/git_pull_remote_wins.sh
else
  git fetch origin main
  git merge --ff-only origin/main
fi

git fetch origin main
printf 'local_head=%s\n' "$(git rev-parse HEAD)"
printf 'origin_main=%s\n' "$(git rev-parse origin/main)"
printf 'ahead_behind=%s\n' "$(git rev-list --left-right --count HEAD...origin/main)"
```

必须完整 fast-forward，满足 `HEAD == origin/main` 且 ahead/behind=`0 0`，再重新打开拉取后的本文档。禁止只拉一个提交、`cherry-pick`、detached checkout 或单文件覆盖。

## 3. 固定环境与边界

```text
项目：/data/node0_disk1/liguowei/AK-Infer-Lab
环境：/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
vLLM 源码：/data/node0_disk1/vllm-0.22.1
vLLM commit：0decac0d96c42b49572498019f0a0e3600f50398
vLLM-Ascend：0.22.1rc1
模型：/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
```

允许：

- 只读复用上述环境、源码和模型；
- source 官方 CANN/ATB `set_env.sh`；
- 使用 NPU 0-7 启动本任务自己的 TP8/EP vLLM 进程；
- 只停止本任务保存 PID/进程组所对应的进程；
- 生成 server-local 日志、小摘要、TSV/JSON、命令与 NPU 前后快照。

禁止：

- 禁止 `conda create`、`pip install`、`pip uninstall`、升级、降级、重建或修复环境；
- 禁止修改 vLLM、vLLM-Ascend、site-packages、模型 config/权重、CANN、ATB、driver、firmware、apt 或系统参数；
- 禁止 `sitecustomize.py`、项目 overlay、user-site、硬编码 ACL 路径或手工复制/软链模块；
- 禁止主动终止、暂停或影响任何非本任务进程；发现任一卡繁忙或端口冲突时记录 `blocked_resource` 并停止；
- 禁止 mixed checkpoint、P6、msprof、request-device aggregate、KV/expert offload、并发压测或其他模型；
- 禁止把 P5 smoke 的时延或吞吐写成 benchmark、compute-bound、memory-bound、HBM bottleneck、scheduler-bound 或优化收益结论；
- 禁止发送邮件、附件或调用 upload-api，直到用户对本轮生成的精确文件范围重新选择传输方式。

## 4. 资源门与预检

先执行并人工核对 NPU 0-7：八卡都必须健康、空闲、无冲突计算进程且具备足够空闲 HBM。只观察进程；不得 kill、暂停、迁移或接管任何未知进程。

```bash
set +e
set -uo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_w8a8_8card_context_smoke_v0221rc1_2026_0712
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
ENV_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
PYTHON_BIN="${ENV_DIR}/bin/python"
VLLM_BIN="${ENV_DIR}/bin/vllm"
VLLM_SRC=/data/node0_disk1/vllm-0.22.1
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
HOST=127.0.0.1
PORT=7000
SERVED_MODEL_NAME=deepseek-v4-flash-w8a8-mtp
OFFICIAL_ASCEND_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model

mkdir -p "${ARTIFACT_DIR}"
printf '%s\n' "$(git rev-parse HEAD)" > "${ARTIFACT_DIR}/git_head.txt"
npu-smi info > "${ARTIFACT_DIR}/npu_smi_before.txt" 2>&1 || true
npu-smi info -t usages > "${ARTIFACT_DIR}/npu_usage_before.txt" 2>&1 || true
ss -ltnp 2>/dev/null | grep -E ":${PORT}([[:space:]]|$)" > "${ARTIFACT_DIR}/port_${PORT}_before.txt" || true

PRECHECK_EXIT=0
[ -x "${PYTHON_BIN}" ] || PRECHECK_EXIT=10
[ -x "${VLLM_BIN}" ] || PRECHECK_EXIT=11
[ -d "${MODEL_PATH}" ] || PRECHECK_EXIT=12
[ "$(git -C "${VLLM_SRC}" rev-parse HEAD 2>/dev/null)" = "0decac0d96c42b49572498019f0a0e3600f50398" ] || PRECHECK_EXIT=13
[ -z "$(git -C "${VLLM_SRC}" status --short 2>/dev/null)" ] || PRECHECK_EXIT=14
[ ! -s "${ARTIFACT_DIR}/port_${PORT}_before.txt" ] || PRECHECK_EXIT=15

unset PYTHONPATH
set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
export PATH="${ENV_DIR}/bin:${PATH}"
export PYTHONNOUSERSITE=1
CANN_GENERATED_PYTHONPATH="${PYTHONPATH:-}"
export CANN_GENERATED_PYTHONPATH
printf '%s\n' "${CANN_GENERATED_PYTHONPATH}" > "${ARTIFACT_DIR}/cann_generated_pythonpath.txt"

case ":${CANN_GENERATED_PYTHONPATH}:" in
  *:/data/node0_disk1/liguowei/AK-Infer-Lab:*|*sitecustomize*) PRECHECK_EXIT=16 ;;
esac

ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 \
VLLM_PLUGINS="${OFFICIAL_ASCEND_PLUGINS}" \
"${PYTHON_BIN}" - "${ARTIFACT_DIR}/preflight.json" "${MODEL_PATH}" <<'PY'
import glob
import json
import sys
from importlib.metadata import version
from pathlib import Path

import torch
import torch_npu
import vllm
import vllm_ascend

output = Path(sys.argv[1])
model = Path(sys.argv[2])
shards = sorted(
    Path(p) for p in glob.glob(str(model / "quant_model_weights-*.safetensors"))
    if not Path(p).name.startswith("._")
)
weight_bytes = sum(p.stat().st_size for p in shards)
result = {
    "python": sys.version.split()[0],
    "torch": torch.__version__,
    "torch_npu": version("torch-npu"),
    "vllm": vllm.__version__,
    "vllm_ascend": version("vllm-ascend"),
    "vllm_root": str(Path(vllm.__file__).resolve().parent),
    "vllm_ascend_root": str(Path(vllm_ascend.__file__).resolve().parent),
    "npu_available": bool(torch.npu.is_available()),
    "visible_device_count": int(torch.npu.device_count()),
    "model_path": str(model),
    "canonical_shard_count": len(shards),
    "weight_bytes": weight_bytes,
    "required_files": {
        name: (model / name).is_file()
        for name in [
            "config.json",
            "generation_config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "quant_model_description.json",
            "quant_model_weights.safetensors.index.json",
        ]
    },
    "acl_origin": "",
    "acl_origin_under_usr_local_Ascend": False,
}
try:
    import acl
    from acl.rt import memcpy
    origin = str(Path(acl.__file__).resolve())
    result["acl_origin"] = origin
    result["acl_origin_under_usr_local_Ascend"] = origin.startswith("/usr/local/Ascend/")
    result["acl_rt_memcpy_imported"] = memcpy is not None
except Exception as exc:
    result["acl_error"] = f"{type(exc).__name__}: {exc}"

ok = (
    result["torch"].startswith("2.10.0")
    and result["torch_npu"] == "2.10.0"
    and result["vllm"].startswith("0.22.1")
    and result["vllm_ascend"] == "0.22.1rc1"
    and result["vllm_root"] == "/data/node0_disk1/vllm-0.22.1/vllm"
    and result["npu_available"] is True
    and result["visible_device_count"] == 8
    and result["canonical_shard_count"] == 70
    and result["weight_bytes"] == 300013759966
    and all(result["required_files"].values())
    and result["acl_origin_under_usr_local_Ascend"] is True
    and result.get("acl_rt_memcpy_imported") is True
)
result["preflight_ok"] = ok
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
sys.exit(0 if ok else 3)
PY
PY_PREFLIGHT_EXIT=$?
if [ "${PY_PREFLIGHT_EXIT}" -ne 0 ] && [ "${PRECHECK_EXIT}" -eq 0 ]; then PRECHECK_EXIT=17; fi

"${PYTHON_BIN}" -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest.log" 2>&1
PYTEST_EXIT=$?
if [ "${PYTEST_EXIT}" -ne 0 ] && [ "${PRECHECK_EXIT}" -eq 0 ]; then PRECHECK_EXIT=18; fi

printf '%s\n' "${PRECHECK_EXIT}" > "${ARTIFACT_DIR}/precheck_exit_code.txt"
```

人工资源门必须在启动前再确认一次：

- `npu-smi` 中 NPU 0-7 均健康，无故障/隔离状态；
- 八卡均无其他计算任务或冲突进程，HBM 足以容纳本轮启动；
- 7000 端口未被占用；
- 只要不能确定空闲归属，就写 `blocked_resource`，生成第 8 节摘要后停止；
- `PRECHECK_EXIT != 0` 时写 `blocked_preflight` 并停止；不得自动修环境、模型或权限。

资源门由服务器执行者明确写入：

```bash
RESOURCE_GATE=not_confirmed  # 人工确认八卡全部健康空闲后，才把本值改为 pass
printf '%s\n' "${RESOURCE_GATE}" > "${ARTIFACT_DIR}/resource_gate.txt"
if [ "${PRECHECK_EXIT}" -ne 0 ]; then
  printf '%s\n' blocked_preflight > "${ARTIFACT_DIR}/task_status.txt"
  exit "${PRECHECK_EXIT}"
fi
if [ "${RESOURCE_GATE}" != pass ]; then
  printf '%s\n' blocked_resource > "${ARTIFACT_DIR}/task_status.txt"
  exit 20
fi
```

## 5. 固定运行环境

继续使用第 4 节 source 后保留的 `PYTHONPATH`，不得再次 unset：

```bash
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export VLLM_PLUGINS="${OFFICIAL_ASCEND_PLUGINS}"
export VLLM_USE_V1=1
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export OMP_PROC_BIND=false
export OMP_NUM_THREADS=8
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export LD_PRELOAD="/usr/lib/aarch64-linux-gnu/libjemalloc.so.2${LD_PRELOAD:+:${LD_PRELOAD}}"
export ACL_OP_INIT_MODE=1
export USE_MULTI_GROUPS_KV_CACHE=1
export TASK_QUEUE_ENABLE=1
export HCCL_OP_EXPANSION_MODE=AIV
export HCCL_BUFFSIZE=512
export USE_MULTI_BLOCK_POOL=1

[ "${PYTHONPATH:-}" = "${CANN_GENERATED_PYTHONPATH}" ] || {
  printf '%s\n' blocked_cann_pythonpath_changed > "${ARTIFACT_DIR}/task_status.txt"
  exit 21
}
```

## 6. 启动与固定输出客户端

定义生命周期函数：

```bash
wait_health() {
  local base_url="$1"
  local server_pid="$2"
  local timeout_sec="$3"
  "${PYTHON_BIN}" - "${base_url}" "${server_pid}" "${timeout_sec}" <<'PY'
import os
import sys
import time
import urllib.request

base = sys.argv[1].rstrip("/")
pid = int(sys.argv[2])
deadline = time.monotonic() + float(sys.argv[3])
while time.monotonic() < deadline:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        sys.exit(2)
    try:
        with urllib.request.urlopen(base + "/health", timeout=5) as response:
            if response.status == 200:
                sys.exit(0)
    except Exception:
        pass
    time.sleep(5)
sys.exit(1)
PY
}

stop_own_profile() {
  local profile_dir="$1"
  if [ -f "${profile_dir}/server_pid.txt" ]; then
    local pid
    pid="$(cat "${profile_dir}/server_pid.txt")"
    kill -- "-${pid}" >/dev/null 2>&1 || kill "${pid}" >/dev/null 2>&1 || true
    sleep 10
  fi
}
```

定义顺序 context ladder 客户端。它不保存生成文本，只保存固定输出计数与 timing：

```bash
run_ladder_client() {
  local profile_dir="$1"
  "${PYTHON_BIN}" - "http://${HOST}:${PORT}" "${SERVED_MODEL_NAME}" "${MODEL_PATH}" "${profile_dir}" <<'PY'
import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

from transformers import AutoTokenizer

base_url = sys.argv[1].rstrip("/")
served_model = sys.argv[2]
model_path = sys.argv[3]
profile_dir = Path(sys.argv[4])
contexts = [4096, 32768, 65536, 98304, 131072]
output_tokens = 64
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

def build_ids(target):
    ids = []
    block = 0
    while len(ids) < target:
        block += 1
        text = (
            f"DeepSeek P5 deterministic context block {block:07d}. "
            "This is synthetic smoke input with no private or generated content. "
            "Fields request phase input output timestamp cache expert.\n"
        )
        encoded = tokenizer(text, add_special_tokens=False).input_ids
        if encoded and isinstance(encoded[0], list):
            encoded = encoded[0]
        ids.extend(encoded)
    return ids[:target]

def request_once(context):
    payload = {
        "model": served_model,
        "prompt": build_ids(context),
        "max_tokens": output_tokens,
        "min_tokens": output_tokens,
        "ignore_eos": True,
        "temperature": 0.0,
        "stream": True,
        "stream_options": {"include_usage": True},
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
    chunks = []
    finish_reason = ""
    usage_completion_tokens = 0
    error = ""
    http_status = 0
    try:
        with urllib.request.urlopen(req, timeout=7200) as response:
            http_status = response.status
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                event = json.loads(data)
                usage = event.get("usage") or {}
                usage_completion_tokens = max(
                    usage_completion_tokens, int(usage.get("completion_tokens") or 0)
                )
                for choice in event.get("choices", []):
                    chunk = choice.get("text") or ""
                    if chunk:
                        if not first:
                            first = time.perf_counter_ns()
                        chunks.append(chunk)
                    if choice.get("finish_reason"):
                        finish_reason = str(choice["finish_reason"])
        end = time.perf_counter_ns()
        if usage_completion_tokens:
            generated = usage_completion_tokens
        else:
            generated_ids = tokenizer("".join(chunks), add_special_tokens=False).input_ids
            if generated_ids and isinstance(generated_ids[0], list):
                generated_ids = generated_ids[0]
            generated = len(generated_ids)
        status = "success" if http_status == 200 and generated == output_tokens else "failed"
    except Exception as exc:
        end = time.perf_counter_ns()
        generated = 0
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
    ttft_us = (first - start) / 1000 if first else 0.0
    wall_us = (end - start) / 1000
    tpot_us = ((end - first) / 1000 / (generated - 1)) if first and generated > 1 else 0.0
    return {
        "context_tokens": context,
        "requested_output_tokens": output_tokens,
        "status": status,
        "http_status": http_status,
        "generated_token_count": generated,
        "finish_reason": finish_reason,
        "ttft_us": round(ttft_us, 3),
        "tpot_us": round(tpot_us, 3),
        "client_wall_us": round(wall_us, 3),
        "output_tokens_per_s": round(generated / (wall_us / 1_000_000), 6) if wall_us else 0.0,
        "error": error,
        "claim_boundary": "p5_smoke_client_timing_not_benchmark",
    }

rows = []
for context in contexts:
    row = request_once(context)
    rows.append(row)
    if row["status"] != "success":
        break

with (profile_dir / "request_ladder.tsv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

successes = [row["context_tokens"] for row in rows if row["status"] == "success"]
result = {
    "status": "success" if successes else "failed",
    "attempted_contexts": [row["context_tokens"] for row in rows],
    "highest_success_context_tokens": max(successes) if successes else 0,
    "target_context_tokens": 131072,
    "output_tokens": output_tokens,
    "all_generated_counts_fixed_64": all(
        row["generated_token_count"] == output_tokens for row in rows if row["status"] == "success"
    ),
    "rows": rows,
    "claim_boundary": "p5_smoke_not_benchmark",
}
(profile_dir / "ladder_result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
PY
}
```

定义 profile。只在本任务 PID/进程组上执行停止：

```bash
run_profile() {
  local profile_name="$1"
  local max_num_seqs="$2"
  local mtp_mode="$3"
  local profile_dir="${ARTIFACT_DIR}/${profile_name}"
  mkdir -p "${profile_dir}"

  local cmd=(
    "${VLLM_BIN}" serve "${MODEL_PATH}"
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
    --additional-config '{"enable_flashcomm1":true,"enable_dsa_cp":true,"enable_cpu_binding":true,"multistream_overlap_shared_expert":false}'
    --compilation-config '{"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[2,4,6,8,10,12,14,16,18,20,22,24,32,36,40]}'
    --model-loader-extra-config '{"enable_multithread_load":true,"num_threads":16}'
  )
  if [ "${mtp_mode}" = mtp_on ]; then
    cmd+=(--speculative-config '{"num_speculative_tokens":1,"method":"mtp"}')
  fi

  printf '%q ' "${cmd[@]}" > "${profile_dir}/server_command.txt"
  printf '\n' >> "${profile_dir}/server_command.txt"
  npu-smi info -t usages > "${profile_dir}/npu_usage_before_start.txt" 2>&1 || true

  setsid "${cmd[@]}" > "${profile_dir}/vllm_server.log" 2>&1 &
  local server_pid=$!
  printf '%s\n' "${server_pid}" > "${profile_dir}/server_pid.txt"
  wait_health "http://${HOST}:${PORT}" "${server_pid}" 3600
  local ready_exit=$?
  printf '%s\n' "${ready_exit}" > "${profile_dir}/server_ready_exit_code.txt"
  npu-smi info -t usages > "${profile_dir}/npu_usage_after_start.txt" 2>&1 || true

  if [ "${ready_exit}" -eq 0 ]; then
    run_ladder_client "${profile_dir}" > "${profile_dir}/ladder_client.log" 2>&1
    printf '%s\n' "$?" > "${profile_dir}/ladder_client_exit_code.txt"
  else
    printf '%s\n' server_not_ready > "${profile_dir}/ladder_client_exit_code.txt"
  fi

  grep -nE 'Traceback|ERROR|Error|Exception|Assertion|unsupported|not supported|OutOfMemory|OOM|HCCL' \
    "${profile_dir}/vllm_server.log" | head -n 120 > "${profile_dir}/first_failure_excerpt.txt" || true
  grep -E 'Avg prompt throughput|Avg generation throughput|KV cache usage|Prefix cache hit rate' \
    "${profile_dir}/vllm_server.log" | tail -n 40 > "${profile_dir}/server_stats_summary.txt" || true
  npu-smi info -t usages > "${profile_dir}/npu_usage_after_ladder.txt" 2>&1 || true
  stop_own_profile "${profile_dir}"
}

reached_target() {
  grep -q '"highest_success_context_tokens": 131072' "$1/ladder_result.json" 2>/dev/null
}
```

## 7. 固定降级顺序与停止规则

先运行 reference：

```bash
run_profile "reference_mtp_maxseq16" 16 mtp_on
```

仅在没有达到 `131072+64`，且失败属于启动内存/graph capture/KV capacity 或长上下文容量类时，按顺序继续：

```bash
if ! reached_target "${ARTIFACT_DIR}/reference_mtp_maxseq16"; then
  run_profile "degraded_mtp_maxseq4" 4 mtp_on
fi
if ! reached_target "${ARTIFACT_DIR}/reference_mtp_maxseq16" \
  && ! reached_target "${ARTIFACT_DIR}/degraded_mtp_maxseq4"; then
  run_profile "degraded_mtp_maxseq1" 1 mtp_on
fi
if ! reached_target "${ARTIFACT_DIR}/reference_mtp_maxseq16" \
  && ! reached_target "${ARTIFACT_DIR}/degraded_mtp_maxseq4" \
  && ! reached_target "${ARTIFACT_DIR}/degraded_mtp_maxseq1"; then
  run_profile "degraded_no_mtp_maxseq1" 1 mtp_off
fi
```

停止例外：如果出现确定性的 environment/import、quantization/format、unsupported SoC/kernel、collective、model route 或模型完整性错误，立即停止，不重复加载 70 个分片，不进入后续降级。把首错归类并说明跳过哪些 profile。降低 `max_num_seqs` 或关闭 MTP 只能处理相应的容量/组合问题，不能掩盖其他错误。

每个成功启动的 profile 从 4096 开始顺序运行；某一档请求失败后停止该 profile 的更高档。任何降级结果只能标记 `degraded_smoke`。

分级：

- `green`：`reference_mtp_maxseq16` server ready，MTP 保持开启，且 `131072 input + 64 output` 成功；
- `yellow`：八卡 server ready 且至少一个固定 64-token 请求成功，但降低 `max_num_seqs`、关闭 MTP 或最高成功档低于 131072；
- `red`：八卡 server 不能 ready，或没有任何请求成功；
- `blocked_preflight` / `blocked_resource`：核心预检或八卡健康空闲门未通过。

结束时只清理本任务保存的 PID/进程组，并再次记录：

```bash
npu-smi info > "${ARTIFACT_DIR}/npu_smi_after.txt" 2>&1 || true
npu-smi info -t usages > "${ARTIFACT_DIR}/npu_usage_after.txt" 2>&1 || true
```

## 8. 本地结果摘要与传输等待门

服务器本地必须生成：

```text
${ARTIFACT_DIR}/result_summary.md
${ARTIFACT_DIR}/delivery_candidates.tsv
```

`result_summary.md` 必须简洁回答：

1. task ID、Git HEAD、origin/main、ahead/behind；
2. 环境版本、import roots、vLLM source commit/clean 状态；
3. W8A8 70 分片、精确 bytes、required files；
4. NPU 0-7 健康/空闲门与端口门；不得泄露其他用户 PID/命令；
5. CANN 生成的 ACL origin、八卡可见数与五插件白名单；
6. 实际执行的 profile、完整 shell-escaped command、server ready exit；
7. 每档 input/output/status/finish reason/TTFT/TPOT/client wall；这些只作 smoke timing；
8. 最高成功 context、是否固定 64-token、P5 grade；
9. 若失败，第一失败阶段、首错摘要、是否开始/完成权重加载；
10. 结束后本任务进程是否清理、NPU 是否恢复；
11. 所有 raw logs 和大产物的 server-local 路径；
12. 明确声明“P5 smoke，不是 P6 benchmark，不做瓶颈或收益归因”。

`delivery_candidates.tsv` 对每个候选小文件列出：

```text
path    size_bytes    sha256    sensitivity    email_feasible    upload_api_feasible    recommended_method    reason
```

候选优先包含 `result_summary.md`、`preflight.json`、`git_head.txt`、`resource_gate.txt`、每个已执行 profile 的 `server_command.txt`、`server_ready_exit_code.txt`、`ladder_result.json`、`request_ladder.tsv`、`server_stats_summary.txt` 和有界 `first_failure_excerpt.txt`。raw `vllm_server.log`、完整 NPU SMI、模型、generated text 和整个 artifact 目录不得列为传输候选。

本轮结果是新的文件范围，尚未批准传输方式。生成摘要和候选清单后暂停，在当前任务会话报告精确路径、bytes、SHA-256、敏感性、可用方法和推荐方法，等待用户选择 `email` 或 `upload-api`。

确认前禁止发送邮件、附件、upload-api 预检或上传。确认后也只能传用户批准的精确文件范围；任何 `401`、`409`、`413`、redirect/proxy、timeout、service 或 SHA-256 校验失败都必须停止并重新请求选择，不得自动重试、改名、扩展范围、补发邮件或切换渠道。

## 9. 最终边界

- 本轮八卡授权只覆盖上述 W8A8 P5 startup/context ladder；不扩展到 P6、profiler、offload、模型转换或 mixed checkpoint。
- 资源授权不等于可以清理服务器现有工作负载；任何冲突都应阻塞本轮。
- 运行成功只证明当前服务器、当前 stack、当前 command 下的 P5 smoke；P6 baseline 必须另行冻结与授权。
- 不提交服务器生成的 runtime artifact，除非后续任务明确要求归档哪些小文件。
