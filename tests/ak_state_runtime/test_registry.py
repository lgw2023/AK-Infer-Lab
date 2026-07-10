from dataclasses import replace
from pathlib import Path

from tools.ak_state_runtime.adapters.p1_fixture import P1FixtureAdapter
from tools.ak_state_runtime.registry import StateRegistry


P1_FIXTURE = Path(
    "工作记录与进度笔记本/p1_inference_contracts/fixtures/minimal_runtime_trace.jsonl"
)


def _events():
    return P1FixtureAdapter(
        model_id="p1_fixture_model",
        runtime_label="vllm_ascend",
    ).read(P1_FIXTURE).events


def test_registry_ignores_request_only_events_and_tracks_two_objects() -> None:
    registry = StateRegistry()

    for event in _events():
        registry.apply(event)

    objects = registry.snapshot()
    assert tuple(item.object_id for item in objects) == (
        "kv:req_0001:L00",
        "prefix:group_a",
    )


def test_registry_preserves_final_kv_and_prefix_metadata() -> None:
    registry = StateRegistry()
    for event in _events():
        registry.apply(event)
    by_id = {item.object_id: item for item in registry.snapshot()}

    prefix = by_id["prefix:group_a"]
    assert prefix.object_type == "prefix_block"
    assert prefix.scope == "session"
    assert prefix.bytes == 524_288
    assert prefix.current_tier == "hbm"
    assert prefix.hit_count == 1
    assert prefix.miss_count == 0
    assert prefix.payload_ref is None
    assert prefix.quality_risk == "high"

    kv = by_id["kv:req_0001:L00"]
    assert kv.object_type == "kv_block"
    assert kv.scope == "request"
    assert kv.bytes == 1_048_576
    assert kv.current_tier == "hbm"
    assert kv.hit_count == 0
    assert kv.miss_count == 1
    assert kv.current_rank == 0
    assert kv.payload_ref is None


def test_registry_snapshot_returns_copies() -> None:
    registry = StateRegistry()
    for event in _events():
        registry.apply(event)

    first = registry.snapshot()[0]
    first.hit_count = 999

    assert registry.snapshot()[0].hit_count == 0


def test_registry_does_not_infer_current_tier_from_source_when_target_is_unknown() -> None:
    event = next(event for event in _events() if event.object_id is not None)
    event = replace(
        event,
        event_id="p8:unknown_target",
        source_event_id="unknown_target",
        object_id="kv:unknown_target",
        source_tier="hbm",
        target_tier=None,
    )
    registry = StateRegistry()

    registry.apply(event)

    assert registry.snapshot()[0].current_tier == "unknown"
