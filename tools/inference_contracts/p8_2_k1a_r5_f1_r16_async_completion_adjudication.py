from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.p8_2_k1a_simple_cpu_offload_observer import (
    summarize_trace_rows,
)


TASK_ID = "p8_2_k1a_r5_f1_r16_async_completion_semantics_2026_0727"
EXPECTED_WORLD_SIZE = 8
EXPECTED_PARENT_GRADE = (
    "red_p8_2_k1a_r5_f1_r15_h2d_evidence_incomplete"
)
GREEN_GRADE = (
    "green_p8_2_k1a_r5_f1_r16_restore_h2d_mechanism_closed"
)
RED_GRADE = (
    "red_p8_2_k1a_r5_f1_r16_async_completion_trace_incomplete"
)
SENSITIVITY = "bounded_operational_metadata_no_content_or_token_ids"
MAX_TRANSFER_BYTES = 71680
DEFAULT_AUDIT = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r16_async_completion_semantics_audit.yaml"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _trace_inventory(trace_paths: list[Path], root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    total_bytes = 0
    for path in trace_paths:
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        file_sha = _sha256(path)
        total_bytes += size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_sha.encode("ascii"))
        digest.update(b"\n")
    return {
        "file_count": len(trace_paths),
        "total_bytes": total_bytes,
        "tree_sha256": digest.hexdigest(),
    }


def _read_trace_rows(
    trace_dir: Path,
) -> tuple[list[dict[str, Any]], list[Path]]:
    paths = sorted(trace_dir.glob("h2d-residency.*.jsonl"))
    if not paths:
        raise ValueError(f"no retained R15 trace files: {trace_dir}")
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


def _event_pids(
    rows: list[dict[str, Any]],
    *,
    event: str,
    direction: str | None = None,
) -> set[int]:
    return {
        int(row["pid"])
        for row in rows
        if row.get("event") == event
        and (direction is None or row.get("direction") == direction)
        and row.get("pid") is not None
    }


def build_worker_completion_rollup(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    copy_thread_started = _event_pids(rows, event="copy_thread_started")
    worker_rows: list[dict[str, Any]] = []
    completion_without_live_pending_count = 0
    for direction in ("d2h", "h2d"):
        submitted = _event_pids(
            rows, event="device_copy_submitted", direction=direction
        )
        ordered_pids = sorted(submitted)
        for ordinal, pid in enumerate(ordered_pids, start=1):
            matching = [
                row
                for row in rows
                if row.get("direction") == direction
                and row.get("pid") is not None
                and int(row["pid"]) == pid
            ]
            events = {str(row.get("event") or "") for row in matching}
            poll_entries = [
                row
                for row in matching
                if row.get("event") == "transfer_poll_entered"
            ]
            live_pending = any(
                int(row.get("pending_event_count") or 0) > 0
                and row.get("copy_thread_alive") is True
                for row in poll_entries
            )
            completed = "transfer_completed" in events
            if completed and not live_pending:
                completion_without_live_pending_count += 1
            worker_rows.append(
                {
                    "worker": f"{direction}_worker_{ordinal:02d}",
                    "direction": direction,
                    "copy_thread_started": pid in copy_thread_started,
                    "submitted": "device_copy_submitted" in events,
                    "enqueued": "device_copy_enqueued" in events,
                    "copy_entered": "copy_blocks_entered" in events,
                    "copy_returned": "copy_blocks_returned" in events,
                    "poll_entered": bool(poll_entries),
                    "poll_returned": "transfer_poll_returned" in events,
                    "poll_live_pending_observed": live_pending,
                    "poll_pending_positive_observed": any(
                        int(row.get("pending_event_count") or 0) > 0
                        for row in poll_entries
                    ),
                    "poll_copy_thread_inactive_observed": any(
                        row.get("copy_thread_alive") is False
                        for row in poll_entries
                    ),
                    "completed": completed,
                    "completion_without_live_pending": (
                        completed and not live_pending
                    ),
                }
            )
    return {
        "schema_version": (
            "p8_2_k1a_r5_f1_r16_worker_completion_rollup_v1"
        ),
        "worker_rows": worker_rows,
        "worker_identity": (
            "direction-local ordinal sorted by process id; raw process ids "
            "are not retained"
        ),
        "completion_without_live_pending_worker_count": (
            completion_without_live_pending_count
        ),
        "raw_process_ids_retained": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
        "raw_hash_values_retained": False,
        "generated_content_retained": False,
    }


def adjudicate_async_completion(
    rows: list[dict[str, Any]],
    *,
    parent_grading: dict[str, Any],
    parent_trigger: dict[str, Any],
    parent_transfer: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    recomputed = summarize_trace_rows(
        rows,
        expected_world_size=EXPECTED_WORLD_SIZE,
        restore_request_suffix="restore_follower",
    )
    parent_exact = all(
        (
            parent_grading.get("server_grade") == EXPECTED_PARENT_GRADE,
            parent_grading.get("experimental_terminal")
            == "restore_request_completed",
            parent_grading.get("operational_grade")
            == "operational_recovery_clean",
            parent_grading.get("restore_step_lineage_primary_class")
            == "delayed_external_then_reqs_to_load",
            parent_grading.get("restore_h2d_path_class")
            == "via_reqs_to_load",
            parent_grading.get("restore_pairing_repair_applied") is True,
            parent_grading.get("restore_any_entered_reqs_to_load") is True,
            parent_trigger.get("h2d_restore_mechanism_candidate") is True,
            parent_trigger.get("target_cpu_only_residency_observed") is True,
            parent_transfer.get("h2d_restore_complete") is True,
            parent_transfer.get("h2d_async_copy_pipeline_exact") is False,
            int(
                parent_transfer.get(
                    "h2d_poll_event_visible_worker_count"
                )
                or 0
            )
            == 7,
            int(parent_transfer.get("h2d_completed_worker_count") or 0)
            == EXPECTED_WORLD_SIZE,
            int(parent_transfer.get("async_copy_failure_event_count") or 0)
            == 0,
        )
    )
    completion_exact = all(
        (
            recomputed.get("d2h_store_complete") is True,
            recomputed.get("h2d_restore_complete") is True,
            recomputed.get("d2h_async_copy_pipeline_exact") is True,
            recomputed.get("h2d_async_copy_pipeline_exact") is True,
            recomputed.get("h2d_poll_returned_completion_exact") is True,
            int(recomputed.get("h2d_worker_count") or 0)
            == EXPECTED_WORLD_SIZE,
            int(recomputed.get("h2d_completed_worker_count") or 0)
            == EXPECTED_WORLD_SIZE,
            int(recomputed.get("async_copy_failure_event_count") or 0) == 0,
        )
    )
    live_pending_exact = (
        recomputed.get("h2d_poll_live_pending_coverage_exact") is True
    )
    grade = GREEN_GRADE if parent_exact and completion_exact else RED_GRADE
    selected_fields = {
        key: recomputed.get(key)
        for key in (
            "trace_event_count",
            "expected_world_size",
            "d2h_worker_count",
            "h2d_worker_count",
            "d2h_completed_worker_count",
            "h2d_completed_worker_count",
            "d2h_enqueued_worker_count",
            "h2d_enqueued_worker_count",
            "d2h_copy_blocks_entered_worker_count",
            "h2d_copy_blocks_entered_worker_count",
            "d2h_copy_blocks_returned_worker_count",
            "h2d_copy_blocks_returned_worker_count",
            "d2h_poll_entered_worker_count",
            "h2d_poll_entered_worker_count",
            "d2h_poll_returned_worker_count",
            "h2d_poll_returned_worker_count",
            "d2h_poll_completed_worker_count",
            "h2d_poll_completed_worker_count",
            "d2h_poll_live_pending_worker_count",
            "h2d_poll_live_pending_worker_count",
            "d2h_poll_live_pending_coverage_exact",
            "h2d_poll_live_pending_coverage_exact",
            "d2h_poll_returned_completion_exact",
            "h2d_poll_returned_completion_exact",
            "copy_thread_started_worker_count",
            "d2h_bytes_total",
            "h2d_bytes_total",
            "async_copy_failure_event_count",
            "d2h_store_complete",
            "h2d_restore_complete",
            "d2h_async_copy_pipeline_exact",
            "h2d_async_copy_pipeline_exact",
            "restore_step_lineage_primary_class",
            "restore_h2d_path_class",
            "restore_any_pairing_repair_applied",
            "restore_any_entered_reqs_to_load",
        )
    }
    summary = {
        "schema_version": (
            "p8_2_k1a_r5_f1_r16_async_completion_adjudication_v1"
        ),
        "task_id": TASK_ID,
        "server_grade": grade,
        "parent_contract_exact": parent_exact,
        "async_completion_evidence_exact": completion_exact,
        "h2d_poll_live_pending_is_diagnostic_only": True,
        "h2d_poll_live_pending_coverage_exact": live_pending_exact,
        "r15_false_negative_gate_observed": (
            parent_exact and completion_exact and not live_pending_exact
        ),
        "completion_semantics": (
            "submitted=enqueued=copy_entered=copy_returned=completed for "
            "the same worker set, all copy threads started, poll completion "
            "returned, and zero async failure events"
        ),
        "live_pending_semantics": (
            "point-in-time observation at poll entry; not required after "
            "transfer completion"
        ),
        "recomputed_transfer": selected_fields,
        "npu_started": False,
        "vllm_started": False,
        "model_requests_sent": 0,
        "performance_claim_authorized": False,
        "unique_cause_claim_authorized": False,
        "next_task_authorized": False,
        "k2_authorized": False,
        "p8_3_i1_authorized": False,
    }
    return summary, recomputed


def _validate_parent_hashes(
    parent_root: Path,
    audit: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    expected = audit.get("accepted_f1_r15_result", {}).get(
        "source_file_sha256"
    )
    if not isinstance(expected, dict) or not expected:
        raise ValueError("R16 audit does not define R15 source_file_sha256")
    observed: dict[str, dict[str, Any]] = {}
    for relative, expected_sha in sorted(expected.items()):
        path = parent_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"missing R15 parent file: {path}")
        actual_sha = _sha256(path)
        if actual_sha != expected_sha:
            raise ValueError(
                f"R15 parent SHA mismatch for {relative}: "
                f"{actual_sha} != {expected_sha}"
            )
        observed[relative] = {
            "bytes": path.stat().st_size,
            "sha256": actual_sha,
            "matched": True,
        }
    return observed


def _write_manifest(output: Path, payloads: list[str]) -> dict[str, Any]:
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
            "schema_version": (
                "p8_2_k1a_r5_f1_r16_candidate_manifest_v1"
            ),
            "task_id": TASK_ID,
            "files": files,
            "payload_file_count": len(files),
            "payload_total_bytes": sum(
                row["bytes"] for row in files.values()
            ),
            "manifest_control_file": manifest_path.name,
            "manifest_bytes": manifest_bytes,
            "transfer_file_count": len(files) + 1,
            "transfer_total_bytes": (
                sum(row["bytes"] for row in files.values())
                + manifest_bytes
            ),
            "max_transfer_bytes": MAX_TRANSFER_BYTES,
            "bounded_transfer_package_exact": True,
            "sensitivity": SENSITIVITY,
            "raw_trace_content_retained": False,
            "generated_content_retained": False,
            "token_ids_retained": False,
            "request_ids_retained": False,
            "raw_process_ids_retained": False,
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
    return value


def analyze(args: argparse.Namespace) -> int:
    parent_root = args.parent_root.resolve()
    output = args.output_dir.resolve()
    audit_path = args.audit.resolve()
    if output.exists():
        raise FileExistsError(f"output directory exists: {output}")
    if parent_root == output or parent_root in output.parents:
        raise ValueError("output must not be inside immutable R15 parent root")
    audit = yaml.safe_load(audit_path.read_text(encoding="utf-8"))
    if not isinstance(audit, dict) or audit.get("task_id") != TASK_ID:
        raise ValueError("R16 audit task_id mismatch")

    parent_hashes = _validate_parent_hashes(parent_root, audit)
    trace_dir = parent_root / "runtime/offload_trace"
    rows, trace_paths = _read_trace_rows(trace_dir)
    trace_before = _trace_inventory(trace_paths, parent_root)
    parent_grading = _read_json(parent_root / "grading_summary.json")
    parent_trigger = _read_json(parent_root / "h2d_trigger_summary.json")
    parent_transfer = _read_json(parent_root / "transfer_trace_summary.json")
    summary, _ = adjudicate_async_completion(
        rows,
        parent_grading=parent_grading,
        parent_trigger=parent_trigger,
        parent_transfer=parent_transfer,
    )
    worker_rollup = build_worker_completion_rollup(rows)
    trace_after = _trace_inventory(trace_paths, parent_root)
    source_unchanged = trace_before == trace_after
    if not source_unchanged:
        raise ValueError("immutable R15 raw trace changed during analysis")

    grade = str(summary["server_grade"])
    provenance = {
        "schema_version": (
            "p8_2_k1a_r5_f1_r16_source_evidence_provenance_v1"
        ),
        "task_id": TASK_ID,
        "parent_root": str(parent_root),
        "parent_source_files": parent_hashes,
        "raw_trace_before": trace_before,
        "raw_trace_after": trace_after,
        "all_source_files_unchanged": source_unchanged,
        "raw_trace_content_retained": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
        "raw_hash_values_retained": False,
        "generated_content_retained": False,
    }
    grading = {
        "schema_version": "p8_2_k1a_r5_f1_r16_grading_v1",
        "task_id": TASK_ID,
        "server_grade": grade,
        "parent_grade": parent_grading.get("server_grade"),
        "parent_source_hashes_exact": True,
        "source_evidence_unchanged": source_unchanged,
        "async_completion_evidence_exact": summary[
            "async_completion_evidence_exact"
        ],
        "h2d_poll_live_pending_is_diagnostic_only": True,
        "r15_false_negative_gate_observed": summary[
            "r15_false_negative_gate_observed"
        ],
        "h2d_restore_mechanism_accepted": grade == GREEN_GRADE,
        "accepted_capacity_invalidated": False,
        "new_npu_lifecycle_executed": False,
        "performance_reference_accepted": False,
        "unique_cause_proven": False,
        "next_task_authorized": False,
        "claim_boundary": (
            "r15_existing_single_lifecycle_raw_trace_offline_async_"
            "completion_semantics_and_restore_h2d_mechanism_only"
        ),
    }

    output.mkdir(parents=True)
    values = {
        "async_completion_adjudication_summary.json": summary,
        "worker_completion_rollup.json": worker_rollup,
        "source_evidence_provenance.json": provenance,
        "grading_summary.json": grading,
    }
    for relative, value in values.items():
        _write_json(output / relative, value)
    (output / "task_grade.txt").write_text(grade + "\n", encoding="utf-8")
    if grade == GREEN_GRADE:
        conclusion = (
            "R15 raw trace proves the same eight H2D workers submitted, "
            "enqueued, entered and returned from copy, returned from poll, "
            "and completed with zero async failures. The 7/8 live-pending "
            "snapshot is diagnostic timing coverage, not missing H2D."
        )
    else:
        conclusion = (
            "R15 raw trace does not close every required async completion "
            "edge; retain the mechanism evidence gap without an NPU rerun."
        )
    (output / "result_summary.md").write_text(
        "\n".join(
            (
                "# P8.2-K1A-R5-F1-R16 async completion adjudication",
                "",
                f"- grade: `{grade}`",
                f"- conclusion: {conclusion}",
                "- execution: zero NPU, zero vLLM, zero model request; R15 "
                "raw evidence read only.",
                "- boundary: no performance, unique-cause, K2, P8.3-I1, "
                "or next-task claim.",
                "",
            )
        ),
        encoding="utf-8",
    )
    payloads = [
        *values,
        "task_grade.txt",
        "result_summary.md",
    ]
    _write_manifest(output, payloads)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("analyze", choices=("analyze",))
    parser.add_argument("--parent-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    return parser


def main() -> int:
    return analyze(_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
