import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest
import yaml

from tools.ak_state_runtime.adapters.base import AdapterError
from tools.ak_state_runtime.adapters.vllm_ascend import VllmAscendAdapter
from tools.ak_state_runtime.replay import replay, validate_replay_result


BASELINE_CONTRACT = Path(
    "benchmarks/deepseek_v4_flash/p8/p8_baseline_contract.yaml"
)
OFFICIAL_MTP_BASELINE_CONTRACT = Path(
    "benchmarks/deepseek_v4_flash/p8/p8_official_mtp_baseline_contract.yaml"
)
MODEL_ID = "deepseek-ai/DeepSeek-V4-Flash-w8a8-mtp"


def _record(
    source_event_id: str,
    timestamp_ns: int,
    *,
    event_type: str,
    phase: str,
    action: str,
    evidence_source: str,
    object_id: str | None = None,
    object_type: str | None = None,
    source_tier: str | None = None,
    target_tier: str | None = None,
    bytes_value: int | None = None,
    latency_ms: float | None = None,
    reason: str = "bounded_server_observation",
) -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "source_event_id": source_event_id,
        "timestamp_ns": timestamp_ns,
        "trace_id": "trace_p8_vllm_ascend_0001",
        "request_id": "req_p8_0001",
        "session_id": "session_p8_0001",
        "phase": phase,
        "event_type": event_type,
        "action": action,
        "object_id": object_id,
        "object_type": object_type,
        "rank_id": None,
        "source_tier": source_tier,
        "target_tier": target_tier,
        "bytes": bytes_value,
        "latency_ms": latency_ms,
        "evidence_source": evidence_source,
        "reason": reason,
    }


def _records() -> list[dict[str, object]]:
    return [
        _record(
            "request_start",
            1_000_000_000,
            event_type="request_stage",
            phase="enqueue",
            action="request_start",
            evidence_source="runtime_event",
        ),
        _record(
            "prefix_cache_hit_proxy",
            1_000_100_000,
            event_type="state_lifecycle",
            phase="prefill",
            action="hit",
            evidence_source="server_stats",
            object_id="prefix_proxy:req_p8_0001",
            object_type="prefix_block",
            source_tier="hbm",
            target_tier="hbm",
            reason="prefix_cache_counter_delta;object_bytes_unavailable",
        ),
        _record(
            "kv_transfer_proxy",
            1_000_200_000,
            event_type="transfer",
            phase="kv_restore",
            action="h2d_copy",
            evidence_source="runtime_event",
            object_id="kv_proxy:req_p8_0001",
            object_type="kv_block",
            source_tier="pinned_dram",
            target_tier="hbm",
            reason="native_transfer_event;bytes_unavailable",
        ),
        _record(
            "first_token",
            1_005_846_203,
            event_type="request_stage",
            phase="decode",
            action="first_token",
            evidence_source="runtime_event",
            latency_ms=5_846.203,
        ),
        _record(
            "request_end",
            1_034_868_222,
            event_type="request_stage",
            phase="decode",
            action="request_end",
            evidence_source="runtime_event",
            latency_ms=34_868.222,
        ),
    ]


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> Path:
    path.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def _adapter(contract: Path = BASELINE_CONTRACT) -> VllmAscendAdapter:
    return VllmAscendAdapter(
        baseline_contract=contract,
        model_id=MODEL_ID,
    )


def test_adapter_rejects_a_nonfrozen_or_unvalidated_runtime_cell(tmp_path: Path) -> None:
    contract = yaml.safe_load(BASELINE_CONTRACT.read_text(encoding="utf-8"))
    contract["contract_status"] = "pending"
    contract["selected_workload"]["validated"] = False
    path = tmp_path / "pending.yaml"
    path.write_text(yaml.safe_dump(contract), encoding="utf-8")

    with pytest.raises(AdapterError, match="frozen_degraded baseline contract"):
        _adapter(path)


def test_adapter_accepts_the_frozen_official_mtp_observe_only_cell(
    tmp_path: Path,
) -> None:
    source = _write_jsonl(tmp_path / "observations.jsonl", _records())

    adapted = _adapter(OFFICIAL_MTP_BASELINE_CONTRACT).read(source)

    assert adapted.source_record_count == 5
    assert adapted.emitted_event_count == 5
    assert {event.model_id for event in adapted.events} == {MODEL_ID}
    assert {event.runtime for event in adapted.events} == {"vllm_ascend"}


def test_adapter_maps_bounded_runtime_observations_without_runtime_imports(
    tmp_path: Path,
) -> None:
    source = _write_jsonl(tmp_path / "observations.jsonl", _records())

    adapted = _adapter().read(source)

    assert adapted.source_record_count == 5
    assert adapted.emitted_event_count == 5
    assert adapted.skipped_record_count == 0
    assert adapted.warnings == ()
    assert {event.model_id for event in adapted.events} == {MODEL_ID}
    assert {event.runtime for event in adapted.events} == {"vllm_ascend"}
    assert {event.artifact_path for event in adapted.events} == {source.as_posix()}
    assert all(
        event.event_id == f"p8:vllm_ascend:{event.source_event_id}"
        for event in adapted.events
    )


def test_adapter_replay_is_strictly_observe_only(tmp_path: Path) -> None:
    source = _write_jsonl(tmp_path / "observations.jsonl", _records())

    result = replay(_adapter().read(source))

    assert validate_replay_result(result) == ()
    assert len(result.state_objects) == 2
    assert len(result.placement_decisions) == 2
    for decision in result.placement_decisions:
        assert decision.execution_mode == "observe_only"
        assert decision.action == "no_op"
        assert decision.executed is False
        assert decision.execution_result == "skipped"
    assert all(state_object.payload_ref is None for state_object in result.state_objects)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda record: record.__setitem__("payload", [1, 2, 3]), "forbidden fields: payload"),
        (
            lambda record: record.__setitem__("event_type", "policy_decision"),
            "event_type must be one of",
        ),
        (lambda record: record.pop("trace_id"), "missing required fields: trace_id"),
        (
            lambda record: record.__setitem__("schema_version", "9.9.9"),
            "schema_version must be 0.1.0",
        ),
    ],
)
def test_adapter_rejects_payload_mutation_and_invalid_records(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    records = _records()
    mutation(records[0])
    source = _write_jsonl(tmp_path / "invalid.jsonl", records)

    with pytest.raises(AdapterError, match=message):
        _adapter().read(source)


def test_transfer_with_unknown_bytes_requires_an_explicit_reason(tmp_path: Path) -> None:
    records = _records()
    records[2]["reason"] = ""
    source = _write_jsonl(tmp_path / "invalid_transfer.jsonl", records)

    with pytest.raises(AdapterError, match="null bytes requires a non-empty reason"):
        _adapter().read(source)


def test_adapter_rejects_duplicate_source_event_ids(tmp_path: Path) -> None:
    records = _records()
    records[1]["source_event_id"] = records[0]["source_event_id"]
    source = _write_jsonl(tmp_path / "duplicate.jsonl", records)

    with pytest.raises(AdapterError, match="duplicate source_event_id: request_start"):
        _adapter().read(source)


def test_adapter_rejects_empty_sources_and_request_payload_metadata(
    tmp_path: Path,
) -> None:
    empty = _write_jsonl(tmp_path / "empty.jsonl", [])
    with pytest.raises(AdapterError, match="at least one record"):
        _adapter().read(empty)

    records = _records()
    records[0]["bytes"] = 4096
    source = _write_jsonl(tmp_path / "request_bytes.jsonl", records)
    with pytest.raises(AdapterError, match="request_stage bytes must be null"):
        _adapter().read(source)


def test_normalized_records_validate_against_the_existing_state_event_schema(
    tmp_path: Path,
) -> None:
    source = _write_jsonl(tmp_path / "observations.jsonl", _records())

    result = replay(_adapter().read(source))

    assert all(record["schema_version"] == "0.2.0" for record in map(asdict, result.events))


def test_cli_builds_a_deterministic_observe_only_candidate_bundle(
    tmp_path: Path,
) -> None:
    source = _write_jsonl(tmp_path / "observations.jsonl", _records())
    first = tmp_path / "first"
    second = tmp_path / "second"
    common = [
        sys.executable,
        "-m",
        "tools.ak_state_runtime.cli",
        "build-vllm-ascend-observe-bundle",
        "--source",
        str(source),
        "--baseline-contract",
        str(BASELINE_CONTRACT),
        "--model-id",
        MODEL_ID,
    ]

    first_run = subprocess.run(
        [*common, "--output", str(first)],
        check=False,
        capture_output=True,
        text=True,
    )
    second_run = subprocess.run(
        [*common, "--output", str(second)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert first_run.returncode == 0, first_run.stderr
    assert second_run.returncode == 0, second_run.stderr
    assert json.loads(first_run.stdout)["trace_validation_errors"] == 0
    for first_file in first.iterdir():
        assert first_file.read_bytes() == (second / first_file.name).read_bytes()

    manifest = yaml.safe_load((first / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["slice_id"] == "p8_vllm_ascend_observe_only_tracer_bullet"
    assert manifest["claim_level"] == "selected_workload_observe_only_candidate"
    assert manifest["provenance_mode"] == "bounded_server_observation"
    assert manifest["server_validated"] is False
    assert manifest["trace_validation_errors"] == 0
