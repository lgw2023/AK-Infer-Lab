from pathlib import Path

import tools.observability_profile.manifest as manifest_module
from tools.observability_profile.manifest import build_manifest, stable_hash


def test_stable_hash_is_ordered_and_repeatable():
    first = stable_hash({"b": "2", "a": "1"})
    second = stable_hash({"a": "1", "b": "2"})
    assert first == second
    assert len(first) == 16


def test_build_manifest_contains_required_run_identity(tmp_path: Path):
    manifest = build_manifest(
        run_id="obs_2026_0703_atlas800t_a2_001",
        output_root=tmp_path,
        server_id="atlas800t-a2-node-001",
        operator="codex",
        probe_script_version="0.1.0",
    )
    assert manifest["profile_run_id"] == "obs_2026_0703_atlas800t_a2_001"
    assert manifest["schema_version"] == "0.1.0"
    assert manifest["server_id"] == "atlas800t-a2-node-001"
    assert manifest["operator"] == "codex"
    assert manifest["hardware_topology_hash"]
    assert manifest["software_stack_hash"]
    assert manifest["probe_script_version"] == "0.1.0"


def test_container_privileged_is_not_inferred_from_root_euid(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(manifest_module.os, "geteuid", lambda: 0)

    manifest = build_manifest(
        run_id="obs_2026_0703_atlas800t_a2_001",
        output_root=tmp_path,
        server_id="atlas800t-a2-node-001",
        operator="codex",
    )

    assert manifest["container_privileged"] is None
    assert manifest["effective_user_is_root"] is True


def test_cann_version_stays_distinct_from_environment(tmp_path: Path, monkeypatch):
    cann_environment = "/usr/local/Ascend/ascend-toolkit\n/usr/local/bin/npu-smi"

    def fake_run_text(command: list[str], timeout: int = 5) -> str:
        if "ASCEND_HOME_PATH" in " ".join(command):
            return cann_environment
        return "unknown"

    monkeypatch.setattr(manifest_module, "_run_text", fake_run_text)

    manifest = build_manifest(
        run_id="obs_2026_0703_atlas800t_a2_001",
        output_root=tmp_path,
        server_id="atlas800t-a2-node-001",
        operator="codex",
    )

    assert manifest["cann_version"] == "unknown"
    assert manifest["cann_environment"] == cann_environment
