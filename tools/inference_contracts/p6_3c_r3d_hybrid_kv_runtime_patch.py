"""R3D loader for frozen hybrid-KV semantics on the live Ascend layout.

The overlay builder publishes this source under the historical module name
``p6_3b_r2_hybrid_kv_runtime_patch`` because the frozen Ascend bootstrap imports
that name.  R3D extends the original deferred loader only by reconciling the
exact-type manager map after vLLM-Ascend replaces the public MLA spec classes.
"""

from __future__ import annotations

import os
from typing import Any

try:
    import p6_3b_hybrid_kv_runtime_impl as _impl
except ModuleNotFoundError:  # Local tests import from the repository.
    from tools.inference_contracts import (
        p6_3b_r1_hybrid_kv_runtime_patch as _impl,
    )


ENABLE_ENV = "P6_3B_R2_ENABLE_HYBRID_KV_PATCH"
DIAGNOSTIC_ENV = "P6_3B_R2_HYBRID_KV_DIAGNOSTIC_PATH"
PATCH_INSTALLED = False


def align_ascend_manager_resolution(
    *,
    manager_module: Any | None = None,
    interface_module: Any | None = None,
) -> dict[str, Any]:
    """Register post-replacement Ascend specs in a stale vLLM manager map."""

    if manager_module is None:
        import vllm.v1.core.single_type_kv_cache_manager as manager_module
    if interface_module is None:
        from vllm_ascend.patch.platform import (
            patch_kv_cache_interface as interface_module,
        )

    ascend_mla = interface_module.AscendMLAAttentionSpec
    ascend_sliding = interface_module.AscendSlidingWindowMLASpec
    stale_mla = manager_module.MLAAttentionSpec
    stale_sliding = manager_module.SlidingWindowMLASpec
    mapping = manager_module.spec_manager_map

    if stale_mla not in mapping and ascend_mla not in mapping:
        raise RuntimeError("no manager registered for MLA attention spec")
    if stale_sliding not in mapping and ascend_sliding not in mapping:
        raise RuntimeError("no manager registered for sliding-window MLA spec")

    mla_manager = mapping.get(ascend_mla, mapping.get(stale_mla))
    sliding_manager = mapping.get(ascend_sliding, mapping.get(stale_sliding))
    if mla_manager is None or sliding_manager is None:
        raise RuntimeError("Ascend KV manager class resolution returned None")

    mapping[ascend_mla] = mla_manager
    mapping[ascend_sliding] = sliding_manager
    manager_module.MLAAttentionSpec = ascend_mla
    manager_module.SlidingWindowMLASpec = ascend_sliding
    return {
        "stale_mla_spec": getattr(stale_mla, "__name__", repr(stale_mla)),
        "stale_sliding_spec": getattr(
            stale_sliding, "__name__", repr(stale_sliding)
        ),
        "ascend_mla_spec": ascend_mla.__name__,
        "ascend_sliding_spec": ascend_sliding.__name__,
        "mla_manager": getattr(mla_manager, "__name__", repr(mla_manager)),
        "sliding_manager": getattr(
            sliding_manager, "__name__", repr(sliding_manager)
        ),
        "mapping_size": len(mapping),
    }


def require_ascend_manager_resolution(
    *,
    manager_module: Any | None = None,
    interface_module: Any | None = None,
) -> dict[str, bool]:
    """Fail unless both post-replacement Ascend specs resolve exactly."""

    if manager_module is None:
        import vllm.v1.core.single_type_kv_cache_manager as manager_module
    if interface_module is None:
        from vllm_ascend.patch.platform import (
            patch_kv_cache_interface as interface_module,
        )

    ascend_mla = interface_module.AscendMLAAttentionSpec
    ascend_sliding = interface_module.AscendSlidingWindowMLASpec
    mapping = manager_module.spec_manager_map
    snapshot = {
        "ascend_mla_exact_key_registered": ascend_mla in mapping,
        "ascend_sliding_window_mla_exact_key_registered": ascend_sliding in mapping,
        "manager_mla_alias_is_ascend": manager_module.MLAAttentionSpec
        is ascend_mla,
        "manager_sliding_window_mla_alias_is_ascend": (
            manager_module.SlidingWindowMLASpec is ascend_sliding
        ),
    }
    if not all(snapshot.values()):
        raise RuntimeError(
            f"Ascend KV spec manager resolution is incomplete: {snapshot}"
        )
    return snapshot


def install_runtime_patch() -> None:
    """Install frozen semantics, then reconcile the live exact-type map."""

    global PATCH_INSTALLED
    if PATCH_INSTALLED:
        return
    if os.environ.get(ENABLE_ENV) != "1":
        raise RuntimeError(f"{ENABLE_ENV}=1 is required")
    diagnostic_path = os.environ.get(DIAGNOSTIC_ENV)
    if diagnostic_path:
        os.environ[_impl.DIAGNOSTIC_ENV] = diagnostic_path
    _impl.install_runtime_patch()
    alignment = align_ascend_manager_resolution()
    resolution = require_ascend_manager_resolution()
    _impl._append_diagnostic(  # noqa: SLF001 - task-local implementation
        {
            "event": "deferred_import_order_verified",
            "manager_alignment": alignment,
            "manager_resolution": resolution,
        }
    )
    PATCH_INSTALLED = bool(_impl.PATCH_INSTALLED)
