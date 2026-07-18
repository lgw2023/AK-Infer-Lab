from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDITOR = (
    REPO_ROOT
    / "tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py"
)
R3_R1_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r3_r1_simple_cpu_offload.sh"
)
R3_R1_AUDIT = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r3_r1_provenance_gate_audit.yaml"
)


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _accepted_r2_evidence(root: Path) -> tuple[Path, Path, Path]:
    geometry = root / "k1a_r2_geometry_summary.json"
    rendezvous = root / "geometry.rendezvous.complete.json"
    allocator = root / "pinned_allocator_envelope_summary.json"
    _write_json(
        geometry,
        {
            "schema_version": "p8_2_k1a_r2_geometry_summary_v1",
            "stage": "P8.2-K1A-R2",
            "probe_run_id": "accepted-r2-run",
            "geometry_gate_ok": True,
            "rendezvous_gate_ok": True,
            "rank_count": 8,
            "rank_coverage": list(range(8)),
            "block_size_tokens": 128,
            "required_restore_tokens": 16384,
            "required_cpu_blocks": 128,
            "total_bytes_per_block": 3364096,
            "required_capacity_bytes_per_rank": 430604288,
            "required_capacity_bytes_total": 3444834304,
            "unique_tensor_count": 44,
            "allocation_attempted": False,
            "formal_lifecycle_authorized": False,
        },
    )
    _write_json(
        rendezvous,
        {
            "schema_version": "p8_2_k1a_r2_geometry_rendezvous_v1",
            "probe_run_id": "accepted-r2-run",
            "rank_coverage": list(range(8)),
            "world_size": 8,
            "geometry_parity_exact": True,
            "allocation_attempted": False,
        },
    )
    _write_json(
        allocator,
        {
            "schema_version": "p8_2_k1a_r2_allocator_envelope_v1",
            "acl_pinned_host_allocator_gate_ok": True,
            "required_cpu_blocks": 128,
            "highest_eight_rank_clean_blocks": 128,
            "candidate_cpu_bytes_per_rank": 430604288,
            "candidate_cpu_bytes_total": 3444834304,
            "capacity_candidate_ready": True,
            "formal_lifecycle_allowed": False,
            "formal_lifecycle_requires_new_handoff": True,
            "grade": "candidate_ready_p8_2_k1a_r2_allocator_capacity",
        },
    )
    return geometry, rendezvous, allocator


def test_r3_r1_provenance_gate_reads_geometry_and_rendezvous_schemas_separately(
    tmp_path: Path,
) -> None:
    geometry, rendezvous, allocator = _accepted_r2_evidence(tmp_path)
    output = tmp_path / "accepted_r2_capacity_provenance.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(AUDITOR),
            "accepted-capacity-provenance",
            "--geometry-summary",
            str(geometry),
            "--rendezvous-marker",
            str(rendezvous),
            "--allocator-summary",
            str(allocator),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    proof = json.loads(output.read_text(encoding="utf-8"))
    assert proof == {
        "accepted_capacity_bytes_per_rank": 430604288,
        "accepted_capacity_bytes_total": 3444834304,
        "accepted_r2_capacity_provenance_gate": "pass",
        "allocation_attempted": False,
        "block_size_tokens": 128,
        "geometry_parity_exact": True,
        "probe_run_id": "accepted-r2-run",
        "rank_coverage": list(range(8)),
        "required_cpu_blocks": 128,
        "required_restore_tokens": 16384,
        "schema_version": "p8_2_k1a_r3_r1_accepted_capacity_provenance_v1",
        "world_size": 8,
    }


def test_r3_r1_provenance_gate_rejects_cross_run_rendezvous(
    tmp_path: Path,
) -> None:
    geometry, rendezvous, allocator = _accepted_r2_evidence(tmp_path)
    marker = json.loads(rendezvous.read_text(encoding="utf-8"))
    marker["probe_run_id"] = "foreign-run"
    _write_json(rendezvous, marker)
    output = tmp_path / "must_not_exist.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(AUDITOR),
            "accepted-capacity-provenance",
            "--geometry-summary",
            str(geometry),
            "--rendezvous-marker",
            str(rendezvous),
            "--allocator-summary",
            str(allocator),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "geometry and rendezvous probe_run_id mismatch" in completed.stderr
    assert not output.exists()


def test_r3_r1_provenance_gate_rejects_allocator_geometry_drift(
    tmp_path: Path,
) -> None:
    geometry, rendezvous, allocator = _accepted_r2_evidence(tmp_path)
    value = json.loads(allocator.read_text(encoding="utf-8"))
    value["required_cpu_blocks"] = 127
    _write_json(allocator, value)

    completed = subprocess.run(
        [
            sys.executable,
            str(AUDITOR),
            "accepted-capacity-provenance",
            "--geometry-summary",
            str(geometry),
            "--rendezvous-marker",
            str(rendezvous),
            "--allocator-summary",
            str(allocator),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "accepted allocator capacity mismatch" in completed.stderr


def test_r3_r1_runner_changes_only_task_lineage_not_runtime_contract(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["P8_2_K1A_AUDIT_ONLY"] = "1"
    completed = subprocess.run(
        ["bash", str(R3_R1_RUNNER), str(tmp_path / "result")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    audit = dict(
        line.split("=", 1)
        for line in completed.stdout.splitlines()
        if "=" in line
    )
    assert audit["task_id"] == (
        "p8_2_k1a_r3_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_"
        "2026_0718"
    )
    assert audit["execution_mode"] == (
        "authorized_repaired_provenance_single_lifecycle_six_request_mechanism"
    )
    assert audit["cpu_bytes_to_use"] == "3444834304"
    assert audit["cpu_bytes_to_use_per_rank"] == "430604288"
    assert audit["server_command_sha256"] == (
        "418d2796ec2dd15ab7504c264a6635a50d064cb7b6425f809cbfba550d2f5bb0"
    )


def test_r3_r1_audit_preserves_parent_block_and_exact_r2_evidence_roles() -> None:
    audit = yaml.safe_load(R3_R1_AUDIT.read_text(encoding="utf-8"))

    assert audit["stage"] == "P8.2-K1A-R3-R1"
    assert audit["parent_r3"]["server_grade"] == (
        "blocked_p8_2_k1a_r3_source_or_provenance_gate"
    )
    assert audit["parent_r3"]["npu_started"] is False
    assert audit["parent_r3"]["model_request_count"] == 0
    assert audit["repair"]["geometry_summary_schema"] == (
        "p8_2_k1a_r2_geometry_summary_v1"
    )
    assert audit["repair"]["rendezvous_marker_schema"] == (
        "p8_2_k1a_r2_geometry_rendezvous_v1"
    )
    assert audit["repair"]["rendezvous_marker_sha256"] == (
        "fa258790475303b88a41d4e3f2db684a41a79026b22d434ba9827f0275280796"
    )
    assert audit["unchanged_runtime"]["server_command_sha256"] == (
        "418d2796ec2dd15ab7504c264a6635a50d064cb7b6425f809cbfba550d2f5bb0"
    )
    assert audit["unchanged_runtime"]["cpu_bytes_to_use_per_rank"] == 430604288
    assert audit["unchanged_runtime"]["cpu_bytes_to_use_total"] == 3444834304
    assert audit["decision"]["formal_lifecycle_count_exact"] == 1
    assert audit["decision"]["model_request_count_exact"] == 6
    assert audit["decision"]["request_retry_count_exact"] == 0
    assert audit["decision"]["k2_authorized"] is False
