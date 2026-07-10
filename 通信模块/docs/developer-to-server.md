# Developer to Server

## 当前任务：构建 v0.22.1rc1 独立栈并复跑官方 FP8/FP4 checkpoint 四卡拉起

任务 ID：

```text
p5_deepseek_v4_flash_4card_fp8_stack_upgrade_probe_v0221rc1_2026_0710
```

本轮唯一授权设备范围：

```text
ASCEND_RT_VISIBLE_DEVICES=4,5,6,7
```

目标：完整同步远端 `main` 后，在不修改任何旧环境的前提下，新建独立 `vLLM 0.22.1+empty / vLLM-Ascend 0.22.1rc1` 环境。先确认该栈在 NPU 平台注册 `deepseek_v4_fp8`，再仅对 `/data/node0_disk1/Public/DeepSeek-V4-Flash` 执行 TP4/EP、8K 上限的真实拉起和单请求 smoke。

上一轮服务器事实已经关闭：

- `vLLM 0.20.2+empty / vLLM-Ascend 0.20.2rc1` 在 `ModelConfig` 校验阶段返回 `deepseek_v4_fp8 quantization is currently not supported in npu`。
- 失败发生在权重加载、HBM 分配和 MTP 初始化之前；不是容量、MTP 或设备健康问题。
- NPU `4,5,6,7` 全部健康、空闲，任务结束后无残留进程。

本轮路线变更：

- 项目停止使用 `/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp`；该目录只保留历史 inventory，禁止启动、转换、benchmark 或作为 fallback。
- 主对象改为官方 `DeepSeek-V4-Flash` checkpoint。其准确格式是“非 expert 权重 FP8 + expert 权重 FP4”的混合 checkpoint，不是纯 FP8。
- `vLLM-Ascend v0.22.1rc1@5f6faa0` 已在源码中把 `fp8` 和 `deepseek_v4_fp8` 加入 NPU `supported_quantization`，并含官方 checkpoint 对应的 FP8 linear / FP4 expert Ascend scheme；这只是下发本轮探针的源码依据，不是本机已通过的结论。
- 当前 vLLM-Ascend 官方 DeepSeek-V4 部署教程仍以 W8A8 为示例，因此本轮必须把官方 FP8/FP4 checkpoint 结果标为项目 runtime probe，不得提前写成官方 Ascend deployment baseline。

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

1. 必须拉取远端 `main` 的全部缺失提交；禁止 `cherry-pick` 单提交、detached checkout 或单文件覆盖。
2. 必须满足 `HEAD == origin/main` 且 ahead/behind=`0 0`。
3. 同步后重新打开本文档。只有任务 ID 仍为 `p5_deepseek_v4_flash_4card_fp8_stack_upgrade_probe_v0221rc1_2026_0710` 才继续。
4. 同步整个仓库不等于执行全部任务。本轮不运行历史 handoff、P8、P6、msprof 或其他 workload。

## 2. 固定版本、路径和不变项

```text
基础环境（只读保留）:
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.20.2rc1

新环境:
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1

新 vLLM 源码:
/data/node0_disk1/vllm-0.22.1
v0.22.1@0decac0d96c42b49572498019f0a0e3600f50398

vLLM-Ascend:
v0.22.1rc1@5f6faa0cb8830f667266f3b8121cd1383606f2a1
wheel=vllm_ascend-0.22.1rc1-cp311-cp311-manylinux_2_34_aarch64.whl
本地开发机从 Ascend index 观测的 wheel SHA-256:
0e08c50ff27b174232c65bbb7feb3605734b09982bdc786d1b874d9ac9615ff1

保持不变:
Python 3.11 / CANN 9.0.0 / torch 2.10.0 / torch-npu 2.10.0
torchvision 0.25.0 / torchaudio 2.10.0 / triton-ascend 3.2.1

目标更新:
transformers 5.5.4
vLLM 0.22.1+empty
vLLM-Ascend 0.22.1rc1
```

约束：

- 禁止修改、删除或重装基础环境和原 `ak-infer-lab` 环境。
- 禁止修改共享 `/data/node0_disk1/vllm`、旧 `/data/node0_disk1/vllm-0.20.2` 或其 tag。
- 禁止改 CANN、driver、firmware、apt、系统 Python 或系统级 NPU runtime。
- 禁止 patch vLLM/vLLM-Ascend 源码，禁止绕过 `supported_quantization` 校验。
- 若新环境或新源码目录已存在但无法证明版本完全一致，不删除、不覆盖，返回 `blocked_existing_target_requires_review`。
- vLLM 0.22.1 的 build-system 声明 `torch==2.11.0`，而 vLLM-Ascend 0.22.1rc1 固定 `torch/torch-npu==2.10.0`。因此沿用已验证的 `VLLM_TARGET_DEVICE=empty + --no-deps + --no-build-isolation` 路线，并在独立环境中显式安装除 torch 2.11 外的 build tooling；禁止让 pip 把 torch 主栈升级到 2.11。

## 3. 资源门

环境构建前后均检查：

1. 只允许物理 NPU `4,5,6,7`；禁止接触 NPU `0,1,2,3`，禁止扩大到八卡。
2. 四卡必须全部 `Health=OK`、空闲且无进程；否则返回 `blocked_resource`，环境可保留，但不启动模型。
3. 记录启动前、每个 profile ready/失败后和最终释放后的四卡 HBM 摘要。raw `npu-smi` 输出留在服务器。
4. 模型必须仍是 46 个连续分片、权重字节数 `159617149040`；config 必须为 `DeepseekV4ForCausalLM`、`model_type=deepseek_v4`、`quant_method=fp8`、`expert_dtype=fp4`。不满足则返回 `blocked_model_files`。

## 4. 构建独立环境

从项目根目录执行。环境构建日志留在服务器；任一步失败即返回 `blocked_environment`，不得改用 `main`、nightly、其他 rc 或源码 patch。

```bash
set -uo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_4card_fp8_stack_upgrade_probe_v0221rc1_2026_0710
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
BASE_ENV=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.20.2rc1
NEW_ENV=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
VLLM_SRC=/data/node0_disk1/vllm-0.22.1
VLLM_COMMIT=0decac0d96c42b49572498019f0a0e3600f50398
WHEEL_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/.wheel-cache/vllm-ascend-0.22.1rc1
WHEEL_SHA256=0e08c50ff27b174232c65bbb7feb3605734b09982bdc786d1b874d9ac9615ff1
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash
RETIRED_W8A8_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp

mkdir -p "${ARTIFACT_DIR}" "${WHEEL_DIR}"

git fetch origin main > "${ARTIFACT_DIR}/git_fetch_verify.log" 2>&1
LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_MAIN="$(git rev-parse origin/main)"
{
  printf 'local_head=%s\n' "${LOCAL_HEAD}"
  printf 'origin_main=%s\n' "${REMOTE_MAIN}"
  git rev-list --left-right --count HEAD...origin/main
} > "${ARTIFACT_DIR}/git_sync_state.txt"

if [ "${LOCAL_HEAD}" != "${REMOTE_MAIN}" ]; then
  echo blocked_git_not_fully_synced > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi
if ! grep -q 'p5_deepseek_v4_flash_4card_fp8_stack_upgrade_probe_v0221rc1_2026_0710' 通信模块/docs/developer-to-server.md; then
  echo blocked_handoff_task_id_changed > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi

build_target_environment() {
  set -euo pipefail

  if [ -e "${NEW_ENV}" ]; then
    if [ ! -f "${NEW_ENV}/.ak_v0221rc1_build_complete" ]; then
      echo "target environment exists without completion marker" >&2
      return 91
    fi
  else
    conda create --prefix "${NEW_ENV}" --clone "${BASE_ENV}" -y
  fi

  if [ -d "${VLLM_SRC}/.git" ]; then
    test -z "$(git -C "${VLLM_SRC}" status --porcelain)"
    test "$(git -C "${VLLM_SRC}" rev-parse HEAD)" = "${VLLM_COMMIT}"
  elif [ -e "${VLLM_SRC}" ]; then
    echo "target vllm path exists but is not the required git checkout" >&2
    return 92
  else
    git clone --depth 1 --branch v0.22.1 https://github.com/vllm-project/vllm.git "${VLLM_SRC}"
    test "$(git -C "${VLLM_SRC}" rev-parse HEAD)" = "${VLLM_COMMIT}"
  fi

  PYTHON_BIN="${NEW_ENV}/bin/python"
  "${PYTHON_BIN}" -m pip download \
    --no-deps --pre \
    --platform manylinux_2_34_aarch64 \
    --python-version 311 --implementation cp --abi cp311 \
    --only-binary=:all: \
    --dest "${WHEEL_DIR}" \
    --extra-index-url https://mirrors.huaweicloud.com/ascend/repos/pypi/variant \
    --extra-index-url https://mirrors.huaweicloud.com/ascend/repos/pypi \
    'vllm-ascend==0.22.1rc1'

  WHEEL="$(find "${WHEEL_DIR}" -maxdepth 1 -type f -name 'vllm_ascend-0.22.1rc1-cp311-cp311-manylinux_2_34_aarch64.whl' -print -quit)"
  test -n "${WHEEL}"
  printf '%s  %s\n' "${WHEEL_SHA256}" "${WHEEL}" | sha256sum --check

  "${PYTHON_BIN}" -m pip install -r "${VLLM_SRC}/requirements/common.txt"
  "${PYTHON_BIN}" -m pip install "${WHEEL}"
  "${PYTHON_BIN}" -m pip install \
    'cmake>=3.26.1' ninja 'packaging>=24.2' \
    'setuptools>=77.0.3,<81.0.0' 'setuptools-scm>=8.0' \
    'setuptools-rust>=1.9.0' wheel jinja2
  (
    cd "${VLLM_SRC}"
    VLLM_TARGET_DEVICE=empty "${PYTHON_BIN}" -m pip install -e . --no-deps --no-build-isolation
  )

  "${PYTHON_BIN}" -m pip check
  touch "${NEW_ENV}/.ak_v0221rc1_build_complete"
}

set +e
build_target_environment > "${ARTIFACT_DIR}/environment_build.log" 2>&1
ENV_BUILD_EXIT_CODE=$?
set -e
echo "${ENV_BUILD_EXIT_CODE}" > "${ARTIFACT_DIR}/environment_build_exit_code.txt"
if [ "${ENV_BUILD_EXIT_CODE}" -ne 0 ]; then
  if [ "${ENV_BUILD_EXIT_CODE}" -eq 91 ] || [ "${ENV_BUILD_EXIT_CODE}" -eq 92 ]; then
    echo blocked_existing_target_requires_review > "${ARTIFACT_DIR}/probe_status.txt"
  else
    echo blocked_environment > "${ARTIFACT_DIR}/probe_status.txt"
  fi
  tail -n 120 "${ARTIFACT_DIR}/environment_build.log" > "${ARTIFACT_DIR}/first_failure_excerpt.txt"
  exit 0
fi
```

## 5. 版本、源码能力与模型预检

继续在同一 shell 中执行：

```bash
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

PYTHON_BIN="${NEW_ENV}/bin/python"
VLLM_BIN="${NEW_ENV}/bin/vllm"

set +e
"${PYTHON_BIN}" -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest.log" 2>&1
PYTEST_EXIT_CODE=$?
set -e
echo "${PYTEST_EXIT_CODE}" > "${ARTIFACT_DIR}/pytest_exit_code.txt"
if [ "${PYTEST_EXIT_CODE}" -ne 0 ]; then
  echo blocked_inference_contracts > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi

npu-smi info > "${ARTIFACT_DIR}/npu_smi_before.txt" 2>&1 || true

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
(artifact_dir / "model_preflight.json").write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

ok = (
    version("vllm").startswith("0.22.1")
    and version("vllm-ascend") == "0.22.1rc1"
    and version("torch") == "2.10.0"
    and version("torch-npu") == "2.10.0"
    and version("transformers") == "5.5.4"
    and torch.npu.is_available()
    and torch.npu.device_count() == 4
    and "deepseek_v4_fp8" in supported
    and len(shards) == 46
    and weight_bytes == 159617149040
    and config.get("architectures") == ["DeepseekV4ForCausalLM"]
    and config.get("model_type") == "deepseek_v4"
    and quant.get("quant_method") == "fp8"
    and config.get("expert_dtype") == "fp4"
)
(artifact_dir / "preflight_status.txt").write_text("ready\n" if ok else "blocked_preflight\n", encoding="utf-8")
PY

if [ "$(tr -d '\r\n' < "${ARTIFACT_DIR}/preflight_status.txt")" != ready ]; then
  echo blocked_preflight > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi
```

开始模型前，人工确认 `npu-smi info` 中物理 NPU 4-7 全部健康、空闲、无进程。脚本只能证明进程内可见 4 卡，不能替代物理卡号核对。若不满足，写 `blocked_resource` 后退出。

## 6. 两个有序 profile

只允许以下顺序：

1. `base_no_mtp`：先验证格式门、权重加载、server ready 和一个 `4096+64` 请求。
2. 只有 `base_no_mtp` 请求成功，才运行 `mtp_on`；除此之外一律停止，不做 fallback。

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
  sleep 5
}

run_single_request() {
  local profile_dir="$1"
  "${PYTHON_BIN}" - "${MODEL_PATH}" "http://${HOST}:${PORT}" "${SERVED_MODEL_NAME}" "${profile_dir}" <<'PY'
import json, sys, time, urllib.request
from pathlib import Path
from transformers import AutoTokenizer

model_path, base_url, served_model, profile_dir = sys.argv[1:]
profile_dir = Path(profile_dir)
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
ids = []
i = 0
while len(ids) < 4096:
    i += 1
    ids.extend(tokenizer(f"DeepSeek official FP8 four-card runtime probe block {i:06d}. ", add_special_tokens=False).input_ids)
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
result = {"status": "failed", "input_tokens": 4096, "requested_output_tokens": 64, "completion_tokens": 0, "error": ""}
try:
    with urllib.request.urlopen(request, timeout=7200) as response:
        body = json.loads(response.read().decode())
        result["http_status"] = response.status
        result["prompt_tokens"] = int((body.get("usage") or {}).get("prompt_tokens") or 0)
        result["completion_tokens"] = int((body.get("usage") or {}).get("completion_tokens") or 0)
        result["status"] = "success" if response.status == 200 and result["prompt_tokens"] == 4096 and result["completion_tokens"] == 64 else "failed"
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

  set +e
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
  set -e
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
    if not root.exists():
        continue
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
    "environment_build_exit_code": (artifact_dir / "environment_build_exit_code.txt").read_text().strip(),
    "authorized_visible_devices": "4,5,6,7",
    "model_path": "/data/node0_disk1/Public/DeepSeek-V4-Flash",
    "checkpoint_format": "fp8_non_expert_plus_fp4_experts",
    "retired_w8a8_started": False,
    "explicit_quantization_argument_used": False,
    "profiles": profiles,
    "residual_process_check": "operator_confirms_from_npu_smi_final",
}
(artifact_dir / "probe_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

excerpts = []
for name in ("base_no_mtp", "mtp_on"):
    text = log_text(name)
    if text:
        excerpts.append(f"## {name} last 100 lines")
        excerpts.extend(text.splitlines()[-100:])
(artifact_dir / "first_failure_excerpt.txt").write_text("\n".join(excerpts)[:30000] + "\n", encoding="utf-8")
PY
```

## 7. 分级与停止规则

| 状态 | 条件 |
| --- | --- |
| `diagnostic_green` | `base_no_mtp` 和 `mtp_on` 均 ready，且各自一个 `4096+64` 请求成功 |
| `diagnostic_yellow_mtp` | base 请求成功，但 MTP profile 未 ready 或请求失败 |
| `diagnostic_red_quant_format` | 新栈仍拒绝 `deepseek_v4_fp8` / FP4 / quantization format |
| `diagnostic_red_weight_load` | 已通过量化平台门，但 checkpoint 权重名称、shape、scale、dtype 或 loader 失败 |
| `diagnostic_red_capacity` | HBM/权重分配 OOM 或容量不足 |
| `diagnostic_red_runtime` | architecture/parser/DSA/operator/collective/request 等其他真实首错 |
| `blocked_environment` | 独立环境无法按固定版本构建、`pip check` 或 import 失败 |
| `blocked_resource` | NPU 4-7 不健康、不空闲或不可见 |

停止规则：

- base 失败后立即停止；禁止用 MTP off/on、W8A8、其他模型格式、offload、context 降级或源码 patch 继续试错。
- 禁止 `--quantization ascend`，禁止任何显式 `--quantization`。
- 禁止 CPU/NVMe/KV offload、swap、UCM、LMCache、KV Pool、weight offload。
- 禁止 128K ladder、并发矩阵、msprof、P6 benchmark、A/B 或瓶颈归因。
- 即使四卡 green，也不自动使用 NPU 0-3，不执行未来八卡任务；等待新的明确授权。

请生成 `probe_result.json` 和不超过 30KB 的 `first_failure_excerpt.txt`。`probe_result.json` 至少包含：环境构建状态、精确版本/commit、`supported_quantization`、每个 profile 的完整命令路径、ready/request 状态、prompt/completion tokens、分级、第一失败阶段、模型路径、设备范围和最终残留进程结论。

## 8. 回传要求

只发送不超过 70KB 的状态邮件正文；不添加附件，不执行 upload-api。邮件标题建议：

```text
[P5-FP8-v0221rc1] <probe_grade> | <first_failure_or_success> | 2026-07-10
```

正文必须包含：

1. `local_head`、`origin_main`、ahead/behind，明确完整同步而非单提交。
2. 新环境构建是否成功；基础环境和旧源码是否保持未改动。
3. vLLM/vLLM-Ascend tag、commit、wheel 文件名/SHA-256、精确包版本和 `pip check` 结果。
4. `supported_quantization` 是否包含 `fp8`、`deepseek_v4_fp8`。
5. NPU 4-7 健康/空闲、启动前与最终 HBM、残留进程结论；明确 NPU 0-3 未触碰。
6. 模型 46 分片/字节数和 FP8+FP4 metadata；明确 W8A8 目录未启动、未转换。
7. 每个实际 profile 的完整命令、ready、请求 token 数、第一失败点和精简错误；明确没有 `--quantization`。
8. `probe_grade`、artifact 目录，以及下列小文件的精确路径和字节数：

```text
git_sync_state.txt
environment_build_exit_code.txt
runtime_versions.tsv
model_preflight.json
preflight_status.txt
pytest_exit_code.txt
profile_decision.txt
probe_result.json
first_failure_excerpt.txt
*/server_command.txt
*/server_ready_exit_code.txt
*/request_result.json
```

raw `environment_build.log`、raw `vllm_server.log`、raw `npu-smi`、模型、wheel、conda 环境、源码目录和完整 artifact 目录全部留在服务器。后续如需传某个小文件，仍必须先报告精确路径、字节数、敏感性与候选传输方式，由用户逐文件选择后再执行。
