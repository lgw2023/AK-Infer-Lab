from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import yaml

from ..models import StateEvent
from ..validation import ValidationError, validate_record
from .base import AdaptedTrace, AdapterError


FORBIDDEN_FIELDS = {
    "data",
    "execute",
    "mutation",
    "payload",
    "payload_ref",
    "placement_decision",
    "target_rank",
    "tensor",
}


class VllmAscendAdapter:
    """Normalize bounded vLLM-Ascend observations without runtime imports."""

    mode = "observe_only"
    payload_move_allowed = False
    placement_mutation_allowed = False

    def __init__(self, *, baseline_contract: Path, model_id: str) -> None:
        self.baseline_contract = baseline_contract
        self.model_id = model_id
        self._validate_baseline_contract()

    def read(self, source: Path) -> AdaptedTrace:
        events: list[StateEvent] = []
        seen_source_ids: set[str] = set()
        source_record_count = 0

        with source.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                source_record_count += 1
                record = _load_record(line, line_number)
                _validate_source_record(record, line_number)

                source_event_id = str(record["source_event_id"])
                if source_event_id in seen_source_ids:
                    raise AdapterError(
                        f"duplicate source_event_id: {source_event_id}"
                    )
                seen_source_ids.add(source_event_id)

                reason = "mapped_from_vllm_ascend_observation"
                if record["reason"]:
                    reason += f";{record['reason']}"
                event = StateEvent(
                    schema_version="0.2.0",
                    event_id=f"p8:vllm_ascend:{source_event_id}",
                    timestamp_ns=int(record["timestamp_ns"]),
                    trace_id=str(record["trace_id"]),
                    request_id=_optional_string(record["request_id"]),
                    session_id=_optional_string(record["session_id"]),
                    object_id=_optional_string(record["object_id"]),
                    object_type=_optional_string(record["object_type"]),
                    model_id=self.model_id,
                    runtime="vllm_ascend",
                    rank_id=_optional_integer(record["rank_id"]),
                    layer_id=None,
                    phase=str(record["phase"]),
                    event_type=str(record["event_type"]),
                    action=str(record["action"]),
                    source_tier=_optional_string(record["source_tier"]),
                    target_tier=_optional_string(record["target_tier"]),
                    bytes=_optional_integer(record["bytes"]),
                    latency_ms=_optional_number(record["latency_ms"]),
                    source_event_id=source_event_id,
                    evidence_source=str(record["evidence_source"]),
                    artifact_path=source.as_posix(),
                    reason=reason,
                )
                try:
                    validate_record("state_event", asdict(event))
                except ValidationError as exc:
                    raise AdapterError(f"line {line_number}: {exc}") from exc
                events.append(event)

        if source_record_count == 0:
            raise AdapterError("observation source must contain at least one record")

        return AdaptedTrace(
            events=tuple(events),
            source_record_count=source_record_count,
            emitted_event_count=len(events),
            skipped_record_count=0,
            warnings=(),
        )

    def _validate_baseline_contract(self) -> None:
        try:
            contract = yaml.safe_load(
                self.baseline_contract.read_text(encoding="utf-8")
            )
        except (OSError, yaml.YAMLError) as exc:
            raise AdapterError(
                f"cannot read baseline contract: {self.baseline_contract}"
            ) from exc
        if not isinstance(contract, dict):
            raise AdapterError("baseline contract must be a YAML mapping")

        selected = contract.get("selected_workload")
        adapter = contract.get("adapter")
        gate = contract.get("gate")
        valid = (
            contract.get("contract_status") == "frozen_degraded"
            and isinstance(selected, dict)
            and selected.get("model_id") == self.model_id
            and selected.get("request_success") is True
            and selected.get("validated") is True
            and isinstance(adapter, dict)
            and adapter.get("mode") == "observe_only"
            and adapter.get("payload_move_allowed") is False
            and adapter.get("placement_mutation_allowed") is False
            and isinstance(gate, dict)
            and gate.get("real_vllm_ascend_adapter") == "open_observe_only"
        )
        if not valid:
            raise AdapterError(
                "VllmAscendAdapter requires a frozen_degraded baseline contract "
                "with the observe-only gate open"
            )


def _load_record(line: str, line_number: int) -> Mapping[str, Any]:
    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        raise AdapterError(
            f"line {line_number} is not valid JSON: {exc.msg}"
        ) from exc
    if not isinstance(record, dict):
        raise AdapterError(f"line {line_number} must contain a JSON object")
    return record


def _validate_source_record(record: Mapping[str, Any], line_number: int) -> None:
    forbidden = sorted(FORBIDDEN_FIELDS & set(record))
    if forbidden:
        raise AdapterError(
            f"line {line_number} forbidden fields: {', '.join(forbidden)}"
        )
    try:
        validate_record("vllm_ascend_observation", record)
    except ValidationError as exc:
        raise AdapterError(f"line {line_number}: {exc}") from exc

    for field in ("source_event_id", "trace_id", "request_id", "action"):
        _require_string(record[field], line_number, field)
    if record["bytes"] is not None and record["bytes"] < 0:
        raise AdapterError(f"line {line_number} bytes must be >= 0")
    if record["latency_ms"] is not None and record["latency_ms"] < 0:
        raise AdapterError(f"line {line_number} latency_ms must be >= 0")

    if record["event_type"] == "request_stage":
        if record["object_id"] is not None or record["object_type"] is not None:
            raise AdapterError(
                f"line {line_number} request_stage must not identify a state object"
            )
        if record["bytes"] is not None:
            raise AdapterError(f"line {line_number} request_stage bytes must be null")
        if record["source_tier"] is not None or record["target_tier"] is not None:
            raise AdapterError(
                f"line {line_number} request_stage tiers must be null"
            )
        return

    _require_string(record["object_id"], line_number, "object_id")
    if record["event_type"] == "transfer":
        if record["source_tier"] is None or record["target_tier"] is None:
            raise AdapterError(
                f"line {line_number} transfer requires source_tier and target_tier"
            )
        if record["bytes"] is None and not record["reason"]:
            raise AdapterError(
                f"line {line_number} transfer with null bytes requires a non-empty reason"
            )


def _require_string(value: Any, line_number: int, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise AdapterError(f"line {line_number} {field} must be non-empty string")


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_integer(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_number(value: Any) -> float | None:
    return None if value is None else float(value)
