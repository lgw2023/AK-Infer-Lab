# Developer to Server

## 当前任务：复用已建成的 v0.22.1rc1 栈，继续官方 FP8/FP4 checkpoint 四卡 runtime probe

任务 ID：

```text
p5_deepseek_v4_flash_4card_fp8_runtime_resume_v0221rc1_2026_0711
```

本轮唯一授权设备范围：

```text
ASCEND_RT_VISIBLE_DEVICES=4,5,6,7
```

目标：完整同步远端 `main` 后，**不重建、不修包、不修改**上一轮已经建成的独立
`vLLM 0.22.1+empty / vLLM-Ascend 0.22.1rc1` 环境。先用精确版本、核心 import、
`supported_quantization`、模型 metadata 和项目合同验收该环境；全量 `pip check` 只作为
诊断记录，只有出现白名单以外的新冲突才阻塞。预检通过后，继续上一轮尚未执行的
TP4/EP `base_no_mtp -> mtp_on` runtime probe。

上一轮服务器事实：

- 旧任务 `p5_deepseek_v4_flash_4card_fp8_stack_upgrade_probe_v0221rc1_2026_0710`
  已完整同步到 `c5108614b54240e5f04446ac821c02cf095275e9`。
- 新环境和新源码已功能性构建完成：vLLM `0.22.1+empty`、vLLM-Ascend
  `0.22.1rc1`、torch/torch-npu `2.10.0`、transformers `5.5.4`、
  triton-ascend `3.2.1`；vLLM source 为干净的
  `v0.22.1@0decac0d96c42b49572498019f0a0e3600f50398`。
- NPU 平台已返回 `['ascend', 'compressed-tensors', 'fp8', 'deepseek_v4_fp8']`，
  因而 `0.20.2rc1` 的量化注册阻塞已经在静态/注册层关闭。
- 全量 `pip check` 的 11 行冲突全部来自旧环境同样存在的 profiling/辅助包；它们不涉及
  vLLM、vLLM-Ascend、torch、torch-npu、transformers 或 triton-ascend。上一轮错误地
  把该全量诊断设为硬门，所以没有执行模型 preflight、权重加载、server ready 或请求。
- 旧脚本在函数内部启用 `set -e` 后泄漏到 caller，导致状态文件未按设计写出。本轮所有
  可能失败的 gate 均在 subshell 内执行并由 caller 显式捕获退出码。
- NPU 4-7 当时健康、空闲、每卡约 62.1 GiB 可用；NPU 0-3 有其他任务，禁止触碰。

## 1. 仓库同步：完整拉取 `main`

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

1. 必须拉取远端 `main` 的全部缺失提交；禁止 `cherry-pick` 单提交、detached checkout
   或单文件覆盖。
2. 必须满足 `HEAD == origin/main` 且 ahead/behind=`0 0`。
3. 同步后重新打开本文档。只有任务 ID 仍为
   `p5_deepseek_v4_flash_4card_fp8_runtime_resume_v0221rc1_2026_0711` 才继续。
4. 同步整个仓库不等于执行全部任务。本轮不运行历史 handoff、八卡任务、P6、P8、
   msprof 或其他 workload。

## 2. 固定对象与禁止项

```text
已建成的新环境（本轮只读复用）:
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1

已建成的新源码（本轮只读复用）:
/data/node0_disk1/vllm-0.22.1
v0.22.1@0decac0d96c42b49572498019f0a0e3600f50398

已安装的 vLLM-Ascend:
v0.22.1rc1@5f6faa0cb8830f667266f3b8121cd1383606f2a1

旧环境（只读保留）:
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.20.2rc1

运行对象:
/data/node0_disk1/Public/DeepSeek-V4-Flash

退役 inventory（禁止启动、转换或 fallback）:
/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
```

禁止项：

- 禁止 `conda create`、`pip install`、`pip uninstall`、删除或覆盖新旧环境。
- 禁止修改 vLLM/vLLM-Ascend 源码、CANN、driver、firmware、apt、系统 Python。
- 禁止为了让全量 `pip check` 变绿而安装、降级或升级 profiling/辅助包。
- 禁止显式 `--quantization`，禁止改 checkpoint config。
- 禁止使用 NPU 0-3；禁止扩成八卡。
- 禁止 W8A8、CPU/NVMe/KV offload、128K ladder、并发矩阵、msprof、P6、A/B。

## 3. 资源门

开始前人工检查 `npu-smi info`：

1. 物理 NPU 4-7 必须全部 `Health=OK`、空闲且无进程；否则写
   `blocked_resource` 后停止。
2. NPU 0-3 上的其他任务不得停止、kill、重启或纳入本轮进程。
3. 记录启动前、每个 profile ready/失败后和最终释放后的 NPU 4-7 HBM 摘要；raw
   `npu-smi` 留在服务器。

## 4. 复用环境预检

以下 gate 使用 subshell；即使失败也必须由 caller 写出状态文件，禁止再次出现
`set -e` 泄漏。

```bash
set +e
set -uo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_4card_fp8_runtime_resume_v0221rc1_2026_0711
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
NEW_ENV=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
BASE_ENV=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.20.2rc1
VLLM_SRC=/data/node0_disk1/vllm-0.22.1
VLLM_COMMIT=0decac0d96c42b49572498019f0a0e3600f50398
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash
RETIRED_W8A8_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
PYTHON_BIN="${NEW_ENV}/bin/python"
VLLM_BIN="${NEW_ENV}/bin/vllm"

mkdir -p "${ARTIFACT_DIR}"

if ! git fetch origin main > "${ARTIFACT_DIR}/git_fetch_verify.log" 2>&1; then
  echo blocked_git_fetch > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi
LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_MAIN="$(git rev-parse origin/main)"
{
  printf 'local_head=%s\n' "${LOCAL_HEAD}"
  printf 'origin_main=%s\n' "${REMOTE_MAIN}"
  printf 'ahead_behind='
  git rev-list --left-right --count HEAD...origin/main
} > "${ARTIFACT_DIR}/git_sync_state.txt"

if [ "${LOCAL_HEAD}" != "${REMOTE_MAIN}" ]; then
  echo blocked_git_not_fully_synced > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi
if ! grep -q 'p5_deepseek_v4_flash_4card_fp8_runtime_resume_v0221rc1_2026_0711' 通信模块/docs/developer-to-server.md; then
  echo blocked_handoff_task_id_changed > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u

export PATH="${NEW_ENV}/bin:${PATH}"
export ASCEND_RT_VISIBLE_DEVICES=4,5,6,7
export VLLM_PLUGINS=ascend
export VLLM_USE_V1=1
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export OMP_PROC_BIND=false
export OMP_NUM_THREADS=8
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export LD_PRELOAD="/usr/lib/aarch64-linux-gnu/libjemalloc.so.2${LD_PRELOAD:+:${LD_PRELOAD}}"
export HCCL_BUFFSIZE=1024
export TASK_QUEUE_ENABLE=1
export HCCL_OP_EXPANSION_MODE=AIV

run_preflight() (
  set -euo pipefail

  test -x "${PYTHON_BIN}"
  test -x "${VLLM_BIN}"
  test -d "${BASE_ENV}"
  test -d "${VLLM_SRC}/.git"
  test -z "$(git -C "${VLLM_SRC}" status --porcelain)"
  test "$(git -C "${VLLM_SRC}" rev-parse HEAD)" = "${VLLM_COMMIT}"

  set +e
  "${PYTHON_BIN}" -m pip check > "${ARTIFACT_DIR}/pip_check_full.txt" 2>&1
  PIP_CHECK_EXIT_CODE=$?
  set -e
  echo "${PIP_CHECK_EXIT_CODE}" > "${ARTIFACT_DIR}/pip_check_exit_code.txt"

  "${PYTHON_BIN}" - "${ARTIFACT_DIR}" "${PIP_CHECK_EXIT_CODE}" <<'PY'
import json
import re
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
exit_code = int(sys.argv[2])
lines = [line.strip() for line in (artifact_dir / "pip_check_full.txt").read_text(
    encoding="utf-8", errors="replace").splitlines() if line.strip()]
allowed_requirements = {
    "mindstudio-kpp": {"plotly"},
    "ms-service-profiler": {
        "matplotlib",
        "msguard",
        "openpyxl",
        "opentelemetry-exporter-otlp-proto-grpc",
        "opentelemetry-exporter-otlp-proto-http",
        "pandas",
    },
    "te": {"ml-dtypes", "tornado"},
    "pyvers": {"packaging"},
    "opencv-python-headless": {"numpy"},
}

def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()

unexpected = []
if exit_code not in (0, 1):
    unexpected.append(f"pip_check_exit_code={exit_code}")
elif exit_code == 1:
    if not lines:
        unexpected.append("pip_check_exit_1_without_conflict_lines")
    for line in lines:
        match = re.match(r"^([A-Za-z0-9_.-]+)\s", line)
        dependent = normalize(match.group(1)) if match else ""
        normalized_line = normalize(line)
        allowed_targets = allowed_requirements.get(dependent, set())
        if not allowed_targets or not any(target in normalized_line for target in allowed_targets):
            unexpected.append(line)

if unexpected:
    status = "blocked_unexpected_dependency_conflict"
elif exit_code == 0:
    status = "clean"
else:
    status = "known_non_core_conflicts_only"

result = {
    "policy": "full_pip_check_is_diagnostic_known_non_core_conflicts_are_allowed",
    "exit_code": exit_code,
    "conflict_line_count": len(lines),
    "allowed_requirements": {
        dependent: sorted(requirements)
        for dependent, requirements in sorted(allowed_requirements.items())
    },
    "unexpected_conflicts": unexpected,
    "status": status,
}
(artifact_dir / "pip_check_classification.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8")
if unexpected:
    raise SystemExit(1)
PY

  set +e
  "${PYTHON_BIN}" -m pytest tests/inference_contracts -q \
    > "${ARTIFACT_DIR}/pytest.log" 2>&1
  PYTEST_EXIT_CODE=$?
  set -e
  echo "${PYTEST_EXIT_CODE}" > "${ARTIFACT_DIR}/pytest_exit_code.txt"
  test "${PYTEST_EXIT_CODE}" -eq 0

  "${PYTHON_BIN}" - "${MODEL_PATH}" "${ARTIFACT_DIR}" <<'PY'
import csv
import importlib.metadata as metadata
import json
import platform
import sys
from pathlib import Path

model_path = Path(sys.argv[1])
artifact_dir = Path(sys.argv[2])

def version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "missing"

import torch
import torch_npu  # noqa: F401
import vllm
import vllm_ascend
from vllm.platforms import current_platform

supported = list(current_platform.supported_quantization)
config = json.loads((model_path / "config.json").read_text(encoding="utf-8"))
quant = config.get("quantization_config") or {}
shards = sorted(p for p in model_path.glob("model-*.safetensors") if not p.name.startswith("._"))
weight_bytes = sum(p.stat().st_size for p in shards)

rows = [
    ("python", platform.python_version()),
    ("torch", version("torch")),
    ("torch_npu", version("torch-npu")),
    ("vllm", version("vllm")),
    ("vllm_ascend", version("vllm-ascend")),
    ("triton_ascend", version("triton-ascend")),
    ("transformers", version("transformers")),
    ("npu_available", str(torch.npu.is_available()).lower()),
    ("visible_device_count", str(torch.npu.device_count())),
    ("supported_quantization", ",".join(supported)),
]
with (artifact_dir / "runtime_versions.tsv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["name", "value"])
    writer.writerows(rows)

preflight = {
    "model_path": str(model_path),
    "shard_count": len(shards),
    "weight_bytes": weight_bytes,
    "architecture": config.get("architectures"),
    "model_type": config.get("model_type"),
    "quant_method": quant.get("quant_method"),
    "expert_dtype": config.get("expert_dtype"),
    "supported_quantization": supported,
}
(artifact_dir / "model_preflight.json").write_text(
    json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

ok = (
    platform.python_version() == "3.11.15"
    and version("vllm") == "0.22.1+empty"
    and version("vllm-ascend") == "0.22.1rc1"
    and version("torch") == "2.10.0"
    and version("torch-npu") == "2.10.0"
    and version("transformers") == "5.5.4"
    and version("triton-ascend") == "3.2.1"
    and torch.npu.is_available()
    and torch.npu.device_count() == 4
    and "fp8" in supported
    and "deepseek_v4_fp8" in supported
    and len(shards) == 46
    and weight_bytes == 159617149040
    and config.get("architectures") == ["DeepseekV4ForCausalLM"]
    and config.get("model_type") == "deepseek_v4"
    and quant.get("quant_method") == "fp8"
    and config.get("expert_dtype") == "fp4"
)
(artifact_dir / "preflight_status.txt").write_text(
    "ready\n" if ok else "blocked_preflight\n", encoding="utf-8")
if not ok:
    raise SystemExit(1)
PY
)

set +e
run_preflight > "${ARTIFACT_DIR}/preflight.log" 2>&1
PREFLIGHT_EXIT_CODE=$?
echo "${PREFLIGHT_EXIT_CODE}" > "${ARTIFACT_DIR}/preflight_exit_code.txt"

if [ "${PREFLIGHT_EXIT_CODE}" -ne 0 ]; then
  echo blocked_preflight > "${ARTIFACT_DIR}/probe_status.txt"
  tail -n 120 "${ARTIFACT_DIR}/preflight.log" > "${ARTIFACT_DIR}/first_failure_excerpt.txt"
  exit 0
fi

echo reused_verified_existing > "${ARTIFACT_DIR}/environment_status.txt"
npu-smi info > "${ARTIFACT_DIR}/npu_smi_before.txt" 2>&1 || true
```

全量 `pip check` 的判定规则：

- `exit 0`：通过。
- `exit 1` 且每行同时匹配已报告的 dependent/requirement 组合：`mindstudio-kpp→plotly`；
  `ms-service-profiler→matplotlib/msguard/openpyxl/opentelemetry exporter/pandas`；
  `te→ml-dtypes/tornado`；`pyvers→packaging`；`opencv-python-headless→numpy`。记录为
  `known_non_core_conflicts_only`，继续。
- 出现其他 dependent、同一 dependent 的新 requirement、无法解析的新行或其他退出码：
  `blocked_preflight`，停止。
- 即使只出现已知冲突，也禁止修包；这不是生产环境健康背书，只是把与当前推理核心无关、
  且已证明为克隆前遗留的问题从本轮 runtime gate 中隔离。

预检脚本完成后，人工再次确认物理 NPU 4-7 健康、空闲且无进程；不满足则写
`blocked_resource` 并停止。

## 5. 两个有序 profile

只允许以下顺序：

1. `base_no_mtp`：验证格式门、权重加载、server ready 和一个 `4096+64` 请求。
2. 只有 `base_no_mtp` 请求成功，才运行 `mtp_on`；除此之外立即停止，不做 fallback。

两个 profile 都不传 `--quantization`，不改 checkpoint config。

```bash
HOST=127.0.0.1
PORT=7000
SERVED_MODEL_NAME=dsv4-official-fp8-four-card
STARTUP_TIMEOUT_SEC=3600

wait_health_or_exit() {
  local pid="$1"
  local deadline=$((SECONDS + STARTUP_TIMEOUT_SEC))
  while [ "${SECONDS}" -lt "${deadline}" ]; do
    if ! kill -0 "${pid}" 2>/dev/null; then return 2; fi
    if curl -fsS --max-time 5 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then return 0; fi
    sleep 5
  done
  return 1
}

stop_profile() {
  local pid="$1"
  kill -- "-${pid}" >/dev/null 2>&1 || kill "${pid}" >/dev/null 2>&1 || true
  wait "${pid}" >/dev/null 2>&1 || true
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
i = 0
while len(ids) < 4096:
    i += 1
    ids.extend(tokenizer(
        f"DeepSeek official FP8 four-card runtime probe block {i:06d}. ",
        add_special_tokens=False,
    ).input_ids)
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
    base_url + "/v1/completions",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
started = time.perf_counter()
result = {
    "status": "failed",
    "input_tokens": 4096,
    "requested_output_tokens": 64,
    "completion_tokens": 0,
    "error": "",
}
try:
    with urllib.request.urlopen(request, timeout=7200) as response:
        body = json.loads(response.read().decode())
        usage = body.get("usage") or {}
        result["http_status"] = response.status
        result["prompt_tokens"] = int(usage.get("prompt_tokens") or 0)
        result["completion_tokens"] = int(usage.get("completion_tokens") or 0)
        result["status"] = (
            "success"
            if response.status == 200
            and result["prompt_tokens"] == 4096
            and result["completion_tokens"] == 64
            else "failed"
        )
except Exception as exc:
    result["error"] = f"{type(exc).__name__}: {exc}"
result["client_wall_s"] = round(time.perf_counter() - started, 6)
(profile_dir / "request_result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    --host "${HOST}" --port "${PORT}"
    --block-size 128
    --tokenizer-mode deepseek_v4
    --tool-call-parser deepseek_v4
    --enable-auto-tool-choice
    --reasoning-parser deepseek_v4
    --no-enable-prefix-caching
    --enforce-eager
    --additional-config '{"enable_flashcomm1":true,"enable_dsa_cp":true,"enable_cpu_binding":true,"multistream_overlap_shared_expert":false}'
  )
  if [ "${mtp_mode}" = mtp_on ]; then
    cmd+=(--speculative-config '{"num_speculative_tokens":1,"method":"mtp","enforce_eager":true}')
  fi

  printf '%q ' "${cmd[@]}" > "${profile_dir}/server_command.txt"
  printf '\n' >> "${profile_dir}/server_command.txt"
  npu-smi info > "${profile_dir}/npu_smi_before.txt" 2>&1 || true

  setsid "${cmd[@]}" > "${profile_dir}/vllm_server.log" 2>&1 &
  local server_pid=$!
  echo "${server_pid}" > "${profile_dir}/server_pid.txt"
  wait_health_or_exit "${server_pid}"
  local ready_exit_code=$?
  echo "${ready_exit_code}" > "${profile_dir}/server_ready_exit_code.txt"
  if [ "${ready_exit_code}" -eq 0 ]; then
    run_single_request "${profile_dir}" > "${profile_dir}/request_client.log" 2>&1
    echo "$?" > "${profile_dir}/request_client_exit_code.txt"
  else
    echo not_run_server_not_ready > "${profile_dir}/request_client_exit_code.txt"
  fi
  npu-smi info > "${profile_dir}/npu_smi_after.txt" 2>&1 || true
  stop_profile "${server_pid}"
}

run_profile base_no_mtp mtp_off
BASE_STATUS="$("${PYTHON_BIN}" -c 'import json, pathlib; p=pathlib.Path("'"${ARTIFACT_DIR}"'/base_no_mtp/request_result.json"); print(json.loads(p.read_text()).get("status", "not_run") if p.exists() else "not_run")')"

if [ "${BASE_STATUS}" = success ]; then
  echo base_success_run_mtp > "${ARTIFACT_DIR}/profile_decision.txt"
  run_profile mtp_on mtp_on
else
  echo base_failed_stop_no_fallback > "${ARTIFACT_DIR}/profile_decision.txt"
fi

npu-smi info > "${ARTIFACT_DIR}/npu_smi_final.txt" 2>&1 || true

"${PYTHON_BIN}" - "${ARTIFACT_DIR}" <<'PY'
import json
import re
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])

def request_result(name):
    path = artifact_dir / name / "request_result.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"status": "not_run"}

def log_text(name):
    path = artifact_dir / name / "vllm_server.log"
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""

def ready_code(name):
    path = artifact_dir / name / "server_ready_exit_code.txt"
    return path.read_text(encoding="utf-8").strip() if path.exists() else "not_run"

base = request_result("base_no_mtp")
mtp = request_result("mtp_on")
base_log = log_text("base_no_mtp")
all_logs = base_log + "\n" + log_text("mtp_on")

quant_re = re.compile(r"deepseek_v4_fp8.*(not supported|unsupported)|unsupported.*(fp4|mxfp4)|quantization.*(not supported|unsupported)", re.I)
weight_re = re.compile(r"(weight|safetensor|checkpoint).*(shape|dtype|scale|name|loader|load).*(error|fail|mismatch|missing)|KeyError.*weight", re.I)
capacity_re = re.compile(r"out of memory|npu.*oom|failed to allocate|not enough memory|insufficient memory", re.I)

if base.get("status") == "success" and mtp.get("status") == "success":
    grade = "diagnostic_green"
    first_failure_stage = "none"
elif base.get("status") == "success":
    grade = "diagnostic_yellow_mtp"
    first_failure_stage = "mtp_startup_or_request"
elif quant_re.search(base_log):
    grade = "diagnostic_red_quant_format"
    first_failure_stage = "model_config_or_quantization_scheme"
elif weight_re.search(base_log):
    grade = "diagnostic_red_weight_load"
    first_failure_stage = "weight_load"
elif capacity_re.search(base_log):
    grade = "diagnostic_red_capacity"
    first_failure_stage = "hbm_or_weight_allocation"
else:
    grade = "diagnostic_red_runtime"
    first_failure_stage = "architecture_operator_collective_or_request"

profiles = []
for name in ("base_no_mtp", "mtp_on"):
    root = artifact_dir / name
    if root.exists():
        request = request_result(name)
        profiles.append({
            "profile": name,
            "server_ready_exit_code": ready_code(name),
            "request_status": request.get("status", "not_run"),
            "prompt_tokens": request.get("prompt_tokens", 0),
            "completion_tokens": request.get("completion_tokens", 0),
            "server_command_path": str(root / "server_command.txt"),
            "server_log_path": str(root / "vllm_server.log"),
        })

result = {
    "run_id": artifact_dir.name,
    "probe_grade": grade,
    "first_failure_stage": first_failure_stage,
    "environment_status": "reused_verified_existing",
    "pip_check_policy": "known_non_core_conflicts_are_diagnostic_only",
    "authorized_visible_devices": "4,5,6,7",
    "model_path": "/data/node0_disk1/Public/DeepSeek-V4-Flash",
    "checkpoint_format": "fp8_non_expert_plus_fp4_experts",
    "retired_w8a8_started": False,
    "explicit_quantization_argument_used": False,
    "profiles": profiles,
    "residual_process_check": "operator_confirms_from_npu_smi_final",
}
(artifact_dir / "probe_result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(artifact_dir / "probe_status.txt").write_text(grade + "\n", encoding="utf-8")

excerpts = []
for name in ("base_no_mtp", "mtp_on"):
    text = log_text(name)
    if text:
        excerpts.append(f"## {name} last 100 lines")
        excerpts.extend(text.splitlines()[-100:])
(artifact_dir / "first_failure_excerpt.txt").write_text(
    "\n".join(excerpts)[:30000] + "\n", encoding="utf-8")
PY
```

## 6. 分级与停止规则

| 状态 | 条件 |
| --- | --- |
| `diagnostic_green` | `base_no_mtp` 和 `mtp_on` 均 ready，且各完成一个 `4096+64` 请求 |
| `diagnostic_yellow_mtp` | base 请求成功，但 MTP profile 未 ready 或请求失败 |
| `diagnostic_red_quant_format` | 新栈仍拒绝 `deepseek_v4_fp8` / FP4 / quantization format |
| `diagnostic_red_weight_load` | 已通过量化注册门，但 checkpoint 权重名称、shape、scale、dtype 或 loader 失败 |
| `diagnostic_red_capacity` | HBM/权重分配 OOM 或容量不足 |
| `diagnostic_red_runtime` | architecture/parser/DSA/operator/collective/request 等其他真实首错 |
| `blocked_preflight` | 精确版本、核心 import、源码、模型 metadata、合同或依赖冲突白名单不满足 |
| `blocked_resource` | NPU 4-7 不健康、不空闲或不可见 |

停止规则：

- base 失败后立即停止；禁止用 W8A8、其他模型格式、offload、context 降级或源码 patch
  继续试错。
- 禁止任何显式 `--quantization`。
- 即使四卡 green，也不自动使用 NPU 0-3，不执行未来八卡任务；等待新的明确授权。
- 最终人工确认 NPU 4-7 已释放、无本轮残留；不得 kill NPU 0-3 上的其他任务。

## 7. 回传要求

只发送不超过 70KB 的状态邮件正文；不添加附件，不执行 upload-api。邮件标题建议：

```text
[P5-FP8-v0221rc1-resume] <probe_grade> | <first_failure_or_success> | 2026-07-11
```

正文必须包含：

1. `local_head`、`origin_main`、ahead/behind，明确完整同步而非单提交。
2. 明确复用了既有新环境，未运行 conda/pip 修改；旧环境和源码均未改。
3. 精确版本、source commit/clean 状态、核心 import、`supported_quantization`。
4. 全量 `pip check` 退出码、冲突行数、dependent/requirement 集合、白名单分类；明确是否出现新冲突。
5. 项目 inference contracts、模型 46 分片/字节数、FP8+FP4 metadata。
6. NPU 4-7 健康/空闲、启动前与最终 HBM、残留进程；明确 NPU 0-3 未触碰。
7. 每个实际 profile 的完整命令、ready、请求 token 数、第一失败点和精简错误；明确没有
   `--quantization`。
8. `probe_grade`、artifact 目录，以及下列小文件的精确路径和字节数：

```text
git_sync_state.txt
environment_status.txt
pip_check_exit_code.txt
pip_check_classification.json
runtime_versions.tsv
model_preflight.json
preflight_status.txt
preflight_exit_code.txt
pytest_exit_code.txt
profile_decision.txt
probe_result.json
first_failure_excerpt.txt
*/server_command.txt
*/server_ready_exit_code.txt
*/request_result.json
```

raw `preflight.log`、`pip_check_full.txt`、`vllm_server.log`、raw `npu-smi`、模型、conda
环境、源码目录和完整 artifact 目录全部留在服务器。后续如需传某个小文件，仍必须先报告
精确路径、字节数、敏感性与候选传输方式，由用户逐文件选择后再执行。
