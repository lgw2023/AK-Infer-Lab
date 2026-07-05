# 开发机 -> 服务器消息

> 本文件每次只保留当前待执行任务；旧历史信息已清空。

## 当前任务：P1.6 runtime profiler bridge 诊断

- 任务 ID：`runtime_profiler_bridge_2026_0706_p1_005`
- 证据基线：`obs_2026_0705_atlas800t_a2_006`
- P1.2 预检：`runtime_trace_smoke_2026_0705_p1_001`
- P1.3 hook 侦查：`runtime_hook_discovery_2026_0705_p1_002`
- P1.4 hook 原型：`runtime_hook_proto_2026_0705_p1_003`
- P1.5 marker pairing：`runtime_marker_pairing_2026_0705_p1_004`
- 当前契约入口：`工作记录与进度笔记本/p1_inference_contracts/`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_profiler_bridge_handoff.md`

P1.5 最新反馈邮件时间为 2026-07-06 00:14:08 CST，服务器执行 commit 为 `569f7a4`，`tests/inference_contracts` 为 `11 passed in 0.19s`，`marker_pairing_trace.jsonl` 校验 `errors=0`、`events=4`。`msprof --msproftx=on` 在 ASCII `/tmp/runtime_marker_pairing_2026_0705_p1_004_msprof` 输出目录下稳定退出 `0`，并生成 78 个 host/device/sqlite/json/raw profiler 文件。

P1.5 的关键结论是：`torch.profiler.record_function` 写入的 `ak_p1_msprof_marker_prefill` / `matmul` / `decode` 没有出现在 `msprof` 可检索产物中。邮件正文和 `msprof_pairing_conclusion.txt` 已手工修正 `grep_has_marker=0`、`sqlite_has_marker=0`，`summary.txt` 里的 `grep_has_marker=1` 是脚本占位文本导致的假阳性。虽然 sqlite/json 中存在时间字段候选，但当前仍不能声称 CANN device timeline 已与 host/runtime marker 对齐。

本轮目标不是小模型，不访问服务器 `models/`，也不安装或修复任何推理框架包。本轮只验证替代 pairing 路径：服务器现有 `torch` / `torch_npu` / PyTorch profiler 能否导出同一份 Chrome trace，其中同时包含自定义 `record_function` marker 和 NPU/device 事件候选。

## 服务器执行边界

请执行：

- 在服务器项目根目录 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行本文件命令。
- 通过 `git pull --ff-only` 获取开发机已提交的最新项目状态。
- 使用服务器当前 conda 环境；不创建新环境。
- 默认使用 `AK_OBS_NPU_DEVICE=npu:6`；如果 NPU 6 不可用，可改用 NPU 7，并在邮件中说明。
- 产出并邮件回传 `runtime_profiler_bridge_2026_0706_p1_005.zip`。

请不要执行：

- 不要运行真实模型推理、小模型 smoke、vLLM engine serve/generate 或 P000-P012 workload。
- 不要访问、加载、复制或枚举服务器 `models/` 目录下的模型文件。
- 不要安装、升级、卸载或修复 `vllm`、`vllm_ascend`、`mindie`、`mindspore` 或其他推理框架包。
- 不要修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码。
- 不要自动修复或重装 `ascend910b-driver`。
- 不要在服务器上修改、提交或 push 项目代码。
- 不要发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。

## 本轮必须回答的问题

- `torch.profiler.ProfilerActivity` 是否包含 `NPU` 或等价 device activity？
- 极小 NPU tensor smoke 是否能在 `torch.profiler.profile(...)` 下完成并导出 Chrome trace？
- 导出的 trace 中是否能找到 `ak_p1_torch_profiler_prefill` / `matmul` / `decode` marker？
- 同一 trace 中是否能找到 NPU/device/op/copy 事件候选？
- marker 和 device event 是否共享 Chrome trace 的 `ts` / `dur` 时间字段？
- 如果该路径可行，后续小模型阶段能否把 `torch_profiler_trace` 作为候选 pairing 证据？
- 如果该路径不可行，后续小模型阶段是否仍只能按 host-side runtime trace 验收？

## 执行命令

在昇腾服务器项目根目录执行：

```bash
set -u

git pull --ff-only

RUN_ID=runtime_profiler_bridge_2026_0706_p1_005
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
export RUN_ID ARTIFACT_DIR
export AK_OBS_NPU_DEVICE="${AK_OBS_NPU_DEVICE:-npu:6}"

rm -rf "${ARTIFACT_DIR}"
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

python - <<'PY' > "${ARTIFACT_DIR}/profiler_api_inventory.txt" 2>&1
import inspect

try:
    import torch
    print(f"torch_version={getattr(torch, '__version__', 'unknown')}")
    from torch.profiler import ProfilerActivity
    print("[ProfilerActivity]")
    for name in sorted(dir(ProfilerActivity)):
        if name.startswith("_"):
            continue
        print(name)
    print("[torch.profiler.profile_signature]")
    print(inspect.signature(torch.profiler.profile))
    print("[torch.profiler.record_function]")
    print(torch.profiler.record_function)
except Exception as exc:
    print(f"torch_profiler_probe_error={type(exc).__name__}: {exc}")

try:
    import torch_npu
    print(f"torch_npu_version={getattr(torch_npu, '__version__', 'unknown')}")
    print("[torch_npu.profiler]")
    profiler = getattr(torch_npu, "profiler", None)
    print(f"module={profiler}")
    if profiler is not None:
        for name in sorted(dir(profiler)):
            if name.startswith("_"):
                continue
            value = getattr(profiler, name)
            print(f"{name}\t{type(value).__name__}")
except Exception as exc:
    print(f"torch_npu_profiler_probe_error={type(exc).__name__}: {exc}")
PY

cat > "${ARTIFACT_DIR}/torch_profiler_bridge_smoke.py" <<'PY'
import os
import sys
import time
import traceback
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
device = os.environ.get("AK_OBS_NPU_DEVICE", "npu:6")
trace_path = artifact_dir / "torch_profiler_trace.json"
markers = [
    "ak_p1_torch_profiler_prefill",
    "ak_p1_torch_profiler_matmul",
    "ak_p1_torch_profiler_decode",
]

try:
    import torch
    import torch_npu  # noqa: F401
    from torch.profiler import ProfilerActivity, profile, record_function

    print(f"device={device}", flush=True)
    print(f"torch_version={getattr(torch, '__version__', 'unknown')}", flush=True)
    print(f"torch_npu_available={hasattr(torch, 'npu')}", flush=True)
    for marker in markers:
        print(f"marker_name={marker}", flush=True)

    activity_names = []
    activities = []
    for name in ("CPU", "NPU"):
        if hasattr(ProfilerActivity, name):
            activity_names.append(name)
            activities.append(getattr(ProfilerActivity, name))
    print(f"profiler_activities={','.join(activity_names) if activity_names else 'none'}", flush=True)

    torch.npu.set_device(device)
    torch.npu.synchronize()
    x = torch.randn((128, 128), device=device)
    y = torch.randn((128, 128), device=device)

    if not activities:
        raise RuntimeError("no ProfilerActivity CPU/NPU activities available")

    started_ns = time.monotonic_ns()
    with profile(
        activities=activities,
        record_shapes=True,
        with_stack=False,
        profile_memory=False,
    ) as prof:
        with record_function(markers[0]):
            a = x + y
            torch.npu.synchronize()
        with record_function(markers[1]):
            b = x @ y
            torch.npu.synchronize()
        with record_function(markers[2]):
            c = b + a
            torch.npu.synchronize()
    ended_ns = time.monotonic_ns()

    prof.export_chrome_trace(str(trace_path))
    print(f"result_shape={tuple(c.shape)}", flush=True)
    print(f"host_monotonic_start_ns={started_ns}", flush=True)
    print(f"host_monotonic_end_ns={ended_ns}", flush=True)
    print(f"trace_path={trace_path}", flush=True)
    print(f"trace_exists={trace_path.exists()}", flush=True)
except Exception:
    traceback.print_exc()
    sys.exit(1)
PY

python "${ARTIFACT_DIR}/torch_profiler_bridge_smoke.py" \
  > "${ARTIFACT_DIR}/torch_profiler_bridge.log" 2>&1
SMOKE_STATUS=$?
cat "${ARTIFACT_DIR}/torch_profiler_bridge.log"
echo "torch_profiler_bridge_exit_code=${SMOKE_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

python - <<'PY'
import json
import os
import time
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
trace_path = artifact_dir / "torch_profiler_trace.json"
markers = [
    "ak_p1_torch_profiler_prefill",
    "ak_p1_torch_profiler_matmul",
    "ak_p1_torch_profiler_decode",
]

inventory_rows = ["index\tname\tcat\tph\tts\tdur\tpid\ttid\targs_preview"]
marker_rows = ["index\tmarker\tname\tcat\tph\tts\tdur\tpid\ttid"]
device_rows = ["index\tname\tcat\tph\tts\tdur\tpid\ttid\treason"]
conclusion = []
events = []

def preview(value, limit=220):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    text = text.replace("\n", "\\n").replace("\t", " ")
    return text[:limit] + ("..." if len(text) > limit else "")

if trace_path.exists():
    try:
        data = json.loads(trace_path.read_text(encoding="utf-8", errors="replace"))
        if isinstance(data, dict):
            raw_events = data.get("traceEvents", [])
        elif isinstance(data, list):
            raw_events = data
        else:
            raw_events = []
        events = [event for event in raw_events if isinstance(event, dict)]
    except Exception as exc:
        conclusion.append(f"trace_parse_error={type(exc).__name__}: {exc}")
else:
    conclusion.append("trace_missing=1")

for index, event in enumerate(events):
    name = str(event.get("name", ""))
    cat = str(event.get("cat", ""))
    ph = str(event.get("ph", ""))
    ts = event.get("ts", "")
    dur = event.get("dur", "")
    pid = event.get("pid", "")
    tid = event.get("tid", "")
    args = event.get("args", {})
    text = " ".join([name, cat, preview(args)]).lower()
    inventory_rows.append(
        "\t".join([str(index), name, cat, ph, str(ts), str(dur), str(pid), str(tid), preview(args)])
    )
    for marker in markers:
        if marker in name or marker in preview(args):
            marker_rows.append(
                "\t".join([str(index), marker, name, cat, ph, str(ts), str(dur), str(pid), str(tid)])
            )
    device_reasons = []
    if any(token in text for token in ("npu", "ascend", "acl", "ge", "aicore", "ai core")):
        device_reasons.append("npu_keyword")
    if any(token in text for token in ("kernel", "matmul", "mm", "add", "memcpy", "copy")) and (
        "cpu" not in cat.lower() or "npu" in text
    ):
        device_reasons.append("op_or_copy_candidate")
    if device_reasons:
        device_rows.append(
            "\t".join([str(index), name, cat, ph, str(ts), str(dur), str(pid), str(tid), ",".join(device_reasons)])
        )

(artifact_dir / "torch_profiler_trace_inventory.tsv").write_text(
    "\n".join(inventory_rows[:5001]) + "\n", encoding="utf-8"
)
(artifact_dir / "torch_profiler_marker_hits.tsv").write_text(
    "\n".join(marker_rows) + "\n", encoding="utf-8"
)
(artifact_dir / "torch_profiler_device_events.tsv").write_text(
    "\n".join(device_rows[:501]) + "\n", encoding="utf-8"
)

marker_hit_count = max(0, len(marker_rows) - 1)
device_event_count = max(0, len(device_rows) - 1)
has_marker_ts = any(row.split("\t")[5] not in ("", "None") for row in marker_rows[1:])
has_device_ts = any(row.split("\t")[4] not in ("", "None") for row in device_rows[1:])

conclusion.extend(
    [
        f"trace_exists={int(trace_path.exists())}",
        f"trace_event_count={len(events)}",
        f"marker_hit_count={marker_hit_count}",
        f"device_event_candidate_count={device_event_count}",
        f"marker_has_ts={int(has_marker_ts)}",
        f"device_event_has_ts={int(has_device_ts)}",
    ]
)
if marker_hit_count and device_event_count and has_marker_ts and has_device_ts:
    conclusion.append("bridge_status=marker_and_device_events_in_single_trace")
    conclusion.append("small_model_trace_claim=torch_profiler_trace_candidate_only")
elif marker_hit_count and not device_event_count:
    conclusion.append("bridge_status=marker_only_no_device_events")
    conclusion.append("small_model_trace_claim=host_side_only_until_device_events_found")
elif device_event_count and not marker_hit_count:
    conclusion.append("bridge_status=device_events_only_no_marker")
    conclusion.append("small_model_trace_claim=host_side_only_until_marker_found")
else:
    conclusion.append("bridge_status=no_bridge_evidence")
    conclusion.append("small_model_trace_claim=host_side_only")

(artifact_dir / "torch_profiler_bridge_conclusion.txt").write_text(
    "\n".join(conclusion) + "\n", encoding="utf-8"
)

trace_jsonl = artifact_dir / "runtime_profiler_bridge_trace.jsonl"
now = time.monotonic_ns()
object_id = "activation:req_profiler_bridge_0001:L00"
device_id = os.environ.get("AK_OBS_NPU_DEVICE", "npu:6")
base = {
    "schema_version": "0.1.0",
    "trace_id": "trace_p1_profiler_bridge_0001",
    "request_id": "req_profiler_bridge_0001",
    "session_id": "session_profiler_bridge",
    "time_base": "host_monotonic_ns",
    "device_id": device_id,
    "source_tier": "host_dram",
    "target_tier": "hbm",
    "hit_or_miss": "not_applicable",
    "stall_reason": "unknown",
    "queue_wait_us": 0,
    "artifact_path": "torch_profiler_trace.json",
    "evidence_source": "torch_profiler_bridge",
}
events_jsonl = [
    {
        **base,
        "event_id": "evt_profiler_bridge_enqueue",
        "timestamp_ns": now,
        "phase": "enqueue",
        "event_type": "point",
        "resource_scope": "request_runtime_profile",
        "layer_id": None,
        "object_id": None,
        "object_type": None,
        "stream_id": "host:runtime",
        "op_name": "profiler_bridge_request",
        "kernel_name": None,
        "bytes_read": 0,
        "bytes_write": 0,
        "latency_us": 0,
        "overlap_ratio": None,
        "policy_decision": "torch_profiler_bridge_probe",
    },
    {
        **base,
        "event_id": "evt_profiler_bridge_state",
        "timestamp_ns": now + 1000,
        "phase": "prefill",
        "event_type": "lifecycle",
        "resource_scope": "state_object_profile",
        "layer_id": 0,
        "object_id": object_id,
        "object_type": "activation",
        "stream_id": f"{device_id}:copy:profiler_bridge",
        "op_name": "profiler_bridge_activation",
        "kernel_name": None,
        "bytes_read": 65536,
        "bytes_write": 65536,
        "latency_us": 1,
        "overlap_ratio": None,
        "policy_decision": "torch_profiler_bridge_state_object",
    },
    {
        **base,
        "event_id": "evt_profiler_bridge_h2d",
        "timestamp_ns": now + 2000,
        "phase": "prefill",
        "event_type": "span_end",
        "resource_scope": "transfer_overlap_profile",
        "layer_id": 0,
        "object_id": object_id,
        "object_type": "activation",
        "stream_id": f"{device_id}:copy:profiler_bridge",
        "op_name": "profiler_bridge_h2d",
        "kernel_name": "torch_profiler_copy_candidate",
        "bytes_read": 65536,
        "bytes_write": 65536,
        "latency_us": 1,
        "overlap_ratio": None,
        "policy_decision": "torch_profiler_bridge_copy",
    },
    {
        **base,
        "event_id": "evt_profiler_bridge_operator",
        "timestamp_ns": now + 3000,
        "phase": "prefill",
        "event_type": "span_end",
        "resource_scope": "operator_timeline_profile",
        "layer_id": 0,
        "object_id": object_id,
        "object_type": "activation",
        "stream_id": f"{device_id}:compute:profiler_bridge",
        "op_name": "ak_p1_torch_profiler_matmul",
        "kernel_name": "torch_profiler_operator_candidate",
        "bytes_read": 131072,
        "bytes_write": 65536,
        "latency_us": 1,
        "overlap_ratio": None,
        "policy_decision": "torch_profiler_bridge_operator_marker",
    },
]
trace_jsonl.write_text(
    "\n".join(json.dumps(event, ensure_ascii=False, sort_keys=True) for event in events_jsonl) + "\n",
    encoding="utf-8",
)
PY

python - <<'PY' > "${ARTIFACT_DIR}/runtime_profiler_bridge_trace_validation.txt" 2>&1
import os
from pathlib import Path

from tools.inference_contracts.validation import validate_trace_fixture

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
trace_path = artifact_dir / "runtime_profiler_bridge_trace.jsonl"
report = validate_trace_fixture(trace_path)
print(f"errors={len(report.errors)}")
print(f"events={len(report.metadata.get('events', []))}")
for error in report.errors:
    print(error)
PY

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt"
  echo
  echo "## pytest"
  cat "${ARTIFACT_DIR}/pytest_inference_contracts.log"
  echo
  echo "## profiler API inventory"
  sed -n '1,160p' "${ARTIFACT_DIR}/profiler_api_inventory.txt"
  echo
  echo "## torch profiler bridge log"
  cat "${ARTIFACT_DIR}/torch_profiler_bridge.log"
  echo
  echo "## marker hits"
  cat "${ARTIFACT_DIR}/torch_profiler_marker_hits.tsv"
  echo
  echo "## device event candidates"
  sed -n '1,80p' "${ARTIFACT_DIR}/torch_profiler_device_events.tsv"
  echo
  echo "## bridge conclusion"
  cat "${ARTIFACT_DIR}/torch_profiler_bridge_conclusion.txt"
  echo
  echo "## trace validation"
  cat "${ARTIFACT_DIR}/runtime_profiler_bridge_trace_validation.txt"
} | tee "${ARTIFACT_DIR}/summary.txt"

( cd "$(dirname "${ARTIFACT_DIR}")" && rm -f "${RUN_ID}.zip" && zip -qr "${RUN_ID}.zip" "${RUN_ID}" )
echo "artifact_zip=$(dirname "${ARTIFACT_DIR}")/${RUN_ID}.zip" | tee -a "${ARTIFACT_DIR}/run_context.txt"
```

## 期望回传附件

请将以下文件打包为：

```text
工作记录与进度笔记本/runtime_trace_smokes/runtime_profiler_bridge_2026_0706_p1_005.zip
```

至少包含：

- `run_context.txt`
- `pytest_inference_contracts.log`
- `profiler_api_inventory.txt`
- `torch_profiler_bridge_smoke.py`
- `torch_profiler_bridge.log`
- `torch_profiler_trace.json`，如果成功导出
- `torch_profiler_trace_inventory.tsv`
- `torch_profiler_marker_hits.tsv`
- `torch_profiler_device_events.tsv`
- `torch_profiler_bridge_conclusion.txt`
- `runtime_profiler_bridge_trace.jsonl`
- `runtime_profiler_bridge_trace_validation.txt`
- `summary.txt`

## 邮件回传要求

邮件主题：

```text
[AK服务器] 任务完成：runtime profiler bridge runtime_profiler_bridge_2026_0706_p1_005
```

默认同时发送给：

```text
gwlee1995@gmail.com,yilili1023@gmail.com
```

邮件正文请包含：

- run id、hostname、执行时间、git commit、Python 路径、NPU 设备
- pytest 结果
- `torch_profiler_bridge_exit_code`
- `ProfilerActivity` 是否包含 `NPU`
- Chrome trace 是否生成
- marker 命中数量
- NPU/device event 候选数量
- `torch_profiler_bridge_conclusion.txt` 的完整内容
- 是否仍不能声称 CANN device timeline pairing
- 附件 zip 文件名

## 成功口径

最低成功：

- pytest 通过
- profiler API 盘点完成
- 无模型 NPU tensor profiler smoke 完成或明确失败码
- 产出 trace 检索、marker 命中、device event 候选和 bridge 结论

强成功：

- Chrome trace 中同时出现自定义 marker 和 NPU/device event 候选
- 两类事件都有 `ts` / `dur` 等同一 trace 时间字段
- 能将 `torch_profiler_trace` 作为后续小模型 smoke 的候选 pairing 路径

如果 marker 或 device event 任一侧缺失，本轮仍算完成诊断，但结论必须写明：后续小模型阶段只能按 host-side runtime trace 验收，不能声称 CANN device timeline 已对齐。
