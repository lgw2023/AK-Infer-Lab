from importlib import import_module
from pathlib import Path
import subprocess

import pytest


def _minimal_spec(**overrides):
    record = {
        "schema_name": "ak_target_tag_source_probe",
        "schema_version": "0.1.0",
        "probe_id": "unit_source_probe",
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
                "expected_commit": "0" * 40,
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
                        "path": "src/feature.py",
                        "contains": "class Feature",
                    }
                ],
                "instrumentation_evidence": [],
                "documentation_evidence": [],
            }
        ],
    }
    record.update(overrides)
    return record


def _run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _init_tagged_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repos" / "runtime"
    (repo / "src").mkdir(parents=True)
    (repo / "docs").mkdir()
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.name", "Source Probe Test")
    _run_git(repo, "config", "user.email", "source-probe@example.invalid")
    (repo / "src" / "feature.py").write_text(
        "class Feature:\n    pass\nINSTRUMENTATION = True\n",
        encoding="utf-8",
    )
    (repo / "docs" / "feature.md").write_text(
        "# Feature documentation\n",
        encoding="utf-8",
    )
    _run_git(repo, "add", "src/feature.py", "docs/feature.md")
    _run_git(repo, "commit", "-q", "-m", "add feature")
    _run_git(repo, "tag", "v1.0.0")
    return repo, _run_git(repo, "rev-parse", "HEAD")


def _status_spec(commit: str):
    record = _minimal_spec()
    record["targets"][0]["expected_commit"] = commit
    record["capabilities"] = [
        {
            "capability_id": "available",
            "runtime_scope": ["runtime"],
            "source_evidence": [
                {
                    "evidence_id": "available_source",
                    "target_id": "runtime",
                    "path": "src/feature.py",
                    "contains": "class Feature",
                }
            ],
            "instrumentation_evidence": [],
            "documentation_evidence": [],
        },
        {
            "capability_id": "instrumented",
            "runtime_scope": ["runtime"],
            "source_evidence": [
                {
                    "evidence_id": "instrumented_source",
                    "target_id": "runtime",
                    "path": "src/feature.py",
                    "contains": "class Feature",
                }
            ],
            "instrumentation_evidence": [
                {
                    "evidence_id": "instrumented_signal",
                    "target_id": "runtime",
                    "path": "src/feature.py",
                    "contains": "INSTRUMENTATION = True",
                }
            ],
            "documentation_evidence": [],
        },
        {
            "capability_id": "documented",
            "runtime_scope": ["runtime"],
            "source_evidence": [
                {
                    "evidence_id": "documented_missing_source",
                    "target_id": "runtime",
                    "path": "src/feature.py",
                    "contains": "class MissingImplementation",
                }
            ],
            "instrumentation_evidence": [],
            "documentation_evidence": [
                {
                    "evidence_id": "documented_doc",
                    "target_id": "runtime",
                    "path": "docs/feature.md",
                    "contains": "Feature documentation",
                }
            ],
        },
        {
            "capability_id": "unsupported",
            "runtime_scope": ["runtime"],
            "source_evidence": [
                {
                    "evidence_id": "unsupported_missing_source",
                    "target_id": "runtime",
                    "path": "src/feature.py",
                    "contains": "class Unsupported",
                }
            ],
            "instrumentation_evidence": [],
            "documentation_evidence": [
                {
                    "evidence_id": "unsupported_missing_doc",
                    "target_id": "runtime",
                    "path": "docs/feature.md",
                    "contains": "Unsupported documentation",
                }
            ],
        },
    ]
    return record


def test_parse_probe_spec_returns_immutable_contracts() -> None:
    models = import_module("tools.ak_state_runtime.capabilities.models")

    spec = models.parse_probe_spec(_minimal_spec())

    assert spec.probe_id == "unit_source_probe"
    assert spec.claim_ceiling == "instrumented"
    assert spec.targets[0].expected_commit == "0" * 40
    assert spec.capabilities[0].source_evidence[0].contains == "class Feature"
    with pytest.raises(Exception):
        spec.targets[0].tag = "v2.0.0"


def test_parse_probe_spec_requires_exact_pinned_commit() -> None:
    models = import_module("tools.ak_state_runtime.capabilities.models")
    record = _minimal_spec()
    del record["targets"][0]["expected_commit"]

    with pytest.raises(models.ProbeSpecError, match="expected_commit"):
        models.parse_probe_spec(record)


def test_source_probe_claim_ceiling_cannot_be_selected_workload() -> None:
    models = import_module("tools.ak_state_runtime.capabilities.models")

    with pytest.raises(models.ProbeSpecError, match="claim_ceiling"):
        models.parse_probe_spec(
            _minimal_spec(claim_ceiling="validated_for_selected_workload")
        )


def test_source_probe_rejects_selected_workload_validation() -> None:
    models = import_module("tools.ak_state_runtime.capabilities.models")
    selected = {
        "model_id": "unit-model",
        "validated": True,
        "gate": "closed",
    }

    with pytest.raises(models.ProbeSpecError, match="selected_workload.validated"):
        models.parse_probe_spec(_minimal_spec(selected_workload=selected))


def test_source_evidence_must_reference_a_declared_target() -> None:
    models = import_module("tools.ak_state_runtime.capabilities.models")
    record = _minimal_spec()
    record["capabilities"][0]["source_evidence"][0]["target_id"] = "missing"

    with pytest.raises(models.ProbeSpecError, match="unknown target_id"):
        models.parse_probe_spec(record)


def test_probe_derives_statuses_from_pinned_git_blobs(tmp_path: Path) -> None:
    models = import_module("tools.ak_state_runtime.capabilities.models")
    source = import_module("tools.ak_state_runtime.capabilities.source")
    repo, commit = _init_tagged_repo(tmp_path)
    before_status = _run_git(repo, "status", "--porcelain")

    result = source.probe_source_capabilities(
        models.parse_probe_spec(_status_spec(commit)),
        tmp_path,
    )

    assert [item.status for item in result.capabilities] == [
        "available_uninstrumented",
        "instrumented",
        "documented_unverified",
        "unsupported",
    ]
    available = result.capabilities[0].source_evidence[0]
    assert available.matched is True
    assert available.matched_lines == (1,)
    assert len(available.blob_oid or "") == 40
    assert result.targets[0].observed_commit == commit
    assert result.targets[0].ref_verified is True
    assert _run_git(repo, "status", "--porcelain") == before_status
    assert _run_git(repo, "rev-parse", "HEAD") == commit


def test_probe_rejects_tag_commit_drift_before_inspection(tmp_path: Path) -> None:
    models = import_module("tools.ak_state_runtime.capabilities.models")
    source = import_module("tools.ak_state_runtime.capabilities.source")
    _repo, commit = _init_tagged_repo(tmp_path)
    record = _status_spec(commit)
    record["targets"][0]["expected_commit"] = "f" * 40

    with pytest.raises(source.SourceProbeError, match="expected commit"):
        source.probe_source_capabilities(
            models.parse_probe_spec(record),
            tmp_path,
        )
