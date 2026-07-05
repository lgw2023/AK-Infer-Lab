from __future__ import annotations

import csv
import importlib.metadata as importlib_metadata
import json
import re
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


def _metric(metric_name: str, metric_value: str | float | int, unit: str) -> dict[str, Any]:
    return {"metric_name": metric_name, "metric_value": metric_value, "unit": unit}


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text.startswith("<"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _round_metric(value: float) -> float:
    return round(value, 6)


def _fio_percentile_us(section: dict[str, Any], percentile: float) -> float | None:
    latency = section.get("clat_ns") or section.get("lat_ns") or {}
    percentiles = latency.get("percentile") if isinstance(latency, dict) else None
    if not isinstance(percentiles, dict):
        return None
    for key, value in percentiles.items():
        key_value = _to_float(key)
        if key_value is None or abs(key_value - percentile) > 0.0001:
            continue
        raw_value = _to_float(value)
        return None if raw_value is None else raw_value / 1000
    return None


def _fio_mean_latency_us(section: dict[str, Any]) -> float | None:
    latency = section.get("clat_ns") or section.get("lat_ns") or {}
    if not isinstance(latency, dict):
        return None
    raw_value = _to_float(latency.get("mean"))
    return None if raw_value is None else raw_value / 1000


def _parse_fio_json_metrics(stdout: str) -> list[dict[str, Any]]:
    payload = json.loads(stdout)
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("fio JSON does not contain a jobs list")

    direction_totals: dict[str, dict[str, float | None]] = {
        "read": {"iops": None, "bw_bytes": None},
        "write": {"iops": None, "bw_bytes": None},
    }
    latency_values: dict[str, dict[str, list[float]]] = {
        "read": {"mean": [], "p95": [], "p99": []},
        "write": {"mean": [], "p95": [], "p99": []},
    }

    for job in jobs:
        if not isinstance(job, dict):
            continue
        for direction in ("read", "write"):
            section = job.get(direction)
            if not isinstance(section, dict):
                continue
            iops = _to_float(section.get("iops"))
            if iops is not None:
                current = direction_totals[direction]["iops"] or 0.0
                direction_totals[direction]["iops"] = current + iops
            bw_bytes = _to_float(section.get("bw_bytes"))
            if bw_bytes is not None:
                current = direction_totals[direction]["bw_bytes"] or 0.0
                direction_totals[direction]["bw_bytes"] = current + bw_bytes
            mean_us = _fio_mean_latency_us(section)
            if mean_us is not None:
                latency_values[direction]["mean"].append(mean_us)
            p95_us = _fio_percentile_us(section, 95.0)
            if p95_us is not None:
                latency_values[direction]["p95"].append(p95_us)
            p99_us = _fio_percentile_us(section, 99.0)
            if p99_us is not None:
                latency_values[direction]["p99"].append(p99_us)

    metrics: list[dict[str, Any]] = []
    total_iops = 0.0
    total_bw_bytes = 0.0
    saw_iops = False
    saw_bw = False
    for direction in ("read", "write"):
        iops = direction_totals[direction]["iops"]
        if iops is not None:
            saw_iops = True
            total_iops += iops
            metrics.append(_metric(f"fio_{direction}_iops", _round_metric(iops), "IOPS"))
        bw_bytes = direction_totals[direction]["bw_bytes"]
        if bw_bytes is not None:
            saw_bw = True
            total_bw_bytes += bw_bytes
            metrics.append(_metric(f"fio_{direction}_bw_mib_s", _round_metric(bw_bytes / (1024**2)), "MiB/s"))
        for label, unit_name in (("mean", "mean"), ("p95", "p95"), ("p99", "p99")):
            values = latency_values[direction][label]
            if values:
                metrics.append(
                    _metric(
                        f"fio_{direction}_clat_{unit_name}_us",
                        _round_metric(sum(values) / len(values)),
                        "us",
                    )
                )
    if saw_iops:
        metrics.append(_metric("fio_total_iops", _round_metric(total_iops), "IOPS"))
    if saw_bw:
        metrics.append(_metric("fio_total_bw_mib_s", _round_metric(total_bw_bytes / (1024**2)), "MiB/s"))
    if not metrics:
        raise ValueError("fio JSON did not contain parseable read/write metrics")
    return metrics


def _cpu_perf_code(duration_s: int) -> str:
    seconds = max(0.05, min(duration_s, 3))
    return (
        "import time\n"
        f"end = time.perf_counter() + {seconds!r}\n"
        "value = 0\n"
        "while time.perf_counter() < end:\n"
        "    for i in range(1000):\n"
        "        value += i * i\n"
        "print(value)\n"
    )


def _perf_metric_from_event(event: str, value: float, unit: str) -> dict[str, Any] | None:
    event = event.strip().split(":")[0]
    unit = unit.strip().lower()
    if event in {"task-clock", "cpu-clock"}:
        if unit in {"sec", "secs", "second", "seconds"}:
            value *= 1000
        elif unit in {"usec", "us"}:
            value /= 1000
        elif unit in {"nsec", "ns"}:
            value /= 1_000_000
        return _metric("perf_task_clock_ms", _round_metric(value), "ms")
    if event == "cycles":
        return _metric("perf_cycles", int(value), "count")
    if event == "instructions":
        return _metric("perf_instructions", int(value), "count")
    if event == "context-switches":
        return _metric("perf_context_switches", int(value), "count")
    return None


def _parse_perf_stat_metrics(output: str) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        metric: dict[str, Any] | None = None
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 3:
            value = _to_float(parts[0])
            if value is not None:
                metric = _perf_metric_from_event(parts[2], value, parts[1])
        if metric is None:
            tokens = line.split()
            if len(tokens) >= 2:
                value = _to_float(tokens[0])
                if value is not None:
                    if len(tokens) >= 3 and tokens[1].lower() in {"msec", "ms", "sec", "secs", "seconds", "usec", "us"}:
                        metric = _perf_metric_from_event(tokens[2], value, tokens[1])
                    else:
                        metric = _perf_metric_from_event(tokens[1], value, "")
        if metric is not None:
            by_name[metric["metric_name"]] = metric

    cycles = by_name.get("perf_cycles")
    instructions = by_name.get("perf_instructions")
    if cycles and instructions:
        cycle_count = _to_float(cycles["metric_value"])
        instruction_count = _to_float(instructions["metric_value"])
        if cycle_count and instruction_count is not None:
            by_name["perf_ipc"] = _metric("perf_ipc", _round_metric(instruction_count / cycle_count), "instructions/cycle")
    return list(by_name.values())


def _perf_failure_category(output: str) -> str:
    lowered = output.lower()
    if "permission" in lowered or "not permitted" in lowered or "access" in lowered:
        return "permission"
    if "not supported" in lowered:
        return "unsupported"
    return "unknown"


def _run_cpu_perf(
    *,
    run_dir: Path,
    duration_s: int,
    command_exists: CommandExists,
) -> dict[str, Any]:
    if not command_exists("perf"):
        return _record_result(
            run_dir=run_dir,
            bench_name="cpu_perf",
            artifact_name="cpu_perf.csv",
            status="blocked",
            command=["perf", "--version"],
            duration_ms=None,
            blocked_reason=_blocked_reason("tool_missing", "perf is not available"),
        )

    command = [
        "perf",
        "stat",
        "-x",
        ",",
        "-e",
        "task-clock,cycles,instructions",
        "--",
        sys.executable,
        "-c",
        _cpu_perf_code(duration_s),
    ]
    started = time.monotonic()
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=max(10, duration_s + 10))
    except subprocess.TimeoutExpired:
        return _record_result(
            run_dir=run_dir,
            bench_name="cpu_perf",
            artifact_name="cpu_perf.csv",
            status="blocked",
            command=command,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            blocked_reason=_blocked_reason("timeout", "perf stat timed out"),
        )
    except OSError as exc:
        return _record_result(
            run_dir=run_dir,
            bench_name="cpu_perf",
            artifact_name="cpu_perf.csv",
            status="blocked",
            command=command,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            blocked_reason=_blocked_reason("tool_missing", str(exc)),
        )

    duration_ms = round((time.monotonic() - started) * 1000, 3)
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    metrics = _parse_perf_stat_metrics(output)
    if result.returncode != 0 and not metrics:
        primary_detail = output[:500] or "perf stat returned nonzero"
        fallback_command = list(command)
        fallback_command[fallback_command.index("-e") + 1] = "task-clock"
        fallback_started = time.monotonic()
        try:
            fallback_result = subprocess.run(
                fallback_command,
                check=False,
                capture_output=True,
                text=True,
                timeout=max(10, duration_s + 10),
            )
        except subprocess.TimeoutExpired:
            return _record_result(
                run_dir=run_dir,
                bench_name="cpu_perf",
                artifact_name="cpu_perf.csv",
                status="blocked",
                command=fallback_command,
                duration_ms=round((time.monotonic() - fallback_started) * 1000, 3),
                blocked_reason=_blocked_reason("timeout", f"{primary_detail}\nfallback task-clock timed out"),
            )
        except OSError as exc:
            return _record_result(
                run_dir=run_dir,
                bench_name="cpu_perf",
                artifact_name="cpu_perf.csv",
                status="blocked",
                command=fallback_command,
                duration_ms=round((time.monotonic() - fallback_started) * 1000, 3),
                blocked_reason=_blocked_reason("tool_missing", f"{primary_detail}\n{exc}"),
            )
        fallback_duration_ms = round((time.monotonic() - fallback_started) * 1000, 3)
        fallback_output = "\n".join(
            part for part in [fallback_result.stdout.strip(), fallback_result.stderr.strip()] if part
        )
        fallback_metrics = _parse_perf_stat_metrics(fallback_output)
        if fallback_result.returncode == 0 and fallback_metrics:
            return _record_result(
                run_dir=run_dir,
                bench_name="cpu_perf",
                artifact_name="cpu_perf.csv",
                status="partial",
                command=fallback_command,
                duration_ms=fallback_duration_ms,
                blocked_reason=_blocked_reason(_perf_failure_category(primary_detail), primary_detail),
                metrics=fallback_metrics,
            )
        output = "\n".join(part for part in [primary_detail, fallback_output[:500]] if part)
        metrics = fallback_metrics
    if result.returncode != 0:
        if metrics:
            return _record_result(
                run_dir=run_dir,
                bench_name="cpu_perf",
                artifact_name="cpu_perf.csv",
                status="partial",
                command=command,
                duration_ms=duration_ms,
                blocked_reason=_blocked_reason(_perf_failure_category(output), output[:500]),
                metrics=metrics,
            )
        return _record_result(
            run_dir=run_dir,
            bench_name="cpu_perf",
            artifact_name="cpu_perf.csv",
            status="blocked",
            command=command,
            duration_ms=duration_ms,
            blocked_reason=_blocked_reason(_perf_failure_category(output), output[:500] or "perf stat returned nonzero"),
        )
    if not metrics:
        return _record_result(
            run_dir=run_dir,
            bench_name="cpu_perf",
            artifact_name="cpu_perf.csv",
            status="blocked",
            command=command,
            duration_ms=duration_ms,
            blocked_reason=_blocked_reason("unknown", output[:500] or "perf stat produced no parseable metrics"),
        )
    return _record_result(
        run_dir=run_dir,
        bench_name="cpu_perf",
        artifact_name="cpu_perf.csv",
        status="measurable",
        command=command,
        duration_ms=duration_ms,
        blocked_reason=_blocked_reason(None, None),
        metrics=metrics,
    )


def _parse_numactl_hardware_metrics(output: str) -> list[dict[str, Any]]:
    nodes: dict[int, dict[str, Any]] = {}
    node_count: int | None = None
    distance_header: list[int] = []
    distances: list[tuple[int, int, int]] = []
    in_distances = False

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        available = re.search(r"available:\s+(\d+)\s+nodes", line)
        if available:
            node_count = int(available.group(1))
            continue
        cpus = re.match(r"node\s+(\d+)\s+cpus:\s*(.*)$", line)
        if cpus:
            node_id = int(cpus.group(1))
            nodes.setdefault(node_id, {})["cpus"] = " ".join(cpus.group(2).split())
            continue
        size = re.match(r"node\s+(\d+)\s+size:\s+(\d+)\s+MB", line)
        if size:
            nodes.setdefault(int(size.group(1)), {})["memory_mb"] = int(size.group(2))
            continue
        free = re.match(r"node\s+(\d+)\s+free:\s+(\d+)\s+MB", line)
        if free:
            nodes.setdefault(int(free.group(1)), {})["free_mb"] = int(free.group(2))
            continue
        if line.startswith("node distances"):
            in_distances = True
            continue
        if not in_distances:
            continue
        if line.startswith("node"):
            distance_header = [int(value) for value in re.findall(r"\d+", line)]
            continue
        row = re.match(r"(\d+):\s*(.*)$", line)
        if row and distance_header:
            source_node = int(row.group(1))
            values = [int(value) for value in re.findall(r"\d+", row.group(2))]
            for target_node, distance in zip(distance_header, values):
                distances.append((source_node, target_node, distance))

    if node_count is None and nodes:
        node_count = len(nodes)

    metrics: list[dict[str, Any]] = []
    if node_count is not None:
        metrics.append(_metric("numa_node_count", node_count, "count"))
    if nodes:
        metrics.append(_metric("numa_node_ids", ",".join(str(node_id) for node_id in sorted(nodes)), "text"))
    for node_id, node in sorted(nodes.items()):
        cpus_value = node.get("cpus", "")
        if cpus_value:
            metrics.append(_metric(f"numa_node_{node_id}_cpus", cpus_value, "text"))
            metrics.append(_metric(f"numa_node_{node_id}_cpu_count", len(cpus_value.split()), "count"))
        if "memory_mb" in node:
            metrics.append(_metric(f"numa_node_{node_id}_memory_mb", node["memory_mb"], "MB"))
        if "free_mb" in node:
            metrics.append(_metric(f"numa_node_{node_id}_free_mb", node["free_mb"], "MB"))
    for source_node, target_node, distance in distances:
        metrics.append(_metric(f"numa_distance_{source_node}_{target_node}", distance, "distance"))
    if not metrics:
        raise ValueError("numactl --hardware output did not contain parseable topology metrics")
    return metrics


def _run_numa_topology(
    *,
    run_dir: Path,
    command_exists: CommandExists,
) -> dict[str, Any]:
    command = ["numactl", "--hardware"]
    if not command_exists("numactl"):
        return _record_result(
            run_dir=run_dir,
            bench_name="numa_topology",
            artifact_name="numa_topology.csv",
            status="blocked",
            command=command,
            duration_ms=None,
            blocked_reason=_blocked_reason("tool_missing", "numactl is not available"),
        )
    started = time.monotonic()
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return _record_result(
            run_dir=run_dir,
            bench_name="numa_topology",
            artifact_name="numa_topology.csv",
            status="blocked",
            command=command,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            blocked_reason=_blocked_reason("timeout", "numactl --hardware timed out"),
        )
    except OSError as exc:
        return _record_result(
            run_dir=run_dir,
            bench_name="numa_topology",
            artifact_name="numa_topology.csv",
            status="blocked",
            command=command,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            blocked_reason=_blocked_reason("tool_missing", str(exc)),
        )
    duration_ms = round((time.monotonic() - started) * 1000, 3)
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    if result.returncode != 0:
        return _record_result(
            run_dir=run_dir,
            bench_name="numa_topology",
            artifact_name="numa_topology.csv",
            status="blocked",
            command=command,
            duration_ms=duration_ms,
            blocked_reason=_blocked_reason("unknown", output[:500] or "numactl --hardware returned nonzero"),
        )
    try:
        metrics = _parse_numactl_hardware_metrics(output)
    except ValueError as exc:
        return _record_result(
            run_dir=run_dir,
            bench_name="numa_topology",
            artifact_name="numa_topology.csv",
            status="blocked",
            command=command,
            duration_ms=duration_ms,
            blocked_reason=_blocked_reason("unknown", str(exc)),
        )
    return _record_result(
        run_dir=run_dir,
        bench_name="numa_topology",
        artifact_name="numa_topology.csv",
        status="measurable",
        command=command,
        duration_ms=duration_ms,
        blocked_reason=_blocked_reason(None, None),
        metrics=metrics,
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
    try:
        metrics = _parse_fio_json_metrics(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        detail = "\n".join(part for part in [str(exc), result.stdout.strip(), result.stderr.strip()] if part)
        return _record_result(
            run_dir=run_dir,
            bench_name="ssd_fio",
            artifact_name="ssd_fio.csv",
            status="blocked",
            command=command,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            blocked_reason=_blocked_reason("unknown", detail[:500]),
        )
    return _record_result(
        run_dir=run_dir,
        bench_name="ssd_fio",
        artifact_name="ssd_fio.csv",
        status="measurable",
        command=command,
        duration_ms=round((time.monotonic() - started) * 1000, 3),
        blocked_reason=_blocked_reason(None, None),
        metrics=metrics,
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
        _run_cpu_perf(
            run_dir=run_dir,
            duration_s=duration_s,
            command_exists=command_exists,
        ),
        _run_dram_bandwidth(run_dir, duration_s),
        _run_numa_topology(
            run_dir=run_dir,
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
