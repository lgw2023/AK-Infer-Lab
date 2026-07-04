from __future__ import annotations

import hashlib
import importlib.metadata as importlib_metadata
import json
import os
import platform
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.observability_profile import __version__


def _run_text(command: list[str], timeout: int = 5) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"{type(exc).__name__}: {exc}"
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    return output[:4000]


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _inside_container() -> bool:
    if Path("/.dockerenv").exists():
        return True
    cgroup = Path("/proc/1/cgroup")
    if cgroup.exists():
        text = cgroup.read_text(errors="ignore")
        return "docker" in text or "containerd" in text or "kubepods" in text
    return False


def _container_id() -> str | None:
    cgroup = Path("/proc/self/cgroup")
    if not cgroup.exists():
        return None
    text = cgroup.read_text(errors="ignore")
    for token in text.replace("/", " ").replace(":", " ").split():
        if len(token) >= 12 and all(ch.isalnum() or ch in "-_" for ch in token):
            return token[:64]
    return None


def _git_commit(repo_root: Path) -> str:
    result = _run_text(["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"])
    if "fatal:" in result or "FileNotFoundError" in result:
        return "unknown"
    return result.splitlines()[0].strip() if result.strip() else "unknown"


def _effective_user_is_root() -> bool | None:
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None:
        return None
    return geteuid() == 0


def _cann_environment() -> str:
    return _run_text(["bash", "-lc", "echo ${ASCEND_HOME_PATH:-unknown} && which npu-smi || true"])


def _parse_version_from_text(text: str) -> str:
    for line in text.splitlines():
        if "version" not in line.lower():
            continue
        match = re.search(r"\b\d+(?:\.\d+)+(?:[A-Za-z0-9_.-]*)\b", line)
        if match:
            return match.group(0)
    return "unknown"


def _cann_version(cann_environment: str = "") -> str:
    output = _run_text([
        "bash",
        "-lc",
        (
            "for file in "
            "${ASCEND_HOME_PATH:-}/version.info "
            "${ASCEND_HOME_PATH:-}/ascend_toolkit_install.info "
            "/usr/local/Ascend/ascend-toolkit/latest/version.info; do "
            "[ -f \"$file\" ] && sed -n '1,20p' \"$file\" && exit 0; "
            "done"
        ),
    ])
    version = _parse_version_from_text(output)
    if version != "unknown":
        return version
    match = re.search(r"\bcann[-_/]?(\d+(?:\.\d+)+(?:[A-Za-z0-9_.-]*)?)\b", cann_environment, re.IGNORECASE)
    if match:
        return match.group(1)
    return "unknown"


def _distribution_name(module_name: str) -> str:
    return module_name.replace("_", "-")


def _module_version(module_name: str) -> str:
    try:
        return importlib_metadata.version(_distribution_name(module_name))
    except importlib_metadata.PackageNotFoundError:
        pass

    output = _run_text([
        sys.executable,
        "-c",
        f"import {module_name}; print(getattr({module_name}, '__version__', 'unknown'))",
    ])
    lowered = output.lower()
    if any(marker in lowered for marker in ("modulenotfounderror", "importerror", "traceback", "timeoutexpired", "timed out")):
        return "unknown"
    return output.splitlines()[0].strip() if output.strip() else "unknown"


def _parse_npu_smi_info(output: str) -> dict[str, Any]:
    driver_match = re.search(r"\bDriver\s+Version\s*[:：]\s*([^\s|]+)", output, re.IGNORECASE)
    firmware_match = re.search(r"\bFirmware\s+Version\s*[:：]\s*([^\s|]+)", output, re.IGNORECASE)
    npu_ids = {int(match.group(1)) for match in re.finditer(r"\bNPU\s*ID\s*[:：]\s*(\d+)\b", output, re.IGNORECASE)}
    hbm_totals_mb = [
        int(match.group(1))
        for match in re.finditer(r"HBM[-\s]*Usage\s*\(MB\)\s*[:：]?\s*\d+\s*/\s*(\d+)", output, re.IGNORECASE)
    ]

    npu_count: int | str = len(npu_ids) if npu_ids else "unknown"
    if npu_count == "unknown" and hbm_totals_mb:
        npu_count = len(hbm_totals_mb)

    hbm_per_npu_gb: float | str = "unknown"
    if hbm_totals_mb:
        hbm_per_npu_gb = round(max(hbm_totals_mb) / 1024, 3)

    return {
        "driver_version": driver_match.group(1) if driver_match else "unknown",
        "firmware_version": firmware_match.group(1) if firmware_match else "unknown",
        "npu_count": npu_count,
        "hbm_per_npu_gb": hbm_per_npu_gb,
    }


def build_manifest(
    *,
    run_id: str,
    output_root: Path,
    server_id: str,
    operator: str,
    probe_script_version: str = __version__,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    repo_root = Path(__file__).resolve().parents[2]
    npu_smi_info = _run_text(["npu-smi", "info"])
    npu_inventory = _parse_npu_smi_info(npu_smi_info)
    hardware_inputs = {
        "npu_smi": npu_smi_info,
        "lspci": _run_text(["lspci"]),
        "numactl": _run_text(["numactl", "--hardware"]),
        "lsblk": _run_text(["lsblk", "-J"]),
    }
    cann_environment = _cann_environment()
    cann_version = _cann_version(cann_environment)
    torch_npu_version = _module_version("torch_npu")
    mindie_version = _module_version("mindie")
    vllm_ascend_version = _module_version("vllm_ascend")
    python_executable = sys.executable
    python_version = platform.python_version()
    conda_prefix = os.environ.get("CONDA_PREFIX", "unknown")
    conda_default_env = os.environ.get("CONDA_DEFAULT_ENV", "unknown")
    software_inputs = {
        "python": python_version,
        "python_executable": python_executable,
        "conda_prefix": conda_prefix,
        "conda_default_env": conda_default_env,
        "platform": platform.platform(),
        "cann_version": cann_version,
        "cann_environment": cann_environment,
        "torch_npu": torch_npu_version,
        "mindie": mindie_version,
        "vllm_ascend": vllm_ascend_version,
        "container_image": os.environ.get("CONTAINER_IMAGE", "unknown"),
    }
    return {
        "profile_run_id": run_id,
        "schema_version": "0.1.0",
        "server_id": server_id,
        "timestamp_start": now,
        "timestamp_end": None,
        "operator": operator,
        "git_commit": _git_commit(repo_root),
        "os_name": platform.system(),
        "kernel_version": platform.release(),
        "python_executable": python_executable,
        "python_version": python_version,
        "conda_prefix": conda_prefix,
        "conda_default_env": conda_default_env,
        "host_name": socket.gethostname(),
        "container_id": _container_id(),
        "container_image": os.environ.get("CONTAINER_IMAGE", "unknown"),
        "inside_container": _inside_container(),
        "container_privileged": None,
        "effective_user_is_root": _effective_user_is_root(),
        "cann_version": cann_version,
        "cann_environment": cann_environment,
        "torch_npu_version": torch_npu_version,
        "mindie_version": mindie_version,
        "vllm_ascend_version": vllm_ascend_version,
        "driver_version": npu_inventory["driver_version"],
        "firmware_version": npu_inventory["firmware_version"],
        "npu_count": npu_inventory["npu_count"],
        "hbm_per_npu_gb": npu_inventory["hbm_per_npu_gb"],
        "field_catalog_version": "0.1.0",
        "hardware_topology_hash": stable_hash(hardware_inputs),
        "software_stack_hash": stable_hash(software_inputs),
        "probe_script_version": probe_script_version,
        "output_root": str(output_root),
        "notes": "Generated by P0 observability profile tool.",
    }
