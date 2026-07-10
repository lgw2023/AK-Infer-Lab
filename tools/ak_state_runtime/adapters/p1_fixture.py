from __future__ import annotations

import json
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

from ..models import StateEvent
from ..validation import ValidationError, load_contracts, validate_record
from .base import AdaptedTrace, AdapterError, AdapterWarning


OBJECT_TYPE_MAP = {
    "kv": "kv_block",
    "prefix": "prefix_block",
}
P1_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "工作记录与进度笔记本/p1_inference_contracts/unified_event_schema.yaml"
)


class P1FixtureAdapter:
    """Read-only anti-corruption adapter for the P1 0.1.0 JSONL contract."""

    def __init__(self, *, model_id: str, runtime_label: str) -> None:
        self.model_id = model_id
        self.runtime_label = runtime_label

    def read(self, source: Path) -> AdaptedTrace:
        events: list[StateEvent] = []
        warnings: list[AdapterWarning] = []
        seen_source_ids: set[str] = set()
        source_record_count = 0
        skipped_record_count = 0

        with source.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                source_record_count += 1
                record = self._load_record(line, line_number)
                self._validate_p1_record(record, line_number)

                source_event_id = str(record["event_id"])
                if source_event_id in seen_source_ids:
                    raise AdapterError(f"duplicate event_id: {source_event_id}")
                seen_source_ids.add(source_event_id)

                event_type = self._map_event_type(record)
                object_type = self._map_object_type(record)
                if event_type is None or object_type is _UNSUPPORTED:
                    skipped_record_count += 1
                    warnings.append(
                        AdapterWarning(
                            line_number=line_number,
                            source_event_id=source_event_id,
                            reason="unsupported_resource_scope_or_object_type",
                        )
                    )
                    continue

                object_bytes, byte_reason = self._object_bytes(record)
                reasons = ["mapped_from_p1_fixture"]
                if byte_reason:
                    reasons.append(byte_reason)
                    warnings.append(
                        AdapterWarning(
                            line_number=line_number,
                            source_event_id=source_event_id,
                            reason=byte_reason,
                        )
                    )

                phase = str(record["phase"])
                allowed_phases = load_contracts()["state_event"]["enums"]["phase"]
                if phase not in allowed_phases:
                    reasons.append(f"source_phase={phase}")
                    phase = "unknown"

                event = StateEvent(
                    schema_version="0.2.0",
                    event_id=f"p8:{source_event_id}",
                    timestamp_ns=record["timestamp_ns"],
                    trace_id=str(record["trace_id"]),
                    request_id=_optional_string(record.get("request_id")),
                    session_id=_optional_string(record.get("session_id")),
                    object_id=_optional_string(record.get("object_id")),
                    object_type=object_type,
                    model_id=self.model_id,
                    runtime=self.runtime_label,
                    rank_id=_rank_id(record.get("device_id")),
                    layer_id=_optional_integer(record.get("layer_id")),
                    phase=phase,
                    event_type=event_type,
                    action=_action(record),
                    source_tier=_optional_string(record.get("source_tier")),
                    target_tier=_optional_string(record.get("target_tier")),
                    bytes=object_bytes,
                    latency_ms=_latency_ms(record.get("latency_us")),
                    source_event_id=source_event_id,
                    evidence_source="offline_fixture",
                    artifact_path=str(record.get("artifact_path") or source.as_posix()),
                    reason=";".join(reasons),
                )
                try:
                    validate_record("state_event", asdict(event))
                except ValidationError as exc:
                    raise AdapterError(f"line {line_number}: {exc}") from exc
                events.append(event)

        return AdaptedTrace(
            events=tuple(events),
            source_record_count=source_record_count,
            emitted_event_count=len(events),
            skipped_record_count=skipped_record_count,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _load_record(line: str, line_number: int) -> Mapping[str, Any]:
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"line {line_number} is not valid JSON: {exc.msg}") from exc
        if not isinstance(record, dict):
            raise AdapterError(f"line {line_number} must contain a JSON object")
        return record

    @staticmethod
    def _validate_p1_record(record: Mapping[str, Any], line_number: int) -> None:
        schema = _load_p1_schema()
        fields = schema["fields"]
        required = {field["name"] for field in fields if field.get("required")}
        missing = sorted(field for field in required if field not in record)
        if missing:
            raise AdapterError(
                f"line {line_number} missing required fields: {', '.join(missing)}"
            )

        if record.get("schema_version") != "0.1.0":
            raise AdapterError(
                f"line {line_number} schema_version must be 0.1.0, "
                f"got {record.get('schema_version')!r}"
            )
        for field_name in ("event_id", "trace_id"):
            value = record.get(field_name)
            if not isinstance(value, str) or not value:
                raise AdapterError(
                    f"line {line_number} {field_name} must be non-empty string"
                )

        for field in fields:
            field_name = field["name"]
            value = record[field_name]
            if value is None:
                if not field.get("nullable"):
                    raise AdapterError(f"line {line_number} {field_name} must not be null")
                continue
            _validate_p1_type(line_number, field, value)

        scope = record.get("resource_scope")
        if scope != "microbench_profile":
            request_id = record.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                raise AdapterError(
                    f"line {line_number} request_id must be non-empty outside microbench"
                )

    @staticmethod
    def _map_event_type(record: Mapping[str, Any]) -> str | None:
        scope = record.get("resource_scope")
        if scope == "request_runtime_profile":
            return "request_stage"
        if scope == "transfer_overlap_profile":
            return "transfer"
        if scope in {"operator_timeline_profile", "state_object_profile"} and record.get(
            "object_id"
        ) is not None:
            return "state_lifecycle"
        return None

    @staticmethod
    def _map_object_type(record: Mapping[str, Any]) -> str | None | object:
        if record.get("object_id") is None:
            return None
        return OBJECT_TYPE_MAP.get(str(record.get("object_type")), _UNSUPPORTED)

    @staticmethod
    def _object_bytes(record: Mapping[str, Any]) -> tuple[int | None, str | None]:
        bytes_read = record.get("bytes_read") or 0
        bytes_write = record.get("bytes_write") or 0
        if bytes_read > 0 and bytes_write == 0:
            return int(bytes_read), None
        if bytes_write > 0 and bytes_read == 0:
            return int(bytes_write), None
        if bytes_read > 0 and bytes_read == bytes_write:
            return int(bytes_read), None
        if bytes_read > 0 and bytes_write > 0:
            return None, "ambiguous_read_write_bytes"
        return None, None


_UNSUPPORTED = object()


@lru_cache(maxsize=1)
def _load_p1_schema() -> dict[str, Any]:
    with P1_SCHEMA_PATH.open(encoding="utf-8") as handle:
        schema = yaml.safe_load(handle)
    if not isinstance(schema, dict) or not isinstance(schema.get("fields"), list):
        raise AdapterError(f"invalid P1 schema: {P1_SCHEMA_PATH}")
    return schema


def _validate_p1_type(line_number: int, field: Mapping[str, Any], value: Any) -> None:
    field_name = str(field["name"])
    expected = field.get("type")
    predicates = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "enum": lambda item: isinstance(item, str),
    }
    if expected not in predicates or not predicates[expected](value):
        raise AdapterError(
            f"line {line_number} {field_name} must be {expected}, "
            f"got {type(value).__name__}"
        )
    allowed = field.get("enum")
    if allowed is not None and value not in allowed:
        raise AdapterError(
            f"line {line_number} {field_name} must be one of {allowed}, got {value!r}"
        )


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_integer(value: Any) -> int | None:
    return None if value is None else int(value)


def _rank_id(device_id: Any) -> int | None:
    if not isinstance(device_id, str) or not device_id.startswith("npu:"):
        return None
    try:
        return int(device_id.split(":", maxsplit=1)[1])
    except ValueError:
        return None


def _latency_ms(latency_us: Any) -> float | None:
    if latency_us is None:
        return None
    return float(latency_us) / 1_000.0


def _action(record: Mapping[str, Any]) -> str:
    hit_or_miss = record.get("hit_or_miss")
    if hit_or_miss in {"hit", "miss"}:
        return str(hit_or_miss)
    return str(record.get("op_name") or "observe")
