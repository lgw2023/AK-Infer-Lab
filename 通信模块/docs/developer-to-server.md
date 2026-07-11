# Developer to Server

## 当前任务：验证安装内容与目标 tag 一致，再验证完整 Ascend 插件激活并有条件复跑四卡 base

任务 ID：

```text
p5_deepseek_v4_flash_4card_fp8_plugin_activation_probe_v0221rc1_2026_0711
```

设备授权：

```text
单卡 fresh-process 插件矩阵：ASCEND_RT_VISIBLE_DEVICES=4
有条件的 base runtime 复跑：ASCEND_RT_VISIBLE_DEVICES=4,5,6,7
NPU 0-3 禁止使用或影响
```

本轮目标只有三项，必须按顺序执行：

1. 先核对服务器实际 import 的 vLLM / vLLM-Ascend 根目录、版本、entry points，以及 6 个关键 Python 文件的 SHA-256；必须与指定 tag/commit 完全一致。
2. provenance gate 通过后，才在两个独立的新 Python 进程中比较 `VLLM_PLUGINS=ascend` 与目标 tag 的完整 Ascend 插件白名单，验证 platform、DeepSeekV4 model registry、`torch.accelerator -> torch.npu` memory redirect 和 `MemorySnapshot`。
3. 只有完整插件白名单同时选中 `AscendDeepseekV4ForCausalLM` 且修复 `MemorySnapshot` 时，才在 NPU 4-7 无 `sitecustomize` / `PYTHONPATH` overlay 复跑一次 TP4/EP `base_no_mtp` 和一个 `4096+64` 请求。

## 0. 上轮证据与本轮假设

上一轮 `p5_deepseek_v4_flash_4card_fp8_allocator_patch_delivery_v0221rc1_2026_0711` 已确认：

- allocator 矩阵支持 patch-delivery 假设；session-scoped `sitecustomize.py` 使 `MemorySnapshot` 成功。
- 四卡复跑时旧 allocator 错误计数为 0，但四个 worker 随后进入 `vllm/models/deepseek_v4/nvidia/model.py`，在 `attention.py:198` 报 `DeepseekV4 attention requires a CUDA device`。
- 失败仍早于权重加载、server ready 和请求；不是量化格式、容量、collective 或请求结论。
- 目标 vLLM `0decac0d...` 把 `VLLM_PLUGINS` 作为 platform/general 等所有插件组共享的名称白名单。
- 目标 vLLM-Ascend `5f6faa0c...` 提供 platform 插件 `ascend`，以及 general 插件 `ascend_kv_connector`、`ascend_model_loader`、`ascend_service_profiling`、`ascend_model`。其中 `ascend_model` 把 `DeepseekV4ForCausalLM` 注册到 `vllm_ascend.models.deepseek_v4:AscendDeepseekV4ForCausalLM`，前三个 general 插件会触发 global patch。
- 上轮命令只设置 `VLLM_PLUGINS=ascend`。当前高置信假设是：该限制值只放行 platform 插件，同时过滤了 Ascend model registration 和 global patch general plugins。

服务器已精确报告 editable vLLM `0decac0d...` clean，但 vLLM-Ascend 是预编译 wheel，版本号本身不能完全排除同版本内容漂移或本地修改。这个差异必须先由 installed-content provenance gate 关闭；插件假设随后再由 fresh-process 矩阵验证，不得直接写成既定根因。

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

必须完整 fast-forward 同步全部缺失提交，满足 `HEAD == origin/main`、ahead/behind=`0 0`，再重新打开本文档。禁止 `cherry-pick`、detached checkout 或单文件覆盖。

## 2. 固定环境、对象与禁止项

```text
复用环境：
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1

vLLM source：
/data/node0_disk1/vllm-0.22.1
v0.22.1@0decac0d96c42b49572498019f0a0e3600f50398

vLLM-Ascend：
v0.22.1rc1@5f6faa0cb8830f667266f3b8121cd1383606f2a1

模型：
/data/node0_disk1/Public/DeepSeek-V4-Flash

退役 inventory（禁止启动）：
/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
```

禁止项：

- 禁止 `conda create`、`pip install`、`pip uninstall`、包升降级或重建环境。
- 禁止修改 vLLM/vLLM-Ascend source、site-packages、CANN、driver、firmware、apt 或系统 Python。
- 禁止沿用、复制或新建上轮 `sitecustomize.py`；禁止通过 `PYTHONPATH` 注入 overlay。
- 禁止使用 NPU 0-3；禁止 kill、停止或影响 NPU 0-3 上其他任务。
- 禁止显式 `--quantization`、config 改写、W8A8、CPU/NVMe/KV offload、MTP、八卡、128K、并发矩阵、msprof、P6 和 A/B。
- 本轮唯一允许的行为变化是进程环境中的 `VLLM_PLUGINS` 白名单。

## 3. 核心预检、installed-content provenance 与 artifact 初始化

```bash
set +e
set -uo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_4card_fp8_plugin_activation_probe_v0221rc1_2026_0711
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
ENV_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
PYTHON_BIN="${ENV_DIR}/bin/python"
VLLM_BIN="${ENV_DIR}/bin/vllm"
VLLM_SRC=/data/node0_disk1/vllm-0.22.1
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash
RETIRED_W8A8_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
PLUGIN_DIR="${ARTIFACT_DIR}/plugin_probe"
OFFICIAL_ASCEND_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model

mkdir -p "${PLUGIN_DIR}" "${ARTIFACT_DIR}/base_no_mtp"
printf '%s\n' "$(git rev-parse HEAD)" > "${ARTIFACT_DIR}/git_head.txt"
npu-smi info > "${ARTIFACT_DIR}/npu_smi_before.txt" 2>&1 || true

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
export PATH="${ENV_DIR}/bin:${PATH}"

PRECHECK_EXIT=0
[ -x "${PYTHON_BIN}" ] || PRECHECK_EXIT=10
[ -x "${VLLM_BIN}" ] || PRECHECK_EXIT=11
[ -d "${MODEL_PATH}" ] || PRECHECK_EXIT=12
[ "$(git -C "${VLLM_SRC}" rev-parse HEAD 2>/dev/null)" = "0decac0d96c42b49572498019f0a0e3600f50398" ] || PRECHECK_EXIT=13
[ -z "$(git -C "${VLLM_SRC}" status --short 2>/dev/null)" ] || PRECHECK_EXIT=14

env -u PYTHONPATH ASCEND_RT_VISIBLE_DEVICES=4,5,6,7 PYTHONNOUSERSITE=1 \
  "${PYTHON_BIN}" - "${ARTIFACT_DIR}/preflight.json" <<'PY'
import hashlib
import json
import sys
from importlib.metadata import entry_points, version
from pathlib import Path

import torch
import torch_npu
import vllm
import vllm_ascend

vllm_root = Path(vllm.__file__).resolve().parent
ascend_root = Path(vllm_ascend.__file__).resolve().parent
installed_paths = {
    "vllm/plugins/__init__.py": vllm_root / "plugins" / "__init__.py",
    "vllm/envs.py": vllm_root / "envs.py",
    "vllm_ascend/__init__.py": ascend_root / "__init__.py",
    "vllm_ascend/models/__init__.py": ascend_root / "models" / "__init__.py",
    "vllm_ascend/models/deepseek_v4.py": ascend_root / "models" / "deepseek_v4.py",
    "vllm_ascend/patch/platform/patch_torch_accelerator.py": (
        ascend_root / "patch" / "platform" / "patch_torch_accelerator.py"
    ),
}

def file_record(path):
    payload = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }

result = {
    "python": sys.version.split()[0],
    "torch": torch.__version__,
    "torch_npu": version("torch-npu"),
    "vllm": vllm.__version__,
    "vllm_ascend": version("vllm-ascend"),
    "npu_available": bool(torch.npu.is_available()),
    "visible_device_count": int(torch.npu.device_count()),
    "import_roots": {
        "vllm": str(vllm_root),
        "vllm_ascend": str(ascend_root),
    },
    "installed_files": {
        name: file_record(path) for name, path in installed_paths.items()
    },
    "platform_entry_points": {
        ep.name: ep.value for ep in entry_points(group="vllm.platform_plugins")
    },
    "general_entry_points": {
        ep.name: ep.value for ep in entry_points(group="vllm.general_plugins")
    },
}
Path(sys.argv[1]).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
PY_PREFLIGHT_EXIT=$?
if [ "${PY_PREFLIGHT_EXIT}" -ne 0 ] && [ "${PRECHECK_EXIT}" -eq 0 ]; then PRECHECK_EXIT=15; fi

"${PYTHON_BIN}" - "${ARTIFACT_DIR}/preflight.json" <<'PY'
import json
import sys
from pathlib import Path

d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected_general = {
    "ascend_kv_connector": "vllm_ascend:register_connector",
    "ascend_model_loader": "vllm_ascend:register_model_loader",
    "ascend_service_profiling": "vllm_ascend:register_service_profiling",
    "ascend_model": "vllm_ascend:register_model",
}
ok = (
    d["torch"].startswith("2.10.0")
    and d["torch_npu"] == "2.10.0"
    and d["vllm"].startswith("0.22.1")
    and d["vllm_ascend"] == "0.22.1rc1"
    and d["npu_available"] is True
    and d["visible_device_count"] == 4
    and d["platform_entry_points"].get("ascend") == "vllm_ascend:register"
    and all(d["general_entry_points"].get(k) == v for k, v in expected_general.items())
)
sys.exit(0 if ok else 3)
PY
ENTRYPOINT_GATE_EXIT=$?
if [ "${ENTRYPOINT_GATE_EXIT}" -ne 0 ] && [ "${PRECHECK_EXIT}" -eq 0 ]; then PRECHECK_EXIT=16; fi

"${PYTHON_BIN}" - "${ARTIFACT_DIR}/preflight.json" "${ARTIFACT_DIR}/installed_content_provenance.json" <<'PY'
import json
import sys
from pathlib import Path

preflight_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
d = json.loads(preflight_path.read_text(encoding="utf-8"))
expected_roots = {
    "vllm": "/data/node0_disk1/vllm-0.22.1/vllm",
    "vllm_ascend": "/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/lib/python3.11/site-packages/vllm_ascend",
}
expected_sha256 = {
    "vllm/plugins/__init__.py": "4be66190ceaee9d0465f62ade801a8e94a907d7ab9fdb0a67fa14ce87448ae9f",
    "vllm/envs.py": "620a7a75d056f9d405d8030886c97d843209e6996d1c3fe4cbadd2f9efd43e7e",
    "vllm_ascend/__init__.py": "1ee8497d375fb292918f729324d5207d653fffcf70572681b33b3969f54b9ae5",
    "vllm_ascend/models/__init__.py": "d823f38dcb6a5b06b81f926b908cf81fab849d538745b3d4bbc4f81892f80e9d",
    "vllm_ascend/models/deepseek_v4.py": "9398e49d7206ba5a62629409405be057318e0657e40a25cf15c43304f78d01a4",
    "vllm_ascend/patch/platform/patch_torch_accelerator.py": "76ca48d51c8af6552828076797ad20b7eed044a8e53be918bd12719152fdc026",
}
root_checks = {
    name: d["import_roots"].get(name) == expected
    for name, expected in expected_roots.items()
}
file_checks = {
    name: d["installed_files"].get(name, {}).get("sha256") == expected
    for name, expected in expected_sha256.items()
}
summary = {
    "target_commits": {
        "vllm": "0decac0d96c42b49572498019f0a0e3600f50398",
        "vllm_ascend": "5f6faa0cb8830f667266f3b8121cd1383606f2a1",
    },
    "expected_import_roots": expected_roots,
    "observed_import_roots": d["import_roots"],
    "root_checks": root_checks,
    "expected_sha256": expected_sha256,
    "observed_files": d["installed_files"],
    "file_checks": file_checks,
    "all_match": all(root_checks.values()) and all(file_checks.values()),
}
output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
sys.exit(0 if summary["all_match"] else 3)
PY
PROVENANCE_GATE_EXIT=$?
if [ "${PROVENANCE_GATE_EXIT}" -ne 0 ] && [ "${PRECHECK_EXIT}" -eq 0 ]; then PRECHECK_EXIT=17; fi

"${PYTHON_BIN}" -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest.log" 2>&1
PYTEST_EXIT=$?
if [ "${PYTEST_EXIT}" -ne 0 ] && [ "${PRECHECK_EXIT}" -eq 0 ]; then PRECHECK_EXIT=18; fi

printf '%s\n' "${PRECHECK_EXIT}" > "${ARTIFACT_DIR}/precheck_exit_code.txt"
if [ "${PRECHECK_EXIT}" -ne 0 ]; then
  if [ "${PRECHECK_EXIT}" -eq 17 ]; then
    printf '%s\n' blocked_provenance > "${ARTIFACT_DIR}/probe_status.txt"
  else
    printf '%s\n' blocked_preflight > "${ARTIFACT_DIR}/probe_status.txt"
  fi
  exit "${PRECHECK_EXIT}"
fi
```

只有 `installed_content_provenance.json` 的两个 root checks、六个 file checks 和 `all_match` 全部为 `true` 才可进入插件矩阵。任何 mismatch 都保持文件不变，写 `blocked_provenance`，报告 expected/observed path 与 SHA-256 后停止；不得自动重装、覆盖或修补。provenance 通过后再人工核对 `npu_smi_before.txt`：NPU 4-7 必须健康、空闲且无其他用户进程；否则写 `blocked_resource` 并停止。NPU 0-3 只观察，不干预。

## 4. NPU 4 fresh-process 插件矩阵

结果 JSON 必须由子进程直接写入指定文件；stdout/stderr 只进入 `.log`，禁止再用混合 stdout 作为 JSON transport。

```bash
set +e
set -uo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_4card_fp8_plugin_activation_probe_v0221rc1_2026_0711
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
ENV_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
PYTHON_BIN="${ENV_DIR}/bin/python"
PLUGIN_DIR="${ARTIFACT_DIR}/plugin_probe"
OFFICIAL_ASCEND_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
mkdir -p "${PLUGIN_DIR}"

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
export PATH="${ENV_DIR}/bin:${PATH}"

cat > "${PLUGIN_DIR}/fresh_plugin_probe.py" <<'PY'
import json
import os
import sys
import traceback
from importlib.metadata import entry_points
from pathlib import Path

output = Path(sys.argv[1])
result = {
    "vllm_plugins": os.environ.get("VLLM_PLUGINS"),
    "platform_entry_points": {
        ep.name: ep.value for ep in entry_points(group="vllm.platform_plugins")
    },
    "general_entry_points": {
        ep.name: ep.value for ep in entry_points(group="vllm.general_plugins")
    },
}
try:
    import torch
    import torch_npu
    from vllm import ModelRegistry
    from vllm.plugins import load_general_plugins

    load_general_plugins()
    from vllm.platforms import current_platform

    result["platform_class"] = type(current_platform).__module__ + "." + type(current_platform).__name__
    result["platform_device_type"] = str(current_platform.device_type)
    registered = ModelRegistry.models["DeepseekV4ForCausalLM"]
    result["registry_module"] = getattr(registered, "module_name", None)
    result["registry_class"] = getattr(registered, "class_name", None)

    torch.npu.set_device(0)
    torch.npu.synchronize()
    result["memory_stats_identity"] = torch.accelerator.memory_stats is torch.npu.memory_stats
    result["memory_reserved_identity"] = torch.accelerator.memory_reserved is torch.npu.memory_reserved
    result["reset_peak_identity"] = (
        torch.accelerator.reset_peak_memory_stats is torch.npu.reset_peak_memory_stats
    )
    try:
        from vllm.utils.mem_utils import MemorySnapshot
        snapshot = MemorySnapshot()
        result["memory_snapshot_ok"] = True
        result["memory_snapshot_repr"] = repr(snapshot)
    except Exception as exc:
        result["memory_snapshot_ok"] = False
        result["memory_snapshot_error"] = f"{type(exc).__name__}: {exc}"
except Exception as exc:
    result["probe_error"] = f"{type(exc).__name__}: {exc}"
    result["traceback_tail"] = traceback.format_exc().splitlines()[-20:]

output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

run_mode() {
  local name="$1"
  local plugins="$2"
  env -u PYTHONPATH ASCEND_RT_VISIBLE_DEVICES=4 PYTHONNOUSERSITE=1 \
    VLLM_PLUGINS="${plugins}" \
    "${PYTHON_BIN}" "${PLUGIN_DIR}/fresh_plugin_probe.py" "${PLUGIN_DIR}/${name}.json" \
    > "${PLUGIN_DIR}/${name}.log" 2>&1
  printf '%s\n' "$?" > "${PLUGIN_DIR}/${name}.exit_code.txt"
}

run_mode restrictive_current ascend
run_mode explicit_official_ascend_plugins "${OFFICIAL_ASCEND_PLUGINS}"

"${PYTHON_BIN}" - "${PLUGIN_DIR}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
current = json.loads((root / "restrictive_current.json").read_text(encoding="utf-8"))
official = json.loads((root / "explicit_official_ascend_plugins.json").read_text(encoding="utf-8"))
checks = {
    "restrictive_platform_is_ascend": current.get("platform_device_type") == "npu",
    "restrictive_registry_is_upstream": current.get("registry_module") == "vllm.models.deepseek_v4",
    "restrictive_memory_snapshot_reproduces_allocator_failure": (
        current.get("memory_snapshot_ok") is False
        and "Allocator for npu is not a DeviceAllocator" in current.get("memory_snapshot_error", "")
    ),
    "official_platform_is_ascend": official.get("platform_device_type") == "npu",
    "official_registry_is_ascend": (
        official.get("registry_module") == "vllm_ascend.models.deepseek_v4"
        and official.get("registry_class") == "AscendDeepseekV4ForCausalLM"
    ),
    "official_memory_redirects_active": all(
        official.get(key) is True
        for key in ("memory_stats_identity", "memory_reserved_identity", "reset_peak_identity")
    ),
    "official_memory_snapshot_ok": official.get("memory_snapshot_ok") is True,
}
summary = {
    "checks": checks,
    "hypothesis_supported": all(checks.values()),
    "approved_runtime_vllm_plugins": (
        "ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model"
    ),
    "sitecustomize_used": False,
    "pythonpath_overlay_used": False,
}
(root / "plugin_matrix_summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
sys.exit(0 if summary["hypothesis_supported"] else 3)
PY
PLUGIN_GATE_EXIT=$?
printf '%s\n' "${PLUGIN_GATE_EXIT}" > "${PLUGIN_DIR}/plugin_gate_exit_code.txt"

if [ "${PLUGIN_GATE_EXIT}" -ne 0 ]; then
  printf '%s\n' diagnostic_red_plugin_filter_hypothesis_mismatch > "${ARTIFACT_DIR}/probe_status.txt"
  exit "${PLUGIN_GATE_EXIT}"
fi
printf '%s\n' plugin_activation_gate_passed > "${ARTIFACT_DIR}/plugin_status.txt"
```

只有 `plugin_matrix_summary.json` 中全部 7 个 checks 与 `hypothesis_supported` 都为 `true` 才可继续。不得只因 `platform_device_type=npu` 就启动模型。

## 5. 条件式 NPU 4-7 `base_no_mtp`

本节必须使用完整 Ascend 插件白名单，并明确 `unset PYTHONPATH`；不允许使用上轮 overlay。

```bash
set +e
set -uo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=p5_deepseek_v4_flash_4card_fp8_plugin_activation_probe_v0221rc1_2026_0711
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
ENV_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash
PYTHON_BIN="${ENV_DIR}/bin/python"
VLLM_BIN="${ENV_DIR}/bin/vllm"
PROFILE_DIR="${ARTIFACT_DIR}/base_no_mtp"
OFFICIAL_ASCEND_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
export PATH="${ENV_DIR}/bin:${PATH}"
export VLLM_PLUGINS="${OFFICIAL_ASCEND_PLUGINS}"
export VLLM_USE_V1=1
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export OMP_PROC_BIND=false
export OMP_NUM_THREADS=8
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export LD_PRELOAD="/usr/lib/aarch64-linux-gnu/libjemalloc.so.2${LD_PRELOAD:+:${LD_PRELOAD}}"
export HCCL_BUFFSIZE=1024
export TASK_QUEUE_ENABLE=1
export HCCL_OP_EXPANSION_MODE=AIV
export PYTHONNOUSERSITE=1
export ASCEND_RT_VISIBLE_DEVICES=4,5,6,7
unset PYTHONPATH

HOST=127.0.0.1
PORT=7000
SERVED_MODEL_NAME=dsv4-official-fp8-four-card
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
printf '%s\n' "${SERVER_PID}" > "${PROFILE_DIR}/server_pid.txt"

wait_health_or_exit "${SERVER_PID}"
READY_EXIT=$?
printf '%s\n' "${READY_EXIT}" > "${PROFILE_DIR}/server_ready_exit_code.txt"

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
        f"DeepSeek Ascend plugin activation probe block {index:06d}. ",
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
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
PY
  REQUEST_EXIT=$?
  printf '%s\n' "${REQUEST_EXIT}" > "${PROFILE_DIR}/request_client_exit_code.txt"
else
  REQUEST_EXIT=99
fi

npu-smi info > "${PROFILE_DIR}/npu_smi_after.txt" 2>&1 || true
stop_server "${SERVER_PID}"
sleep 5
npu-smi info > "${ARTIFACT_DIR}/npu_smi_final.txt" 2>&1 || true
tail -n 200 "${PROFILE_DIR}/vllm_server.log" > "${ARTIFACT_DIR}/first_failure_excerpt.txt"

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
    grade = "diagnostic_red_global_patch"
elif "DeepseekV4 attention requires a CUDA device" in log or "vllm/models/deepseek_v4/nvidia/model.py" in log:
    grade = "diagnostic_red_ascend_model_registration"
else:
    grade = "diagnostic_yellow_plugin_route_fixed"
result = {
    "probe_grade": grade,
    "plugin_activation_hypothesis_supported": True,
    "vllm_plugins": "ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model",
    "sitecustomize_used": False,
    "pythonpath_overlay_used": False,
    "server_ready_exit_code": ready,
    "request_client_exit_code": request_exit,
    "request_result": request,
    "allocator_error_count": log.count("Allocator for npu is not a DeviceAllocator"),
    "cuda_attention_assertion_count": log.count("DeepseekV4 attention requires a CUDA device"),
    "ascend_model_path_count": log.count("vllm_ascend.models.deepseek_v4"),
    "nvidia_model_path_count": log.count("vllm/models/deepseek_v4/nvidia/model.py"),
    "mtp_on_run": False,
}
(root / "probe_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
(root / "probe_status.txt").write_text(grade + "\n", encoding="utf-8")
PY
```

无论成败，都必须确认 NPU 4-7 没有本轮残留进程；不得 kill NPU 0-3 进程。`base_failed_stop_no_fallback`：任何 base 启动/请求失败都停止，不运行 MTP、overlay、插件子集枚举或其他 fallback。

## 6. 结果分级与交付等待门

- `blocked_provenance`：服务器实际 import root 或 6 个关键文件的 SHA-256 与目标 tag 不一致；不运行插件矩阵或模型。
- `blocked_preflight` / `blocked_resource`：核心版本、source、entry point、测试或资源门未过。
- `diagnostic_red_plugin_filter_hypothesis_mismatch`：fresh-process 矩阵不支持当前假设，禁止启动模型。
- `diagnostic_red_ascend_model_registration`：完整官方插件白名单仍未选择 `AscendDeepseekV4ForCausalLM`，或四卡仍进入 NVIDIA model path。
- `diagnostic_red_global_patch`：完整官方插件白名单仍未让 memory redirect / `MemorySnapshot` 生效。
- `diagnostic_yellow_plugin_route_fixed`：Ascend model route 与 allocator route 均已修复，但 base 在更后首错停止。
- `diagnostic_green_base_runtime`：无 overlay 条件下 server ready 且一个 `4096+64` 请求成功；仍不授权 MTP、八卡、128K 或 P6。

完成实验后先在服务器本地生成 `${ARTIFACT_DIR}/result_summary.md`，建议的最终主题写入其中：

```text
[P5-FP8-v0221rc1-plugins] <probe_grade> | <first_failure_or_base_success> | 2026-07-11
```

`${ARTIFACT_DIR}/result_summary.md` 必须包含 task/Git、服务器实际 import roots、6 文件 expected/observed SHA-256 与 provenance 总门、两种 `VLLM_PLUGINS` 精确值、发现的 entry points、逐项 7-check matrix、两种模式的 platform/registry/三项 memory identity/`MemorySnapshot`、四卡 ready/request/Ascend 与 NVIDIA path/更后首错、NPU 4-7 健康和残留。另生成 `${ARTIFACT_DIR}/delivery_candidates.tsv`，逐项列出摘要与候选附件的精确服务器路径、bytes、SHA-256、敏感性、`email` / `upload-api` 可行性和一个推荐方式。

本轮尚未批准任何结果传输。生成上述两个本地文件后立即暂停，只在当前任务会话向用户展示候选清单并询问：选择 `email` 统一发送正文+批准附件，还是选择 `upload-api` 统一上传 `result_summary.md`+批准附件。确认前禁止调用 `send_notify.py` 的发送/测试模式，禁止 upload-api 预检或上传，也禁止先发一封状态邮件。raw log、完整 NPU SMI、模型和大 artifact 保持 server-local。不得显示 token、`.env` 值、其他用户 PID/命令或未脱敏敏感信息。

用户确认后只执行已选渠道和精确范围：

- 选择 `email`：使用 `python3 通信模块/send_notify.py --subject "<上述主题>" --body-file <result_summary.md> --attach <每个已批准附件> --confirmed-method email`，正文和每个附件均不得超过 70KB，一封邮件完成交付。
- 选择 `upload-api`：不发送任何邮件；将 `result_summary.md` 与每个已批准附件分别用 `python3 通信模块/upload_file.py --upload <文件> --confirmed-method upload-api` 上传。

任一渠道失败后只在当前任务会话报告脱敏错误并重新等待用户决定；不得自动重试、改名、补发状态邮件、扩展范围或切换渠道。
