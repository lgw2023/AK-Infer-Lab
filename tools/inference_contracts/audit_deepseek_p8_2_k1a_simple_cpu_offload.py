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
CANDIDATE_GRADE = "conditional_p8_2_k1a_simple_cpu_offload_source_candidate"

EXPECTED_SOURCES = {
    "vllm": {
        "vllm/distributed/kv_transfer/kv_connector/v1/simple_cpu_offload_connector.py": (
            "15904da9e53185dd964f749e1d85cc3256b8f497",
            9307,
            "fe4c1858af7b764ff0e1cbcb7b1994450471e4aa056e93e4742c89cad4ada1e0",
        ),
        "vllm/v1/simple_kv_offload/manager.py": (
            "24b6a178ce9db406b5544d044aed5a6ffab51e7f",
            34411,
            "fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b",
        ),
        "vllm/v1/simple_kv_offload/metadata.py": (
            "8c8d4511ee60a004c883d82cdeca79b8d479af82",
            2331,
            "6fd003219f3746e848bd8f93c5bb570c5d3b1564a5eb18c847c7c50bc1fb8bac",
        ),
        "vllm/v1/simple_kv_offload/worker.py": (
            "c23b44f291737941e722f86bc69601327bc83eae",
            12548,
            "cfc416891139e3b57f3a9d1cf9138274fdff9ef515b3aa8e260c96f367243a71",
        ),
        "tests/v1/simple_kv_offload/test_scheduler.py": (
            "970e16e5279864509516defa8f05e52956877682",
            53013,
            "612decca97716c6a3d6da93193f852ab0e4aabf10e276688bb2af5f519275029",
        ),
    },
    "vllm_ascend": {
        "vllm_ascend/distributed/kv_transfer/__init__.py": (
            "e0beaadfb3db95335ef6ecbaa9c1ecbb7d156727",
            3177,
            "dc693fd52eb44921e731b69021388ecc186f4e5fa5eca3b28fc1963661e355d1",
        ),
        "vllm_ascend/distributed/kv_transfer/kv_pool/simple_cpu_offload/simple_cpu_offload_connector.py": (
            "d4a59c5b27b09dbd238385d0114c7d6485e54a52",
            2607,
            "6abccc1dab9d3759a658889de84208620b01559e3b2f069a309278a25fc972d6",
        ),
        "vllm_ascend/simple_kv_offload/worker.py": (
            "7b3e8aefa95841ff97618bbdb568754af5cd6490",
            9982,
            "d1c8f3b99c1a35cfe18cfdf0d7588a44befd0d4fe618234d4bc8b447ae750434",
        ),
        "vllm_ascend/simple_kv_offload/copy_backend.py": (
            "5572ee8f1cd63906d0136bab0ae5c13f884a9983",
            4414,
            "51de529e72c3a0757e9285f2d9d9c1f50038d0aeb1f404f5d64ca5c3d51824cf",
        ),
        "vllm_ascend/simple_kv_offload/npu_mem_ops.py": (
            "fd873b906ce76ef68855042f8e826dfb3e69b22b",
            3485,
            "837b1ac035a20dcad918bdcab7e965ad44e62582c97e7ceda9be4b77871351c8",
        ),
        "tests/e2e/pull_request/one_card/test_simple_cpu_offload.py": (
            "688eea8accbfcd2583dfb093eac0ae470c2d5fa9",
            3655,
            "0ba4e55a5498f96e2e7482379ca56cbd089c993d4f64eddf82368237b76fda13",
        ),
    },
}


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    ).stdout


def _evaluate(
    source_bytes: dict[tuple[str, str], bytes],
    inventory: list[dict[str, Any]],
    source_hash_gate: bool,
) -> dict[str, Any]:
    connector = source_bytes[
        (
            "vllm",
            "vllm/distributed/kv_transfer/kv_connector/v1/simple_cpu_offload_connector.py",
        )
    ].decode()
    manager = source_bytes[("vllm", "vllm/v1/simple_kv_offload/manager.py")].decode()
    registration = source_bytes[
        ("vllm_ascend", "vllm_ascend/distributed/kv_transfer/__init__.py")
    ].decode()
    ascend_connector = source_bytes[
        (
            "vllm_ascend",
            "vllm_ascend/distributed/kv_transfer/kv_pool/simple_cpu_offload/simple_cpu_offload_connector.py",
        )
    ].decode()
    ascend_worker = source_bytes[
        ("vllm_ascend", "vllm_ascend/simple_kv_offload/worker.py")
    ].decode()
    copy_backend = source_bytes[
        ("vllm_ascend", "vllm_ascend/simple_kv_offload/copy_backend.py")
    ].decode()
    mem_ops = source_bytes[
        ("vllm_ascend", "vllm_ascend/simple_kv_offload/npu_mem_ops.py")
    ].decode()

    supports_hma = (
        "class SimpleCPUOffloadConnector(KVConnectorBase_V1, SupportsHMA)"
        in connector
        and "request_finished_all_groups" in connector
    )
    hybrid = all(
        marker in manager
        for marker in (
            "FullAttentionSpec",
            "SlidingWindowSpec",
            "MambaSpec",
            "kv_cache_groups",
            "num_stored_blocks: list[int]",
        )
    )
    override = all(
        marker in registration
        for marker in (
            '"SimpleCPUOffloadConnector"',
            '"AscendSimpleCPUOffloadConnector"',
            "vllm_ascend.distributed.kv_transfer.kv_pool.simple_cpu_offload",
        )
    ) and "class AscendSimpleCPUOffloadConnector(SimpleCPUOffloadConnector)" in ascend_connector
    npu_backend = all(
        (
            "SimpleCPUOffloadNPUWorker" in ascend_worker,
            "NPUDmaCopyBackend" in ascend_worker,
            "DIRECTION_D2H" in copy_backend,
            "DIRECTION_H2D" in copy_backend,
            "swap_blocks_batch" in mem_ops,
        )
    )
    candidate = source_hash_gate and supports_hma and hybrid and override and npu_backend
    return {
        "audit_grade": (
            CANDIDATE_GRADE
            if candidate
            else "blocked_p8_2_k1a_simple_cpu_offload_source_drift"
        ),
        "vllm_commit": VLLM_COMMIT,
        "vllm_ascend_commit": VLLM_ASCEND_COMMIT,
        "source_hash_gate": source_hash_gate,
        "source_inventory": inventory,
        "ascend_connector_override_present": override,
        "supports_hma_present": supports_hma,
        "hybrid_multi_group_source_support_present": hybrid,
        "npu_d2h_h2d_backend_present": npu_backend,
        "formal_k1a_runtime_allowed_after_server_probe": candidate,
        "runtime_evidence_accepted": False,
        "performance_reference_accepted": False,
        "npu_started": False,
        "vllm_server_started": False,
        "model_request_sent": False,
    }


def inspect_frozen_sources(vllm_repo: Path, vllm_ascend_repo: Path) -> dict[str, Any]:
    repos = {"vllm": vllm_repo, "vllm_ascend": vllm_ascend_repo}
    commits = {"vllm": VLLM_COMMIT, "vllm_ascend": VLLM_ASCEND_COMMIT}
    inventory: list[dict[str, Any]] = []
    source_bytes: dict[tuple[str, str], bytes] = {}
    source_hash_gate = True
    for target, expected_by_path in EXPECTED_SOURCES.items():
        repo = repos[target]
        commit = commits[target]
        _git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
        for relative_path, expected in expected_by_path.items():
            expected_oid, expected_bytes, expected_sha = expected
            payload = _git(repo, "show", f"{commit}:{relative_path}")
            oid = _git(repo, "rev-parse", f"{commit}:{relative_path}").decode().strip()
            sha256 = hashlib.sha256(payload).hexdigest()
            matched = (
                oid == expected_oid
                and len(payload) == expected_bytes
                and sha256 == expected_sha
            )
            source_hash_gate = source_hash_gate and matched
            source_bytes[(target, relative_path)] = payload
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
    return _evaluate(source_bytes, inventory, source_hash_gate)


def inspect_installed_sources(
    vllm_root: Path, vllm_ascend_root: Path
) -> dict[str, Any]:
    roots = {"vllm": vllm_root, "vllm_ascend": vllm_ascend_root}
    inventory: list[dict[str, Any]] = []
    source_bytes: dict[tuple[str, str], bytes] = {}
    source_hash_gate = True
    for target, expected_by_path in EXPECTED_SOURCES.items():
        for relative_path, expected in expected_by_path.items():
            if relative_path.startswith("tests/"):
                continue
            expected_oid, expected_bytes, expected_sha = expected
            path = roots[target] / relative_path
            payload = path.read_bytes()
            sha256 = hashlib.sha256(payload).hexdigest()
            matched = len(payload) == expected_bytes and sha256 == expected_sha
            source_hash_gate = source_hash_gate and matched
            source_bytes[(target, relative_path)] = payload
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
    return _evaluate(source_bytes, inventory, source_hash_gate)


RUNTIME_PROBE = r'''
import inspect
import json

result = {}
try:
    from vllm.config import KVTransferConfig
    from vllm.distributed.kv_transfer.kv_connector.factory import KVConnectorFactory
    from vllm.distributed.kv_transfer.kv_connector.v1.simple_cpu_offload_connector import SimpleCPUOffloadConnector
    from vllm_ascend.distributed.kv_transfer import register_connector

    config = KVTransferConfig(
        kv_connector="SimpleCPUOffloadConnector",
        kv_role="kv_both",
        kv_connector_extra_config={
            "cpu_bytes_to_use": 274877906944,
            "cpu_bytes_to_use_per_rank": 34359738368,
            "lazy_offload": False,
        },
    )
    register_connector()
    connector_class = KVConnectorFactory.get_connector_class_by_name(
        "SimpleCPUOffloadConnector"
    )
    from vllm_ascend.distributed.kv_transfer.kv_pool.simple_cpu_offload.simple_cpu_offload_connector import AscendSimpleCPUOffloadConnector
    from vllm_ascend.simple_kv_offload.worker import SimpleCPUOffloadNPUWorker
    from vllm_ascend.simple_kv_offload.copy_backend import NPUDmaCopyBackend

    poll_method_owner = next(
        cls.__module__ + "." + cls.__name__
        for cls in SimpleCPUOffloadNPUWorker.__mro__
        if "_poll_stream_events" in cls.__dict__
    )

    result.update({
        "kv_transfer_config": {
            "kv_connector": config.kv_connector,
            "kv_role": config.kv_role,
            "kv_connector_extra_config": config.kv_connector_extra_config,
        },
        "registry_module": connector_class.__module__,
        "registry_class": connector_class.__name__,
        "connector_import": (
            "success" if connector_class is AscendSimpleCPUOffloadConnector else "wrong_class"
        ),
        "worker_import": (
            "success" if SimpleCPUOffloadNPUWorker.__name__ else "failed"
        ),
        "copy_backend_import": (
            "success" if NPUDmaCopyBackend.__name__ else "failed"
        ),
        "poll_method_callable": callable(
            getattr(SimpleCPUOffloadNPUWorker, "_poll_stream_events", None)
        ),
        "poll_method_owner": poll_method_owner,
        "poll_method_parameters": list(
            inspect.signature(SimpleCPUOffloadNPUWorker._poll_stream_events).parameters
        ),
        "launch_copy_parameters": list(
            inspect.signature(NPUDmaCopyBackend.launch_copy).parameters
        ),
        "ascend_connector_inherits_upstream": issubclass(
            AscendSimpleCPUOffloadConnector, SimpleCPUOffloadConnector
        ),
    })
except Exception as exc:
    result["probe_error"] = {
        "error_type": type(exc).__name__,
        "error": str(exc),
    }

result.update({
    "npu_started": False,
    "vllm_server_started": False,
    "model_request_sent": False,
})
print("P8K1A_RUNTIME_JSON=" + json.dumps(result, sort_keys=True))
'''


def inspect_runtime_imports(runtime_python: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [str(runtime_python), "-c", RUNTIME_PROBE],
        text=True,
        capture_output=True,
        check=False,
    )
    marker = "P8K1A_RUNTIME_JSON="
    payload_line = next(
        (
            line
            for line in reversed(completed.stdout.splitlines())
            if line.startswith(marker)
        ),
        None,
    )
    payload = json.loads(payload_line[len(marker) :]) if payload_line else None
    return {
        "subprocess_exit": completed.returncode,
        "probe": payload,
        "stdout_without_payload": "\n".join(
            line
            for line in completed.stdout.splitlines()
            if not line.startswith(marker)
        ),
        "stderr": completed.stderr,
        "npu_started": False,
        "vllm_server_started": False,
        "model_request_sent": False,
    }


def inspect_accepted_capacity_provenance(
    geometry_summary: Path,
    rendezvous_marker: Path,
    allocator_summary: Path,
) -> dict[str, Any]:
    geometry = json.loads(geometry_summary.read_text(encoding="utf-8"))
    rendezvous = json.loads(rendezvous_marker.read_text(encoding="utf-8"))
    allocator = json.loads(allocator_summary.read_text(encoding="utf-8"))
    expected_ranks = list(range(8))

    checks = (
        (
            geometry.get("schema_version")
            == "p8_2_k1a_r2_geometry_summary_v1",
            "geometry summary schema mismatch",
        ),
        (
            rendezvous.get("schema_version")
            == "p8_2_k1a_r2_geometry_rendezvous_v1",
            "rendezvous marker schema mismatch",
        ),
        (
            allocator.get("schema_version")
            == "p8_2_k1a_r2_allocator_envelope_v1",
            "allocator summary schema mismatch",
        ),
        (
            geometry.get("probe_run_id") == rendezvous.get("probe_run_id")
            and bool(geometry.get("probe_run_id")),
            "geometry and rendezvous probe_run_id mismatch",
        ),
        (geometry.get("rank_count") == 8, "geometry rank_count mismatch"),
        (
            geometry.get("rank_coverage") == expected_ranks,
            "geometry rank coverage mismatch",
        ),
        (
            rendezvous.get("rank_coverage") == expected_ranks,
            "rendezvous rank coverage mismatch",
        ),
        (rendezvous.get("world_size") == 8, "rendezvous world_size mismatch"),
        (
            rendezvous.get("geometry_parity_exact") is True,
            "rendezvous geometry parity is not exact",
        ),
        (
            geometry.get("geometry_gate_ok") is True
            and geometry.get("rendezvous_gate_ok") is True,
            "geometry acceptance gate is not green",
        ),
        (
            geometry.get("allocation_attempted") is False
            and rendezvous.get("allocation_attempted") is False,
            "geometry probe attempted allocation",
        ),
        (
            geometry.get("block_size_tokens") == 128
            and geometry.get("required_restore_tokens") == 16384
            and geometry.get("required_cpu_blocks") == 128,
            "accepted restore geometry mismatch",
        ),
        (
            geometry.get("total_bytes_per_block") == 3364096
            and geometry.get("required_capacity_bytes_per_rank") == 430604288
            and geometry.get("required_capacity_bytes_total") == 3444834304,
            "accepted geometry capacity mismatch",
        ),
        (
            allocator.get("acl_pinned_host_allocator_gate_ok") is True
            and allocator.get("required_cpu_blocks") == 128
            and allocator.get("highest_eight_rank_clean_blocks") == 128
            and allocator.get("candidate_cpu_bytes_per_rank") == 430604288
            and allocator.get("candidate_cpu_bytes_total") == 3444834304
            and allocator.get("capacity_candidate_ready") is True,
            "accepted allocator capacity mismatch",
        ),
        (
            allocator.get("grade")
            == "candidate_ready_p8_2_k1a_r2_allocator_capacity",
            "allocator grade mismatch",
        ),
        (
            geometry.get("formal_lifecycle_authorized") is False
            and allocator.get("formal_lifecycle_allowed") is False
            and allocator.get("formal_lifecycle_requires_new_handoff") is True,
            "R2 formal lifecycle boundary mismatch",
        ),
    )
    for condition, message in checks:
        if not condition:
            raise ValueError(message)

    return {
        "schema_version": "p8_2_k1a_r3_r1_accepted_capacity_provenance_v1",
        "accepted_r2_capacity_provenance_gate": "pass",
        "probe_run_id": geometry["probe_run_id"],
        "rank_coverage": expected_ranks,
        "world_size": 8,
        "geometry_parity_exact": True,
        "block_size_tokens": 128,
        "required_restore_tokens": 16384,
        "required_cpu_blocks": 128,
        "accepted_capacity_bytes_per_rank": 430604288,
        "accepted_capacity_bytes_total": 3444834304,
        "allocation_attempted": False,
    }


def _emit(value: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit the frozen P8.2-K1A SimpleCPUOffload candidate without NPU use."
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
    provenance = subparsers.add_parser("accepted-capacity-provenance")
    provenance.add_argument("--geometry-summary", type=Path, required=True)
    provenance.add_argument("--rendezvous-marker", type=Path, required=True)
    provenance.add_argument("--allocator-summary", type=Path, required=True)
    provenance.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "source-audit":
        result = inspect_frozen_sources(args.vllm_repo, args.vllm_ascend_repo)
    elif args.command == "installed-source-audit":
        result = inspect_installed_sources(args.vllm_root, args.vllm_ascend_root)
    elif args.command == "runtime-import-probe":
        result = inspect_runtime_imports(args.runtime_python)
    else:
        result = inspect_accepted_capacity_provenance(
            args.geometry_summary,
            args.rendezvous_marker,
            args.allocator_summary,
        )
    _emit(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
