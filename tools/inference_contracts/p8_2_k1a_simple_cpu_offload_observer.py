from __future__ import annotations

from functools import wraps
import json
import os
from pathlib import Path
import time
from typing import Any


TRACE_ENV = "P8_2_K1A_TRANSFER_TRACE_DIR"
ACTIVE_ROLE_PATH_ENV = "P8_2_K1A_H2D_ACTIVE_ROLE_PATH"
REPAIR_ENABLE_ENV = "P8_2_K1A_ENABLE_COMPRESS_AWARE_PAIRING_REPAIR"
EXPECTED_MANAGER_SHA256 = (
    "fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b"
)


def _active_contract_role() -> str | None:
    raw_path = os.environ.get(ACTIVE_ROLE_PATH_ENV)
    if not raw_path:
        return None
    try:
        value = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    role = value.get("role") if isinstance(value, dict) else None
    return str(role) if role else None


def _emit(event: str, **fields: Any) -> None:
    trace_root = os.environ.get(TRACE_ENV)
    if not trace_root:
        return
    root = Path(trace_root)
    root.mkdir(parents=True, exist_ok=True)
    row = {
        "event": event,
        "pid": os.getpid(),
        "rank": os.environ.get("RANK"),
        "local_rank": os.environ.get("LOCAL_RANK"),
        "timestamp_ns": time.time_ns(),
        **fields,
    }
    with (root / f"trace.{os.getpid()}.jsonl").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")


def _bounded_error_fields(error: BaseException) -> dict[str, str]:
    return {
        "error_type": type(error).__name__,
        "error_message": str(error).replace("\n", " ")[:1024],
    }


def _pending_non_null_block_count(pending: object | None) -> int:
    if pending is None:
        return 0
    cpu_hit_blocks = pending[0] if isinstance(pending, tuple) else pending
    try:
        return sum(
            1
            for group in cpu_hit_blocks
            for block in group
            if not getattr(block, "is_null", False)
        )
    except TypeError:
        return 0


def _as_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _cdiv(a: int, b: int) -> int:
    if b <= 0:
        return 0
    return -(-int(a) // int(b))


def _frozen_group_block_size(scheduler: Any, group_index: int) -> int | None:
    """Exact frozen update_state_after_alloc group block size (spec.block_size)."""

    try:
        groups = scheduler.cpu_kv_cache_config.kv_cache_groups
        return int(groups[group_index].kv_cache_spec.block_size)
    except Exception:
        return None


def _effective_group_block_size(scheduler: Any, group_index: int) -> int | None:
    """Frozen-aligned size used by R13 preflight (spec.block_size * cp)."""

    try:
        base = _frozen_group_block_size(scheduler, group_index)
        if base is None:
            return None
        cp = int(getattr(scheduler, "cp_world_size", 1) or 1)
        return int(base) * cp
    except Exception:
        return None


def _compress_aware_group_block_size(
    scheduler: Any, group_index: int
) -> tuple[int | None, str]:
    """Runtime physical tokens/block, including Ascend compress_ratio."""

    try:
        groups = scheduler.cpu_kv_cache_config.kv_cache_groups
        spec = groups[group_index].kv_cache_spec
        base = int(spec.block_size)
        cp = int(getattr(scheduler, "cp_world_size", 1) or 1)
        try:
            compress = max(1, int(getattr(spec, "compress_ratio", 1) or 1))
        except (TypeError, ValueError):
            compress = 1
        coordinator = getattr(scheduler, "cpu_coordinator", None)
        method = getattr(coordinator, "_get_effective_block_size", None)
        if callable(method):
            return int(method(spec)), "runtime_cpu_coordinator"
        if type(spec).__name__ == "MambaSpec":
            return base, "mamba_spec_block_size"
        return base * cp * compress, "observer_compress_aware_fallback"
    except Exception:
        return None, "unreadable"


def _manager_source_sha256() -> str:
    try:
        import vllm.v1.simple_kv_offload.manager as manager_module

        path = Path(manager_module.__file__).resolve()
        digest = __import__("hashlib").sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        return ""


def observe_update_pairing_geometry(
    scheduler: Any,
    blocks: Any,
    num_external_tokens: int,
    pending: object | None,
) -> dict[str, Any]:
    """Observe-only replica of frozen update pairing math; never mutates state."""

    out: dict[str, Any] = {
        "geometry_preflight_status": "skipped",
        "geometry_preflight_failure_class": "none",
        "fa_gidx": int(getattr(scheduler, "fa_gidx", -1) or -1),
        "fa_block_size": int(getattr(scheduler, "fa_block_size", 0) or 0),
        "num_cached_fa_blocks": 0,
        "num_computed_tokens_from_fa": 0,
        "total_computed_tokens_expected": 0,
        "gpu_group_count": 0,
        "pending_group_count": 0,
        "gpu_block_table_lens": [],
        "pending_block_counts": [],
        "pending_non_null_counts": [],
        "n_take_by_group": [],
        "gpu_ext_start_by_group": [],
        "first_alignment_failure_group_index": -1,
        "first_pairing_overflow_group_index": -1,
        "first_overflow_needed_index": -1,
        "first_overflow_gpu_len": -1,
        "predicted_transfer_pair_count": 0,
    }
    if pending is None or int(num_external_tokens) <= 0:
        out["geometry_preflight_status"] = "not_applicable"
        return out
    try:
        block_ids_by_group = blocks.get_block_ids()
        cpu_hit_blocks_full = pending[0] if isinstance(pending, tuple) else pending
        gpu_group_count = len(block_ids_by_group)
        pending_group_count = len(cpu_hit_blocks_full)
        out["gpu_group_count"] = gpu_group_count
        out["pending_group_count"] = pending_group_count
        out["gpu_block_table_lens"] = [len(ids) for ids in block_ids_by_group]
        out["pending_block_counts"] = [len(group) for group in cpu_hit_blocks_full]
        out["pending_non_null_counts"] = [
            sum(1 for block in group if not getattr(block, "is_null", False))
            for group in cpu_hit_blocks_full
        ]

        fa_gidx = int(getattr(scheduler, "fa_gidx", -1))
        fa_block_size = int(getattr(scheduler, "fa_block_size", 0) or 0)
        out["fa_gidx"] = fa_gidx
        out["fa_block_size"] = fa_block_size
        if 0 <= fa_gidx < len(getattr(blocks, "blocks", ()) or ()):
            fa_blocks = blocks.blocks[fa_gidx]
            num_cached_fa_blocks = sum(
                1 for blk in fa_blocks if getattr(blk, "block_hash", None) is not None
            )
        else:
            num_cached_fa_blocks = 0
        num_computed_tokens = num_cached_fa_blocks * fa_block_size
        total_computed_tokens = num_computed_tokens + int(num_external_tokens)
        out["num_cached_fa_blocks"] = num_cached_fa_blocks
        out["num_computed_tokens_from_fa"] = num_computed_tokens
        out["total_computed_tokens_expected"] = total_computed_tokens

        scheduler_block_size = int(getattr(scheduler, "block_size", 0) or 0)
        if scheduler_block_size <= 0 or int(num_external_tokens) // scheduler_block_size <= 0:
            out["geometry_preflight_status"] = "would_fail"
            out["geometry_preflight_failure_class"] = "blocks_to_load_assert"
            return out

        num_groups = min(gpu_group_count, pending_group_count)
        n_take_by_group: list[int] = []
        gpu_ext_start_by_group: list[int] = []
        predicted_pairs = 0
        for g in range(num_groups):
            g_block_size = _effective_group_block_size(scheduler, g)
            if g_block_size is None or g_block_size <= 0:
                out["geometry_preflight_status"] = "would_fail"
                out["geometry_preflight_failure_class"] = "group_block_size_unreadable"
                out["first_alignment_failure_group_index"] = g
                return out
            if int(num_external_tokens) % g_block_size != 0:
                out["geometry_preflight_status"] = "would_fail"
                out["geometry_preflight_failure_class"] = "alignment_assert"
                out["first_alignment_failure_group_index"] = g
                out["n_take_by_group"] = n_take_by_group
                out["gpu_ext_start_by_group"] = gpu_ext_start_by_group
                return out
            n_take_g = int(num_external_tokens) // g_block_size
            cpu_blocks_g = list(cpu_hit_blocks_full[g][:n_take_g])
            n_ext_g = len(cpu_blocks_g)
            n_take_by_group.append(n_take_g)
            if n_ext_g == 0:
                gpu_ext_start_by_group.append(0)
                continue
            n_computed_g = _cdiv(total_computed_tokens, g_block_size)
            gpu_ext_start = n_computed_g - n_ext_g
            gpu_ext_start_by_group.append(gpu_ext_start)
            group_gpu_ids = block_ids_by_group[g]
            gpu_len = len(group_gpu_ids)
            for i, cpu_blk in enumerate(cpu_blocks_g):
                if getattr(cpu_blk, "is_null", False):
                    continue
                needed = gpu_ext_start + i
                if needed < 0 or needed >= gpu_len:
                    out["geometry_preflight_status"] = "would_fail"
                    out["geometry_preflight_failure_class"] = (
                        "index_error_gpu_cpu_pairing"
                    )
                    out["first_pairing_overflow_group_index"] = g
                    out["first_overflow_needed_index"] = needed
                    out["first_overflow_gpu_len"] = gpu_len
                    out["n_take_by_group"] = n_take_by_group
                    out["gpu_ext_start_by_group"] = gpu_ext_start_by_group
                    out["predicted_transfer_pair_count"] = predicted_pairs
                    return out
                predicted_pairs += 1

        out["n_take_by_group"] = n_take_by_group
        out["gpu_ext_start_by_group"] = gpu_ext_start_by_group
        out["predicted_transfer_pair_count"] = predicted_pairs
        out["geometry_preflight_status"] = "ok"
        out["geometry_preflight_failure_class"] = "none"
        return out
    except Exception as error:  # pragma: no cover - defensive observer path
        out["geometry_preflight_status"] = "observer_geometry_failed"
        out["geometry_preflight_failure_class"] = type(error).__name__
        return out


def observe_compress_aware_pairing_geometry(
    scheduler: Any,
    blocks: Any,
    num_external_tokens: int,
    pending: object | None,
) -> dict[str, Any]:
    """Observe-only pairing math using compress-aware effective block sizes."""

    out: dict[str, Any] = {
        "compress_aware_geometry_status": "skipped",
        "compress_aware_geometry_failure_class": "none",
        "compress_aware_block_sizes": [],
        "compress_aware_block_size_sources": [],
        "compress_aware_fa_block_size": 0,
        "compress_aware_num_computed_tokens_from_fa": 0,
        "compress_aware_total_computed_tokens": 0,
        "compress_aware_n_take_by_group": [],
        "compress_aware_gpu_ext_start_by_group": [],
        "compress_aware_first_overflow_group_index": -1,
        "compress_aware_first_overflow_needed_index": -1,
        "compress_aware_first_overflow_gpu_len": -1,
        "compress_aware_predicted_transfer_pair_count": 0,
    }
    if pending is None or int(num_external_tokens) <= 0:
        out["compress_aware_geometry_status"] = "not_applicable"
        return out
    try:
        block_ids_by_group = blocks.get_block_ids()
        cpu_hit_blocks_full = pending[0] if isinstance(pending, tuple) else pending
        fa_gidx = int(getattr(scheduler, "fa_gidx", -1))
        fa_eff, fa_source = _compress_aware_group_block_size(scheduler, fa_gidx)
        if fa_eff is None or fa_eff <= 0:
            out["compress_aware_geometry_status"] = "would_fail"
            out["compress_aware_geometry_failure_class"] = "fa_block_size_unreadable"
            return out
        if 0 <= fa_gidx < len(getattr(blocks, "blocks", ()) or ()):
            fa_blocks = blocks.blocks[fa_gidx]
            num_cached_fa_blocks = sum(
                1 for blk in fa_blocks if getattr(blk, "block_hash", None) is not None
            )
        else:
            num_cached_fa_blocks = 0
        num_computed_tokens = num_cached_fa_blocks * int(fa_eff)
        total_computed_tokens = num_computed_tokens + int(num_external_tokens)
        out["compress_aware_fa_block_size"] = int(fa_eff)
        out["compress_aware_num_computed_tokens_from_fa"] = num_computed_tokens
        out["compress_aware_total_computed_tokens"] = total_computed_tokens

        scheduler_block_size = int(getattr(scheduler, "block_size", 0) or 0)
        if scheduler_block_size <= 0 or int(num_external_tokens) // scheduler_block_size <= 0:
            out["compress_aware_geometry_status"] = "would_fail"
            out["compress_aware_geometry_failure_class"] = "blocks_to_load_assert"
            return out

        num_groups = min(len(block_ids_by_group), len(cpu_hit_blocks_full))
        n_take_by_group: list[int] = []
        gpu_ext_start_by_group: list[int] = []
        block_sizes: list[int] = []
        sources: list[str] = [fa_source]
        predicted_pairs = 0
        for g in range(num_groups):
            g_block_size, source = _compress_aware_group_block_size(scheduler, g)
            sources.append(source)
            if g_block_size is None or g_block_size <= 0:
                out["compress_aware_geometry_status"] = "would_fail"
                out["compress_aware_geometry_failure_class"] = (
                    "group_block_size_unreadable"
                )
                out["compress_aware_block_sizes"] = block_sizes
                out["compress_aware_block_size_sources"] = sources
                return out
            block_sizes.append(int(g_block_size))
            if int(num_external_tokens) % int(g_block_size) != 0:
                out["compress_aware_geometry_status"] = "would_fail"
                out["compress_aware_geometry_failure_class"] = "alignment_assert"
                out["compress_aware_block_sizes"] = block_sizes
                out["compress_aware_block_size_sources"] = sources
                out["compress_aware_n_take_by_group"] = n_take_by_group
                out["compress_aware_gpu_ext_start_by_group"] = gpu_ext_start_by_group
                return out
            n_take_g = int(num_external_tokens) // int(g_block_size)
            cpu_blocks_g = list(cpu_hit_blocks_full[g][:n_take_g])
            n_ext_g = len(cpu_blocks_g)
            n_take_by_group.append(n_take_g)
            if n_ext_g == 0:
                gpu_ext_start_by_group.append(0)
                continue
            n_computed_g = _cdiv(total_computed_tokens, int(g_block_size))
            gpu_ext_start = n_computed_g - n_ext_g
            gpu_ext_start_by_group.append(gpu_ext_start)
            group_gpu_ids = block_ids_by_group[g]
            gpu_len = len(group_gpu_ids)
            for i, cpu_blk in enumerate(cpu_blocks_g):
                if getattr(cpu_blk, "is_null", False):
                    continue
                needed = gpu_ext_start + i
                if needed < 0 or needed >= gpu_len:
                    out["compress_aware_geometry_status"] = "would_fail"
                    out["compress_aware_geometry_failure_class"] = (
                        "index_error_gpu_cpu_pairing"
                    )
                    out["compress_aware_first_overflow_group_index"] = g
                    out["compress_aware_first_overflow_needed_index"] = needed
                    out["compress_aware_first_overflow_gpu_len"] = gpu_len
                    out["compress_aware_block_sizes"] = block_sizes
                    out["compress_aware_block_size_sources"] = sources
                    out["compress_aware_n_take_by_group"] = n_take_by_group
                    out["compress_aware_gpu_ext_start_by_group"] = (
                        gpu_ext_start_by_group
                    )
                    out["compress_aware_predicted_transfer_pair_count"] = (
                        predicted_pairs
                    )
                    return out
                predicted_pairs += 1

        out["compress_aware_block_sizes"] = block_sizes
        out["compress_aware_block_size_sources"] = sources
        out["compress_aware_n_take_by_group"] = n_take_by_group
        out["compress_aware_gpu_ext_start_by_group"] = gpu_ext_start_by_group
        out["compress_aware_predicted_transfer_pair_count"] = predicted_pairs
        out["compress_aware_geometry_status"] = "ok"
        out["compress_aware_geometry_failure_class"] = "none"
        return out
    except Exception as error:  # pragma: no cover - defensive observer path
        out["compress_aware_geometry_status"] = "observer_geometry_failed"
        out["compress_aware_geometry_failure_class"] = type(error).__name__
        return out


def repaired_update_state_after_alloc(
    scheduler: Any,
    request: Any,
    blocks: Any,
    num_external_tokens: int,
) -> None:
    """Task-local compress-aware clone of frozen update_state_after_alloc.

    Uses the same control flow and side effects as the frozen method, but
    substitutes compress-aware effective block sizes for per-group pairing.
    Does not edit installed site-packages.
    """

    from vllm.v1.simple_kv_offload.manager import (
        LoadRequestState,
        StoreRequestState,
        TransferMeta,
    )

    req_id = request.request_id
    block_ids_by_group = blocks.get_block_ids()
    num_groups = len(block_ids_by_group)

    if not scheduler._lazy_mode and req_id not in scheduler._reqs_to_store:
        scheduler._reqs_to_store[req_id] = StoreRequestState(
            request=request,
            block_ids=tuple([] for _ in range(num_groups)),
            num_stored_blocks=[0] * num_groups,
        )

    pending = scheduler._pending_cpu_hits.pop(req_id, None)
    if num_external_tokens == 0:
        if pending is not None:
            scheduler._free_pending_cpu_hit(pending)
        return
    if pending is None:
        return

    cpu_hit_blocks_full, _ = pending
    num_blocks_to_load = int(num_external_tokens) // int(scheduler.block_size)
    assert num_blocks_to_load > 0

    fa_gidx = int(scheduler.fa_gidx)
    fa_eff, _ = _compress_aware_group_block_size(scheduler, fa_gidx)
    if fa_eff is None or fa_eff <= 0:
        scheduler._free_pending_cpu_hit(pending)
        raise RuntimeError("compress-aware FA block size unreadable")
    num_cached_fa_blocks = sum(
        blk.block_hash is not None for blk in blocks.blocks[fa_gidx]
    )
    num_computed_tokens = num_cached_fa_blocks * int(fa_eff)
    total_computed_tokens = num_computed_tokens + int(num_external_tokens)

    cpu_hit_blocks: list[list[Any]] = []
    for g in range(num_groups):
        g_block_size, _ = _compress_aware_group_block_size(scheduler, g)
        if g_block_size is None or g_block_size <= 0:
            scheduler._free_pending_cpu_hit(pending)
            raise RuntimeError(f"compress-aware group {g} block size unreadable")
        assert int(num_external_tokens) % int(g_block_size) == 0, (
            f"num_external_tokens={num_external_tokens} not aligned to "
            f"group {g} compress-aware block_size={g_block_size}"
        )
        n_take_g = int(num_external_tokens) // int(g_block_size)
        cpu_hit_blocks.append(list(cpu_hit_blocks_full[g][:n_take_g]))

    gpu_block_ids: list[int] = []
    cpu_block_ids: list[int] = []
    cpu_blocks_to_touch: list[Any] = []
    for g in range(num_groups):
        cpu_blocks_g = cpu_hit_blocks[g]
        n_ext_g = len(cpu_blocks_g)
        if n_ext_g == 0:
            continue
        g_block_size, _ = _compress_aware_group_block_size(scheduler, g)
        assert g_block_size is not None and g_block_size > 0
        n_computed_g = _cdiv(total_computed_tokens, int(g_block_size))
        gpu_ext_start = n_computed_g - n_ext_g
        group_gpu_ids = block_ids_by_group[g]
        for i, cpu_blk in enumerate(cpu_blocks_g):
            if getattr(cpu_blk, "is_null", False):
                continue
            needed = gpu_ext_start + i
            if needed < 0 or needed >= len(group_gpu_ids):
                scheduler._free_pending_cpu_hit(pending)
                raise IndexError(
                    "compress-aware pairing overflow at "
                    f"group={g} needed={needed} gpu_len={len(group_gpu_ids)}"
                )
            gpu_block_ids.append(group_gpu_ids[needed])
            cpu_block_ids.append(cpu_blk.block_id)
            cpu_blocks_to_touch.append(cpu_blk)

    scheduler.cpu_block_pool.touch(cpu_blocks_to_touch)
    scheduler._free_pending_cpu_hit(pending)
    assert scheduler._gpu_block_pool is not None
    scheduler._gpu_block_pool.touch(
        [scheduler._gpu_block_pool.blocks[bid] for bid in gpu_block_ids]
    )
    assert scheduler._reqs_to_load.get(req_id) is None
    scheduler._reqs_to_load[req_id] = LoadRequestState(
        request=request,
        transfer_meta=TransferMeta(gpu_block_ids, cpu_block_ids),
    )


def classify_update_raise_subclass(update: dict[str, Any] | None) -> str:
    if update is None:
        return "none"
    if str(update.get("early_return_reason") or "") != "update_raised":
        return "none"
    error_type = str(update.get("error_type") or "")
    error_message = str(update.get("error_message") or "")
    preflight = str(update.get("geometry_preflight_failure_class") or "none")
    if (
        error_type == "IndexError"
        or preflight == "index_error_gpu_cpu_pairing"
        or _as_int(update.get("first_pairing_overflow_group_index"), -1) >= 0
    ):
        return "index_error_gpu_cpu_pairing"
    if error_type == "AssertionError" and (
        "not aligned" in error_message or preflight == "alignment_assert"
    ):
        return "alignment_assert"
    if error_type == "AssertionError" and preflight == "blocks_to_load_assert":
        return "blocks_to_load_assert"
    if error_type == "AssertionError" and (
        "gpu_block_pool" in error_message or "_gpu_block_pool" in error_message
    ):
        return "gpu_pool_assert"
    if error_type == "AssertionError":
        return "assertion_other"
    if error_type:
        return f"other_{error_type}"
    return "update_raised_without_error_fields"


def classify_restore_hit_to_load_gap(
    rows: list[dict[str, Any]],
    *,
    restore_request_suffix: str = "restore_follower",
) -> dict[str, Any]:
    """Classify the observe-only gap between CPU hit and H2D load schedule."""

    def _is_restore(row: dict[str, Any]) -> bool:
        return row.get("contract_role") == "restore_follower" or str(
            row.get("request_id", "")
        ).endswith(restore_request_suffix)

    hits = [
        row
        for row in rows
        if row.get("event") == "cpu_hit_matched"
        and _is_restore(row)
        and int(row.get("num_new_tokens") or 0) > 0
    ]
    allocs = [
        row
        for row in rows
        if row.get("event") == "allocate_slots_observed" and _is_restore(row)
    ]
    updates = [
        row
        for row in rows
        if row.get("event") == "update_state_after_alloc_observed"
        and _is_restore(row)
    ]
    loads = [
        row
        for row in rows
        if row.get("event") == "load_scheduled"
        and _is_restore(row)
        and int(row.get("block_count") or 0) > 0
    ]
    load_metas = [
        row
        for row in rows
        if row.get("event") == "connector_load_meta_observed"
        and _is_restore(row)
    ]
    hit = hits[-1] if hits else None
    alloc = allocs[-1] if allocs else None
    update = updates[-1] if updates else None
    load = loads[-1] if loads else None
    load_meta = load_metas[-1] if load_metas else None

    gap_class = "no_restore_cpu_hit"
    if hit is not None and load is not None:
        gap_class = "load_scheduled"
    elif hit is not None and alloc is not None and alloc.get("allocate_slots_ok") is False:
        gap_class = "allocate_slots_failed_after_hit"
    elif hit is not None and not updates:
        gap_class = "update_state_after_alloc_not_called_after_hit"
    elif hit is not None and update is not None:
        reason = str(update.get("early_return_reason") or "")
        if reason in {
            "num_external_zero",
            "pending_missing",
            "empty_transfer_after_null_filter",
            "update_raised",
            "success",
        }:
            gap_class = reason if reason != "success" else "load_registered_without_positive_blocks"
        else:
            gap_class = "update_observed_without_load"
    elif hit is not None:
        gap_class = "hit_without_alloc_or_update_evidence"

    raise_subclass = classify_update_raise_subclass(update)
    gpu_table_lens = list((update or {}).get("gpu_block_table_lens") or [])
    fa_gidx = _as_int((update or {}).get("fa_gidx"), -1)
    fa_table_len = (
        _as_int(gpu_table_lens[fa_gidx], 0)
        if 0 <= fa_gidx < len(gpu_table_lens)
        else 0
    )

    return {
        "schema_version": "p8_2_k1a_hit_to_load_gap_v3",
        "restore_cpu_hit_observed": hit is not None,
        "restore_cpu_hit_tokens_max": max(
            (_as_int(row.get("num_new_tokens"), 0) for row in hits),
            default=0,
        ),
        "restore_cpu_hit_is_async": (
            bool(hit.get("is_async")) if hit is not None else False
        ),
        "restore_allocate_slots_observed": alloc is not None,
        "restore_allocate_slots_ok": (
            alloc.get("allocate_slots_ok") is True if alloc is not None else False
        ),
        "restore_allocate_slots_none": (
            alloc.get("allocate_slots_ok") is False if alloc is not None else False
        ),
        "restore_num_external_tokens_at_alloc": _as_int(
            (alloc or {}).get("num_external_computed_tokens"), 0
        ),
        "restore_num_new_tokens_at_alloc": _as_int(
            (alloc or {}).get("num_new_tokens"), 0
        ),
        "restore_delay_cache_blocks_at_alloc": (
            (alloc or {}).get("delay_cache_blocks") is True
        ),
        "restore_update_after_alloc_called": update is not None,
        "restore_num_external_tokens_at_update": _as_int(
            (update or {}).get("num_external_tokens"), 0
        ),
        "restore_pending_present_at_update": (
            (update or {}).get("pending_present") is True
        ),
        "restore_pending_non_null_block_count": _as_int(
            (update or hit or {}).get("pending_non_null_block_count"), 0
        ),
        "restore_update_early_return_reason": str(
            (update or {}).get("early_return_reason") or "not_called"
        ),
        "restore_update_error_type": str((update or {}).get("error_type") or ""),
        "restore_update_error_message": str(
            (update or {}).get("error_message") or ""
        )[:512],
        "restore_update_raise_subclass": raise_subclass,
        "restore_geometry_preflight_status": str(
            (update or {}).get("geometry_preflight_status") or "missing"
        ),
        "restore_geometry_preflight_failure_class": str(
            (update or {}).get("geometry_preflight_failure_class") or "none"
        ),
        "restore_fa_gidx": fa_gidx,
        "restore_fa_block_size": _as_int((update or {}).get("fa_block_size"), 0),
        "restore_num_cached_fa_blocks": _as_int(
            (update or {}).get("num_cached_fa_blocks"), 0
        ),
        "restore_num_computed_tokens_from_fa": _as_int(
            (update or {}).get("num_computed_tokens_from_fa"), 0
        ),
        "restore_total_computed_tokens_expected": _as_int(
            (update or {}).get("total_computed_tokens_expected"), 0
        ),
        "restore_gpu_group_count": _as_int((update or {}).get("gpu_group_count"), 0),
        "restore_pending_group_count": _as_int(
            (update or {}).get("pending_group_count"), 0
        ),
        "restore_gpu_block_table_lens": gpu_table_lens,
        "restore_pending_block_counts": list(
            (update or {}).get("pending_block_counts") or []
        ),
        "restore_pending_non_null_counts": list(
            (update or {}).get("pending_non_null_counts") or []
        ),
        "restore_n_take_by_group": list((update or {}).get("n_take_by_group") or []),
        "restore_gpu_ext_start_by_group": list(
            (update or {}).get("gpu_ext_start_by_group") or []
        ),
        "restore_gpu_block_table_len_fa": fa_table_len,
        "restore_first_alignment_failure_group_index": _as_int(
            (update or {}).get("first_alignment_failure_group_index"), -1
        ),
        "restore_first_pairing_overflow_group_index": _as_int(
            (update or {}).get("first_pairing_overflow_group_index"), -1
        ),
        "restore_first_overflow_needed_index": _as_int(
            (update or {}).get("first_overflow_needed_index"), -1
        ),
        "restore_first_overflow_gpu_len": _as_int(
            (update or {}).get("first_overflow_gpu_len"), -1
        ),
        "restore_predicted_transfer_pair_count": _as_int(
            (update or {}).get("predicted_transfer_pair_count"), 0
        ),
        "restore_pairing_repair_enabled": (
            (update or {}).get("pairing_repair_enabled") is True
        ),
        "restore_pairing_repair_eligible": (
            (update or {}).get("pairing_repair_eligible") is True
        ),
        "restore_pairing_repair_applied": (
            (update or {}).get("pairing_repair_applied") is True
        ),
        "restore_pairing_repair_skip_reason": str(
            (update or {}).get("pairing_repair_skip_reason") or "none"
        ),
        "restore_manager_source_sha_matched": (
            (update or {}).get("manager_source_sha_matched") is True
        ),
        "restore_compress_aware_geometry_status": str(
            (update or {}).get("compress_aware_geometry_status") or "missing"
        ),
        "restore_compress_aware_geometry_failure_class": str(
            (update or {}).get("compress_aware_geometry_failure_class") or "none"
        ),
        "restore_compress_aware_block_sizes": list(
            (update or {}).get("compress_aware_block_sizes") or []
        ),
        "restore_compress_aware_n_take_by_group": list(
            (update or {}).get("compress_aware_n_take_by_group") or []
        ),
        "restore_compress_aware_gpu_ext_start_by_group": list(
            (update or {}).get("compress_aware_gpu_ext_start_by_group") or []
        ),
        "restore_compress_aware_predicted_transfer_pair_count": _as_int(
            (update or {}).get("compress_aware_predicted_transfer_pair_count"), 0
        ),
        "restore_entered_reqs_to_load": (
            (update or {}).get("entered_reqs_to_load") is True
        ),
        "restore_transfer_gpu_block_count": _as_int(
            (update or load or {}).get("gpu_block_ids_count")
            if (update or load or {}).get("gpu_block_ids_count") is not None
            else (load or {}).get("block_count"),
            0,
        ),
        "restore_transfer_cpu_block_count": _as_int(
            (update or {}).get("cpu_block_ids_count"), 0
        ),
        "restore_null_cpu_blocks_skipped": _as_int(
            (update or {}).get("null_cpu_blocks_skipped"), 0
        ),
        "restore_load_scheduled": load is not None,
        "restore_connector_load_meta_observed": load_meta is not None,
        "restore_connector_load_event_ready": (
            (load_meta or {}).get("load_event_ready") is True
        ),
        "restore_connector_load_gpu_block_count": _as_int(
            (load_meta or {}).get("load_gpu_block_count"), 0
        ),
        "restore_hit_to_load_gap_class": gap_class,
        "raw_hash_values_retained": False,
        "request_ids_retained": False,
        "block_ids_retained": False,
    }


def install_p8_2_k1a_simple_cpu_offload_observer() -> None:
    from vllm.v1.core.kv_cache_manager import KVCacheManager
    from vllm.v1.simple_kv_offload.manager import SimpleCPUOffloadScheduler
    from vllm_ascend.simple_kv_offload import copy_backend as copy_backend_module
    from vllm_ascend.simple_kv_offload.copy_backend import NPUDmaCopyBackend
    from vllm_ascend.simple_kv_offload.worker import SimpleCPUOffloadNPUWorker

    if getattr(SimpleCPUOffloadScheduler, "_p8_2_k1a_observer_installed", False):
        return

    original_match = SimpleCPUOffloadScheduler.get_num_new_matched_tokens

    @wraps(original_match)
    def observed_match(self, request, num_computed_tokens):
        result = original_match(self, request, num_computed_tokens)
        num_new_tokens, is_async = result
        if num_new_tokens and num_new_tokens > 0:
            pending = self._pending_cpu_hits.get(request.request_id)
            max_hit_len = int(request.num_tokens) - 1 - int(num_computed_tokens)
            _emit(
                "cpu_hit_matched",
                component="scheduler",
                direction="h2d",
                request_id=request.request_id,
                contract_role=_active_contract_role(),
                num_new_tokens=num_new_tokens,
                is_async=bool(is_async),
                num_computed_tokens_arg=int(num_computed_tokens),
                max_hit_len=max_hit_len,
                pending_stored=pending is not None,
                pending_non_null_block_count=_pending_non_null_block_count(
                    pending
                ),
            )
        return result

    original_allocate = KVCacheManager.allocate_slots

    @wraps(original_allocate)
    def observed_allocate(
        self,
        request,
        num_new_tokens,
        num_new_computed_tokens=0,
        new_computed_blocks=None,
        num_lookahead_tokens=0,
        num_external_computed_tokens=0,
        delay_cache_blocks=False,
        num_encoder_tokens=0,
        full_sequence_must_fit=False,
    ):
        contract_role = _active_contract_role()
        observe_restore = contract_role == "restore_follower" or str(
            request.request_id
        ).endswith("restore_follower")
        free_blocks = None
        if observe_restore:
            coordinator = getattr(self, "coordinator", None)
            block_pool = getattr(coordinator, "block_pool", None)
            if block_pool is not None and hasattr(block_pool, "get_num_free_blocks"):
                try:
                    free_blocks = int(block_pool.get_num_free_blocks())
                except Exception:
                    free_blocks = None
        result = original_allocate(
            self,
            request,
            num_new_tokens,
            num_new_computed_tokens=num_new_computed_tokens,
            new_computed_blocks=new_computed_blocks,
            num_lookahead_tokens=num_lookahead_tokens,
            num_external_computed_tokens=num_external_computed_tokens,
            delay_cache_blocks=delay_cache_blocks,
            num_encoder_tokens=num_encoder_tokens,
            full_sequence_must_fit=full_sequence_must_fit,
        )
        if observe_restore:
            _emit(
                "allocate_slots_observed",
                component="kv_cache_manager",
                direction="h2d",
                request_id=request.request_id,
                contract_role=contract_role,
                num_new_tokens=int(num_new_tokens),
                num_new_computed_tokens=int(num_new_computed_tokens),
                num_external_computed_tokens=int(num_external_computed_tokens),
                num_lookahead_tokens=int(num_lookahead_tokens),
                delay_cache_blocks=bool(delay_cache_blocks),
                allocate_slots_ok=result is not None,
                gpu_free_block_count_before=free_blocks,
            )
        return result

    original_update = SimpleCPUOffloadScheduler.update_state_after_alloc

    @wraps(original_update)
    def observed_update(self, request, blocks, num_external_tokens):
        req_id = request.request_id
        pending_before = self._pending_cpu_hits.get(req_id)
        pending_present = pending_before is not None
        pending_non_null = _pending_non_null_block_count(pending_before)
        geometry = observe_update_pairing_geometry(
            self,
            blocks,
            int(num_external_tokens),
            pending_before,
        )
        compress_geometry = observe_compress_aware_pairing_geometry(
            self,
            blocks,
            int(num_external_tokens),
            pending_before,
        )
        repair_enabled = os.environ.get(REPAIR_ENABLE_ENV) == "1"
        manager_sha = _manager_source_sha256() if repair_enabled else ""
        manager_sha_matched = bool(
            manager_sha and manager_sha == EXPECTED_MANAGER_SHA256
        )
        repair_eligible = (
            repair_enabled
            and manager_sha_matched
            and geometry.get("geometry_preflight_failure_class")
            == "index_error_gpu_cpu_pairing"
            and compress_geometry.get("compress_aware_geometry_status") == "ok"
        )
        if not repair_enabled:
            repair_skip_reason = "repair_disabled"
        elif not manager_sha_matched:
            repair_skip_reason = "manager_sha_mismatch_or_unreadable"
        elif geometry.get("geometry_preflight_failure_class") != (
            "index_error_gpu_cpu_pairing"
        ):
            repair_skip_reason = "frozen_geometry_not_index_overflow"
        elif compress_geometry.get("compress_aware_geometry_status") != "ok":
            repair_skip_reason = "compress_aware_geometry_not_ok"
        else:
            repair_skip_reason = "none"
        repair_fields = {
            "pairing_repair_enabled": repair_enabled,
            "pairing_repair_eligible": repair_eligible,
            "pairing_repair_applied": False,
            "pairing_repair_skip_reason": repair_skip_reason,
            "manager_source_sha_matched": manager_sha_matched,
            **compress_geometry,
        }
        early_return_reason = "success"
        entered_reqs_to_load = False
        gpu_block_ids_count = 0
        cpu_block_ids_count = 0
        null_cpu_blocks_skipped = 0
        try:
            if repair_eligible:
                repaired_update_state_after_alloc(
                    self, request, blocks, int(num_external_tokens)
                )
                result = None
                repair_fields["pairing_repair_applied"] = True
                _emit(
                    "compress_aware_pairing_repair_applied",
                    component="scheduler",
                    direction="h2d",
                    request_id=req_id,
                    contract_role=_active_contract_role(),
                    num_external_tokens=int(num_external_tokens),
                    predicted_transfer_pair_count=_as_int(
                        compress_geometry.get(
                            "compress_aware_predicted_transfer_pair_count"
                        ),
                        0,
                    ),
                    compress_aware_block_sizes=list(
                        compress_geometry.get("compress_aware_block_sizes") or []
                    ),
                )
            else:
                result = original_update(
                    self, request, blocks, num_external_tokens
                )
        except BaseException as error:
            _emit(
                "update_state_after_alloc_observed",
                component="scheduler",
                direction="h2d",
                request_id=req_id,
                contract_role=_active_contract_role(),
                num_external_tokens=int(num_external_tokens),
                pending_present=pending_present,
                pending_non_null_block_count=pending_non_null,
                early_return_reason="update_raised",
                entered_reqs_to_load=False,
                gpu_block_ids_count=0,
                cpu_block_ids_count=0,
                null_cpu_blocks_skipped=0,
                **geometry,
                **repair_fields,
                **_bounded_error_fields(error),
            )
            raise
        state = self._reqs_to_load.get(req_id)
        transfer = state.transfer_meta if state is not None else None
        if transfer is not None:
            gpu_block_ids_count = len(transfer.gpu_block_ids)
            cpu_block_ids_count = len(transfer.cpu_block_ids)
            entered_reqs_to_load = True
            if gpu_block_ids_count <= 0:
                early_return_reason = "empty_transfer_after_null_filter"
            _emit(
                "load_scheduled",
                component="scheduler",
                direction="h2d",
                request_id=req_id,
                contract_role=_active_contract_role(),
                block_count=gpu_block_ids_count,
                num_external_tokens=int(num_external_tokens),
                gpu_block_ids_count=gpu_block_ids_count,
                cpu_block_ids_count=cpu_block_ids_count,
                pairing_repair_applied=repair_fields["pairing_repair_applied"],
            )
        elif int(num_external_tokens) == 0:
            early_return_reason = "num_external_zero"
        elif not pending_present:
            early_return_reason = "pending_missing"
        else:
            early_return_reason = "empty_transfer_after_null_filter"
            if pending_before is not None:
                null_cpu_blocks_skipped = max(
                    pending_non_null - cpu_block_ids_count,
                    0,
                )
        _emit(
            "update_state_after_alloc_observed",
            component="scheduler",
            direction="h2d",
            request_id=req_id,
            contract_role=_active_contract_role(),
            num_external_tokens=int(num_external_tokens),
            pending_present=pending_present,
            pending_non_null_block_count=pending_non_null,
            early_return_reason=early_return_reason,
            entered_reqs_to_load=entered_reqs_to_load,
            gpu_block_ids_count=gpu_block_ids_count,
            cpu_block_ids_count=cpu_block_ids_count,
            null_cpu_blocks_skipped=null_cpu_blocks_skipped,
            **geometry,
            **repair_fields,
        )
        return result

    original_build = SimpleCPUOffloadScheduler.build_connector_meta

    @wraps(original_build)
    def observed_build(self, scheduler_output):
        metadata = original_build(self, scheduler_output)
        if metadata.store_event >= 0 and metadata.store_gpu_blocks:
            _emit(
                "transfer_scheduled",
                component="scheduler",
                direction="d2h",
                event_idx=metadata.store_event,
                block_count=len(metadata.store_gpu_blocks),
            )
        load_gpu_count = len(metadata.load_gpu_blocks or [])
        load_event_ready = int(metadata.load_event) >= 0 and load_gpu_count > 0
        pending_load_req_count = sum(
            1
            for state in self._reqs_to_load.values()
            if getattr(state, "load_event", None) is None
        )
        if (
            _active_contract_role() == "restore_follower"
            or pending_load_req_count
            or load_gpu_count
            or int(metadata.load_event) >= 0
        ):
            _emit(
                "connector_load_meta_observed",
                component="scheduler",
                direction="h2d",
                contract_role=_active_contract_role(),
                load_event=int(metadata.load_event),
                load_event_ready=load_event_ready,
                load_gpu_block_count=load_gpu_count,
                pending_load_request_count=pending_load_req_count,
            )
        if load_event_ready:
            _emit(
                "transfer_scheduled",
                component="scheduler",
                direction="h2d",
                event_idx=metadata.load_event,
                block_count=load_gpu_count,
            )
        return metadata

    original_output = SimpleCPUOffloadScheduler.update_connector_output

    @wraps(original_output)
    def observed_output(self, connector_output):
        store_before = dict(self._store_event_to_blocks)
        load_before = set(self._reqs_to_load)
        result = original_output(self, connector_output)
        for event_idx in sorted(set(store_before) - set(self._store_event_to_blocks)):
            transfer = store_before[event_idx]
            _emit(
                "store_event_completed",
                component="scheduler",
                direction="d2h",
                event_idx=event_idx,
                block_count=len(transfer.cpu_block_ids),
            )
        for request_id in sorted(load_before - set(self._reqs_to_load)):
            _emit(
                "load_request_completed",
                component="scheduler",
                direction="h2d",
                request_id=request_id,
                contract_role=_active_contract_role(),
            )
        return result

    original_copy_blocks = copy_backend_module.copy_blocks

    @wraps(original_copy_blocks)
    def observed_copy_blocks(src_blocks, dst_blocks, params):
        direction = (
            "d2h"
            if params.direction == copy_backend_module.DIRECTION_D2H
            else "h2d"
        )
        _emit(
            "copy_blocks_entered",
            component="npu_copy_primitive",
            direction=direction,
            block_count=len(src_blocks),
            byte_count=sum(int(value) for value in params.bpb) * len(src_blocks),
            sub_tensor_count=params.num_sub_tensors,
        )
        try:
            result = original_copy_blocks(src_blocks, dst_blocks, params)
        except BaseException as error:
            _emit(
                "copy_blocks_failed",
                component="npu_copy_primitive",
                direction=direction,
                **_bounded_error_fields(error),
            )
            raise
        _emit(
            "copy_blocks_returned",
            component="npu_copy_primitive",
            direction=direction,
        )
        return result

    original_copy_loop = NPUDmaCopyBackend._copy_loop

    @wraps(original_copy_loop)
    def observed_copy_loop(self):
        _emit("copy_thread_started", component="npu_copy_backend")
        try:
            return original_copy_loop(self)
        except BaseException as error:
            _emit(
                "copy_thread_failed",
                component="npu_copy_backend",
                **_bounded_error_fields(error),
            )
            raise
        finally:
            _emit("copy_thread_exited", component="npu_copy_backend")

    original_launch = NPUDmaCopyBackend.launch_copy

    @wraps(original_launch)
    def observed_launch(
        self,
        src_blocks,
        dst_blocks,
        is_store,
        event_idx,
        events_list,
    ):
        params = self._store_params if is_store else self._load_params
        bytes_per_block = (
            sum(int(value) for value in params.bpb) if params is not None else 0
        )
        _emit(
            "device_copy_submitted",
            component="npu_copy_backend",
            direction="d2h" if is_store else "h2d",
            event_idx=event_idx,
            block_count=len(src_blocks),
            byte_count=bytes_per_block * len(src_blocks),
            sub_tensor_count=(params.num_sub_tensors if params is not None else 0),
        )
        try:
            result = original_launch(
                self,
                src_blocks,
                dst_blocks,
                is_store,
                event_idx,
                events_list,
            )
        except Exception as error:
            _emit(
                "device_copy_launch_failed",
                component="npu_copy_backend",
                direction="d2h" if is_store else "h2d",
                event_idx=event_idx,
                **_bounded_error_fields(error),
            )
            raise
        _emit(
            "device_copy_enqueued",
            component="npu_copy_backend",
            direction="d2h" if is_store else "h2d",
            event_idx=event_idx,
        )
        _emit(
            "device_copy_launch_returned",
            component="npu_copy_backend",
            direction="d2h" if is_store else "h2d",
            event_idx=event_idx,
        )
        return result

    original_poll = SimpleCPUOffloadNPUWorker._poll_stream_events

    @wraps(original_poll)
    def observed_poll(self, is_store):
        before = self._store_hwm if is_store else self._load_hwm
        events = self._store_events if is_store else self._load_events
        copy_thread = getattr(self._backend, "_thread", None)
        _emit(
            "transfer_poll_entered",
            component="npu_worker",
            direction="d2h" if is_store else "h2d",
            pending_event_count=len(events),
            event_idx=(events[0][0] if events else None),
            copy_thread_alive=(
                copy_thread.is_alive() if copy_thread is not None else False
            ),
        )
        try:
            hwm = original_poll(self, is_store)
        except Exception as error:
            _emit(
                "transfer_poll_failed",
                component="npu_worker",
                direction="d2h" if is_store else "h2d",
                **_bounded_error_fields(error),
            )
            raise
        _emit(
            "transfer_poll_returned",
            component="npu_worker",
            direction="d2h" if is_store else "h2d",
            event_hwm=hwm,
        )
        if hwm > before:
            _emit(
                "transfer_completed",
                component="npu_worker",
                direction="d2h" if is_store else "h2d",
                event_hwm=hwm,
            )
        return hwm

    SimpleCPUOffloadScheduler.get_num_new_matched_tokens = observed_match
    KVCacheManager.allocate_slots = observed_allocate
    SimpleCPUOffloadScheduler.update_state_after_alloc = observed_update
    SimpleCPUOffloadScheduler.build_connector_meta = observed_build
    SimpleCPUOffloadScheduler.update_connector_output = observed_output
    copy_backend_module.copy_blocks = observed_copy_blocks
    NPUDmaCopyBackend._copy_loop = observed_copy_loop
    NPUDmaCopyBackend.launch_copy = observed_launch
    SimpleCPUOffloadNPUWorker._poll_stream_events = observed_poll
    SimpleCPUOffloadScheduler._p8_2_k1a_observer_installed = True
    KVCacheManager._p8_2_k1a_allocate_observer_installed = True
    _emit("observer_installed", component="runtime_patch", mutation="observe_only")
    if os.environ.get("P8_2_K1A_ENABLE_H2D_RESIDENCY_OBSERVER") == "1":
        from p8_2_k1a_h2d_residency_observer import (
            install_p8_2_k1a_h2d_residency_observer,
        )

        install_p8_2_k1a_h2d_residency_observer()


def summarize_trace_rows(
    rows: list[dict[str, Any]],
    *,
    expected_world_size: int,
    restore_request_suffix: str,
) -> dict[str, Any]:
    submitted = {
        direction: [
            row
            for row in rows
            if row.get("event") == "device_copy_submitted"
            and row.get("direction") == direction
            and int(row.get("byte_count") or 0) > 0
        ]
        for direction in ("d2h", "h2d")
    }
    completed = {
        direction: [
            row
            for row in rows
            if row.get("event") == "transfer_completed"
            and row.get("direction") == direction
        ]
        for direction in ("d2h", "h2d")
    }
    enqueued = {
        direction: [
            row
            for row in rows
            if row.get("event") == "device_copy_enqueued"
            and row.get("direction") == direction
        ]
        for direction in ("d2h", "h2d")
    }
    copy_entered = {
        direction: [
            row
            for row in rows
            if row.get("event") == "copy_blocks_entered"
            and row.get("direction") == direction
        ]
        for direction in ("d2h", "h2d")
    }
    copy_returned = {
        direction: [
            row
            for row in rows
            if row.get("event") == "copy_blocks_returned"
            and row.get("direction") == direction
        ]
        for direction in ("d2h", "h2d")
    }
    poll_event_visible = {
        direction: [
            row
            for row in rows
            if row.get("event") == "transfer_poll_entered"
            and row.get("direction") == direction
            and int(row.get("pending_event_count") or 0) > 0
            and row.get("copy_thread_alive") is True
        ]
        for direction in ("d2h", "h2d")
    }
    submitted_pids = {
        direction: {int(row["pid"]) for row in values}
        for direction, values in submitted.items()
    }
    completed_pids = {
        direction: {int(row["pid"]) for row in values}
        for direction, values in completed.items()
    }
    enqueued_pids = {
        direction: {int(row["pid"]) for row in values}
        for direction, values in enqueued.items()
    }
    copy_entered_pids = {
        direction: {int(row["pid"]) for row in values}
        for direction, values in copy_entered.items()
    }
    copy_returned_pids = {
        direction: {int(row["pid"]) for row in values}
        for direction, values in copy_returned.items()
    }
    poll_event_visible_pids = {
        direction: {int(row["pid"]) for row in values}
        for direction, values in poll_event_visible.items()
    }
    copy_thread_started_pids = {
        int(row["pid"])
        for row in rows
        if row.get("event") == "copy_thread_started"
    }
    cpu_hits = [
        row
        for row in rows
        if row.get("event") == "cpu_hit_matched"
        and (
            row.get("contract_role") == "restore_follower"
            or str(row.get("request_id", "")).endswith(restore_request_suffix)
        )
        and int(row.get("num_new_tokens") or 0) > 0
    ]
    load_scheduled = [
        row
        for row in rows
        if row.get("event") == "load_scheduled"
        and (
            row.get("contract_role") == "restore_follower"
            or str(row.get("request_id", "")).endswith(restore_request_suffix)
        )
        and int(row.get("block_count") or 0) > 0
    ]
    load_completed = [
        row
        for row in rows
        if row.get("event") == "load_request_completed"
        and (
            row.get("contract_role") == "restore_follower"
            or str(row.get("request_id", "")).endswith(restore_request_suffix)
        )
    ]
    store_completed = [
        row for row in rows if row.get("event") == "store_event_completed"
    ]
    copy_failures = [
        row for row in rows if row.get("event") == "device_copy_launch_failed"
    ]
    poll_failures = [
        row for row in rows if row.get("event") == "transfer_poll_failed"
    ]
    copy_thread_failures = [
        row for row in rows if row.get("event") == "copy_thread_failed"
    ]
    copy_blocks_failures = [
        row for row in rows if row.get("event") == "copy_blocks_failed"
    ]
    async_failure_events = (
        copy_failures
        + poll_failures
        + copy_thread_failures
        + copy_blocks_failures
    )
    async_pipeline_exact = {
        direction: bool(submitted_pids[direction])
        and all(
            pids == submitted_pids[direction]
            for pids in (
                enqueued_pids[direction],
                copy_entered_pids[direction],
                copy_returned_pids[direction],
                poll_event_visible_pids[direction],
            )
        )
        and submitted_pids[direction].issubset(copy_thread_started_pids)
        and not async_failure_events
        for direction in ("d2h", "h2d")
    }
    d2h_store_complete = all(
        (
            len(submitted_pids["d2h"]) == expected_world_size,
            completed_pids["d2h"] == submitted_pids["d2h"],
            bool(store_completed),
        )
    )
    h2d_restore_complete = all(
        (
            len(submitted_pids["h2d"]) == expected_world_size,
            completed_pids["h2d"] == submitted_pids["h2d"],
            bool(cpu_hits),
            bool(load_scheduled),
            bool(load_completed),
        )
    )
    hit_to_load = classify_restore_hit_to_load_gap(
        rows,
        restore_request_suffix=restore_request_suffix,
    )
    return {
        "trace_event_count": len(rows),
        "expected_world_size": expected_world_size,
        "d2h_worker_count": len(submitted_pids["d2h"]),
        "h2d_worker_count": len(submitted_pids["h2d"]),
        "d2h_completed_worker_count": len(completed_pids["d2h"]),
        "h2d_completed_worker_count": len(completed_pids["h2d"]),
        "d2h_enqueued_worker_count": len(enqueued_pids["d2h"]),
        "h2d_enqueued_worker_count": len(enqueued_pids["h2d"]),
        "d2h_copy_blocks_entered_worker_count": len(copy_entered_pids["d2h"]),
        "h2d_copy_blocks_entered_worker_count": len(copy_entered_pids["h2d"]),
        "d2h_copy_blocks_returned_worker_count": len(copy_returned_pids["d2h"]),
        "h2d_copy_blocks_returned_worker_count": len(copy_returned_pids["h2d"]),
        "d2h_poll_event_visible_worker_count": len(poll_event_visible_pids["d2h"]),
        "h2d_poll_event_visible_worker_count": len(poll_event_visible_pids["h2d"]),
        "copy_thread_started_worker_count": len(copy_thread_started_pids),
        "d2h_bytes_total": sum(
            int(row.get("byte_count") or 0) for row in submitted["d2h"]
        ),
        "h2d_bytes_total": sum(
            int(row.get("byte_count") or 0) for row in submitted["h2d"]
        ),
        "store_event_completed_count": len(store_completed),
        "restore_cpu_hit_tokens_max": max(
            (int(row.get("num_new_tokens") or 0) for row in cpu_hits),
            default=0,
        ),
        "restore_load_scheduled_count": len(load_scheduled),
        "restore_load_completed_count": len(load_completed),
        "device_copy_launch_failed_count": len(copy_failures),
        "transfer_poll_failed_count": len(poll_failures),
        "copy_thread_failed_count": len(copy_thread_failures),
        "copy_blocks_failed_count": len(copy_blocks_failures),
        "async_copy_failure_event_count": len(async_failure_events),
        "transfer_failure_event_count": len(async_failure_events),
        "d2h_async_copy_pipeline_exact": async_pipeline_exact["d2h"],
        "h2d_async_copy_pipeline_exact": async_pipeline_exact["h2d"],
        "d2h_store_complete": d2h_store_complete,
        "h2d_restore_complete": h2d_restore_complete,
        "runtime_evidence_exact": (
            d2h_store_complete
            and h2d_restore_complete
            and async_pipeline_exact["d2h"]
            and async_pipeline_exact["h2d"]
        ),
        **{
            key: value
            for key, value in hit_to_load.items()
            if key != "schema_version"
        },
    }
