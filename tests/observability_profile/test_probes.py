import os
import subprocess

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


def test_first_token_sudo_is_blocked_without_execution(monkeypatch):
    executed = False

    def fake_run(*args, **kwargs):
        nonlocal executed
        executed = True
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(probes_module.subprocess, "run", fake_run)

    result = run_probe_command(ProbeCommand(name="sudo_probe", command=["sudo", "-n", "true"]))

    assert executed is False
    assert result["available"] is False
    assert result["exit_code"] == 126
    assert result["permission_status"] == "blocked"
    assert result["blocked_reason"]["category"] == "permission"


def test_nested_shell_sudo_is_blocked_without_execution(monkeypatch):
    executed = False

    def fake_run(*args, **kwargs):
        nonlocal executed
        executed = True
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(probes_module.subprocess, "run", fake_run)

    result = run_probe_command(ProbeCommand(name="shell_sudo_probe", command=["bash", "-lc", "sudo -n true"]))

    assert executed is False
    assert result["available"] is False
    assert result["exit_code"] == 126
    assert result["permission_status"] == "blocked"
    assert result["blocked_reason"]["category"] == "permission"


def test_missing_binary_returns_tool_missing_without_raising(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("missing-tool")

    monkeypatch.setattr(probes_module.subprocess, "run", fake_run)

    result = run_probe_command(ProbeCommand(name="missing_probe", command=["missing-tool"]))

    assert result["available"] is False
    assert result["exit_code"] == 127
    assert result["blocked_reason"]["category"] == "tool_missing"


def test_generic_nonzero_returns_unknown_blocked_reason(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=2, stdout="", stderr="usage error")

    monkeypatch.setattr(probes_module.subprocess, "run", fake_run)

    result = run_probe_command(ProbeCommand(name="generic_failure", command=["probe", "--bad-arg"]))

    assert result["available"] is False
    assert result["exit_code"] == 2
    assert result["blocked_reason"]["category"] == "unknown"


def test_container_permission_probe_does_not_map_to_container_privileged():
    probes = run_standard_probes()
    container_probe = next(probe for probe in probes if probe["tool"] == "container_permission_probe")

    assert "server_observability_profile.container_privileged" not in container_probe["maps_to_fields"]


def test_shell_sudo_after_attached_separator_is_blocked_without_execution(monkeypatch):
    executed = False

    def fake_run(*args, **kwargs):
        nonlocal executed
        executed = True
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(probes_module.subprocess, "run", fake_run)

    result = run_probe_command(
        ProbeCommand(name="shell_sudo_probe", command=["bash", "-lc", "echo ok; sudo -n true"])
    )

    assert executed is False
    assert result["available"] is False
    assert result["exit_code"] == 126
    assert result["permission_status"] == "blocked"
    assert result["blocked_reason"]["category"] == "permission"


def test_destructive_direct_command_is_blocked_without_execution(monkeypatch):
    executed = False

    def fake_run(*args, **kwargs):
        nonlocal executed
        executed = True
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(probes_module.subprocess, "run", fake_run)

    result = run_probe_command(ProbeCommand(name="rm_probe", command=["rm", "-rf", "/tmp/example"]))

    assert executed is False
    assert result["available"] is False
    assert result["exit_code"] == 126
    assert result["permission_status"] == "blocked"
    assert result["blocked_reason"]["category"] == "permission"


def test_destructive_shell_command_after_separator_is_blocked_without_execution(monkeypatch):
    executed = False

    def fake_run(*args, **kwargs):
        nonlocal executed
        executed = True
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(probes_module.subprocess, "run", fake_run)

    result = run_probe_command(ProbeCommand(name="shell_rm_probe", command=["bash", "-lc", "echo ok && rm -rf /tmp/example"]))

    assert executed is False
    assert result["available"] is False
    assert result["exit_code"] == 126
    assert result["permission_status"] == "blocked"
    assert result["blocked_reason"]["category"] == "permission"


def test_timeout_returns_structured_blocked_reason(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"], output="partial", stderr="late")

    monkeypatch.setattr(probes_module.subprocess, "run", fake_run)

    result = run_probe_command(ProbeCommand(name="timeout_probe", command=["slow-probe"], timeout_s=1))

    assert result["available"] is False
    assert result["exit_code"] == 124
    assert result["permission_status"] == "blocked"
    assert result["blocked_reason"]["category"] == "unknown"
    assert result["blocked_reason"]["detail"]


def test_standard_probe_names_match_expected_set_exactly():
    probes = run_standard_probes()

    assert [probe["tool"] for probe in probes] == [
        "npu_smi_probe",
        "cann_profiler_probe",
        "perf_probe",
        "ebpf_probe",
        "fio_probe",
        "numa_probe",
        "container_permission_probe",
    ]
