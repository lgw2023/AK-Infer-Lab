from dataclasses import asdict

import pytest

from tools.ak_state_runtime.models import PlacementDecision, StateEvent, StateObject
from tools.ak_state_runtime.validation import ValidationError, load_contracts, validate_record


def _state_event() -> StateEvent:
    return StateEvent(
        schema_version="0.2.0",
        event_id="evt_prefix_hit",
        timestamp_ns=1_000,
        trace_id="trace_001",
        request_id="req_001",
        session_id="session_001",
        object_id="prefix:group_a",
        object_type="prefix_block",
        model_id="fixture_model",
        runtime="vllm_ascend",
        rank_id=0,
        layer_id=0,
        phase="prefill",
        event_type="state_lifecycle",
        action="hit",
        source_tier="hbm",
        target_tier="hbm",
        bytes=524_288,
        latency_ms=0.055,
        source_event_id="p1_evt_prefix_hit",
        evidence_source="offline_fixture",
        artifact_path="fixtures/minimal_runtime_trace.jsonl",
        reason="mapped_from_p1_fixture",
    )


def _state_object() -> StateObject:
    return StateObject(
        schema_version="0.2.0",
        object_id="prefix:group_a",
        object_type="prefix_block",
        model_id="fixture_model",
        layer_id=0,
        expert_id=None,
        owner_request_id="req_001",
        session_id="session_001",
        scope="session",
        payload_ref=None,
        bytes=524_288,
        precision=None,
        layout=None,
        checksum_or_version=None,
        current_tier="hbm",
        current_rank=0,
        target_tier="none",
        hotness_score=None,
        reuse_distance=None,
        next_use_estimate_ms=None,
        load_cost_ms=None,
        evict_cost_ms=None,
        recompute_cost_ms=None,
        prefetch_lead_time_ms=None,
        hit_count=1,
        miss_count=0,
        last_access_ts_ns=1_000,
        evidence_source="offline_fixture",
        quality_risk="high",
    )


def _placement_decision() -> PlacementDecision:
    return PlacementDecision(
        schema_version="0.2.0",
        decision_id="decision:p1_evt_prefix_hit",
        object_id="prefix:group_a",
        policy_name="observe_only",
        policy_version="0.1.0",
        action="no_op",
        source_tier="hbm",
        target_tier="hbm",
        issued_ts_ns=1_000,
        deadline_ts_ns=None,
        expected_benefit_ms=None,
        expected_cost_ms=None,
        confidence=None,
        execution_mode="observe_only",
        executed=False,
        execution_result="skipped",
        reason="observe_only_does_not_move_payload",
    )


def test_contracts_expose_v020_fields_and_enums() -> None:
    contracts = load_contracts()

    assert set(contracts) == {"state_object", "state_event", "placement_decision"}
    assert {contract["schema_version"] for contract in contracts.values()} == {"0.2.0"}
    assert "object_id" in contracts["state_object"]["required_fields"]
    assert "source_event_id" in contracts["state_event"]["required_fields"]
    assert "execution_mode" in contracts["placement_decision"]["required_fields"]
    assert "prefix_block" in contracts["state_object"]["enums"]["object_type"]
    assert "transfer" in contracts["state_event"]["enums"]["event_type"]
    assert "observe_only" in contracts["placement_decision"]["enums"]["execution_mode"]


@pytest.mark.parametrize(
    ("contract_name", "record"),
    [
        ("state_object", _state_object()),
        ("state_event", _state_event()),
        ("placement_decision", _placement_decision()),
    ],
)
def test_model_records_validate(contract_name: str, record: object) -> None:
    validate_record(contract_name, asdict(record))


def test_missing_required_field_is_rejected() -> None:
    record = asdict(_state_event())
    del record["trace_id"]

    with pytest.raises(ValidationError, match="missing required fields: trace_id"):
        validate_record("state_event", record)


def test_invalid_enum_is_rejected() -> None:
    record = asdict(_placement_decision())
    record["execution_mode"] = "secret_runtime_mode"

    with pytest.raises(ValidationError, match="execution_mode"):
        validate_record("placement_decision", record)


def test_nullable_values_are_explicitly_allowed() -> None:
    record = asdict(_state_object())
    record["bytes"] = None
    record["current_tier"] = "unknown"

    validate_record("state_object", record)
