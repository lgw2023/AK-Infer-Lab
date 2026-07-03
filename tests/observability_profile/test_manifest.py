from pathlib import Path

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
