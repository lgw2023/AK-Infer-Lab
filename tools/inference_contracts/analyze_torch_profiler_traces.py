"""Stream and summarize request-scoped vLLM/Ascend profiler traces.

The parser deliberately separates *where an event was observed* from *what
the event name appears to describe*.  Ascend ``trace_view.json`` files often
contain device kernels, runtime queue records, and host-side PyTorch ranges in
one top-level JSON array.  Treating every name containing ``npu`` or ``matmul``
as a device kernel overstates the evidence, so this module records an explicit
``evidence_domain`` and ``detection_basis`` for every timed range.

Duration sums remain descriptive counters.  Nested ranges and concurrent
streams overlap; they are not a wall-clock or causal critical-path
decomposition.  When timestamps are monotonic, the analyzer additionally
reports an overlap-resolved interval union as an activity measure, not as a
critical path.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import gzip
import json
from pathlib import Path
import re
from statistics import median
from typing import Any, Iterable, Iterator, TextIO


TORCH_TRACE_SUFFIXES = (".pt.trace.json", ".pt.trace.json.gz")
ASCEND_TRACE_NAMES = ("trace_view.json", "trace_view.json.gz")
RANK_PATTERN = re.compile(r"(?:^|[_/])rank[_-]?(\d+)(?:[_/]|$)", re.IGNORECASE)


@dataclass
class TraceParseState:
    """Mutable completion state populated by :func:`iter_trace_events`."""

    top_level_schema: str = "unknown"
    parse_complete: bool = False
    event_limit: int | None = None
    event_limit_reached: bool = False
    events_yielded: int = 0
    parse_error: str | None = None


@dataclass
class IntervalUnion:
    """Streaming interval union for timestamp-ordered Chrome ranges."""

    first_start: float | None = None
    last_start: float | None = None
    current_start: float | None = None
    current_end: float | None = None
    union_us: float = 0.0
    max_end: float | None = None
    timestamp_count: int = 0
    timestamp_monotonic: bool = True

    def add(self, start: float, duration: float) -> None:
        end = start + duration
        self.timestamp_count += 1
        if self.first_start is None:
            self.first_start = start
        if self.last_start is not None and start < self.last_start:
            self.timestamp_monotonic = False
        self.last_start = start
        self.max_end = end if self.max_end is None else max(self.max_end, end)
        if self.current_start is None:
            self.current_start = start
            self.current_end = end
            return
        if start <= float(self.current_end):
            self.current_end = max(float(self.current_end), end)
            return
        self.union_us += float(self.current_end) - float(self.current_start)
        self.current_start = start
        self.current_end = end

    def summary(self) -> dict[str, float | int | bool | None]:
        union = self.union_us
        if self.current_start is not None and self.current_end is not None:
            union += self.current_end - self.current_start
        return {
            "timestamp_count": self.timestamp_count,
            "timestamp_monotonic": self.timestamp_monotonic,
            "active_time_union_us": (
                round(union, 6)
                if self.timestamp_count and self.timestamp_monotonic
                else None
            ),
            "timestamp_span_us": (
                round(float(self.max_end) - float(self.first_start), 6)
                if self.first_start is not None and self.max_end is not None
                else None
            ),
        }


def _open_text(path: Path) -> TextIO:
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open(encoding="utf-8", errors="replace")


def _array_payload(handle: TextIO, path: Path) -> tuple[str, str]:
    """Return ``(schema, buffer_after_array_opener)`` for a trace file."""

    buffer = ""
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            raise ValueError(f"empty or unsupported trace: {path}")
        buffer += chunk
        stripped = buffer.lstrip("\ufeff \t\r\n")
        if not stripped:
            continue
        if stripped.startswith("["):
            return "bare_event_array", stripped[1:]
        if not stripped.startswith("{"):
            raise ValueError(f"unsupported trace top-level JSON value: {path}")
        if '"traceEvents"' not in buffer:
            if len(buffer) > 16 * 1024 * 1024:
                raise ValueError(f"traceEvents key missing near trace header: {path}")
            continue
        after_key = buffer.split('"traceEvents"', 1)[1]
        while "[" not in after_key:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                raise ValueError(f"traceEvents array opener missing: {path}")
            after_key += chunk
        return "trace_events_object", after_key.split("[", 1)[1]


def iter_trace_events(
    path: Path,
    *,
    state: TraceParseState | None = None,
    max_events: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield trace events without materializing a potentially multi-GB file.

    ``max_events=None`` is intentionally the default.  A bounded diagnostic
    pass may set a limit, but that pass is then marked incomplete and cannot
    satisfy a scientific completeness gate.
    """

    parse_state = state if state is not None else TraceParseState()
    parse_state.event_limit = max_events
    decoder = json.JSONDecoder()
    try:
        with _open_text(path) as handle:
            schema, buffer = _array_payload(handle, path)
            parse_state.top_level_schema = schema
            while True:
                buffer = buffer.lstrip(" \t\r\n,")
                if buffer.startswith("]"):
                    parse_state.parse_complete = True
                    return
                if max_events is not None and parse_state.events_yielded >= max_events:
                    parse_state.event_limit_reached = True
                    return
                try:
                    event, end = decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        raise ValueError(f"truncated event array: {path}")
                    buffer += chunk
                    continue
                buffer = buffer[end:]
                if isinstance(event, dict):
                    parse_state.events_yielded += 1
                    yield event
    except (OSError, UnicodeError, ValueError) as exc:
        parse_state.parse_error = str(exc)
        raise


def discover_trace_files(root: Path) -> list[Path]:
    """Discover one trace family without double-counting converted traces.

    Ascend analysis can leave both raw torch traces and converted
    ``trace_view.json`` files below the same root.  When any trace-view files
    exist, they are the canonical family for this aggregation; otherwise the
    original torch-profiler traces are used.
    """

    if not root.is_dir():
        return []
    trace_views = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name in ASCEND_TRACE_NAMES
    )
    if trace_views:
        return trace_views
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name.endswith(TORCH_TRACE_SUFFIXES)
    )


def trace_rank(path: Path) -> str:
    match = RANK_PATTERN.search(path.as_posix())
    return match.group(1) if match else "unknown"


def op_category(name: str) -> str:
    """Map an event name to a semantic operation family."""

    value = name.lower()
    if any(
        token in value
        for token in (
            "hcom",
            "hccl",
            "allreduce",
            "allgather",
            "reduce_scatter",
            "reducescatter",
            "alltoall",
            "all_to_all",
            "broadcast",
        )
    ):
        return "collective_communication"
    if any(
        token in value
        for token in (
            "sparse_attn",
            "attention",
            "flashattention",
            "flash_attention",
            "flash_attn",
            "paged_attention",
            "prompt_flash",
            "lightning_indexer",
            "mla",
        )
    ):
        return "attention"
    if any(
        token in value
        for token in (
            "matmul",
            "gemm",
            "groupedmatmul",
            "grouped_matmul",
            "moe",
            "swiglu",
            "gatingtopk",
            "gating_top_k",
        )
    ):
        return "matmul_or_moe"
    if any(token in value for token in ("fx_compiler", "compile", "graph")):
        return "compiler_or_graph"
    if any(
        token in value
        for token in ("memcpy", "copy_", "transfer", "dma", "h2d", "d2h")
    ):
        return "memory_transfer"
    if any(
        token in value
        for token in ("sample", "softmax", "topk", "top_k", "argmax", "multinomial")
    ):
        return "sampling_or_selection"
    if any(
        token in value
        for token in ("rms_norm", "layer_norm", "layernorm", "elementwise")
    ):
        return "normalization_or_elementwise"
    return "other"


def _metadata_device_pid(event: dict[str, Any]) -> str | None:
    if event.get("ph") != "M":
        return None
    if event.get("name") not in {"process_name", "process_labels"}:
        return None
    args = event.get("args") or {}
    label = f"{args.get('name', '')} {args.get('labels', '')}".lower()
    if any(token in label for token in ("npu", "gpu", "device", "kernel")):
        return str(event.get("pid"))
    return None


def _timed_range(event: dict[str, Any]) -> bool:
    try:
        return event.get("ph") == "X" and float(event.get("dur") or 0) > 0
    except (TypeError, ValueError):
        return False


def event_domain(
    event: dict[str, Any], device_pids: set[str]
) -> tuple[str, str]:
    """Return an evidence domain and the basis for that assignment."""

    if not _timed_range(event):
        return "not_timed_range", "phase_or_duration"
    name = str(event.get("name") or "").lower()
    category = str(event.get("cat") or "").lower()
    args = event.get("args") or {}
    device_type = str(
        args.get("Device Type")
        or args.get("device_type")
        or args.get("Task Type")
        or args.get("task_type")
        or ""
    ).lower()

    if any(
        token in name
        for token in (
            "dequeue@",
            "enqueue@",
            "aclrt",
            "synchronize",
            "stream_wait",
            "event::wait",
            "queue wait",
        )
    ):
        return "runtime_or_queue_wait", "runtime_name"
    if str(event.get("pid")) in device_pids:
        return "device_kernel", "device_process_metadata"
    if any(token in category for token in ("kernel", "npu", "gpu", "device")):
        return "device_kernel", "trace_category"
    if any(token in device_type for token in ("npu", "gpu", "device", "kernel")):
        return "device_kernel", "event_args"
    if name.startswith(("aten::", "vllm::", "c10d::", "_c_ascend::", "npu::")):
        return "host_framework_range", "framework_namespace"
    if "npu_fx_compiler" in name:
        return "host_framework_range", "compiler_range_name"
    if name.startswith(("aclnn", "hcom", "hccl", "ascendcl@")) or any(
        token in name
        for token in (
            "groupedmatmul",
            "quantbatchmatmul",
            "matmulv",
            "moegating",
            "flashattention",
            "sparseattn",
        )
    ):
        return "name_inferred_device_candidate", "operator_name_only"
    return "unclassified_timed_range", "no_device_provenance"


def _event_timestamp(event: dict[str, Any]) -> tuple[float, float] | None:
    try:
        return float(event["ts"]), float(event["dur"])
    except (KeyError, TypeError, ValueError):
        return None


def _rank_sort_key(rank: str) -> tuple[int, str]:
    return (int(rank), rank) if rank.isdigit() else (10**9, rank)


def _median(values: list[float]) -> float | None:
    return round(float(median(values)), 6) if values else None


def analyze_trace_roots(
    roots: dict[str, Path],
    *,
    top_n_ops: int = 30,
    expected_ranks_per_lifecycle: int | None = None,
    max_events_per_trace: int | None = None,
    normalizers: dict[str, dict[str, int | float]] | None = None,
) -> dict[str, Any]:
    """Aggregate trace evidence across every discovered rank."""

    normalizers = normalizers or {}
    inventory: list[dict[str, Any]] = []
    domain_category_totals: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    op_totals: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    interval_totals: dict[tuple[str, str, str, str], IntervalUnion] = defaultdict(
        IntervalUnion
    )

    for lifecycle_id, root in roots.items():
        for path in discover_trace_files(root):
            rank_id = trace_rank(path)
            parse_state = TraceParseState()
            device_pids: set[str] = set()
            timed_event_count = 0
            evidence_event_count = 0
            summed_evidence_duration_us = 0.0
            domain_counts: dict[str, int] = defaultdict(int)
            try:
                for event in iter_trace_events(
                    path, state=parse_state, max_events=max_events_per_trace
                ):
                    metadata_pid = _metadata_device_pid(event)
                    if metadata_pid is not None:
                        device_pids.add(metadata_pid)
                        continue
                    if not _timed_range(event):
                        continue
                    timed_event_count += 1
                    duration = float(event.get("dur") or 0)
                    name = str(event.get("name") or "unknown")
                    semantic_category = op_category(name)
                    domain, basis = event_domain(event, device_pids)
                    domain_counts[domain] += 1
                    evidence_event_count += 1
                    summed_evidence_duration_us += duration
                    key = (lifecycle_id, rank_id, domain, semantic_category)
                    category_row = domain_category_totals.setdefault(
                        key,
                        {
                            "lifecycle_id": lifecycle_id,
                            "rank_id": rank_id,
                            "evidence_domain": domain,
                            "op_category": semantic_category,
                            "event_count": 0,
                            "summed_duration_us": 0.0,
                        },
                    )
                    category_row["event_count"] += 1
                    category_row["summed_duration_us"] += duration
                    op_key = (lifecycle_id, rank_id, domain, semantic_category, name)
                    op_row = op_totals.setdefault(
                        op_key,
                        {
                            "lifecycle_id": lifecycle_id,
                            "rank_id": rank_id,
                            "evidence_domain": domain,
                            "detection_basis": basis,
                            "op_name": name,
                            "op_category": semantic_category,
                            "event_count": 0,
                            "summed_duration_us": 0.0,
                        },
                    )
                    op_row["event_count"] += 1
                    op_row["summed_duration_us"] += duration
                    timestamp = _event_timestamp(event)
                    if timestamp is not None:
                        interval_totals[key].add(*timestamp)
            except (OSError, UnicodeError, ValueError):
                pass

            inventory.append(
                {
                    "lifecycle_id": lifecycle_id,
                    "rank_id": rank_id,
                    "trace_path": str(path),
                    "trace_family": (
                        "ascend_trace_view"
                        if path.name in ASCEND_TRACE_NAMES
                        else "torch_profiler_trace"
                    ),
                    "trace_bytes": path.stat().st_size,
                    "top_level_schema": parse_state.top_level_schema,
                    "event_count": parse_state.events_yielded,
                    "timed_event_count": timed_event_count,
                    "device_pid_count": len(device_pids),
                    "evidence_event_count": evidence_event_count,
                    "summed_evidence_duration_us": round(
                        summed_evidence_duration_us, 6
                    ),
                    "parse_complete": parse_state.parse_complete,
                    "event_limit": parse_state.event_limit,
                    "event_limit_reached": parse_state.event_limit_reached,
                    "parse_error": parse_state.parse_error or "",
                    "strong_device_event_count": domain_counts["device_kernel"],
                    "runtime_or_queue_event_count": domain_counts[
                        "runtime_or_queue_wait"
                    ],
                    "host_framework_event_count": domain_counts[
                        "host_framework_range"
                    ],
                    "name_inferred_event_count": domain_counts[
                        "name_inferred_device_candidate"
                    ],
                }
            )

    category_rows: list[dict[str, Any]] = []
    for key, source_row in domain_category_totals.items():
        row = dict(source_row)
        interval = interval_totals[key].summary()
        row["summed_duration_us"] = round(float(row["summed_duration_us"]), 6)
        row.update(interval)
        norm = normalizers.get(str(row["lifecycle_id"]), {})
        for label in ("relevant_step_count", "prefill_chunk_count", "pressure_chunk_count"):
            count = int(norm.get(label) or 0)
            row[label] = count
            row[f"summed_duration_us_per_{label.removesuffix('_count')}"] = (
                round(float(row["summed_duration_us"]) / count, 6)
                if count > 0
                else None
            )
        category_rows.append(row)
    category_rows.sort(
        key=lambda row: (
            str(row["lifecycle_id"]),
            _rank_sort_key(str(row["rank_id"])),
            str(row["evidence_domain"]),
            str(row["op_category"]),
        )
    )

    top_ops: list[dict[str, Any]] = []
    lifecycle_op_totals: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for (_, _, domain, semantic_category, name), source_row in op_totals.items():
        key = (str(source_row["lifecycle_id"]), domain, semantic_category, name)
        row = lifecycle_op_totals.setdefault(
            key,
            {
                "lifecycle_id": source_row["lifecycle_id"],
                "evidence_domain": domain,
                "op_category": semantic_category,
                "op_name": name,
                "event_count": 0,
                "summed_duration_us": 0.0,
                "ranks_present": set(),
            },
        )
        row["event_count"] += int(source_row["event_count"])
        row["summed_duration_us"] += float(source_row["summed_duration_us"])
        row["ranks_present"].add(str(source_row["rank_id"]))
    for lifecycle_id in roots:
        selected = sorted(
            (
                row
                for (row_lifecycle, _, _, _), row in lifecycle_op_totals.items()
                if row_lifecycle == lifecycle_id
            ),
            key=lambda row: float(row["summed_duration_us"]),
            reverse=True,
        )[:top_n_ops]
        for duration_rank, source_row in enumerate(selected, start=1):
            row = dict(source_row)
            row["ranks_present"] = ",".join(
                sorted(row["ranks_present"], key=_rank_sort_key)
            )
            row["rank_count"] = len(row["ranks_present"].split(","))
            row["summed_duration_us"] = round(float(row["summed_duration_us"]), 6)
            row["duration_rank"] = duration_rank
            norm = normalizers.get(lifecycle_id, {})
            chunks = int(norm.get("prefill_chunk_count") or 0)
            row["events_per_rank_per_prefill_chunk"] = (
                round(int(row["event_count"]) / row["rank_count"] / chunks, 6)
                if row["rank_count"] and chunks
                else None
            )
            top_ops.append(row)

    rank_rows: list[dict[str, Any]] = []
    by_rank: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in category_rows:
        by_rank[(str(row["lifecycle_id"]), str(row["rank_id"]))].append(row)
    for (lifecycle_id, rank_id), rows in sorted(
        by_rank.items(), key=lambda item: (item[0][0], _rank_sort_key(item[0][1]))
    ):
        rank_rows.append(
            {
                "lifecycle_id": lifecycle_id,
                "rank_id": rank_id,
                "event_count": sum(int(row["event_count"]) for row in rows),
                "summed_duration_us": round(
                    sum(float(row["summed_duration_us"]) for row in rows), 6
                ),
                "strong_device_event_count": sum(
                    int(row["event_count"])
                    for row in rows
                    if row["evidence_domain"] == "device_kernel"
                ),
                "runtime_or_queue_event_count": sum(
                    int(row["event_count"])
                    for row in rows
                    if row["evidence_domain"] == "runtime_or_queue_wait"
                ),
                "host_framework_event_count": sum(
                    int(row["event_count"])
                    for row in rows
                    if row["evidence_domain"] == "host_framework_range"
                ),
                "name_inferred_event_count": sum(
                    int(row["event_count"])
                    for row in rows
                    if row["evidence_domain"] == "name_inferred_device_candidate"
                ),
            }
        )

    cross_rank_rows: list[dict[str, Any]] = []
    cross_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in category_rows:
        cross_groups[
            (
                str(row["lifecycle_id"]),
                str(row["evidence_domain"]),
                str(row["op_category"]),
            )
        ].append(row)
    for (lifecycle_id, domain, semantic_category), rows in sorted(cross_groups.items()):
        durations = [float(row["summed_duration_us"]) for row in rows]
        events = [float(row["event_count"]) for row in rows]
        cross_rank_rows.append(
            {
                "lifecycle_id": lifecycle_id,
                "evidence_domain": domain,
                "op_category": semantic_category,
                "rank_count": len(rows),
                "event_count_median": _median(events),
                "event_count_min": int(min(events)),
                "event_count_max": int(max(events)),
                "summed_duration_us_median": _median(durations),
                "summed_duration_us_min": round(min(durations), 6),
                "summed_duration_us_max": round(max(durations), 6),
            }
        )

    lifecycle_summaries: list[dict[str, Any]] = []
    for lifecycle_id, root in roots.items():
        trace_rows = [row for row in inventory if row["lifecycle_id"] == lifecycle_id]
        ranks = sorted(
            {str(row["rank_id"]) for row in trace_rows}, key=_rank_sort_key
        )
        rank_coverage_complete = bool(trace_rows) and (
            expected_ranks_per_lifecycle is None
            or (
                len(ranks) == expected_ranks_per_lifecycle
                and len(trace_rows) == expected_ranks_per_lifecycle
            )
        )
        lifecycle_summaries.append(
            {
                "lifecycle_id": lifecycle_id,
                "trace_root": str(root),
                "trace_file_count": len(trace_rows),
                "rank_ids": ranks,
                "rank_count": len(ranks),
                "expected_rank_count": expected_ranks_per_lifecycle,
                "rank_coverage_complete": rank_coverage_complete,
                "trace_bytes": sum(int(row["trace_bytes"]) for row in trace_rows),
                "event_count": sum(int(row["event_count"]) for row in trace_rows),
                "timed_event_count": sum(
                    int(row["timed_event_count"]) for row in trace_rows
                ),
                "evidence_event_count": sum(
                    int(row["evidence_event_count"]) for row in trace_rows
                ),
                "strong_device_event_count": sum(
                    int(row["strong_device_event_count"]) for row in trace_rows
                ),
                "name_inferred_event_count": sum(
                    int(row["name_inferred_event_count"]) for row in trace_rows
                ),
                "trace_available": bool(trace_rows),
                "parse_complete": bool(trace_rows)
                and all(row["parse_complete"] is True for row in trace_rows),
                "event_limit_reached": any(
                    row["event_limit_reached"] is True for row in trace_rows
                ),
            }
        )

    complete = bool(lifecycle_summaries) and all(
        row["trace_available"] is True
        and row["parse_complete"] is True
        and row["rank_coverage_complete"] is True
        and row["event_limit_reached"] is False
        and int(row["evidence_event_count"]) > 0
        for row in lifecycle_summaries
    )
    return {
        "schema": "p6_3c_request_scoped_execution_path_v2",
        "profiler_complete": complete,
        "expected_ranks_per_lifecycle": expected_ranks_per_lifecycle,
        "event_limit_per_trace": max_events_per_trace,
        "duration_unit": "chrome_trace_microseconds",
        "duration_sum_caveat": (
            "nested_ranges_and_concurrent_streams_make_duration_sums_diagnostic_only"
        ),
        "active_time_union_caveat": (
            "timestamp_ordered_interval_union_is_activity_not_causal_critical_path"
        ),
        "classification_caveat": (
            "name_inferred_device_candidate_is_not_equivalent_to_device_kernel"
        ),
        "lifecycle_summaries": lifecycle_summaries,
        "trace_inventory": inventory,
        "category_rows": category_rows,
        "rank_rows": rank_rows,
        "cross_rank_rows": cross_rank_rows,
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
