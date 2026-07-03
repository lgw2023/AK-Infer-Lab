import os

import tools.observability_profile.probes as probes_module
from tools.observability_profile.probes import ProbeCommand, run_probe_command, run_standard_probes


def test_run_probe_command_records_exit_code_and_context():
    result = run_probe_command(ProbeCommand(name="python_version", command=["python", "--version"]))

    assert result["tool"] == "python_version"
    assert result["exit_code"] == 0
    assert result["runtime_ms"] >= 0
    assert "run_as_user" in result
    assert "inside_container" in result
    assert "output_excerpt" in result


def test_standard_probes_are_non_empty():
    probes = run_standard_probes()
    names = {probe["tool"] for probe in probes}

    assert "npu_smi_probe" in names
    assert "container_permission_probe" in names


def test_container_privileged_is_not_inferred_from_root_euid(monkeypatch):
    monkeypatch.setattr(probes_module.os, "geteuid", lambda: 0, raising=False)

    result = run_probe_command(ProbeCommand(name="python_version", command=["python", "--version"]))

    assert result["container_privileged"] is None
    if hasattr(os, "geteuid"):
        assert result["effective_user_is_root"] is True
