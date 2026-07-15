"""Task-local frozen-vLLM compatibility patch for P6.3B-R1.

The server runner copies this file to ``sitecustomize.py`` in its task-local
overlay.  It is inert unless ``P6_3B_R1_ENABLE_HYBRID_KV_PATCH=1``.  When
enabled, it validates the exact frozen vLLM sources before installing the two
write-path semantics needed by vLLM PR #44082.  The vLLM-Ascend manager
propagation half is applied separately to the copied plugin package.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


ENABLE_ENV = "P6_3B_R1_ENABLE_HYBRID_KV_PATCH"
DIAGNOSTIC_ENV = "P6_3B_R1_HYBRID_KV_DIAGNOSTIC_PATH"
EXPECTED_SOURCE_SHA256 = {
    "vllm.v1.core.single_type_kv_cache_manager": (
        "d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1"
    ),
    "vllm.v1.core.kv_cache_coordinator": (
        "a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89"
    ),
}
PATCH_INSTALLED = False
_DIAGNOSTIC_KEYS: set[tuple[Any, ...]] = set()


def _cdiv(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


def eagle_reachable_block_mask(
    *,
    start_block: int,
    end_block: int,
    alignment_tokens: int,
    block_size: int,
    sliding_window: int,
    use_eagle: bool,
) -> list[bool] | None:
    """Return the SWA write mask aligned with the EAGLE read boundary."""

    if alignment_tokens <= block_size:
        return None
    per_segment = alignment_tokens // block_size
    needed = _cdiv(sliding_window - 1, block_size) + int(use_eagle)
    if needed >= per_segment:
        return None
    shift = int(use_eagle)
    return [
        index >= shift
        and (index - shift) % per_segment >= per_segment - needed
        for index in range(start_block, end_block)
    ]


def cache_target_tokens(
    *,
    num_computed_tokens: int,
    alignment_tokens: int,
    block_size: int,
    use_eagle: bool,
) -> int:
    """Clamp writes to a hit boundary plus one EAGLE lookahead block."""

    aligned = num_computed_tokens // alignment_tokens * alignment_tokens
    if use_eagle and aligned > 0:
        return min(num_computed_tokens, aligned + block_size)
    return aligned


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_diagnostic(event: dict[str, Any]) -> None:
    destination = os.environ.get(DIAGNOSTIC_ENV)
    if not destination:
        return
    payload = json.dumps(
        {"pid": os.getpid(), **event},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)


def _record_once(key: tuple[Any, ...], event: dict[str, Any]) -> None:
    if key in _DIAGNOSTIC_KEYS:
        return
    _DIAGNOSTIC_KEYS.add(key)
    _append_diagnostic(event)


def _manager_snapshot(coordinator: Any) -> list[dict[str, Any]]:
    snapshots = []
    for group_id, manager in enumerate(coordinator.single_type_managers):
        spec = manager.kv_cache_spec
        snapshots.append(
            {
                "group_id": group_id,
                "manager_type": type(manager).__name__,
                "spec_type": type(spec).__name__,
                "block_size": int(manager.block_size),
                "spec_block_size": int(spec.block_size),
                "sliding_window": getattr(spec, "sliding_window", None),
                "compress_ratio": getattr(spec, "compress_ratio", None),
                "use_eagle": bool(getattr(manager, "use_eagle", False)),
            }
        )
    return snapshots


def install_runtime_patch() -> None:
    global PATCH_INSTALLED
    if PATCH_INSTALLED:
        return

    import vllm.v1.core.kv_cache_coordinator as coordinator_module
    import vllm.v1.core.single_type_kv_cache_manager as manager_module

    modules = {
        "vllm.v1.core.single_type_kv_cache_manager": manager_module,
        "vllm.v1.core.kv_cache_coordinator": coordinator_module,
    }
    source_evidence = {}
    for module_name, module in modules.items():
        source_path = Path(module.__file__).resolve()
        actual_sha256 = _sha256(source_path)
        expected_sha256 = EXPECTED_SOURCE_SHA256[module_name]
        source_evidence[module_name] = {
            "path": str(source_path),
            "sha256": actual_sha256,
            "expected_sha256": expected_sha256,
            "match": actual_sha256 == expected_sha256,
        }
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"frozen source mismatch for {module_name}: {actual_sha256}"
            )

    single_type_manager = manager_module.SingleTypeKVCacheManager
    sliding_window_manager = manager_module.SlidingWindowManager
    hybrid_coordinator = coordinator_module.HybridKVCacheCoordinator

    original_init = single_type_manager.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        self.use_eagle = False

    def patched_cache_block_mask(
        self: Any,
        num_cached_blocks: int,
        num_full_blocks: int,
        alignment_tokens: int,
    ) -> list[bool] | None:
        mask = eagle_reachable_block_mask(
            start_block=num_cached_blocks,
            end_block=num_full_blocks,
            alignment_tokens=alignment_tokens,
            block_size=int(self.block_size),
            sliding_window=int(self.sliding_window),
            use_eagle=bool(getattr(self, "use_eagle", False)),
        )
        if getattr(self, "use_eagle", False):
            _record_once(
                (
                    "eagle_reachable_mask",
                    type(self).__name__,
                    alignment_tokens,
                    self.block_size,
                    self.sliding_window,
                ),
                {
                    "event": "eagle_reachable_mask",
                    "manager_type": type(self).__name__,
                    "alignment_tokens": alignment_tokens,
                    "block_size": int(self.block_size),
                    "sliding_window": int(self.sliding_window),
                    "mask_is_sparse": mask is not None,
                },
            )
        return mask

    def patched_cache_blocks(
        self: Any,
        request: Any,
        num_computed_tokens: int,
    ) -> None:
        alignment_tokens = int(self.lcm_block_size)
        _record_once(
            ("coordinator_snapshot", id(self)),
            {
                "event": "coordinator_snapshot",
                "coordinator_type": type(self).__name__,
                "lcm_block_size": alignment_tokens,
                "scheduler_block_size": getattr(self, "scheduler_block_size", None),
                "eagle_group_ids": sorted(getattr(self, "eagle_group_ids", set())),
                "attention_groups": [
                    {
                        "spec_type": type(spec).__name__,
                        "group_ids": list(group_ids),
                        "manager_type": manager_class.__name__,
                    }
                    for spec, group_ids, manager_class in self.attention_groups
                ],
                "managers": _manager_snapshot(self),
                "prefix_cache_retention_interval": os.environ.get(
                    "VLLM_PREFIX_CACHE_RETENTION_INTERVAL"
                ),
            },
        )
        aligned = num_computed_tokens // alignment_tokens * alignment_tokens
        for manager in self.single_type_managers:
            target = cache_target_tokens(
                num_computed_tokens=num_computed_tokens,
                alignment_tokens=alignment_tokens,
                block_size=int(manager.block_size),
                use_eagle=bool(getattr(manager, "use_eagle", False)),
            )
            if target > aligned:
                _record_once(
                    (
                        "eagle_lookahead_cache_target",
                        type(manager).__name__,
                        alignment_tokens,
                        manager.block_size,
                    ),
                    {
                        "event": "eagle_lookahead_cache_target",
                        "manager_type": type(manager).__name__,
                        "alignment_tokens": alignment_tokens,
                        "block_size": int(manager.block_size),
                        "aligned_tokens": aligned,
                        "cache_target_tokens": target,
                    },
                )
            manager.cache_blocks(
                request,
                target,
                alignment_tokens=alignment_tokens,
            )

    patched_init._p6_3b_r1_hybrid_kv_patch = True  # type: ignore[attr-defined]
    patched_cache_block_mask._p6_3b_r1_hybrid_kv_patch = True  # type: ignore[attr-defined]
    patched_cache_blocks._p6_3b_r1_hybrid_kv_patch = True  # type: ignore[attr-defined]
    single_type_manager.__init__ = patched_init
    sliding_window_manager._cache_block_mask = patched_cache_block_mask
    hybrid_coordinator.cache_blocks = patched_cache_blocks
    PATCH_INSTALLED = True
    _append_diagnostic(
        {
            "event": "runtime_patch_installed",
            "source_evidence": source_evidence,
            "retention_interval": os.environ.get(
                "VLLM_PREFIX_CACHE_RETENTION_INTERVAL"
            ),
        }
    )


if os.environ.get(ENABLE_ENV) == "1":
    try:
        install_runtime_patch()
    except BaseException as error:  # fail closed even though sitecustomize is optional
        try:
            _append_diagnostic(
                {
                    "event": "runtime_patch_install_failed",
                    "error_type": type(error).__name__,
                    "error": str(error)[:2048],
                }
            )
        finally:
            os._exit(78)
