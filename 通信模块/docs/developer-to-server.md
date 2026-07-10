# Developer to Server

## 当前任务：DeepSeek-V4-Flash W8A8-MTP 四卡拉起诊断

任务 ID：

```text
p5_deepseek_v4_flash_4card_startup_probe_v0202_2026_0710
```

用户本轮只授权：

```text
ASCEND_RT_VISIBLE_DEVICES=4,5,6,7
```

目标：使用已验证的独立 `vLLM 0.20.2+empty / vLLM-Ascend 0.20.2rc1` 环境，对 `/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp` 做一次有界 TP4/EP 拉起诊断，记录真实 DeepSeek-V4 路径的首个失败点。若 server ready，只发送一个 `4096 input + 64 output` 请求。

已知 canonical W8A8 权重约 `279.41 GiB`，而四张 64GB NPU 原始 HBM 合计约 `256 GiB`，尚未计入 KV、activation、workspace 和通信 buffer。因此容量不足是强预期，但本轮按用户要求允许一次真实拉起尝试。这是 P5 前置诊断，不是八卡 P5 验收，不是 P6 benchmark。

## 必须先做的资源门检查

1. 先用 `server_local/git_pull_remote_wins.sh` 拉取远端最新代码，然后以拉取后的本文档为唯一任务。
2. 只检查物理 NPU `4,5,6,7`。四卡必须全部健康且空闲；任一卡不满足时返回 `blocked_resource`，不启动模型。
3. 不允许使用 NPU `0,1,2,3`，不允许自动扩大到八卡。
4. 记录四卡启动前/feasible 时的 HBM used/free 小摘要。不回传 raw 时序。

## 固定实验边界

- 固定新环境：`/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.20.2rc1`。
- 固定 `TP4 + EP + quantization=ascend`、`max_model_len=8192`、`max_num_seqs=1`、eager mode。
- 使用 `additional_config.enable_flashcomm1=true` 和 `additional_config.enable_dsa_cp=true`；不再使用旧 FlashComm1 环境变量作为主配置。
- 四卡诊断为减少运行时额外 HBM 占用，通过 `additional_config.enable_mlapo=false` 关闭 MLAPO；该结果不可写成 official reference baseline。
- 首次保留 MTP。只有首次日志明确是 MTP/speculative 配置错误且不是 HBM/权重容量错误时，才允许补一次 `MTP off` 诊断。
- 一旦出现 HBM OOM、权重分配不足或其他明确容量失败，立即停止；不重试、不关 MTP 后再试。
- 不启用 `--cpu-offload-gb`、swap、NVMe offload、KV offload、UCM、LMCache 或任何权重分层。
- 不跑 128K context ladder、msprof、并发矩阵、A/B、吞吐 benchmark、瓶颈归因或 P8 real-move。
- 不安装、升级、降级、卸载或修复包；不改 vLLM/vLLM-Ascend 源码、CANN、driver、apt 或 NPU runtime。

## 建议执行命令

资源门检查确认 NPU `4,5,6,7` 全部健康且空闲后，在服务器上执行：

```bash
set -uo pipefail

cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_4card_startup_probe_v0202_2026_0710
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
SUMMARY_DIR="${ARTIFACT_DIR}/summary"
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.20.2rc1
PYTHON_BIN="${ENV_PREFIX}/bin/python"
VLLM_BIN="${ENV_PREFIX}/bin/vllm"
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
HOST=127.0.0.1
PORT=7000
SERVED_MODEL_NAME=dsv4
STARTUP_TIMEOUT_SEC=3600

mkdir -p "${ARTIFACT_DIR}" "${SUMMARY_DIR}"

set +e
if [ -x server_local/git_pull_remote_wins.sh ]; then
  server_local/git_pull_remote_wins.sh > "${ARTIFACT_DIR}/git_pull.log" 2>&1
else
  git pull --ff-only > "${ARTIFACT_DIR}/git_pull.log" 2>&1
fi
git_pull_exit_code=$?
set -e
echo "${git_pull_exit_code}" > "${ARTIFACT_DIR}/git_pull_exit_code.txt"
if [ "${git_pull_exit_code}" -ne 0 ]; then
  echo "blocked_git_pull" > "${ARTIFACT_DIR}/probe_status.txt"
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
  echo "commit=$(git rev-parse HEAD)"
  echo "timestamp=$(date -Is)"
  echo "environment=${ENV_PREFIX}"
  echo "model_path=${MODEL_PATH}"
  echo "ASCEND_RT_VISIBLE_DEVICES=${ASCEND_RT_VISIBLE_DEVICES}"
  echo "tensor_parallel_size=4"
  echo "max_model_len=8192"
  echo "max_num_seqs=1"
  echo "request_shape=4096+64"
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

"${PYTHON_BIN}" - "${ARTIFACT_DIR}" "${MODEL_PATH}" <<'PY'
import csv
import importlib.metadata as metadata
import json
import platform
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
model_path = Path(sys.argv[2])

def pkg(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "missing"

config = {}
try:
    config = json.loads((model_path / "config.json").read_text(encoding="utf-8"))
except Exception as exc:
    config = {"metadata_error": f"{type(exc).__name__}: {exc}"}

shards = sorted(path for path in model_path.glob("quant_model_weights-*.safetensors") if not path.name.startswith("._"))
shard_bytes = sum(path.stat().st_size for path in shards)
metadata_row = {
    "model_path": str(model_path),
    "path_exists": str(model_path.exists()).lower(),
    "architecture": ",".join(config.get("architectures", []) or []),
    "model_type": config.get("model_type", ""),
    "canonical_shard_count": len(shards),
    "canonical_shard_bytes": shard_bytes,
    "canonical_shard_gib": round(shard_bytes / 1024**3, 6),
    "four_card_raw_hbm_gib": 256,
    "static_capacity_margin_gib": round(256 - shard_bytes / 1024**3, 6),
}
with (artifact_dir / "model_capacity_preflight.tsv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(metadata_row), delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerow(metadata_row)

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
        f"DeepSeek four-card startup probe block {block:06d}. "
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
    --quantization ascend
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
if grep -Eqi 'out of memory|npu[^[:cntrl:]]*oom|failed to allocate|not enough memory|insufficient memory' "${MTP_LOG}"; then
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

for name, mtp_enabled in (("mtp_on", True), ("mtp_off", False)):
    root = artifact_dir / name
    if not root.exists():
        continue
    ready = (root / "server_ready_exit_code.txt").read_text(encoding="utf-8", errors="replace").strip() if (root / "server_ready_exit_code.txt").exists() else "missing"
    request = {}
    if (root / "request_result.json").exists():
        request = json.loads((root / "request_result.json").read_text(encoding="utf-8"))
    log_text = (root / "vllm_server.log").read_text(encoding="utf-8", errors="replace") if (root / "vllm_server.log").exists() else ""
    is_capacity = bool(re.search(r"out of memory|npu.*oom|failed to allocate|not enough memory|insufficient memory", log_text, re.I))
    request_success = request.get("status") == "success"
    any_ready = any_ready or ready == "0"
    any_success = any_success or request_success
    mtp_success = mtp_success or (mtp_enabled and request_success)
    capacity_failure = capacity_failure or is_capacity
    profiles.append({
        "profile": name,
        "mtp_enabled": mtp_enabled,
        "server_ready_exit_code": ready,
        "request_status": request.get("status", "not_run"),
        "completion_tokens": request.get("completion_tokens", 0),
        "capacity_failure_matched": is_capacity,
        "server_command_path": str(root / "server_command.txt"),
        "server_log_path": str(root / "vllm_server.log"),
    })

if mtp_success:
    grade = "diagnostic_green"
elif any_ready:
    grade = "diagnostic_yellow"
elif capacity_failure:
    grade = "diagnostic_red_expected_capacity"
else:
    grade = "diagnostic_red_runtime"

result = {
    "run_id": artifact_dir.name,
    "probe_grade": grade,
    "authorized_visible_devices": "4,5,6,7",
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
    "git_pull_exit_code.txt",
    "pytest_exit_code.txt",
    "runtime_versions.tsv",
    "model_capacity_preflight.tsv",
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
    f"any_server_ready={str(any_ready).lower()}",
    f"any_request_success={str(any_success).lower()}",
    f"capacity_failure_matched={str(capacity_failure).lower()}",
    "canonical_p5_eight_card_gate_unchanged=true",
    f"artifact_dir={artifact_dir}",
]
(artifact_dir / "mail_summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
PY
```

## 结果分级

| 本轮状态 | 条件 | 开发机下一步 |
| --- | --- | --- |
| `diagnostic_green` | TP4 + MTP server ready，且 `4096+64` 成功 | 只记四卡诊断成功；不解锁 P6，再决定是否等八卡 P5 |
| `diagnostic_yellow` | server ready 但请求失败，或只有 MTP off 成功 | 留在 P5，按第一失败点做稳定化 |
| `diagnostic_red_expected_capacity` | HBM OOM、权重分配或其他容量失败 | 四卡 W8A8 原位拉起路线停止；等八卡授权，或另立更小 checkpoint/offload 决策 |
| `diagnostic_red_runtime` | 容量失败之前出现 architecture/parser/MTP/kernel/runtime 错误 | 留在 P5，对该首失败点定向修复 |
| `blocked_resource` | NPU 4-7 任一卡不健康、不空闲或不可见 | 不启动模型，等资源恢复 |

任何四卡结果都不得把 canonical 八卡 P5 标记为 `green`，也不得把四卡失败外推为八卡不可行。

## 回传要求

本轮只回传不超过 70KB 的状态邮件正文，不添加附件，不执行 upload-api。邮件正文必须包含：

1. 拉取后 commit、`pytest` 结果、精确 runtime 版本。
2. NPU `4,5,6,7` 健康/空闲结论和启动前 HBM 小摘要。
3. canonical shard 数、权重字节数/GiB、四卡 256GiB 静态差额。
4. 每个实际运行 profile 的完整启动命令、server ready 状态、请求结果、第一失败点类型和精简错误摘要。
5. `probe_grade`、服务器 artifact 目录和以下小文件的精确路径/字节数，供开发机后续决定是否传输：

```text
run_context.txt
runtime_versions.tsv
model_capacity_preflight.tsv
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
