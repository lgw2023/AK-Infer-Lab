import importlib.metadata as importlib_metadata
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


def test_module_version_prefers_distribution_metadata_without_import(monkeypatch):
    def fake_version(package_name: str) -> str:
        assert package_name == "torch-npu"
        return "2.6.0"

    def fail_run_text(command: list[str], timeout: int = 5) -> str:
        raise AssertionError(f"module import command should not run: {command}")

    monkeypatch.setattr(importlib_metadata, "version", fake_version)
    monkeypatch.setattr(manifest_module, "_run_text", fail_run_text)

    assert manifest_module._module_version("torch_npu") == "2.6.0"


def test_cann_version_falls_back_to_cann_path(tmp_path: Path, monkeypatch):
    cann_environment = "/usr/local/Ascend/cann-9.0.0\n/usr/local/sbin/npu-smi"

    def fake_run_text(command: list[str], timeout: int = 5) -> str:
        command_text = " ".join(command)
        if "echo ${ASCEND_HOME_PATH" in command_text:
            return cann_environment
        if "version.info" in command_text:
            return "unknown"
        return "unknown"

    monkeypatch.setattr(manifest_module, "_run_text", fake_run_text)

    manifest = build_manifest(
        run_id="obs_2026_0703_atlas800t_a2_001",
        output_root=tmp_path,
        server_id="atlas800t-a2-node-001",
        operator="codex",
    )

    assert manifest["cann_version"] == "9.0.0"
    assert manifest["cann_environment"] == cann_environment


def test_build_manifest_parses_npu_smi_inventory(tmp_path: Path, monkeypatch):
    npu_smi = """
Driver Version: 23.0.6
Firmware Version: 7.1.0
NPU ID: 0
HBM-Usage(MB): 1024 / 65536
NPU ID: 1
HBM-Usage(MB): 2048 / 65536
"""

    def fake_run_text(command: list[str], timeout: int = 5) -> str:
        if command == ["npu-smi", "info"]:
            return npu_smi
        return "unknown"

    monkeypatch.setattr(manifest_module, "_run_text", fake_run_text)

    manifest = build_manifest(
        run_id="obs_2026_0703_atlas800t_a2_001",
        output_root=tmp_path,
        server_id="atlas800t-a2-node-001",
        operator="codex",
    )

    assert manifest["driver_version"] == "23.0.6"
    assert manifest["firmware_version"] == "7.1.0"
    assert manifest["npu_count"] == 2
    assert manifest["hbm_per_npu_gb"] == 64.0
