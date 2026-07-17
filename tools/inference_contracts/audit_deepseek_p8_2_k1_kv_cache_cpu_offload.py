#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


VLLM_COMMIT = "0decac0d96c42b49572498019f0a0e3600f50398"
VLLM_ASCEND_COMMIT = "5f6faa0cb8830f667266f3b8121cd1383606f2a1"
BLOCKED_GRADE = "blocked_p8_2_k1_frozen_stack_import_incompatible"

EXPECTED_SOURCES = {
    "vllm": {
        "vllm/config/kv_transfer.py": (
            "b22af99f703f168c49607f05c2e9610209ea351a",
            4447,
            "d661008cfb85fbe0758994ab1970c55199e68abcd3633fd9d12e8b39d99d1652",
        ),
        "vllm/engine/arg_utils.py": (
            "79c6e0ae925d9fc9f0f3bcbea0a2f7fedd2c34a7",
            111327,
            "ee107df77e59d1ca860d826feda540158bdefbdcaa3a2b786967396d83315d16",
        ),
        "vllm/v1/kv_offload/base.py": (
            "de65be1c05e63a7dde07e7047b8c2d3bf23500e3",
            13989,
            "af70c723898631e5461cc2873629a3bbd4b75492996e60be573686355d618f2a",
        ),
        "vllm/v1/kv_offload/factory.py": (
            "8b967f771b046e8f4476586b0d28f54b9d1558de",
            2252,
            "2e389bfd245dc41ccc3ddbc03897e09c9b95fab0676850fd73294c1b7a2353f5",
        ),
        "vllm/distributed/kv_transfer/kv_connector/v1/offloading_connector.py": (
            "6c75bda0c4cf5393383919c086eb4c333f0812e8",
            7768,
            "b7e83ac78d50ea8652227eb1f245206c37dbd692597cf08348fef1e6df032025",
        ),
        "vllm/distributed/kv_transfer/kv_connector/v1/offloading/metrics.py": (
            "0839b2727ccc01b4b3cea9e1b69e08093fca81d2",
            6195,
            "5ab3c65af3c0f78b0696bcc60c68ecfe51332c6d5f6684bb2cfa0e0ea9677d73",
        ),
    },
    "vllm_ascend": {
        "vllm_ascend/kv_offload/npu.py": (
            "90816ce3abbc4143e8eb2ab1a081cab8d07c0b86",
            2699,
            "ab2b86b807f7bd3582d607e597e437c5e113ef9dde4a8198c86353716e17ad55",
        ),
        "vllm_ascend/kv_offload/cpu_npu.py": (
            "1f9f8391ac12ea88e367458f00e428791324732b",
            10307,
            "ff95f78e28d985c43e29f8a2a3dd99fd05794a84223a59809320b9b42c15ab78",
        ),
        "docs/source/user_guide/feature_guide/kv_cache_cpu_offload.md": (
            "974897e6f3e1ad57bd88a211993e5f859caa2d4a",
            4613,
            "c0eb9cf3785f5224136aac5e44ae17352db7fc264be2b8e2ce4e610311a689ad",
        ),
    },
}

LEGACY_MODULE_PATHS = [
    "vllm/v1/kv_offload/abstract.py",
    "vllm/v1/kv_offload/mediums.py",
    "vllm/v1/kv_offload/spec.py",
]


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=check,
    )


def _read_object(repo: Path, commit: str, relative_path: str) -> bytes:
    return _git(repo, "show", f"{commit}:{relative_path}").stdout


def _object_exists(repo: Path, commit: str, relative_path: str) -> bool:
    return (
        _git(repo, "cat-file", "-e", f"{commit}:{relative_path}", check=False).returncode
        == 0
    )


def _evaluate_source_payloads(
    source_bytes: dict[tuple[str, str], bytes],
    inventory: list[dict[str, Any]],
    source_hash_gate: bool,
    missing: list[str],
) -> dict[str, Any]:
    npu_source = source_bytes[("vllm_ascend", "vllm_ascend/kv_offload/npu.py")].decode()
    base_source = source_bytes[("vllm", "vllm/v1/kv_offload/base.py")].decode()
    config_source = source_bytes[("vllm", "vllm/config/kv_transfer.py")].decode()
    arg_source = source_bytes[("vllm", "vllm/engine/arg_utils.py")].decode()
    imports_expected = all(
        module in npu_source
        for module in (
            "vllm.v1.kv_offload.abstract",
            "vllm.v1.kv_offload.mediums",
            "vllm.v1.kv_offload.spec",
        )
    )
    single_group_assertions = npu_source.count("assert len(self.gpu_block_size) == 1")
    frozen_api_expected = all(
        marker in base_source
        for marker in ("class CanonicalKVCaches", "class OffloadingSpec")
    )
    cli_config_expected = all(
        marker in config_source
        for marker in ("class KVTransferConfig", "kv_connector_extra_config")
    ) and '"--kv-transfer-config"' in arg_source
    blocked = (
        source_hash_gate
        and imports_expected
        and len(missing) == len(LEGACY_MODULE_PATHS)
        and single_group_assertions == 2
        and frozen_api_expected
        and cli_config_expected
    )
    return {
        "audit_grade": BLOCKED_GRADE if blocked else "blocked_p8_2_k1_source_gate_drift",
        "vllm_commit": VLLM_COMMIT,
        "vllm_ascend_commit": VLLM_ASCEND_COMMIT,
        "source_hash_gate": source_hash_gate,
        "source_inventory": inventory,
        "missing_legacy_modules": missing,
        "npu_spec_single_group_assertion_count": single_group_assertions,
        "frozen_vllm_base_api_present": frozen_api_expected,
        "kv_transfer_cli_and_config_present": cli_config_expected,
        "formal_k1_workload_allowed": False,
        "npu_started": False,
        "vllm_server_started": False,
        "model_request_sent": False,
    }


def inspect_frozen_sources(vllm_repo: Path, vllm_ascend_repo: Path) -> dict[str, Any]:
    repos = {"vllm": vllm_repo, "vllm_ascend": vllm_ascend_repo}
    commits = {"vllm": VLLM_COMMIT, "vllm_ascend": VLLM_ASCEND_COMMIT}
    inventory: list[dict[str, Any]] = []
    source_hash_gate = True
    source_bytes: dict[tuple[str, str], bytes] = {}

    for target, expected_by_path in EXPECTED_SOURCES.items():
        repo = repos[target]
        commit = commits[target]
        _git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
        for relative_path, (expected_oid, expected_bytes, expected_sha) in expected_by_path.items():
            payload = _read_object(repo, commit, relative_path)
            source_bytes[(target, relative_path)] = payload
            oid = _git(repo, "rev-parse", f"{commit}:{relative_path}").stdout.decode().strip()
            sha256 = hashlib.sha256(payload).hexdigest()
            matched = (
                oid == expected_oid
                and len(payload) == expected_bytes
                and sha256 == expected_sha
            )
            source_hash_gate = source_hash_gate and matched
            inventory.append(
                {
                    "target": target,
                    "relative_path": relative_path,
                    "blob_oid": oid,
                    "bytes": len(payload),
                    "sha256": sha256,
                    "matched": matched,
                }
            )

    missing = [
        path
        for path in LEGACY_MODULE_PATHS
        if not _object_exists(vllm_repo, VLLM_COMMIT, path)
    ]
    return _evaluate_source_payloads(
        source_bytes, inventory, source_hash_gate, missing
    )


def inspect_installed_sources(
    vllm_root: Path, vllm_ascend_root: Path
) -> dict[str, Any]:
    roots = {"vllm": vllm_root, "vllm_ascend": vllm_ascend_root}
    inventory: list[dict[str, Any]] = []
    source_bytes: dict[tuple[str, str], bytes] = {}
    source_hash_gate = True
    for target, expected_by_path in EXPECTED_SOURCES.items():
        for relative_path, (expected_oid, expected_bytes, expected_sha) in expected_by_path.items():
            path = roots[target] / relative_path
            if not path.is_file() and relative_path.startswith("docs/"):
                inventory.append(
                    {
                        "target": target,
                        "relative_path": relative_path,
                        "frozen_blob_oid": expected_oid,
                        "runtime_required": False,
                        "installed": False,
                        "matched": None,
                    }
                )
                continue
            payload = path.read_bytes()
            source_bytes[(target, relative_path)] = payload
            sha256 = hashlib.sha256(payload).hexdigest()
            matched = len(payload) == expected_bytes and sha256 == expected_sha
            source_hash_gate = source_hash_gate and matched
            inventory.append(
                {
                    "target": target,
                    "relative_path": relative_path,
                    "frozen_blob_oid": expected_oid,
                    "bytes": len(payload),
                    "sha256": sha256,
                    "matched": matched,
                }
            )
    missing = [path for path in LEGACY_MODULE_PATHS if not (vllm_root / path).exists()]
    return _evaluate_source_payloads(
        source_bytes, inventory, source_hash_gate, missing
    )


RUNTIME_PROBE = r'''
import importlib.util
import json

result = {"module_resolution": {}}
for name in (
    "vllm.v1.kv_offload.abstract",
    "vllm.v1.kv_offload.mediums",
    "vllm.v1.kv_offload.spec",
):
    try:
        spec = importlib.util.find_spec(name)
        result["module_resolution"][name] = None if spec is None else spec.origin
    except Exception as exc:
        result["module_resolution"][name] = {
            "error_type": type(exc).__name__, "error": str(exc)
        }

try:
    from vllm.config import KVTransferConfig
    config = KVTransferConfig(
        kv_connector="OffloadingConnector",
        kv_role="kv_both",
        kv_connector_extra_config={
            "num_cpu_blocks": 1000,
            "block_size": 128,
            "spec_name": "NPUOffloadingSpec",
            "spec_module_path": "vllm_ascend.kv_offload.npu",
        },
    )
    result["kv_transfer_config"] = {
        "kv_connector": config.kv_connector,
        "kv_role": config.kv_role,
        "kv_connector_extra_config": config.kv_connector_extra_config,
    }
except Exception as exc:
    result["kv_transfer_config_error"] = {
        "error_type": type(exc).__name__, "error": str(exc)
    }

try:
    import vllm_ascend.kv_offload.npu as npu  # noqa: F401
    result["npu_spec_import"] = "success"
except Exception as exc:
    result["npu_spec_import"] = "failed"
    result["npu_spec_import_error"] = {
        "error_type": type(exc).__name__, "error": str(exc)
    }

result.update({
    "npu_started": False,
    "vllm_server_started": False,
    "model_request_sent": False,
})
print("P8K1_RUNTIME_JSON=" + json.dumps(result, sort_keys=True))
'''


def inspect_runtime_imports(runtime_python: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [str(runtime_python), "-c", RUNTIME_PROBE],
        text=True,
        capture_output=True,
        check=False,
    )
    marker = "P8K1_RUNTIME_JSON="
    payload_line = next(
        (line for line in reversed(completed.stdout.splitlines()) if line.startswith(marker)),
        None,
    )
    payload = json.loads(payload_line[len(marker) :]) if payload_line else None
    return {
        "subprocess_exit": completed.returncode,
        "probe": payload,
        "stdout_without_payload": "\n".join(
            line for line in completed.stdout.splitlines() if not line.startswith(marker)
        ),
        "stderr": completed.stderr,
        "npu_started": False,
        "vllm_server_started": False,
        "model_request_sent": False,
    }


def _emit(value: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit frozen P8.2-K1 KV Cache CPU Offload compatibility without NPU use."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    source = subparsers.add_parser("source-audit")
    source.add_argument("--vllm-repo", type=Path, required=True)
    source.add_argument("--vllm-ascend-repo", type=Path, required=True)
    source.add_argument("--output", type=Path)
    installed = subparsers.add_parser("installed-source-audit")
    installed.add_argument("--vllm-root", type=Path, required=True)
    installed.add_argument("--vllm-ascend-root", type=Path, required=True)
    installed.add_argument("--output", type=Path)
    runtime = subparsers.add_parser("runtime-import-probe")
    runtime.add_argument("--runtime-python", type=Path, required=True)
    runtime.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "source-audit":
        result = inspect_frozen_sources(args.vllm_repo, args.vllm_ascend_repo)
    elif args.command == "installed-source-audit":
        result = inspect_installed_sources(args.vllm_root, args.vllm_ascend_root)
    else:
        result = inspect_runtime_imports(args.runtime_python)
    _emit(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
