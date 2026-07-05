# P1.2 Server Runtime Trace Smoke Handoff

Task ID: `runtime_trace_smoke_2026_0705_p1_001`.

Evidence anchor: `obs_2026_0705_atlas800t_a2_006`.

Contract anchor: `工作记录与进度笔记本/p1_inference_contracts/fixtures/minimal_runtime_trace.jsonl`.

This is the first server-facing task after the local P1.1 trace fixture. It is a contract and runtime-stack preflight, not a model performance run.

## Scope

The server should:

- pull the latest committed project state with `git pull --ff-only`;
- validate the P1 inference contracts on the Ascend server checkout;
- validate `fixtures/minimal_runtime_trace.jsonl` with the local validator;
- report whether the server runtime stack exposes candidate hook entry points for vLLM-Ascend, MindIE, torch, torch-npu, and CANN tooling;
- return a zipped artifact by email.

The server should not:

- rerun `obs_2026_0705_atlas800t_a2_006`;
- run a real model inference workload in this task;
- change driver, CANN, apt, dpkg, or NPU runtime configuration;
- install packages unless a missing Python dependency blocks the explicitly listed validation commands;
- modify, commit, or push project code from the server.

服务器侧安全边界：

- 不要在服务器上修改、提交或 push 项目代码。
- 不要发送 `.env`、SMTP authorization codes, proxy credentials, account names, private keys, cookies, or other secrets.

## Required Join Keys

The trace smoke shape must preserve these target relationships:

- `trace_id` joins request runtime events to all child events.
- `request_id` joins scheduler/runtime events to operator and object events.
- `layer_id` joins operator timeline events to state object lifecycle events.
- `object_id` joins state object lifecycle events to copy overlap events.
- `stream_id` distinguishes compute and copy streams for overlap checks.

The fixture is valid only if the same request can be followed through request runtime, operator timeline, state object, and transfer overlap scopes.

## Time Bases

- Host-side wrapper markers use `host_monotonic_ns`.
- Future CANN profiler ranges use `cann_device_timeline`.
- This task does not require CANN timeline alignment yet.
- If the runtime stack probe cannot identify a path toward paired host/CANN markers, report that explicitly and do not invent timing attribution.

## Server Commands

Run from the project root on the Ascend server.

```bash
set -u

git pull --ff-only

RUN_ID=runtime_trace_smoke_2026_0705_p1_001
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
FIXTURE="工作记录与进度笔记本/p1_inference_contracts/fixtures/minimal_runtime_trace.jsonl"

mkdir -p "${ARTIFACT_DIR}"

{
  echo "run_id=${RUN_ID}"
  echo "commit=$(git rev-parse --short HEAD)"
  echo "timestamp=$(date -Is)"
  echo "hostname=$(hostname)"
  echo "python=$(command -v python || true)"
} | tee "${ARTIFACT_DIR}/run_context.txt"

python -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest_inference_contracts.log" 2>&1
PYTEST_STATUS=$?
cat "${ARTIFACT_DIR}/pytest_inference_contracts.log"

python - <<'PY' > "${ARTIFACT_DIR}/trace_fixture_validation.txt" 2>&1
from pathlib import Path

from tools.inference_contracts.validation import validate_trace_fixture

path = Path("工作记录与进度笔记本/p1_inference_contracts/fixtures/minimal_runtime_trace.jsonl")
report = validate_trace_fixture(path)
events = report.metadata.get("events", [])
print(f"fixture={path}")
print(f"errors={len(report.errors)}")
print(f"events={len(events)}")
print("resource_scopes=" + ",".join(sorted({str(event.get("resource_scope")) for event in events})))
for error in report.errors:
    print(f"ERROR {error}")
raise SystemExit(1 if report.errors else 0)
PY
TRACE_STATUS=$?
cat "${ARTIFACT_DIR}/trace_fixture_validation.txt"

{
  echo "pytest_exit_code=${PYTEST_STATUS}"
  echo "trace_fixture_validation_exit_code=${TRACE_STATUS}"
} >> "${ARTIFACT_DIR}/run_context.txt"

cp "${FIXTURE}" "${ARTIFACT_DIR}/minimal_runtime_trace.jsonl"

python - <<'PY' > "${ARTIFACT_DIR}/runtime_stack_probe.txt"
import importlib.util
import os
import shutil
import subprocess
import sys

print(f"python_executable={sys.executable}")
print(f"python_version={sys.version.split()[0]}")
print(f"cwd={os.getcwd()}")

for module_name in ["torch", "torch_npu", "vllm", "vllm_ascend", "mindie", "mindspore"]:
    spec = importlib.util.find_spec(module_name)
    print(f"module:{module_name}={'available' if spec else 'missing'}")
    if spec and spec.origin:
        print(f"module_origin:{module_name}={spec.origin}")

for binary_name in ["npu-smi", "msprof", "msnpureport", "python", "python3"]:
    print(f"binary:{binary_name}={shutil.which(binary_name) or 'missing'}")

for command in [
    ["npu-smi", "info"],
    ["python", "-c", "import torch; print(getattr(torch, '__version__', 'unknown'))"],
    ["python", "-c", "import torch_npu; print(getattr(torch_npu, '__version__', 'unknown'))"],
]:
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=20, check=False)
    except Exception as exc:
        print(f"command:{' '.join(command)}=error:{exc}")
        continue
    first_line = (result.stdout or result.stderr or "").strip().splitlines()
    print(f"command:{' '.join(command)}=exit:{result.returncode}:first_line:{first_line[0] if first_line else ''}")
PY

python - <<'PY'
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

run_id = "runtime_trace_smoke_2026_0705_p1_001"
artifact_dir = Path("工作记录与进度笔记本/runtime_trace_smokes") / run_id
zip_path = artifact_dir.with_suffix(".zip")
with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
    for path in sorted(artifact_dir.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(artifact_dir.parent))
print(zip_path)
PY

if [ "${PYTEST_STATUS}" -ne 0 ] || [ "${TRACE_STATUS}" -ne 0 ]; then
  echo "P1.2 validation failed; attach the zip artifact and include the failing exit code in email."
else
  echo "P1.2 validation passed; attach the zip artifact in email."
fi
```

## Return Requirements / 回传要求

Email subject:

```text
[AK服务器] 任务完成：runtime trace smoke runtime_trace_smoke_2026_0705_p1_001
```

Email body must include:

- commit hash after `git pull --ff-only`;
- pytest exit status;
- trace fixture validation exit status;
- whether `torch`, `torch_npu`, `vllm`, `vllm_ascend`, `mindie`, and CANN tools are available;
- zip artifact path;
- any blocker that prevents the listed commands from completing.

Attach:

- `工作记录与进度笔记本/runtime_trace_smokes/runtime_trace_smoke_2026_0705_p1_001.zip`

Do not send `.env`, SMTP authorization codes, proxy credentials, account names, private keys, cookies, or other secrets.

## Success Criteria / 成功口径

- `python -m pytest tests/inference_contracts -q` exits with status 0.
- `trace_fixture_validation.txt` reports `errors=0`.
- The artifact includes `run_context.txt`, `pytest_inference_contracts.log`, `trace_fixture_validation.txt`, `minimal_runtime_trace.jsonl`, and `runtime_stack_probe.txt`.
- The report explicitly covers `trace_id`, `request_id`, `layer_id`, `object_id`, `stream_id`, `host_monotonic_ns`, and `cann_device_timeline` as the next runtime hook target keys and time bases.

This task can only prove that the server checkout can see and validate the P1.1 trace contract. It does not prove runtime hook correctness, CANN timeline alignment, or model bottleneck attribution.
