from pathlib import Path

import yaml

from tools.observability_profile.cli import run_observability_profile


def test_run_observability_profile_writes_all_outputs(tmp_path: Path):
    run_dir = run_observability_profile(
        output_base=tmp_path,
        run_id="obs_2026_0703_atlas800t_a2_001",
        server_id="atlas800t-a2-node-001",
        operator="codex",
        probes=[
            {
                "tool": "npu_smi_probe",
                "available": True,
                "permission_status": "ok",
                "command": "npu-smi info",
                "exit_code": 0,
                "start_time": "2026-07-03T00:00:00Z",
                "end_time": "2026-07-03T00:00:01Z",
                "runtime_ms": 1000,
                "run_as_user": "501",
                "inside_container": False,
                "container_privileged": False,
                "output_excerpt": "OK",
                "artifact_path": None,
                "maps_to_fields": ["npu_hbm_profile.hbm_free_bytes"],
                "blocked_reason": {"category": None, "detail": None},
            }
        ],
    )
    assert (run_dir / "manifest.yaml").exists()
    assert (run_dir / "server_observability_profile.md").exists()
    assert (run_dir / "field_availability.yaml").exists()
    assert (run_dir / "join_key_readiness.yaml").exists()
    assert (run_dir / "p0_acceptance_fields.yaml").exists()
    assert (run_dir / "probe_results" / "npu_smi_probe.md").exists()

    field_data = yaml.safe_load((run_dir / "field_availability.yaml").read_text())
    assert "fields" in field_data
    p0_data = yaml.safe_load((run_dir / "p0_acceptance_fields.yaml").read_text())
    assert "p0_acceptance_fields" in p0_data


def test_run_observability_profile_uses_run_id_in_directory(tmp_path: Path):
    first = run_observability_profile(
        output_base=tmp_path,
        run_id="obs_2026_0703_atlas800t_a2_001",
        server_id="atlas800t-a2-node-001",
        operator="codex",
        probes=[],
    )
    second = run_observability_profile(
        output_base=tmp_path,
        run_id="obs_2026_0703_atlas800t_a2_002",
        server_id="atlas800t-a2-node-001",
        operator="codex",
        probes=[],
    )

    assert first != second
    assert first.exists()
    assert second.exists()
    assert "obs_2026_0703_atlas800t_a2_001" in first.name
    assert "obs_2026_0703_atlas800t_a2_002" in second.name


def test_run_observability_profile_applies_manifest_evidence(tmp_path: Path):
    run_dir = run_observability_profile(
        output_base=tmp_path,
        run_id="obs_2026_0703_atlas800t_a2_001",
        server_id="atlas800t-a2-node-001",
        operator="codex",
        probes=[],
    )

    field_data = yaml.safe_load((run_dir / "field_availability.yaml").read_text())
    by_key = {f"{field['profile']}.{field['name']}": field for field in field_data["fields"]}

    availability = by_key["server_observability_profile.os_name"]["availability"]
    assert availability["status"] == "measurable"
    assert availability["evidence_probe"] == "manifest"
    assert availability["evidence_artifact"] == "manifest.yaml"
