import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from tools.ak_state_runtime.adapters.p1_fixture import P1FixtureAdapter
from tools.ak_state_runtime.bundle import BundleError, write_bundle
from tools.ak_state_runtime.replay import replay, validate_replay_result


P1_FIXTURE = Path(
    "工作记录与进度笔记本/p1_inference_contracts/fixtures/minimal_runtime_trace.jsonl"
)
COMMITTED_EXEMPLAR = Path(
    "benchmarks/deepseek_v4_flash/p8/offline_tracer_bullet"
)


def _adapted():
    return P1FixtureAdapter(
        model_id="p1_fixture_model",
        runtime_label="vllm_ascend",
    ).read(P1_FIXTURE)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_replay_sorts_events_and_produces_valid_joins() -> None:
    adapted = _adapted()
    reversed_adapted = replace(adapted, events=tuple(reversed(adapted.events)))

    result = replay(reversed_adapted)

    assert [event.timestamp_ns for event in result.events] == sorted(
        event.timestamp_ns for event in result.events
    )
    assert len(result.state_objects) == 2
    assert len(result.placement_decisions) == 5
    assert validate_replay_result(result) == ()


def test_bundle_is_byte_identical_across_two_output_directories(tmp_path: Path) -> None:
    result = replay(_adapted())
    first = tmp_path / "first"
    second = tmp_path / "second"

    write_bundle(result, first, source_artifact=P1_FIXTURE)
    write_bundle(result, second, source_artifact=P1_FIXTURE)

    filenames = {
        "manifest.yaml",
        "state_objects.jsonl",
        "state_events.jsonl",
        "placement_decisions.jsonl",
        "validation_report.json",
    }
    assert {path.name for path in first.iterdir()} == filenames
    for filename in filenames:
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_bundle_manifest_contains_real_digests_and_offline_claim_boundary(
    tmp_path: Path,
) -> None:
    output = tmp_path / "bundle"
    write_bundle(replay(_adapted()), output, source_artifact=P1_FIXTURE)

    manifest = yaml.safe_load((output / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "0.2.0"
    assert manifest["provenance_mode"] == "offline_fixture"
    assert manifest["server_validated"] is False
    assert manifest["claim_level"] == "toolchain_only"
    assert manifest["source_record_count"] == 8
    assert manifest["emitted_event_count"] == 8
    assert manifest["skipped_record_count"] == 0
    assert manifest["state_object_count"] == 2
    assert manifest["placement_decision_count"] == 5
    assert manifest["trace_validation_errors"] == 0
    assert manifest["source_sha256"] == _sha256(P1_FIXTURE)
    for filename, digest in manifest["artifact_sha256"].items():
        assert digest == _sha256(output / filename)

    report = json.loads((output / "validation_report.json").read_text(encoding="utf-8"))
    assert report["trace_validation_errors"] == 0
    assert report["errors"] == []
    assert len(report["warnings"]) == 2


def test_invalid_cross_reference_is_rejected_before_output(tmp_path: Path) -> None:
    valid = replay(_adapted())
    bad_decision = replace(valid.placement_decisions[0], object_id="missing:object")
    invalid = replace(
        valid,
        placement_decisions=(bad_decision, *valid.placement_decisions[1:]),
    )
    output = tmp_path / "invalid"

    errors = validate_replay_result(invalid)
    assert (
        "decision decision:evt_op_l00_prefill_attention_start references missing object missing:object"
        in errors
    )
    with pytest.raises(BundleError, match="references missing object"):
        write_bundle(invalid, output, source_artifact=P1_FIXTURE)
    assert not output.exists()


def test_schema_invalid_replay_result_is_rejected_before_output(tmp_path: Path) -> None:
    valid = replay(_adapted())
    bad_decision = replace(
        valid.placement_decisions[0],
        execution_mode="secret_runtime_mode",
    )
    invalid = replace(
        valid,
        placement_decisions=(bad_decision, *valid.placement_decisions[1:]),
    )
    output = tmp_path / "schema_invalid"

    errors = validate_replay_result(invalid)
    assert len(errors) == 1
    assert "secret_runtime_mode" in errors[0]
    with pytest.raises(BundleError, match="secret_runtime_mode"):
        write_bundle(invalid, output, source_artifact=P1_FIXTURE)
    assert not output.exists()


def test_replay_result_count_invariants_are_checked() -> None:
    valid = replay(_adapted())
    invalid = replace(valid, emitted_event_count=1, source_record_count=99)

    errors = validate_replay_result(invalid)

    assert "emitted_event_count 1 does not match 8 events" in errors
    assert "source_record_count 99 does not equal emitted 1 plus skipped 0" in errors


def test_non_request_event_requires_object_and_matching_decision() -> None:
    valid = replay(_adapted())
    transfer_index = next(
        index for index, event in enumerate(valid.events) if event.event_type == "transfer"
    )
    events = list(valid.events)
    events[transfer_index] = replace(
        events[transfer_index],
        object_id=None,
        object_type=None,
    )
    invalid = replace(valid, events=tuple(events))

    errors = validate_replay_result(invalid)

    assert any("transfer event" in error and "requires object_id" in error for error in errors)
    assert any("has no object-bearing source event" in error for error in errors)


def test_every_object_event_requires_its_deterministic_decision() -> None:
    valid = replay(_adapted())
    missing = valid.placement_decisions[0]
    invalid = replace(valid, placement_decisions=valid.placement_decisions[1:])

    errors = validate_replay_result(invalid)

    assert (
        f"object event p8:evt_op_l00_prefill_attention_start missing decision "
        f"{missing.decision_id}"
    ) in errors


def test_cli_builds_the_same_bundle_twice(tmp_path: Path) -> None:
    first = tmp_path / "cli_first"
    second = tmp_path / "cli_second"
    common = [
        sys.executable,
        "-m",
        "tools.ak_state_runtime.cli",
        "build-offline-bundle",
        "--source",
        str(P1_FIXTURE),
        "--model-id",
        "p1_fixture_model",
        "--runtime-label",
        "vllm_ascend",
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
    assert json.loads(second_run.stdout)["trace_validation_errors"] == 0
    for first_file in first.iterdir():
        assert first_file.read_bytes() == (second / first_file.name).read_bytes()


def test_committed_exemplar_is_cli_regenerable(tmp_path: Path) -> None:
    regenerated = tmp_path / "regenerated"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.ak_state_runtime.cli",
            "build-offline-bundle",
            "--source",
            str(P1_FIXTURE),
            "--output",
            str(regenerated),
            "--model-id",
            "p1_fixture_model",
            "--runtime-label",
            "vllm_ascend",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert {path.name for path in regenerated.iterdir()} == {
        path.name for path in COMMITTED_EXEMPLAR.iterdir()
    }
    for expected in COMMITTED_EXEMPLAR.iterdir():
        assert expected.read_bytes() == (regenerated / expected.name).read_bytes()
