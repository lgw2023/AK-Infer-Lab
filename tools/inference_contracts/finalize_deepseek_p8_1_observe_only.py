from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import yaml


CANDIDATE_GREEN = "candidate_green_p8_1_official_mtp_observe_only_trace"


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


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    bundle_dir = artifact_dir / "observe_only_bundle"
    request = _load_json(artifact_dir / "request_result.json")
    prefix = _load_json(artifact_dir / "prefix_cache_metrics.json")
    mtp = _load_json(artifact_dir / "mtp_metrics.json")
    transfer = _load_json(artifact_dir / "transfer_availability.json")
    manifest = yaml.safe_load((bundle_dir / "manifest.yaml").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("observe-only bundle manifest must be a YAML mapping")
    validation = _load_json(bundle_dir / "validation_report.json")
    events = _load_jsonl(bundle_dir / "state_events.jsonl")
    objects = _load_jsonl(bundle_dir / "state_objects.jsonl")
    decisions = _load_jsonl(bundle_dir / "placement_decisions.jsonl")
    cleanup = (artifact_dir / "cleanup_status.txt").read_text(encoding="utf-8").strip()

    request_exact = (
        request.get("status") == "success"
        and request.get("http_status") == 200
        and request.get("prompt_tokens") == 4096
        and request.get("generated_token_count") == 64
        and request.get("streamed_token_count") == 64
        and request.get("finish_reason") == "length"
        and request.get("generated_text_retained") is False
        and request.get("token_ids_retained") is False
    )
    mtp_delta = mtp.get("delta") if isinstance(mtp.get("delta"), dict) else {}
    mtp_activity_ok = (
        mtp.get("counter_continuity") is True
        and float(mtp_delta.get("num_drafts") or 0.0) > 0.0
        and float(mtp_delta.get("num_draft_tokens") or 0.0) > 0.0
        and float(mtp_delta.get("num_accepted_tokens") or 0.0) >= 0.0
    )
    trace_validation_errors = int(
        manifest.get("trace_validation_errors", validation.get("trace_validation_errors", -1))
    )
    request_stage_event_count = sum(
        event.get("event_type") == "request_stage" for event in events
    )
    observe_only_decisions_ok = bool(decisions) and all(
        decision.get("execution_mode") == "observe_only"
        and decision.get("action") == "no_op"
        and decision.get("executed") is False
        and decision.get("execution_result") == "skipped"
        for decision in decisions
    )
    payload_refs_absent = bool(objects) and all(
        state_object.get("payload_ref") is None for state_object in objects
    )
    trace_exact = (
        trace_validation_errors == 0
        and request_stage_event_count == 3
        and len(objects) == 1
        and len(decisions) == 1
        and observe_only_decisions_ok
        and payload_refs_absent
        and manifest.get("server_validated") is False
        and manifest.get("runtime_label") == "vllm_ascend"
    )
    prefix_delta = prefix.get("delta") if isinstance(prefix.get("delta"), dict) else {}
    prefix_observation_ok = float(prefix_delta.get("queries") or 0.0) > 0.0
    transfer_boundary_ok = (
        transfer.get("status") in {"available", "unavailable"}
        and not (
            transfer.get("status") == "unavailable"
            and transfer.get("event_emitted") is True
        )
    )

    if not request_exact:
        grade = "red_p8_1_official_mtp_request_no_success"
    elif not (trace_exact and mtp_activity_ok and prefix_observation_ok and transfer_boundary_ok):
        grade = "yellow_p8_1_official_mtp_trace_invalid"
    elif cleanup != "clean":
        grade = "red_cleanup_incomplete"
    else:
        grade = CANDIDATE_GREEN

    trace_summary = {
        "emitted_event_count": len(events),
        "request_stage_event_count": request_stage_event_count,
        "state_object_count": len(objects),
        "placement_decision_count": len(decisions),
        "observe_only_decisions_ok": observe_only_decisions_ok,
        "payload_refs_absent": payload_refs_absent,
        "trace_validation_errors": trace_validation_errors,
        "prefix_query_delta": prefix_delta.get("queries"),
        "prefix_hit_delta": prefix_delta.get("hits"),
        "transfer_status": transfer.get("status"),
        "synthetic_transfer_emitted": (
            transfer.get("status") == "unavailable"
            and transfer.get("event_emitted") is True
        ),
    }
    grading = {
        "grade": grade,
        "request_exact": request_exact,
        "mtp_activity_ok": mtp_activity_ok,
        "prefix_observation_ok": prefix_observation_ok,
        "transfer_boundary_ok": transfer_boundary_ok,
        "trace_validation_errors": trace_validation_errors,
        "request_stage_event_count": request_stage_event_count,
        "state_object_count": len(objects),
        "placement_decision_count": len(decisions),
        "observe_only_decisions_ok": observe_only_decisions_ok,
        "payload_refs_absent": payload_refs_absent,
        "cleanup": cleanup,
        "claim_boundary": "official_mtp_4096_64_c1_observe_only_trace_not_performance",
    }
    _write_json(artifact_dir / "trace_summary.json", trace_summary)
    _write_json(artifact_dir / "grading_inputs.json", grading)
    (artifact_dir / "first_failure_excerpt.txt").write_text(
        "" if grade == CANDIDATE_GREEN else f"grade={grade}\n",
        encoding="utf-8",
    )
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(
            [
                "# P8.1 official MTP observe-only result",
                "",
                f"- grade: `{grade}`",
                f"- request_exact: `{str(request_exact).lower()}`",
                f"- mtp_activity_ok: `{str(mtp_activity_ok).lower()}`",
                f"- request_stage_events: `{request_stage_event_count}`",
                f"- state_objects: `{len(objects)}`",
                f"- placement_decisions: `{len(decisions)}`",
                f"- trace_validation_errors: `{trace_validation_errors}`",
                f"- cleanup: `{cleanup}`",
                "- boundary: one official MTP 4096+64+c1 observe-only trace; not a performance comparison.",
                "- content retention: completion content and token IDs are not retained.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return grading


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finalize the bounded P8.1 trace")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    grading = finalize_artifacts(args.artifact_dir)
    print(json.dumps(grading, sort_keys=True))
    return 0 if grading["grade"] == CANDIDATE_GREEN else 1


if __name__ == "__main__":
    raise SystemExit(main())
