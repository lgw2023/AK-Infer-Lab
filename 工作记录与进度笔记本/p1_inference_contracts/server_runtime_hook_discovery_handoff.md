# P1.3 Server Runtime Hook Discovery Handoff

Task ID: `runtime_hook_discovery_2026_0705_p1_002`.

Evidence anchors:
- `obs_2026_0705_atlas800t_a2_006`
- `runtime_trace_smoke_2026_0705_p1_001`

This task is the first step after the P1.2 contract preflight. The latest P1.2 feedback email was sent at 2026-07-05 20:40:48 CST for commit `42cb0f9`; `tests/inference_contracts` passed with `11 passed in 0.19s`, and the minimal trace fixture validation reported `errors=0`, `events=8`. This P1.3 task is a read-only hook discovery and marker feasibility task. It does not run a model workload, does not load any model from the server `models/` directory, and does not claim runtime attribution.

This task does not install, upgrade, or repair inference-framework packages. If `vllm`, `vllm_ascend`, `mindie`, or other framework packages are missing or unusable, report that as `framework_missing_or_unusable` and leave environment/package work to a separate task.

## Scope

The server should:

- pull the latest committed project state with `git pull --ff-only`;
- confirm the P1 inference contracts still pass on the server checkout;
- inspect the actual server-side `vllm` and `vllm_ascend` source paths for hook candidate symbols only if those modules are already importable in the current environment;
- inspect `torch_npu`, `torch.npu`, `torch.profiler`, `msprof`, and `msnpureport` marker/profile APIs;
- run one minimal NPU tensor smoke with host-side `time.monotonic_ns()` markers on `npu:6` by default;
- validate the generated marker JSONL with the existing P1 trace validator;
- return a zipped artifact by email.

The server should not:

- run real model inference;
- access, load, or copy any model under the server `models/` directory;
- run P000-P012 workload prompts;
- modify driver, CANN, apt, dpkg, NPU runtime, or vLLM source;
- install packages;
- install, upgrade, or repair `vllm`, `vllm_ascend`, `mindie`, `mindspore`, or any other inference framework package;
- modify, commit, or push project code from the server.

## Target Questions

The returned artifact should answer these questions with evidence:

- Are `vllm` and `vllm_ascend` already importable in the current server environment? If yes, where are request enqueue / scheduling / finish hooks in the current vLLM checkout?
- If `vllm_ascend` is already importable, where are NPU model execution hooks?
- If the current framework packages are usable, where are KV/prefix/cache manager and NPU copy hooks?
- Does `torch.npu` expose usable `Event`, `Stream`, `synchronize`, and profiler marker APIs?
- Can a minimal host-marker JSONL preserve `trace_id`, `request_id`, `layer_id`, `object_id`, and `stream_id` and pass the current validator?
- Is CANN timeline pairing still unconfirmed, or is there a concrete marker/range API candidate for the next task?

## Server Commands

Run from the project root on the Ascend server.

```bash
set -u

git pull --ff-only

RUN_ID=runtime_hook_discovery_2026_0705_p1_002
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

python - <<'PY' > "${ARTIFACT_DIR}/runtime_module_probe.txt" 2>&1
import importlib.util
import sys
from pathlib import Path

print(f"python_executable={sys.executable}")
print(f"python_version={sys.version.split()[0]}")

for module_name in ["torch", "torch_npu", "vllm", "vllm_ascend", "mindie", "mindspore"]:
    spec = importlib.util.find_spec(module_name)
    print(f"module:{module_name}={'available' if spec else 'missing'}")
    if not spec:
        continue
    if spec.origin:
        print(f"module_origin:{module_name}={spec.origin}")
    roots = list(spec.submodule_search_locations or [])
    if roots:
        print(f"module_root:{module_name}={roots[0]}")
    elif spec.origin:
        print(f"module_root:{module_name}={Path(spec.origin).parent}")
PY

python - <<'PY' > "${ARTIFACT_DIR}/torch_npu_marker_api_probe.txt" 2>&1
import importlib

def print_matching_attrs(label, obj):
    tokens = ["stream", "event", "synchron", "profil", "range", "record", "device", "memory"]
    print(f"[{label}]")
    for attr in sorted(dir(obj)):
        lower = attr.lower()
        if any(token in lower for token in tokens):
            value = getattr(obj, attr, None)
            print(f"{attr}\t{type(value).__name__}")

try:
    torch = importlib.import_module("torch")
    print(f"torch_version={getattr(torch, '__version__', 'unknown')}")
    print_matching_attrs("torch.npu", getattr(torch, "npu", object()))
    print_matching_attrs("torch.profiler", getattr(torch, "profiler", object()))
except Exception as exc:
    print(f"torch_probe_error={type(exc).__name__}: {exc}")

try:
    torch_npu = importlib.import_module("torch_npu")
    print(f"torch_npu_version={getattr(torch_npu, '__version__', 'unknown')}")
    print_matching_attrs("torch_npu", torch_npu)
except Exception as exc:
    print(f"torch_npu_probe_error={type(exc).__name__}: {exc}")
PY

python - <<'PY' > "${ARTIFACT_DIR}/vllm_hook_candidates.tsv" 2>&1
import importlib.util
from pathlib import Path

categories = {
    "request_runtime": ["add_request", "finish_requests", "AsyncLLM", "LLMEngine", "EngineCore", "OutputProcessor"],
    "scheduler": ["class Scheduler", "def schedule", "SchedulerOutput", "RequestQueue", "update_from_output"],
    "model_execute": ["execute_model", "ModelRunner", "NPUModelRunner", "GPUModelRunner", "sample_tokens"],
    "kv_prefix_state": ["kv_cache", "prefix_cache", "block_pool", "KVConnector", "register_kv_caches", "load_kv", "save_kv"],
    "copy_overlap": ["torch.npu.Stream", "torch.npu.Event", "launch_copy", "copy_blocks", "synchronize"],
    "profiler_marker": ["record_function", "record_function_or_nullcontext", "profiler", "range_push", "range_pop"],
}
skip_parts = {".git", "__pycache__", "tests", "docs", "examples", "benchmarks"}
max_hits_per_category = 100
hit_counts = {category: 0 for category in categories}

def roots_for(module_name):
    spec = importlib.util.find_spec(module_name)
    if not spec:
        return []
    roots = list(spec.submodule_search_locations or [])
    if roots:
        return [Path(roots[0])]
    if spec.origin:
        return [Path(spec.origin).parent]
    return []

print("module\tcategory\tpath\tline\ttext")
for module_name in ["vllm", "vllm_ascend"]:
    for root in roots_for(module_name):
        for path in sorted(root.rglob("*.py")):
            if any(part in skip_parts for part in path.parts):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            rel_path = path.relative_to(root)
            for line_number, line in enumerate(lines, start=1):
                stripped = " ".join(line.strip().split())
                lowered = stripped.lower()
                if not stripped:
                    continue
                for category, needles in categories.items():
                    if hit_counts[category] >= max_hits_per_category:
                        continue
                    if any(needle.lower() in lowered for needle in needles):
                        hit_counts[category] += 1
                        print(f"{module_name}\t{category}\t{rel_path}\t{line_number}\t{stripped[:220]}")

print("# hit_counts")
for category, count in sorted(hit_counts.items()):
    print(f"# {category}\t{count}")
PY

python - <<'PY' > "${ARTIFACT_DIR}/vllm_tree_summary.txt" 2>&1
import importlib.util
from pathlib import Path

for module_name in ["vllm", "vllm_ascend"]:
    spec = importlib.util.find_spec(module_name)
    print(f"## {module_name}")
    if not spec:
        print("missing")
        continue
    roots = list(spec.submodule_search_locations or [])
    root = Path(roots[0]) if roots else Path(spec.origin).parent
    print(f"root={root}")
    for rel in [
        "v1/engine/core.py",
        "v1/engine/async_llm.py",
        "v1/engine/llm_engine.py",
        "v1/core/sched/scheduler.py",
        "v1/worker/gpu_model_runner.py",
        "worker/model_runner_v1.py",
        "worker/worker.py",
        "simple_kv_offload/copy_backend.py",
        "simple_kv_offload/worker.py",
    ]:
        candidate = root / rel
        print(f"{rel}\t{'present' if candidate.is_file() else 'missing'}")
PY

{
  echo "msprof=$(command -v msprof || true)"
  if command -v msprof >/dev/null 2>&1; then
    msprof --help | sed -n '1,120p'
  fi
  echo "msnpureport=$(command -v msnpureport || true)"
  if command -v msnpureport >/dev/null 2>&1; then
    msnpureport --help | sed -n '1,80p'
  fi
} > "${ARTIFACT_DIR}/cann_tool_help.txt" 2>&1

python - <<'PY' > "${ARTIFACT_DIR}/host_marker_npu_smoke.log" 2>&1
import json
import os
import time
import traceback
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
device = os.environ.get("AK_OBS_NPU_DEVICE", "npu:6")
trace_path = artifact_dir / "host_marker_npu_smoke.jsonl"
trace_id = "trace_p1_marker_smoke_0001"
request_id = "req_marker_0001"
session_id = "session_marker_smoke"
object_id = "activation:req_marker_0001:L00"

def now_ns():
    return time.monotonic_ns()

def emit(handle, **event):
    base = {
        "schema_version": "0.1.0",
        "trace_id": trace_id,
        "request_id": request_id,
        "session_id": session_id,
        "queue_wait_us": 0,
        "overlap_ratio": None,
        "hit_or_miss": "not_applicable",
        "stall_reason": "unknown",
        "artifact_path": "host_marker_npu_smoke.jsonl",
    }
    base.update(event)
    handle.write(json.dumps(base, ensure_ascii=False) + "\n")

try:
    import torch
    import torch_npu  # noqa: F401

    if hasattr(torch, "npu"):
        torch.npu.set_device(device)

    tensor_bytes = 64 * 64 * 4
    req_start = now_ns()
    host_tensor = torch.ones((64, 64), dtype=torch.float32)
    copy_start = now_ns()
    npu_tensor = host_tensor.to(device)
    if hasattr(torch, "npu"):
        torch.npu.synchronize()
    copy_end = now_ns()
    compute_start = now_ns()
    result = npu_tensor @ npu_tensor
    if hasattr(torch, "npu"):
        torch.npu.synchronize()
    compute_end = now_ns()
    _ = float(result.cpu()[0, 0])

    with trace_path.open("w", encoding="utf-8") as handle:
        emit(
            handle,
            event_id="evt_marker_req_prefill_start",
            timestamp_ns=req_start,
            time_base="host_monotonic_ns",
            phase="prefill",
            event_type="span_start",
            resource_scope="request_runtime_profile",
            layer_id=None,
            op_name="host_marker_smoke",
            kernel_name=None,
            stream_id="host:runtime",
            device_id="host:cpu",
            object_type=None,
            object_id=None,
            source_tier="host_dram",
            target_tier="hbm",
            bytes_read=0,
            bytes_write=0,
            latency_us=(compute_end - req_start) // 1000,
            policy_decision="marker_smoke",
            evidence_source="runtime_queue_trace",
        )
        emit(
            handle,
            event_id="evt_marker_activation_state",
            timestamp_ns=copy_start,
            time_base="host_monotonic_ns",
            phase="prefill",
            event_type="lifecycle",
            resource_scope="state_object_profile",
            layer_id=0,
            op_name="activation_h2d",
            kernel_name=None,
            stream_id=f"{device}:copy:unknown",
            device_id=device,
            object_type="activation",
            object_id=object_id,
            source_tier="host_dram",
            target_tier="hbm",
            bytes_read=tensor_bytes,
            bytes_write=tensor_bytes,
            latency_us=(copy_end - copy_start) // 1000,
            policy_decision="copy_activation_to_npu",
            evidence_source="state_object_trace",
        )
        emit(
            handle,
            event_id="evt_marker_h2d_done",
            timestamp_ns=copy_end,
            time_base="host_monotonic_ns",
            phase="prefill",
            event_type="span_end",
            resource_scope="transfer_overlap_profile",
            layer_id=0,
            op_name="h2d_copy",
            kernel_name="torch_tensor_to_npu",
            stream_id=f"{device}:copy:unknown",
            device_id=device,
            object_type="activation",
            object_id=object_id,
            source_tier="host_dram",
            target_tier="hbm",
            bytes_read=tensor_bytes,
            bytes_write=tensor_bytes,
            latency_us=(copy_end - copy_start) // 1000,
            policy_decision="sync_copy",
            evidence_source="copy_overlap_trace",
        )
        emit(
            handle,
            event_id="evt_marker_matmul_end",
            timestamp_ns=compute_end,
            time_base="host_monotonic_ns",
            phase="prefill",
            event_type="span_end",
            resource_scope="operator_timeline_profile",
            layer_id=0,
            op_name="matmul_marker",
            kernel_name="torch_matmul",
            stream_id=f"{device}:compute:unknown",
            device_id=device,
            object_type="activation",
            object_id=object_id,
            source_tier="hbm",
            target_tier="hbm",
            bytes_read=tensor_bytes * 2,
            bytes_write=tensor_bytes,
            latency_us=(compute_end - compute_start) // 1000,
            policy_decision="execute_marker_matmul",
            evidence_source="operator_timeline",
        )

    from tools.inference_contracts.validation import validate_trace_fixture

    report = validate_trace_fixture(trace_path)
    validation_path = artifact_dir / "host_marker_npu_smoke_validation.txt"
    with validation_path.open("w", encoding="utf-8") as handle:
        handle.write(f"errors={len(report.errors)}\n")
        handle.write(f"events={len(report.metadata.get('events', []))}\n")
        for error in report.errors:
            handle.write(f"ERROR {error}\n")
    print(f"device={device}")
    print(f"trace_path={trace_path}")
    print(f"validation_errors={len(report.errors)}")
    raise SystemExit(1 if report.errors else 0)
except Exception as exc:
    print(f"BLOCKED host marker NPU smoke failed: {type(exc).__name__}: {exc}")
    traceback.print_exc()
    raise SystemExit(2)
PY
HOST_MARKER_STATUS=$?
echo "host_marker_npu_smoke_exit_code=${HOST_MARKER_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

python - <<'PY'
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

run_id = os.environ["RUN_ID"]
artifact_dir = Path(os.environ["ARTIFACT_DIR"])
zip_path = artifact_dir.with_suffix(".zip")
with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
    for path in sorted(artifact_dir.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(artifact_dir.parent))
print(zip_path)
PY

if [ "${PYTEST_STATUS}" -ne 0 ] || [ "${HOST_MARKER_STATUS}" -ne 0 ]; then
  echo "P1.3 hook discovery completed with blockers; attach the zip artifact and include failing exit code(s)."
else
  echo "P1.3 hook discovery passed; attach the zip artifact in email."
fi
```

## Return Requirements / 回传要求

Email subject:

```text
[AK服务器] 任务完成：runtime hook discovery runtime_hook_discovery_2026_0705_p1_002
```

Email body must include:

- commit hash after `git pull --ff-only`;
- pytest exit status;
- host-marker NPU smoke exit status;
- whether `host_marker_npu_smoke_validation.txt` reports `errors=0`;
- actual module roots for `vllm` and `vllm_ascend` if already importable; otherwise report the import/root discovery failure;
- the strongest hook candidates found for request runtime, scheduler, model execution, KV/prefix state, copy overlap, and profiler marker if the framework packages are already usable;
- whether CANN timeline pairing is still unconfirmed or has a concrete next candidate;
- zip artifact path;
- any blocker that prevents the listed commands from completing.

Attach:

- `工作记录与进度笔记本/runtime_trace_smokes/runtime_hook_discovery_2026_0705_p1_002.zip`

Do not send `.env`, SMTP authorization codes, proxy credentials, account names, private keys, cookies, or other secrets.

## Success Criteria / 成功口径

- P1 inference contract tests pass.
- If server-side `vllm` / `vllm_ascend` are already importable, `vllm_hook_candidates.tsv` contains candidate files for scheduler/model/KV/copy/profiler categories. If they are not importable, the task succeeds only if the blocker is explicit and no package installation is attempted.
- `torch_npu_marker_api_probe.txt` reports whether `torch.npu.Event`, `torch.npu.Stream`, and `torch.npu.synchronize` exist.
- `host_marker_npu_smoke_validation.txt` reports `errors=0`, or the blocker is explicit and reproducible.
- The report still distinguishes host marker feasibility from real vLLM hook correctness and CANN timeline alignment.

This task can only prove hook-entry discovery and minimal marker feasibility. It does not prove model runtime hook correctness, CANN timeline alignment, or bottleneck attribution.
