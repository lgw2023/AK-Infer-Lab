"""Zero-NPU step/flow linkage analysis for the completed R3E-F1 traces.

R3E-F1-A1 established complete cross-rank trace coverage, but whole-window
duration sums cannot identify a causal bottleneck.  A2 reuses the same source
tree and asks two narrower questions:

1. can profiler timestamps be aligned to the scheduler/executor step windows;
2. do trace flow/correlation identifiers connect host, runtime and device
   execution domains?

The analysis is deliberately conservative.  Temporal containment is reported
as temporal evidence, not dependency proof, and device analysis tracks such as
``Communication(Not Overlapped)`` are not relabelled as kernels.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import heapq
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from tools.inference_contracts import analyze_torch_profiler_traces as trace_analysis
from tools.inference_contracts import (
    run_deepseek_p6_3c_r3e_f1_a1_trace_reaggregation as a1,
)


TASK_ID = "p6_3c_r3e_f1_a2_step_flow_causal_linkage_2026_0809"
SOURCE_A1_TASK_ID = a1.TASK_ID
LINK_FIELD_KEYS = {
    "correlationid": "correlation_id",
    "externalid": "external_id",
    "recordfunctionid": "record_function_id",
    "sequencenumber": "sequence_number",
    "flowid": "flow_id",
    "connectionid": "connection_id",
    "taskid": "task_id",
}
FLOW_PHASES = {"s", "t", "f"}
ANALYSIS_ROLE_NAMES = {
    "free": "analysis_free",
    "computing": "analysis_computing",
    "communication": "analysis_communication",
    "communication(not overlapped)": "analysis_communication_not_overlapped",
    "notify_wait": "analysis_notify_wait",
}
BOUNDED_CANDIDATES = (
    "result_summary.md",
    "grading_inputs.json",
    "scientific_outcome.json",
    "source_evidence_manifest.json",
    "trace_linkage_inventory.tsv",
    "link_field_summary.tsv",
    "cross_domain_link_chains.tsv",
    "step_rank_path_summary.tsv",
    "step_cross_rank_summary.tsv",
    "bottleneck_hypothesis_review.json",
    "adaptive_execution_review.json",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_tsv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    trace_analysis.write_tsv(path, rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_key(value: object) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def _link_tokens(event: dict[str, Any]) -> set[tuple[str, str]]:
    tokens: set[tuple[str, str]] = set()
    phase = str(event.get("ph") or "")
    if phase in FLOW_PHASES and event.get("id") is not None:
        scope = event.get("scope") or event.get("cat") or "global"
        tokens.add(("chrome_flow", f"{scope}:{event['id']}"))
    for container in (event, event.get("args") or {}):
        if not isinstance(container, dict):
            continue
        for raw_key, raw_value in container.items():
            kind = LINK_FIELD_KEYS.get(_normalized_key(raw_key))
            if kind and raw_value not in (None, "", -1, "-1"):
                tokens.add((kind, str(raw_value)))
    return tokens


def _point_domain(event: dict[str, Any], device_pids: set[str]) -> str:
    synthetic = dict(event)
    synthetic["ph"] = "X"
    synthetic["dur"] = 1
    return trace_analysis.event_domain(synthetic, device_pids)[0]


def _execution_role(event: dict[str, Any], domain: str, category: str) -> str:
    name = str(event.get("name") or "").lower()
    if domain == "device_analysis_timeline":
        return ANALYSIS_ROLE_NAMES.get(name, "analysis_other")
    if domain == "runtime_or_queue_wait" and category == "collective_communication":
        return "runtime_collective_queue"
    if domain == "actual_device_kernel" and category == "collective_communication":
        return "actual_device_collective_kernel"
    if domain == "actual_device_kernel":
        return f"actual_device_kernel_{category}"
    if domain == "device_process_timed_range":
        return f"device_process_range_{category}"
    if domain == "host_framework_range":
        return f"host_framework_{category}"
    if domain == "name_inferred_device_candidate":
        return f"name_inferred_candidate_{category}"
    return f"{domain}_{category}"


def _step_class(step: dict[str, Any]) -> str:
    resident = int(step.get("resident_decode_tokens") or 0)
    injected = int(step.get("injected_prefill_tokens") or 0)
    if resident and injected:
        return "mixed_prefill_decode"
    if resident:
        return "resident_decode_only"
    if injected:
        return "injected_prefill_only"
    return "other"


def scheduler_step_windows(source: Path) -> list[dict[str, Any]]:
    """Join the four read-only observer events into execution windows."""

    output: list[dict[str, Any]] = []
    for lifecycle_id in a1.LIFECYCLE_IDS:
        trace_dir = source / "lifecycles" / lifecycle_id / "runtime/scheduler_trace"
        by_context: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for path in sorted(trace_dir.glob("trace.*.jsonl")):
            for row in _read_jsonl(path):
                context = str(row.get("timing_context_id") or "")
                if context:
                    by_context[context][str(row.get("event") or "")] = row
        for context_id, events in by_context.items():
            step = events.get("scheduler_step")
            submit = events.get("executor_execute_submit")
            complete = events.get("executor_execute_complete")
            update = events.get("scheduler_update_complete")
            if not all((step, submit, complete, update)):
                continue
            start_us = float(submit.get("submit_start_monotonic_ns") or 0) / 1000
            complete_us = (
                float(complete.get("executor_complete_monotonic_ns") or 0) / 1000
            )
            update_us = float(update.get("update_start_monotonic_ns") or 0) / 1000
            end_us = max(complete_us, update_us)
            if not (start_us > 0 and end_us > start_us):
                continue
            wall_minus_monotonic_us = (
                float(step.get("timestamp_ns") or 0)
                - float(step.get("monotonic_ns") or 0)
            ) / 1000
            output.append(
                {
                    "lifecycle_id": lifecycle_id,
                    "config_id": a1.EXPECTED_CONFIGS[lifecycle_id],
                    "timing_context_id": context_id,
                    "step_index": int(step.get("step_index") or 0),
                    "step_class": _step_class(step),
                    "resident_decode_tokens": int(
                        step.get("resident_decode_tokens") or 0
                    ),
                    "injected_prefill_tokens": int(
                        step.get("injected_prefill_tokens") or 0
                    ),
                    "window_start_monotonic_us": round(start_us, 3),
                    "window_end_monotonic_us": round(end_us, 3),
                    "window_duration_us": round(end_us - start_us, 3),
                    "wall_minus_monotonic_us": round(
                        wall_minus_monotonic_us, 3
                    ),
                }
            )
    output.sort(key=lambda row: (row["lifecycle_id"], row["step_index"]))
    return output


@dataclass(frozen=True)
class ClockTransform:
    name: str
    scale_to_us: float
    offset_to_monotonic_us: float
    sample_inside_count: int
    sample_count: int
    median_distance_us: float

    def timestamp(self, raw: float) -> float:
        return raw * self.scale_to_us + self.offset_to_monotonic_us

    def duration(self, raw: float) -> float:
        return raw * self.scale_to_us


def _distance_to_ranges(value: float, windows: list[dict[str, Any]]) -> float:
    best = math.inf
    for row in windows:
        start = float(row["window_start_monotonic_us"])
        end = float(row["window_end_monotonic_us"])
        if start <= value <= end:
            return 0.0
        best = min(best, abs(value - start), abs(value - end))
    return best


def infer_clock_transform(
    samples: list[float], windows: list[dict[str, Any]]
) -> ClockTransform | None:
    if not samples or not windows:
        return None
    wall_offset = float(median(row["wall_minus_monotonic_us"] for row in windows))
    candidates: list[ClockTransform] = []
    for scale_name, scale in (("microseconds", 1.0), ("nanoseconds", 0.001), ("milliseconds", 1000.0)):
        for origin, offset in (("monotonic", 0.0), ("wall", -wall_offset)):
            distances = [
                _distance_to_ranges(sample * scale + offset, windows)
                for sample in samples
            ]
            candidates.append(
                ClockTransform(
                    name=f"{scale_name}_{origin}",
                    scale_to_us=scale,
                    offset_to_monotonic_us=offset,
                    sample_inside_count=sum(distance == 0 for distance in distances),
                    sample_count=len(samples),
                    median_distance_us=float(median(distances)),
                )
            )
    return min(
        candidates,
        key=lambda row: (-row.sample_inside_count, row.median_distance_us),
    )


@dataclass
class LinkAggregate:
    kind: str
    value_hash: str
    event_count: int = 0
    domains: set[str] = field(default_factory=set)
    categories: set[str] = field(default_factory=set)
    phases: set[str] = field(default_factory=set)


class LinkSpool:
    """Disk-shard link IDs so complete traces do not require unbounded RAM."""

    def __init__(self, root: Path, *, shard_count: int = 32) -> None:
        self.root = root
        self.shard_count = shard_count
        self.root.mkdir(parents=True, exist_ok=False)
        self._handles: dict[int, Any] = {}

    def add(
        self,
        kind: str,
        value_hash: str,
        domain: str,
        category: str,
        phase: str,
    ) -> None:
        shard = int(value_hash[:8], 16) % self.shard_count
        handle = self._handles.get(shard)
        if handle is None:
            handle = (self.root / f"links.{shard:02d}.tsv").open(
                "a", encoding="utf-8"
            )
            self._handles[shard] = handle
        handle.write(
            f"{kind}\t{value_hash}\t{domain}\t{category}\t{phase or 'none'}\n"
        )

    def aggregates(self) -> Iterable[LinkAggregate]:
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()
        for shard in range(self.shard_count):
            path = self.root / f"links.{shard:02d}.tsv"
            if not path.is_file():
                continue
            values: dict[tuple[str, str], LinkAggregate] = {}
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    kind, value_hash, domain, category, phase = line.rstrip(
                        "\n"
                    ).split("\t", 4)
                    aggregate = values.setdefault(
                        (kind, value_hash), LinkAggregate(kind, value_hash)
                    )
                    aggregate.event_count += 1
                    aggregate.domains.add(domain)
                    aggregate.categories.add(category)
                    aggregate.phases.add(phase)
            yield from values.values()
            path.unlink()
        self.root.rmdir()


@dataclass
class PathAggregate:
    event_count: int = 0
    clipped_duration_us: float = 0.0
    first_start_us: float | None = None
    last_end_us: float | None = None

    def add(self, start: float, end: float) -> None:
        self.event_count += 1
        self.clipped_duration_us += max(end - start, 0.0)
        self.first_start_us = start if self.first_start_us is None else min(
            self.first_start_us, start
        )
        self.last_end_us = end if self.last_end_us is None else max(
            self.last_end_us, end
        )


def _overlapping_windows(
    start: float,
    end: float,
    windows: list[dict[str, Any]],
    starts: list[float],
    max_width: float,
) -> Iterable[dict[str, Any]]:
    left = bisect_left(starts, start - max_width)
    right = bisect_right(starts, end)
    for row in windows[left:right]:
        if float(row["window_end_monotonic_us"]) >= start:
            yield row


def analyze_trace_linkage(
    source: Path,
    windows: list[dict[str, Any]],
    *,
    scratch_root: Path,
    trace_workspace: Path | None = None,
    sample_events: int = 4096,
    max_events_per_trace: int | None = None,
) -> dict[str, Any]:
    roots = a1._trace_roots(source, trace_workspace)  # noqa: SLF001
    windows_by_lifecycle = {
        lifecycle_id: [
            row for row in windows if row["lifecycle_id"] == lifecycle_id
        ]
        for lifecycle_id in a1.LIFECYCLE_IDS
    }
    inventory: list[dict[str, Any]] = []
    field_summary: dict[tuple[str, str, str], dict[str, Any]] = {}
    chain_heap: list[tuple[int, int, dict[str, Any]]] = []
    chain_sequence = 0
    chain_rows_total = 0
    path_aggregates: dict[tuple[str, str, str, str], PathAggregate] = defaultdict(
        PathAggregate
    )

    for lifecycle_id, root in roots.items():
        lifecycle_windows = windows_by_lifecycle[lifecycle_id]
        starts = [float(row["window_start_monotonic_us"]) for row in lifecycle_windows]
        max_width = max(
            (float(row["window_duration_us"]) for row in lifecycle_windows),
            default=0.0,
        )
        for path in trace_analysis.discover_trace_files(root):
            rank_id = trace_analysis.trace_rank(path)
            spool = LinkSpool(
                scratch_root / f"{lifecycle_id}.rank_{rank_id}"
            )
            state = trace_analysis.TraceParseState()
            device_pids: set[str] = set()
            samples: list[float] = []
            buffered: list[tuple[dict[str, Any], float, float, str, str, str]] = []
            transform: ClockTransform | None = None
            flow_event_count = 0
            linked_event_count = 0
            timed_event_count = 0
            temporally_attributed_event_count = 0
            multi_window_event_count = 0

            def attribute(
                event: dict[str, Any],
                raw_ts: float,
                raw_dur: float,
                domain: str,
                category: str,
                role: str,
            ) -> None:
                nonlocal temporally_attributed_event_count, multi_window_event_count
                if transform is None:
                    return
                start_us = transform.timestamp(raw_ts)
                end_us = start_us + max(transform.duration(raw_dur), 0.0)
                matched = 0
                for window in _overlapping_windows(
                    start_us, end_us, lifecycle_windows, starts, max_width
                ):
                    clipped_start = max(
                        start_us, float(window["window_start_monotonic_us"])
                    )
                    clipped_end = min(
                        end_us, float(window["window_end_monotonic_us"])
                    )
                    if clipped_end <= clipped_start:
                        continue
                    matched += 1
                    key = (
                        lifecycle_id,
                        str(window["timing_context_id"]),
                        rank_id,
                        role,
                    )
                    path_aggregates[key].add(clipped_start, clipped_end)
                if matched:
                    temporally_attributed_event_count += 1
                if matched > 1:
                    multi_window_event_count += 1

            for event in trace_analysis.iter_trace_events(
                path, state=state, max_events=max_events_per_trace
            ):
                metadata_pid = trace_analysis._metadata_device_pid(event)  # noqa: SLF001
                if metadata_pid is not None:
                    device_pids.add(metadata_pid)
                phase = str(event.get("ph") or "")
                if phase in FLOW_PHASES:
                    flow_event_count += 1
                domain = _point_domain(event, device_pids)
                category = trace_analysis.op_category(str(event.get("name") or ""))
                tokens = _link_tokens(event)
                if tokens:
                    linked_event_count += 1
                for kind, value in tokens:
                    value_hash = hashlib.sha256(
                        f"{kind}\0{value}".encode("utf-8", errors="replace")
                    ).hexdigest()[:20]
                    spool.add(kind, value_hash, domain, category, phase)

                timestamp = trace_analysis._event_timestamp(event)  # noqa: SLF001
                if timestamp is None:
                    continue
                raw_ts, raw_dur = timestamp
                timed_event_count += 1
                domain, _ = trace_analysis.event_domain(event, device_pids)
                category = trace_analysis.op_category(str(event.get("name") or ""))
                role = _execution_role(event, domain, category)
                if transform is None:
                    samples.append(raw_ts)
                    buffered.append((event, raw_ts, raw_dur, domain, category, role))
                    if len(samples) >= sample_events:
                        transform = infer_clock_transform(samples, lifecycle_windows)
                        for buffered_event in buffered:
                            attribute(*buffered_event)
                        buffered.clear()
                else:
                    attribute(event, raw_ts, raw_dur, domain, category, role)

            if transform is None:
                transform = infer_clock_transform(samples, lifecycle_windows)
                for buffered_event in buffered:
                    attribute(*buffered_event)

            cross_domain = 0
            host_runtime_device = 0
            unique_link_value_count = 0
            by_kind: dict[str, dict[str, int]] = defaultdict(
                lambda: {
                    "unique": 0,
                    "events": 0,
                    "cross_domain": 0,
                    "host_runtime_device": 0,
                }
            )
            for aggregate in spool.aggregates():
                unique_link_value_count += 1
                kind_summary = by_kind[aggregate.kind]
                kind_summary["unique"] += 1
                kind_summary["events"] += aggregate.event_count
                substantive_domains = aggregate.domains - {"not_timed_range"}
                if len(substantive_domains) >= 2:
                    cross_domain += 1
                    kind_summary["cross_domain"] += 1
                host = "host_framework_range" in substantive_domains
                runtime = "runtime_or_queue_wait" in substantive_domains
                device = bool(
                    substantive_domains
                    & {
                        "actual_device_kernel",
                        "device_process_timed_range",
                        "device_analysis_timeline",
                        "name_inferred_device_candidate",
                    }
                )
                if host and runtime and device:
                    host_runtime_device += 1
                    kind_summary["host_runtime_device"] += 1
                    chain_rows_total += 1
                    chain_sequence += 1
                    chain_row = {
                        "lifecycle_id": lifecycle_id,
                        "rank_id": rank_id,
                        "link_kind": aggregate.kind,
                        "link_value_sha256_prefix": aggregate.value_hash,
                        "event_count": aggregate.event_count,
                        "domains": ",".join(sorted(aggregate.domains)),
                        "categories": ",".join(sorted(aggregate.categories)),
                        "phases": ",".join(sorted(aggregate.phases)),
                    }
                    heap_item = (aggregate.event_count, chain_sequence, chain_row)
                    if len(chain_heap) < 20:
                        heapq.heappush(chain_heap, heap_item)
                    elif aggregate.event_count > chain_heap[0][0]:
                        heapq.heapreplace(chain_heap, heap_item)
            for kind, values in by_kind.items():
                key = (lifecycle_id, rank_id, kind)
                field_summary[key] = {
                    "lifecycle_id": lifecycle_id,
                    "rank_id": rank_id,
                    "link_kind": kind,
                    "unique_value_count": values["unique"],
                    "event_count": values["events"],
                    "cross_domain_value_count": values["cross_domain"],
                    "host_runtime_device_value_count": values[
                        "host_runtime_device"
                    ],
                }

            reliable_clock = bool(
                transform
                and transform.sample_inside_count > 0
                and transform.sample_inside_count / transform.sample_count >= 0.01
            )
            inventory.append(
                {
                    "lifecycle_id": lifecycle_id,
                    "rank_id": rank_id,
                    "trace_path": str(path),
                    "trace_bytes": path.stat().st_size,
                    "event_count": state.events_yielded,
                    "timed_event_count": timed_event_count,
                    "flow_event_count": flow_event_count,
                    "linked_event_count": linked_event_count,
                    "unique_link_value_count": unique_link_value_count,
                    "cross_domain_link_value_count": cross_domain,
                    "host_runtime_device_link_value_count": host_runtime_device,
                    "clock_transform": transform.name if transform else "unresolved",
                    "clock_sample_inside_count": (
                        transform.sample_inside_count if transform else 0
                    ),
                    "clock_sample_count": transform.sample_count if transform else 0,
                    "clock_median_distance_us": (
                        round(transform.median_distance_us, 3) if transform else None
                    ),
                    "clock_alignment_reliable": reliable_clock,
                    "temporally_attributed_event_count": temporally_attributed_event_count,
                    "multi_window_event_count": multi_window_event_count,
                    "parse_complete": state.parse_complete,
                    "event_limit_reached": state.event_limit_reached,
                    "parse_error": state.parse_error or "",
                }
            )

    chain_rows = [item[2] for item in sorted(chain_heap, reverse=True)]
    return {
        "inventory": inventory,
        "field_summary": list(field_summary.values()),
        "chain_rows": chain_rows,
        "chain_rows_total": chain_rows_total,
        "path_aggregates": path_aggregates,
    }


def _path_rows(
    windows: list[dict[str, Any]],
    aggregates: dict[tuple[str, str, str, str], PathAggregate],
) -> list[dict[str, Any]]:
    window_map = {
        (str(row["lifecycle_id"]), str(row["timing_context_id"])): row
        for row in windows
    }
    rows: list[dict[str, Any]] = []
    for (lifecycle, context, rank, role), value in sorted(aggregates.items()):
        window = window_map[(lifecycle, context)]
        rows.append(
            {
                "lifecycle_id": lifecycle,
                "config_id": window["config_id"],
                "timing_context_id": context,
                "step_index": window["step_index"],
                "step_class": window["step_class"],
                "rank_id": rank,
                "execution_role": role,
                "event_count": value.event_count,
                "clipped_duration_sum_us": round(value.clipped_duration_us, 3),
                "first_start_monotonic_us": round(value.first_start_us or 0, 3),
                "last_end_monotonic_us": round(value.last_end_us or 0, 3),
                "window_duration_us": window["window_duration_us"],
                "duration_sum_is_not_interval_union": True,
            }
        )
    return rows


def _cross_rank_step_rows(
    windows: list[dict[str, Any]], path_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in path_rows:
        grouped[(row["lifecycle_id"], row["timing_context_id"])].append(row)
    output: list[dict[str, Any]] = []
    for window in windows:
        key = (window["lifecycle_id"], window["timing_context_id"])
        rows = grouped.get(key, [])
        by_rank: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_rank[str(row["rank_id"])].append(row)
        ends = {
            rank: max(float(row["last_end_monotonic_us"]) for row in rank_rows)
            for rank, rank_rows in by_rank.items()
        }
        slowest = max(ends, key=ends.get) if ends else ""
        output.append(
            {
                "lifecycle_id": window["lifecycle_id"],
                "config_id": window["config_id"],
                "timing_context_id": window["timing_context_id"],
                "step_index": window["step_index"],
                "step_class": window["step_class"],
                "rank_count": len(by_rank),
                "rank_ids": ",".join(sorted(by_rank, key=lambda value: int(value))),
                "slowest_activity_rank": slowest,
                "rank_activity_end_skew_us": (
                    round(max(ends.values()) - min(ends.values()), 3)
                    if len(ends) >= 2
                    else None
                ),
                "temporal_attribution_not_dependency_proof": True,
            }
        )
    return output


def _compact_path_rows(path_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bounded lifecycle/rank/role evidence; full step rows remain server-local."""

    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in path_rows:
        key = (row["lifecycle_id"], row["rank_id"], row["execution_role"])
        target = grouped.setdefault(
            key,
            {
                "lifecycle_id": row["lifecycle_id"],
                "config_id": row["config_id"],
                "rank_id": row["rank_id"],
                "execution_role": row["execution_role"],
                "step_count": 0,
                "event_count": 0,
                "clipped_duration_sum_us": 0.0,
            },
        )
        target["step_count"] += 1
        target["event_count"] += int(row["event_count"])
        target["clipped_duration_sum_us"] += float(row["clipped_duration_sum_us"])
    rows = list(grouped.values())
    for row in rows:
        row["clipped_duration_sum_us"] = round(
            float(row["clipped_duration_sum_us"]), 3
        )
        row["duration_sum_is_not_interval_union"] = True
    by_rank: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_rank[(row["lifecycle_id"], row["rank_id"])].append(row)
    selected: list[dict[str, Any]] = []
    for key in sorted(by_rank, key=lambda item: (item[0], int(item[1]))):
        rank_rows = sorted(
            by_rank[key],
            key=lambda row: float(row["clipped_duration_sum_us"]),
            reverse=True,
        )
        required = {
            "analysis_communication_not_overlapped",
            "runtime_collective_queue",
            "actual_device_collective_kernel",
        }
        chosen = rank_rows[:8]
        chosen_roles = {row["execution_role"] for row in chosen}
        chosen.extend(
            row
            for row in rank_rows
            if row["execution_role"] in required
            and row["execution_role"] not in chosen_roles
        )
        selected.extend(chosen)
    return selected


def _candidate_manifest(output: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for name in BOUNDED_CANDIDATES:
        path = output / name
        if path.is_file():
            files.append(
                {
                    "path": name,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "sensitivity": "internal_project_evidence_no_generated_content",
                }
            )
    total = sum(int(row["bytes"]) for row in files)
    if total > 70 * 1024:
        raise ValueError(f"bounded candidate package exceeds 70KB: {total}")
    return {
        "schema": "p6_3c_r3e_f1_a2_candidate_manifest_v1",
        "task_id": TASK_ID,
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "available_methods": ["email", "upload-api", "server-local"],
        "recommended_method": "upload-api",
        "recommended_reason": "one_named_multi_file_session_with_sha_validation",
        "manifest_generated_after_adaptive_review": (
            output.joinpath("adaptive_execution_review.json").is_file()
        ),
        "candidate_file_count": len(files),
        "candidate_total_bytes": total,
        "files": files,
    }


def package(output: Path) -> dict[str, Any]:
    manifest_path = output / "candidate_manifest.server_local.json"
    manifest_path.unlink(missing_ok=True)
    manifest = _candidate_manifest(output)
    _write_json(manifest_path, manifest)
    return manifest


def analyze(
    source: Path,
    source_a1: Path,
    output: Path,
    *,
    expected_ranks: int,
    trace_workspace: Path | None,
    max_events_per_trace: int | None,
) -> dict[str, Any]:
    if source.resolve() == output.resolve() or source_a1.resolve() == output.resolve():
        raise ValueError("derived output must not overwrite source evidence")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"derived output must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    validation = a1.validate_source(
        source, expected_ranks=expected_ranks, trace_workspace=trace_workspace
    )
    source_a1_outcome = _read_json(source_a1 / "scientific_outcome.json")
    a1_exact = (
        source_a1_outcome.get("task_id") == SOURCE_A1_TASK_ID
        and source_a1_outcome.get("cross_rank_trace_complete") is True
    )
    source_before = a1.source_evidence_manifest(source, trace_workspace)
    windows = scheduler_step_windows(source)
    scratch_root = output / ".a2_link_scratch"
    linkage = analyze_trace_linkage(
        source,
        windows,
        trace_workspace=trace_workspace,
        scratch_root=scratch_root,
        max_events_per_trace=max_events_per_trace,
    )
    scratch_root.rmdir()
    source_after = a1.source_evidence_manifest(source, trace_workspace)
    source_unchanged = source_before == source_after
    path_rows = _path_rows(windows, linkage["path_aggregates"])
    cross_rank_rows = _cross_rank_step_rows(windows, path_rows)

    inventory = linkage["inventory"]
    trace_complete = bool(inventory) and all(
        row["parse_complete"] is True and row["event_limit_reached"] is False
        for row in inventory
    )
    ranks_complete = all(
        len({row["rank_id"] for row in inventory if row["lifecycle_id"] == lifecycle})
        == expected_ranks
        for lifecycle in a1.LIFECYCLE_IDS
    )
    clock_complete = bool(inventory) and all(
        row["clock_alignment_reliable"] is True for row in inventory
    )
    step_rank_complete = bool(cross_rank_rows) and all(
        int(row["rank_count"]) == expected_ranks for row in cross_rank_rows
    )
    cross_domain_links = sum(
        int(row["cross_domain_link_value_count"]) for row in inventory
    )
    host_runtime_device_links = sum(
        int(row["host_runtime_device_link_value_count"]) for row in inventory
    )
    dependency_linkage_available = host_runtime_device_links > 0
    descriptive_complete = all(
        (
            validation["source_validation_complete"],
            a1_exact,
            source_unchanged,
            bool(windows),
            trace_complete,
            ranks_complete,
            max_events_per_trace is None,
        )
    )
    causal_bottleneck_resolved = False
    optimization_target_selected = False
    if not descriptive_complete:
        scientific_outcome = "step_flow_linkage_analysis_incomplete"
    elif clock_complete and dependency_linkage_available and step_rank_complete:
        scientific_outcome = (
            "temporal_step_and_cross_domain_links_observed_causal_bottleneck_unresolved"
        )
    elif clock_complete:
        scientific_outcome = (
            "temporal_step_attribution_complete_dependency_linkage_unavailable"
        )
    else:
        scientific_outcome = (
            "trace_schema_censused_scheduler_profiler_clock_linkage_unresolved"
        )

    review = {
        "task_id": TASK_ID,
        "clock_alignment_complete": clock_complete,
        "step_rank_coverage_complete": step_rank_complete,
        "cross_domain_link_value_count": cross_domain_links,
        "host_runtime_device_link_value_count": host_runtime_device_links,
        "dependency_linkage_available": dependency_linkage_available,
        "causal_bottleneck_resolved": causal_bottleneck_resolved,
        "optimization_target_selected": optimization_target_selected,
        "interpretation": (
            "scheduler-window containment and cross-domain identifiers narrow the "
            "execution path, but a target requires repeated dependency-linked final "
            "wait or kernel evidence within pressure steps"
        ),
        "next_action_if_unresolved": (
            "design_a_distinct_R3E_F2_request_scoped_profile_with_explicit_step_and_"
            "worker_rank_correlation_markers;_do_not_repeat_R3D_budget_sweeps"
        ),
        "device_analysis_timeline_rule": (
            "Free_Computing_Communication_and_Notify_Wait_are_derived_analysis_"
            "tracks_not_actual_device_kernels"
        ),
    }

    _write_tsv(output / "scheduler_step_windows.tsv", windows)
    _write_tsv(output / "trace_linkage_inventory.tsv", inventory)
    _write_tsv(output / "link_field_summary.tsv", linkage["field_summary"])
    _write_tsv(output / "cross_domain_link_chains.tsv", linkage["chain_rows"])
    _write_tsv(output / "step_rank_path_full.server_local.tsv", path_rows)
    _write_tsv(output / "step_rank_path_summary.tsv", _compact_path_rows(path_rows))
    _write_tsv(output / "step_cross_rank_summary.tsv", cross_rank_rows)
    _write_json(output / "bottleneck_hypothesis_review.json", review)
    _write_json(
        output / "source_evidence_manifest.json",
        {
            "source_f1": source_after,
            "source_a1_result": str(source_a1),
            "source_a1_task_id_exact": a1_exact,
            "source_a1_scientific_outcome": source_a1_outcome.get(
                "scientific_outcome"
            ),
            "source_result_overwritten": False,
            "source_evidence_unchanged": source_unchanged,
        },
    )
    outcome = {
        "task_id": TASK_ID,
        "source_task_id": a1.SOURCE_TASK_ID,
        "source_a1_task_id": SOURCE_A1_TASK_ID,
        "scientific_outcome": scientific_outcome,
        "parent_a1_outcome_preserved": source_a1_outcome.get("scientific_outcome"),
        "parent_r3d_outcome_preserved": (
            "persistent_prefill_tradeoff_no_candidate_within_bounds"
        ),
        "causal_bottleneck_resolved": causal_bottleneck_resolved,
        "optimization_target_selected": optimization_target_selected,
        "claim_boundary": (
            "request_scoped_temporal_and_identifier_linkage_not_performance_or_"
            "universal_bottleneck_claim"
        ),
    }
    _write_json(output / "scientific_outcome.json", outcome)
    grading = {
        "task_id": TASK_ID,
        "server_grade": (
            "complete_p6_3c_r3e_f1_a2_linkage_evidence"
            if descriptive_complete
            else "incomplete_p6_3c_r3e_f1_a2_linkage_evidence"
        ),
        "evidence_status": "complete" if descriptive_complete else "incomplete",
        "scientific_outcome": scientific_outcome,
        "source_validation_complete": validation["source_validation_complete"],
        "source_a1_task_id_exact": a1_exact,
        "source_evidence_unchanged": source_unchanged,
        "scheduler_window_count": len(windows),
        "trace_complete": trace_complete,
        "rank_coverage_complete": ranks_complete,
        "clock_alignment_complete": clock_complete,
        "step_rank_coverage_complete": step_rank_complete,
        "dependency_linkage_available": dependency_linkage_available,
        "causal_bottleneck_resolved": causal_bottleneck_resolved,
        "optimization_target_selected": optimization_target_selected,
        "npu_used": False,
        "keep_alive_action": "left_running",
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "next_task_authorized": False,
    }
    _write_json(output / "grading_inputs.json", grading)
    _write_json(
        output / "adaptive_execution_review.json",
        {
            "task_id": TASK_ID,
            "operation": "zero_npu_read_only_step_flow_linkage_analysis",
            "adaptive_attempt_count": 0,
            "adaptive_patch_paths": [],
            "scientific_contract_changed": False,
            "source_result_overwritten": False,
            "source_evidence_unchanged": source_unchanged,
            "final_package_must_be_regenerated_after_any_adaptation": True,
        },
    )
    (output / "result_summary.md").write_text(
        "\n".join(
            [
                f"# {TASK_ID} 结果摘要",
                "",
                f"- evidence status: `{grading['evidence_status']}`",
                f"- scientific outcome: `{scientific_outcome}`",
                f"- scheduler windows: `{len(windows)}`；trace/rank complete: `{trace_complete}/{ranks_complete}`。",
                f"- clock alignment complete: `{clock_complete}`；step × rank coverage complete: `{step_rank_complete}`。",
                f"- cross-domain link values: `{cross_domain_links}`；host→runtime→device link values: `{host_runtime_device_links}`。",
                f"- causal bottleneck resolved: `{causal_bottleneck_resolved}`；optimization target selected: `{optimization_target_selected}`。",
                "- scheduler-window containment is temporal evidence. Flow/correlation identifiers are dependency candidates; neither is converted into a causal critical path without a repeated linked final-edge pattern.",
                "- Free/Computing/Communication/Communication(Not Overlapped)/Notify_Wait are device analysis timeline ranges, not actual device kernels.",
                "- A1、F1、R3D 与原 P6.3C 的结论边界均保留；本任务不重跑模型，也不产生新的性能收益声明。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    package(output)
    return grading


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-only")
    validate.add_argument("--source-artifact-dir", type=Path, required=True)
    validate.add_argument("--source-a1-result", type=Path, required=True)
    validate.add_argument("--trace-workspace", type=Path)
    validate.add_argument("--expected-ranks", type=int, default=8)
    derive = sub.add_parser("analyze")
    derive.add_argument("--source-artifact-dir", type=Path, required=True)
    derive.add_argument("--source-a1-result", type=Path, required=True)
    derive.add_argument("--output-dir", type=Path, required=True)
    derive.add_argument("--trace-workspace", type=Path)
    derive.add_argument("--expected-ranks", type=int, default=8)
    derive.add_argument("--max-events-per-trace", type=int)
    package_parser = sub.add_parser("package")
    package_parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "package":
        print(json.dumps(package(args.output_dir), indent=2, sort_keys=True))
        return 0
    validation = a1.validate_source(
        args.source_artifact_dir,
        expected_ranks=args.expected_ranks,
        trace_workspace=args.trace_workspace,
    )
    a1_outcome = _read_json(args.source_a1_result / "scientific_outcome.json")
    validation["source_a1_task_id_exact"] = a1_outcome.get("task_id") == SOURCE_A1_TASK_ID
    validation["source_a1_cross_rank_trace_complete"] = (
        a1_outcome.get("cross_rank_trace_complete") is True
    )
    if args.command == "validate-only":
        print(json.dumps(validation, indent=2, sort_keys=True))
        return 0 if all(
            (
                validation["source_validation_complete"],
                validation["source_a1_task_id_exact"],
                validation["source_a1_cross_rank_trace_complete"],
            )
        ) else 2
    grading = analyze(
        args.source_artifact_dir,
        args.source_a1_result,
        args.output_dir,
        expected_ranks=args.expected_ranks,
        trace_workspace=args.trace_workspace,
        max_events_per_trace=args.max_events_per_trace,
    )
    print(json.dumps(grading, indent=2, sort_keys=True))
    return 0 if grading["evidence_status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
