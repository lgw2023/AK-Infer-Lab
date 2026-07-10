from pathlib import Path

from tools.ak_state_runtime.adapters.p1_fixture import P1FixtureAdapter
from tools.ak_state_runtime.policies.observe_only import ObserveOnlyPolicy


P1_FIXTURE = Path(
    "工作记录与进度笔记本/p1_inference_contracts/fixtures/minimal_runtime_trace.jsonl"
)


def _events():
    return P1FixtureAdapter(
        model_id="p1_fixture_model",
        runtime_label="vllm_ascend",
    ).read(P1_FIXTURE).events


def test_policy_emits_no_decision_for_request_only_events() -> None:
    policy = ObserveOnlyPolicy()
    request_events = [event for event in _events() if event.object_id is None]

    assert len(request_events) == 3
    assert [policy.decide(event) for event in request_events] == [None, None, None]


def test_policy_emits_deterministic_unexecuted_no_op_for_object_events() -> None:
    policy = ObserveOnlyPolicy()
    object_events = [event for event in _events() if event.object_id is not None]

    first_pass = [policy.decide(event) for event in object_events]
    second_pass = [policy.decide(event) for event in object_events]

    assert len(first_pass) == 5
    assert first_pass == second_pass
    assert all(decision is not None for decision in first_pass)
    assert all(decision.action == "no_op" for decision in first_pass if decision)
    assert all(decision.execution_mode == "observe_only" for decision in first_pass if decision)
    assert all(decision.executed is False for decision in first_pass if decision)
    assert all(decision.execution_result == "skipped" for decision in first_pass if decision)
    assert [decision.decision_id for decision in first_pass if decision] == [
        f"decision:{event.source_event_id}" for event in object_events
    ]


def test_no_op_decision_does_not_restate_an_observed_transfer_as_a_move() -> None:
    policy = ObserveOnlyPolicy()
    restore_event = next(
        event for event in _events() if event.source_event_id == "evt_kv_l00_restore_done"
    )

    decision = policy.decide(restore_event)

    assert decision is not None
    assert decision.action == "no_op"
    assert decision.source_tier == "hbm"
    assert decision.target_tier == "hbm"
