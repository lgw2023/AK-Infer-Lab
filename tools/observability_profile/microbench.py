from __future__ import annotations

import csv
import importlib.metadata as importlib_metadata
import shutil
import subprocess
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
) -> dict[str, Any]:
    artifact_path = Path("microbench") / artifact_name
    row = {
        "bench_name": bench_name,
        "status": status,
        "command": _command_text(command),
        "artifact_path": str(artifact_path),
        "duration_ms": duration_ms,
        "blocked_category": blocked_reason["category"],
        "blocked_detail": blocked_reason["detail"],
        "metric_name": metric_name,
        "metric_value": metric_value,
        "unit": unit,
    }
    _write_result_csv(run_dir / artifact_path, [row])
    return {
        "bench_name": bench_name,
        "status": status,
        "command": command,
        "artifact_path": str(artifact_path),
        "duration_ms": duration_ms,
        "blocked_reason": blocked_reason,
    }


def _torch_npu_ready() -> dict[str, str | None]:
    try:
        importlib_metadata.version("torch-npu")
    except importlib_metadata.PackageNotFoundError:
        return _blocked_reason("tool_missing", "torch-npu package metadata is not installed")

    command = ["python", "-c", "import torch_npu; print('torch_npu_import_ok')"]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)
    except subprocess.TimeoutExpired:
        return _blocked_reason("timeout", "torch-npu import timed out after 5 seconds")
    except OSError as exc:
        return _blocked_reason("tool_missing", str(exc))
    if result.returncode != 0:
        detail = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        return _blocked_reason("unknown", detail[:500] or "torch-npu import failed")
    return _blocked_reason(None, None)


def _record_npu_bench(
    *,
    run_dir: Path,
    bench_name: str,
    artifact_name: str,
    command: str,
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
    return _record_result(
        run_dir=run_dir,
        bench_name=bench_name,
        artifact_name=artifact_name,
        status="partial",
        command=command,
        duration_ms=None,
        blocked_reason=_blocked_reason(None, None),
        metric_name="torch_npu_initialization",
        metric_value="ok",
        unit="status",
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
            torch_block=torch_block,
        ),
        _record_npu_bench(
            run_dir=run_dir,
            bench_name="npu_copy_d2h",
            artifact_name="npu_copy_d2h.csv",
            command=f"torch-npu D2H copy sizes={copy_sizes}",
            torch_block=torch_block,
        ),
        _record_npu_bench(
            run_dir=run_dir,
            bench_name="npu_copy_overlap",
            artifact_name="npu_copy_overlap.csv",
            command=f"torch-npu copy overlap sizes={copy_sizes}",
            torch_block=torch_block,
        ),
        _record_npu_bench(
            run_dir=run_dir,
            bench_name="npu_matmul_shape",
            artifact_name="npu_matmul_shape.csv",
            command="torch-npu matmul shape sweep",
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
