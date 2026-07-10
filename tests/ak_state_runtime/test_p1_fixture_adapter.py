import json
from pathlib import Path

import pytest

from tools.ak_state_runtime.adapters.base import AdapterError
from tools.ak_state_runtime.adapters.p1_fixture import P1FixtureAdapter


P1_FIXTURE = Path(
    "工作记录与进度笔记本/p1_inference_contracts/fixtures/minimal_runtime_trace.jsonl"
)


def _read_fixture():
    return P1FixtureAdapter(
        model_id="p1_fixture_model",
        runtime_label="vllm_ascend",
    ).read(P1_FIXTURE)


def test_adapter_maps_all_eight_p1_records_without_skips() -> None:
    adapted = _read_fixture()

    assert adapted.source_record_count == 8
    assert adapted.emitted_event_count == 8
    assert adapted.skipped_record_count == 0
    assert len(adapted.events) == 8
    assert sum(event.event_type == "request_stage" for event in adapted.events) == 3
    assert sum(event.event_type == "transfer" for event in adapted.events) == 1
    assert sum(event.event_type == "state_lifecycle" for event in adapted.events) == 4


def test_adapter_is_the_only_p1_to_p8_object_type_mapping_boundary() -> None:
    adapted = _read_fixture()
    object_types = {event.object_type for event in adapted.events if event.object_type}

    assert object_types == {"kv_block", "prefix_block"}
    assert {event.runtime for event in adapted.events} == {"vllm_ascend"}
    assert {event.model_id for event in adapted.events} == {"p1_fixture_model"}
    assert {event.evidence_source for event in adapted.events} == {"offline_fixture"}


def test_adapter_preserves_unambiguous_bytes_and_marks_ambiguous_bytes() -> None:
    adapted = _read_fixture()
    by_source_id = {event.source_event_id: event for event in adapted.events}

    assert by_source_id["evt_prefix_group_a_hit"].bytes == 524_288
    assert by_source_id["evt_kv_l00_restore_done"].bytes == 1_048_576
    assert by_source_id["evt_copy_kv_l00_h2d_done"].bytes == 1_048_576
    assert by_source_id["evt_op_l00_prefill_attention_start"].bytes is None
    assert by_source_id["evt_op_l00_decode_attention_end"].bytes is None
    assert "ambiguous_read_write_bytes" in by_source_id[
        "evt_op_l00_prefill_attention_start"
    ].reason
    assert len(adapted.warnings) == 2


def test_adapter_maps_hit_miss_rank_and_latency_without_payload_access() -> None:
    adapted = _read_fixture()
    by_source_id = {event.source_event_id: event for event in adapted.events}

    prefix_hit = by_source_id["evt_prefix_group_a_hit"]
    kv_miss = by_source_id["evt_kv_l00_restore_done"]

    assert prefix_hit.action == "hit"
    assert prefix_hit.rank_id is None
    assert prefix_hit.latency_ms == pytest.approx(0.055)
    assert kv_miss.action == "miss"
    assert kv_miss.rank_id == 0
    assert kv_miss.source_tier == "pinned_dram"
    assert kv_miss.target_tier == "hbm"


def _mutated_fixture(tmp_path: Path, mutate) -> Path:
    records = [json.loads(line) for line in P1_FIXTURE.read_text(encoding="utf-8").splitlines()]
    mutate(records)
    path = tmp_path / "mutated.jsonl"
    path.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def test_adapter_rejects_duplicate_event_ids(tmp_path: Path) -> None:
    source = _mutated_fixture(
        tmp_path,
        lambda records: records[1].__setitem__("event_id", records[0]["event_id"]),
    )
    adapter = P1FixtureAdapter(model_id="fixture", runtime_label="vllm_ascend")

    with pytest.raises(AdapterError, match="duplicate event_id: evt_req_enqueue"):
        adapter.read(source)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda record: record.pop("trace_id"), "missing required fields: trace_id"),
        (lambda record: record.__setitem__("event_id", None), "event_id must be non-empty string"),
        (
            lambda record: record.__setitem__("schema_version", "9.9.9"),
            "schema_version must be 0.1.0",
        ),
        (
            lambda record: record.__setitem__("timestamp_ns", "1000"),
            "timestamp_ns must be integer",
        ),
    ],
)
def test_adapter_validates_the_p1_record_contract(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    source = _mutated_fixture(tmp_path, lambda records: mutation(records[0]))
    adapter = P1FixtureAdapter(model_id="fixture", runtime_label="vllm_ascend")

    with pytest.raises(AdapterError, match=message):
        adapter.read(source)


def test_adapter_skips_unknown_resource_scope_even_when_object_id_exists(
    tmp_path: Path,
) -> None:
    source = _mutated_fixture(
        tmp_path,
        lambda records: records[2].__setitem__(
            "resource_scope", "private_runtime_scope"
        ),
    )

    adapted = P1FixtureAdapter(
        model_id="fixture",
        runtime_label="vllm_ascend",
    ).read(source)

    assert len(adapted.events) == 7
    assert adapted.source_record_count == 8
    assert adapted.skipped_record_count == 1
    assert adapted.warnings[0].reason == "unsupported_resource_scope_or_object_type"
