from __future__ import annotations

import argparse
from collections import Counter
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


TASK_ID = "p8_2_k1a_r5_f1_r17_full_trace_source_replay_2026_0727"
EXPECTED_WORLD_SIZE = 8
GREEN_GRADE = (
    "green_p8_2_k1a_r5_f1_r17_restore_h2d_mechanism_closed"
)
RED_GRADE = (
    "red_p8_2_k1a_r5_f1_r17_async_completion_evidence_incomplete"
)
BLOCKED_GRADE = (
    "blocked_p8_2_k1a_r5_f1_r17_source_trace_coverage_mismatch"
)
SENSITIVITY = "bounded_operational_metadata_no_content_or_token_ids"
MAX_TRANSFER_BYTES = 71680
PAYLOAD_FILES = (
    "full_trace_replay_summary.json",
    "trace_source_coverage_summary.json",
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
    "p8_2_k1a_r5_f1_r17_full_trace_source_replay_audit.yaml"
)
KEY_TRANSFER_EVENTS = (
    "copy_thread_started",
    "device_copy_submitted",
    "device_copy_enqueued",
    "copy_blocks_entered",
    "copy_blocks_returned",
    "transfer_poll_entered",
    "transfer_poll_returned",
    "transfer_completed",
    "cpu_hit_matched",
    "load_scheduled",
    "load_request_completed",
)
REPLAY_FIELDS = (
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
    "d2h_poll_event_visible_worker_count",
    "h2d_poll_event_visible_worker_count",
    "copy_thread_started_worker_count",
    "d2h_bytes_total",
    "h2d_bytes_total",
    "async_copy_failure_event_count",
    "d2h_store_complete",
    "h2d_restore_complete",
    "restore_step_lineage_primary_class",
    "restore_h2d_path_class",
    "restore_any_pairing_repair_applied",
    "restore_any_entered_reqs_to_load",
)
OUTPUT_TRANSFER_FIELDS = (
    *REPLAY_FIELDS,
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
    "d2h_async_copy_pipeline_exact",
    "h2d_async_copy_pipeline_exact",
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


def _load_audit(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("task_id") != TASK_ID:
        raise ValueError("R17 audit task_id mismatch")
    return value


def _validate_hashes(
    root: Path,
    expected: object,
    *,
    label: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(expected, dict) or not expected:
        raise ValueError(f"R17 audit does not define {label} SHA inventory")
    observed: dict[str, dict[str, Any]] = {}
    for relative, expected_sha in sorted(expected.items()):
        path = root / str(relative)
        if not path.is_file():
            raise FileNotFoundError(f"missing {label} input: {path}")
        actual_sha = _sha256(path)
        if actual_sha != expected_sha:
            raise ValueError(
                f"{label} SHA mismatch for {relative}: "
                f"{actual_sha} != {expected_sha}"
            )
        observed[str(relative)] = {
            "bytes": path.stat().st_size,
            "sha256": actual_sha,
            "matched": True,
        }
    return observed


def _facts_match(
    actual: dict[str, Any],
    expected: object,
) -> tuple[bool, dict[str, dict[str, Any]]]:
    if not isinstance(expected, dict) or not expected:
        raise ValueError("expected fact contract is empty")
    comparisons = {
        str(key): {
            "expected": value,
            "observed": actual.get(key),
            "matched": actual.get(key) == value,
        }
        for key, value in expected.items()
    }
    return all(row["matched"] for row in comparisons.values()), comparisons


def _trace_family(path: Path) -> str:
    if path.name == "combined.json":
        return "combined_json"
    if path.name.startswith("trace.") and path.suffix == ".jsonl":
        return "async_transfer_trace"
    if (
        path.name.startswith("h2d-residency.")
        and path.suffix == ".jsonl"
    ):
        return "residency_trace"
    return "other_jsonl"


def _trace_paths(trace_dir: Path) -> tuple[list[Path], list[Path], str]:
    combined = trace_dir / "combined.json"
    jsonl_paths = sorted(trace_dir.glob("*.jsonl"))
    all_paths = ([combined] if combined.is_file() else []) + jsonl_paths
    if combined.is_file():
        selected = [combined]
        selection_mode = "combined_json"
    else:
        selected = jsonl_paths
        selection_mode = "all_jsonl"
    if not selected:
        raise ValueError(f"no retained R15 trace source: {trace_dir}")
    return all_paths, selected, selection_mode


def _read_trace_path(path: Path) -> list[dict[str, Any]]:
    if path.name == "combined.json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, list) or not all(
            isinstance(row, dict) for row in value
        ):
            raise ValueError(f"combined trace is not a list of objects: {path}")
        return value
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(
                f"trace row is not an object: {path}:{line_number}"
            )
        rows.append(value)
    return rows


def _tree_inventory(paths: list[Path], root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    family_counts: Counter[str] = Counter()
    total_bytes = 0
    for path in paths:
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        file_sha = _sha256(path)
        total_bytes += size
        family_counts[_trace_family(path)] += 1
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_sha.encode("ascii"))
        digest.update(b"\n")
    return {
        "file_count": len(paths),
        "total_bytes": total_bytes,
        "tree_sha256": digest.hexdigest(),
        "file_family_counts": dict(sorted(family_counts.items())),
    }


def read_canonical_trace_source(
    trace_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_paths, selected_paths, selection_mode = _trace_paths(trace_dir)
    rows: list[dict[str, Any]] = []
    selected_family_rows: Counter[str] = Counter()
    selected_family_events: dict[str, Counter[str]] = {}
    for path in selected_paths:
        family = _trace_family(path)
        path_rows = _read_trace_path(path)
        rows.extend(path_rows)
        selected_family_rows[family] += len(path_rows)
        family_events = selected_family_events.setdefault(family, Counter())
        family_events.update(str(row.get("event") or "") for row in path_rows)
    event_histogram = Counter(str(row.get("event") or "") for row in rows)
    all_family_counts = Counter(_trace_family(path) for path in all_paths)
    selected_family_counts = Counter(
        _trace_family(path) for path in selected_paths
    )
    family_inventory: dict[str, dict[str, Any]] = {}
    for family in sorted(set(all_family_counts) | set(selected_family_counts)):
        family_inventory[family] = {
            "available_file_count": all_family_counts[family],
            "selected_file_count": selected_family_counts[family],
            "selected_row_count": selected_family_rows[family],
            "selected_key_event_counts": {
                event: selected_family_events.get(family, Counter())[event]
                for event in KEY_TRANSFER_EVENTS
            },
        }
    source = {
        "selection_mode": selection_mode,
        "all_source_file_count": len(all_paths),
        "selected_source_file_count": len(selected_paths),
        "family_inventory": family_inventory,
        "selected_trace_event_count": len(rows),
        "selected_event_histogram": dict(sorted(event_histogram.items())),
        "canonical_reader_semantics": (
            "use combined.json alone when present; otherwise concatenate "
            "every *.jsonl in lexical path order"
        ),
        "duplicate_combined_and_jsonl_read": False,
    }
    return rows, source


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
    for direction in ("d2h", "h2d"):
        submitted = _event_pids(
            rows,
            event="device_copy_submitted",
            direction=direction,
        )
        for ordinal, pid in enumerate(sorted(submitted), start=1):
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
                    "completed": completed,
                    "completion_without_live_pending": (
                        completed and not live_pending
                    ),
                }
            )
    return {
        "schema_version": (
            "p8_2_k1a_r5_f1_r17_worker_completion_rollup_v1"
        ),
        "worker_rows": worker_rows,
        "worker_identity": (
            "direction-local ordinal sorted by process id; raw process ids "
            "are not retained"
        ),
        "worker_row_count": len(worker_rows),
        "completion_without_live_pending_worker_count": sum(
            1
            for row in worker_rows
            if row["completion_without_live_pending"]
        ),
        "raw_process_ids_retained": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
        "raw_hash_values_retained": False,
        "generated_content_retained": False,
    }


def _read_parent_evidence(
    r15_root: Path,
    r16_root: Path,
    audit: dict[str, Any],
) -> dict[str, Any]:
    r15_contract = audit.get("accepted_f1_r15_result")
    r16_contract = audit.get("accepted_f1_r16_result")
    if not isinstance(r15_contract, dict) or not isinstance(
        r16_contract, dict
    ):
        raise ValueError("R17 audit parent contracts are missing")
    r15_hashes = _validate_hashes(
        r15_root,
        r15_contract.get("source_file_sha256"),
        label="R15 parent",
    )
    r16_hashes = _validate_hashes(
        r16_root,
        r16_contract.get("source_file_sha256"),
        label="R16 parent",
    )
    r15_grading = _read_json(r15_root / "grading_summary.json")
    r15_trigger = _read_json(r15_root / "h2d_trigger_summary.json")
    r15_transfer = _read_json(r15_root / "transfer_trace_summary.json")
    r16_grading = _read_json(r16_root / "grading_summary.json")
    r16_adjudication = _read_json(
        r16_root / "async_completion_adjudication_summary.json"
    )
    r16_provenance = _read_json(
        r16_root / "source_evidence_provenance.json"
    )
    checks: dict[str, Any] = {}
    checks["r15_grading_exact"], checks["r15_grading_comparisons"] = (
        _facts_match(r15_grading, r15_contract.get("grading_fields"))
    )
    checks["r15_trigger_exact"], checks["r15_trigger_comparisons"] = (
        _facts_match(r15_trigger, r15_contract.get("trigger_fields"))
    )
    checks["r15_transfer_exact"], checks["r15_transfer_comparisons"] = (
        _facts_match(r15_transfer, r15_contract.get("transfer_fields"))
    )
    checks["r16_grading_exact"], checks["r16_grading_comparisons"] = (
        _facts_match(r16_grading, r16_contract.get("grading_fields"))
    )
    (
        checks["r16_adjudication_exact"],
        checks["r16_adjudication_comparisons"],
    ) = _facts_match(
        r16_adjudication,
        r16_contract.get("adjudication_fields"),
    )
    r16_recomputed = r16_adjudication.get("recomputed_transfer")
    if not isinstance(r16_recomputed, dict):
        raise ValueError("R16 adjudication recomputed_transfer is missing")
    (
        checks["r16_recomputed_exact"],
        checks["r16_recomputed_comparisons"],
    ) = _facts_match(
        r16_recomputed,
        r16_contract.get("recomputed_transfer_fields"),
    )
    (
        checks["r16_provenance_exact"],
        checks["r16_provenance_comparisons"],
    ) = _facts_match(
        r16_provenance,
        r16_contract.get("provenance_fields"),
    )
    r16_raw_trace_before = r16_provenance.get("raw_trace_before")
    if not isinstance(r16_raw_trace_before, dict):
        raise ValueError("R16 provenance raw_trace_before is missing")
    (
        checks["r16_raw_trace_exact"],
        checks["r16_raw_trace_comparisons"],
    ) = _facts_match(
        r16_raw_trace_before,
        r16_contract.get("raw_trace_fields"),
    )
    checks["parent_contract_exact"] = all(
        checks[key] is True
        for key in (
            "r15_grading_exact",
            "r15_trigger_exact",
            "r15_transfer_exact",
            "r16_grading_exact",
            "r16_adjudication_exact",
            "r16_recomputed_exact",
            "r16_provenance_exact",
            "r16_raw_trace_exact",
        )
    )
    if not checks["parent_contract_exact"]:
        raise ValueError("R15/R16 parent fact contract mismatch")
    return {
        "r15_hashes": r15_hashes,
        "r16_hashes": r16_hashes,
        "r15_grading": r15_grading,
        "r15_trigger": r15_trigger,
        "r15_transfer": r15_transfer,
        "r16_grading": r16_grading,
        "r16_adjudication": r16_adjudication,
        "r16_provenance": r16_provenance,
        "checks": checks,
    }


def build_trace_source_coverage(
    rows: list[dict[str, Any]],
    *,
    source: dict[str, Any],
    parent_transfer: dict[str, Any],
    r16_adjudication: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    recomputed = summarize_trace_rows(
        rows,
        expected_world_size=EXPECTED_WORLD_SIZE,
        restore_request_suffix="restore_follower",
    )
    field_comparisons = {
        field: {
            "expected_from_r15": parent_transfer.get(field),
            "observed_from_full_replay": recomputed.get(field),
            "matched": recomputed.get(field) == parent_transfer.get(field),
        }
        for field in REPLAY_FIELDS
    }
    event_histogram = source["selected_event_histogram"]
    key_event_nonzero = {
        event: int(event_histogram.get(event) or 0) > 0
        for event in KEY_TRANSFER_EVENTS
    }
    family_inventory = source["family_inventory"]
    if source["selection_mode"] == "combined_json":
        file_family_coverage_exact = (
            family_inventory.get("combined_json", {}).get(
                "selected_file_count"
            )
            == 1
        )
    else:
        file_family_coverage_exact = all(
            family_inventory.get(family, {}).get("selected_file_count", 0)
            > 0
            for family in ("async_transfer_trace", "residency_trace")
        )
    mismatch_reasons: list[str] = []
    if not file_family_coverage_exact:
        mismatch_reasons.append("required_trace_file_family_not_selected")
    for event, nonzero in key_event_nonzero.items():
        if not nonzero:
            mismatch_reasons.append(f"required_event_missing:{event}")
    for field, comparison in field_comparisons.items():
        if comparison["matched"] is not True:
            mismatch_reasons.append(f"r15_replay_field_mismatch:{field}")
    coverage_exact = not mismatch_reasons
    r16_recomputed = r16_adjudication.get("recomputed_transfer")
    if not isinstance(r16_recomputed, dict):
        raise ValueError("R16 adjudication recomputed_transfer is missing")
    r16_event_count = int(r16_recomputed.get("trace_event_count") or 0)
    full_event_count = int(recomputed.get("trace_event_count") or 0)
    r16_selector_fault_confirmed = all(
        (
            coverage_exact,
            full_event_count > r16_event_count > 0,
            int(
                event_histogram.get("device_copy_submitted")
                or 0
            )
            > 0,
            int(event_histogram.get("transfer_completed") or 0) > 0,
        )
    )
    coverage = {
        "schema_version": (
            "p8_2_k1a_r5_f1_r17_trace_source_coverage_v1"
        ),
        "task_id": TASK_ID,
        **source,
        "r15_replay_field_comparisons": field_comparisons,
        "required_key_event_nonzero": key_event_nonzero,
        "file_family_coverage_exact": file_family_coverage_exact,
        "trace_source_coverage_exact": coverage_exact,
        "coverage_mismatch_reasons": mismatch_reasons,
        "r16_selected_trace_event_count": r16_event_count,
        "full_replay_trace_event_count": full_event_count,
        "recovered_trace_event_count_vs_r16": (
            full_event_count - r16_event_count
        ),
        "r16_source_selector_fault_confirmed": (
            r16_selector_fault_confirmed
        ),
        "r16_selector_fault_class": (
            "h2d_residency_only_omitted_async_transfer_trace_family"
            if r16_selector_fault_confirmed
            else "not_confirmed"
        ),
        "source_coverage_failure_is_mechanism_red": False,
    }
    return coverage, recomputed


def adjudicate_full_trace_replay(
    rows: list[dict[str, Any]],
    *,
    source: dict[str, Any],
    parent: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    coverage, recomputed = build_trace_source_coverage(
        rows,
        source=source,
        parent_transfer=parent["r15_transfer"],
        r16_adjudication=parent["r16_adjudication"],
    )
    completion_exact = all(
        (
            recomputed.get("d2h_store_complete") is True,
            recomputed.get("h2d_restore_complete") is True,
            recomputed.get("d2h_async_copy_pipeline_exact") is True,
            recomputed.get("h2d_async_copy_pipeline_exact") is True,
            recomputed.get("d2h_poll_returned_completion_exact") is True,
            recomputed.get("h2d_poll_returned_completion_exact") is True,
            int(recomputed.get("d2h_worker_count") or 0)
            == EXPECTED_WORLD_SIZE,
            int(recomputed.get("h2d_worker_count") or 0)
            == EXPECTED_WORLD_SIZE,
            int(recomputed.get("d2h_completed_worker_count") or 0)
            == EXPECTED_WORLD_SIZE,
            int(recomputed.get("h2d_completed_worker_count") or 0)
            == EXPECTED_WORLD_SIZE,
            int(recomputed.get("async_copy_failure_event_count") or 0) == 0,
        )
    )
    coverage_exact = coverage["trace_source_coverage_exact"] is True
    if not coverage_exact:
        grade = BLOCKED_GRADE
        adjudication_performed = False
    elif completion_exact:
        grade = GREEN_GRADE
        adjudication_performed = True
    else:
        grade = RED_GRADE
        adjudication_performed = True
    selected_fields = {
        field: recomputed.get(field) for field in OUTPUT_TRANSFER_FIELDS
    }
    summary = {
        "schema_version": (
            "p8_2_k1a_r5_f1_r17_full_trace_replay_v1"
        ),
        "task_id": TASK_ID,
        "server_grade": grade,
        "parent_contract_exact": parent["checks"]["parent_contract_exact"],
        "trace_source_coverage_exact": coverage_exact,
        "mechanism_adjudication_performed": adjudication_performed,
        "async_completion_evidence_exact": (
            completion_exact if adjudication_performed else None
        ),
        "h2d_restore_mechanism_accepted": grade == GREEN_GRADE,
        "r16_source_selector_fault_confirmed": coverage[
            "r16_source_selector_fault_confirmed"
        ],
        "r16_historical_grade_superseded_for_mechanism_claim": all(
            (
                coverage_exact,
                coverage["r16_source_selector_fault_confirmed"],
            )
        ),
        "historical_r16_grade": parent["r16_grading"].get("server_grade"),
        "h2d_poll_live_pending_is_diagnostic_only": True,
        "completion_semantics": (
            "submitted=enqueued=copy_entered=copy_returned=completed for "
            "the same worker set, all copy threads started, poll returned "
            "for completed workers, and zero async failures"
        ),
        "recomputed_transfer": selected_fields,
        "accepted_capacity_invalidated": False,
        "new_npu_lifecycle_executed": False,
        "npu_started": False,
        "vllm_started": False,
        "model_requests_sent": 0,
        "performance_claim_authorized": False,
        "unique_cause_claim_authorized": False,
        "next_task_authorized": False,
        "k2_authorized": False,
        "p8_3_i1_authorized": False,
    }
    return summary, coverage, recomputed


def _write_manifest(output: Path) -> dict[str, Any]:
    files = {
        relative: {
            "bytes": (output / relative).stat().st_size,
            "sha256": _sha256(output / relative),
            "sensitivity": SENSITIVITY,
        }
        for relative in PAYLOAD_FILES
    }
    manifest_path = output / MANIFEST_FILE
    manifest_bytes = 0
    while True:
        value = {
            "schema_version": (
                "p8_2_k1a_r5_f1_r17_candidate_manifest_v1"
            ),
            "task_id": TASK_ID,
            "files": files,
            "payload_file_count": len(files),
            "payload_total_bytes": sum(
                row["bytes"] for row in files.values()
            ),
            "manifest_control_file": MANIFEST_FILE,
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
    if not isinstance(files, dict) or set(files) != set(PAYLOAD_FILES):
        raise ValueError("R17 manifest payload set mismatch")
    payload_total = 0
    for relative in PAYLOAD_FILES:
        row = files.get(relative)
        if not isinstance(row, dict):
            raise ValueError(f"R17 manifest row invalid: {relative}")
        path = output / relative
        if not path.is_file():
            raise FileNotFoundError(f"missing R17 payload: {path}")
        actual_bytes = path.stat().st_size
        actual_sha = _sha256(path)
        if actual_bytes != int(row.get("bytes") or -1):
            raise ValueError(f"R17 payload byte mismatch: {relative}")
        if actual_sha != row.get("sha256"):
            raise ValueError(f"R17 payload SHA mismatch: {relative}")
        if row.get("sensitivity") != SENSITIVITY:
            raise ValueError(f"R17 payload sensitivity mismatch: {relative}")
        payload_total += actual_bytes
    manifest_bytes = manifest_path.stat().st_size
    transfer_total = payload_total + manifest_bytes
    controls = {
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
    for key, expected in controls.items():
        if manifest.get(key) != expected:
            raise ValueError(
                f"R17 manifest control mismatch for {key}: "
                f"{manifest.get(key)!r} != {expected!r}"
            )
    if transfer_total > MAX_TRANSFER_BYTES:
        raise ValueError("R17 verified package exceeds 71680 bytes")
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


def _prepare(args: argparse.Namespace) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
]:
    audit = _load_audit(args.audit.resolve())
    repository_hashes = _validate_hashes(
        REPO_ROOT,
        audit.get("repository_input_sha256"),
        label="repository",
    )
    parent = _read_parent_evidence(
        args.r15_root.resolve(),
        args.r16_root.resolve(),
        audit,
    )
    trace_dir = args.r15_root.resolve() / "runtime/offload_trace"
    all_paths_before, _, _ = _trace_paths(trace_dir)
    before = _tree_inventory(all_paths_before, trace_dir)
    rows, source = read_canonical_trace_source(trace_dir)
    all_paths_after, _, _ = _trace_paths(trace_dir)
    after = _tree_inventory(all_paths_after, trace_dir)
    if before != after:
        raise ValueError("immutable R15 raw trace changed during replay")
    r15_contract = audit["accepted_f1_r15_result"]
    r16_contract = audit["accepted_f1_r16_result"]
    if (
        _validate_hashes(
            args.r15_root.resolve(),
            r15_contract.get("source_file_sha256"),
            label="R15 parent",
        )
        != parent["r15_hashes"]
    ):
        raise ValueError("immutable R15 parent sources changed during replay")
    if (
        _validate_hashes(
            args.r16_root.resolve(),
            r16_contract.get("source_file_sha256"),
            label="R16 parent",
        )
        != parent["r16_hashes"]
    ):
        raise ValueError("immutable R16 parent sources changed during replay")
    return audit, repository_hashes, parent, rows, source, {
        "before": before,
        "after": after,
    }


def preflight(args: argparse.Namespace) -> int:
    (
        audit,
        repository_hashes,
        parent,
        rows,
        source,
        trace_inventory,
    ) = _prepare(args)
    summary, coverage, _ = adjudicate_full_trace_replay(
        rows,
        source=source,
        parent=parent,
    )
    if (
        _validate_hashes(
            REPO_ROOT,
            audit.get("repository_input_sha256"),
            label="repository",
        )
        != repository_hashes
    ):
        raise ValueError("R17 repository inputs changed during preflight")
    values = {
        "preflight_status": "pass",
        "task_id": TASK_ID,
        "repository_input_file_count": len(repository_hashes),
        "repository_input_hashes_exact": True,
        "r15_parent_source_file_count": len(parent["r15_hashes"]),
        "r16_parent_source_file_count": len(parent["r16_hashes"]),
        "parent_source_hashes_exact": True,
        "parent_contract_exact": True,
        "trace_selection_mode": source["selection_mode"],
        "trace_source_file_count": trace_inventory["before"]["file_count"],
        "selected_trace_file_count": source["selected_source_file_count"],
        "selected_trace_event_count": len(rows),
        "trace_source_coverage_exact": coverage[
            "trace_source_coverage_exact"
        ],
        "r16_source_selector_fault_confirmed": coverage[
            "r16_source_selector_fault_confirmed"
        ],
        "prospective_grade": summary["server_grade"],
        "raw_trace_unchanged_during_preflight": True,
        "npu_started": False,
        "vllm_started": False,
        "model_requests_sent": 0,
        "keep_alive_action": "leave_running",
    }
    for key, value in values.items():
        print(f"{key}={str(value).lower() if isinstance(value, bool) else value}")
    return 0


def analyze(args: argparse.Namespace) -> int:
    output = args.output_dir.resolve()
    if output.exists():
        raise FileExistsError(f"output directory exists: {output}")
    for parent_root in (args.r15_root.resolve(), args.r16_root.resolve()):
        if parent_root == output or parent_root in output.parents:
            raise ValueError("output must not be inside an immutable parent")
    (
        audit,
        repository_hashes,
        parent,
        rows,
        source,
        trace_inventory,
    ) = _prepare(args)
    summary, coverage, _ = adjudicate_full_trace_replay(
        rows,
        source=source,
        parent=parent,
    )
    worker_rollup = build_worker_completion_rollup(rows)
    if (
        _validate_hashes(
            REPO_ROOT,
            audit.get("repository_input_sha256"),
            label="repository",
        )
        != repository_hashes
    ):
        raise ValueError("R17 repository inputs changed during analysis")
    grade = str(summary["server_grade"])
    provenance = {
        "schema_version": (
            "p8_2_k1a_r5_f1_r17_source_evidence_provenance_v1"
        ),
        "task_id": TASK_ID,
        "r15_parent_root": str(args.r15_root.resolve()),
        "r16_parent_root": str(args.r16_root.resolve()),
        "repository_input_files": repository_hashes,
        "r15_parent_source_files": parent["r15_hashes"],
        "r16_parent_source_files": parent["r16_hashes"],
        "raw_trace_before": trace_inventory["before"],
        "raw_trace_after": trace_inventory["after"],
        "all_source_files_unchanged": True,
        "canonical_trace_reader_used": True,
        "raw_trace_content_retained": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
        "raw_hash_values_retained": False,
        "generated_content_retained": False,
    }
    grading = {
        "schema_version": "p8_2_k1a_r5_f1_r17_grading_v1",
        "task_id": TASK_ID,
        "server_grade": grade,
        "r15_parent_grade": parent["r15_grading"].get("server_grade"),
        "r16_parent_grade": parent["r16_grading"].get("server_grade"),
        "parent_source_hashes_exact": True,
        "parent_contract_exact": True,
        "source_evidence_unchanged": True,
        "trace_source_coverage_exact": summary[
            "trace_source_coverage_exact"
        ],
        "mechanism_adjudication_performed": summary[
            "mechanism_adjudication_performed"
        ],
        "async_completion_evidence_exact": summary[
            "async_completion_evidence_exact"
        ],
        "r16_source_selector_fault_confirmed": summary[
            "r16_source_selector_fault_confirmed"
        ],
        "r16_historical_grade_superseded_for_mechanism_claim": summary[
            "r16_historical_grade_superseded_for_mechanism_claim"
        ],
        "h2d_restore_mechanism_accepted": grade == GREEN_GRADE,
        "accepted_capacity_invalidated": False,
        "new_npu_lifecycle_executed": False,
        "performance_reference_accepted": False,
        "unique_cause_proven": False,
        "next_task_authorized": False,
        "claim_boundary": (
            "r15_existing_accepted_capacity_single_lifecycle_complete_raw_"
            "trace_source_replay_and_restore_h2d_mechanism_only"
        ),
    }
    output.mkdir(parents=True)
    artifacts = {
        "full_trace_replay_summary.json": summary,
        "trace_source_coverage_summary.json": coverage,
        "worker_completion_rollup.json": worker_rollup,
        "source_evidence_provenance.json": provenance,
        "grading_summary.json": grading,
    }
    for relative, value in artifacts.items():
        _write_json(output / relative, value)
    (output / "task_grade.txt").write_text(grade + "\n", encoding="utf-8")
    replay = summary["recomputed_transfer"]
    if grade == GREEN_GRADE:
        conclusion = (
            "The complete R15 trace source recovers the omitted async "
            "transfer family and closes D2H/H2D completion on all eight "
            "workers. R16 is superseded for the mechanism claim because "
            "its selector read only the residency trace family."
        )
    elif grade == BLOCKED_GRADE:
        conclusion = (
            "The selected source does not reproduce the frozen R15 trace "
            "coverage. No H2D mechanism grade is issued; this is an input "
            "coverage block, not mechanism RED."
        )
    else:
        conclusion = (
            "The complete R15 trace source matches the frozen parent "
            "coverage but still lacks at least one required async "
            "completion edge."
        )
    result_lines = [
        "# P8.2-K1A-R5-F1-R17 complete trace-source replay",
        "",
        "## Decision",
        "",
        f"- grade: `{grade}`",
        f"- conclusion: {conclusion}",
        "- trace_source_coverage_exact: "
        f"`{str(summary['trace_source_coverage_exact']).lower()}`",
        "- mechanism_adjudication_performed: "
        f"`{str(summary['mechanism_adjudication_performed']).lower()}`",
        "- async_completion_evidence_exact: "
        f"`{str(summary['async_completion_evidence_exact']).lower()}`",
        "- r16_source_selector_fault_confirmed: "
        f"`{str(summary['r16_source_selector_fault_confirmed']).lower()}`",
        "- r16_historical_grade_superseded_for_mechanism_claim: "
        f"`{str(summary['r16_historical_grade_superseded_for_mechanism_claim']).lower()}`",
        "",
        "## Source coverage",
        "",
        f"- canonical selection mode: `{source['selection_mode']}`",
        "- canonical rule: `combined.json` alone when present; otherwise "
        "all `*.jsonl`.",
        f"- all source files: `{source['all_source_file_count']}`",
        f"- selected source files: `{source['selected_source_file_count']}`",
        f"- full replay events: `{coverage['full_replay_trace_event_count']}`",
        f"- R16 selected events: `{coverage['r16_selected_trace_event_count']}`",
        "- recovered events versus R16: "
        f"`{coverage['recovered_trace_event_count_vs_r16']}`",
        "- coverage mismatch reasons: "
        f"`{json.dumps(coverage['coverage_mismatch_reasons'])}`",
        "- raw trace unchanged before/after read: `true`",
        "",
        "## Replayed completion evidence",
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
                submitted=replay.get(f"{direction}_worker_count"),
                enqueued=replay.get(f"{direction}_enqueued_worker_count"),
                entered=replay.get(
                    f"{direction}_copy_blocks_entered_worker_count"
                ),
                returned=replay.get(
                    f"{direction}_copy_blocks_returned_worker_count"
                ),
                poll_entered=replay.get(
                    f"{direction}_poll_entered_worker_count"
                ),
                poll_returned=replay.get(
                    f"{direction}_poll_returned_worker_count"
                ),
                live=replay.get(
                    f"{direction}_poll_live_pending_worker_count"
                ),
                completed=replay.get(
                    f"{direction}_completed_worker_count"
                ),
                byte_count=replay.get(f"{direction}_bytes_total"),
            )
        )
    result_lines.extend(
        (
            "",
            "- async copy failure events: "
            f"`{replay.get('async_copy_failure_event_count')}`",
            "- H2D poll-returned completion exact: "
            f"`{str(replay.get('h2d_poll_returned_completion_exact')).lower()}`",
            "- H2D async pipeline exact: "
            f"`{str(replay.get('h2d_async_copy_pipeline_exact')).lower()}`",
            "",
            "## Execution and claim boundary",
            "",
            "- zero NPU, zero vLLM, zero model request; keep-alive left "
            "running.",
            "- accepted-capacity invalidated: `false`",
            "- performance reference accepted: `false`",
            "- unique cause proven: `false`",
            "- K2 authorized: `false`",
            "- P8.3-I1 authorized: `false`",
            "- next task authorized: `false`",
            "- raw trace, process IDs, request IDs, token IDs, raw hash "
            "values, and generated content are not retained.",
            "",
            "## Candidate package",
            "",
            "- fixed payloads: `7`; manifest: `1`",
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
    _write_manifest(output)
    _verify_output_package(output)
    return 0


def verify_output(args: argparse.Namespace) -> int:
    values = _verify_output_package(args.output_dir.resolve())
    for key, value in values.items():
        print(f"{key}={str(value).lower() if isinstance(value, bool) else value}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("preflight", "analyze"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--r15-root", type=Path, required=True)
        command_parser.add_argument("--r16-root", type=Path, required=True)
        command_parser.add_argument(
            "--audit",
            type=Path,
            default=DEFAULT_AUDIT,
        )
        if command == "analyze":
            command_parser.add_argument(
                "--output-dir",
                type=Path,
                required=True,
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
