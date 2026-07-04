from __future__ import annotations

import csv
import importlib.metadata as importlib_metadata
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable


CommandExists = Callable[[str], bool]


def _default_command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _blocked_reason(category: str | None, detail: str | None) -> dict[str, str | None]:
    return {"category": category, "detail": detail}


def _command_text(command: str | list[str]) -> str:
    return command if isinstance(command, str) else " ".join(command)


def _write_result_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "bench_name",
        "status",
        "command",
        "artifact_path",
        "duration_ms",
        "blocked_category",
        "blocked_detail",
        "metric_name",
        "metric_value",
        "unit",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def _record_result(
    *,
    run_dir: Path,
    bench_name: str,
    artifact_name: str,
    status: str,
    command: str | list[str],
    duration_ms: float | None,
    blocked_reason: dict[str, str | None],
    metric_name: str | None = None,
    metric_value: str | float | int | None = None,
    unit: str | None = None,
    metrics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    artifact_path = Path("microbench") / artifact_name
    base_row = {
        "bench_name": bench_name,
        "status": status,
        "command": _command_text(command),
        "artifact_path": str(artifact_path),
        "duration_ms": duration_ms,
        "blocked_category": blocked_reason["category"],
        "blocked_detail": blocked_reason["detail"],
    }
    rows = []
    if metrics:
        for metric in metrics:
            row = dict(base_row)
            row.update(
                {
                    "metric_name": metric.get("metric_name"),
                    "metric_value": metric.get("metric_value"),
                    "unit": metric.get("unit"),
                }
            )
            rows.append(row)
    else:
        row = dict(base_row)
        row.update(
            {
                "metric_name": metric_name,
                "metric_value": metric_value,
                "unit": unit,
            }
        )
        rows.append(row)
    _write_result_csv(run_dir / artifact_path, rows)
    return {
        "bench_name": bench_name,
        "status": status,
        "command": command,
        "artifact_path": str(artifact_path),
        "duration_ms": duration_ms,
        "blocked_reason": blocked_reason,
        "metrics": metrics or [],
    }


def _npu_bench_code(*, bench_name: str, copy_sizes: str, duration_s: int) -> str:
    template = r'''
import json
import os
import time


def emit(payload):
    print(json.dumps(payload, sort_keys=True))
    raise SystemExit(0)


def blocked(category, detail):
    emit({
        "status": "blocked",
        "duration_ms": None,
        "blocked_reason": {"category": category, "detail": detail},
        "metrics": [],
    })


def parse_size(token):
    token = token.strip().upper()
    if not token:
        raise ValueError("empty size token")
    multiplier = 1
    if token[-1] in {"K", "M", "G"}:
        multiplier = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}[token[-1]]
        token = token[:-1]
    return int(float(token) * multiplier)


def metric(name, value, unit):
    if isinstance(value, float):
        value = round(value, 6)
    return {"metric_name": name, "metric_value": value, "unit": unit}


def label_size(num_bytes):
    for suffix, factor in (("G", 1024 ** 3), ("M", 1024 ** 2), ("K", 1024)):
        if num_bytes >= factor and num_bytes % factor == 0:
            return f"{num_bytes // factor}{suffix}"
    return f"{num_bytes}B"


def repeats_for(num_bytes, duration_s):
    if num_bytes >= 256 * 1024 * 1024:
        return 1
    return max(1, min(5, int(duration_s)))


def bandwidth_gbps(num_bytes, seconds):
    if seconds <= 0:
        return 0.0
    return num_bytes / seconds / (1024 ** 3)


def sync():
    torch.npu.synchronize()


def timed(fn):
    started = time.perf_counter()
    fn()
    sync()
    return time.perf_counter() - started


bench_name = __BENCH_NAME__
copy_sizes = __COPY_SIZES__
duration_s = __DURATION_S__

try:
    import torch
    import torch_npu  # noqa: F401

    if not torch.npu.is_available() or torch.npu.device_count() < 1:
        blocked("npu_unavailable", "torch.npu reports no available NPU device")

    device = os.environ.get("AK_OBS_NPU_DEVICE", "npu:0")
    torch.npu.set_device(device)
    sizes = [parse_size(part) for part in copy_sizes.split(",") if part.strip()]
    if not sizes:
        blocked("invalid_input", "copy_sizes is empty")

    metrics = []
    started = time.perf_counter()

    if bench_name in {"npu_copy_h2d", "npu_copy_d2h"}:
        direction = "h2d" if bench_name == "npu_copy_h2d" else "d2h"
        for num_bytes in sizes:
            elements = max(1, num_bytes // 4)
            repeat_count = repeats_for(num_bytes, duration_s)
            if direction == "h2d":
                source = torch.empty(elements, dtype=torch.float32)

                def once():
                    source.to(device)

            else:
                source = torch.empty(elements, dtype=torch.float32, device=device)

                def once():
                    source.cpu()

            once()
            sync()
            elapsed = sum(timed(once) for _ in range(repeat_count)) / repeat_count
            size_label = label_size(num_bytes)
            metrics.append(metric(f"{direction}_latency_us_{size_label}", elapsed * 1_000_000, "us"))
            metrics.append(metric(f"{direction}_bandwidth_gbps_{size_label}", bandwidth_gbps(num_bytes, elapsed), "GB/s"))

    elif bench_name == "npu_copy_overlap":
        eligible_sizes = [size for size in sizes if size <= 16 * 1024 * 1024]
        num_bytes = max(eligible_sizes) if eligible_sizes else min(sizes)
        elements = max(1, num_bytes // 4)
        first = torch.empty(elements, dtype=torch.float32)
        second = torch.empty(elements, dtype=torch.float32)

        def sequential():
            first.to(device)
            sync()
            second.to(device)

        def concurrent():
            stream_a = torch.npu.Stream()
            stream_b = torch.npu.Stream()
            with torch.npu.stream(stream_a):
                first.to(device, non_blocking=True)
            with torch.npu.stream(stream_b):
                second.to(device, non_blocking=True)

        sequential()
        sync()
        concurrent()
        sync()
        sequential_s = timed(sequential)
        concurrent_s = timed(concurrent)
        metrics.append(metric("copy_overlap_ratio", sequential_s / concurrent_s if concurrent_s else 0.0, "ratio"))
        metrics.append(metric("copy_overlap_sequential_ms", sequential_s * 1000, "ms"))
        metrics.append(metric("copy_overlap_concurrent_ms", concurrent_s * 1000, "ms"))

    elif bench_name == "npu_matmul_shape":
        for dim in (256, 512, 1024):
            left = torch.ones((dim, dim), dtype=torch.float16, device=device)
            right = torch.ones((dim, dim), dtype=torch.float16, device=device)

            def once():
                left @ right

            once()
            sync()
            repeat_count = max(1, min(5, int(duration_s)))
            elapsed = sum(timed(once) for _ in range(repeat_count)) / repeat_count
            metrics.append(metric(f"matmul_ms_{dim}x{dim}", elapsed * 1000, "ms"))

    else:
        blocked("invalid_input", f"unknown NPU bench: {bench_name}")

    emit({
        "status": "measurable",
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "blocked_reason": {"category": None, "detail": None},
        "metrics": metrics,
    })
except Exception as exc:
    blocked("runtime_error", f"{type(exc).__name__}: {exc}")
'''
    return (
        template.replace("__BENCH_NAME__", json.dumps(bench_name))
        .replace("__COPY_SIZES__", json.dumps(copy_sizes))
        .replace("__DURATION_S__", str(max(1, duration_s)))
    )


def _parse_json_payload(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        return json.loads(line)
    raise ValueError("no JSON payload found in stdout")


def _run_npu_python_bench(*, bench_name: str, copy_sizes: str, duration_s: int) -> dict[str, Any]:
    command = [sys.executable, "-c", _npu_bench_code(bench_name=bench_name, copy_sizes=copy_sizes, duration_s=duration_s)]
    display_command = f"{sys.executable} -c <{bench_name} torch-npu microbench>"
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(60, duration_s + 30),
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "blocked",
            "command": display_command,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "blocked_reason": _blocked_reason("timeout", f"{bench_name} timed out"),
            "metrics": [],
        }
    except OSError as exc:
        return {
            "status": "blocked",
            "command": display_command,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "blocked_reason": _blocked_reason("tool_missing", str(exc)),
            "metrics": [],
        }

    elapsed_ms = round((time.monotonic() - started) * 1000, 3)
    if result.returncode != 0:
        detail = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        return {
            "status": "blocked",
            "command": display_command,
            "duration_ms": elapsed_ms,
            "blocked_reason": _blocked_reason("runtime_error", detail[:500] or f"{bench_name} failed"),
            "metrics": [],
        }

    try:
        payload = _parse_json_payload(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        detail = "\n".join(part for part in [str(exc), result.stdout.strip(), result.stderr.strip()] if part)
        return {
            "status": "blocked",
            "command": display_command,
            "duration_ms": elapsed_ms,
            "blocked_reason": _blocked_reason("unknown", detail[:500]),
            "metrics": [],
        }

    status = payload.get("status", "blocked")
    if status not in {"measurable", "partial", "blocked"}:
        status = "blocked"
    return {
        "status": status,
        "command": display_command,
        "duration_ms": payload.get("duration_ms", elapsed_ms),
        "blocked_reason": payload.get("blocked_reason") or _blocked_reason(None, None),
        "metrics": payload.get("metrics", []),
    }


def _torch_npu_ready(
    *,
    python_executable: str | None = None,
    import_timeout_s: int = 30,
) -> dict[str, str | None]:
    try:
        importlib_metadata.version("torch-npu")
    except importlib_metadata.PackageNotFoundError:
        return _blocked_reason("tool_missing", "torch-npu package metadata is not installed")

    executable = python_executable or sys.executable
    command = [
        executable,
        "-c",
        "import sys; import torch_npu; print(sys.executable); print('torch_npu_import_ok')",
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=import_timeout_s)
    except subprocess.TimeoutExpired:
        return _blocked_reason(
            "timeout",
            f"torch-npu import with {executable} timed out after {import_timeout_s} seconds",
        )
    except OSError as exc:
        return _blocked_reason("tool_missing", str(exc))
    if result.returncode != 0:
        detail = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        return _blocked_reason("unknown", detail[:500] or f"torch-npu import failed with {executable}")
    return _blocked_reason(None, None)


def _record_npu_bench(
    *,
    run_dir: Path,
    bench_name: str,
    artifact_name: str,
    command: str,
    copy_sizes: str,
    duration_s: int,
    torch_block: dict[str, str | None],
) -> dict[str, Any]:
    if torch_block["category"] is not None:
        return _record_result(
            run_dir=run_dir,
            bench_name=bench_name,
            artifact_name=artifact_name,
            status="blocked",
            command=command,
            duration_ms=None,
            blocked_reason=torch_block,
        )
    result = _run_npu_python_bench(bench_name=bench_name, copy_sizes=copy_sizes, duration_s=duration_s)
    return _record_result(
        run_dir=run_dir,
        bench_name=bench_name,
        artifact_name=artifact_name,
        status=result["status"],
        command=result.get("command", command),
        duration_ms=result.get("duration_ms"),
        blocked_reason=result.get("blocked_reason", _blocked_reason(None, None)),
        metrics=result.get("metrics", []),
    )


def _run_cpu_kernel(run_dir: Path, duration_s: int) -> dict[str, Any]:
    started = time.monotonic()
    loops = 0
    target_s = max(0.05, min(duration_s, 1))
    while time.monotonic() - started < target_s:
        loops += sum(i * i for i in range(1000))
    elapsed = time.monotonic() - started
    duration_ms = round(elapsed * 1000, 3)
    return _record_result(
        run_dir=run_dir,
        bench_name="cpu_kernel",
        artifact_name="cpu_kernel.csv",
        status="measurable",
        command="python internal cpu loop",
        duration_ms=duration_ms,
        blocked_reason=_blocked_reason(None, None),
        metric_name="loop_score_per_s",
        metric_value=round(loops / elapsed, 3),
        unit="score/s",
    )


def _run_dram_bandwidth(run_dir: Path, duration_s: int) -> dict[str, Any]:
    started = time.monotonic()
    data = bytearray(16 * 1024 * 1024)
    passes = 0
    target_s = max(0.05, min(duration_s, 1))
    checksum = 0
    while time.monotonic() - started < target_s:
        checksum ^= sum(data)
        passes += 1
    elapsed = time.monotonic() - started
    gb_read = (len(data) * passes) / (1024**3)
    return _record_result(
        run_dir=run_dir,
        bench_name="dram_bandwidth",
        artifact_name="dram_bandwidth.csv",
        status="measurable",
        command="python internal bytearray scan",
        duration_ms=round(elapsed * 1000, 3),
        blocked_reason=_blocked_reason(None, None),
        metric_name="dram_read_gbps",
        metric_value=round(gb_read / elapsed, 3),
        unit="GB/s",
    )


def _record_tool_probe(
    *,
    run_dir: Path,
    bench_name: str,
    artifact_name: str,
    command_name: str,
    command_exists: CommandExists,
) -> dict[str, Any]:
    if not command_exists(command_name):
        return _record_result(
            run_dir=run_dir,
            bench_name=bench_name,
            artifact_name=artifact_name,
            status="blocked",
            command=[command_name, "--version"],
            duration_ms=None,
            blocked_reason=_blocked_reason("tool_missing", f"{command_name} is not available"),
        )
    return _record_result(
        run_dir=run_dir,
        bench_name=bench_name,
        artifact_name=artifact_name,
        status="partial",
        command=[command_name, "--version"],
        duration_ms=None,
        blocked_reason=_blocked_reason(None, None),
        metric_name="tool_available",
        metric_value=1,
        unit="bool",
    )


def _run_ssd_fio(
    *,
    run_dir: Path,
    scratch_dir: Path | None,
    fio_qdepth: str,
    duration_s: int,
    command_exists: CommandExists,
) -> dict[str, Any]:
    if scratch_dir is None:
        return _record_result(
            run_dir=run_dir,
            bench_name="ssd_fio",
            artifact_name="ssd_fio.csv",
            status="blocked",
            command="fio skipped because --scratch-dir was not provided",
            duration_ms=None,
            blocked_reason=_blocked_reason("scratch_missing", "--scratch-dir is required for SSD fio microbench"),
        )
    if not command_exists("fio"):
        return _record_result(
            run_dir=run_dir,
            bench_name="ssd_fio",
            artifact_name="ssd_fio.csv",
            status="blocked",
            command=["fio", "--version"],
            duration_ms=None,
            blocked_reason=_blocked_reason("tool_missing", "fio is not available"),
        )

    first_qdepth = fio_qdepth.split(",", 1)[0].strip() or "1"
    try:
        scratch_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _record_result(
            run_dir=run_dir,
            bench_name="ssd_fio",
            artifact_name="ssd_fio.csv",
            status="blocked",
            command=f"mkdir -p {scratch_dir}",
            duration_ms=None,
            blocked_reason=_blocked_reason("permission", str(exc)),
        )
    fio_file = scratch_dir / "ak_observability_fio.dat"
    command = [
        "fio",
        "--name=ak_observability",
        f"--filename={fio_file}",
        "--rw=randrw",
        "--bs=4k",
        "--size=64M",
        "--direct=1",
        f"--iodepth={first_qdepth}",
        f"--runtime={max(1, duration_s)}",
        "--time_based=1",
        "--output-format=json",
    ]
    started = time.monotonic()
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=max(5, duration_s + 10))
    except subprocess.TimeoutExpired:
        return _record_result(
            run_dir=run_dir,
            bench_name="ssd_fio",
            artifact_name="ssd_fio.csv",
            status="blocked",
            command=command,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            blocked_reason=_blocked_reason("timeout", "fio timed out"),
        )
    if result.returncode != 0:
        detail = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        return _record_result(
            run_dir=run_dir,
            bench_name="ssd_fio",
            artifact_name="ssd_fio.csv",
            status="blocked",
            command=command,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            blocked_reason=_blocked_reason("unknown", detail[:500] or "fio returned nonzero exit code"),
        )
    return _record_result(
        run_dir=run_dir,
        bench_name="ssd_fio",
        artifact_name="ssd_fio.csv",
        status="measurable",
        command=command,
        duration_ms=round((time.monotonic() - started) * 1000, 3),
        blocked_reason=_blocked_reason(None, None),
        metric_name="fio_completed",
        metric_value=1,
        unit="bool",
    )


def run_microbench_suite(
    *,
    run_dir: Path,
    scratch_dir: Path | None,
    copy_sizes: str,
    fio_qdepth: str,
    duration_s: int,
    command_exists: CommandExists = _default_command_exists,
) -> list[dict[str, Any]]:
    torch_block = _torch_npu_ready()
    results = [
        _record_npu_bench(
            run_dir=run_dir,
            bench_name="npu_copy_h2d",
            artifact_name="npu_copy_h2d.csv",
            command=f"torch-npu H2D copy sizes={copy_sizes}",
            copy_sizes=copy_sizes,
            duration_s=duration_s,
            torch_block=torch_block,
        ),
        _record_npu_bench(
            run_dir=run_dir,
            bench_name="npu_copy_d2h",
            artifact_name="npu_copy_d2h.csv",
            command=f"torch-npu D2H copy sizes={copy_sizes}",
            copy_sizes=copy_sizes,
            duration_s=duration_s,
            torch_block=torch_block,
        ),
        _record_npu_bench(
            run_dir=run_dir,
            bench_name="npu_copy_overlap",
            artifact_name="npu_copy_overlap.csv",
            command=f"torch-npu copy overlap sizes={copy_sizes}",
            copy_sizes=copy_sizes,
            duration_s=duration_s,
            torch_block=torch_block,
        ),
        _record_npu_bench(
            run_dir=run_dir,
            bench_name="npu_matmul_shape",
            artifact_name="npu_matmul_shape.csv",
            command="torch-npu matmul shape sweep",
            copy_sizes=copy_sizes,
            duration_s=duration_s,
            torch_block=torch_block,
        ),
        _run_cpu_kernel(run_dir, duration_s),
        _record_tool_probe(
            run_dir=run_dir,
            bench_name="cpu_perf",
            artifact_name="cpu_perf.csv",
            command_name="perf",
            command_exists=command_exists,
        ),
        _run_dram_bandwidth(run_dir, duration_s),
        _record_tool_probe(
            run_dir=run_dir,
            bench_name="numa_topology",
            artifact_name="numa_topology.csv",
            command_name="numactl",
            command_exists=command_exists,
        ),
        _run_ssd_fio(
            run_dir=run_dir,
            scratch_dir=scratch_dir,
            fio_qdepth=fio_qdepth,
            duration_s=duration_s,
            command_exists=command_exists,
        ),
    ]
    return results
