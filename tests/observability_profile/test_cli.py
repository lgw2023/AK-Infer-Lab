import subprocess
import sys
from pathlib import Path

import pytest
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
    assert first == tmp_path / "obs_2026_0703_atlas800t_a2_001"
    assert second == tmp_path / "obs_2026_0703_atlas800t_a2_002"


def test_run_observability_profile_refuses_existing_run_directory(tmp_path: Path):
    run_observability_profile(
        output_base=tmp_path,
        run_id="obs_2026_0703_atlas800t_a2_001",
        server_id="atlas800t-a2-node-001",
        operator="codex",
        probes=[],
    )

    with pytest.raises(FileExistsError):
        run_observability_profile(
            output_base=tmp_path,
            run_id="obs_2026_0703_atlas800t_a2_001",
            server_id="atlas800t-a2-node-001",
            operator="codex",
            probes=[],
        )


def test_collect_help_exposes_microbench_options():
    result = subprocess.run(
        [sys.executable, "-m", "tools.observability_profile.cli", "collect", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--include-microbench" in result.stdout
    assert "--scratch-dir" in result.stdout
    assert "--copy-sizes" in result.stdout
    assert "--fio-qdepth" in result.stdout
    assert "--microbench-duration" in result.stdout


def test_run_observability_profile_writes_microbench_blocked_artifact_without_scratch(tmp_path: Path):
    run_dir = run_observability_profile(
        output_base=tmp_path,
        run_id="obs_2026_0703_atlas800t_a2_001",
        server_id="atlas800t-a2-node-001",
        operator="codex",
        probes=[],
        include_microbench=True,
    )

    artifact = run_dir / "microbench" / "ssd_fio.csv"
    assert artifact.exists()
    assert "scratch_missing" in artifact.read_text()

    field_data = yaml.safe_load((run_dir / "field_availability.yaml").read_text())
    by_key = {f"{field['profile']}.{field['name']}": field for field in field_data["fields"]}
    ssd_iops = by_key["microbench_profile.ssd_iops"]["availability"]
    h2d_latency = by_key["microbench_profile.h2d_latency_us"]["availability"]

    assert ssd_iops["status"] == "blocked"
    assert ssd_iops["blocked_reason"]["category"] == "scratch_missing"
    assert h2d_latency["blocked_reason"]["category"] != "scratch_missing"


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
