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
PAYLOAD_FILES = (
    "async_completion_adjudication_summary.json",
    "worker_completion_rollup.json",
    "source_evidence_provenance.json",
    "grading_summary.json",
    "task_grade.txt",
    "result_summary.md",
)
MANIFEST_FILE = "candidate_manifest.server_local.json"
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


def _find_trace_paths(trace_dir: Path) -> list[Path]:
    paths = sorted(trace_dir.glob("h2d-residency.*.jsonl"))
    if not paths:
        raise ValueError(f"no retained R15 trace files: {trace_dir}")
    return paths


def _read_trace_rows(
    paths: list[Path],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"trace row is not an object: {path}")
            rows.append(value)
    return rows


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


def _load_audit(audit_path: Path) -> dict[str, Any]:
    audit = yaml.safe_load(audit_path.read_text(encoding="utf-8"))
    if not isinstance(audit, dict) or audit.get("task_id") != TASK_ID:
        raise ValueError("R16 audit task_id mismatch")
    return audit


def _validate_repository_hashes(
    audit: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    expected = audit.get("repository_input_sha256")
    if not isinstance(expected, dict) or not expected:
        raise ValueError("R16 audit does not define repository_input_sha256")
    observed: dict[str, dict[str, Any]] = {}
    for relative, expected_sha in sorted(expected.items()):
        path = REPO_ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"missing R16 repository input: {path}")
        actual_sha = _sha256(path)
        if actual_sha != expected_sha:
            raise ValueError(
                f"R16 repository SHA mismatch for {relative}: "
                f"{actual_sha} != {expected_sha}"
            )
        observed[relative] = {
            "bytes": path.stat().st_size,
            "sha256": actual_sha,
            "matched": True,
        }
    return observed


def _read_parent_evidence(
    parent_root: Path,
    audit: dict[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    parent_hashes = _validate_parent_hashes(parent_root, audit)
    parent_grading = _read_json(parent_root / "grading_summary.json")
    parent_trigger = _read_json(parent_root / "h2d_trigger_summary.json")
    parent_transfer = _read_json(parent_root / "transfer_trace_summary.json")
    return (
        parent_hashes,
        parent_grading,
        parent_trigger,
        parent_transfer,
    )


def preflight(args: argparse.Namespace) -> int:
    parent_root = args.parent_root.resolve()
    audit_path = args.audit.resolve()
    audit = _load_audit(audit_path)
    repository_hashes = _validate_repository_hashes(audit)
    (
        parent_hashes,
        parent_grading,
        parent_trigger,
        parent_transfer,
    ) = _read_parent_evidence(parent_root, audit)
    trace_paths = _find_trace_paths(parent_root / "runtime/offload_trace")
    trace_before = _trace_inventory(trace_paths, parent_root)
    rows = _read_trace_rows(trace_paths)
    trace_after = _trace_inventory(trace_paths, parent_root)
    if trace_before != trace_after:
        raise ValueError("immutable R15 raw trace changed during preflight")
    if _validate_parent_hashes(parent_root, audit) != parent_hashes:
        raise ValueError("immutable R15 parent sources changed during preflight")
    if _validate_repository_hashes(audit) != repository_hashes:
        raise ValueError("R16 repository inputs changed during preflight")
    summary, _ = adjudicate_async_completion(
        rows,
        parent_grading=parent_grading,
        parent_trigger=parent_trigger,
        parent_transfer=parent_transfer,
    )
    if summary["parent_contract_exact"] is not True:
        raise ValueError("R15 parent fact contract mismatch")

    values = {
        "preflight_status": "pass",
        "task_id": TASK_ID,
        "repository_input_file_count": len(repository_hashes),
        "repository_input_hashes_exact": True,
        "parent_source_file_count": len(parent_hashes),
        "parent_source_hashes_exact": True,
        "parent_contract_exact": True,
        "raw_trace_file_count": trace_before["file_count"],
        "raw_trace_total_bytes": trace_before["total_bytes"],
        "raw_trace_tree_sha256": trace_before["tree_sha256"],
        "raw_trace_unchanged_during_preflight": True,
        "npu_started": False,
        "vllm_started": False,
        "model_requests_sent": 0,
        "keep_alive_action": "leave_running",
    }
    for key, value in values.items():
        print(f"{key}={str(value).lower() if isinstance(value, bool) else value}")
    return 0


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


def _verify_output_package(output: Path) -> dict[str, Any]:
    manifest_path = output / MANIFEST_FILE
    manifest = _read_json(manifest_path)
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("R16 manifest files must be an object")
    if set(files) != set(PAYLOAD_FILES):
        raise ValueError(
            "R16 manifest payload set mismatch: "
            f"{sorted(files)} != {sorted(PAYLOAD_FILES)}"
        )
    payload_total = 0
    for relative in PAYLOAD_FILES:
        row = files.get(relative)
        if not isinstance(row, dict):
            raise ValueError(f"R16 manifest row invalid: {relative}")
        path = output / relative
        if not path.is_file():
            raise FileNotFoundError(f"missing R16 payload: {path}")
        actual_bytes = path.stat().st_size
        actual_sha = _sha256(path)
        if actual_bytes != int(row.get("bytes") or -1):
            raise ValueError(f"R16 payload byte mismatch: {relative}")
        if actual_sha != row.get("sha256"):
            raise ValueError(f"R16 payload SHA mismatch: {relative}")
        if row.get("sensitivity") != SENSITIVITY:
            raise ValueError(f"R16 payload sensitivity mismatch: {relative}")
        payload_total += actual_bytes

    manifest_bytes = manifest_path.stat().st_size
    transfer_total = payload_total + manifest_bytes
    required_controls = {
        "payload_file_count": len(PAYLOAD_FILES),
        "payload_total_bytes": payload_total,
        "manifest_bytes": manifest_bytes,
        "transfer_file_count": len(PAYLOAD_FILES) + 1,
        "transfer_total_bytes": transfer_total,
        "max_transfer_bytes": MAX_TRANSFER_BYTES,
        "bounded_transfer_package_exact": True,
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
    for key, expected in required_controls.items():
        if manifest.get(key) != expected:
            raise ValueError(
                f"R16 manifest control mismatch for {key}: "
                f"{manifest.get(key)!r} != {expected!r}"
            )
    if transfer_total > MAX_TRANSFER_BYTES:
        raise ValueError("R16 verified transfer package exceeds 71680 bytes")
    return {
        "package_verification_status": "pass",
        "payload_file_count": len(PAYLOAD_FILES),
        "manifest_file_count": 1,
        "transfer_file_count": len(PAYLOAD_FILES) + 1,
        "payload_total_bytes": payload_total,
        "manifest_bytes": manifest_bytes,
        "transfer_total_bytes": transfer_total,
        "bounded_transfer_package_exact": True,
    }


def verify_output(args: argparse.Namespace) -> int:
    values = _verify_output_package(args.output_dir.resolve())
    for key, value in values.items():
        print(f"{key}={str(value).lower() if isinstance(value, bool) else value}")
    return 0


def analyze(args: argparse.Namespace) -> int:
    parent_root = args.parent_root.resolve()
    output = args.output_dir.resolve()
    audit_path = args.audit.resolve()
    if output.exists():
        raise FileExistsError(f"output directory exists: {output}")
    if parent_root == output or parent_root in output.parents:
        raise ValueError("output must not be inside immutable R15 parent root")
    audit = _load_audit(audit_path)
    repository_hashes = _validate_repository_hashes(audit)
    (
        parent_hashes,
        parent_grading,
        parent_trigger,
        parent_transfer,
    ) = _read_parent_evidence(parent_root, audit)
    trace_dir = parent_root / "runtime/offload_trace"
    trace_paths = _find_trace_paths(trace_dir)
    trace_before = _trace_inventory(trace_paths, parent_root)
    rows = _read_trace_rows(trace_paths)
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
    if _validate_parent_hashes(parent_root, audit) != parent_hashes:
        raise ValueError("immutable R15 parent sources changed during analysis")
    if _validate_repository_hashes(audit) != repository_hashes:
        raise ValueError("R16 repository inputs changed during analysis")

    grade = str(summary["server_grade"])
    provenance = {
        "schema_version": (
            "p8_2_k1a_r5_f1_r16_source_evidence_provenance_v1"
        ),
        "task_id": TASK_ID,
        "parent_root": str(parent_root),
        "repository_input_files": repository_hashes,
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
    recomputed = summary["recomputed_transfer"]
    result_lines = [
        "# P8.2-K1A-R5-F1-R16 async completion adjudication",
        "",
        "## Decision",
        "",
        f"- grade: `{grade}`",
        f"- conclusion: {conclusion}",
        "- parent_contract_exact: "
        f"`{str(summary['parent_contract_exact']).lower()}`",
        "- async_completion_evidence_exact: "
        f"`{str(summary['async_completion_evidence_exact']).lower()}`",
        "- h2d_poll_live_pending_coverage_exact: "
        f"`{str(summary['h2d_poll_live_pending_coverage_exact']).lower()}`",
        "- r15_false_negative_gate_observed: "
        f"`{str(summary['r15_false_negative_gate_observed']).lower()}`",
        "",
        "## Execution and immutability",
        "",
        "- execution: zero NPU, zero vLLM, zero model request; keep-alive "
        "left running.",
        f"- parent root: `{parent_root}`",
        f"- repository input hashes exact: `true` "
        f"({len(repository_hashes)} files)",
        f"- parent source hashes exact: `true` ({len(parent_hashes)} files)",
        f"- raw trace files: `{trace_before['file_count']}`",
        f"- raw trace bytes: `{trace_before['total_bytes']}`",
        f"- raw trace tree SHA-256: `{trace_before['tree_sha256']}`",
        "- raw trace unchanged before/after read: `true`",
        "",
        "## Recomputed completion evidence",
        "",
        "| direction | submitted | enqueued | copy entered | copy returned | "
        "poll entered | poll returned | live-pending | completed | bytes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for direction in ("d2h", "h2d"):
        result_lines.append(
            "| {direction} | {submitted} | {enqueued} | {entered} | "
            "{returned} | {poll_entered} | {poll_returned} | {live} | "
            "{completed} | {byte_count} |".format(
                direction=direction.upper(),
                submitted=recomputed.get(f"{direction}_worker_count"),
                enqueued=recomputed.get(f"{direction}_enqueued_worker_count"),
                entered=recomputed.get(
                    f"{direction}_copy_blocks_entered_worker_count"
                ),
                returned=recomputed.get(
                    f"{direction}_copy_blocks_returned_worker_count"
                ),
                poll_entered=recomputed.get(
                    f"{direction}_poll_entered_worker_count"
                ),
                poll_returned=recomputed.get(
                    f"{direction}_poll_returned_worker_count"
                ),
                live=recomputed.get(
                    f"{direction}_poll_live_pending_worker_count"
                ),
                completed=recomputed.get(
                    f"{direction}_completed_worker_count"
                ),
                byte_count=recomputed.get(f"{direction}_bytes_total"),
            )
        )
    result_lines.extend(
        (
            "",
            "- async copy failure events: "
            f"`{recomputed.get('async_copy_failure_event_count')}`",
            "- H2D poll-returned completion exact: "
            f"`{str(recomputed.get('h2d_poll_returned_completion_exact')).lower()}`",
            "- H2D async pipeline exact: "
            f"`{str(recomputed.get('h2d_async_copy_pipeline_exact')).lower()}`",
            "",
            "## Claim boundary",
            "",
            "- accepted-capacity invalidated: `false`",
            "- performance reference accepted: `false`",
            "- unique cause proven: `false`",
            "- K2 authorized: `false`",
            "- P8.3-I1 authorized: `false`",
            "- next task authorized: `false`",
            "- raw trace, process IDs, request IDs, token IDs, raw hash "
            "values, and generated content are not retained in this package.",
            "",
            "## Candidate package",
            "",
            "- fixed payloads: `6`; manifest: `1`",
            "- maximum complete package: `71680 bytes`",
            "- transfer eligibility: `true`; selected channel: none",
            "- available channels after explicit user choice: "
            "`email / upload-api / server-local`",
            "",
        )
    )
    (output / "result_summary.md").write_text(
        "\n".join(result_lines),
        encoding="utf-8",
    )
    _write_manifest(output, list(PAYLOAD_FILES))
    _verify_output_package(output)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("preflight", "analyze"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument(
            "--parent-root", type=Path, required=True
        )
        command_parser.add_argument(
            "--audit", type=Path, default=DEFAULT_AUDIT
        )
        if command == "analyze":
            command_parser.add_argument(
                "--output-dir", type=Path, required=True
            )
    verify_parser = subparsers.add_parser("verify-output")
    verify_parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "preflight":
        return preflight(args)
    if args.command == "analyze":
        return analyze(args)
    if args.command == "verify-output":
        return verify_output(args)
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
