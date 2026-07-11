# Developer to Server

## 当前任务：回传已批准诊断文件，验证 spawned worker allocator patch delivery

任务 ID：

```text
p5_deepseek_v4_flash_4card_fp8_allocator_patch_delivery_v0221rc1_2026_0711
```

设备授权：

```text
单卡 allocator 诊断：ASCEND_RT_VISIBLE_DEVICES=4
有条件的 base runtime 复跑：ASCEND_RT_VISIBLE_DEVICES=4,5,6,7
```

本轮目标有且只有三个：

1. 按用户已明确选择的 `upload-api`，回传上一轮 artifact 目录中 6 个精确文件，合计 `12728 bytes`。
2. 只用 NPU 4 定位官方 `torch.accelerator -> torch.npu` memory API patch 在 fresh/spawned process 中的生效状态。
3. 仅在 allocator 矩阵完整证明 patch-delivery 假设时，使用任务目录内的 session-scoped `sitecustomize.py` 复跑 NPU 4-7 `base_no_mtp`，最多发送一个 `4096+64` 请求。

## 0. 上轮结果与本轮判断边界

上轮 `p5_deepseek_v4_flash_4card_fp8_runtime_resume_v0221rc1_2026_0711` 已确认：

- Git、精确核心版本、已知非核心 `pip check` 分类、`fp8/deepseek_v4_fp8` 注册、模型 metadata 和 NPU 4-7 资源门均通过。
- `base_no_mtp` 启动后，四个 worker 在 `NPUWorker._init_device -> MemorySnapshot -> torch.accelerator.memory_stats -> torch._C._accelerator_isAllocatorInitialized` 触发相同断言：`Allocator for npu is not a DeviceAllocator`。
- 失败早于权重加载、server ready、HCCL 集合通信和请求；上轮邮件的 `architecture_operator_collective_or_request` 是过宽阶段名，本项目将首错收窄为 `worker_init_memory_snapshot_allocator`。
- 目标 vLLM `0decac0d...` 的 `MemorySnapshot` 使用 `torch.accelerator.memory_stats/memory_reserved/reset_peak_memory_stats`。目标 vLLM-Ascend `5f6faa0c...` 的 `vllm_ascend/patch/platform/patch_torch_accelerator.py` 已把这三个 API 指向 `torch.npu.*`。
- 因此“官方 patch 存在，但未在实际 spawned worker 生效”是待验证假设，不是已证实结论。

上轮结果仍为 `diagnostic_red_runtime`，不是 `diagnostic_red_quant_format`、`diagnostic_red_weight_load`、容量结论、DeepSeek operator 结论或 collective 结论。

## 1. 完整同步远程 `main`

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

要求：

1. 必须同步远程 `main` 的全部缺失提交；禁止 `cherry-pick`、detached checkout 或单文件覆盖。
2. 必须满足 `HEAD == origin/main` 且 ahead/behind=`0 0`。
3. 同步后重新打开本文档；只有任务 ID 仍精确匹配才继续。

## 2. 固定环境、对象与禁止项

```text
核心版本基线：
vLLM 0.22.1+empty / vLLM-Ascend 0.22.1rc1

本轮复用环境：
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1

vLLM editable source：
/data/node0_disk1/vllm-0.22.1
v0.22.1@0decac0d96c42b49572498019f0a0e3600f50398

vLLM-Ascend：
v0.22.1rc1@5f6faa0cb8830f667266f3b8121cd1383606f2a1

旧环境（只读保留）：
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.20.2rc1

模型：
/data/node0_disk1/Public/DeepSeek-V4-Flash

退役 inventory（禁止启动）：
/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
```

禁止项：

- 禁止 `conda create`、`pip install`、`pip uninstall`、包升降级或重建环境。
- 禁止修改 vLLM/vLLM-Ascend source、site-packages、CANN、driver、firmware、apt 或系统 Python。
- 禁止使用 NPU 0-3；禁止 kill、停止或影响 NPU 0-3 上的其他任务。
- 禁止显式 `--quantization`、checkpoint config 改写、W8A8、CPU/NVMe/KV offload、128K、并发矩阵、msprof、P6 和 A/B。
- `mtp_on 禁止`；即使 base 请求成功也不在本轮启用 MTP。
- 不得把 session-scoped `sitecustomize.py` 写成上游修复、生产验证或对其他模型的通用修复。

## 3. 先通过 upload-api 回传已批准的 6 个旧文件

用户已针对以下精确范围选择 `upload-api`：

```text
first_failure_excerpt.txt:9555
probe_result.json:1177
pip_check_classification.json:634
model_preflight.json:360
runtime_versions.tsv:246
base_no_mtp/server_command.txt:756
total_bytes:12728
```

根目录：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_4card_fp8_runtime_resume_v0221rc1_2026_0711
```

这 6 个文件是普通技术诊断，可能包含服务器绝对路径、模型名、PID 和堆栈；不应包含 token、密码、私钥、Cookie 或 `.env` 内容。上传前必须只输出扫描计数，不在终端打印可疑秘密原文。

```bash
set +e
set -uo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_4card_fp8_allocator_patch_delivery_v0221rc1_2026_0711
OLD_RUN_ID=p5_deepseek_v4_flash_4card_fp8_runtime_resume_v0221rc1_2026_0711
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
OLD_ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${OLD_RUN_ID}"
TRANSFER_DIR="${ARTIFACT_DIR}/prior_six_file_upload"
NEW_ENV=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
BASE_ENV=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.20.2rc1
VLLM_SRC=/data/node0_disk1/vllm-0.22.1
VLLM_COMMIT=0decac0d96c42b49572498019f0a0e3600f50398
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash
RETIRED_W8A8_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
PYTHON_BIN="${NEW_ENV}/bin/python"
VLLM_BIN="${NEW_ENV}/bin/vllm"
mkdir -p "${TRANSFER_DIR}"

APPROVED_FILES=(
  "first_failure_excerpt.txt:9555"
  "probe_result.json:1177"
  "pip_check_classification.json:634"
  "model_preflight.json:360"
  "runtime_versions.tsv:246"
  "base_no_mtp/server_command.txt:756"
)

TRANSFER_OK=1
TOTAL_BYTES=0
for item in "${APPROVED_FILES[@]}"; do
  rel="${item%:*}"
  expected="${item##*:}"
  path="${OLD_ARTIFACT_DIR}/${rel}"
  if [ ! -f "${path}" ]; then
    printf 'missing\t%s\n' "${rel}" >> "${TRANSFER_DIR}/validation.tsv"
    TRANSFER_OK=0
    continue
  fi
  actual="$(stat -c '%s' "${path}")"
  printf '%s\t%s\t%s\n' "${rel}" "${expected}" "${actual}" >> "${TRANSFER_DIR}/validation.tsv"
  if [ "${actual}" != "${expected}" ]; then TRANSFER_OK=0; fi
  TOTAL_BYTES=$((TOTAL_BYTES + actual))
done
printf 'total_bytes=%s\n' "${TOTAL_BYTES}" >> "${TRANSFER_DIR}/validation.tsv"
if [ "${TOTAL_BYTES}" -ne 12728 ]; then TRANSFER_OK=0; fi

"${PYTHON_BIN}" - "${OLD_ARTIFACT_DIR}" "${TRANSFER_DIR}/secret_scan.json" <<'PY'
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])
files = [
    "first_failure_excerpt.txt",
    "probe_result.json",
    "pip_check_classification.json",
    "model_preflight.json",
    "runtime_versions.tsv",
    "base_no_mtp/server_command.txt",
]
patterns = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "credential_assignment": re.compile(
        r"(?i)\b(?:AK_COMM_UPLOAD_TOKEN|AK_COMM_SMTP_PASSWORD|password|secret|access[_-]?token)\s*[:=]\s*\S+"
    ),
}
counts = {name: 0 for name in patterns}
for rel in files:
    text = (root / rel).read_text(encoding="utf-8", errors="replace")
    for name, pattern in patterns.items():
        counts[name] += len(pattern.findall(text))
result = {"files": files, "match_counts": counts, "safe_to_upload": not any(counts.values())}
out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
if not result["safe_to_upload"]:
    raise SystemExit(1)
PY
SECRET_SCAN_EXIT=$?
if [ "${SECRET_SCAN_EXIT}" -ne 0 ]; then TRANSFER_OK=0; fi

if [ "${TRANSFER_OK}" -ne 1 ]; then
  echo blocked_transfer_validation > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi

python3 通信模块/upload_file.py --show-config > "${TRANSFER_DIR}/upload_config_redacted.json" 2>&1
python3 通信模块/upload_file.py \
  --preflight \
  --confirmed-method upload-api \
  > "${TRANSFER_DIR}/preflight_receipt.json" 2>&1
if [ "$?" -ne 0 ]; then
  echo blocked_transfer_preflight > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi

for item in "${APPROVED_FILES[@]}"; do
  rel="${item%:*}"
  path="${OLD_ARTIFACT_DIR}/${rel}"
  receipt_name="$(printf '%s' "${rel}" | tr '/ ' '__')"
  python3 通信模块/upload_file.py --inspect "${path}" \
    > "${TRANSFER_DIR}/${receipt_name}.inspect.json" 2>&1
  if [ "$?" -ne 0 ]; then
    echo blocked_transfer_inspect > "${ARTIFACT_DIR}/probe_status.txt"
    exit 0
  fi
  python3 通信模块/upload_file.py \
    --upload "${path}" \
    --confirmed-method upload-api \
    > "${TRANSFER_DIR}/${receipt_name}.upload.json" 2>&1
  if [ "$?" -ne 0 ]; then
    echo blocked_transfer_upload > "${ARTIFACT_DIR}/probe_status.txt"
    exit 0
  fi
done
echo prior_six_files_uploaded > "${TRANSFER_DIR}/status.txt"
```

`upload_file.py` 只有在 curl 成功、HTTP `201`、返回 JSON 有效且远程/本地 `SHA-256` 一致时才返回成功。任一 `401/409/413/3xx/5xx`、超时、代理异常、非 JSON 或 hash 不一致都立即停止整个任务；禁止自动改名、重试、换邮件或扩大文件范围。

## 4. 核心 preflight 与资源门

上传成功后才继续。所有可失败 gate 仍在 subshell 内运行，caller 无条件写退出码。

```bash
set +e
set -uo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_4card_fp8_allocator_patch_delivery_v0221rc1_2026_0711
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
NEW_ENV=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
BASE_ENV=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.20.2rc1
VLLM_SRC=/data/node0_disk1/vllm-0.22.1
VLLM_COMMIT=0decac0d96c42b49572498019f0a0e3600f50398
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash
PYTHON_BIN="${NEW_ENV}/bin/python"
VLLM_BIN="${NEW_ENV}/bin/vllm"
mkdir -p "${ARTIFACT_DIR}"

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u

export PATH="${NEW_ENV}/bin:${PATH}"
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
  test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
  grep -q "${RUN_ID}" 通信模块/docs/developer-to-server.md

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
        "matplotlib", "msguard", "openpyxl",
        "opentelemetry-exporter-otlp-proto-grpc",
        "opentelemetry-exporter-otlp-proto-http", "pandas",
    },
    "te": {"ml-dtypes", "tornado"},
    "pyvers": {"packaging"},
    "opencv-python-headless": {"numpy"},
}

def normalize(value):
    return re.sub(r"[-_.]+", "-", value).lower()

unexpected = []
if exit_code not in (0, 1):
    unexpected.append(f"pip_check_exit_code={exit_code}")
elif exit_code == 1:
    if not lines:
        unexpected.append("pip_check_exit_1_without_conflict_lines")
    for line in lines:
        match = re.match(r"^([A-Za-z0-9_.-]+)\s", line)
        dependent = normalize(match.group(1)) if match else ""
        targets = allowed_requirements.get(dependent, set())
        normalized = normalize(line)
        if not targets or not any(target in normalized for target in targets):
            unexpected.append(line)
result = {
    "policy": "full_pip_check_is_diagnostic_known_non_core_conflicts_are_allowed",
    "exit_code": exit_code,
    "allowed_requirements": {k: sorted(v) for k, v in allowed_requirements.items()},
    "unexpected_conflicts": unexpected,
}
(artifact_dir / "pip_check_classification.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8")
if unexpected:
    raise SystemExit(1)
PY

  "${PYTHON_BIN}" -m pytest tests/inference_contracts -q \
    > "${ARTIFACT_DIR}/pytest.log" 2>&1

  ASCEND_RT_VISIBLE_DEVICES=4,5,6,7 "${PYTHON_BIN}" - "${MODEL_PATH}" "${ARTIFACT_DIR}" <<'PY'
import importlib.metadata as metadata
import json
import platform
import sys
from pathlib import Path

model = Path(sys.argv[1])
out = Path(sys.argv[2])
import torch
import torch_npu  # noqa: F401
import vllm
import vllm_ascend
from vllm.platforms import current_platform

def version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "missing"

config = json.loads((model / "config.json").read_text(encoding="utf-8"))
quant = config.get("quantization_config") or {}
shards = sorted(p for p in model.glob("model-*.safetensors") if not p.name.startswith("._"))
supported = list(current_platform.supported_quantization)
result = {
    "python": platform.python_version(),
    "torch": version("torch"),
    "torch_npu": version("torch-npu"),
    "vllm": version("vllm"),
    "vllm_ascend": version("vllm-ascend"),
    "triton_ascend": version("triton-ascend"),
    "transformers": version("transformers"),
    "npu_available": torch.npu.is_available(),
    "visible_device_count": torch.npu.device_count(),
    "supported_quantization": supported,
    "shard_count": len(shards),
    "weight_bytes": sum(p.stat().st_size for p in shards),
    "architecture": config.get("architectures"),
    "model_type": config.get("model_type"),
    "quant_method": quant.get("quant_method"),
    "expert_dtype": config.get("expert_dtype"),
}
(out / "preflight.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
expected = {
    "python": "3.11.15", "torch": "2.10.0", "torch_npu": "2.10.0",
    "vllm": "0.22.1+empty", "vllm_ascend": "0.22.1rc1",
    "triton_ascend": "3.2.1", "transformers": "5.5.4",
    "visible_device_count": 4, "shard_count": 46,
    "weight_bytes": 159617149040, "architecture": ["DeepseekV4ForCausalLM"],
    "model_type": "deepseek_v4", "quant_method": "fp8", "expert_dtype": "fp4",
}
ok = all(result.get(key) == value for key, value in expected.items())
ok = ok and result["npu_available"] and "fp8" in supported and "deepseek_v4_fp8" in supported
if not ok:
    raise SystemExit(1)
PY
)

run_preflight > "${ARTIFACT_DIR}/preflight.log" 2>&1
PREFLIGHT_EXIT_CODE=$?
echo "${PREFLIGHT_EXIT_CODE}" > "${ARTIFACT_DIR}/preflight_exit_code.txt"
if [ "${PREFLIGHT_EXIT_CODE}" -ne 0 ]; then
  echo blocked_preflight > "${ARTIFACT_DIR}/probe_status.txt"
  tail -n 120 "${ARTIFACT_DIR}/preflight.log" > "${ARTIFACT_DIR}/first_failure_excerpt.txt"
  exit 0
fi
npu-smi info > "${ARTIFACT_DIR}/npu_smi_before_allocator.txt" 2>&1 || true
```

人工确认物理 NPU 4 `Health=OK`、空闲且无进程；不满足则写 `blocked_resource` 并停止。

## 5. NPU 4 allocator / patch-delivery 矩阵

先只读定位已安装的 `patch_torch_accelerator.py`，记录路径、SHA-256 和三行映射；不修改该文件。然后在 `spawn` 子进程中分别运行：

1. 未显式导入官方 patch。
2. 显式导入官方 `vllm_ascend.patch.platform.patch_torch_accelerator`。
3. 通过 fresh interpreter 启动时加载、仅位于本任务 artifact 目录的 `sitecustomize.py`。

```bash
set +e
set -uo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RUN_ID=p5_deepseek_v4_flash_4card_fp8_allocator_patch_delivery_v0221rc1_2026_0711
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
NEW_ENV=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
PYTHON_BIN="${NEW_ENV}/bin/python"
ALLOC_DIR="${ARTIFACT_DIR}/allocator_probe"
PATCH_DIR="${ALLOC_DIR}/worker_startup_patch"
mkdir -p "${PATCH_DIR}"

ASCEND_RT_VISIBLE_DEVICES=4 "${PYTHON_BIN}" - "${ALLOC_DIR}" <<'PY'
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
spec = importlib.util.find_spec("vllm_ascend.patch.platform.patch_torch_accelerator")
if spec is None or spec.origin is None:
    raise SystemExit("official patch module not found")
path = Path(spec.origin)
text = path.read_text(encoding="utf-8")
required = [
    "torch.accelerator.memory_stats = torch.npu.memory_stats",
    "torch.accelerator.memory_reserved = torch.npu.memory_reserved",
    "torch.accelerator.reset_peak_memory_stats = torch.npu.reset_peak_memory_stats",
]
result = {
    "path": str(path),
    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    "required_redirects_present": {line: line in text for line in required},
}
(out / "installed_official_patch.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8")
if not all(result["required_redirects_present"].values()):
    raise SystemExit(1)
PY
if [ "$?" -ne 0 ]; then
  echo diagnostic_red_hypothesis_mismatch > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi

"${PYTHON_BIN}" - "${ALLOC_DIR}/spawn_probe.py" <<'PY'
import sys
from pathlib import Path

script = '''import json
import multiprocessing as mp
import sys
import traceback

def call(fn):
    try:
        value = fn()
        if hasattr(value, "get"):
            value = {"allocated_peak": value.get("allocated_bytes.all.peak", 0)}
        return {"ok": True, "value": value}
    except Exception as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=8),
        }

def collect(mode):
    import torch
    import torch_npu  # noqa: F401
    torch.npu.set_device("npu:0")
    if mode == "official_patch":
        import vllm_ascend.patch.platform.patch_torch_accelerator  # noqa: F401
    from vllm.utils.mem_utils import MemorySnapshot
    return {
        "mode": mode,
        "memory_stats_identity": torch.accelerator.memory_stats is torch.npu.memory_stats,
        "memory_reserved_identity": torch.accelerator.memory_reserved is torch.npu.memory_reserved,
        "native_memory_stats": call(lambda: torch.npu.memory_stats("npu:0")),
        "generic_memory_stats": call(lambda: torch.accelerator.memory_stats("npu:0")),
        "native_memory_reserved": call(lambda: torch.npu.memory_reserved("npu:0")),
        "generic_memory_reserved": call(lambda: torch.accelerator.memory_reserved("npu:0")),
        "memory_snapshot": call(lambda: repr(MemorySnapshot(device="npu:0"))),
    }

def child(mode, queue):
    queue.put(collect(mode))

if __name__ == "__main__":
    mode = sys.argv[1]
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    proc = ctx.Process(target=child, args=(mode, queue))
    proc.start()
    proc.join(120)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        raise SystemExit("spawn child timeout")
    if proc.exitcode != 0:
        raise SystemExit(f"spawn child exit={proc.exitcode}")
    print(json.dumps(queue.get(timeout=10), indent=2))
'''
Path(sys.argv[1]).write_text(script, encoding="utf-8")
PY

ASCEND_RT_VISIBLE_DEVICES=4 "${PYTHON_BIN}" "${ALLOC_DIR}/spawn_probe.py" unpatched \
  > "${ALLOC_DIR}/spawn_unpatched.json" 2> "${ALLOC_DIR}/spawn_unpatched.stderr"
UNPATCHED_EXIT=$?
ASCEND_RT_VISIBLE_DEVICES=4 "${PYTHON_BIN}" "${ALLOC_DIR}/spawn_probe.py" official_patch \
  > "${ALLOC_DIR}/spawn_official_patch.json" 2> "${ALLOC_DIR}/spawn_official_patch.stderr"
OFFICIAL_EXIT=$?

"${PYTHON_BIN}" - "${PATCH_DIR}/sitecustomize.py" <<'PY'
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    "import torch\n"
    "import torch_npu  # noqa: F401\n"
    "torch.accelerator.memory_stats = torch.npu.memory_stats\n"
    "torch.accelerator.memory_reserved = torch.npu.memory_reserved\n"
    "torch.accelerator.reset_peak_memory_stats = torch.npu.reset_peak_memory_stats\n",
    encoding="utf-8",
)
PY

PYTHONPATH="${PATCH_DIR}${PYTHONPATH:+:${PYTHONPATH}}" \
  ASCEND_RT_VISIBLE_DEVICES=4 \
  "${PYTHON_BIN}" "${ALLOC_DIR}/spawn_probe.py" sitecustomize \
  > "${ALLOC_DIR}/spawn_sitecustomize.json" 2> "${ALLOC_DIR}/spawn_sitecustomize.stderr"
SITECUSTOMIZE_EXIT=$?

printf 'unpatched_exit=%s\nofficial_exit=%s\nsitecustomize_exit=%s\n' \
  "${UNPATCHED_EXIT}" "${OFFICIAL_EXIT}" "${SITECUSTOMIZE_EXIT}" \
  > "${ALLOC_DIR}/process_exit_codes.txt"

"${PYTHON_BIN}" - "${ALLOC_DIR}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
results = {}
for name in ("spawn_unpatched", "spawn_official_patch", "spawn_sitecustomize"):
    path = root / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"missing {path}")
    results[name] = json.loads(path.read_text(encoding="utf-8"))

unpatched = results["spawn_unpatched"]
official = results["spawn_official_patch"]
site = results["spawn_sitecustomize"]
allocator_text = " ".join([
    unpatched["generic_memory_stats"].get("error", ""),
    unpatched["memory_snapshot"].get("error", ""),
])
native_ok = unpatched["native_memory_stats"]["ok"] and unpatched["native_memory_reserved"]["ok"]
generic_reproduced = (
    not unpatched["generic_memory_stats"]["ok"]
    and "Allocator for npu is not a DeviceAllocator" in allocator_text
)
official_ok = (
    official["memory_stats_identity"]
    and official["memory_reserved_identity"]
    and official["generic_memory_stats"]["ok"]
    and official["generic_memory_reserved"]["ok"]
    and official["memory_snapshot"]["ok"]
)
site_ok = (
    site["memory_stats_identity"]
    and site["memory_reserved_identity"]
    and site["generic_memory_stats"]["ok"]
    and site["generic_memory_reserved"]["ok"]
    and site["memory_snapshot"]["ok"]
)
summary = {
    "native_ok": native_ok,
    "unpatched_generic_allocator_failure_reproduced": generic_reproduced,
    "explicit_official_patch_ok": official_ok,
    "session_sitecustomize_ok": site_ok,
    "hypothesis_supported": native_ok and generic_reproduced and official_ok and site_ok,
}
(root / "allocator_matrix_summary.json").write_text(
    json.dumps(summary, indent=2) + "\n", encoding="utf-8")
if not summary["hypothesis_supported"]:
    raise SystemExit(1)
PY
ALLOCATOR_GATE_EXIT=$?
echo "${ALLOCATOR_GATE_EXIT}" > "${ALLOC_DIR}/allocator_gate_exit_code.txt"
if [ "${ALLOCATOR_GATE_EXIT}" -ne 0 ]; then
  echo diagnostic_red_hypothesis_mismatch > "${ARTIFACT_DIR}/probe_status.txt"
  exit 0
fi
echo allocator_patch_delivery_hypothesis_supported > "${ARTIFACT_DIR}/allocator_status.txt"
```

只有 `allocator_matrix_summary.json` 中四个条件字段都为 `true`才可继续。任一不成立都写 `diagnostic_red_hypothesis_mismatch`，禁止启动模型。

## 6. 有条件的 NPU 4-7 `base_no_mtp` 复跑

先人工确认物理 NPU 4-7 均 `Health=OK`、空闲且无进程。不满足写 `blocked_resource` 并停止。

```bash
set +e
set -uo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_4card_fp8_allocator_patch_delivery_v0221rc1_2026_0711
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
NEW_ENV=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash
PYTHON_BIN="${NEW_ENV}/bin/python"
VLLM_BIN="${NEW_ENV}/bin/vllm"
PATCH_DIR="${ARTIFACT_DIR}/allocator_probe/worker_startup_patch"

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
export PATH="${NEW_ENV}/bin:${PATH}"
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

export ASCEND_RT_VISIBLE_DEVICES=4,5,6,7
export PYTHONPATH="${PATCH_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
HOST=127.0.0.1
PORT=7000
SERVED_MODEL_NAME=dsv4-official-fp8-four-card
PROFILE_DIR="${ARTIFACT_DIR}/base_no_mtp"
STARTUP_TIMEOUT_SEC=3600
mkdir -p "${PROFILE_DIR}"
npu-smi info > "${PROFILE_DIR}/npu_smi_before.txt" 2>&1 || true

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

stop_server() {
  local pid="$1"
  kill -- "-${pid}" >/dev/null 2>&1 || kill "${pid}" >/dev/null 2>&1 || true
  wait "${pid}" >/dev/null 2>&1 || true
  sleep 5
}

CMD=(
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

printf '%q ' "${CMD[@]}" > "${PROFILE_DIR}/server_command.txt"
printf '\n' >> "${PROFILE_DIR}/server_command.txt"
setsid "${CMD[@]}" > "${PROFILE_DIR}/vllm_server.log" 2>&1 &
SERVER_PID=$!
echo "${SERVER_PID}" > "${PROFILE_DIR}/server_pid.txt"

wait_health_or_exit "${SERVER_PID}"
READY_EXIT=$?
echo "${READY_EXIT}" > "${PROFILE_DIR}/server_ready_exit_code.txt"

if [ "${READY_EXIT}" -eq 0 ]; then
  "${PYTHON_BIN}" - "${MODEL_PATH}" "http://${HOST}:${PORT}" "${SERVED_MODEL_NAME}" "${PROFILE_DIR}" <<'PY'
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
index = 0
while len(ids) < 4096:
    index += 1
    ids.extend(tokenizer(
        f"DeepSeek allocator patch delivery probe block {index:06d}. ",
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
result = {"status": "failed", "input_tokens": 4096, "requested_output_tokens": 64}
try:
    with urllib.request.urlopen(request, timeout=7200) as response:
        body = json.loads(response.read().decode())
        usage = body.get("usage") or {}
        result.update({
            "http_status": response.status,
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
        })
        if response.status == 200 and result["prompt_tokens"] == 4096 and result["completion_tokens"] == 64:
            result["status"] = "success"
except Exception as exc:
    result["error"] = f"{type(exc).__name__}: {exc}"
result["client_wall_s"] = round(time.perf_counter() - started, 6)
(profile_dir / "request_result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  REQUEST_EXIT=$?
  echo "${REQUEST_EXIT}" > "${PROFILE_DIR}/request_client_exit_code.txt"
else
  REQUEST_EXIT=99
fi

npu-smi info > "${PROFILE_DIR}/npu_smi_after.txt" 2>&1 || true
stop_server "${SERVER_PID}"
unset PYTHONPATH
sleep 5
npu-smi info > "${ARTIFACT_DIR}/npu_smi_final.txt" 2>&1 || true
tail -n 160 "${PROFILE_DIR}/vllm_server.log" > "${ARTIFACT_DIR}/first_failure_excerpt.txt"

"${PYTHON_BIN}" - "${ARTIFACT_DIR}" "${READY_EXIT}" "${REQUEST_EXIT}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
ready = int(sys.argv[2])
request_exit = int(sys.argv[3])
request_path = root / "base_no_mtp" / "request_result.json"
request = json.loads(request_path.read_text(encoding="utf-8")) if request_path.is_file() else None
log = (root / "base_no_mtp" / "vllm_server.log").read_text(encoding="utf-8", errors="replace")
if ready == 0 and request_exit == 0 and request and request.get("status") == "success":
    grade = "diagnostic_green_base_runtime"
elif "Allocator for npu is not a DeviceAllocator" in log:
    grade = "diagnostic_red_allocator_patch_delivery"
elif "deepseek_v4_fp8" in log and "not supported" in log:
    grade = "diagnostic_red_quant_format"
elif "out of memory" in log.lower() or "OOM" in log:
    grade = "diagnostic_red_capacity"
else:
    grade = "diagnostic_yellow_allocator_bypass"
result = {
    "probe_grade": grade,
    "allocator_patch_delivery_hypothesis_supported": True,
    "session_overlay_used": True,
    "server_ready_exit_code": ready,
    "request_client_exit_code": request_exit,
    "request_result": request,
    "mtp_on_run": False,
}
(root / "probe_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
(root / "probe_status.txt").write_text(grade + "\n", encoding="utf-8")
PY
```

无论成败，都必须确认 NPU 4-7 没有本轮残留进程；不得 kill NPU 0-3 进程。`base_failed_stop_no_fallback`：任何 base 启动/请求失败都立即停止，不运行 MTP 或其他 fallback。

## 7. 结果分级与回传

- `blocked_transfer`：已批准 6 文件的预检/上传任一失败。
- `blocked_preflight` / `blocked_resource`：核心环境/资源门未过。
- `diagnostic_red_hypothesis_mismatch`：allocator 矩阵不支持当前 patch-delivery 假设，未启动模型。
- `diagnostic_red_allocator_patch_delivery`：显式官方映射或 session overlay 仍无法修复 `MemorySnapshot`。
- `diagnostic_yellow_allocator_bypass`：overlay 已越过 allocator 门，但 base 在更后的首错停止。
- `diagnostic_green_base_runtime`：overlay 条件下 server ready 且一个 `4096+64` 请求成功。这仍不授权 MTP、八卡、128K 或 P6。

发送一封不超过 70KB 的状态邮件，主题使用：

```text
[P5-FP8-v0221rc1-allocator] <probe_grade> | <first_failure_or_base_success> | 2026-07-11
```

正文必须包含 task/Git、6 文件 upload receipts、官方 patch 路径与 SHA-256、三组 allocator 矩阵、是否启动 base、ready/request/新首错、NPU 4-7 健康与残留，以及新产物的精确服务器路径、逐文件 bytes、敏感性、`email` / `upload-api` 候选和建议方式。不得显示 token 或 `.env`。

本次 `upload-api` 授权只覆盖第 3 节的 6 个旧文件。新产生的 allocator/runtime 文件不得自动上传；先报告精确清单、大小和敏感性，等待新的用户选择。raw logs、完整环境、模型和大 artifact 留在服务器。
