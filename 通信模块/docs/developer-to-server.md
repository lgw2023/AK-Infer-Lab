# 开发机 -> 服务器消息

> 本文件每次只保留当前待执行任务；旧历史信息已清空。

## 当前任务：P1.4 runtime hook 原型与无模型 marker pairing smoke

- 任务 ID：`runtime_hook_proto_2026_0705_p1_003`
- 证据基线：`obs_2026_0705_atlas800t_a2_006`
- P1.2 预检：`runtime_trace_smoke_2026_0705_p1_001`
- P1.3 hook 侦查：`runtime_hook_discovery_2026_0705_p1_002`
- 当前契约入口：`工作记录与进度笔记本/p1_inference_contracts/`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_hook_proto_handoff.md`

P1.3 最新反馈邮件时间为 2026-07-05 21:53:52 CST，服务器执行 commit 为 `7527cd8`，`tests/inference_contracts` 为 `11 passed in 0.20s`，`host_marker_npu_smoke.jsonl` 校验 `errors=0`、`events=4`。服务器现有环境中 `torch`、`torch_npu`、`vllm`、`vllm_ascend`、`msprof`、`msnpureport` 可用；`mindie` 和 `mindspore` 缺失。本轮继续不处理缺失框架，不安装包，不跑真实模型。

P1.3 已定位的强候选包括：

- request runtime：`vllm/v1/engine/core.py`、`vllm/v1/engine/async_llm.py`、`vllm/v1/engine/llm_engine.py`
- scheduler：`vllm/v1/core/sched/scheduler.py`
- model execution：`vllm/v1/worker/gpu_model_runner.py`、`vllm_ascend/worker/model_runner_v1.py`、`vllm_ascend/worker/worker.py`、`vllm_ascend/worker/v2/model_runner.py`
- KV / prefix / state：`vllm/v1/core/kv_cache_manager.py`、`block_pool` 相关模块、`distributed/kv_transfer/kv_connector/v1/*`
- copy overlap：`vllm_ascend/worker/model_runner_v1.py` 中的 `torch.npu.Stream` / `update_stream` / record_function 相关路径
- profiler marker：`torch.profiler.record_function` 可用；`msprof --help` 显示支持 `--msproftx` / `mstx` 数据，但 host marker 到 CANN device timeline 的 pairing 仍未确认

本轮目标是把 P1.3 的“入口发现”推进到“可插桩原型验证”：确认候选类/函数签名、在临时 Python 进程内验证 wrapper/monkey-patch 可挂载并可恢复、生成一份符合 P1 schema 的无模型 hook 原型 JSONL，并尝试用 `msprof --msproftx=on` 包住极小 NPU tensor marker smoke，判断 marker 名称是否能在 profiler 产物中被检索到。

## 服务器执行边界

请执行：

- 在服务器项目根目录 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行本文件命令。
- 通过 `git pull --ff-only` 获取开发机已提交的最新项目状态。
- 使用服务器当前 conda 环境；不创建新环境。
- 默认使用 `AK_OBS_NPU_DEVICE=npu:6`；如果 NPU 6 不可用，可改用 NPU 7，并在邮件中说明。
- 只做 import、签名/源码位置读取、临时进程内 wrapper 挂载/恢复、无模型 NPU tensor marker smoke。
- 产出并邮件回传 `runtime_hook_proto_2026_0705_p1_003.zip`。

请不要执行：

- 不要运行真实模型推理、小模型 smoke、vLLM engine serve/generate 或 P000-P012 workload。
- 不要访问、加载、复制或枚举服务器 `models/` 目录下的模型文件。
- 不要安装、升级、卸载或修复 `vllm`、`vllm_ascend`、`mindie`、`mindspore` 或其他推理框架包。
- 不要修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码。
- 不要把 monkey-patch 写入源码；只允许在临时 Python 进程内 `setattr` 后立即恢复。
- 不要自动修复或重装 `ascend910b-driver`。
- 不要在服务器上修改、提交或 push 项目代码。
- 不要发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。

## 本轮必须回答的问题

- P1.3 候选模块中，哪些类/函数可 import、可 `inspect.signature`、可定位 source file/source line？
- `Scheduler.schedule`、`Scheduler.update_from_output`、`NPUModelRunner.execute_model`、`vllm_ascend.worker.worker.execute_model` 等候选是否能在临时进程内挂载 wrapper 并恢复？
- 无模型 hook 原型 JSONL 是否能通过当前 P1 trace validator？
- `msprof --msproftx=on` 包住极小 NPU tensor marker smoke 是否能成功退出？如失败，失败码和错误文本是什么？
- profiler 产物中是否能检索到 `ak_p1_msprof_marker_prefill` / `ak_p1_msprof_marker_matmul` 等 marker 名称？
- CANN timeline pairing 是否仍未确认；如果已有可验证线索，请给出具体文件、命令和 marker 证据。

## 执行命令

在昇腾服务器项目根目录执行：

```bash
set -u

git pull --ff-only

RUN_ID=runtime_hook_proto_2026_0705_p1_003
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
export RUN_ID ARTIFACT_DIR
export AK_OBS_NPU_DEVICE="${AK_OBS_NPU_DEVICE:-npu:6}"

mkdir -p "${ARTIFACT_DIR}"

{
  echo "run_id=${RUN_ID}"
  echo "commit=$(git rev-parse --short HEAD)"
  echo "timestamp=$(date -Is)"
  echo "hostname=$(hostname)"
  echo "python=$(command -v python || true)"
  echo "AK_OBS_NPU_DEVICE=${AK_OBS_NPU_DEVICE}"
} | tee "${ARTIFACT_DIR}/run_context.txt"

python -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest_inference_contracts.log" 2>&1
PYTEST_STATUS=$?
cat "${ARTIFACT_DIR}/pytest_inference_contracts.log"
echo "pytest_exit_code=${PYTEST_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

cat > "${ARTIFACT_DIR}/hook_target_probe.py" <<'PY'
import functools
import importlib
import inspect
import json
import os
import time
from pathlib import Path

artifact_dir = Path(__file__).resolve().parent
inventory_path = artifact_dir / "hook_target_inventory.jsonl"
patchability_path = artifact_dir / "hook_patchability.tsv"
trace_path = artifact_dir / "runtime_hook_proto_trace.jsonl"
device = os.environ.get("AK_OBS_NPU_DEVICE", "npu:6")

target_modules = [
    ("request_runtime", "vllm.v1.engine.core", ["EngineCore"], ["add_request", "step", "run", "run_busy_loop"]),
    ("request_runtime", "vllm.v1.engine.async_llm", ["AsyncLLM"], ["add_request", "generate", "step", "run"]),
    ("request_runtime", "vllm.v1.engine.llm_engine", ["LLMEngine"], ["add_request", "step", "run"]),
    ("scheduler", "vllm.v1.core.sched.scheduler", ["Scheduler"], ["schedule", "update_from_output"]),
    ("model_execute", "vllm.v1.worker.gpu_model_runner", ["GPUModelRunner"], ["execute_model", "synchronize_input_prep", "sample"]),
    ("model_execute", "vllm_ascend.worker.model_runner_v1", ["NPUModelRunner"], ["execute_model", "update_stream", "sample"]),
    ("model_execute", "vllm_ascend.worker.worker", ["*"], ["execute_model"]),
    ("model_execute", "vllm_ascend.worker.v2.model_runner", ["NPUModelRunner"], ["execute_model", "update_stream", "sample"]),
]

def safe_signature(obj):
    try:
        return str(inspect.signature(obj))
    except Exception as exc:
        return f"<signature_error:{type(exc).__name__}:{exc}>"

def source_location(obj):
    try:
        return inspect.getsourcefile(obj), inspect.getsourcelines(obj)[1]
    except Exception as exc:
        return None, f"<source_error:{type(exc).__name__}:{exc}>"

def candidate_classes(module, class_names):
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if "*" in class_names or name in class_names:
            yield name, obj

def candidate_methods(cls, method_names):
    for name, obj in inspect.getmembers(cls, inspect.isfunction):
        if any(token in name for token in method_names):
            yield name, obj

def make_wrapper(original):
    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        return original(*args, **kwargs)
    return wrapper

inventory = []
patch_rows = ["category\tmodule\tclass\tmethod\tpatch_status\trestore_status\tsource_file\tsource_line\tsignature"]

for category, module_name, class_names, method_names in target_modules:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        inventory.append({
            "category": category,
            "module": module_name,
            "status": "import_error",
            "error": f"{type(exc).__name__}: {exc}",
        })
        continue

    module_file = getattr(module, "__file__", None)
    inventory.append({
        "category": category,
        "module": module_name,
        "status": "import_ok",
        "module_file": module_file,
    })

    for class_name, cls in candidate_classes(module, class_names):
        class_file, class_line = source_location(cls)
        inventory.append({
            "category": category,
            "module": module_name,
            "class": class_name,
            "status": "class_found",
            "source_file": class_file,
            "source_line": class_line,
        })

        for method_name, method in candidate_methods(cls, method_names):
            method_file, method_line = source_location(method)
            signature = safe_signature(method)
            record = {
                "category": category,
                "module": module_name,
                "class": class_name,
                "method": method_name,
                "status": "method_found",
                "source_file": method_file,
                "source_line": method_line,
                "signature": signature,
            }
            inventory.append(record)

            patch_status = "not_attempted"
            restore_status = "not_attempted"
            original = getattr(cls, method_name, None)
            try:
                setattr(cls, method_name, make_wrapper(original))
                patch_status = "patched_in_process"
            except Exception as exc:
                patch_status = f"patch_error:{type(exc).__name__}:{exc}"
            finally:
                try:
                    setattr(cls, method_name, original)
                    restore_status = "restored"
                except Exception as exc:
                    restore_status = f"restore_error:{type(exc).__name__}:{exc}"

            patch_rows.append(
                "\t".join(
                    [
                        category,
                        module_name,
                        class_name,
                        method_name,
                        patch_status,
                        restore_status,
                        str(method_file),
                        str(method_line),
                        signature.replace("\t", " "),
                    ]
                )
            )

with inventory_path.open("w", encoding="utf-8") as handle:
    for record in inventory:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

patchability_path.write_text("\n".join(patch_rows) + "\n", encoding="utf-8")

now = time.monotonic_ns()
base_event = {
    "schema_version": "0.1.0",
    "trace_id": "trace_p1_hook_proto_0001",
    "request_id": "req_hook_proto_0001",
    "session_id": "session_hook_proto",
    "queue_wait_us": 0,
    "overlap_ratio": None,
    "hit_or_miss": "not_applicable",
    "stall_reason": "unknown",
    "artifact_path": "runtime_hook_proto_trace.jsonl",
}

events = [
    {
        **base_event,
        "event_id": "evt_hook_request_enqueue",
        "timestamp_ns": now,
        "time_base": "host_monotonic_ns",
        "phase": "enqueue",
        "event_type": "point",
        "resource_scope": "request_runtime_profile",
        "layer_id": None,
        "op_name": "hook_proto_request",
        "kernel_name": None,
        "stream_id": "host:runtime",
        "device_id": "host:cpu",
        "object_type": None,
        "object_id": None,
        "source_tier": "host_dram",
        "target_tier": "hbm",
        "bytes_read": 0,
        "bytes_write": 0,
        "latency_us": 0,
        "policy_decision": "prototype_hook_emit",
        "evidence_source": "runtime_hook_probe",
    },
    {
        **base_event,
        "event_id": "evt_hook_activation_state",
        "timestamp_ns": now + 1_000,
        "time_base": "host_monotonic_ns",
        "phase": "prefill",
        "event_type": "lifecycle",
        "resource_scope": "state_object_profile",
        "layer_id": 0,
        "op_name": "hook_proto_activation",
        "kernel_name": None,
        "stream_id": f"{device}:copy:proto",
        "device_id": device,
        "object_type": "activation",
        "object_id": "activation:req_hook_proto_0001:L00",
        "source_tier": "host_dram",
        "target_tier": "hbm",
        "bytes_read": 16384,
        "bytes_write": 16384,
        "latency_us": 1,
        "policy_decision": "prototype_state_object",
        "evidence_source": "runtime_hook_probe",
    },
    {
        **base_event,
        "event_id": "evt_hook_h2d_done",
        "timestamp_ns": now + 2_000,
        "time_base": "host_monotonic_ns",
        "phase": "prefill",
        "event_type": "span_end",
        "resource_scope": "transfer_overlap_profile",
        "layer_id": 0,
        "op_name": "hook_proto_h2d",
        "kernel_name": "prototype_copy",
        "stream_id": f"{device}:copy:proto",
        "device_id": device,
        "object_type": "activation",
        "object_id": "activation:req_hook_proto_0001:L00",
        "source_tier": "host_dram",
        "target_tier": "hbm",
        "bytes_read": 16384,
        "bytes_write": 16384,
        "latency_us": 1,
        "policy_decision": "prototype_copy",
        "evidence_source": "runtime_hook_probe",
    },
    {
        **base_event,
        "event_id": "evt_hook_operator",
        "timestamp_ns": now + 3_000,
        "time_base": "host_monotonic_ns",
        "phase": "prefill",
        "event_type": "span_end",
        "resource_scope": "operator_timeline_profile",
        "layer_id": 0,
        "op_name": "hook_proto_execute_model",
        "kernel_name": "prototype_operator",
        "stream_id": f"{device}:compute:proto",
        "device_id": device,
        "object_type": "activation",
        "object_id": "activation:req_hook_proto_0001:L00",
        "source_tier": "hbm",
        "target_tier": "hbm",
        "bytes_read": 32768,
        "bytes_write": 16384,
        "latency_us": 1,
        "policy_decision": "prototype_operator_marker",
        "evidence_source": "runtime_hook_probe",
    },
]

with trace_path.open("w", encoding="utf-8") as handle:
    for event in events:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
PY

python "${ARTIFACT_DIR}/hook_target_probe.py" > "${ARTIFACT_DIR}/hook_target_probe.log" 2>&1
HOOK_PROBE_STATUS=$?
echo "hook_target_probe_exit_code=${HOOK_PROBE_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"
cat "${ARTIFACT_DIR}/hook_target_probe.log"

python - <<'PY' > "${ARTIFACT_DIR}/runtime_hook_proto_validation.txt" 2>&1
from pathlib import Path
from tools.inference_contracts.validation import validate_trace_fixture

path = Path("工作记录与进度笔记本/runtime_trace_smokes/runtime_hook_proto_2026_0705_p1_003/runtime_hook_proto_trace.jsonl")
report = validate_trace_fixture(path)
print(f"errors={len(report.errors)}")
print(f"events={len(report.metadata.get('events', []))}")
for error in report.errors:
    print(error)
PY

cat > "${ARTIFACT_DIR}/msprof_marker_smoke.py" <<'PY'
import os
import time

import torch
import torch_npu  # noqa: F401

device = os.environ.get("AK_OBS_NPU_DEVICE", "npu:6")
torch.npu.set_device(device)

def sync():
    torch.npu.synchronize()

with torch.profiler.record_function("ak_p1_msprof_marker_prefill"):
    x = torch.ones((64, 64), dtype=torch.float16, device="cpu").to(device)
    sync()

with torch.profiler.record_function("ak_p1_msprof_marker_matmul"):
    y = x @ x
    sync()

print(f"device={device}")
print(f"result_shape={tuple(y.shape)}")
print(f"host_monotonic_ns={time.monotonic_ns()}")
PY

MSPROF_DIR="${ARTIFACT_DIR}/msprof_marker"
MSPROF_STATUS=0
if command -v timeout >/dev/null 2>&1; then
  timeout 90 msprof --output "${MSPROF_DIR}" --msproftx=on --runtime-api=on --task-time=on python "${ARTIFACT_DIR}/msprof_marker_smoke.py" > "${ARTIFACT_DIR}/msprof_marker_smoke.log" 2>&1 || MSPROF_STATUS=$?
else
  msprof --output "${MSPROF_DIR}" --msproftx=on --runtime-api=on --task-time=on python "${ARTIFACT_DIR}/msprof_marker_smoke.py" > "${ARTIFACT_DIR}/msprof_marker_smoke.log" 2>&1 || MSPROF_STATUS=$?
fi
echo "msprof_marker_smoke_exit_code=${MSPROF_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

{
  echo "msprof_dir=${MSPROF_DIR}"
  echo "msprof_marker_smoke_exit_code=${MSPROF_STATUS}"
  find "${MSPROF_DIR}" -maxdepth 4 -type f -print 2>/dev/null | sort
} > "${ARTIFACT_DIR}/msprof_marker_artifacts.txt"

grep -R "ak_p1_msprof_marker" "${MSPROF_DIR}" > "${ARTIFACT_DIR}/msprof_marker_search.txt" 2>&1 || true

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt"
  echo
  echo "## pytest"
  cat "${ARTIFACT_DIR}/pytest_inference_contracts.log"
  echo
  echo "## hook validation"
  cat "${ARTIFACT_DIR}/runtime_hook_proto_validation.txt"
  echo
  echo "## hook patchability summary"
  sed -n '1,80p' "${ARTIFACT_DIR}/hook_patchability.tsv" 2>/dev/null || true
  echo
  echo "## msprof marker log"
  sed -n '1,160p' "${ARTIFACT_DIR}/msprof_marker_smoke.log" 2>/dev/null || true
  echo
  echo "## msprof marker search"
  sed -n '1,120p' "${ARTIFACT_DIR}/msprof_marker_search.txt" 2>/dev/null || true
} > "${ARTIFACT_DIR}/summary.txt"

(cd "$(dirname "${ARTIFACT_DIR}")" && zip -qr "${RUN_ID}.zip" "${RUN_ID}")
```

## 回传要求

邮件主题建议：

```text
[AK服务器] 任务完成：runtime hook proto runtime_hook_proto_2026_0705_p1_003
```

邮件正文请包含：

- run id、服务器主机名、执行时间、git commit。
- `pytest_inference_contracts.log` 结果和退出码。
- `runtime_hook_proto_validation.txt` 的 `errors` 和 `events`。
- `hook_target_inventory.jsonl` / `hook_patchability.tsv` 的关键结论：哪些候选可 import、可定位源码、可 patch、可恢复。
- `msprof_marker_smoke_exit_code`、`msprof_marker_artifacts.txt` 文件列表、`msprof_marker_search.txt` 是否命中 marker 名称。
- 明确说明本轮是否仍未确认 CANN device timeline pairing。
- 明确说明本轮没有访问 `models/`、没有加载模型、没有安装或修复推理框架包。

附件请回传：

```text
工作记录与进度笔记本/runtime_trace_smokes/runtime_hook_proto_2026_0705_p1_003.zip
```

默认同时发送到：

```text
gwlee1995@gmail.com,yilili1023@gmail.com
```

## 成功口径

本轮成功只表示：

- 服务器能基于实际 `vllm` / `vllm_ascend` 模块定位候选 hook 类/函数签名。
- 临时 Python 进程内 wrapper 挂载/恢复机制可用。
- 无模型 hook 原型事件能通过当前 P1 trace validator。
- `msprof --msproftx=on` 的 marker smoke 给出了明确结果：命中 marker、未命中 marker 或工具失败原因。

本轮仍不表示：

- 真实 vLLM/vLLM-Ascend 推理 hook 已经采集成功。
- CANN device timeline 已经和 host runtime marker 对齐。
- 小模型或 MoE 模型已经可跑。
- 任何真实模型瓶颈已经完成归因。
