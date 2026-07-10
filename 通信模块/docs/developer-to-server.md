# Developer to Server

## 当前任务：DeepSeek-V4-Flash 较小 checkpoint 四卡格式/拉起诊断

任务 ID：

```text
p5_deepseek_v4_flash_4card_small_checkpoint_probe_v0202_2026_0710
```

用户本轮只授权：

```text
ASCEND_RT_VISIBLE_DEVICES=4,5,6,7
```

目标：先完整同步远端 `main` 的全部缺失提交，再只执行本文档规定的四卡任务。使用已验证的独立 `vLLM 0.20.2+empty / vLLM-Ascend 0.20.2rc1` 环境，对较小的 `/data/node0_disk1/Public/DeepSeek-V4-Flash` 做一次有界 TP4/EP 真实拉起，固定 FP8/FP4 checkpoint 在 Ascend 上的首个格式或运行时失败点；若 server ready，只发送一个 `4096 input + 64 output` 请求。

服务器新回传的磁盘事实：

- 本轮选中目录共有 46 个连续分片、`159,617,149,040 B ≈ 148.66 GiB`；相对四张 64GB NPU 的约 `256 GiB` 原始 HBM，静态余量约 `107.34 GiB`，但仍不保证计入 KV、activation、workspace 和通信 buffer 后可以拉起。
- `/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp` 共有 70 个连续分片、`300,013,759,966 B ≈ 279.41 GiB`，静态权重已超过四卡原始 HBM，因此本轮明确不启动该目录。
- 选中目录的 `config.json` 含 `quant_method=fp8`、`expert_dtype=fp4` 和 `num_nextn_predict_layers=1`，但不含 `kv_lora_rank`。目标 vLLM tag 的源码会识别为 `deepseek_v4_fp8`；目标 vLLM-Ascend tag 的 NPU 平台公开量化方法为 `ascend` / `compressed-tensors`。这只是静态源码风险，不是服务器运行结论，本轮要记录真实首错。

这是 P5 前置诊断，不是 canonical W8A8 八卡 P5 验收，不是 P6 benchmark。

## 1. 仓库同步：拉完整 `main`，不是只拉一个提交

在服务器项目根目录执行：

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

同步要求：

1. 这是正常的 `main` 全量快进同步；会拉取服务器缺失的全部提交。
2. 禁止 `cherry-pick` 单个提交，禁止按某个哈希做 detached checkout，禁止只取一份文件覆盖仓库。
3. 同步后必须满足 `HEAD == origin/main` 且 ahead/behind 为 `0 0`；提交哈希只用于记录同步结果，不是“只拉该提交”的指令。
4. 同步完成后重新打开拉取后的 `通信模块/docs/developer-to-server.md`。只有任务 ID 仍为 `p5_deepseek_v4_flash_4card_small_checkpoint_probe_v0202_2026_0710` 才继续；若任务 ID 已变化，以新文档为准，不执行旧命令。
5. 同步整个仓库不等于执行整个仓库。本轮只执行下述四卡诊断，不运行 P8、其他 workload、历史 handoff 或额外测试任务。

## 2. 必须先做的资源门检查

1. 只检查物理 NPU `4,5,6,7`。四卡必须全部健康且空闲；任一卡不满足时返回 `blocked_resource`，不启动模型。
2. 不允许使用 NPU `0,1,2,3`，不允许自动扩大到八卡。
3. 记录四卡启动前和可行时的 HBM used/free 小摘要；raw `npu-smi` 输出留在服务器。
4. 若仓库未完整同步、模型文件预检不通过或 inference contracts 失败，分别返回 `blocked_git_not_fully_synced`、`blocked_model_files`、`blocked_inference_contracts`，不启动模型。

## 3. 固定实验边界

- 固定环境：`/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.20.2rc1`。
- 固定模型：`/data/node0_disk1/Public/DeepSeek-V4-Flash`；本轮不启动 W8A8-MTP 目录。
- 固定 `TP4 + EP`、`max_model_len=8192`、`max_num_seqs=1`、eager mode。
- 不传 `--quantization ascend`，也不传其他 `--quantization`；让 checkpoint 自带的 FP8/FP4 配置暴露真实 runtime 识别结果。禁止改写/删除 `config.json` 的量化字段。
- 使用 `additional_config.enable_flashcomm1=true`、`additional_config.enable_dsa_cp=true` 和 `additional_config.enable_mlapo=false`。关闭 MLAPO 只用于缩小四卡诊断开销，不可写成 official reference baseline。
- 首次保留 MTP。只有首次日志明确是 MTP/speculative 错误，且不是量化格式、HBM/权重容量或其他更早失败，才允许补一次 `MTP off` 诊断。
- 一旦出现量化格式拒绝、HBM OOM、权重分配不足或其他明确容量失败，立即停止；不重试、不切换到 W8A8、不改量化配置。
- 不启用 `--cpu-offload-gb`、swap、NVMe offload、KV offload、UCM、LMCache 或任何权重分层。
- 不跑 128K context ladder、msprof、并发矩阵、A/B、吞吐 benchmark、瓶颈归因或 P8 real-move。
- 不安装、升级、降级、卸载或修复包；不改 vLLM/vLLM-Ascend 源码、CANN、driver、apt 或 NPU runtime。

## 4. 建议执行命令

完成全量同步并重新打开本文档，且确认 NPU `4,5,6,7` 全部健康、空闲后执行：

```bash
set -uo pipefail

cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_4card_small_checkpoint_probe_v0202_2026_0710
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.20.2rc1
PYTHON_BIN="${ENV_PREFIX}/bin/python"
VLLM_BIN="${ENV_PREFIX}/bin/vllm"
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash
EXCLUDED_W8A8_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
HOST=127.0.0.1
PORT=7000
SERVED_MODEL_NAME=dsv4-four-card-probe
STARTUP_TIMEOUT_SEC=3600

mkdir -p "${ARTIFACT_DIR}"

set +e
git fetch origin main > "${ARTIFACT_DIR}/git_fetch_verify.log" 2>&1
git_fetch_exit_code=$?
set -e
echo "${git_fetch_exit_code}" > "${ARTIFACT_DIR}/git_fetch_verify_exit_code.txt"
LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_MAIN="$(git rev-parse origin/main)"
printf 'local_head=%s\norigin_main=%s\n' "${LOCAL_HEAD}" "${REMOTE_MAIN}" \
  > "${ARTIFACT_DIR}/git_sync_state.txt"
git rev-list --left-right --count HEAD...origin/main \
  >> "${ARTIFACT_DIR}/git_sync_state.txt"

if [ "${git_fetch_exit_code}" -ne 0 ] || [ "${LOCAL_HEAD}" != "${REMOTE_MAIN}" ]; then
  echo "blocked_git_not_fully_synced" > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi

if ! grep -q 'p5_deepseek_v4_flash_4card_small_checkpoint_probe_v0202_2026_0710' \
  通信模块/docs/developer-to-server.md; then
  echo "blocked_handoff_task_id_changed" > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u

export PATH="${ENV_PREFIX}/bin:${PATH}"
export ASCEND_RT_VISIBLE_DEVICES=4,5,6,7
export VLLM_PLUGINS=ascend
export VLLM_USE_V1=1
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export VLLM_ASCEND_APPLY_DSV4_PATCH=1
export LD_PRELOAD="/usr/lib/aarch64-linux-gnu/libjemalloc.so.2${LD_PRELOAD:+:${LD_PRELOAD}}"
export OMP_PROC_BIND=false
export OMP_NUM_THREADS=8
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export ACL_OP_INIT_MODE=1
export USE_MULTI_GROUPS_KV_CACHE=1
export TASK_QUEUE_ENABLE=1
export HCCL_OP_EXPANSION_MODE=AIV
export HCCL_BUFFSIZE=512
export USE_MULTI_BLOCK_POOL=1

{
  echo "run_id=${RUN_ID}"
  echo "commit=${LOCAL_HEAD}"
  echo "origin_main=${REMOTE_MAIN}"
  echo "timestamp=$(date -Is)"
  echo "environment=${ENV_PREFIX}"
  echo "model_path=${MODEL_PATH}"
  echo "excluded_w8a8_path=${EXCLUDED_W8A8_PATH}"
  echo "ASCEND_RT_VISIBLE_DEVICES=${ASCEND_RT_VISIBLE_DEVICES}"
  echo "tensor_parallel_size=4"
  echo "max_model_len=8192"
  echo "max_num_seqs=1"
  echo "request_shape=4096+64"
  echo "quantization_argument=omitted_use_checkpoint_config"
  echo "cpu_offload_gb=0"
  echo "mlapo=disabled_for_four_card_diagnostic"
  echo "canonical_p5_gate=unchanged"
} > "${ARTIFACT_DIR}/run_context.txt"

set +e
"${PYTHON_BIN}" -m pytest tests/inference_contracts -q \
  > "${ARTIFACT_DIR}/pytest.log" 2>&1
pytest_exit_code=$?
set -e
echo "${pytest_exit_code}" > "${ARTIFACT_DIR}/pytest_exit_code.txt"
if [ "${pytest_exit_code}" -ne 0 ]; then
  echo "blocked_inference_contracts" > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi

npu-smi info > "${ARTIFACT_DIR}/npu_smi_info.txt" 2>&1 || true
npu-smi info -t usages > "${ARTIFACT_DIR}/npu_smi_usage_before.txt" 2>&1 || true

"${PYTHON_BIN}" - "${ARTIFACT_DIR}" "${MODEL_PATH}" "${EXCLUDED_W8A8_PATH}" <<'PY'
import csv
import importlib.metadata as metadata
import json
import platform
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
model_path = Path(sys.argv[2])
excluded_w8a8_path = Path(sys.argv[3])

def pkg(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "missing"

def payload_shards(root, pattern):
    return sorted(path for path in root.glob(pattern) if not path.name.startswith("._"))

config = {}
try:
    config = json.loads((model_path / "config.json").read_text(encoding="utf-8"))
except Exception as exc:
    config = {"metadata_error": f"{type(exc).__name__}: {exc}"}

selected_shards = payload_shards(model_path, "model-*.safetensors")
selected_bytes = sum(path.stat().st_size for path in selected_shards)
excluded_shards = payload_shards(excluded_w8a8_path, "quant_model_weights-*.safetensors")
excluded_bytes = sum(path.stat().st_size for path in excluded_shards)
quant_config = config.get("quantization_config") or {}

rows = [
    {
        "role": "selected_four_card_probe",
        "model_path": str(model_path),
        "path_exists": str(model_path.exists()).lower(),
        "shard_count": len(selected_shards),
        "weight_bytes": selected_bytes,
        "weight_gib": round(selected_bytes / 1024**3, 6),
        "four_card_raw_hbm_gib": 256,
        "static_capacity_margin_gib": round(256 - selected_bytes / 1024**3, 6),
        "architecture": ",".join(config.get("architectures", []) or []),
        "model_type": config.get("model_type", ""),
        "quant_method": quant_config.get("quant_method", ""),
        "expert_dtype": config.get("expert_dtype", ""),
        "num_nextn_predict_layers": config.get("num_nextn_predict_layers", ""),
        "has_kv_lora_rank": str("kv_lora_rank" in config).lower(),
    },
    {
        "role": "excluded_static_overcapacity_w8a8",
        "model_path": str(excluded_w8a8_path),
        "path_exists": str(excluded_w8a8_path.exists()).lower(),
        "shard_count": len(excluded_shards),
        "weight_bytes": excluded_bytes,
        "weight_gib": round(excluded_bytes / 1024**3, 6),
        "four_card_raw_hbm_gib": 256,
        "static_capacity_margin_gib": round(256 - excluded_bytes / 1024**3, 6),
        "architecture": "",
        "model_type": "",
        "quant_method": "ascend_modelslim",
        "expert_dtype": "",
        "num_nextn_predict_layers": "",
        "has_kv_lora_rank": "",
    },
]
with (artifact_dir / "model_capacity_preflight.tsv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

selected_ok = (
    model_path.is_dir()
    and len(selected_shards) == 46
    and selected_bytes > 0
    and config.get("architectures") == ["DeepseekV4ForCausalLM"]
    and config.get("model_type") == "deepseek_v4"
    and quant_config.get("quant_method") == "fp8"
    and config.get("expert_dtype") == "fp4"
)
(artifact_dir / "model_preflight_status.txt").write_text(
    "ready\n" if selected_ok else "blocked_model_files\n", encoding="utf-8"
)

runtime_rows = [
    {"name": "python", "value": platform.python_version()},
    {"name": "torch", "value": pkg("torch")},
    {"name": "torch_npu", "value": pkg("torch-npu")},
    {"name": "vllm", "value": pkg("vllm")},
    {"name": "vllm_ascend", "value": pkg("vllm-ascend")},
    {"name": "triton_ascend", "value": pkg("triton-ascend")},
    {"name": "transformers", "value": pkg("transformers")},
]
try:
    import torch
    import torch_npu  # noqa: F401
    runtime_rows.extend([
        {"name": "npu_available", "value": str(torch.npu.is_available()).lower()},
        {"name": "visible_device_count", "value": str(torch.npu.device_count())},
    ])
except Exception as exc:
    runtime_rows.append({"name": "torch_npu_probe", "value": f"failed:{type(exc).__name__}:{exc}"})

with (artifact_dir / "runtime_versions.tsv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=["name", "value"], delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(runtime_rows)
PY

if [ "$(tr -d '\r\n' < "${ARTIFACT_DIR}/model_preflight_status.txt")" != "ready" ]; then
  echo "blocked_model_files" > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi

VISIBLE_COUNT="$(awk -F '\t' '$1 == "visible_device_count" {print $2}' "${ARTIFACT_DIR}/runtime_versions.tsv")"
if [ "${VISIBLE_COUNT}" != "4" ]; then
  echo "blocked_resource" > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi

wait_health_or_exit() {
  local pid="$1"
  local deadline=$((SECONDS + STARTUP_TIMEOUT_SEC))
  while [ "${SECONDS}" -lt "${deadline}" ]; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      return 2
    fi
    if curl -fsS --max-time 5 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  return 1
}

stop_profile() {
  local pid="$1"
  kill -- "-${pid}" >/dev/null 2>&1 || kill "${pid}" >/dev/null 2>&1 || true
  sleep 5
}

run_single_request() {
  local profile_dir="$1"
  "${PYTHON_BIN}" - "${MODEL_PATH}" "http://${HOST}:${PORT}" "${SERVED_MODEL_NAME}" "${profile_dir}" <<'PY'
import json
import sys
import time
import urllib.request
from pathlib import Path

from transformers import AutoTokenizer

model_path, base_url, served_model, profile_dir = sys.argv[1:]
profile_dir = Path(profile_dir)
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
ids = []
block = 0
while len(ids) < 4096:
    block += 1
    text = (
        f"DeepSeek four-card format probe block {block:06d}. "
        "This deterministic input is only for a bounded runtime smoke. "
    )
    ids.extend(tokenizer(text, add_special_tokens=False).input_ids)
payload = {
    "model": served_model,
    "prompt": ids[:4096],
    "max_tokens": 64,
    "min_tokens": 64,
    "ignore_eos": True,
    "temperature": 0.0,
    "stream": False,
}
request = urllib.request.Request(
    base_url.rstrip("/") + "/v1/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
started = time.perf_counter()
result = {
    "status": "failed",
    "http_status": 0,
    "input_tokens": 4096,
    "requested_output_tokens": 64,
    "completion_tokens": 0,
    "finish_reason": "",
    "client_wall_s": 0.0,
    "error": "",
}
try:
    with urllib.request.urlopen(request, timeout=7200) as response:
        body = json.loads(response.read().decode("utf-8"))
        result["http_status"] = response.status
        result["completion_tokens"] = int((body.get("usage") or {}).get("completion_tokens") or 0)
        choices = body.get("choices") or []
        result["finish_reason"] = str((choices[0] if choices else {}).get("finish_reason") or "")
        if response.status == 200 and result["completion_tokens"] == 64:
            result["status"] = "success"
except Exception as exc:
    result["error"] = f"{type(exc).__name__}: {exc}"
result["client_wall_s"] = round(time.perf_counter() - started, 6)
(profile_dir / "request_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

run_profile() {
  local profile_name="$1"
  local mtp_mode="$2"
  local profile_dir="${ARTIFACT_DIR}/${profile_name}"
  mkdir -p "${profile_dir}"

  local cmd=(
    "${VLLM_BIN}" serve "${MODEL_PATH}"
    --safetensors-load-strategy prefetch
    --max-model-len 8192
    --max-num-batched-tokens 4096
    --served-model-name "${SERVED_MODEL_NAME}"
    --gpu-memory-utilization 0.92
    --max-num-seqs 1
    --data-parallel-size 1
    --tensor-parallel-size 4
    --enable-expert-parallel
    --host "${HOST}"
    --port "${PORT}"
    --block-size 128
    --tokenizer-mode deepseek_v4
    --tool-call-parser deepseek_v4
    --enable-auto-tool-choice
    --reasoning-parser deepseek_v4
    --enforce-eager
    --additional-config '{"enable_flashcomm1":true,"enable_dsa_cp":true,"enable_mlapo":false,"enable_cpu_binding":true,"multistream_overlap_shared_expert":false}'
  )
  if [ "${mtp_mode}" = "mtp_on" ]; then
    cmd+=(--speculative-config '{"num_speculative_tokens":1,"method":"mtp","enforce_eager":true}')
  fi

  printf '%q ' "${cmd[@]}" > "${profile_dir}/server_command.txt"
  printf '\n' >> "${profile_dir}/server_command.txt"
  npu-smi info -t usages > "${profile_dir}/npu_smi_usage_before_start.txt" 2>&1 || true

  set +e
  setsid "${cmd[@]}" > "${profile_dir}/vllm_server.log" 2>&1 &
  local server_pid=$!
  echo "${server_pid}" > "${profile_dir}/server_pid.txt"
  wait_health_or_exit "${server_pid}"
  local ready_exit_code=$?
  echo "${ready_exit_code}" > "${profile_dir}/server_ready_exit_code.txt"
  npu-smi info -t usages > "${profile_dir}/npu_smi_usage_after_start.txt" 2>&1 || true

  if [ "${ready_exit_code}" -eq 0 ]; then
    run_single_request "${profile_dir}" > "${profile_dir}/request_client.log" 2>&1
    echo "$?" > "${profile_dir}/request_client_exit_code.txt"
  else
    echo "not_run_server_not_ready" > "${profile_dir}/request_client_exit_code.txt"
  fi

  npu-smi info -t usages > "${profile_dir}/npu_smi_usage_after_request.txt" 2>&1 || true
  stop_profile "${server_pid}"
  set -e
}

set +e
run_profile mtp_on mtp_on

MTP_LOG="${ARTIFACT_DIR}/mtp_on/vllm_server.log"
if grep -Eqi 'unknown quantization|quantization[^[:cntrl:]]*(not supported|unsupported|does not match)|unsupported[^[:cntrl:]]*(fp4|mxfp4)|deepseek_v4_fp8[^[:cntrl:]]*(not supported|unsupported)' "${MTP_LOG}"; then
  echo "quantization_format_failure_stop_no_retry" > "${ARTIFACT_DIR}/fallback_decision.txt"
elif grep -Eqi 'out of memory|npu[^[:cntrl:]]*oom|failed to allocate|not enough memory|insufficient memory' "${MTP_LOG}"; then
  echo "capacity_failure_stop_no_retry" > "${ARTIFACT_DIR}/fallback_decision.txt"
elif [ "$(cat "${ARTIFACT_DIR}/mtp_on/server_ready_exit_code.txt")" != "0" ] \
  && grep -Eqi 'unsupported speculative|speculative[^[:cntrl:]]*(error|fail|unsupported)|mtp[^[:cntrl:]]*(error|fail|unsupported)|DeepSeekV4MTP[^[:cntrl:]]*(error|exception|attribute)' "${MTP_LOG}"; then
  echo "explicit_mtp_failure_retry_once_without_mtp" > "${ARTIFACT_DIR}/fallback_decision.txt"
  run_profile mtp_off mtp_off
else
  echo "no_fallback" > "${ARTIFACT_DIR}/fallback_decision.txt"
fi
set -e

"${PYTHON_BIN}" - "${ARTIFACT_DIR}" <<'PY'
import json
import re
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
profiles = []
any_ready = False
any_success = False
mtp_success = False
capacity_failure = False
quant_format_failure = False

capacity_pattern = re.compile(r"out of memory|npu.*oom|failed to allocate|not enough memory|insufficient memory", re.I)
quant_pattern = re.compile(
    r"unknown quantization|quantization.*(not supported|unsupported|does not match)|"
    r"unsupported.*(fp4|mxfp4)|deepseek_v4_fp8.*(not supported|unsupported)",
    re.I,
)

for name, mtp_enabled in (("mtp_on", True), ("mtp_off", False)):
    root = artifact_dir / name
    if not root.exists():
        continue
    ready = (root / "server_ready_exit_code.txt").read_text(encoding="utf-8", errors="replace").strip() if (root / "server_ready_exit_code.txt").exists() else "missing"
    request = {}
    if (root / "request_result.json").exists():
        request = json.loads((root / "request_result.json").read_text(encoding="utf-8"))
    log_text = (root / "vllm_server.log").read_text(encoding="utf-8", errors="replace") if (root / "vllm_server.log").exists() else ""
    is_capacity = bool(capacity_pattern.search(log_text))
    is_quant_format = bool(quant_pattern.search(log_text))
    request_success = request.get("status") == "success"
    any_ready = any_ready or ready == "0"
    any_success = any_success or request_success
    mtp_success = mtp_success or (mtp_enabled and request_success)
    capacity_failure = capacity_failure or is_capacity
    quant_format_failure = quant_format_failure or is_quant_format
    profiles.append({
        "profile": name,
        "mtp_enabled": mtp_enabled,
        "server_ready_exit_code": ready,
        "request_status": request.get("status", "not_run"),
        "completion_tokens": request.get("completion_tokens", 0),
        "quant_format_failure_matched": is_quant_format,
        "capacity_failure_matched": is_capacity,
        "server_command_path": str(root / "server_command.txt"),
        "server_log_path": str(root / "vllm_server.log"),
    })

if mtp_success:
    grade = "diagnostic_green"
elif any_ready:
    grade = "diagnostic_yellow"
elif quant_format_failure:
    grade = "diagnostic_red_quant_format"
elif capacity_failure:
    grade = "diagnostic_red_capacity"
else:
    grade = "diagnostic_red_runtime"

result = {
    "run_id": artifact_dir.name,
    "probe_grade": grade,
    "authorized_visible_devices": "4,5,6,7",
    "selected_checkpoint": "/data/node0_disk1/Public/DeepSeek-V4-Flash",
    "excluded_w8a8_checkpoint": "/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp",
    "canonical_p5_eight_card_gate_unchanged": True,
    "four_card_failure_extrapolates_to_eight_cards": False,
    "profiles": profiles,
}
(artifact_dir / "probe_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

excerpts = []
for profile in profiles:
    log_path = Path(profile["server_log_path"])
    if not log_path.exists():
        continue
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    excerpts.append(f"## {profile['profile']} last 80 lines")
    excerpts.extend(lines[-80:])
excerpt_text = "\n".join(excerpts)[:30000]
(artifact_dir / "first_failure_excerpt.txt").write_text(excerpt_text + "\n", encoding="utf-8")

candidate_names = [
    "run_context.txt",
    "git_sync_state.txt",
    "pytest_exit_code.txt",
    "runtime_versions.tsv",
    "model_capacity_preflight.tsv",
    "model_preflight_status.txt",
    "fallback_decision.txt",
    "probe_result.json",
    "first_failure_excerpt.txt",
]
manifest_lines = ["path\tsize_bytes\tunder_70kb"]
for name in candidate_names:
    path = artifact_dir / name
    if path.exists():
        manifest_lines.append(f"{path}\t{path.stat().st_size}\t{str(path.stat().st_size <= 70 * 1024).lower()}")
(artifact_dir / "return_candidate_manifest.tsv").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

summary_lines = [
    f"run_id={artifact_dir.name}",
    f"probe_grade={grade}",
    "authorized_visible_devices=4,5,6,7",
    "selected_checkpoint=DeepSeek-V4-Flash_148.66GiB",
    "excluded_w8a8_checkpoint=279.41GiB_static_overcapacity",
    f"any_server_ready={str(any_ready).lower()}",
    f"any_request_success={str(any_success).lower()}",
    f"quant_format_failure_matched={str(quant_format_failure).lower()}",
    f"capacity_failure_matched={str(capacity_failure).lower()}",
    "canonical_p5_eight_card_gate_unchanged=true",
    f"artifact_dir={artifact_dir}",
]
(artifact_dir / "mail_summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
PY
```

## 5. 结果分级

| 本轮状态 | 条件 | 开发机下一步 |
| --- | --- | --- |
| `diagnostic_green` | 选中 checkpoint 在 TP4 + MTP 下 server ready，且 `4096+64` 成功 | 只记四卡格式/运行时诊断成功；不解锁 P6，再决定 canonical 八卡 P5 |
| `diagnostic_yellow` | server ready 但请求失败，或只有 MTP off 成功 | 留在 P5，按请求或 MTP 第一失败点稳定化 |
| `diagnostic_red_quant_format` | `deepseek_v4_fp8`、FP4/MXFP4 或 NPU quantization platform gate 拒绝 | 停止四卡原 checkpoint 路线；评估 ModelSlim W4A8/其他可装入四卡的 Ascend 格式，不改包、不现场转换 |
| `diagnostic_red_capacity` | 选中 148.66GiB checkpoint 仍在权重/HBM 分配失败 | 记录真实运行时开销；不启用 offload，不切 W8A8 |
| `diagnostic_red_runtime` | architecture/parser/`kv_lora_rank`/DSA/MTP/kernel 等其他运行时错误 | 留在 P5，按首个真实失败点定向修复 |
| `blocked_resource` | NPU 4-7 任一卡不健康、不空闲或不可见 | 不启动模型，等资源恢复 |

任何四卡结果都不得把 canonical W8A8 八卡 P5 标记为 `green`，也不得把四卡失败外推为八卡 W8A8 不可行。

## 6. 回传要求

本轮只回传不超过 70KB 的状态邮件正文，不添加附件，不执行 upload-api。邮件正文必须包含：

1. 全量拉取后的 `local_head`、`origin_main`、ahead/behind，明确是否为 `0 0`；不要只写某个提交已存在。
2. `pytest` 结果、精确 runtime 版本。
3. NPU `4,5,6,7` 健康/空闲结论和启动前 HBM 小摘要。
4. 两个目录各自的 shard 数、权重字节数/GiB、四卡 256GiB 静态差额，并明确 W8A8 未启动。
5. 每个实际运行 profile 的完整启动命令、server ready 状态、请求结果、第一失败点类型和精简错误摘要；明确命令没有 `--quantization` 参数。
6. `probe_grade`、服务器 artifact 目录和以下小文件的精确路径/字节数，供开发机后续决定是否传输：

```text
run_context.txt
git_sync_state.txt
runtime_versions.tsv
model_capacity_preflight.tsv
model_preflight_status.txt
fallback_decision.txt
probe_result.json
first_failure_excerpt.txt
return_candidate_manifest.tsv
mail_summary.txt
*/server_command.txt
*/server_ready_exit_code.txt
*/request_result.json
```

raw `vllm_server.log`、raw `npu-smi` 时序、生成文本、模型文件、环境目录和完整 artifact 目录必须留在服务器。如后续需要传输具体小文件，先由开发机向用户报告精确路径、字节数、敏感性和候选方式，取得本次范围的明确选择后才能发送。
