"""Deferred loader for the frozen P6.3B hybrid-KV runtime repair.

The server copies this module and the frozen R1 implementation into the
task-local overlay.  The Ascend KV interface patch calls
``install_runtime_patch`` only after it has installed the Ascend MLA spec
classes.  Importing this module alone is intentionally inert.
"""

from __future__ import annotations

import os
from typing import Any

try:
    import p6_3b_hybrid_kv_runtime_impl as _impl
except ModuleNotFoundError:  # Local contract tests import from the repository.
    from tools.inference_contracts import (
        p6_3b_r1_hybrid_kv_runtime_patch as _impl,
    )


ENABLE_ENV = "P6_3B_R2_ENABLE_HYBRID_KV_PATCH"
DIAGNOSTIC_ENV = "P6_3B_R2_HYBRID_KV_DIAGNOSTIC_PATH"
PATCH_INSTALLED = False


def require_ascend_manager_resolution(
    *,
    manager_module: Any | None = None,
    interface_module: Any | None = None,
) -> dict[str, bool]:
    """Fail unless frozen vLLM registered both post-replacement Ascend specs."""

    if manager_module is None:
        import vllm.v1.core.single_type_kv_cache_manager as manager_module
    if interface_module is None:
        import vllm_ascend.patch.platform.patch_kv_cache_interface as interface_module

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
    """Install the frozen implementation when called by the Ascend bootstrap."""

    global PATCH_INSTALLED
    if PATCH_INSTALLED:
        return
    if os.environ.get(ENABLE_ENV) != "1":
        raise RuntimeError(f"{ENABLE_ENV}=1 is required")
    diagnostic_path = os.environ.get(DIAGNOSTIC_ENV)
    if diagnostic_path:
        os.environ[_impl.DIAGNOSTIC_ENV] = diagnostic_path
    _impl.install_runtime_patch()
    resolution = require_ascend_manager_resolution()
    _impl._append_diagnostic(  # noqa: SLF001 - frozen task-local implementation
        {
            "event": "deferred_import_order_verified",
            "manager_resolution": resolution,
        }
    )
    PATCH_INSTALLED = bool(_impl.PATCH_INSTALLED)
