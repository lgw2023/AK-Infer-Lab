from importlib import import_module
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from tools.ak_state_runtime.capabilities.models import (
    CapabilityResult,
    EvidenceResult,
    SourceProbeResult,
    TargetResult,
)


TARGET_SPEC = Path(
    "benchmarks/deepseek_v4_flash/p8/source_capability_probe.yaml"
)
COMMITTED_MATRIX = Path(
    "benchmarks/deepseek_v4_flash/p8/runtime_capability_matrix.yaml"
)
COMMITTED_REPORT = Path(
    "benchmarks/deepseek_v4_flash/p8/p8_0_source_capability_probe_report.md"
)
V0221_PROBE_DIR = Path(
    "benchmarks/deepseek_v4_flash/p8/source_probes/"
    "vllm-v0.22.1__vllm-ascend-v0.22.1rc1"
)
V0221_SPEC = V0221_PROBE_DIR / "source_capability_probe.yaml"
V0221_MATRIX = V0221_PROBE_DIR / "runtime_capability_matrix.yaml"
V0221_REPORT = V0221_PROBE_DIR / "source_capability_probe_report.md"


def _result() -> SourceProbeResult:
    evidence = EvidenceResult(
        evidence_id="feature_source",
        evidence_group="source",
        target_id="runtime",
        path="src/feature.py",
        contains="class Feature",
        matched=True,
        blob_oid="1" * 40,
        matched_lines=(7,),
        error=None,
    )
    return SourceProbeResult(
        probe_id="unit_source_probe",
        probe_date="2026-07-10",
        claim_ceiling="instrumented",
        selected_workload_model_id="unit-model",
        selected_workload_validated=False,
        selected_workload_gate="waiting_selected_workload_runtime_gate",
        real_vllm_ascend_adapter_gate=(
            "waiting_selected_workload_runtime_gate"
        ),
        targets=(
            TargetResult(
                target_id="runtime",
                repo_path="repos/runtime",
                tag="v1.0.0",
                expected_commit="0" * 40,
                observed_commit="0" * 40,
                ref_verified=True,
            ),
        ),
        capabilities=(
            CapabilityResult(
                capability_id="feature",
                runtime_scope=("runtime",),
                status="available_uninstrumented",
                source_evidence=(evidence,),
                instrumentation_evidence=(),
                documentation_evidence=(),
                selected_workload_validated=False,
                runtime_gate="waiting_selected_workload_runtime_gate",
            ),
        ),
    )


def _run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _init_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repos" / "runtime"
    repo.mkdir(parents=True)
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.name", "Source Probe Test")
    _run_git(repo, "config", "user.email", "source-probe@example.invalid")
    (repo / "feature.py").write_text("class Feature:\n    pass\n", encoding="utf-8")
    _run_git(repo, "add", "feature.py")
    _run_git(repo, "commit", "-q", "-m", "add feature")
    _run_git(repo, "tag", "v1.0.0")
    return repo, _run_git(repo, "rev-parse", "HEAD")


def _cli_spec(commit: str) -> dict:
    return {
        "schema_name": "ak_target_tag_source_probe",
        "schema_version": "0.1.0",
        "probe_id": "cli_source_probe",
        "probe_date": "2026-07-10",
        "claim_ceiling": "instrumented",
        "selected_workload": {
            "model_id": "unit-model",
            "validated": False,
            "gate": "waiting_selected_workload_runtime_gate",
        },
        "real_vllm_ascend_adapter_gate": (
            "waiting_selected_workload_runtime_gate"
        ),
        "targets": [
            {
                "target_id": "runtime",
                "repo_path": "repos/runtime",
                "tag": "v1.0.0",
                "expected_commit": commit,
            }
        ],
        "capabilities": [
            {
                "capability_id": "feature",
                "runtime_scope": ["runtime"],
                "source_evidence": [
                    {
                        "evidence_id": "feature_source",
                        "target_id": "runtime",
                        "path": "feature.py",
                        "contains": "class Feature",
                    }
                ],
                "instrumentation_evidence": [],
                "documentation_evidence": [],
            }
        ],
    }


def test_source_probe_outputs_are_deterministic_and_bounded() -> None:
    report = import_module("tools.ak_state_runtime.capabilities.report")
    result = _result()

    assert report.matrix_bytes(result) == report.matrix_bytes(result)
    assert report.report_bytes(result) == report.report_bytes(result)
    matrix = yaml.safe_load(report.matrix_bytes(result))
    assert matrix["schema_name"] == "ak_runtime_capability_matrix"
    assert matrix["claim_ceiling"] == "instrumented"
    assert matrix["selected_workload_validated"] is False
    assert matrix["real_vllm_ascend_adapter_gate"] == (
        "waiting_selected_workload_runtime_gate"
    )
    assert matrix["status_counts"]["available_uninstrumented"] == 1
    text = report.report_bytes(result).decode("utf-8")
    assert "v1.0.0" in text
    assert "available_uninstrumented" in text
    assert "does not validate the selected workload" in text


def test_output_writer_refuses_to_overwrite_either_artifact(tmp_path: Path) -> None:
    report = import_module("tools.ak_state_runtime.capabilities.report")
    matrix = tmp_path / "matrix.yaml"
    markdown = tmp_path / "report.md"
    matrix.write_text("preserve\n", encoding="utf-8")

    with pytest.raises(report.CapabilityReportError, match="already exists"):
        report.write_source_probe_outputs(_result(), matrix, markdown)

    assert matrix.read_text(encoding="utf-8") == "preserve\n"
    assert not markdown.exists()


def test_report_refuses_status_above_source_claim_ceiling() -> None:
    report = import_module("tools.ak_state_runtime.capabilities.report")
    result = _result()
    elevated = replace(
        result.capabilities[0],
        status="validated_for_selected_workload",
        selected_workload_validated=True,
    )
    unsafe = replace(
        result,
        capabilities=(elevated,),
        selected_workload_validated=True,
    )

    with pytest.raises(report.CapabilityReportError, match="claim ceiling"):
        report.matrix_bytes(unsafe)


def test_report_refuses_a_capability_that_bypasses_runtime_gate() -> None:
    report = import_module("tools.ak_state_runtime.capabilities.report")
    result = _result()
    bypassed = replace(result.capabilities[0], runtime_gate="closed")

    with pytest.raises(report.CapabilityReportError, match="runtime gate"):
        report.report_bytes(replace(result, capabilities=(bypassed,)))


def test_cli_does_not_publish_on_tag_commit_drift(tmp_path: Path) -> None:
    _repo, commit = _init_repo(tmp_path)
    spec_path = tmp_path / "probe.yaml"
    record = _cli_spec(commit)
    record["targets"][0]["expected_commit"] = "f" * 40
    spec_path.write_text(
        yaml.safe_dump(record, sort_keys=False),
        encoding="utf-8",
    )
    matrix = tmp_path / "matrix.yaml"
    markdown = tmp_path / "report.md"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.ak_state_runtime.cli",
            "probe-source-capabilities",
            "--spec",
            str(spec_path),
            "--repo-root",
            str(tmp_path),
            "--matrix-output",
            str(matrix),
            "--report-output",
            str(markdown),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "expected commit" in completed.stderr
    assert not matrix.exists()
    assert not markdown.exists()


def test_cli_publishes_deterministic_source_probe_outputs(tmp_path: Path) -> None:
    _repo, commit = _init_repo(tmp_path)
    spec_path = tmp_path / "probe.yaml"
    spec_path.write_text(
        yaml.safe_dump(_cli_spec(commit), sort_keys=False),
        encoding="utf-8",
    )
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    outputs = []
    for output_dir in (first_dir, second_dir):
        matrix = output_dir / "matrix.yaml"
        markdown = output_dir / "report.md"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.ak_state_runtime.cli",
                "probe-source-capabilities",
                "--spec",
                str(spec_path),
                "--repo-root",
                str(tmp_path),
                "--matrix-output",
                str(matrix),
                "--report-output",
                str(markdown),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        summary = json.loads(completed.stdout)
        assert summary["claim_ceiling"] == "instrumented"
        assert summary["selected_workload_validated"] is False
        outputs.append((matrix.read_bytes(), markdown.read_bytes()))

    assert outputs[0] == outputs[1]


def test_committed_matrix_is_source_only_and_adapter_remains_gated() -> None:
    spec = yaml.safe_load(TARGET_SPEC.read_text(encoding="utf-8"))
    matrix = yaml.safe_load(COMMITTED_MATRIX.read_text(encoding="utf-8"))

    assert matrix["claim_ceiling"] == "instrumented"
    assert matrix["selected_workload_validated"] is False
    assert matrix["real_vllm_ascend_adapter_gate"] == (
        "waiting_selected_workload_runtime_gate"
    )
    assert matrix["capability_count"] == 13
    assert matrix["status_counts"] == {
        "unsupported": 0,
        "documented_unverified": 0,
        "available_uninstrumented": 7,
        "instrumented": 6,
        "validated_for_selected_workload": 0,
    }
    assert [target["observed_commit"] for target in matrix["targets"]] == [
        "bc150f50299199599673614f80d12a196f377655",
        "367b8e62da799870a7476ce34f5f7658589a8aad",
    ]
    assert all(target["ref_verified"] is True for target in matrix["targets"])
    assert all(
        row["status"] != "validated_for_selected_workload"
        and row["selected_workload_validated"] is False
        for row in matrix["capabilities"]
    )
    assert all(
        evidence["matched"] is True and evidence["error"] is None
        for row in matrix["capabilities"]
        for group in (
            "source_evidence",
            "instrumentation_evidence",
            "documentation_evidence",
        )
        for evidence in row[group]
    )
    assert [row["capability_id"] for row in matrix["capabilities"]] == [
        row["capability_id"] for row in spec["capabilities"]
    ]
    report = COMMITTED_REPORT.read_text(encoding="utf-8")
    assert "does not validate the selected workload" in report
    assert "does not authorize a real VllmAscendAdapter" in report


def test_v0221_probe_is_versioned_without_replacing_v0202_history() -> None:
    historical_spec = yaml.safe_load(TARGET_SPEC.read_text(encoding="utf-8"))
    spec = yaml.safe_load(V0221_SPEC.read_text(encoding="utf-8"))
    matrix = yaml.safe_load(V0221_MATRIX.read_text(encoding="utf-8"))

    assert [target["tag"] for target in historical_spec["targets"]] == [
        "v0.20.2",
        "v0.20.2rc1",
    ]
    assert [target["tag"] for target in spec["targets"]] == [
        "v0.22.1",
        "v0.22.1rc1",
    ]
    assert [target["observed_commit"] for target in matrix["targets"]] == [
        "0decac0d96c42b49572498019f0a0e3600f50398",
        "5f6faa0cb8830f667266f3b8121cd1383606f2a1",
    ]
    assert all(target["ref_verified"] is True for target in matrix["targets"])
    assert matrix["claim_ceiling"] == "instrumented"
    assert matrix["selected_workload_validated"] is False
    assert matrix["real_vllm_ascend_adapter_gate"] == (
        "waiting_selected_workload_runtime_gate"
    )
    assert matrix["capability_count"] == 13
    assert matrix["status_counts"] == {
        "unsupported": 0,
        "documented_unverified": 0,
        "available_uninstrumented": 7,
        "instrumented": 6,
        "validated_for_selected_workload": 0,
    }
    assert all(
        evidence["matched"] is True and evidence["error"] is None
        for row in matrix["capabilities"]
        for group in (
            "source_evidence",
            "instrumentation_evidence",
            "documentation_evidence",
        )
        for evidence in row[group]
    )
    report = V0221_REPORT.read_text(encoding="utf-8")
    assert "v0.22.1" in report
    assert "v0.22.1rc1" in report
    assert "does not validate the selected workload" in report
    assert "does not authorize a real VllmAscendAdapter" in report
