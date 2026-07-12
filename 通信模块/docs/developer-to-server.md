# Developer to Server

## 当前任务：DeepSeek-V4-Flash W8A8 八卡关闭 MTP 隔离

任务 ID：

```text
p5_deepseek_v4_flash_w8a8_8card_no_mtp_isolation_v0221rc1_2026_0712
```

继续使用用户已授权的同一 P5 八卡范围：

```text
ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
```

本轮只回答一个问题：在现有 `vLLM 0.22.1+empty / vLLM-Ascend 0.22.1rc1` 栈、W8A8 checkpoint、TP8+EP、`--quantization ascend` 下，关闭 MTP 运行 `vllm serve` 后能否完成第一个 `4096 input + 64 output` 请求。

只允许两个顺序 profile：

1. `base_no_mtp_graph_maxseq1`：关闭 MTP，保留 `FULL_DECODE_ONLY` 图捕获；
2. `base_no_mtp_eager_maxseq1`：仅当第 1 个 profile 明确失败在主模型 graph capture 时运行，关闭 MTP 并增加 `--enforce-eager`。

任一 profile 完成一个 `4096+64` 请求后立即停止。本轮不跑 context ladder、MTP、P6、profiler、并发、offload、A/B 或瓶颈归因。

## 1. 上轮结论与证据边界

上轮 `p5_deepseek_v4_flash_w8a8_8card_context_smoke_v0221rc1_2026_0712` 为 `red_deterministic_mtp_dsa_cp_graph_capture`：

- preflight 通过，vLLM source commit/clean、CANN ACL、五插件和八卡可见性匹配；
- 服务器摘要报告 8 个 worker 均完成 70 分片、300013759966 bytes（约 279.41 GiB）权重加载，MTP draft model 也完成加载；
- server 未 ready、没有请求；
- 首错在 MTP proposer dummy run 的 DSA-CP graph capture：`dsa_cp.py:280` 对 `positions_cpu=None` 做切片，触发 `TypeError: 'NoneType' object is not subscriptable`。

这证明失败与 MTP graph path 高度相关，但尚未证明关闭 MTP 后的 base request 能运行。上游后续 MTP graph 支持跨多个文件且面向更新版本，本轮禁止在 live 环境做单行补丁或部分 backport。

注意：上轮权重加载结论来自服务器 `result_summary.md`；开发机收到的有界首错摘录没有包含完整 load 行。本轮必须在小型摘录中同时保留 load 与首错证据，但 raw log 继续留在服务器。

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

必须完整同步，满足 `HEAD == origin/main`、ahead/behind=`0 0`，然后重新打开拉取后的本文档。禁止只拉一个提交、`cherry-pick`、detached checkout 或单文件覆盖。

## 3. 固定对象与禁止项

```text
项目：/data/node0_disk1/liguowei/AK-Infer-Lab
环境：/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
vLLM 源码：/data/node0_disk1/vllm-0.22.1
vLLM commit：0decac0d96c42b49572498019f0a0e3600f50398
vLLM-Ascend：0.22.1rc1
模型：/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
```

允许：只读复用上述环境、源码与模型；source 官方 CANN/ATB；在 NPU 0-7 启动本任务 TP8/EP 进程；停止本任务记录的 PID/进程组；生成 server-local 日志和小摘要。

禁止：

- 禁止修改、patch、overlay、升级、降级或重建 vLLM、vLLM-Ascend、site-packages、模型、CANN、ATB、driver、firmware 或系统环境；
- 禁止 `conda create`、`pip install`、`pip uninstall`、`sitecustomize.py`、手工复制/软链模块或硬编码 ACL 路径；
- 禁止主动终止、暂停或影响任何非本任务进程；任一卡繁忙、归属不清或端口冲突时写 `blocked_resource` 并停止；上轮针对特定 keepalive PID 的一次性清理授权不得复用；
- 禁止 `--speculative-config`、MTP、context ladder、mixed checkpoint、P6、msprof、offload、并发或其他模型；
- 禁止把本轮 timing 写成 benchmark、吞吐基线、瓶颈或收益结论；
- 禁止发送邮件、附件或调用 upload-api，直到用户针对本轮精确结果范围重新选择传输方式。

## 4. 资源门与预检

```bash
set +e
set -uo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_w8a8_8card_no_mtp_isolation_v0221rc1_2026_0712
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
    "canonical_shard_count": len(shards),
    "weight_bytes": sum(path.stat().st_size for path in shards),
    "required_files": {
        name: (model / name).is_file()
        for name in [
            "config.json", "generation_config.json", "tokenizer.json",
            "tokenizer_config.json", "quant_model_description.json",
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

RESOURCE_GATE=not_confirmed  # 人工确认 NPU 0-7 全部健康、空闲、无冲突后才改为 pass
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

资源门需人工核对八卡健康、空闲、无冲突计算进程、HBM 已回到可启动状态且 7000 端口空闲。只观察，不清理未知进程；无法确认归属即停止。

## 5. 固定运行环境

继续保留 source 后的 `PYTHONPATH`：

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

## 6. 生命周期与单请求客户端

```bash
wait_health() {
  local server_pid="$1"
  "${PYTHON_BIN}" - "http://${HOST}:${PORT}" "${server_pid}" <<'PY'
import os
import sys
import time
import urllib.request

base = sys.argv[1].rstrip("/")
pid = int(sys.argv[2])
deadline = time.monotonic() + 3600
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

run_one_request() {
  local profile_dir="$1"
  "${PYTHON_BIN}" - "http://${HOST}:${PORT}" "${SERVED_MODEL_NAME}" "${MODEL_PATH}" "${profile_dir}" <<'PY'
import json
import sys
import time
import urllib.request
from pathlib import Path

from transformers import AutoTokenizer

base, served_model, model_path = sys.argv[1:4]
profile_dir = Path(sys.argv[4])
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
ids = []
block = 0
while len(ids) < 4096:
    block += 1
    text = (
        f"DeepSeek P5 no-MTP isolation block {block:07d}. "
        "Synthetic smoke input with no private or generated content.\n"
    )
    ids.extend(tokenizer(text, add_special_tokens=False).input_ids)
payload = {
    "model": served_model,
    "prompt": ids[:4096],
    "max_tokens": 64,
    "min_tokens": 64,
    "ignore_eos": True,
    "temperature": 0.0,
    "stream": True,
    "stream_options": {"include_usage": True},
}
request = urllib.request.Request(
    base.rstrip("/") + "/v1/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    method="POST",
)
start = time.perf_counter_ns()
first = 0
completion_tokens = 0
finish_reason = ""
error = ""
http_status = 0
try:
    with urllib.request.urlopen(request, timeout=7200) as response:
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
            completion_tokens = max(completion_tokens, int(usage.get("completion_tokens") or 0))
            for choice in event.get("choices", []):
                if choice.get("text") and not first:
                    first = time.perf_counter_ns()
                if choice.get("finish_reason"):
                    finish_reason = str(choice["finish_reason"])
except Exception as exc:
    error = f"{type(exc).__name__}: {exc}"
end = time.perf_counter_ns()
success = http_status == 200 and completion_tokens == 64
result = {
    "status": "success" if success else "failed",
    "input_tokens": 4096,
    "requested_output_tokens": 64,
    "generated_token_count": completion_tokens,
    "http_status": http_status,
    "finish_reason": finish_reason,
    "ttft_us": round((first - start) / 1000, 3) if first else 0.0,
    "client_wall_us": round((end - start) / 1000, 3),
    "error": error,
    "claim_boundary": "p5_failure_isolation_smoke_not_benchmark",
}
(profile_dir / "request_result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
sys.exit(0 if success else 3)
PY
}
```

## 7. 两个受限 profile

```bash
run_profile() {
  local profile_name="$1"
  local eager_mode="$2"
  local profile_dir="${ARTIFACT_DIR}/${profile_name}"
  mkdir -p "${profile_dir}"

  local cmd=(
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
  )
  if [ "${eager_mode}" = graph ]; then
    cmd+=(--compilation-config '{"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[2,4,6,8,10,12,14,16,18,20,22,24,32,36,40]}')
  else
    cmd+=(--enforce-eager)
  fi

  printf '%q ' "${cmd[@]}" > "${profile_dir}/server_command.txt"
  printf '\n' >> "${profile_dir}/server_command.txt"
  npu-smi info -t usages > "${profile_dir}/npu_usage_before_start.txt" 2>&1 || true
  setsid "${cmd[@]}" > "${profile_dir}/vllm_server.log" 2>&1 &
  local server_pid=$!
  printf '%s\n' "${server_pid}" > "${profile_dir}/server_pid.txt"

  wait_health "${server_pid}"
  local ready_exit=$?
  printf '%s\n' "${ready_exit}" > "${profile_dir}/server_ready_exit_code.txt"
  if [ "${ready_exit}" -eq 0 ]; then
    run_one_request "${profile_dir}" > "${profile_dir}/request_client.log" 2>&1
    printf '%s\n' "$?" > "${profile_dir}/request_client_exit_code.txt"
  else
    printf '%s\n' server_not_ready > "${profile_dir}/request_client_exit_code.txt"
  fi

  grep -nE 'Loading model weights took|Draft model loaded|Capturing|Traceback|ERROR|Error|Exception|Assertion|unsupported|not supported|OutOfMemory|OOM|HCCL|positions_cpu' \
    "${profile_dir}/vllm_server.log" | head -n 180 > "${profile_dir}/load_and_failure_excerpt.txt" || true
  grep -E 'Avg prompt throughput|Avg generation throughput|KV cache usage|Prefix cache hit rate' \
    "${profile_dir}/vllm_server.log" | tail -n 40 > "${profile_dir}/server_stats_summary.txt" || true
  npu-smi info -t usages > "${profile_dir}/npu_usage_after_request.txt" 2>&1 || true
  stop_own_profile "${profile_dir}"
}

run_profile base_no_mtp_graph_maxseq1 graph
```

运行第 1 个 profile 后人工分类：

- `request_result.json` 为 success：写 `yellow_no_mtp_graph_request_success`，停止；
- server ready 但请求失败：记录 request runtime 首错，停止；不得用 eager 掩盖请求错误；
- server 未 ready，且首个确定性错误明确位于主模型 cudagraph capture：才允许把下面的 `RUN_EAGER` 改为 `pass`；
- environment/import、quantization/format、unsupported SoC/kernel、collective、model route、模型完整性、OOM/容量或归属不明的错误：停止，不运行 eager。

```bash
RUN_EAGER=not_confirmed  # 只有人工确认“主模型 graph capture 首错”后才改为 pass
printf '%s\n' "${RUN_EAGER}" > "${ARTIFACT_DIR}/eager_gate.txt"
if [ "${RUN_EAGER}" = pass ]; then
  run_profile base_no_mtp_eager_maxseq1 eager
fi
```

分级：

- `yellow_no_mtp_graph_request_success`：第 1 个 profile server ready 且 `4096+64` 成功；
- `yellow_no_mtp_eager_request_success`：第 2 个 profile server ready 且 `4096+64` 成功；
- `red_*`：两个允许的 profile 都没有成功请求，按第一失败阶段加后缀；
- `blocked_preflight` / `blocked_resource`：预检或资源门未通过。

人工判级后把上述精确值写入：

```bash
TASK_STATUS=not_classified  # 按实际结果改为上述 yellow/red/blocked 精确状态
printf '%s\n' "${TASK_STATUS}" > "${ARTIFACT_DIR}/task_status.txt"
```

任何 yellow 都只证明当前 no-MTP base request 路径，MTP 仍未通过；不升级为 P5 green。结束时：

```bash
npu-smi info > "${ARTIFACT_DIR}/npu_smi_after.txt" 2>&1 || true
npu-smi info -t usages > "${ARTIFACT_DIR}/npu_usage_after.txt" 2>&1 || true
```

## 8. 结果摘要与传输等待门

服务器本地生成：

```text
${ARTIFACT_DIR}/result_summary.md
${ARTIFACT_DIR}/delivery_candidates.tsv
```

`result_summary.md` 必须回答：task ID 与 Git 三方状态；精确环境/import roots/source commit；70 分片与 bytes；八卡资源门、ACL origin、五插件；每个实际 profile 的完整 shell-escaped command、ready/request exit；是否观察到 MTP 路径；权重加载证据；`4096+64` 状态、finish reason 与仅供 smoke 的 client timing；首错阶段；最终 grade；进程清理和 NPU 恢复；raw log 的 server-local 路径；明确“P5 failure-isolation smoke，不是 P6 benchmark”。

`delivery_candidates.tsv` 每行列出：

```text
path    size_bytes    sha256    sensitivity    email_feasible    upload_api_feasible    recommended_method    reason
```

候选优先包含 `result_summary.md`、`preflight.json`、`git_head.txt`、`resource_gate.txt`、`eager_gate.txt`、`task_status.txt`，以及每个实际 profile 的 `server_command.txt`、`server_ready_exit_code.txt`、`request_client_exit_code.txt`、`request_result.json`、`server_stats_summary.txt`、有界 `load_and_failure_excerpt.txt`。raw `vllm_server.log`、完整 NPU SMI、模型、生成文本和整个目录不得列为候选。

本轮是新的结果范围，传输方式尚未选择。生成摘要与候选清单后，在当前任务会话报告每个候选的精确路径、bytes、SHA-256、敏感性、可用方法和一个推荐方法，等待用户选择 `email`、`upload-api` 或 `server-local`。

确认前禁止发送邮件、附件、upload-api 预检或上传。任何传输失败都停止并重新请求选择，不自动重试、改名、扩展范围、补发邮件或切换渠道。

## 9. 最终边界

- 本轮只授权同一 P5 范围内的 no-MTP graph 与条件式 eager 隔离；不授权 MTP patch/backport、v0.23 环境或 P6。
- 成功请求可把 P5 记为 yellow，并为后续 baseline freeze 提供候选；是否冻结与进入 P8/P6 由开发机结合结果另行决定。
- 不提交服务器 runtime artifact，除非后续任务明确指定小文件归档范围。
