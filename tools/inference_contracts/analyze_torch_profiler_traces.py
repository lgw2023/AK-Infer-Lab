"""Stream and summarize request-scoped vLLM torch-profiler traces.

The R3E-F1 server starts profiling through vLLM's ``/start_profile`` endpoint
only after the model is ready and the lifecycle warmup has completed.  Trace
files can still be large, so this reader does not load the Chrome trace into
memory.  Device-duration sums are descriptive counters: concurrent streams
can overlap and therefore must not be interpreted as wall-clock components.
"""

from __future__ import annotations

from collections import defaultdict
import gzip
import json
from pathlib import Path
from typing import Any, Iterable, Iterator, TextIO


TRACE_SUFFIXES = (".pt.trace.json", ".pt.trace.json.gz")


def _open_text(path: Path) -> TextIO:
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open(encoding="utf-8", errors="replace")


def iter_trace_events(path: Path) -> Iterator[dict[str, Any]]:
    """Yield Chrome ``traceEvents`` entries without materializing the file."""

    decoder = json.JSONDecoder()
    with _open_text(path) as handle:
        buffer = ""
        while '"traceEvents"' not in buffer:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                raise ValueError(f"traceEvents array missing: {path}")
            buffer += chunk
            if len(buffer) > 16 * 1024 * 1024:
                buffer = buffer[-16 * 1024 * 1024 :]
        buffer = buffer.split('"traceEvents"', 1)[1]
        while "[" not in buffer:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                raise ValueError(f"traceEvents array opener missing: {path}")
            buffer += chunk
        buffer = buffer.split("[", 1)[1]

        while True:
            buffer = buffer.lstrip(" \t\r\n,")
            if buffer.startswith("]"):
                return
            try:
                event, end = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    raise ValueError(f"truncated traceEvents array: {path}")
                buffer += chunk
                continue
            buffer = buffer[end:]
            if isinstance(event, dict):
                yield event


def discover_trace_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name.endswith(TRACE_SUFFIXES)
    )


def op_category(name: str) -> str:
    value = name.lower()
    if any(
        token in value
        for token in (
            "hcom",
            "hccl",
            "allreduce",
            "allgather",
            "reducescatter",
            "reduce_scatter",
            "alltoall",
            "all_to_all",
            "broadcast",
        )
    ):
        return "collective_communication"
    if any(
        token in value
        for token in ("matmul", "gemm", "groupedmatmul", "grouped_matmul", "moe")
    ):
        return "matmul_or_moe"
    if any(
        token in value
        for token in ("attention", "flashattention", "flash_attention", "mla")
    ):
        return "attention"
    if any(
        token in value
        for token in ("memcpy", "copy", "transfer", "transpose", "sync")
    ):
        return "memory_transfer_or_sync"
    if any(
        token in value
        for token in ("sample", "softmax", "topk", "top_k", "argmax", "multinomial")
    ):
        return "sampling_or_selection"
    return "other"


def _device_pids(path: Path) -> set[str]:
    output: set[str] = set()
    for event in iter_trace_events(path):
        if event.get("ph") != "M":
            continue
        if event.get("name") not in {"process_name", "process_labels"}:
            continue
        label = str((event.get("args") or {}).get("name") or "") + " " + str(
            (event.get("args") or {}).get("labels") or ""
        )
        if any(token in label.lower() for token in ("npu", "gpu", "device")):
            output.add(str(event.get("pid")))
    return output


def _is_device_event(event: dict[str, Any], device_pids: set[str]) -> bool:
    if event.get("ph") != "X" or float(event.get("dur") or 0) <= 0:
        return False
    category = str(event.get("cat") or "").lower()
    args = event.get("args") or {}
    device_type = str(args.get("Device Type") or args.get("device_type") or "")
    return (
        str(event.get("pid")) in device_pids
        or any(token in category for token in ("kernel", "npu", "gpu", "device"))
        or any(token in device_type.lower() for token in ("npu", "gpu", "device"))
    )


def analyze_trace_roots(
    roots: dict[str, Path],
    *,
    top_n_ops: int = 30,
) -> dict[str, Any]:
    inventory: list[dict[str, Any]] = []
    category_totals: dict[tuple[str, str], dict[str, float | int | str]] = {}
    op_totals: dict[tuple[str, str], dict[str, float | int | str]] = {}

    for lifecycle_id, root in roots.items():
        for path in discover_trace_files(root):
            device_pids = _device_pids(path)
            event_count = 0
            device_event_count = 0
            device_duration_us = 0.0
            for event in iter_trace_events(path):
                event_count += 1
                if not _is_device_event(event, device_pids):
                    continue
                duration = float(event.get("dur") or 0)
                name = str(event.get("name") or "unknown")
                category = op_category(name)
                device_event_count += 1
                device_duration_us += duration
                category_row = category_totals.setdefault(
                    (lifecycle_id, category),
                    {
                        "lifecycle_id": lifecycle_id,
                        "op_category": category,
                        "device_event_count": 0,
                        "summed_device_duration_us": 0.0,
                    },
                )
                category_row["device_event_count"] = int(
                    category_row["device_event_count"]
                ) + 1
                category_row["summed_device_duration_us"] = float(
                    category_row["summed_device_duration_us"]
                ) + duration
                op_row = op_totals.setdefault(
                    (lifecycle_id, name),
                    {
                        "lifecycle_id": lifecycle_id,
                        "op_name": name,
                        "op_category": category,
                        "device_event_count": 0,
                        "summed_device_duration_us": 0.0,
                    },
                )
                op_row["device_event_count"] = int(op_row["device_event_count"]) + 1
                op_row["summed_device_duration_us"] = float(
                    op_row["summed_device_duration_us"]
                ) + duration
            inventory.append(
                {
                    "lifecycle_id": lifecycle_id,
                    "trace_path": str(path),
                    "trace_bytes": path.stat().st_size,
                    "event_count": event_count,
                    "device_pid_count": len(device_pids),
                    "device_event_count": device_event_count,
                    "summed_device_duration_us": round(device_duration_us, 6),
                }
            )

    category_rows = list(category_totals.values())
    lifecycle_duration = defaultdict(float)
    for row in category_rows:
        lifecycle_duration[str(row["lifecycle_id"])] += float(
            row["summed_device_duration_us"]
        )
    for row in category_rows:
        total = lifecycle_duration[str(row["lifecycle_id"])]
        row["diagnostic_duration_fraction"] = (
            round(float(row["summed_device_duration_us"]) / total, 8)
            if total > 0
            else None
        )
        row["summed_device_duration_us"] = round(
            float(row["summed_device_duration_us"]), 6
        )
    category_rows.sort(key=lambda row: (str(row["lifecycle_id"]), str(row["op_category"])))

    top_ops: list[dict[str, Any]] = []
    for lifecycle_id in roots:
        selected = sorted(
            (
                dict(row)
                for (row_lifecycle, _), row in op_totals.items()
                if row_lifecycle == lifecycle_id
            ),
            key=lambda row: float(row["summed_device_duration_us"]),
            reverse=True,
        )[:top_n_ops]
        for rank, row in enumerate(selected, start=1):
            row["duration_rank"] = rank
            row["summed_device_duration_us"] = round(
                float(row["summed_device_duration_us"]), 6
            )
            top_ops.append(row)

    lifecycle_summaries: list[dict[str, Any]] = []
    for lifecycle_id, root in roots.items():
        trace_rows = [row for row in inventory if row["lifecycle_id"] == lifecycle_id]
        lifecycle_summaries.append(
            {
                "lifecycle_id": lifecycle_id,
                "trace_root": str(root),
                "trace_file_count": len(trace_rows),
                "trace_bytes": sum(int(row["trace_bytes"]) for row in trace_rows),
                "event_count": sum(int(row["event_count"]) for row in trace_rows),
                "device_event_count": sum(
                    int(row["device_event_count"]) for row in trace_rows
                ),
                "summed_device_duration_us": round(
                    sum(float(row["summed_device_duration_us"]) for row in trace_rows),
                    6,
                ),
                "trace_available": bool(trace_rows),
                "device_events_available": any(
                    int(row["device_event_count"]) > 0 for row in trace_rows
                ),
            }
        )

    complete = bool(lifecycle_summaries) and all(
        row["trace_available"] is True and row["device_events_available"] is True
        for row in lifecycle_summaries
    )
    return {
        "schema": "p6_3c_vllm_torch_profiler_device_categories_v1",
        "profiler_complete": complete,
        "duration_unit": "chrome_trace_microseconds",
        "duration_sum_caveat": (
            "concurrent_stream_overlap_means_summed_device_duration_is_diagnostic_not_wall_time"
        ),
        "lifecycle_summaries": lifecycle_summaries,
        "trace_inventory": inventory,
        "category_rows": category_rows,
        "top_operator_rows": top_ops,
    }


def write_tsv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    import csv

    materialized = list(rows)
    fields = list(materialized[0]) if materialized else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(materialized)
