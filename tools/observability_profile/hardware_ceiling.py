from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from statistics import median
from typing import Any

from tools.observability_profile.microbench import _parse_fio_json_metrics


MAIL_LIMIT_BYTES = 70 * 1024


def parse_size_bytes(token: str) -> int:
    text = token.strip().upper()
    if not text:
        raise ValueError("empty size token")
    multiplier = 1
    if text[-1] in {"K", "M", "G"}:
        multiplier = {"K": 1024, "M": 1024**2, "G": 1024**3}[text[-1]]
        text = text[:-1]
    value = float(text)
    if value <= 0:
        raise ValueError(f"size must be positive: {token}")
    return int(value * multiplier)


def parse_csv_list(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def label_size(num_bytes: int) -> str:
    for suffix, factor in (("G", 1024**3), ("M", 1024**2), ("K", 1024)):
        if num_bytes >= factor and num_bytes % factor == 0:
            return f"{num_bytes // factor}{suffix}"
    return f"{num_bytes}B"


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _status_row(bench: str, status: str, error: str = "") -> dict[str, Any]:
    return {"bench": bench, "status": status, "error": error}


NPU_SWEEP_CODE = r"""
import json
import sys
import time
from statistics import median


def emit(payload):
    print(json.dumps(payload, sort_keys=True))
    raise SystemExit(0)


def parse_dtype(torch, name):
    mapping = {
        "float16": torch.float16,
        "fp16": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }
    if name not in mapping:
        raise ValueError(f"unsupported dtype: {name}")
    return mapping[name]


def sync(torch):
    torch.npu.synchronize()


def timed(torch, fn, reps):
    values = []
    for _ in range(reps):
        started = time.perf_counter()
        fn()
        sync(torch)
        values.append(time.perf_counter() - started)
    return values


config = json.loads(sys.argv[1])
copy_sizes = config["copy_sizes"]
matmul_dims = config["matmul_dims"]
matmul_dtypes = config["matmul_dtypes"]
copy_repeats = int(config["copy_repeats"])
matmul_repeats = int(config["matmul_repeats"])
device = config["npu_device"]

rows_copy = []
rows_matmul = []

try:
    import torch
    import torch_npu  # noqa: F401

    if not torch.npu.is_available() or torch.npu.device_count() < 1:
        emit({"status": "blocked", "error": "torch.npu reports no visible NPU", "copy": [], "matmul": []})

    torch.npu.set_device(device)

    for num_bytes in copy_sizes:
        elements = max(1, num_bytes // 4)
        for pinned in (False, True):
            try:
                cpu_src = torch.empty(elements, dtype=torch.float32)
                cpu_dst = torch.empty(elements, dtype=torch.float32)
                if pinned:
                    cpu_src = cpu_src.pin_memory()
                    cpu_dst = cpu_dst.pin_memory()
                npu_src = torch.empty(elements, dtype=torch.float32, device=device)
                npu_dst = torch.empty(elements, dtype=torch.float32, device=device)
            except Exception as exc:
                for direction in ("h2d", "d2h"):
                    rows_copy.append({
                        "bench": "npu_copy",
                        "direction": direction,
                        "bytes": num_bytes,
                        "size_label": config["size_labels"][str(num_bytes)],
                        "host_pinned": int(pinned),
                        "non_blocking": "",
                        "repetitions": 0,
                        "status": "blocked",
                        "min_ms": "",
                        "median_ms": "",
                        "best_gbps": "",
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                continue

            for non_blocking in (False, True):
                def h2d_once():
                    npu_dst.copy_(cpu_src, non_blocking=non_blocking)

                def d2h_once():
                    cpu_dst.copy_(npu_src, non_blocking=non_blocking)

                for direction, fn in (("h2d", h2d_once), ("d2h", d2h_once)):
                    try:
                        fn()
                        sync(torch)
                        values = timed(torch, fn, copy_repeats)
                        best = min(values)
                        rows_copy.append({
                            "bench": "npu_copy",
                            "direction": direction,
                            "bytes": num_bytes,
                            "size_label": config["size_labels"][str(num_bytes)],
                            "host_pinned": int(pinned),
                            "non_blocking": int(non_blocking),
                            "repetitions": copy_repeats,
                            "status": "measurable",
                            "min_ms": round(best * 1000, 6),
                            "median_ms": round(median(values) * 1000, 6),
                            "best_gbps": round(num_bytes / best / (1024 ** 3), 6) if best > 0 else 0.0,
                            "error": "",
                        })
                    except Exception as exc:
                        rows_copy.append({
                            "bench": "npu_copy",
                            "direction": direction,
                            "bytes": num_bytes,
                            "size_label": config["size_labels"][str(num_bytes)],
                            "host_pinned": int(pinned),
                            "non_blocking": int(non_blocking),
                            "repetitions": 0,
                            "status": "blocked",
                            "min_ms": "",
                            "median_ms": "",
                            "best_gbps": "",
                            "error": f"{type(exc).__name__}: {exc}",
                        })

    for dtype_name in matmul_dtypes:
        try:
            dtype = parse_dtype(torch, dtype_name)
        except Exception as exc:
            for dim in matmul_dims:
                rows_matmul.append({
                    "bench": "npu_matmul",
                    "dtype": dtype_name,
                    "m": dim,
                    "n": dim,
                    "k": dim,
                    "repetitions": 0,
                    "status": "blocked",
                    "min_ms": "",
                    "median_ms": "",
                    "tflops": "",
                    "error": f"{type(exc).__name__}: {exc}",
                })
            continue
        for dim in matmul_dims:
            try:
                left = torch.randn((dim, dim), dtype=dtype, device=device)
                right = torch.randn((dim, dim), dtype=dtype, device=device)

                def once():
                    left @ right

                once()
                sync(torch)
                reps = max(1, min(matmul_repeats, 5 if dim <= 2048 else 3 if dim <= 4096 else 1))
                values = timed(torch, once, reps)
                best = min(values)
                flops = 2 * dim * dim * dim
                rows_matmul.append({
                    "bench": "npu_matmul",
                    "dtype": dtype_name,
                    "m": dim,
                    "n": dim,
                    "k": dim,
                    "repetitions": reps,
                    "status": "measurable",
                    "min_ms": round(best * 1000, 6),
                    "median_ms": round(median(values) * 1000, 6),
                    "tflops": round(flops / best / 1e12, 6) if best > 0 else 0.0,
                    "error": "",
                })
            except Exception as exc:
                rows_matmul.append({
                    "bench": "npu_matmul",
                    "dtype": dtype_name,
                    "m": dim,
                    "n": dim,
                    "k": dim,
                    "repetitions": 0,
                    "status": "blocked",
                    "min_ms": "",
                    "median_ms": "",
                    "tflops": "",
                    "error": f"{type(exc).__name__}: {exc}",
                })

    emit({"status": "success", "error": "", "copy": rows_copy, "matmul": rows_matmul})
except Exception as exc:
    emit({"status": "blocked", "error": f"{type(exc).__name__}: {exc}", "copy": rows_copy, "matmul": rows_matmul})
"""


def run_npu_sweeps(
    *,
    python_bin: str,
    npu_device: str,
    copy_sizes: list[int],
    matmul_dims: list[int],
    matmul_dtypes: list[str],
    copy_repeats: int,
    matmul_repeats: int,
    timeout_s: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    config = {
        "npu_device": npu_device,
        "copy_sizes": copy_sizes,
        "size_labels": {str(size): label_size(size) for size in copy_sizes},
        "matmul_dims": matmul_dims,
        "matmul_dtypes": matmul_dtypes,
        "copy_repeats": copy_repeats,
        "matmul_repeats": matmul_repeats,
    }
    command = [python_bin, "-c", NPU_SWEEP_CODE, json.dumps(config)]
    started = time.monotonic()
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        meta = {
            "status": "blocked",
            "error": f"NPU sweep timed out after {timeout_s} seconds",
            "duration_sec": _round(time.monotonic() - started),
        }
        return ([_status_row("npu_copy", "blocked", meta["error"])], [_status_row("npu_matmul", "blocked", meta["error"])], meta)
    except OSError as exc:
        meta = {"status": "blocked", "error": str(exc), "duration_sec": _round(time.monotonic() - started)}
        return ([_status_row("npu_copy", "blocked", meta["error"])], [_status_row("npu_matmul", "blocked", meta["error"])], meta)

    duration = _round(time.monotonic() - started)
    payload = None
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            payload = json.loads(line)
            break
    if result.returncode != 0 or payload is None:
        detail = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        meta = {"status": "blocked", "error": detail[:1000] or "NPU sweep failed", "duration_sec": duration}
        return ([_status_row("npu_copy", "blocked", meta["error"])], [_status_row("npu_matmul", "blocked", meta["error"])], meta)

    payload["duration_sec"] = duration
    return payload.get("copy", []), payload.get("matmul", []), payload


def run_cpu_dram_sweep(*, sizes: list[int], repeats: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    started = time.monotonic()
    try:
        import numpy as np
    except Exception as exc:
        return ([_status_row("cpu_dram_numpy", "blocked", f"{type(exc).__name__}: {exc}")], {"status": "blocked"})

    for num_bytes in sizes:
        elements = max(1, num_bytes // 8)
        try:
            source = np.ones(elements, dtype=np.float64)
            dest = np.empty_like(source)
            read_values: list[float] = []
            copy_values: list[float] = []
            for _ in range(repeats):
                t0 = time.perf_counter()
                checksum = float(source.sum())
                t1 = time.perf_counter()
                np.copyto(dest, source)
                t2 = time.perf_counter()
                if checksum < 0:
                    raise RuntimeError("unreachable checksum guard")
                read_values.append(t1 - t0)
                copy_values.append(t2 - t1)
            read_best = min(read_values)
            copy_best = min(copy_values)
            rows.append(
                {
                    "bench": "cpu_dram_numpy",
                    "bytes": num_bytes,
                    "size_label": label_size(num_bytes),
                    "repetitions": repeats,
                    "status": "measurable",
                    "read_best_gbps": _round(num_bytes / read_best / (1024**3)),
                    "copy_best_gbps": _round(num_bytes / copy_best / (1024**3)),
                    "read_min_ms": _round(read_best * 1000),
                    "copy_min_ms": _round(copy_best * 1000),
                    "error": "",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "bench": "cpu_dram_numpy",
                    "bytes": num_bytes,
                    "size_label": label_size(num_bytes),
                    "repetitions": 0,
                    "status": "blocked",
                    "read_best_gbps": "",
                    "copy_best_gbps": "",
                    "read_min_ms": "",
                    "copy_min_ms": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return rows, {"status": "success", "duration_sec": _round(time.monotonic() - started)}


def _metrics_to_map(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    return {str(metric["metric_name"]): metric.get("metric_value") for metric in metrics}


def run_fio_sweep(
    *,
    scratch_dir: Path,
    block_sizes: list[str],
    queue_depths: list[str],
    rw_modes: list[str],
    runtime_s: int,
    size: str,
    timeout_padding_s: int = 30,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    started = time.monotonic()
    if shutil.which("fio") is None:
        return ([_status_row("ssd_fio_sweep", "blocked", "fio is not available")], {"status": "blocked"})
    try:
        scratch_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ([_status_row("ssd_fio_sweep", "blocked", str(exc))], {"status": "blocked"})

    for rw_mode in rw_modes:
        for block_size in block_sizes:
            for queue_depth in queue_depths:
                fio_file = scratch_dir / f"ak_ceiling_{rw_mode}_{block_size}_qd{queue_depth}.dat"
                command = [
                    "fio",
                    "--name=ak_hardware_ceiling",
                    f"--filename={fio_file}",
                    f"--rw={rw_mode}",
                    f"--bs={block_size}",
                    f"--iodepth={queue_depth}",
                    f"--size={size}",
                    "--direct=1",
                    f"--runtime={runtime_s}",
                    "--time_based=1",
                    "--output-format=json",
                ]
                row = {
                    "bench": "ssd_fio_sweep",
                    "rw": rw_mode,
                    "bs": block_size,
                    "iodepth": queue_depth,
                    "runtime_s": runtime_s,
                    "size": size,
                    "status": "blocked",
                    "fio_read_iops": "",
                    "fio_write_iops": "",
                    "fio_total_iops": "",
                    "fio_read_bw_mib_s": "",
                    "fio_write_bw_mib_s": "",
                    "fio_total_bw_mib_s": "",
                    "fio_read_clat_p95_us": "",
                    "fio_write_clat_p95_us": "",
                    "error": "",
                }
                try:
                    result = subprocess.run(
                        command,
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=runtime_s + timeout_padding_s,
                    )
                    if result.returncode != 0:
                        row["error"] = (result.stderr or result.stdout or "fio returned nonzero")[:1000]
                    else:
                        metrics = _metrics_to_map(_parse_fio_json_metrics(result.stdout))
                        row.update({name: metrics.get(name, "") for name in row if name.startswith("fio_")})
                        row["status"] = "measurable"
                except subprocess.TimeoutExpired:
                    row["error"] = f"fio timed out after {runtime_s + timeout_padding_s} seconds"
                except Exception as exc:
                    row["error"] = f"{type(exc).__name__}: {exc}"
                rows.append(row)
    return rows, {"status": "success", "duration_sec": _round(time.monotonic() - started)}


def _peak(rows: list[dict[str, Any]], field: str, **filters: Any) -> float | None:
    values = []
    for row in rows:
        if any(str(row.get(key)) != str(value) for key, value in filters.items()):
            continue
        try:
            values.append(float(row.get(field)))
        except (TypeError, ValueError):
            continue
    return max(values) if values else None


def build_summary(
    *,
    run_id: str,
    copy_rows: list[dict[str, Any]],
    matmul_rows: list[dict[str, Any]],
    dram_rows: list[dict[str, Any]],
    fio_rows: list[dict[str, Any]],
    result: dict[str, Any],
) -> str:
    lines = [
        f"# Hardware Ceiling Sweep Summary",
        "",
        f"run_id={run_id}",
        f"overall_status={result['overall_status']}",
        "policy=hardware_microbench_only_no_model_inference_no_bottleneck_claim",
        "",
        "## peak_readout",
        f"h2d_best_gbps={_peak(copy_rows, 'best_gbps', direction='h2d')}",
        f"d2h_best_gbps={_peak(copy_rows, 'best_gbps', direction='d2h')}",
        f"matmul_best_tflops={_peak(matmul_rows, 'tflops')}",
        f"dram_read_best_gbps={_peak(dram_rows, 'read_best_gbps')}",
        f"dram_copy_best_gbps={_peak(dram_rows, 'copy_best_gbps')}",
        f"fio_read_best_mib_s={_peak(fio_rows, 'fio_read_bw_mib_s')}",
        f"fio_write_best_mib_s={_peak(fio_rows, 'fio_write_bw_mib_s')}",
        "",
        "## row_counts",
        f"copy_rows={len(copy_rows)}",
        f"matmul_rows={len(matmul_rows)}",
        f"dram_rows={len(dram_rows)}",
        f"fio_rows={len(fio_rows)}",
        "",
        "## boundary",
        "This is a synthetic hardware ceiling sweep. It does not run model inference,",
        "does not claim production benchmark throughput, and does not perform bottleneck attribution.",
    ]
    return "\n".join(lines) + "\n"


def write_mail_candidates(artifact_dir: Path, paths: list[Path]) -> None:
    lines = ["path\tsize_bytes\tmail_ok"]
    for path in paths:
        if not path.exists():
            continue
        size = path.stat().st_size
        lines.append(f"{path}\t{size}\t{str(size <= MAIL_LIMIT_BYTES).lower()}")
    (artifact_dir / "mail_attachment_candidates.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def collect_hardware_ceiling(args: argparse.Namespace) -> Path:
    run_id = args.run_id
    artifact_dir = Path(args.output_base) / run_id
    if artifact_dir.exists() and not args.overwrite:
        raise FileExistsError(f"artifact directory already exists: {artifact_dir}")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    copy_sizes = [parse_size_bytes(token) for token in parse_csv_list(args.copy_sizes)]
    matmul_dims = [int(token) for token in parse_csv_list(args.matmul_dims)]
    matmul_dtypes = parse_csv_list(args.matmul_dtypes)
    dram_sizes = [parse_size_bytes(token) for token in parse_csv_list(args.dram_sizes)]

    run_context = {
        "run_id": run_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python_bin": args.python_bin,
        "npu_device": args.npu_device,
        "copy_sizes": args.copy_sizes,
        "matmul_dims": args.matmul_dims,
        "matmul_dtypes": args.matmul_dtypes,
        "dram_sizes": args.dram_sizes,
        "fio_block_sizes": args.fio_block_sizes,
        "fio_queue_depths": args.fio_queue_depths,
        "fio_rw_modes": args.fio_rw_modes,
        "fio_runtime_s": args.fio_runtime_s,
        "fio_size": args.fio_size,
        "scratch_dir": args.scratch_dir,
    }
    (artifact_dir / "run_context.json").write_text(json.dumps(run_context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    copy_rows, matmul_rows, npu_meta = run_npu_sweeps(
        python_bin=args.python_bin,
        npu_device=args.npu_device,
        copy_sizes=copy_sizes,
        matmul_dims=matmul_dims,
        matmul_dtypes=matmul_dtypes,
        copy_repeats=args.copy_repeats,
        matmul_repeats=args.matmul_repeats,
        timeout_s=args.npu_timeout_s,
    )
    dram_rows, dram_meta = run_cpu_dram_sweep(sizes=dram_sizes, repeats=args.dram_repeats)
    fio_rows, fio_meta = run_fio_sweep(
        scratch_dir=Path(args.scratch_dir),
        block_sizes=parse_csv_list(args.fio_block_sizes),
        queue_depths=parse_csv_list(args.fio_queue_depths),
        rw_modes=parse_csv_list(args.fio_rw_modes),
        runtime_s=args.fio_runtime_s,
        size=args.fio_size,
    )

    _write_csv(
        artifact_dir / "npu_copy_sweep.csv",
        copy_rows,
        ["bench", "direction", "bytes", "size_label", "host_pinned", "non_blocking", "repetitions", "status", "min_ms", "median_ms", "best_gbps", "error"],
    )
    _write_csv(
        artifact_dir / "npu_matmul_sweep.csv",
        matmul_rows,
        ["bench", "dtype", "m", "n", "k", "repetitions", "status", "min_ms", "median_ms", "tflops", "error"],
    )
    _write_csv(
        artifact_dir / "cpu_dram_sweep.csv",
        dram_rows,
        ["bench", "bytes", "size_label", "repetitions", "status", "read_best_gbps", "copy_best_gbps", "read_min_ms", "copy_min_ms", "error"],
    )
    _write_csv(
        artifact_dir / "ssd_fio_sweep.csv",
        fio_rows,
        ["bench", "rw", "bs", "iodepth", "runtime_s", "size", "status", "fio_read_iops", "fio_write_iops", "fio_total_iops", "fio_read_bw_mib_s", "fio_write_bw_mib_s", "fio_total_bw_mib_s", "fio_read_clat_p95_us", "fio_write_clat_p95_us", "error"],
    )

    result = {
        "run_id": run_id,
        "overall_status": "success",
        "npu_status": npu_meta.get("status"),
        "dram_status": dram_meta.get("status"),
        "fio_status": fio_meta.get("status"),
        "row_counts": {
            "npu_copy_sweep": len(copy_rows),
            "npu_matmul_sweep": len(matmul_rows),
            "cpu_dram_sweep": len(dram_rows),
            "ssd_fio_sweep": len(fio_rows),
        },
        "peaks": {
            "h2d_best_gbps": _peak(copy_rows, "best_gbps", direction="h2d"),
            "d2h_best_gbps": _peak(copy_rows, "best_gbps", direction="d2h"),
            "matmul_best_tflops": _peak(matmul_rows, "tflops"),
            "dram_read_best_gbps": _peak(dram_rows, "read_best_gbps"),
            "dram_copy_best_gbps": _peak(dram_rows, "copy_best_gbps"),
            "fio_read_best_mib_s": _peak(fio_rows, "fio_read_bw_mib_s"),
            "fio_write_best_mib_s": _peak(fio_rows, "fio_write_bw_mib_s"),
        },
        "policy": "hardware_microbench_only_no_model_inference_no_bottleneck_claim",
    }
    if all(row.get("status") != "measurable" for row in copy_rows + matmul_rows + dram_rows + fio_rows):
        result["overall_status"] = "blocked"
    (artifact_dir / "hardware_ceiling_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = build_summary(
        run_id=run_id,
        copy_rows=copy_rows,
        matmul_rows=matmul_rows,
        dram_rows=dram_rows,
        fio_rows=fio_rows,
        result=result,
    )
    (artifact_dir / "summary.txt").write_text(summary, encoding="utf-8")
    (artifact_dir / "mail_summary.txt").write_text(summary, encoding="utf-8")
    write_mail_candidates(
        artifact_dir,
        [
            artifact_dir / "summary.txt",
            artifact_dir / "mail_summary.txt",
            artifact_dir / "run_context.json",
            artifact_dir / "hardware_ceiling_result.json",
            artifact_dir / "npu_copy_sweep.csv",
            artifact_dir / "npu_matmul_sweep.csv",
            artifact_dir / "cpu_dram_sweep.csv",
            artifact_dir / "ssd_fio_sweep.csv",
        ],
    )
    return artifact_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AK hardware ceiling microbench sweeps.")
    subparsers = parser.add_subparsers(dest="command")
    collect = subparsers.add_parser("collect", description="Collect a hardware ceiling sweep.")
    collect.add_argument("--run-id", required=True)
    collect.add_argument("--output-base", default="工作记录与进度笔记本/hardware_ceiling_runs")
    collect.add_argument("--scratch-dir", required=True)
    collect.add_argument("--python-bin", default=sys.executable)
    collect.add_argument("--npu-device", default="npu:0")
    collect.add_argument("--copy-sizes", default="4K,16K,64K,1M,16M,64M,256M,1G")
    collect.add_argument("--copy-repeats", type=int, default=5)
    collect.add_argument("--matmul-dims", default="512,1024,2048,4096,8192")
    collect.add_argument("--matmul-dtypes", default="float16")
    collect.add_argument("--matmul-repeats", type=int, default=5)
    collect.add_argument("--dram-sizes", default="256M,1G,4G")
    collect.add_argument("--dram-repeats", type=int, default=3)
    collect.add_argument("--fio-block-sizes", default="4k,128k,1m")
    collect.add_argument("--fio-queue-depths", default="1,4,16,32")
    collect.add_argument("--fio-rw-modes", default="read,write,randread,randwrite")
    collect.add_argument("--fio-runtime-s", type=int, default=5)
    collect.add_argument("--fio-size", default="1G")
    collect.add_argument("--npu-timeout-s", type=int, default=1800)
    collect.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "collect":
        parser.print_help()
        return 2
    artifact_dir = collect_hardware_ceiling(args)
    print(f"artifact_dir={artifact_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
