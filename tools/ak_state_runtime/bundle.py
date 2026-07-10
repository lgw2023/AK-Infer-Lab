from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

import yaml

from .replay import ReplayResult, validate_replay_result


class BundleError(ValueError):
    """Raised when a deterministic trace bundle cannot be published safely."""


def write_bundle(
    result: ReplayResult,
    output_dir: Path,
    *,
    source_artifact: Path,
) -> Path:
    errors = validate_replay_result(result)
    if errors:
        raise BundleError("; ".join(errors))
    if not source_artifact.is_file():
        raise BundleError(f"source artifact does not exist: {source_artifact}")
    if output_dir.exists():
        raise BundleError(f"output directory already exists: {output_dir}")

    runtime_labels = {event.runtime for event in result.events}
    if len(runtime_labels) != 1:
        raise BundleError(f"bundle must contain exactly one runtime label: {runtime_labels}")

    output_dir.mkdir(parents=True)
    data_files = {
        "state_objects.jsonl": _jsonl_bytes(
            asdict(item) for item in result.state_objects
        ),
        "state_events.jsonl": _jsonl_bytes(asdict(item) for item in result.events),
        "placement_decisions.jsonl": _jsonl_bytes(
            asdict(item) for item in result.placement_decisions
        ),
    }
    for filename, content in data_files.items():
        (output_dir / filename).write_bytes(content)

    validation_report = {
        "errors": [],
        "trace_validation_errors": 0,
        "warnings": [asdict(warning) for warning in result.warnings],
    }
    (output_dir / "validation_report.json").write_bytes(
        _json_bytes(validation_report, indent=2)
    )

    hashed_files = [*data_files, "validation_report.json"]
    artifact_sha256 = {
        filename: _sha256(output_dir / filename) for filename in sorted(hashed_files)
    }
    manifest = {
        "artifact_sha256": artifact_sha256,
        "claim_level": "toolchain_only",
        "emitted_event_count": result.emitted_event_count,
        "placement_decision_count": len(result.placement_decisions),
        "provenance_mode": "offline_fixture",
        "runtime_label": next(iter(runtime_labels)),
        "schema_version": "0.2.0",
        "server_validated": False,
        "skipped_record_count": result.skipped_record_count,
        "slice_id": "p8_offline_observe_only_tracer_bullet",
        "source_artifact": source_artifact.as_posix(),
        "source_record_count": result.source_record_count,
        "source_sha256": _sha256(source_artifact),
        "state_object_count": len(result.state_objects),
        "trace_validation_errors": 0,
        "warning_count": len(result.warnings),
    }
    manifest_text = yaml.safe_dump(
        manifest,
        allow_unicode=True,
        sort_keys=True,
    )
    (output_dir / "manifest.yaml").write_text(manifest_text, encoding="utf-8")
    return output_dir


def _jsonl_bytes(records: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(_json_bytes(record) for record in records)


def _json_bytes(record: Any, *, indent: int | None = None) -> bytes:
    return (
        json.dumps(
            record,
            ensure_ascii=False,
            indent=indent,
            separators=None if indent is not None else (",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
