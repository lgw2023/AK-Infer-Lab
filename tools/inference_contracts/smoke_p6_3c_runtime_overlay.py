"""Zero-NPU import smoke for the task-local P6.3C runtime overlay."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any


EXPECTED_ACL_GRAPH_SHA256 = (
    "f81b08686b4e62daff5de4c795ce3eb80415a6eef133f82177876c7a3e18b0ad"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_smoke_evidence() -> dict[str, Any]:
    """Exercise the same deferred imports that precede the vLLM server."""

    import vllm_ascend.patch.platform.patch_kv_cache_interface  # noqa: F401
    import p6_3b_r2_hybrid_kv_runtime_patch as hybrid_patch
    from vllm_ascend.compilation import acl_graph

    resolution = hybrid_patch.require_ascend_manager_resolution()
    acl_graph_path = Path(acl_graph.__file__).resolve(strict=True)
    acl_graph_sha256 = _sha256(acl_graph_path)
    guard_callable_name = "update_full_graph_params"
    guard_callable = getattr(acl_graph, guard_callable_name, None)
    if not callable(guard_callable):
        raise RuntimeError(
            f"acl_graph.{guard_callable_name} is required by the published overlay"
        )
    graph_source = inspect.getsource(guard_callable)
    graph_guard_present = (
        'hasattr(impl_cls, "update_graph_params")' in graph_source
    )
    evidence = {
        "schema": "p6_3c_runtime_overlay_import_smoke_v1",
        "hybrid_kv_patch_installed": bool(hybrid_patch.PATCH_INSTALLED),
        "ascend_manager_resolution": resolution,
        "ascend_manager_resolution_complete": all(resolution.values()),
        "acl_graph_path": str(acl_graph_path),
        "acl_graph_sha256": acl_graph_sha256,
        "acl_graph_expected_sha256": EXPECTED_ACL_GRAPH_SHA256,
        "acl_graph_sha256_exact": acl_graph_sha256
        == EXPECTED_ACL_GRAPH_SHA256,
        "acl_graph_guard_callable": guard_callable_name,
        "acl_graph_update_full_graph_params_guard_present": graph_guard_present,
        # Compatibility alias retained for R3D result readers.  The field
        # describes the guard semantics, not a module-level callable name.
        "acl_graph_update_params_guard_present": graph_guard_present,
        "npu_operation_requested": False,
    }
    evidence["runtime_overlay_import_smoke_complete"] = all(
        (
            evidence["hybrid_kv_patch_installed"],
            evidence["ascend_manager_resolution_complete"],
            evidence["acl_graph_sha256_exact"],
            evidence["acl_graph_update_params_guard_present"],
        )
    )
    if not evidence["runtime_overlay_import_smoke_complete"]:
        raise RuntimeError(f"runtime overlay import smoke failed: {evidence}")
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    evidence = collect_smoke_evidence()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("runtime_overlay_import_smoke_complete=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
