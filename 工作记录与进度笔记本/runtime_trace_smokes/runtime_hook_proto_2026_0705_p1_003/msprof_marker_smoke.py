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
