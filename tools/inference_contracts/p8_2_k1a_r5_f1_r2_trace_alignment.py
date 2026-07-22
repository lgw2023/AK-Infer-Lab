from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.p8_2_k1a_r5_f1_r1_request_local_pressure import (
    derive_request_local_pressure_candidate,
)


TARGET_BLOCK_COUNT = 64
EXPECTED_CANDIDATE_CONTEXT_TOKENS = 36800
EXPECTED_CALIBRATION_GRADE = (
    "candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure"
)
EXPECTED_L2_GRADE = "red_p8_2_k1a_r5_f1_r1_fixed_pressure_target_lost"
MID_REQUEST_ENDPOINT_MISMATCH_GRADE = (
    "candidate_p8_2_k1a_r5_f1_r2_mid_request_window_endpoint_mismatch"
)
NO_L2_CPU_ONLY_WINDOW_GRADE = (
    "candidate_p8_2_k1a_r5_f1_r2_no_l2_cpu_only_window"
)
BLOCKED_GRADE = "blocked_p8_2_k1a_r5_f1_r2_trace_alignment_incomplete"
SENSITIVITY = "bounded_operational_metadata_no_content_or_token_ids"
MAX_TRANSFER_BYTES = 71680


def _timestamp(row: dict[str, Any]) -> int:
    return int(row.get("timestamp_ns") or 0)


def _pressure_endpoint(timeline: dict[str, Any]) -> dict[str, Any]:
    samples = timeline.get("gate_samples")
    if not isinstance(samples, list):
        return {}
    matches = [
        row
        for row in samples
        if isinstance(row, dict) and row.get("after_role") == "pressure_01"
    ]
    return matches[-1] if matches else {}


def _progress_histogram(rows: list[dict[str, Any]]) -> dict[str, int]:
    values = Counter(
        int(row.get("num_scheduled_tokens") or 0)
        for row in rows
        if row.get("event") == "request_local_pressure_progress"
        and row.get("contract_role") == "pressure_01"
        and row.get("request_local_progress_exact") is True
        and int(row.get("num_scheduled_tokens") or 0) > 0
    )
    return {str(key): values[key] for key in sorted(values)}


def align_calibration_and_l2(
    *,
    calibration_rows: list[dict[str, Any]],
    calibration_pressure_start_ns: int,
    l2_rows: list[dict[str, Any]],
    l2_pressure_start_ns: int,
    l2_endpoint_timeline: dict[str, Any],
) -> dict[str, Any]:
    calibration = derive_request_local_pressure_candidate(calibration_rows)
    calibration_pressure_rows = sorted(
        (row for row in calibration_rows if _timestamp(row) >= calibration_pressure_start_ns),
        key=_timestamp,
    )
    l2_pressure_rows = sorted(
        (row for row in l2_rows if _timestamp(row) >= l2_pressure_start_ns),
        key=_timestamp,
    )
    snapshots = [
        row
        for row in l2_pressure_rows
        if row.get("event") == "target_residency_snapshot"
        and int(row.get("target_block_count") or 0) == TARGET_BLOCK_COUNT
    ]
    cpu_only = [
        row
        for row in snapshots
        if int(row.get("cpu_target_block_count") or 0) == TARGET_BLOCK_COUNT
        and int(row.get("gpu_target_block_count") or 0) == 0
    ]
    cpu_evictions = [
        row
        for row in l2_pressure_rows
        if row.get("event") == "target_cache_evicted"
        and row.get("tier") == "cpu"
        and int(row.get("target_evicted_count") or 0) > 0
    ]
    first_cpu_eviction_ns = min((_timestamp(row) for row in cpu_evictions), default=None)
    cpu_only_before_eviction = bool(
        [
            row
            for row in cpu_only
            if first_cpu_eviction_ns is None or _timestamp(row) < first_cpu_eviction_ns
        ]
    )
    endpoint = _pressure_endpoint(l2_endpoint_timeline)
    endpoint_cpu = (
        int(endpoint.get("latest_cpu_target_block_count"))
        if endpoint.get("latest_cpu_target_block_count") is not None
        else None
    )
    endpoint_gpu = (
        int(endpoint.get("latest_gpu_target_block_count"))
        if endpoint.get("latest_gpu_target_block_count") is not None
        else None
    )
    endpoint_target_lost = all(
        (
            endpoint.get("decision") == "cpu_target_lost",
            endpoint_cpu is not None and endpoint_cpu < TARGET_BLOCK_COUNT,
            endpoint_gpu == 0,
            l2_endpoint_timeline.get("restore_sent") is False,
        )
    )
    calibration_exact = all(
        (
            calibration.get("request_local_progress_source_exact") is True,
            calibration.get("formal_fixed_l2_candidate_allowed") is True,
            int(calibration.get("candidate_pressure_context_tokens") or 0)
            == EXPECTED_CANDIDATE_CONTEXT_TOKENS,
        )
    )
    l2_snapshot_coverage = bool(snapshots)
    if (
        calibration_exact
        and l2_snapshot_coverage
        and cpu_only_before_eviction
        and endpoint_target_lost
    ):
        grade = MID_REQUEST_ENDPOINT_MISMATCH_GRADE
    elif (
        calibration_exact
        and l2_snapshot_coverage
        and not cpu_only
        and cpu_evictions
        and endpoint_target_lost
    ):
        grade = NO_L2_CPU_ONLY_WINDOW_GRADE
    else:
        grade = BLOCKED_GRADE

    reason_counts = Counter(str(row.get("reason") or "missing") for row in snapshots)
    state_counts = Counter(
        (
            int(row.get("cpu_target_block_count") or 0),
            int(row.get("gpu_target_block_count") or 0),
        )
        for row in snapshots
    )
    first_cpu_only = min((_timestamp(row) for row in cpu_only), default=None)
    return {
        "schema_version": "p8_2_k1a_r5_f1_r2_trace_alignment_v1",
        "server_grade": grade,
        "calibration_pressure_start_marker_exact": calibration_pressure_start_ns > 0,
        "calibration_pressure_event_count": len(calibration_pressure_rows),
        "calibration_progress_event_count": calibration[
            "progress_event_count"
        ],
        "calibration_progress_sequence_exact": calibration[
            "request_local_progress_source_exact"
        ],
        "calibration_scheduled_token_histogram": _progress_histogram(
            calibration_pressure_rows
        ),
        "calibration_candidate_total_tokens": calibration[
            "candidate_pressure_total_tokens"
        ],
        "calibration_candidate_context_tokens": calibration[
            "candidate_pressure_context_tokens"
        ],
        "calibration_cpu_only_progress_event_count": calibration[
            "exact_cpu_only_progress_event_count"
        ],
        "calibration_candidate_reproduced_from_raw_trace": calibration_exact,
        "l2_pressure_start_marker_exact": l2_pressure_start_ns > 0,
        "l2_pressure_event_count": len(l2_pressure_rows),
        "l2_pressure_snapshot_count": len(snapshots),
        "l2_snapshot_reason_histogram": {
            key: reason_counts[key] for key in sorted(reason_counts)
        },
        "l2_residency_state_histogram": {
            f"cpu_{cpu}_gpu_{gpu}": state_counts[(cpu, gpu)]
            for cpu, gpu in sorted(state_counts)
        },
        "l2_cpu_only_snapshot_count": len(cpu_only),
        "l2_cpu_only_first_offset_ns": (
            first_cpu_only - l2_pressure_start_ns
            if first_cpu_only is not None
            else None
        ),
        "l2_cpu_target_eviction_event_count": len(cpu_evictions),
        "l2_first_cpu_target_eviction_offset_ns": (
            first_cpu_eviction_ns - l2_pressure_start_ns
            if first_cpu_eviction_ns is not None
            else None
        ),
        "l2_cpu_only_before_first_cpu_eviction": cpu_only_before_eviction,
        "l2_endpoint_gate_sample_present": bool(endpoint),
        "l2_endpoint_decision": endpoint.get("decision"),
        "l2_endpoint_cpu_target_block_count": endpoint_cpu,
        "l2_endpoint_gpu_target_block_count": endpoint_gpu,
        "l2_endpoint_target_lost": endpoint_target_lost,
        "l2_restore_sent": l2_endpoint_timeline.get("restore_sent") is True,
        "calibration_window_reproduced_in_fixed_l2": cpu_only_before_eviction,
        "mid_request_window_to_endpoint_gate_mismatch_observed": (
            grade == MID_REQUEST_ENDPOINT_MISMATCH_GRADE
        ),
        "request_end_trace_event_present": any(
            row.get("event") == "request_end" for row in l2_rows
        ),
        "request_end_timestamp_alignment_exact": False,
        "request_end_alignment_limitation": (
            "observer trace uses wall-clock timestamp_ns while client request timing "
            "uses monotonic_ns and no request_end event is emitted; endpoint ordering "
            "is accepted only from the controller contract and gate timeline"
        ),
        "current_candidate_rule_uses_mid_request_after_schedule_state": True,
        "current_controller_gate_runs_after_pressure_request_returns": True,
        "pressure_context_change_authorized": False,
        "context_search_or_sweep_authorized": False,
        "new_npu_lifecycle_authorized": False,
        "h2d_restore_mechanism_accepted": False,
        "performance_reference_accepted": False,
        "unique_cause_proven": False,
        "k2_authorized": False,
        "p8_3_i1_authorized": False,
        "next_task_authorized": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
        "generated_content_retained": False,
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _read_trace_dir(trace_dir: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    paths = sorted(trace_dir.glob("h2d-residency.*.jsonl"))
    if not paths:
        raise ValueError(f"no h2d residency trace files: {trace_dir}")
    rows: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"trace row is not an object: {path}")
            rows.append(value)
    return rows, paths


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selected_inventory(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    return {
        label: {
            "source_relative_path": str(path),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for label, path in sorted(paths.items())
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_manifest(output: Path, payloads: list[str]) -> None:
    files = {
        relative: {
            "bytes": (output / relative).stat().st_size,
            "sha256": _sha256(output / relative),
            "sensitivity": SENSITIVITY,
        }
        for relative in payloads
    }
    manifest_path = output / "candidate_manifest.server_local.json"
    manifest_bytes = 0
    while True:
        value = {
            "schema_version": "p8_2_k1a_r5_f1_r2_candidate_manifest_v1",
            "files": files,
            "payload_file_count": len(files),
            "payload_total_bytes": sum(row["bytes"] for row in files.values()),
            "manifest_control_file": manifest_path.name,
            "manifest_bytes": manifest_bytes,
            "transfer_file_count": len(files) + 1,
            "transfer_total_bytes": (
                sum(row["bytes"] for row in files.values()) + manifest_bytes
            ),
            "max_transfer_bytes": MAX_TRANSFER_BYTES,
            "sensitivity": SENSITIVITY,
            "raw_trace_content_retained": False,
            "generated_content_retained": False,
            "token_ids_retained": False,
            "request_ids_retained": False,
            "raw_hash_values_retained": False,
            "result_transfer_authorized": True,
            "transfer_method_selected": False,
            "automatic_transfer_allowed": False,
        }
        _write_json(manifest_path, value)
        actual = manifest_path.stat().st_size
        if actual == manifest_bytes:
            break
        manifest_bytes = actual
    if value["transfer_total_bytes"] > MAX_TRANSFER_BYTES:
        raise ValueError("bounded transfer package exceeds 71680 bytes")


def _validate_root_boundary(output: Path, sources: list[Path]) -> None:
    if output.exists():
        raise FileExistsError(f"output directory exists: {output}")
    for source in sources:
        if output == source or source in output.parents or output in source.parents:
            raise ValueError("output and immutable source roots must be disjoint")


def analyze(args: argparse.Namespace) -> int:
    calibration_root = args.calibration_root.resolve()
    calibration_analysis_root = args.calibration_analysis_root.resolve()
    l2_root = args.l2_root.resolve()
    output = args.output_dir.resolve()
    _validate_root_boundary(
        output, [calibration_root, calibration_analysis_root, l2_root]
    )

    calibration_trace_dir = calibration_root / "runtime/offload_trace"
    l2_trace_dir = l2_root / "runtime/offload_trace"
    calibration_rows, calibration_trace_paths = _read_trace_dir(
        calibration_trace_dir
    )
    l2_rows, l2_trace_paths = _read_trace_dir(l2_trace_dir)
    calibration_role_path = (
        calibration_root / "runtime/request_control/active_role.json"
    )
    l2_role_path = l2_root / "runtime/request_control/active_role.json"
    timeline_path = l2_root / "runtime/request_control/residency_gate_timeline.json"
    calibration_grading_path = calibration_analysis_root / "grading_summary.json"
    calibration_candidate_path = calibration_analysis_root / "pressure_candidate.json"
    l2_grading_path = l2_root / "grading_summary.json"
    selected_paths = {
        "calibration_active_role": calibration_role_path,
        "calibration_analysis_grading": calibration_grading_path,
        "calibration_analysis_candidate": calibration_candidate_path,
        "l2_active_role": l2_role_path,
        "l2_endpoint_timeline": timeline_path,
        "l2_grading": l2_grading_path,
    }
    selected_paths.update(
        {
            f"calibration_trace_{index:03d}": path
            for index, path in enumerate(calibration_trace_paths, start=1)
        }
    )
    selected_paths.update(
        {
            f"l2_trace_{index:03d}": path
            for index, path in enumerate(l2_trace_paths, start=1)
        }
    )
    before = _selected_inventory(selected_paths)

    calibration_role = _read_json(calibration_role_path)
    l2_role = _read_json(l2_role_path)
    calibration_grading = _read_json(calibration_grading_path)
    calibration_candidate = _read_json(calibration_candidate_path)
    l2_grading = _read_json(l2_grading_path)
    timeline = _read_json(timeline_path)
    if calibration_role.get("role") != "pressure_01":
        raise ValueError("calibration active role is not pressure_01")
    if l2_role.get("role") != "pressure_01":
        raise ValueError("fixed L2 active role is not pressure_01")
    if calibration_grading.get("server_grade") != EXPECTED_CALIBRATION_GRADE:
        raise ValueError("calibration ready grade is not the accepted F1-R1 grade")
    if calibration_grading.get("formal_fixed_l2_candidate_allowed") is not True:
        raise ValueError("calibration analysis did not allow the fixed L2 candidate")
    if int(calibration_candidate.get("candidate_pressure_context_tokens") or 0) != (
        EXPECTED_CANDIDATE_CONTEXT_TOKENS
    ):
        raise ValueError("calibration candidate context is not 36800")
    if calibration_candidate.get("candidate_is_fixed_not_search") is not True:
        raise ValueError("calibration candidate is not fixed and non-search")
    if l2_grading.get("server_grade") != EXPECTED_L2_GRADE:
        raise ValueError("fixed L2 grade is not the accepted target-lost red")

    alignment = align_calibration_and_l2(
        calibration_rows=calibration_rows,
        calibration_pressure_start_ns=int(
            calibration_role.get("updated_timestamp_ns") or 0
        ),
        l2_rows=l2_rows,
        l2_pressure_start_ns=int(l2_role.get("updated_timestamp_ns") or 0),
        l2_endpoint_timeline=timeline,
    )
    after = _selected_inventory(selected_paths)
    unchanged = before == after
    if not unchanged:
        raise ValueError("immutable source evidence changed during analysis")

    provenance = {
        "schema_version": "p8_2_k1a_r5_f1_r2_source_provenance_v1",
        "selected_source_files_before": before,
        "selected_source_files_after": after,
        "all_source_files_unchanged": unchanged,
        "calibration_raw_trace_file_count": len(calibration_trace_paths),
        "l2_raw_trace_file_count": len(l2_trace_paths),
        "raw_trace_content_retained": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
        "generated_content_retained": False,
    }
    grade = str(alignment["server_grade"])
    grading = {
        "schema_version": "p8_2_k1a_r5_f1_r2_grading_v1",
        "server_grade": grade,
        "source_evidence_unchanged": unchanged,
        "calibration_parent_grade": calibration_grading.get("server_grade"),
        "l2_parent_grade": l2_grading.get("server_grade"),
        "l2_parent_request_count": l2_grading.get("request_count"),
        "l2_parent_successful_request_count": l2_grading.get(
            "successful_request_count"
        ),
        "l2_parent_cleanup": l2_grading.get("cleanup"),
        "mid_request_window_to_endpoint_gate_mismatch_observed": alignment[
            "mid_request_window_to_endpoint_gate_mismatch_observed"
        ],
        "request_end_timestamp_alignment_exact": False,
        "new_npu_lifecycle_authorized": False,
        "model_requests_authorized": False,
        "context_search_or_sweep_authorized": False,
        "h2d_restore_mechanism_accepted": False,
        "performance_reference_accepted": False,
        "unique_cause_proven": False,
        "next_task_authorized": False,
        "claim_boundary": (
            "server_local_raw_trace_timing_alignment_only_no_new_runtime_"
            "h2d_performance_or_unique_cause_claim"
        ),
    }
    if grade == MID_REQUEST_ENDPOINT_MISMATCH_GRADE:
        conclusion = (
            "The fixed L2 raw trace contains a complete CPU-only target window "
            "before CPU target eviction, while the post-request gate records target "
            "loss. This proves an observation-point mismatch, not a unique cause."
        )
    elif grade == NO_L2_CPU_ONLY_WINDOW_GRADE:
        conclusion = (
            "The fixed L2 raw trace does not contain a complete CPU-only target "
            "window before the post-request target-lost endpoint."
        )
    else:
        conclusion = (
            "The retained evidence is insufficient to distinguish a mid-request "
            "window from an endpoint-only target-loss path."
        )

    output.mkdir(parents=True)
    values = {
        "trace_alignment_summary.json": alignment,
        "source_evidence_provenance.json": provenance,
        "grading_summary.json": grading,
    }
    for relative, value in values.items():
        _write_json(output / relative, value)
    (output / "task_grade.txt").write_text(grade + "\n", encoding="utf-8")
    (output / "result_summary.md").write_text(
        "\n".join(
            (
                "# P8.2-K1A-R5-F1-R2 raw trace timing alignment",
                "",
                f"- grade: `{grade}`",
                f"- conclusion: {conclusion}",
                "- no NPU/vLLM lifecycle or model request was started by this analysis.",
                "- no context change, sweep, H2D, performance, K2, P8.3-I1 or unique-cause claim is authorized.",
                "",
            )
        ),
        encoding="utf-8",
    )
    payloads = [*values, "task_grade.txt", "result_summary.md"]
    _write_manifest(output, payloads)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--calibration-root", type=Path, required=True)
    analyze_parser.add_argument(
        "--calibration-analysis-root", type=Path, required=True
    )
    analyze_parser.add_argument("--l2-root", type=Path, required=True)
    analyze_parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "analyze":
        return analyze(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
