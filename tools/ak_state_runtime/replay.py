from __future__ import annotations

from dataclasses import asdict, dataclass

from .adapters.base import AdaptedTrace, AdapterWarning
from .models import PlacementDecision, StateEvent, StateObject
from .policies.observe_only import ObserveOnlyPolicy
from .registry import StateRegistry
from .validation import ValidationError, validate_record


@dataclass(frozen=True)
class ReplayResult:
    events: tuple[StateEvent, ...]
    state_objects: tuple[StateObject, ...]
    placement_decisions: tuple[PlacementDecision, ...]
    source_record_count: int
    emitted_event_count: int
    skipped_record_count: int
    warnings: tuple[AdapterWarning, ...]


def replay(
    adapted: AdaptedTrace,
    registry: StateRegistry | None = None,
    policy: ObserveOnlyPolicy | None = None,
) -> ReplayResult:
    registry = registry or StateRegistry()
    policy = policy or ObserveOnlyPolicy()
    events = tuple(sorted(adapted.events, key=lambda event: (event.timestamp_ns, event.event_id)))
    decisions: list[PlacementDecision] = []

    for event in events:
        validate_record("state_event", asdict(event))
        registry.apply(event)
        decision = policy.decide(event)
        if decision is not None:
            decisions.append(decision)

    result = ReplayResult(
        events=events,
        state_objects=registry.snapshot(),
        placement_decisions=tuple(decisions),
        source_record_count=adapted.source_record_count,
        emitted_event_count=adapted.emitted_event_count,
        skipped_record_count=adapted.skipped_record_count,
        warnings=adapted.warnings,
    )
    errors = validate_replay_result(result)
    if errors:
        raise ValueError("; ".join(errors))
    return result


def validate_replay_result(result: ReplayResult) -> tuple[str, ...]:
    errors: list[str] = []
    for event in result.events:
        _append_record_error(errors, "event", event.event_id, "state_event", asdict(event))
    for state_object in result.state_objects:
        _append_record_error(
            errors,
            "object",
            state_object.object_id,
            "state_object",
            asdict(state_object),
        )
    for decision in result.placement_decisions:
        _append_record_error(
            errors,
            "decision",
            decision.decision_id,
            "placement_decision",
            asdict(decision),
        )

    if result.emitted_event_count != len(result.events):
        errors.append(
            f"emitted_event_count {result.emitted_event_count} does not match "
            f"{len(result.events)} events"
        )
    if result.source_record_count != result.emitted_event_count + result.skipped_record_count:
        errors.append(
            f"source_record_count {result.source_record_count} does not equal emitted "
            f"{result.emitted_event_count} plus skipped {result.skipped_record_count}"
        )
    _append_duplicate_errors(
        errors,
        "event_id",
        [event.event_id for event in result.events],
    )
    _append_duplicate_errors(
        errors,
        "object_id",
        [state_object.object_id for state_object in result.state_objects],
    )
    _append_duplicate_errors(
        errors,
        "decision_id",
        [decision.decision_id for decision in result.placement_decisions],
    )

    object_ids = {state_object.object_id for state_object in result.state_objects}
    referenced_object_ids = {
        event.object_id for event in result.events if event.object_id is not None
    }
    for event in result.events:
        if event.event_type != "request_stage" and (
            event.object_id is None or event.object_type is None
        ):
            errors.append(
                f"{event.event_type} event {event.event_id} requires object_id and object_type"
            )
    for object_id in sorted(referenced_object_ids - object_ids):
        errors.append(f"event references missing object {object_id}")
    for object_id in sorted(object_ids - referenced_object_ids):
        errors.append(f"object {object_id} has no source event")

    expected_decisions = {
        f"decision:{event.source_event_id}": event
        for event in result.events
        if event.object_id is not None
    }
    actual_decisions = {
        decision.decision_id: decision for decision in result.placement_decisions
    }
    for decision_id in sorted(expected_decisions.keys() - actual_decisions.keys()):
        event = expected_decisions[decision_id]
        errors.append(f"object event {event.event_id} missing decision {decision_id}")
    for decision_id in sorted(actual_decisions.keys() - expected_decisions.keys()):
        errors.append(f"decision {decision_id} has no object-bearing source event")
    for decision_id in sorted(expected_decisions.keys() & actual_decisions.keys()):
        event = expected_decisions[decision_id]
        decision = actual_decisions[decision_id]
        if decision.object_id != event.object_id:
            errors.append(
                f"decision {decision_id} object {decision.object_id} does not match "
                f"event object {event.object_id}"
            )
    for decision in result.placement_decisions:
        if decision.object_id not in object_ids:
            errors.append(
                f"decision {decision.decision_id} references missing object {decision.object_id}"
            )
    return tuple(errors)


def _append_record_error(
    errors: list[str],
    label: str,
    record_id: str,
    contract_name: str,
    record: dict[str, object],
) -> None:
    try:
        validate_record(contract_name, record)
    except ValidationError as exc:
        errors.append(f"{label} {record_id}: {exc}")


def _append_duplicate_errors(errors: list[str], label: str, values: list[str]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    for value in sorted(duplicates):
        errors.append(f"duplicate {label}: {value}")
