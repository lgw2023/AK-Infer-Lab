# 开发机 -> 服务器消息

> 本文件每次只保留当前待执行任务；旧历史信息已清空。

## 当前任务：P1.5 runtime marker pairing 诊断

- 任务 ID：`runtime_marker_pairing_2026_0705_p1_004`
- 证据基线：`obs_2026_0705_atlas800t_a2_006`
- P1.2 预检：`runtime_trace_smoke_2026_0705_p1_001`
- P1.3 hook 侦查：`runtime_hook_discovery_2026_0705_p1_002`
- P1.4 hook 原型：`runtime_hook_proto_2026_0705_p1_003`
- 当前契约入口：`工作记录与进度笔记本/p1_inference_contracts/`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_marker_pairing_handoff.md`

P1.4 最新反馈邮件时间为 2026-07-05 22:53:33 CST，服务器执行 commit 为 `bbc98a7`，`tests/inference_contracts` 为 `11 passed in 0.19s`，`runtime_hook_proto_trace.jsonl` 校验 `errors=0`、`events=4`。P1.4 已证明候选 hook 可 import、可 inspect、可临时 wrapper patch 并恢复，也证明 host-side P1 JSONL 原型可通过 validator。

P1.4 未解决的问题是 marker pairing：官方脚本把 `msprof --output` 指向含中文路径的 artifact 目录时退出 `255`；改用 `/tmp/msprof_marker_p1_003` 后 `msprof --msproftx=on` 能退出 `0`，并生成 host、device_6、sqlite、sample.json 等产物，但 `ak_p1_msprof_marker_prefill` / `ak_p1_msprof_marker_matmul` 未在可检索产物中命中。因此当前仍不能声称 CANN device timeline 已与 host/runtime marker 对齐。

本轮目标只做无模型 marker pairing 取证：固定使用 ASCII `/tmp` 目录作为 `msprof --output`，执行极小 NPU tensor marker smoke，枚举 profiler 产物，搜索 marker 名称，读取 sqlite/json 结构和时间字段候选，并给出是否能进入小模型 trace smoke 的 pairing 结论。

## 服务器执行边界

请执行：

- 在服务器项目根目录 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行本文件命令。
- 通过 `git pull --ff-only` 获取开发机已提交的最新项目状态。
- 使用服务器当前 conda 环境；不创建新环境。
- 默认使用 `AK_OBS_NPU_DEVICE=npu:6`；如果 NPU 6 不可用，可改用 NPU 7，并在邮件中说明。
- 使用 `/tmp/runtime_marker_pairing_2026_0705_p1_004_msprof` 作为 `msprof --output`，不要把 msprof output 直接指向中文路径。
- 产出并邮件回传 `runtime_marker_pairing_2026_0705_p1_004.zip`。

请不要执行：

- 不要运行真实模型推理、小模型 smoke、vLLM engine serve/generate 或 P000-P012 workload。
- 不要访问、加载、复制或枚举服务器 `models/` 目录下的模型文件。
- 不要安装、升级、卸载或修复 `vllm`、`vllm_ascend`、`mindie`、`mindspore` 或其他推理框架包。
- 不要修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码。
- 不要自动修复或重装 `ascend910b-driver`。
- 不要在服务器上修改、提交或 push 项目代码。
- 不要发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。

## 本轮必须回答的问题

- 使用 ASCII `/tmp` 目录作为 `msprof --output` 后，`msprof --msproftx=on` 是否稳定退出 `0`？
- profiler 目录下实际生成哪些 host/device/sqlite/json/raw 文件？
- 二进制 grep 是否能在任何 profiler 产物中命中 `ak_p1_msprof_marker_prefill` / `ak_p1_msprof_marker_matmul` / `ak_p1_msprof_marker_decode`？
- sqlite 表结构中是否存在 marker、range、event、api、op、time、timestamp、start、end、duration 等字段？
- sqlite 文本列搜索是否能命中 marker 名称？
- json 产物中是否存在可解释的 marker 或时间字段？
- 是否能给出 host marker 与 device timeline 的可验证 pairing 证据？如果不能，请明确 blocker 和证据文件。

## 执行命令

在昇腾服务器项目根目录执行：

```bash
set -u

git pull --ff-only

RUN_ID=runtime_marker_pairing_2026_0705_p1_004
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
MSPROF_OUT="/tmp/${RUN_ID}_msprof"
export RUN_ID ARTIFACT_DIR MSPROF_OUT
export AK_OBS_NPU_DEVICE="${AK_OBS_NPU_DEVICE:-npu:6}"

rm -rf "${MSPROF_OUT}"
mkdir -p "${ARTIFACT_DIR}" "${MSPROF_OUT}"

{
  echo "run_id=${RUN_ID}"
  echo "commit=$(git rev-parse --short HEAD)"
  echo "timestamp=$(date -Is)"
  echo "hostname=$(hostname)"
  echo "python=$(command -v python || true)"
  echo "AK_OBS_NPU_DEVICE=${AK_OBS_NPU_DEVICE}"
  echo "MSPROF_OUT=${MSPROF_OUT}"
} | tee "${ARTIFACT_DIR}/run_context.txt"

python -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest_inference_contracts.log" 2>&1
PYTEST_STATUS=$?
cat "${ARTIFACT_DIR}/pytest_inference_contracts.log"
echo "pytest_exit_code=${PYTEST_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

cat > "${ARTIFACT_DIR}/marker_pairing_smoke.py" <<'PY'
import os
import time

device = os.environ.get("AK_OBS_NPU_DEVICE", "npu:6")
markers = [
    "ak_p1_msprof_marker_prefill",
    "ak_p1_msprof_marker_matmul",
    "ak_p1_msprof_marker_decode",
]

print(f"device={device}", flush=True)
for marker in markers:
    print(f"marker_name={marker}", flush=True)

import torch
import torch_npu  # noqa: F401

torch.npu.set_device(device)
torch.npu.synchronize()
x = torch.randn((64, 64), device=device)
y = torch.randn((64, 64), device=device)

with torch.profiler.record_function(markers[0]):
    a = x + y
    torch.npu.synchronize()

with torch.profiler.record_function(markers[1]):
    b = x @ y
    torch.npu.synchronize()

with torch.profiler.record_function(markers[2]):
    c = b + a
    torch.npu.synchronize()

print(f"result_shape={tuple(c.shape)}", flush=True)
print(f"host_monotonic_ns={time.monotonic_ns()}", flush=True)
PY

MSPROF_BIN="$(command -v msprof || true)"
if [ -z "${MSPROF_BIN}" ]; then
  echo "msprof_missing=1" | tee "${ARTIFACT_DIR}/msprof_marker_pairing.log"
  MSPROF_STATUS=127
else
  "${MSPROF_BIN}" --msproftx=on --output="${MSPROF_OUT}" \
    python "${ARTIFACT_DIR}/marker_pairing_smoke.py" \
    > "${ARTIFACT_DIR}/msprof_marker_pairing.log" 2>&1
  MSPROF_STATUS=$?
fi

cat "${ARTIFACT_DIR}/msprof_marker_pairing.log"
echo "msprof_marker_pairing_exit_code=${MSPROF_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

find "${MSPROF_OUT}" -maxdepth 8 -type f -print | sort > "${ARTIFACT_DIR}/msprof_output_files.txt" 2>&1 || true

grep -aR -n -E "ak_p1_msprof_marker_(prefill|matmul|decode)" "${MSPROF_OUT}" \
  > "${ARTIFACT_DIR}/msprof_grep_marker_hits.txt" 2>&1 || true
if [ ! -s "${ARTIFACT_DIR}/msprof_grep_marker_hits.txt" ]; then
  echo "(no text or binary grep hits for ak_p1_msprof_marker_* in profiler output tree)" \
    > "${ARTIFACT_DIR}/msprof_grep_marker_hits.txt"
fi

python - <<'PY'
import json
import os
import sqlite3
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
root = Path(os.environ["MSPROF_OUT"])
markers = [
    "ak_p1_msprof_marker_prefill",
    "ak_p1_msprof_marker_matmul",
    "ak_p1_msprof_marker_decode",
]
time_tokens = ("time", "timestamp", "start", "end", "duration", "ts")

schema_rows = ["db_path\ttable\tcolumn\ttype"]
sqlite_hits = ["db_path\ttable\tcolumn\trowid\tmarker\tvalue_preview"]
json_keys = []
time_candidates = ["source\tpath\ttable_or_json\tcolumn_or_key\ttype_or_value"]

def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'

def preview(value, limit=240):
    text = str(value).replace("\n", "\\n").replace("\t", " ")
    if len(text) > limit:
        return text[:limit] + "..."
    return text

def walk_json_keys(obj, prefix=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            json_keys.append(path)
            if any(token in path.lower() for token in time_tokens):
                time_candidates.append(
                    "\t".join(["json", str(current_json), "-", path, preview(type(value).__name__)])
                )
            walk_json_keys(value, path)
    elif isinstance(obj, list):
        for index, value in enumerate(obj[:20]):
            walk_json_keys(value, f"{prefix}[{index}]")

for current_json in root.rglob("*.json"):
    try:
        data = json.loads(current_json.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        json_keys.append(f"{current_json}\t<json_error:{type(exc).__name__}:{exc}>")
        continue
    walk_json_keys(data)

for db_path in root.rglob("*.db"):
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception as exc:
        schema_rows.append(f"{db_path}\t<connect_error>\t-\t{type(exc).__name__}:{exc}")
        continue
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table' order by name"
            )
        ]
        for table in tables:
            try:
                cols = list(conn.execute(f"pragma table_info({quote_ident(table)})"))
            except Exception as exc:
                schema_rows.append(f"{db_path}\t{table}\t<pragma_error>\t{type(exc).__name__}:{exc}")
                continue
            for _, column, col_type, *_ in cols:
                schema_rows.append(f"{db_path}\t{table}\t{column}\t{col_type}")
                lower_name = str(column).lower()
                if any(token in lower_name for token in time_tokens):
                    time_candidates.append(
                        "\t".join(["sqlite", str(db_path), table, str(column), str(col_type)])
                    )
            for _, column, _, *_ in cols:
                quoted_col = quote_ident(str(column))
                quoted_table = quote_ident(str(table))
                for marker in markers:
                    try:
                        rows = conn.execute(
                            f"select rowid, {quoted_col} from {quoted_table} "
                            f"where cast({quoted_col} as text) like ? limit 20",
                            (f"%{marker}%",),
                        ).fetchall()
                    except Exception:
                        continue
                    for rowid, value in rows:
                        sqlite_hits.append(
                            "\t".join(
                                [
                                    str(db_path),
                                    str(table),
                                    str(column),
                                    str(rowid),
                                    marker,
                                    preview(value),
                                ]
                            )
                        )
    finally:
        conn.close()

(artifact_dir / "msprof_sqlite_schema.tsv").write_text("\n".join(schema_rows) + "\n", encoding="utf-8")
(artifact_dir / "msprof_sqlite_marker_hits.tsv").write_text("\n".join(sqlite_hits) + "\n", encoding="utf-8")
(artifact_dir / "msprof_json_key_inventory.txt").write_text("\n".join(json_keys[:5000]) + "\n", encoding="utf-8")
(artifact_dir / "msprof_timebase_candidates.tsv").write_text("\n".join(time_candidates) + "\n", encoding="utf-8")

grep_text = (artifact_dir / "msprof_grep_marker_hits.txt").read_text(encoding="utf-8", errors="replace")
grep_has_marker = "ak_p1_msprof_marker_" in grep_text
sqlite_has_marker = len(sqlite_hits) > 1
time_has_candidate = len(time_candidates) > 1

conclusion = [
    f"grep_has_marker={int(grep_has_marker)}",
    f"sqlite_has_marker={int(sqlite_has_marker)}",
    f"time_has_candidate={int(time_has_candidate)}",
]
if grep_has_marker or sqlite_has_marker:
    conclusion.append("pairing_status=marker_name_visible_in_msprof_outputs")
else:
    conclusion.append("pairing_status=marker_name_not_found_in_msprof_outputs")
    conclusion.append("small_model_trace_claim=CANN timeline pairing must remain unclaimed")

(artifact_dir / "msprof_pairing_conclusion.txt").write_text("\n".join(conclusion) + "\n", encoding="utf-8")
PY

python - <<'PY' > "${ARTIFACT_DIR}/marker_pairing_trace_validation.txt" 2>&1
import json
import os
import time
from pathlib import Path

from tools.inference_contracts.validation import validate_trace_fixture

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
device = os.environ.get("AK_OBS_NPU_DEVICE", "npu:6")
trace_path = artifact_dir / "marker_pairing_trace.jsonl"
base = time.monotonic_ns()
object_id = "activation:req_marker_pairing_0001:L00"

events = [
    {
        "schema_version": "0.1.0",
        "event_id": "evt_marker_request_enqueue",
        "timestamp_ns": base,
        "time_base": "host_monotonic_ns",
        "trace_id": "trace_p1_marker_pairing_0001",
        "request_id": "req_marker_pairing_0001",
        "session_id": "session_marker_pairing",
        "phase": "enqueue",
        "event_type": "point",
        "resource_scope": "request_runtime_profile",
        "layer_id": None,
        "op_name": "marker_pairing_request",
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
        "queue_wait_us": 0,
        "overlap_ratio": None,
        "policy_decision": "marker_pairing_probe",
        "hit_or_miss": "not_applicable",
        "stall_reason": "unknown",
        "evidence_source": "runtime_hook_probe",
        "artifact_path": str(trace_path.name),
    },
    {
        "schema_version": "0.1.0",
        "event_id": "evt_marker_state",
        "timestamp_ns": base + 1000,
        "time_base": "host_monotonic_ns",
        "trace_id": "trace_p1_marker_pairing_0001",
        "request_id": "req_marker_pairing_0001",
        "session_id": "session_marker_pairing",
        "phase": "prefill",
        "event_type": "lifecycle",
        "resource_scope": "state_object_profile",
        "layer_id": 0,
        "op_name": "marker_pairing_activation",
        "kernel_name": None,
        "stream_id": f"{device}:copy:marker",
        "device_id": device,
        "object_type": "activation",
        "object_id": object_id,
        "source_tier": "host_dram",
        "target_tier": "hbm",
        "bytes_read": 16384,
        "bytes_write": 16384,
        "latency_us": 1,
        "queue_wait_us": 0,
        "overlap_ratio": None,
        "policy_decision": "marker_pairing_state_object",
        "hit_or_miss": "not_applicable",
        "stall_reason": "unknown",
        "evidence_source": "runtime_hook_probe",
        "artifact_path": str(trace_path.name),
    },
    {
        "schema_version": "0.1.0",
        "event_id": "evt_marker_h2d",
        "timestamp_ns": base + 2000,
        "time_base": "host_monotonic_ns",
        "trace_id": "trace_p1_marker_pairing_0001",
        "request_id": "req_marker_pairing_0001",
        "session_id": "session_marker_pairing",
        "phase": "prefill",
        "event_type": "span_end",
        "resource_scope": "transfer_overlap_profile",
        "layer_id": 0,
        "op_name": "marker_pairing_h2d",
        "kernel_name": "prototype_copy",
        "stream_id": f"{device}:copy:marker",
        "device_id": device,
        "object_type": "activation",
        "object_id": object_id,
        "source_tier": "host_dram",
        "target_tier": "hbm",
        "bytes_read": 16384,
        "bytes_write": 16384,
        "latency_us": 1,
        "queue_wait_us": 0,
        "overlap_ratio": None,
        "policy_decision": "marker_pairing_copy",
        "hit_or_miss": "not_applicable",
        "stall_reason": "unknown",
        "evidence_source": "runtime_hook_probe",
        "artifact_path": str(trace_path.name),
    },
    {
        "schema_version": "0.1.0",
        "event_id": "evt_marker_operator",
        "timestamp_ns": base + 3000,
        "time_base": "host_monotonic_ns",
        "trace_id": "trace_p1_marker_pairing_0001",
        "request_id": "req_marker_pairing_0001",
        "session_id": "session_marker_pairing",
        "phase": "prefill",
        "event_type": "span_end",
        "resource_scope": "operator_timeline_profile",
        "layer_id": 0,
        "op_name": "ak_p1_msprof_marker_matmul",
        "kernel_name": "prototype_operator",
        "stream_id": f"{device}:compute:marker",
        "device_id": device,
        "object_type": "activation",
        "object_id": object_id,
        "source_tier": "hbm",
        "target_tier": "hbm",
        "bytes_read": 32768,
        "bytes_write": 16384,
        "latency_us": 1,
        "queue_wait_us": 0,
        "overlap_ratio": None,
        "policy_decision": "marker_pairing_operator_marker",
        "hit_or_miss": "not_applicable",
        "stall_reason": "unknown",
        "evidence_source": "runtime_hook_probe",
        "artifact_path": str(trace_path.name),
    },
]

with trace_path.open("w", encoding="utf-8") as handle:
    for event in events:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

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
  echo "## msprof pairing log tail"
  tail -n 80 "${ARTIFACT_DIR}/msprof_marker_pairing.log"
  echo
  echo "## grep marker hits"
  cat "${ARTIFACT_DIR}/msprof_grep_marker_hits.txt"
  echo
  echo "## sqlite marker hits"
  cat "${ARTIFACT_DIR}/msprof_sqlite_marker_hits.tsv"
  echo
  echo "## pairing conclusion"
  cat "${ARTIFACT_DIR}/msprof_pairing_conclusion.txt"
  echo
  echo "## trace validation"
  cat "${ARTIFACT_DIR}/marker_pairing_trace_validation.txt"
} | tee "${ARTIFACT_DIR}/summary.txt"

( cd "$(dirname "${ARTIFACT_DIR}")" && rm -f "${RUN_ID}.zip" && zip -qr "${RUN_ID}.zip" "${RUN_ID}" )
echo "artifact_zip=$(dirname "${ARTIFACT_DIR}")/${RUN_ID}.zip" | tee -a "${ARTIFACT_DIR}/run_context.txt"
```

## 期望回传附件

请将以下文件打包为：

```text
工作记录与进度笔记本/runtime_trace_smokes/runtime_marker_pairing_2026_0705_p1_004.zip
```

至少包含：

- `run_context.txt`
- `pytest_inference_contracts.log`
- `marker_pairing_smoke.py`
- `msprof_marker_pairing.log`
- `msprof_output_files.txt`
- `msprof_grep_marker_hits.txt`
- `msprof_sqlite_schema.tsv`
- `msprof_sqlite_marker_hits.tsv`
- `msprof_json_key_inventory.txt`
- `msprof_timebase_candidates.tsv`
- `msprof_pairing_conclusion.txt`
- `marker_pairing_trace.jsonl`
- `marker_pairing_trace_validation.txt`
- `summary.txt`

## 邮件回传要求

邮件主题：

```text
[AK服务器] 任务完成：runtime marker pairing runtime_marker_pairing_2026_0705_p1_004
```

默认同时发送给：

```text
gwlee1995@gmail.com,yilili1023@gmail.com
```

邮件正文请包含：

- run id、hostname、执行时间、git commit、Python 路径、NPU 设备
- pytest 结果
- `msprof_marker_pairing_exit_code`
- marker grep 是否命中
- sqlite marker 搜索是否命中
- 是否找到 host/device 时间字段候选
- `msprof_pairing_conclusion.txt` 的完整内容
- 是否仍不能声称 CANN device timeline pairing
- 附件 zip 文件名

## 成功口径

最低成功：

- pytest 通过
- `msprof --msproftx=on` 使用 `/tmp` 输出目录完成或明确失败码
- 产出 profiler 文件枚举、grep 搜索结果、sqlite schema、sqlite marker 搜索、json key 盘点、timebase 候选和 pairing 结论

强成功：

- marker 名称在 msprof 可检索产物中命中
- 同时找到可解释的 host/device 时间字段候选
- 能给出后续小模型 trace smoke 的 pairing 证据路径

如果 marker 仍不可见，本轮仍算完成诊断，但结论必须写明：后续小模型阶段不能声称 CANN device timeline 已对齐。
