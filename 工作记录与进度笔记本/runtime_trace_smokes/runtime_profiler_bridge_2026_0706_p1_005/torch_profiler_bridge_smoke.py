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
