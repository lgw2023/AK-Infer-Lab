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
