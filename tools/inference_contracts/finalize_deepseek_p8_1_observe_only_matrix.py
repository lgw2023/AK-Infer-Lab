from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import yaml


CANDIDATE_GREEN = "candidate_green_p8_1_official_mtp_observe_only_matrix"
EXPECTED_SLOTS = (
    ("short_isolated_a", "req_p8_short_isolated_a", 4096, 0),
    ("medium_shared_prime", "req_p8_medium_shared_prime", 65536, 0),
    ("medium_shared_follower", "req_p8_medium_shared_follower", 65536, 49152),
    ("long_isolated_a", "req_p8_long_isolated_a", 131072, 0),
    ("short_isolated_b", "req_p8_short_isolated_b", 4096, 0),
    ("long_isolated_b", "req_p8_long_isolated_b", 131072, 0),
)


def _load_json(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return record


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        records.append(record)
    return records


def _rows(record: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    rows = record.get("requests")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path} requests must be a list of JSON objects")
    return rows


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def finalize_matrix_artifacts(artifact_dir: Path) -> dict[str, Any]:
    bundle_dir = artifact_dir / "observe_only_bundle"
    request_rows = _rows(
        _load_json(artifact_dir / "request_matrix_summary.json"),
        artifact_dir / "request_matrix_summary.json",
    )
    prefix_rows = _rows(
        _load_json(artifact_dir / "prefix_cache_metrics_summary.json"),
        artifact_dir / "prefix_cache_metrics_summary.json",
    )
    mtp_rows = _rows(
        _load_json(artifact_dir / "mtp_metrics_summary.json"),
        artifact_dir / "mtp_metrics_summary.json",
    )
    queue_rows = _rows(
        _load_json(artifact_dir / "queue_health_summary.json"),
        artifact_dir / "queue_health_summary.json",
    )
    transfer_rows = _rows(
        _load_json(artifact_dir / "transfer_availability_summary.json"),
        artifact_dir / "transfer_availability_summary.json",
    )
    replay = _load_json(artifact_dir / "replay_determinism.json")
    manifest = yaml.safe_load((bundle_dir / "manifest.yaml").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("observe-only bundle manifest must be a YAML mapping")
    validation = _load_json(bundle_dir / "validation_report.json")
    events = _load_jsonl(bundle_dir / "state_events.jsonl")
    objects = _load_jsonl(bundle_dir / "state_objects.jsonl")
    decisions = _load_jsonl(bundle_dir / "placement_decisions.jsonl")
    cleanup = (artifact_dir / "cleanup_status.txt").read_text(encoding="utf-8").strip()

    expected_by_slot = {
        slot_id: {
            "request_id": request_id,
            "prompt_tokens": prompt_tokens,
            "prefix_hits": prefix_hits,
        }
        for slot_id, request_id, prompt_tokens, prefix_hits in EXPECTED_SLOTS
    }
    expected_request_ids = {item["request_id"] for item in expected_by_slot.values()}

    request_by_slot = {str(row.get("slot_id")): row for row in request_rows}
    request_exact_by_slot: dict[str, bool] = {}
    for slot_id, expected in expected_by_slot.items():
        row = request_by_slot.get(slot_id, {})
        request_exact_by_slot[slot_id] = (
            row.get("request_id") == expected["request_id"]
            and row.get("status") == "success"
            and row.get("http_status") == 200
            and row.get("prompt_tokens") == expected["prompt_tokens"]
            and row.get("generated_token_count") == 64
            and row.get("streamed_token_count") == 64
            and row.get("finish_reason") == "length"
            and row.get("generated_text_retained") is False
            and row.get("token_ids_retained") is False
        )
    successful_request_count = sum(request_exact_by_slot.values())
    request_matrix_exact = (
        len(request_rows) == len(EXPECTED_SLOTS)
        and set(request_by_slot) == set(expected_by_slot)
        and successful_request_count == len(EXPECTED_SLOTS)
    )

    prefix_by_slot = {str(row.get("slot_id")): row for row in prefix_rows}
    prefix_exact_by_slot: dict[str, bool] = {}
    for slot_id, expected in expected_by_slot.items():
        delta = prefix_by_slot.get(slot_id, {}).get("delta")
        delta = delta if isinstance(delta, dict) else {}
        prefix_exact_by_slot[slot_id] = (
            float(delta.get("queries") or 0.0) > 0.0
            and float(delta.get("hits") or 0.0) == float(expected["prefix_hits"])
        )
    shared_prefix_exact = prefix_exact_by_slot.get("medium_shared_follower", False)
    isolated_zero_hit = all(
        prefix_exact_by_slot.get(slot_id, False)
        for slot_id, expected in expected_by_slot.items()
        if expected["prefix_hits"] == 0
    )

    mtp_by_slot = {str(row.get("slot_id")): row for row in mtp_rows}
    mtp_ok_by_slot: dict[str, bool] = {}
    for slot_id in expected_by_slot:
        row = mtp_by_slot.get(slot_id, {})
        delta = row.get("delta") if isinstance(row.get("delta"), dict) else {}
        mtp_ok_by_slot[slot_id] = (
            row.get("counter_continuity") is True
            and float(delta.get("num_drafts") or 0.0) > 0.0
            and float(delta.get("num_draft_tokens") or 0.0) > 0.0
            and float(delta.get("num_accepted_tokens") or 0.0) >= 0.0
        )
    per_request_mtp_ok = len(mtp_rows) == len(EXPECTED_SLOTS) and all(
        mtp_ok_by_slot.values()
    )

    queue_by_slot = {str(row.get("slot_id")): row for row in queue_rows}
    queue_ok_by_slot = {
        slot_id: (
            queue_by_slot.get(slot_id, {}).get("health_before") is True
            and queue_by_slot.get(slot_id, {}).get("health_after") is True
            and float(queue_by_slot.get(slot_id, {}).get("running_after") or 0.0) == 0.0
            and float(queue_by_slot.get(slot_id, {}).get("waiting_after") or 0.0) == 0.0
        )
        for slot_id in expected_by_slot
    }
    health_queue_ok = len(queue_rows) == len(EXPECTED_SLOTS) and all(
        queue_ok_by_slot.values()
    )

    transfer_by_slot = {str(row.get("slot_id")): row for row in transfer_rows}
    transfer_boundary_ok = len(transfer_rows) == len(EXPECTED_SLOTS) and all(
        row.get("status") in {"available", "unavailable"}
        and not (
            row.get("status") == "unavailable" and row.get("event_emitted") is True
        )
        for row in transfer_by_slot.values()
    )
    replay_deterministic = (
        replay.get("deterministic") is True
        and int(replay.get("compared_file_count") or 0) > 0
        and replay.get("mismatches") == []
    )

    trace_validation_errors = int(
        manifest.get("trace_validation_errors", validation.get("trace_validation_errors", -1))
    )
    request_stage_events = [
        event for event in events if event.get("event_type") == "request_stage"
    ]
    request_stage_event_count = len(request_stage_events)
    event_request_ids = {
        str(event.get("request_id")) for event in events if event.get("request_id")
    }
    session_ids = {
        str(event.get("session_id")) for event in events if event.get("session_id")
    }
    source_event_ids = [str(event.get("source_event_id")) for event in events]
    object_ids = {str(state_object.get("object_id")) for state_object in objects}
    decision_object_ids = {str(decision.get("object_id")) for decision in decisions}
    lifecycle_object_ids = {
        str(event.get("object_id"))
        for event in events
        if event.get("event_type") == "state_lifecycle" and event.get("object_id")
    }
    expected_object_ids = {
        f"prefix_proxy:{request_id}" for request_id in expected_request_ids
    }
    stage_actions_by_request = {
        request_id: {
            str(event.get("action"))
            for event in request_stage_events
            if event.get("request_id") == request_id
        }
        for request_id in expected_request_ids
    }
    observe_only_decisions_ok = len(decisions) == len(EXPECTED_SLOTS) and all(
        decision.get("execution_mode") == "observe_only"
        and decision.get("action") == "no_op"
        and decision.get("executed") is False
        and decision.get("execution_result") == "skipped"
        for decision in decisions
    )
    payload_refs_absent = len(objects) == len(EXPECTED_SLOTS) and all(
        state_object.get("payload_ref") is None for state_object in objects
    )
    join_coverage_complete = (
        event_request_ids == expected_request_ids
        and session_ids == {"session_p8_matrix_0001"}
        and len(source_event_ids) == len(set(source_event_ids))
        and all(
            actions == {"request_start", "first_token", "request_end"}
            for actions in stage_actions_by_request.values()
        )
        and lifecycle_object_ids == expected_object_ids
        and object_ids == expected_object_ids
        and decision_object_ids == expected_object_ids
        and manifest.get("runtime_label") == "vllm_ascend"
    )
    trace_exact = (
        trace_validation_errors == 0
        and len(events) == 24
        and request_stage_event_count == 18
        and len(objects) == 6
        and len(decisions) == 6
        and observe_only_decisions_ok
        and payload_refs_absent
        and join_coverage_complete
        and manifest.get("server_validated") is False
    )

    if successful_request_count == 0:
        grade = "red_p8_1_matrix_request_no_success"
    elif not request_matrix_exact:
        grade = "yellow_p8_1_matrix_partial"
    elif not (
        shared_prefix_exact
        and isolated_zero_hit
        and per_request_mtp_ok
        and health_queue_ok
        and transfer_boundary_ok
        and replay_deterministic
        and trace_exact
    ):
        grade = "yellow_p8_1_matrix_trace_invalid"
    elif cleanup != "clean":
        grade = "red_cleanup_incomplete"
    else:
        grade = CANDIDATE_GREEN

    join_coverage = {
        "request_runtime_object_join_complete": join_coverage_complete,
        "request_ids": sorted(event_request_ids),
        "runtime": manifest.get("runtime_label"),
        "object_ids": sorted(object_ids),
        "single_session": len(session_ids) == 1,
        "device_join_status": "unavailable_with_explicit_reason",
        "device_join_reason": (
            "bounded_public_runtime_metrics_do_not_expose_per_request_device_or_rank_identity"
        ),
        "fabricated_device_identity": False,
    }
    trace_summary = {
        "emitted_event_count": len(events),
        "request_stage_event_count": request_stage_event_count,
        "state_object_count": len(objects),
        "placement_decision_count": len(decisions),
        "observe_only_decisions_ok": observe_only_decisions_ok,
        "payload_refs_absent": payload_refs_absent,
        "trace_validation_errors": trace_validation_errors,
        "single_session": len(session_ids) == 1,
        "unique_source_event_ids": len(source_event_ids) == len(set(source_event_ids)),
    }
    grading = {
        "grade": grade,
        "successful_request_count": successful_request_count,
        "request_matrix_exact": request_matrix_exact,
        "shared_prefix_exact": shared_prefix_exact,
        "isolated_zero_hit": isolated_zero_hit,
        "per_request_mtp_ok": per_request_mtp_ok,
        "health_queue_ok": health_queue_ok,
        "transfer_boundary_ok": transfer_boundary_ok,
        "replay_deterministic": replay_deterministic,
        "join_coverage_complete": join_coverage_complete,
        "trace_validation_errors": trace_validation_errors,
        "request_stage_event_count": request_stage_event_count,
        "state_object_count": len(objects),
        "placement_decision_count": len(decisions),
        "observe_only_decisions_ok": observe_only_decisions_ok,
        "payload_refs_absent": payload_refs_absent,
        "cleanup": cleanup,
        "claim_boundary": (
            "official_mtp_multicontext_shared_prefix_observe_only_trace_not_performance"
        ),
    }
    _write_json(artifact_dir / "join_coverage.json", join_coverage)
    _write_json(artifact_dir / "trace_summary.json", trace_summary)
    _write_json(artifact_dir / "grading_inputs.json", grading)
    (artifact_dir / "first_failure_excerpt.txt").write_text(
        "" if grade == CANDIDATE_GREEN else f"grade={grade}\n",
        encoding="utf-8",
    )
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(
            [
                "# P8.1 official MTP observe-only matrix result",
                "",
                f"- grade: `{grade}`",
                f"- successful_requests: `{successful_request_count}/6`",
                f"- shared_prefix_exact: `{str(shared_prefix_exact).lower()}`",
                f"- isolated_zero_hit: `{str(isolated_zero_hit).lower()}`",
                f"- per_request_mtp_ok: `{str(per_request_mtp_ok).lower()}`",
                f"- health_queue_ok: `{str(health_queue_ok).lower()}`",
                f"- replay_deterministic: `{str(replay_deterministic).lower()}`",
                f"- join_coverage_complete: `{str(join_coverage_complete).lower()}`",
                f"- trace_validation_errors: `{trace_validation_errors}`",
                f"- cleanup: `{cleanup}`",
                "- boundary: six sequential official-MTP observe-only requests; not a performance comparison.",
                "- device join: unavailable with an explicit reason; no rank or device identity was fabricated.",
                "- content retention: completion content and generated token IDs are not retained.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return grading


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finalize the bounded P8.1 matrix")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    grading = finalize_matrix_artifacts(args.artifact_dir)
    print(json.dumps(grading, sort_keys=True))
    return 0 if grading["grade"] == CANDIDATE_GREEN else 1


if __name__ == "__main__":
    raise SystemExit(main())
