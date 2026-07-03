from __future__ import annotations

import getpass
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OUTPUT_EXCERPT_LIMIT = 4000
UNSAFE_COMMANDS = {
    "rm",
    "mv",
    "dd",
    "mkfs",
    "mount",
    "umount",
    "chmod",
    "chown",
    "kill",
    "pkill",
    "reboot",
    "shutdown",
}
SHELLS = {"bash", "sh", "zsh", "dash"}
CANN_PROFILER_COMMAND = (
    "bash",
    "-lc",
    "command -v msprof >/dev/null 2>&1 || exit 127; msprof --help | head -40",
)
EBPF_COMMAND = (
    "bash",
    "-lc",
    "command -v bpftrace >/dev/null 2>&1 || exit 127; bpftrace --version",
)
CONTAINER_PERMISSION_COMMAND = (
    "bash",
    "-lc",
    "id && test -r /proc/1/cgroup && head -5 /proc/1/cgroup",
)
ALLOWED_SHELL_COMMANDS = {
    CANN_PROFILER_COMMAND,
    EBPF_COMMAND,
    CONTAINER_PERMISSION_COMMAND,
}


@dataclass(frozen=True)
class ProbeCommand:
    name: str
    command: list[str]
    maps_to_fields: list[str] = field(default_factory=list)
    timeout_s: int = 5


def inside_container() -> bool:
    if Path("/.dockerenv").exists():
        return True
    cgroup = Path("/proc/1/cgroup")
    if cgroup.exists():
        text = cgroup.read_text(errors="ignore")
        return "docker" in text or "containerd" in text or "kubepods" in text
    return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _effective_user_is_root() -> bool | None:
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None:
        return None
    return geteuid() == 0


def _run_as_user() -> str:
    try:
        return getpass.getuser()
    except OSError:
        return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"


def _output_excerpt(stdout: str | None, stderr: str | None) -> str:
    output = "\n".join(part for part in [(stdout or "").strip(), (stderr or "").strip()] if part)
    return output[:OUTPUT_EXCERPT_LIMIT]


def _blocked_reason(category: str | None, detail: str | None) -> dict[str, str | None]:
    return {"category": category, "detail": detail}


def _is_shell_command(command: list[str]) -> bool:
    return bool(command) and Path(command[0]).name in SHELLS


def _safety_block_reason(command: list[str]) -> dict[str, str | None] | None:
    command_name = Path(command[0]).name if command else ""
    if command_name == "env":
        return _blocked_reason("permission", "env wrapper probes are not allowed")
    if command_name == "sudo":
        return _blocked_reason("permission", "sudo probes are not allowed")
    if command_name in UNSAFE_COMMANDS:
        return _blocked_reason("permission", f"unsafe probe command is not allowed: {command_name}")
    if _is_shell_command(command) and tuple(command) not in ALLOWED_SHELL_COMMANDS:
        return _blocked_reason("permission", "non-allowlisted shell probe command is not allowed")
    return None


def _classify_failure(exit_code: int | None, output: str) -> dict[str, str | None]:
    lowered = output.lower()
    if "/proc/1/cgroup" in lowered and ("no such file" in lowered or "not found" in lowered):
        return _blocked_reason("container_isolation", "container cgroup context is unavailable")
    if exit_code == 127 or "command not found" in lowered or "not found" in lowered:
        return _blocked_reason("tool_missing", "probe command is not available")
    if (
        "permission denied" in lowered
        or "operation not permitted" in lowered
        or "sudo" in lowered
        or "password" in lowered
    ):
        return _blocked_reason("permission", "probe command lacks required permission")
    return _blocked_reason("unknown", "probe command returned a nonzero exit code")


def run_probe_command(probe: ProbeCommand) -> dict[str, Any]:
    start_time = _now()
    started_at = time.monotonic()
    exit_code: int | None = None
    stdout = ""
    stderr = ""
    blocked_reason = _blocked_reason(None, None)
    safety_block_reason = _safety_block_reason(probe.command)

    if not probe.command:
        exit_code = 127
        blocked_reason = _blocked_reason("tool_missing", "empty command")
    elif safety_block_reason is not None:
        exit_code = 126
        blocked_reason = safety_block_reason
    else:
        try:
            result = subprocess.run(
                probe.command,
                check=False,
                capture_output=True,
                text=True,
                timeout=probe.timeout_s,
            )
            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr
        except FileNotFoundError as exc:
            exit_code = 127
            stderr = str(exc)
            blocked_reason = _blocked_reason("tool_missing", str(exc))
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            blocked_reason = _blocked_reason("unknown", f"probe timed out after {probe.timeout_s} seconds")
        except OSError as exc:
            exit_code = 127 if isinstance(exc, FileNotFoundError) else 1
            stderr = str(exc)
            category = "tool_missing" if exit_code == 127 else "unknown"
            blocked_reason = _blocked_reason(category, str(exc))

    end_time = _now()
    runtime_ms = round((time.monotonic() - started_at) * 1000, 3)
    output_excerpt = _output_excerpt(stdout, stderr)
    if exit_code != 0 and blocked_reason["category"] is None:
        blocked_reason = _classify_failure(exit_code, output_excerpt)

    available = exit_code == 0
    return {
        "tool": probe.name,
        "available": available,
        "permission_status": "ok" if available else "blocked",
        "command": list(probe.command),
        "exit_code": exit_code,
        "start_time": start_time,
        "end_time": end_time,
        "runtime_ms": runtime_ms,
        "run_as_user": _run_as_user(),
        "inside_container": inside_container(),
        "container_privileged": None,
        "effective_user_is_root": _effective_user_is_root(),
        "output_excerpt": output_excerpt,
        "artifact_path": None,
        "maps_to_fields": list(probe.maps_to_fields),
        "blocked_reason": blocked_reason,
    }


STANDARD_PROBES = [
    ProbeCommand(
        name="npu_smi_probe",
        command=["npu-smi", "info"],
        maps_to_fields=["server_observability_profile.npu_smi_available"],
    ),
    ProbeCommand(
        name="cann_profiler_probe",
        command=list(CANN_PROFILER_COMMAND),
        maps_to_fields=["server_observability_profile.cann_profiler_available"],
    ),
    ProbeCommand(
        name="perf_probe",
        command=["perf", "--version"],
        maps_to_fields=["server_observability_profile.perf_available"],
    ),
    ProbeCommand(
        name="ebpf_probe",
        command=list(EBPF_COMMAND),
        maps_to_fields=["server_observability_profile.ebpf_available"],
    ),
    ProbeCommand(
        name="fio_probe",
        command=["fio", "--version"],
        maps_to_fields=["server_observability_profile.fio_available"],
    ),
    ProbeCommand(
        name="numa_probe",
        command=["numactl", "--hardware"],
        maps_to_fields=["server_observability_profile.numa_available"],
    ),
    ProbeCommand(
        name="container_permission_probe",
        command=list(CONTAINER_PERMISSION_COMMAND),
        maps_to_fields=["server_observability_profile.container_cgroup_readable"],
    ),
]


def run_standard_probes() -> list[dict[str, Any]]:
    return [run_probe_command(probe) for probe in STANDARD_PROBES]
