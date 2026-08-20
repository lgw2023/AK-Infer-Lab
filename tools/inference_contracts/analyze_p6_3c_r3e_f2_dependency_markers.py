"""Analyze explicit R3E-F2 worker ranges and cross-domain dependency edges.

The analyzer performs two complete streaming passes over each trace.  The
first discovers structured worker marker ranges and device-process metadata;
the second keeps only events inside those ranges and builds identifier-linked
host -> runtime -> actual-device-kernel chains.  Generic scheduler-window
overlap and Ascend derived analysis timelines are never accepted as a causal
edge.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts import (  # noqa: E402
    analyze_torch_profiler_traces as trace_analysis,
)
from tools.inference_contracts import (  # noqa: E402
    p6_3c_r3e_f2_dependency_marker as marker_contract,
)
from tools.inference_contracts import (  # noqa: E402
    run_deepseek_p6_3c_r3e_f1_a2_causal_linkage as a2,
)


EXPECTED_RANKS = tuple(str(rank) for rank in range(8))
LINKED_DOMAINS = {
    "host_framework_range",
    "runtime_or_queue_wait",
    "actual_device_kernel",
}
DERIVED_ANALYSIS_NAMES = {
    "free",
    "computing",
    "communication",
    "communication(not overlapped)",
    "notify_wait",
}


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_tsv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    trace_analysis.write_tsv(path, rows)


def _hash_token(kind: str, value: str) -> str:
    return hashlib.sha256(
        f"{kind}\0{value}".encode("utf-8", errors="replace")
    ).hexdigest()[:20]


def _bounded_name(value: object, limit: int = 160) -> str:
    return str(value).replace("\t", " ").replace("\n", " ")[:limit]


@dataclass(frozen=True)
class MarkerRange:
    lifecycle_id: str
    policy_id: str
    timing_context_id: str
    step_index: int
    worker_rank: str
    start_us: float
    end_us: float
    marker_name: str

    @property
    def key(self) -> tuple[str, str, str]:
        return self.lifecycle_id, self.timing_context_id, self.worker_rank


@dataclass
class EventRef:
    event_id: int
    name: str
    domain: str
    domain_basis: str
    category: str
    start_us: float
    end_us: float
    tokens: set[tuple[str, str]] = field(default_factory=set)


@dataclass
class MarkerEvidence:
    marker: MarkerRange
    marker_range_count: int = 1
    events: list[EventRef] = field(default_factory=list)
    analysis_timeline_event_count: int = 0
    device_process_range_event_count: int = 0


def expected_marker_steps(
    artifact_dir: Path, lifecycle_ids: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Read the engine-side selection records, not request contents."""

    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for lifecycle_id in lifecycle_ids:
        trace_root = (
            artifact_dir
            / "lifecycles"
            / lifecycle_id
            / "runtime"
            / "scheduler_trace"
        )
        for path in sorted(trace_root.glob("trace.*.jsonl")):
            for row in _read_jsonl(path):
                if row.get("event") != "dependency_marker_scheduled":
                    continue
                context_id = str(row.get("timing_context_id") or "")
                key = lifecycle_id, context_id
                if not context_id or key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "lifecycle_id": lifecycle_id,
                        "policy_id": str(row.get("policy_id") or ""),
                        "timing_context_id": context_id,
                        "step_index": int(row.get("step_index") or 0),
                        "step_class": "mixed_prefill_decode",
                        "marker_selection_source": "engine_scheduler_output",
                    }
                )
    rows.sort(
        key=lambda row: (
            lifecycle_ids.index(str(row["lifecycle_id"])),
            int(row["step_index"]),
        )
    )
    return rows


def _marker_ranges(
    trace_path: Path, lifecycle_id: str
) -> tuple[list[MarkerRange], set[str], trace_analysis.TraceParseState]:
    state = trace_analysis.TraceParseState()
    device_pids: set[str] = set()
    ranges: list[MarkerRange] = []
    try:
        for event in trace_analysis.iter_trace_events(trace_path, state=state):
            device_pid = trace_analysis._metadata_device_pid(event)  # noqa: SLF001
            if device_pid is not None:
                device_pids.add(device_pid)
            parsed = marker_contract.parse_marker_name(str(event.get("name") or ""))
            timestamp = trace_analysis._event_timestamp(event)  # noqa: SLF001
            if parsed is None or timestamp is None:
                continue
            if parsed["lifecycle_id"] != lifecycle_id:
                continue
            start, duration = timestamp
            if duration <= 0:
                continue
            ranges.append(
                MarkerRange(
                    lifecycle_id=lifecycle_id,
                    policy_id=str(parsed["policy_id"]),
                    timing_context_id=str(parsed["timing_context_id"]),
                    step_index=int(parsed["step_index"]),
                    worker_rank=str(parsed["worker_rank"]),
                    start_us=float(start),
                    end_us=float(start + duration),
                    marker_name=str(event.get("name") or ""),
                )
            )
    except (OSError, UnicodeError, ValueError):
        pass
    return ranges, device_pids, state


def _matching_marker(
    start_us: float, end_us: float, ranges: list[MarkerRange]
) -> MarkerRange | None:
    matches = [
        row
        for row in ranges
        if start_us >= row.start_us and end_us <= row.end_us
    ]
    if not matches:
        return None
    return min(matches, key=lambda row: row.end_us - row.start_us)


def analyze_trace(
    trace_path: Path, lifecycle_id: str
) -> tuple[dict[tuple[str, str, str], MarkerEvidence], dict[str, Any]]:
    ranges, device_pids, first_state = _marker_ranges(trace_path, lifecycle_id)
    evidence: dict[tuple[str, str, str], MarkerEvidence] = {}
    for row in ranges:
        if row.key in evidence:
            evidence[row.key].marker_range_count += 1
        else:
            evidence[row.key] = MarkerEvidence(marker=row)
    second_state = trace_analysis.TraceParseState()
    event_id = 0
    try:
        for event in trace_analysis.iter_trace_events(trace_path, state=second_state):
            timestamp = trace_analysis._event_timestamp(event)  # noqa: SLF001
            if timestamp is None:
                continue
            parsed_marker = marker_contract.parse_marker_name(
                str(event.get("name") or "")
            )
            if parsed_marker is not None:
                continue
            start, duration = timestamp
            if duration <= 0:
                continue
            matched = _matching_marker(float(start), float(start + duration), ranges)
            if matched is None:
                continue
            target = evidence[matched.key]
            domain, domain_basis = trace_analysis.event_domain(event, device_pids)
            name = str(event.get("name") or "")
            if (
                domain == "device_analysis_timeline"
                or name.lower() in DERIVED_ANALYSIS_NAMES
            ):
                target.analysis_timeline_event_count += 1
                continue
            if domain == "device_process_timed_range":
                target.device_process_range_event_count += 1
                continue
            if domain not in LINKED_DOMAINS:
                continue
            tokens = a2._link_tokens(event)  # noqa: SLF001
            target.events.append(
                EventRef(
                    event_id=event_id,
                    name=_bounded_name(name),
                    domain=domain,
                    domain_basis=domain_basis,
                    category=trace_analysis.op_category(name),
                    start_us=float(start),
                    end_us=float(start + duration),
                    tokens=tokens,
                )
            )
            event_id += 1
    except (OSError, UnicodeError, ValueError):
        pass
    inventory = {
        "lifecycle_id": lifecycle_id,
        "rank_id_from_path": trace_analysis.trace_rank(trace_path),
        "trace_path": str(trace_path),
        "trace_bytes": trace_path.stat().st_size,
        "marker_range_count": len(ranges),
        "first_pass_event_count": first_state.events_yielded,
        "first_pass_parse_complete": first_state.parse_complete,
        "first_pass_event_limit_reached": first_state.event_limit_reached,
        "first_pass_parse_error": first_state.parse_error or "",
        "second_pass_event_count": second_state.events_yielded,
        "second_pass_parse_complete": second_state.parse_complete,
        "second_pass_event_limit_reached": second_state.event_limit_reached,
        "second_pass_parse_error": second_state.parse_error or "",
    }
    return evidence, inventory


def _event_pairs(
    left: list[EventRef], right: list[EventRef]
) -> list[tuple[EventRef, EventRef, tuple[str, str]]]:
    right_by_token: dict[tuple[str, str], list[EventRef]] = defaultdict(list)
    for event in right:
        for token in event.tokens:
            right_by_token[token].append(event)
    output: list[tuple[EventRef, EventRef, tuple[str, str]]] = []
    seen: set[tuple[int, int, str, str]] = set()
    for left_event in left:
        for token in left_event.tokens:
            for right_event in right_by_token.get(token, []):
                key = (
                    left_event.event_id,
                    right_event.event_id,
                    token[0],
                    token[1],
                )
                if key in seen:
                    continue
                seen.add(key)
                output.append((left_event, right_event, token))
    return output


def marker_chains(
    evidence: MarkerEvidence,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    hosts = [
        row for row in evidence.events if row.domain == "host_framework_range"
    ]
    runtimes = [
        row for row in evidence.events if row.domain == "runtime_or_queue_wait"
    ]
    devices = [
        row for row in evidence.events if row.domain == "actual_device_kernel"
    ]
    host_runtime = _event_pairs(hosts, runtimes)
    runtime_device = _event_pairs(runtimes, devices)
    hr_by_runtime: dict[
        int, list[tuple[EventRef, EventRef, tuple[str, str]]]
    ] = defaultdict(list)
    rd_by_runtime: dict[
        int, list[tuple[EventRef, EventRef, tuple[str, str]]]
    ] = defaultdict(list)
    for row in host_runtime:
        hr_by_runtime[row[1].event_id].append(row)
    for row in runtime_device:
        rd_by_runtime[row[0].event_id].append(row)

    raw_chains: list[
        tuple[
            EventRef,
            EventRef,
            EventRef,
            tuple[str, str],
            tuple[str, str],
        ]
    ] = []
    for runtime_id in sorted(set(hr_by_runtime) & set(rd_by_runtime)):
        for host, runtime, hr_token in hr_by_runtime[runtime_id]:
            for _, device, rd_token in rd_by_runtime[runtime_id]:
                raw_chains.append((host, runtime, device, hr_token, rd_token))

    terminal_device: EventRef | None = None
    if raw_chains:
        terminal_device = max(
            (row[2] for row in raw_chains),
            key=lambda event: (event.end_us, event.start_us, event.event_id),
        )
    terminal_chains = [
        row for row in raw_chains if row[2].event_id == terminal_device.event_id
    ] if terminal_device is not None else []
    chain_rows: list[dict[str, Any]] = []
    final_signatures: set[str] = set()
    for host, runtime, device, hr_token, rd_token in terminal_chains[:16]:
        signature_payload = (
            f"{hr_token[0]}>{rd_token[0]}>{device.category}>{device.name}"
        )
        signature = hashlib.sha256(signature_payload.encode("utf-8")).hexdigest()[:20]
        final_signatures.add(signature)
        chain_rows.append(
            {
                "lifecycle_id": evidence.marker.lifecycle_id,
                "policy_id": evidence.marker.policy_id,
                "timing_context_id": evidence.marker.timing_context_id,
                "step_index": evidence.marker.step_index,
                "worker_rank": evidence.marker.worker_rank,
                "marker_to_host_link_kind": "instrumented_scope_containment",
                "host_op_name": host.name,
                "host_runtime_link_kind": hr_token[0],
                "host_runtime_link_hash": _hash_token(*hr_token),
                "runtime_op_name": runtime.name,
                "runtime_device_link_kind": rd_token[0],
                "runtime_device_link_hash": _hash_token(*rd_token),
                "actual_device_kernel_name": device.name,
                "actual_device_kernel_category": device.category,
                "actual_device_kernel_provenance": device.domain_basis,
                "final_edge_signature": signature,
                "actual_device_kernel_provenance_required": True,
            }
        )
    summary = {
        "host_event_count": len(hosts),
        "runtime_event_count": len(runtimes),
        "actual_device_kernel_event_count": len(devices),
        "device_analysis_timeline_event_count": (
            evidence.analysis_timeline_event_count
        ),
        "device_process_range_event_count": evidence.device_process_range_event_count,
        "marker_to_host_edge_count": len(hosts),
        "host_runtime_edge_count": len(host_runtime),
        "runtime_actual_device_edge_count": len(runtime_device),
        "complete_chain_count": len(raw_chains),
        "terminal_chain_count": len(terminal_chains),
        "final_edge_signatures": sorted(final_signatures),
    }
    return summary, chain_rows


def _edge_rows(
    marker_range: MarkerRange, summary: dict[str, Any]
) -> list[dict[str, Any]]:
    segments = (
        (
            "marker_to_host_op",
            "instrumented_scope_containment",
            int(summary["marker_to_host_edge_count"]),
            "no_host_framework_range_contained_by_marker",
        ),
        (
            "host_op_to_runtime_launch",
            "shared_profiler_flow_or_correlation_identifier",
            int(summary["host_runtime_edge_count"]),
            "no_shared_identifier_between_host_and_runtime",
        ),
        (
            "runtime_launch_to_actual_device_kernel",
            "shared_profiler_flow_or_correlation_identifier",
            int(summary["runtime_actual_device_edge_count"]),
            "no_shared_identifier_between_runtime_and_actual_device_kernel",
        ),
    )
    return [
        {
            "lifecycle_id": marker_range.lifecycle_id,
            "policy_id": marker_range.policy_id,
            "timing_context_id": marker_range.timing_context_id,
            "step_index": marker_range.step_index,
            "worker_rank": marker_range.worker_rank,
            "edge_segment": segment,
            "required_link_kind": kind,
            "edge_count": count,
            "edge_complete": count > 0,
            "missing_reason": "" if count > 0 else reason,
            "temporal_overlap_alone_is_dependency_proof": False,
        }
        for segment, kind, count, reason in segments
    ]


def _edge_coverage_rows(
    coverage_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate edge coverage without hiding the per-rank table."""

    segments = (
        (
            "marker_to_host_op",
            "instrumented_scope_containment",
            "marker_to_host_edge_count",
            "no_host_framework_range_contained_by_marker",
        ),
        (
            "host_op_to_runtime_launch",
            "shared_profiler_flow_or_correlation_identifier",
            "host_runtime_edge_count",
            "no_shared_identifier_between_host_and_runtime",
        ),
        (
            "runtime_launch_to_actual_device_kernel",
            "shared_profiler_flow_or_correlation_identifier",
            "runtime_actual_device_edge_count",
            "no_shared_identifier_between_runtime_and_actual_device_kernel",
        ),
    )
    output: list[dict[str, Any]] = []
    policy_ids = sorted({str(row["policy_id"]) for row in coverage_rows})
    for policy_id in policy_ids:
        policy_rows = [
            row for row in coverage_rows if str(row["policy_id"]) == policy_id
        ]
        step_ids = sorted({int(row["step_index"]) for row in policy_rows})
        for segment, link_kind, count_field, missing_reason in segments:
            complete_rows = [
                row for row in policy_rows if int(row[count_field]) > 0
            ]
            complete_steps = [
                step_id
                for step_id in step_ids
                if {
                    str(row["worker_rank"])
                    for row in policy_rows
                    if int(row["step_index"]) == step_id
                    and int(row[count_field]) > 0
                }
                == set(EXPECTED_RANKS)
            ]
            expected_rank_rows = len(policy_rows)
            expected_steps = len(step_ids)
            output.append(
                {
                    "policy_id": policy_id,
                    "edge_segment": segment,
                    "required_link_kind": link_kind,
                    "total_edge_count": sum(
                        int(row[count_field]) for row in policy_rows
                    ),
                    "expected_pressure_step_count": expected_steps,
                    "complete_pressure_step_count": len(complete_steps),
                    "complete_pressure_step_indices": ",".join(
                        str(value) for value in complete_steps
                    ),
                    "repeated_pressure_step_coverage_rate": (
                        round(len(complete_steps) / expected_steps, 6)
                        if expected_steps
                        else 0.0
                    ),
                    "repeated_across_multiple_pressure_steps": (
                        len(complete_steps) >= 2
                    ),
                    "expected_rank_row_count": expected_rank_rows,
                    "complete_rank_row_count": len(complete_rows),
                    "rank_row_coverage_rate": (
                        round(len(complete_rows) / expected_rank_rows, 6)
                        if expected_rank_rows
                        else 0.0
                    ),
                    "edge_complete_for_all_expected_rows": (
                        bool(expected_rank_rows)
                        and len(complete_rows) == expected_rank_rows
                    ),
                    "missing_reason": (
                        ""
                        if expected_rank_rows
                        and len(complete_rows) == expected_rank_rows
                        else missing_reason
                    ),
                    "temporal_overlap_alone_is_dependency_proof": False,
                }
            )
    return output


def _stable_final_edge(
    coverage_rows: list[dict[str, Any]], policy_ids: set[str]
) -> tuple[bool, str | None, dict[str, Any]]:
    signature_steps: dict[str, dict[str, dict[int, set[str]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(set))
    )
    for row in coverage_rows:
        policy = str(row["policy_id"])
        step = int(row["step_index"])
        rank = str(row["worker_rank"])
        for signature in str(row.get("final_edge_signatures") or "").split(","):
            if signature:
                signature_steps[signature][policy][step].add(rank)

    qualifying_by_policy: dict[str, set[str]] = {}
    detail: dict[str, Any] = {}
    for policy in sorted(policy_ids):
        qualifying: set[str] = set()
        policy_detail: dict[str, Any] = {}
        for signature, by_policy in signature_steps.items():
            complete_steps = sorted(
                step
                for step, ranks in by_policy.get(policy, {}).items()
                if ranks == set(EXPECTED_RANKS)
            )
            if len(complete_steps) >= 2:
                qualifying.add(signature)
                policy_detail[signature] = complete_steps
        qualifying_by_policy[policy] = qualifying
        detail[policy] = policy_detail
    common = set.intersection(*qualifying_by_policy.values()) if policy_ids else set()
    signature = sorted(common)[0] if common else None
    return signature is not None, signature, detail


def analyze_artifact(
    artifact_dir: Path,
    lifecycle_ids: tuple[str, ...],
    output_dir: Path,
    *,
    stage: str,
) -> dict[str, Any]:
    expected_steps = expected_marker_steps(artifact_dir, lifecycle_ids)
    marker_evidence: dict[tuple[str, str, str], MarkerEvidence] = {}
    inventory_rows: list[dict[str, Any]] = []
    for lifecycle_id in lifecycle_ids:
        root = (
            artifact_dir
            / "lifecycles"
            / lifecycle_id
            / "runtime"
            / "torch_profiler"
        )
        for trace_path in trace_analysis.discover_trace_files(root):
            evidence, inventory = analyze_trace(trace_path, lifecycle_id)
            inventory_rows.append(inventory)
            for key, value in evidence.items():
                if key in marker_evidence:
                    raise ValueError(f"duplicate F2 marker across trace files: {key}")
                marker_evidence[key] = value

    coverage_rows: list[dict[str, Any]] = []
    edge_rank_rows: list[dict[str, Any]] = []
    chain_rows: list[dict[str, Any]] = []
    summaries: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, evidence in sorted(marker_evidence.items()):
        summary, chains = marker_chains(evidence)
        summaries[key] = summary
        edge_rank_rows.extend(_edge_rows(evidence.marker, summary))
        chain_rows.extend(chains)

    for step in expected_steps:
        for rank in EXPECTED_RANKS:
            key = (
                str(step["lifecycle_id"]),
                str(step["timing_context_id"]),
                rank,
            )
            evidence = marker_evidence.get(key)
            summary = summaries.get(key, {})
            coverage_rows.append(
                {
                    **step,
                    "worker_rank": rank,
                    "marker_present": evidence is not None,
                    "marker_range_count": (
                        evidence.marker_range_count if evidence is not None else 0
                    ),
                    "marker_name_schema_exact": (
                        marker_contract.parse_marker_name(
                            evidence.marker.marker_name
                        )
                        is not None
                        if evidence is not None
                        else False
                    ),
                    "marker_to_host_edge_count": int(
                        summary.get("marker_to_host_edge_count") or 0
                    ),
                    "host_runtime_edge_count": int(
                        summary.get("host_runtime_edge_count") or 0
                    ),
                    "runtime_actual_device_edge_count": int(
                        summary.get("runtime_actual_device_edge_count") or 0
                    ),
                    "complete_chain_count": int(
                        summary.get("complete_chain_count") or 0
                    ),
                    "final_edge_signatures": ",".join(
                        summary.get("final_edge_signatures") or []
                    ),
                    "derived_analysis_timeline_excluded": True,
                }
            )

    trace_parse_complete = bool(inventory_rows) and all(
        row["first_pass_parse_complete"] is True
        and row["second_pass_parse_complete"] is True
        and row["first_pass_event_limit_reached"] is False
        and row["second_pass_event_limit_reached"] is False
        for row in inventory_rows
    )
    ranks_by_lifecycle = {
        lifecycle_id: {
            str(row["rank_id_from_path"])
            for row in inventory_rows
            if row["lifecycle_id"] == lifecycle_id
        }
        for lifecycle_id in lifecycle_ids
    }
    trace_rank_coverage_complete = all(
        ranks == set(EXPECTED_RANKS) for ranks in ranks_by_lifecycle.values()
    )
    expected_marker_rank_rows = len(expected_steps) * len(EXPECTED_RANKS)
    marker_presence_complete = bool(coverage_rows) and all(
        row["marker_present"] is True
        and int(row["marker_range_count"]) == 1
        and row["marker_name_schema_exact"] is True
        for row in coverage_rows
    )
    full_chain_complete = bool(coverage_rows) and all(
        int(row["complete_chain_count"]) > 0 for row in coverage_rows
    )
    s1_authorized = all(
        (
            stage.upper() == "S1",
            len(expected_steps) == 1,
            trace_parse_complete,
            trace_rank_coverage_complete,
            marker_presence_complete,
            full_chain_complete,
        )
    )
    policy_ids = {str(row["policy_id"]) for row in expected_steps}
    stable, stable_signature, stable_detail = _stable_final_edge(
        coverage_rows, policy_ids
    )
    causal_bottleneck_resolved = all(
        (
            stage.upper() == "FINAL",
            len(policy_ids) >= 2,
            trace_parse_complete,
            trace_rank_coverage_complete,
            marker_presence_complete,
            full_chain_complete,
            stable,
        )
    )
    missing_counts = {
        "marker_to_host_op": sum(
            int(row["marker_to_host_edge_count"]) == 0 for row in coverage_rows
        ),
        "host_op_to_runtime_launch": sum(
            int(row["host_runtime_edge_count"]) == 0 for row in coverage_rows
        ),
        "runtime_launch_to_actual_device_kernel": sum(
            int(row["runtime_actual_device_edge_count"]) == 0
            for row in coverage_rows
        ),
    }
    missing_segments = [
        segment for segment, count in missing_counts.items() if count > 0
    ]
    dependency_linkage_gap = (
        "none"
        if not missing_segments and marker_presence_complete
        else ";".join(
            [
                *( ["worker_marker_missing_or_rank_incomplete"]
                   if not marker_presence_complete else [] ),
                *missing_segments,
            ]
        )
    )
    summary = {
        "schema": "p6_3c_r3e_f2_marker_propagation_summary_v1",
        "stage": stage.upper(),
        "lifecycle_ids": list(lifecycle_ids),
        "policy_ids": sorted(policy_ids),
        "expected_pressure_step_count": len(expected_steps),
        "expected_marker_rank_row_count": expected_marker_rank_rows,
        "observed_marker_rank_row_count": sum(
            row["marker_present"] is True for row in coverage_rows
        ),
        "trace_parse_complete": trace_parse_complete,
        "trace_rank_coverage_complete": trace_rank_coverage_complete,
        "marker_presence_complete": marker_presence_complete,
        "full_dependency_chain_complete": full_chain_complete,
        "s2_authorized": s1_authorized,
        "causal_bottleneck_resolved": causal_bottleneck_resolved,
        "optimization_target_selected": False,
        "stable_final_edge_signature": stable_signature,
        "stable_final_edge_detail": stable_detail,
        "dependency_linkage_gap": dependency_linkage_gap,
        "missing_edge_rank_row_counts": missing_counts,
        "marker_scope_semantics": (
            "instrumented_worker_execute_model_scope_not_generic_temporal_overlap"
        ),
        "device_analysis_timeline_rule": (
            "Free_Computing_Communication_CommunicationNotOverlapped_and_"
            "Notify_Wait_are_derived_analysis_tracks_not_actual_device_kernels"
        ),
    }
    review = {
        **summary,
        "repeated_final_edge_required_for_causal_resolution": True,
        "repeated_final_edge_gate": (
            "same_link_kind_and_actual_kernel_signature_on_8_of_8_ranks_"
            "for_at_least_two_pressure_steps_in_each_executed_S2_policy"
        ),
        "performance_gain_claimed": False,
        "automatic_optimization_target_selection_allowed": False,
    }
    _write_json(output_dir / "marker_propagation_summary.json", summary)
    _write_tsv(output_dir / "step_rank_marker_coverage.tsv", coverage_rows)
    _write_tsv(
        output_dir / "dependency_edge_summary.tsv",
        _edge_coverage_rows(coverage_rows),
    )
    _write_tsv(
        output_dir / "dependency_edge_rank_detail.server_local.tsv",
        edge_rank_rows,
    )
    _write_tsv(output_dir / "cross_domain_link_chains.tsv", chain_rows)
    _write_tsv(output_dir / "trace_marker_inventory.server_local.tsv", inventory_rows)
    _write_json(output_dir / "bottleneck_hypothesis_review.json", review)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=("S1", "FINAL"), required=True)
    parser.add_argument("--lifecycle-id", action="append", required=True)
    args = parser.parse_args(argv)
    summary = analyze_artifact(
        args.artifact_dir,
        tuple(args.lifecycle_id),
        args.output_dir,
        stage=args.stage,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["trace_parse_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
