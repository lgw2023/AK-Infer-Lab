from __future__ import annotations

import argparse
from functools import wraps
import json
import os
from pathlib import Path
import time
from typing import Any
import weakref


TRACE_ENV = "P8_2_K1A_TRANSFER_TRACE_DIR"
TARGET_SUFFIX_ENV = "P8_2_K1A_H2D_TARGET_REQUEST_SUFFIX"
RESTORE_SUFFIX_ENV = "P8_2_K1A_H2D_RESTORE_REQUEST_SUFFIX"
TARGET_BLOCK_COUNT_ENV = "P8_2_K1A_H2D_TARGET_BLOCK_COUNT"
RESTORE_MATCH_TOKENS_ENV = "P8_2_K1A_RESTORE_MATCH_TOKENS"
BLOCK_SIZE_TOKENS_ENV = "P8_2_K1A_BLOCK_SIZE_TOKENS"
ACTIVE_ROLE_PATH_ENV = "P8_2_K1A_H2D_ACTIVE_ROLE_PATH"
REQUEST_LOCAL_PRESSURE_OBSERVER_ENV = (
    "P8_2_K1A_ENABLE_REQUEST_LOCAL_PRESSURE_OBSERVER"
)
_POOL_TIERS: dict[int, str] = {}
_POOL_SCHEDULERS: dict[int, weakref.ReferenceType[Any]] = {}


def derive_restore_eligibility_contract(
    *, restore_match_tokens: int, block_size_tokens: int
) -> dict[str, int]:
    if restore_match_tokens <= 0 or block_size_tokens <= 0:
        raise ValueError("restore eligibility geometry must be positive")
    if restore_match_tokens % block_size_tokens != 0:
        raise ValueError("restore match tokens must align to the block size")
    return {
        "restore_match_tokens_required": restore_match_tokens,
        "block_size_tokens": block_size_tokens,
        "required_restore_block_count": (
            restore_match_tokens // block_size_tokens
        ),
    }


def validate_effective_restore_contract(
    *,
    target_block_count: int,
    restore_match_tokens: int,
    block_size_tokens: int,
    require_restore_group_eligibility: bool,
) -> dict[str, Any]:
    geometry = derive_restore_eligibility_contract(
        restore_match_tokens=restore_match_tokens,
        block_size_tokens=block_size_tokens,
    )
    exact = target_block_count == geometry["required_restore_block_count"]
    if require_restore_group_eligibility and not exact:
        raise ValueError(
            "effective target block count does not match restore geometry: "
            f"target={target_block_count}, "
            f"required={geometry['required_restore_block_count']}"
        )
    return {
        **geometry,
        "effective_target_block_count": target_block_count,
        "restore_group_eligibility_required": require_restore_group_eligibility,
        "effective_restore_contract_exact": exact,
    }


def capture_restore_group_hashes(
    *,
    group_index: int,
    group_block_ids: list[int],
    block_lookup: Any,
    restore_match_tokens: int,
    effective_block_size_tokens: int,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    if restore_match_tokens <= 0 or effective_block_size_tokens <= 0:
        raise ValueError("restore group capture geometry must be positive")
    if restore_match_tokens % effective_block_size_tokens != 0:
        raise ValueError("restore match tokens must align to the group block size")
    theoretical_count = restore_match_tokens // effective_block_size_tokens
    selected_ids = group_block_ids[:theoretical_count]
    selected_blocks = [block_lookup[block_id] for block_id in selected_ids]
    non_null_blocks = [block for block in selected_blocks if not block.is_null]
    hashes = tuple(
        block.block_hash
        for block in non_null_blocks
        if block.block_hash is not None
    )
    selected_geometry_exact = len(selected_ids) == theoretical_count
    # A runtime group with supplied block IDs remains applicable even when its
    # selected blocks are null or unhashable.  Treating applicability as
    # ``bool(hashes)`` would silently drop precisely the incomplete capture
    # that must fail the pre-pressure gate.
    group_applicable = bool(group_block_ids)
    hash_capture_exact = (
        len(non_null_blocks) == len(hashes)
        and (not group_applicable or len(hashes) == theoretical_count)
    )
    return hashes, {
        "group_index": group_index,
        "restore_match_tokens_required": restore_match_tokens,
        "effective_block_size_tokens": effective_block_size_tokens,
        "theoretical_block_count": theoretical_count,
        "physical_key_count_required": theoretical_count,
        "provided_block_id_count": len(group_block_ids),
        "selected_block_id_count": len(selected_ids),
        "non_null_block_count": len(non_null_blocks),
        "hashable_block_count": len(hashes),
        "unhashable_non_null_block_count": len(non_null_blocks) - len(hashes),
        "required_block_count": theoretical_count if group_applicable else 0,
        "group_applicable": group_applicable,
        "selected_geometry_exact": selected_geometry_exact,
        "hash_capture_exact": hash_capture_exact,
        "logical_coverage_exact": (
            group_applicable
            and selected_geometry_exact
            and hash_capture_exact
        ),
        "capture_basis": "hashable_blocks_used_by_cache_lookup",
        "raw_block_ids_retained": False,
        "raw_hash_values_retained": False,
    }


def derive_runtime_group_geometry(
    scheduler: Any,
    *,
    group_index: int,
    group: Any,
    restore_match_tokens: int,
) -> dict[str, Any]:
    """Mirror the live coordinator's per-group cache-key geometry.

    The vLLM-Ascend coordinator may multiply a group's declared block size by
    context-parallel width and ``compress_ratio``.  The scheduler's retained
    group block IDs already use that coordinator geometry, so observer-side
    slicing must use the same unit instead of treating every physical key as
    one logical hash block.
    """

    spec = group.kv_cache_spec
    base_block_size = int(spec.block_size)
    cp_world_size = int(getattr(scheduler, "cp_world_size", 1) or 1)
    raw_compress_ratio = getattr(spec, "compress_ratio", 1)
    try:
        compress_ratio = max(1, int(raw_compress_ratio or 1))
    except (TypeError, ValueError):
        compress_ratio = 1

    coordinator = getattr(scheduler, "cpu_coordinator", None)
    coordinator_method = getattr(
        coordinator, "_get_effective_block_size", None
    )
    if callable(coordinator_method):
        effective_block_size = int(coordinator_method(spec))
        geometry_source = "runtime_cpu_coordinator"
    else:
        is_mamba = type(spec).__name__ == "MambaSpec"
        effective_block_size = base_block_size
        if not is_mamba:
            effective_block_size *= cp_world_size
            effective_block_size *= compress_ratio
        geometry_source = "observer_source_aligned_fallback"

    aligned = (
        effective_block_size > 0
        and restore_match_tokens % effective_block_size == 0
    )
    return {
        "group_index": group_index,
        "kv_cache_spec_type": type(spec).__name__,
        "base_block_size_tokens": base_block_size,
        "cp_world_size": cp_world_size,
        "compress_ratio": compress_ratio,
        "effective_block_size_tokens": effective_block_size,
        "restore_match_tokens_required": restore_match_tokens,
        "physical_key_count_required": (
            restore_match_tokens // effective_block_size
            if aligned
            else -1
        ),
        "effective_geometry_aligned": aligned,
        "effective_geometry_source": geometry_source,
        "raw_block_ids_retained": False,
        "raw_hash_values_retained": False,
    }


def select_target_hashes(
    *,
    request_hashes: list[Any],
    fa_group_hashes: list[Any],
    target_block_count: int,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    if target_block_count <= 0:
        raise ValueError("target block count must be positive")
    request_candidates = tuple(
        value for value in request_hashes[:target_block_count] if value is not None
    )
    fa_candidates = tuple(
        value for value in fa_group_hashes[:target_block_count] if value is not None
    )
    if len(request_candidates) == target_block_count:
        selected = request_candidates
        source = "request_block_hashes"
    elif len(fa_candidates) == target_block_count:
        selected = fa_candidates
        source = "fa_group_block_hashes"
    elif len(request_candidates) >= len(fa_candidates):
        selected = request_candidates
        source = "request_block_hashes_near_miss"
    else:
        selected = fa_candidates
        source = "fa_group_block_hashes_near_miss"
    return selected, {
        "configured_target_block_count": target_block_count,
        "request_hash_candidate_count": len(request_candidates),
        "fa_group_hash_candidate_count": len(fa_candidates),
        "selected_target_hash_count": len(selected),
        "target_capture_source": source,
        "target_capture_exact": len(selected) == target_block_count,
        "raw_hash_values_retained": False,
    }


def probe_logical_restore_window(
    *,
    cpu_coordinator: Any,
    request_hashes: list[Any],
    restore_match_tokens: int,
    hash_block_size_tokens: int,
    cpu_pool: Any,
    gpu_pool: Any,
    retained_pool_keys: tuple[Any, ...] = (),
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    """Probe restore coverage through the runtime's own cache-key semantics.

    Request hashes are logical hash-granularity values. Pool maps are keyed by
    the runtime's per-group wrapped hashes, and compressed/sparse KV groups do
    not have one physical key per logical hash block. Reusing the CPU
    coordinator avoids reimplementing those mappings in the observer.
    """

    geometry = derive_restore_eligibility_contract(
        restore_match_tokens=restore_match_tokens,
        block_size_tokens=hash_block_size_tokens,
    )
    side_effect_field = "num_uncached_common_prefix_tokens"
    had_side_effect_field = hasattr(cpu_coordinator, side_effect_field)
    previous_side_effect_value = getattr(
        cpu_coordinator, side_effect_field, None
    )
    try:
        result = cpu_coordinator.find_longest_cache_hit(
            request_hashes, restore_match_tokens
        )
    finally:
        if had_side_effect_field:
            setattr(
                cpu_coordinator,
                side_effect_field,
                previous_side_effect_value,
            )
        elif hasattr(cpu_coordinator, side_effect_field):
            delattr(cpu_coordinator, side_effect_field)
    if not isinstance(result, tuple) or len(result) < 2:
        raise ValueError("runtime CPU coordinator returned an invalid hit result")
    groups = tuple(result[0])
    hit_tokens = max(0, min(int(result[1]), restore_match_tokens))
    logical_exact = hit_tokens == restore_match_tokens

    group_keys: list[tuple[Any, ...]] = []
    current_keys: list[Any] = []
    seen: set[Any] = set()
    for blocks in groups:
        keys = []
        for block in blocks:
            key = getattr(block, "block_hash", None)
            if getattr(block, "is_null", False) or key is None:
                continue
            keys.append(key)
            if key not in seen:
                seen.add(key)
                current_keys.append(key)
        group_keys.append(tuple(keys))

    if logical_exact and current_keys:
        target_pool_keys = tuple(current_keys)
    else:
        target_pool_keys = retained_pool_keys

    def count(pool: Any, keys: tuple[Any, ...]) -> int:
        if pool is None:
            return 0
        mapping = pool.cached_block_hash_to_block
        return sum(mapping.get_one_block(key) is not None for key in keys)

    group_rows = []
    for group_index, keys in enumerate(group_keys):
        group_rows.append(
            {
                "group_index": group_index,
                "required_block_count": len(keys),
                "captured_block_count": len(keys),
                "cpu_block_count": count(cpu_pool, keys),
                "gpu_block_count": count(gpu_pool, keys),
                "capture_basis": "runtime_cpu_coordinator_longest_hit",
                "raw_block_ids_retained": False,
                "raw_hash_values_retained": False,
            }
        )
    group_summary = build_restore_group_residency_summary(group_rows)
    cpu_pool_matches = count(cpu_pool, target_pool_keys)
    gpu_pool_matches = count(gpu_pool, target_pool_keys)
    request_candidates = [
        value
        for value in request_hashes[
            : geometry["required_restore_block_count"]
        ]
        if value is not None
    ]
    cardinality_exact = (
        len(request_candidates) == geometry["required_restore_block_count"]
    )
    keyspace_matchable = all(
        (
            logical_exact,
            bool(target_pool_keys),
            cpu_pool_matches == len(target_pool_keys),
        )
    )
    capture_exact = all(
        (
            cardinality_exact,
            keyspace_matchable,
            group_summary["restore_group_eligibility_complete"] is True,
        )
    )
    return (
        {
            "configured_target_block_count": geometry[
                "required_restore_block_count"
            ],
            "request_hash_candidate_count": len(request_candidates),
            "selected_target_hash_count": geometry[
                "required_restore_block_count"
            ]
            if cardinality_exact
            else 0,
            "target_capture_source": "runtime_cpu_coordinator_longest_hit",
            "target_capture_cardinality_exact": cardinality_exact,
            "target_keyspace_matchable": keyspace_matchable,
            "target_capture_exact": capture_exact,
            "logical_restore_match_tokens": hit_tokens,
            "logical_restore_window_exact": logical_exact,
            "coordinator_returned_pool_key_count": len(current_keys),
            "coordinator_cpu_pool_key_match_count": count(
                cpu_pool, tuple(current_keys)
            ),
            "coordinator_gpu_pool_key_match_count": count(
                gpu_pool, tuple(current_keys)
            ),
            "target_pool_key_count": len(target_pool_keys),
            "cpu_target_pool_key_match_count": cpu_pool_matches,
            "gpu_target_pool_key_match_count": gpu_pool_matches,
            "target_count_unit": "logical_request_hash_blocks",
            "cpu_target_count_unit": "logical_request_hash_blocks",
            "gpu_target_count_unit": "runtime_group_pool_keys",
            "target_pool_key_count_unit": "runtime_group_pool_keys",
            "cpu_target_block_count": hit_tokens // hash_block_size_tokens,
            "gpu_target_block_count": gpu_pool_matches,
            **group_summary,
            "raw_hash_values_retained": False,
        },
        target_pool_keys,
    )


def refresh_logical_restore_window(
    scheduler: Any,
    *,
    restore_match_tokens: int,
    hash_block_size_tokens: int,
) -> dict[str, Any]:
    request_hashes = list(
        getattr(scheduler, "_p8_2_k1a_target_request_hashes", ()) or ()
    )
    required = restore_match_tokens // hash_block_size_tokens
    if not request_hashes:
        return {
            "configured_target_block_count": required,
            "target_capture_source": "runtime_cpu_coordinator_longest_hit",
            "target_capture_cardinality_exact": False,
            "target_keyspace_matchable": False,
            "target_capture_exact": False,
            "logical_restore_match_tokens": 0,
            "logical_restore_window_exact": False,
            "target_pool_key_count": 0,
            "cpu_target_pool_key_match_count": 0,
            "gpu_target_pool_key_match_count": 0,
            "target_count_unit": "logical_request_hash_blocks",
            "cpu_target_count_unit": "logical_request_hash_blocks",
            "gpu_target_count_unit": "runtime_group_pool_keys",
            "target_pool_key_count_unit": "runtime_group_pool_keys",
            "cpu_target_block_count": 0,
            "gpu_target_block_count": 0,
            "restore_group_eligibility_complete": False,
            "raw_hash_values_retained": False,
        }
    retained = tuple(
        getattr(scheduler, "_p8_2_k1a_target_pool_keys", ()) or ()
    )
    try:
        summary, target_pool_keys = probe_logical_restore_window(
            cpu_coordinator=scheduler.cpu_coordinator,
            request_hashes=request_hashes,
            restore_match_tokens=restore_match_tokens,
            hash_block_size_tokens=hash_block_size_tokens,
            cpu_pool=getattr(scheduler, "cpu_block_pool", None),
            gpu_pool=getattr(scheduler, "_gpu_block_pool", None),
            retained_pool_keys=retained,
        )
    except Exception as error:  # Observe-only: never alter scheduler behavior.
        summary = {
            "configured_target_block_count": required,
            "request_hash_candidate_count": len(request_hashes[:required]),
            "target_capture_source": "runtime_cpu_coordinator_longest_hit",
            "target_capture_cardinality_exact": len(request_hashes[:required])
            == required,
            "target_keyspace_matchable": False,
            "target_capture_exact": False,
            "logical_restore_match_tokens": 0,
            "logical_restore_window_exact": False,
            "target_pool_key_count": len(retained),
            "cpu_target_pool_key_match_count": 0,
            "gpu_target_pool_key_match_count": 0,
            "target_count_unit": "logical_request_hash_blocks",
            "cpu_target_count_unit": "logical_request_hash_blocks",
            "gpu_target_count_unit": "runtime_group_pool_keys",
            "target_pool_key_count_unit": "runtime_group_pool_keys",
            "cpu_target_block_count": 0,
            "gpu_target_block_count": 0,
            "restore_group_eligibility_complete": False,
            "target_keyspace_probe_error_type": type(error).__name__,
            "raw_hash_values_retained": False,
        }
        target_pool_keys = retained
    lineage = _target_store_lineage_residency_summary(scheduler)
    if lineage:
        logical_fields = {
            key: summary.get(key)
            for key in (
                "logical_restore_match_tokens",
                "logical_restore_window_exact",
                "coordinator_returned_pool_key_count",
                "coordinator_cpu_pool_key_match_count",
                "coordinator_gpu_pool_key_match_count",
                "target_keyspace_probe_error_type",
            )
            if key in summary
        }
        request_hash_candidate_count = int(
            summary.get("request_hash_candidate_count") or 0
        )
        summary = {
            **summary,
            **lineage,
            **logical_fields,
            "request_hash_candidate_count": request_hash_candidate_count,
            "target_capture_cardinality_exact": (
                request_hash_candidate_count == required
            ),
            "selected_target_hash_count": (
                required if request_hash_candidate_count == required else 0
            ),
            "target_capture_source": (
                "target_finish_gpu_group_wrapped_keys"
            ),
            "target_keyspace_matchable": (
                lineage.get("target_store_lineage_capture_exact") is True
            ),
            "target_capture_exact": all(
                (
                    request_hash_candidate_count == required,
                    lineage.get("target_store_lineage_capture_exact") is True,
                )
            ),
        }
        target_pool_keys = tuple(
            getattr(scheduler, "_p8_2_k1a_target_store_keys", ()) or ()
        )
    if target_pool_keys:
        scheduler._p8_2_k1a_target_pool_keys = target_pool_keys
    else:
        scheduler._p8_2_k1a_target_pool_keys = retained
    scheduler._p8_2_k1a_target_hashes = tuple(
        scheduler._p8_2_k1a_target_pool_keys
    )
    scheduler._p8_2_k1a_target_capture_summary = summary
    scheduler._p8_2_k1a_logical_restore_summary = summary
    return summary


def build_restore_group_residency_summary(
    group_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    geometry_fields = (
        "restore_match_tokens_required",
        "base_block_size_tokens",
        "cp_world_size",
        "compress_ratio",
        "effective_block_size_tokens",
        "physical_key_count_required",
        "theoretical_block_count",
        "provided_block_id_count",
        "selected_block_id_count",
        "non_null_block_count",
        "hashable_block_count",
        "unhashable_non_null_block_count",
        "group_applicable",
        "selected_geometry_exact",
        "hash_capture_exact",
        "logical_coverage_exact",
        "effective_geometry_aligned",
        "effective_geometry_source",
        "kv_cache_spec_type",
        "capture_basis",
    )
    bounded_rows: list[dict[str, Any]] = []
    for row in group_rows:
        required = int(row.get("required_block_count") or 0)
        captured = int(row.get("captured_block_count") or 0)
        cpu_count = int(row.get("cpu_block_count") or 0)
        gpu_count = int(row.get("gpu_block_count") or 0)
        applicable = (
            row.get("group_applicable") is True
            if "group_applicable" in row
            else required > 0
        )
        capture_exact = all(
            (
                applicable,
                captured == required,
                row.get("selected_geometry_exact", True) is True,
                row.get("hash_capture_exact", True) is True,
            )
        )
        bounded = {
            "group_index": int(row.get("group_index") or 0),
            "required_block_count": required,
            "captured_block_count": captured,
            "cpu_block_count": cpu_count,
            "gpu_block_count": gpu_count,
            "group_applicable": applicable,
            "capture_exact": capture_exact,
            "cpu_complete": applicable and cpu_count == required,
            "gpu_absent": applicable and gpu_count == 0,
        }
        if any(field in row for field in geometry_fields):
            bounded.update(
                {
                    field: row[field]
                    for field in geometry_fields
                    if field in row
                }
            )
            bounded.update(
                {
                    "raw_block_ids_retained": False,
                    "raw_hash_values_retained": False,
                }
            )
        bounded_rows.append(bounded)
    group_count = len(bounded_rows)
    applicable_rows = [
        row for row in bounded_rows if row["group_applicable"] is True
    ]
    applicable_count = len(applicable_rows)
    captured_exact = (
        applicable_count > 0
        and all(row["capture_exact"] is True for row in applicable_rows)
    )
    captured_exact_count = sum(
        row["capture_exact"] for row in applicable_rows
    )
    cpu_complete_count = sum(row["cpu_complete"] for row in applicable_rows)
    gpu_absent_count = sum(row["gpu_absent"] for row in applicable_rows)
    return {
        "restore_group_count": group_count,
        "restore_group_applicable_count": applicable_count,
        "restore_groups_captured_exact_count": captured_exact_count,
        "restore_groups_captured_exact": captured_exact,
        "restore_groups_cpu_complete_count": cpu_complete_count,
        "restore_groups_gpu_absent_count": gpu_absent_count,
        "restore_group_eligibility_complete": (
            captured_exact
            and cpu_complete_count == applicable_count
            and gpu_absent_count == applicable_count
        ),
        "restore_group_rows": bounded_rows,
    }


def build_restore_eligibility_gate(
    rows: list[dict[str, Any]],
    *,
    required_restore_block_count: int,
    require_effective_group_geometry: bool = False,
) -> dict[str, Any]:
    candidates = [
        row
        for row in rows
        if row.get("event")
        in {"request_local_pressure_progress", "target_residency_snapshot"}
    ]
    latest = candidates[-1] if candidates else {}
    observed = int(latest.get("target_block_count") or 0)
    cpu_count = int(latest.get("cpu_target_block_count") or 0)
    gpu_count = int(latest.get("gpu_target_block_count") or 0)
    group_count = int(latest.get("restore_group_count") or 0)
    groups_captured = latest.get("restore_groups_captured_exact") is True
    groups_complete = (
        latest.get("restore_group_eligibility_complete") is True
    )
    capture_exact = (
        latest.get("target_capture_exact") is True
        if "target_capture_exact" in latest
        else groups_captured
    )
    cardinality_exact = (
        latest.get("target_capture_cardinality_exact") is True
        if "target_capture_cardinality_exact" in latest
        else capture_exact
    )
    keyspace_matchable = (
        latest.get("target_keyspace_matchable") is True
        if "target_keyspace_matchable" in latest
        else capture_exact
    )
    cpu_evictions = [
        row
        for row in rows
        if row.get("event") == "target_cache_evicted"
        and row.get("tier") == "cpu"
        and int(row.get("target_evicted_count") or 0) > 0
    ]

    def row_capture_exact(row: dict[str, Any]) -> bool:
        return (
            row.get("target_capture_exact") is True
            if "target_capture_exact" in row
            else row.get("restore_groups_captured_exact") is True
        )

    def physical_window_exact(row: dict[str, Any]) -> bool:
        if require_effective_group_geometry:
            return all(
                (
                    int(row.get("target_block_count") or 0)
                    == required_restore_block_count,
                    row.get("target_logical_coverage_exact") is True,
                    row.get("physical_target_window_exact") is True,
                    row_capture_exact(row),
                    row.get("restore_group_eligibility_complete") is True,
                )
            )
        return all(
            (
                int(row.get("target_block_count") or 0)
                == required_restore_block_count,
                int(row.get("cpu_target_block_count") or 0)
                == required_restore_block_count,
                int(row.get("gpu_target_block_count") or 0) == 0,
                row_capture_exact(row),
                row.get("restore_group_eligibility_complete") is True,
            )
        )

    full_was_observed = any(
        physical_window_exact(row) for row in candidates
    )
    last_full_timestamp_ns = max(
        (
            int(row.get("timestamp_ns") or 0)
            for row in candidates
            if physical_window_exact(row)
        ),
        default=0,
    )
    cpu_evictions_after_full = [
        row
        for row in cpu_evictions
        if int(row.get("timestamp_ns") or 0) > last_full_timestamp_ns
    ]

    if not candidates:
        decision = "unobservable"
    elif observed != required_restore_block_count:
        decision = "insufficient_restore_coverage"
    elif (
        require_effective_group_geometry
        and latest.get("target_logical_coverage_exact") is not True
    ):
        decision = "effective_group_geometry_incomplete"
    elif not capture_exact or not keyspace_matchable:
        decision = "target_keyspace_unaligned"
    elif not groups_captured or group_count <= 0 or not groups_complete:
        decision = "restore_groups_incomplete"
    elif cpu_evictions_after_full or (
        full_was_observed
        and cpu_count
        < (
            int(
                latest.get("target_fa_required_physical_key_count")
                or 0
            )
            if require_effective_group_geometry
            else required_restore_block_count
        )
    ):
        decision = "cpu_target_lost"
    elif physical_window_exact(latest):
        decision = "trigger_ready"
    else:
        decision = "continue_pressure"
    return {
        "schema_version": "p8_2_k1a_r5_f1_r4_restore_eligibility_gate_v1",
        "decision": decision,
        "restore_allowed": decision == "trigger_ready",
        "required_restore_block_count": required_restore_block_count,
        "observed_target_block_count": observed,
        "latest_cpu_target_block_count": cpu_count,
        "latest_gpu_target_block_count": gpu_count,
        "target_capture_cardinality_exact": cardinality_exact,
        "target_keyspace_matchable": keyspace_matchable,
        "target_capture_exact": capture_exact,
        "restore_group_count": group_count,
        "restore_groups_captured_exact": groups_captured,
        "restore_group_eligibility_complete": groups_complete,
        "cpu_target_eviction_observed": bool(cpu_evictions),
        "cpu_target_eviction_after_full_window_observed": bool(
            cpu_evictions_after_full
        ),
        "raw_hash_values_retained": False,
        "effective_group_geometry_required": (
            require_effective_group_geometry
        ),
        "target_fa_required_physical_key_count": int(
            latest.get("target_fa_required_physical_key_count") or 0
        ),
        "target_logical_coverage_exact": (
            latest.get("target_logical_coverage_exact") is True
        ),
        "physical_target_window_exact": (
            latest.get("physical_target_window_exact") is True
        ),
    }


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
    with (root / f"h2d-residency.{os.getpid()}.jsonl").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")


def _register_pools(scheduler: Any) -> None:
    cpu_pool = getattr(scheduler, "cpu_block_pool", None)
    gpu_pool = getattr(scheduler, "_gpu_block_pool", None)
    for pool, tier in ((cpu_pool, "cpu"), (gpu_pool, "gpu")):
        if pool is None:
            continue
        _POOL_TIERS[id(pool)] = tier
        _POOL_SCHEDULERS[id(pool)] = weakref.ref(scheduler)


def _target_residency_counts(scheduler: Any) -> tuple[int, int]:
    summary = dict(
        getattr(scheduler, "_p8_2_k1a_logical_restore_summary", {})
    )
    return (
        int(summary.get("cpu_target_block_count") or 0),
        int(summary.get("gpu_target_block_count") or 0),
    )


def _capture_restore_group_hashes(
    scheduler: Any,
    block_ids: Any,
    *,
    restore_match_tokens: int,
) -> tuple[
    tuple[tuple[Any, ...], ...],
    tuple[int, ...],
    tuple[dict[str, Any], ...],
]:
    gpu_pool = scheduler._gpu_block_pool
    groups = scheduler.cpu_kv_cache_config.kv_cache_groups
    hashes_by_group: list[tuple[Any, ...]] = []
    required_by_group: list[int] = []
    geometry_by_group: list[dict[str, Any]] = []
    for group_index, group in enumerate(groups):
        runtime_geometry = derive_runtime_group_geometry(
            scheduler,
            group_index=group_index,
            group=group,
            restore_match_tokens=restore_match_tokens,
        )
        effective_block_size = int(
            runtime_geometry["effective_block_size_tokens"]
        )
        if restore_match_tokens % effective_block_size != 0:
            hashes_by_group.append(())
            required_by_group.append(-1)
            geometry_by_group.append(
                {
                    **runtime_geometry,
                    "group_index": group_index,
                    "restore_match_tokens_required": restore_match_tokens,
                    "effective_block_size_tokens": effective_block_size,
                    "theoretical_block_count": -1,
                    "provided_block_id_count": len(block_ids[group_index]),
                    "selected_block_id_count": 0,
                    "non_null_block_count": 0,
                    "hashable_block_count": 0,
                    "unhashable_non_null_block_count": 0,
                    "required_block_count": -1,
                    "group_applicable": False,
                    "selected_geometry_exact": False,
                    "hash_capture_exact": False,
                    "logical_coverage_exact": False,
                    "capture_basis": "unaligned_group_geometry",
                    "raw_block_ids_retained": False,
                    "raw_hash_values_retained": False,
                }
            )
            continue
        hashes, geometry = capture_restore_group_hashes(
            group_index=group_index,
            group_block_ids=list(block_ids[group_index]),
            block_lookup=gpu_pool.blocks,
            restore_match_tokens=restore_match_tokens,
            effective_block_size_tokens=effective_block_size,
        )
        geometry = {**geometry, **runtime_geometry}
        hashes_by_group.append(hashes)
        required_by_group.append(
            int(geometry.get("required_block_count") or 0)
        )
        geometry_by_group.append(geometry)
    return (
        tuple(hashes_by_group),
        tuple(required_by_group),
        tuple(geometry_by_group),
    )


def _unique_keys(groups: tuple[tuple[Any, ...], ...]) -> tuple[Any, ...]:
    values: list[Any] = []
    seen: set[Any] = set()
    for group in groups:
        for value in group:
            if value not in seen:
                seen.add(value)
                values.append(value)
    return tuple(values)


def _capture_target_store_lineage(
    scheduler: Any,
    block_ids: Any,
    *,
    restore_match_tokens: int,
    hash_block_size_tokens: int,
) -> dict[str, Any]:
    hashes_by_group, required_by_group, geometry_by_group = (
        _capture_restore_group_hashes(
            scheduler,
            block_ids,
            restore_match_tokens=restore_match_tokens,
        )
    )
    target_keys = _unique_keys(hashes_by_group)
    scheduler._p8_2_k1a_restore_group_hashes = hashes_by_group
    scheduler._p8_2_k1a_restore_group_required_counts = required_by_group
    scheduler._p8_2_k1a_restore_group_geometry_rows = geometry_by_group
    scheduler._p8_2_k1a_target_store_keys = target_keys
    scheduler._p8_2_k1a_target_pool_keys = target_keys
    scheduler._p8_2_k1a_target_hashes = target_keys
    target_set = set(target_keys)
    cpu_pool = getattr(scheduler, "cpu_block_pool", None)
    completed = (
        {
            value
            for value in target_keys
            if cpu_pool.cached_block_hash_to_block.get_one_block(value)
            is not None
        }
        if cpu_pool is not None
        else set()
    )
    pending: set[Any] = set()
    for transfer in (
        getattr(scheduler, "_store_event_to_blocks", {}) or {}
    ).values():
        for block_id in getattr(transfer, "cpu_block_ids", ()) or ():
            block_hash = scheduler.cpu_block_pool.blocks[
                block_id
            ].block_hash
            if block_hash in target_set:
                pending.add(block_hash)
    scheduler._p8_2_k1a_target_store_scheduled_keys = (
        completed | pending
    )
    scheduler._p8_2_k1a_target_store_completed_keys = completed
    scheduler._p8_2_k1a_target_cpu_evicted_keys = set()
    scheduler._p8_2_k1a_target_gpu_evicted_keys = set()
    scheduler._p8_2_k1a_target_fa_group_index = int(
        getattr(scheduler, "fa_gidx", -1)
    )
    scheduler._p8_2_k1a_target_logical_block_count = (
        restore_match_tokens // hash_block_size_tokens
    )
    scheduler._p8_2_k1a_target_restore_match_tokens = restore_match_tokens
    return _target_store_lineage_residency_summary(scheduler)


def _target_store_lineage_residency_summary(
    scheduler: Any,
) -> dict[str, Any]:
    hashes_by_group = tuple(
        getattr(scheduler, "_p8_2_k1a_restore_group_hashes", ()) or ()
    )
    if not hashes_by_group:
        return {}
    required_by_group = tuple(
        getattr(
            scheduler, "_p8_2_k1a_restore_group_required_counts", ()
        )
        or ()
    )
    geometry_by_group = tuple(
        getattr(
            scheduler, "_p8_2_k1a_restore_group_geometry_rows", ()
        )
        or ()
    )
    cpu_pool = getattr(scheduler, "cpu_block_pool", None)
    gpu_pool = getattr(scheduler, "_gpu_block_pool", None)

    def count(pool: Any, hashes: tuple[Any, ...]) -> int:
        if pool is None:
            return 0
        mapping = pool.cached_block_hash_to_block
        return sum(
            mapping.get_one_block(value) is not None for value in hashes
        )

    rows = []
    for group_index, hashes in enumerate(hashes_by_group):
        required = (
            required_by_group[group_index]
            if group_index < len(required_by_group)
            else len(hashes)
        )
        geometry = (
            dict(geometry_by_group[group_index])
            if group_index < len(geometry_by_group)
            else {}
        )
        rows.append(
            {
                **geometry,
                "group_index": group_index,
                "required_block_count": required,
                "captured_block_count": len(hashes),
                "cpu_block_count": count(cpu_pool, hashes),
                "gpu_block_count": count(gpu_pool, hashes),
                "capture_basis": (
                    "target_finish_gpu_group_wrapped_keys"
                ),
            }
        )
    group_summary = build_restore_group_residency_summary(rows)
    target_keys = tuple(
        getattr(scheduler, "_p8_2_k1a_target_store_keys", ()) or ()
    )
    fa_group_index = int(
        getattr(scheduler, "_p8_2_k1a_target_fa_group_index", -1)
    )
    fa_keys = (
        hashes_by_group[fa_group_index]
        if 0 <= fa_group_index < len(hashes_by_group)
        else ()
    )
    logical_block_count = int(
        getattr(scheduler, "_p8_2_k1a_target_logical_block_count", 0)
        or 0
    )
    geometry_by_index = {
        int(row.get("group_index") or 0): row for row in geometry_by_group
    }
    fa_geometry = geometry_by_index.get(fa_group_index, {})
    fa_required_physical_key_count = int(
        fa_geometry.get("physical_key_count_required") or 0
    )
    restore_match_tokens = int(
        getattr(scheduler, "_p8_2_k1a_target_restore_match_tokens", 0)
        or 0
    )
    fa_effective_block_size = int(
        fa_geometry.get("effective_block_size_tokens") or 0
    )
    target_logical_coverage_exact = all(
        (
            logical_block_count > 0,
            fa_required_physical_key_count > 0,
            len(fa_keys) == fa_required_physical_key_count,
            fa_required_physical_key_count * fa_effective_block_size
            == restore_match_tokens,
            fa_geometry.get("effective_geometry_aligned") is True,
            fa_geometry.get("selected_geometry_exact") is True,
            fa_geometry.get("hash_capture_exact") is True,
        )
    )
    fa_capture_exact = all(
        (
            target_logical_coverage_exact,
            fa_geometry.get("logical_coverage_exact") is True,
        )
    )
    scheduled = set(
        getattr(
            scheduler, "_p8_2_k1a_target_store_scheduled_keys", set()
        )
        or set()
    )
    completed = set(
        getattr(
            scheduler, "_p8_2_k1a_target_store_completed_keys", set()
        )
        or set()
    )
    cpu_evicted = set(
        getattr(scheduler, "_p8_2_k1a_target_cpu_evicted_keys", set())
        or set()
    )
    gpu_evicted = set(
        getattr(scheduler, "_p8_2_k1a_target_gpu_evicted_keys", set())
        or set()
    )
    fa_set = set(fa_keys)
    cpu_matches = count(cpu_pool, target_keys)
    gpu_matches = count(gpu_pool, target_keys)
    cpu_fa_matches = count(cpu_pool, fa_keys)
    gpu_fa_matches = count(gpu_pool, fa_keys)
    physical_target_window_exact = all(
        (
            target_logical_coverage_exact,
            fa_capture_exact,
            cpu_fa_matches == fa_required_physical_key_count,
            gpu_fa_matches == 0,
            group_summary["restore_group_eligibility_complete"] is True,
        )
    )
    return {
        "target_store_lineage_capture_exact": all(
            (
                fa_capture_exact,
                group_summary["restore_groups_captured_exact"] is True,
                bool(target_keys),
            )
        ),
        "target_store_key_count": len(target_keys),
        "target_store_scheduled_key_count": len(scheduled),
        "target_store_completed_key_count": len(completed),
        "target_cpu_evicted_key_count": len(cpu_evicted),
        "target_gpu_evicted_key_count": len(gpu_evicted),
        "target_fa_group_index": fa_group_index,
        "target_fa_key_count": len(fa_keys),
        "target_fa_required_physical_key_count": (
            fa_required_physical_key_count
        ),
        "target_fa_capture_exact": fa_capture_exact,
        "target_logical_block_count": logical_block_count,
        "target_logical_coverage_tokens": restore_match_tokens,
        "target_logical_coverage_exact": target_logical_coverage_exact,
        "physical_target_window_exact": physical_target_window_exact,
        "target_fa_store_scheduled_key_count": len(scheduled & fa_set),
        "target_fa_store_completed_key_count": len(completed & fa_set),
        "target_fa_cpu_evicted_key_count": len(cpu_evicted & fa_set),
        "target_fa_gpu_evicted_key_count": len(gpu_evicted & fa_set),
        "target_pool_key_count": len(target_keys),
        "cpu_target_pool_key_match_count": cpu_matches,
        "gpu_target_pool_key_match_count": gpu_matches,
        "target_count_unit": "logical_request_hash_blocks",
        "cpu_target_count_unit": "physical_full_attention_group_keys",
        "gpu_target_count_unit": "physical_full_attention_group_keys",
        "target_pool_key_count_unit": "runtime_group_wrapped_pool_keys",
        "cpu_target_block_count": cpu_fa_matches,
        "gpu_target_block_count": gpu_fa_matches,
        **group_summary,
        "raw_block_ids_retained": False,
        "raw_hash_values_retained": False,
    }


def _target_store_event_overlap(
    scheduler: Any,
    keys: tuple[Any, ...],
) -> dict[str, Any]:
    target_groups = tuple(
        getattr(scheduler, "_p8_2_k1a_restore_group_hashes", ()) or ()
    )
    selected = set(keys)
    group_counts = [
        len(selected & set(group))
        for group in target_groups
    ]
    fa_group_index = int(
        getattr(scheduler, "_p8_2_k1a_target_fa_group_index", -1)
    )
    return {
        "target_store_event_key_count": sum(group_counts),
        "target_store_event_fa_key_count": (
            group_counts[fa_group_index]
            if 0 <= fa_group_index < len(group_counts)
            else 0
        ),
        "target_store_event_group_key_counts": group_counts,
        "raw_hash_values_retained": False,
    }


def _restore_group_residency_summary(scheduler: Any) -> dict[str, Any]:
    lineage = _target_store_lineage_residency_summary(scheduler)
    if lineage:
        return {
            key: lineage[key]
            for key in (
                "restore_group_count",
                "restore_group_applicable_count",
                "restore_groups_captured_exact_count",
                "restore_groups_captured_exact",
                "restore_groups_cpu_complete_count",
                "restore_groups_gpu_absent_count",
                "restore_group_eligibility_complete",
                "restore_group_rows",
            )
            if key in lineage
        }
    logical = dict(
        getattr(scheduler, "_p8_2_k1a_logical_restore_summary", {})
    )
    if "restore_group_rows" in logical:
        return {
            key: logical[key]
            for key in (
                "restore_group_count",
                "restore_group_applicable_count",
                "restore_groups_captured_exact_count",
                "restore_groups_captured_exact",
                "restore_groups_cpu_complete_count",
                "restore_groups_gpu_absent_count",
                "restore_group_eligibility_complete",
                "restore_group_rows",
            )
            if key in logical
        }
    hashes_by_group = tuple(
        getattr(scheduler, "_p8_2_k1a_restore_group_hashes", ())
    )
    required_by_group = tuple(
        getattr(scheduler, "_p8_2_k1a_restore_group_required_counts", ())
    )
    geometry_by_group = tuple(
        getattr(scheduler, "_p8_2_k1a_restore_group_geometry_rows", ())
    )
    cpu_pool = getattr(scheduler, "cpu_block_pool", None)
    gpu_pool = getattr(scheduler, "_gpu_block_pool", None)

    def count(pool: Any, hashes: tuple[Any, ...]) -> int:
        if pool is None:
            return 0
        mapping = pool.cached_block_hash_to_block
        return sum(mapping.get_one_block(value) is not None for value in hashes)

    rows = []
    for group_index, required in enumerate(required_by_group):
        hashes = hashes_by_group[group_index] if group_index < len(hashes_by_group) else ()
        geometry = (
            dict(geometry_by_group[group_index])
            if group_index < len(geometry_by_group)
            else {}
        )
        rows.append(
            {
                **geometry,
                "group_index": group_index,
                "required_block_count": required,
                "captured_block_count": len(hashes),
                "cpu_block_count": count(cpu_pool, hashes),
                "gpu_block_count": count(gpu_pool, hashes),
            }
        )
    return build_restore_group_residency_summary(rows)


def build_request_local_pressure_progress(
    scheduler_output: Any,
    *,
    contract_role: str | None,
    target_block_count: int,
    cpu_target_block_count: int,
    gpu_target_block_count: int,
    restore_group_summary: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not contract_role or not contract_role.startswith("pressure_"):
        return None

    scheduled = dict(getattr(scheduler_output, "num_scheduled_tokens", {}))
    request_ids = [
        request_id
        for request_id, count in scheduled.items()
        if int(count or 0) > 0
    ]
    if not request_ids:
        return None
    computed_before: dict[str, int] = {}
    for request in getattr(scheduler_output, "scheduled_new_reqs", ()):
        computed_before[str(request.req_id)] = int(request.num_computed_tokens)
    cached = getattr(scheduler_output, "scheduled_cached_reqs", None)
    if cached is not None:
        computed_before.update(
            {
                str(request_id): int(count)
                for request_id, count in zip(
                    getattr(cached, "req_ids", ()),
                    getattr(cached, "num_computed_tokens", ()),
                )
            }
        )

    exact = len(request_ids) == 1 and request_ids[0] in computed_before
    before = computed_before[request_ids[0]] if exact else None
    scheduled_tokens = int(scheduled[request_ids[0]]) if exact else None
    return {
        "schema_version": "p8_2_k1a_r5_f1_r1_request_local_progress_v1",
        "contract_role": contract_role,
        "scheduled_request_count": len(request_ids),
        "request_local_progress_exact": exact,
        "num_computed_tokens_before_schedule": before,
        "num_scheduled_tokens": scheduled_tokens,
        "num_computed_tokens_after_schedule": (
            before + scheduled_tokens if exact else None
        ),
        "target_block_count": target_block_count,
        "cpu_target_block_count": cpu_target_block_count,
        "gpu_target_block_count": gpu_target_block_count,
        **(restore_group_summary or {}),
        "request_id_retained": False,
        "token_ids_retained": False,
        "generated_content_retained": False,
    }


def build_refreshed_request_local_pressure_progress(
    scheduler: Any,
    scheduler_output: Any,
    *,
    contract_role: str | None,
    target_block_count: int,
    restore_match_tokens: int,
    hash_block_size_tokens: int,
    logical_summary: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Refresh the runtime keyspace before evaluating one pressure step."""

    if not contract_role or not contract_role.startswith("pressure_"):
        return None
    summary = (
        refresh_logical_restore_window(
            scheduler,
            restore_match_tokens=restore_match_tokens,
            hash_block_size_tokens=hash_block_size_tokens,
        )
        if logical_summary is None
        else dict(logical_summary)
    )
    summary["logical_keyspace_probe_reason"] = (
        "pressure_request_local_progress"
    )
    return build_request_local_pressure_progress(
        scheduler_output,
        contract_role=contract_role,
        target_block_count=target_block_count,
        cpu_target_block_count=int(
            summary.get("cpu_target_block_count") or 0
        ),
        gpu_target_block_count=int(
            summary.get("gpu_target_block_count") or 0
        ),
        restore_group_summary={
            **summary,
            **_restore_group_residency_summary(scheduler),
        },
    )


def _emit_residency_snapshot(
    scheduler: Any,
    *,
    reason: str,
    restore_match_tokens: int,
    hash_block_size_tokens: int,
) -> dict[str, Any] | None:
    request_hashes = tuple(
        getattr(scheduler, "_p8_2_k1a_target_request_hashes", ())
    )
    if not request_hashes:
        return None
    summary = refresh_logical_restore_window(
        scheduler,
        restore_match_tokens=restore_match_tokens,
        hash_block_size_tokens=hash_block_size_tokens,
    )
    cpu_pool = scheduler.cpu_block_pool
    gpu_pool = scheduler._gpu_block_pool
    _emit(
        "target_residency_snapshot",
        component="scheduler",
        reason=reason,
        target_block_count=restore_match_tokens // hash_block_size_tokens,
        **summary,
        cpu_free_block_count=cpu_pool.get_num_free_blocks(),
        gpu_free_block_count=(
            gpu_pool.get_num_free_blocks() if gpu_pool is not None else None
        ),
    )
    return summary


def install_p8_2_k1a_h2d_residency_observer() -> None:
    from vllm.v1.core.block_pool import BlockPool
    from vllm.v1.simple_kv_offload.manager import SimpleCPUOffloadScheduler

    marker = "_p8_2_k1a_h2d_residency_observer_installed"
    if getattr(SimpleCPUOffloadScheduler, marker, False):
        return

    target_suffix = os.environ.get(TARGET_SUFFIX_ENV, "target_prime")
    restore_suffix = os.environ.get(RESTORE_SUFFIX_ENV, "restore_follower")
    target_block_count = int(os.environ.get(TARGET_BLOCK_COUNT_ENV, "64"))
    restore_match_tokens = int(os.environ.get(RESTORE_MATCH_TOKENS_ENV, "16384"))
    block_size_tokens = int(os.environ.get(BLOCK_SIZE_TOKENS_ENV, "128"))
    require_restore_group_eligibility = (
        os.environ.get("P8_2_K1A_REQUIRE_RESTORE_GROUP_ELIGIBILITY", "0") == "1"
    )
    eligibility_contract = validate_effective_restore_contract(
        target_block_count=target_block_count,
        restore_match_tokens=restore_match_tokens,
        block_size_tokens=block_size_tokens,
        require_restore_group_eligibility=require_restore_group_eligibility,
    )

    original_finished = SimpleCPUOffloadScheduler.request_finished_all_groups

    @wraps(original_finished)
    def observed_finished(self, request, block_ids):
        _register_pools(self)
        contract_role = _active_contract_role()
        is_target = contract_role == "target_prime" or str(
            request.request_id
        ).endswith(target_suffix)
        is_pressure = bool(
            contract_role and contract_role.startswith("pressure_")
        )
        request_hashes = tuple(
            getattr(request, "block_hashes", ()) or ()
        )
        if is_target:
            self._p8_2_k1a_target_request_hashes = request_hashes
            lineage_capture = _capture_target_store_lineage(
                self,
                block_ids,
                restore_match_tokens=restore_match_tokens,
                hash_block_size_tokens=block_size_tokens,
            )
            _emit(
                "target_store_lineage_captured",
                component="scheduler",
                contract_role=contract_role,
                target_block_count=target_block_count,
                **eligibility_contract,
                **lineage_capture,
            )
        result = original_finished(self, request, block_ids)
        if is_target:
            target_capture_summary = refresh_logical_restore_window(
                self,
                restore_match_tokens=restore_match_tokens,
                hash_block_size_tokens=block_size_tokens,
            )
            _emit(
                "target_hashes_captured",
                component="scheduler",
                request_id=request.request_id,
                contract_role=contract_role,
                target_block_count=target_block_count,
                **eligibility_contract,
                **target_capture_summary,
            )
            _emit_residency_snapshot(
                self,
                reason="target_request_finished",
                restore_match_tokens=restore_match_tokens,
                hash_block_size_tokens=block_size_tokens,
            )
        elif is_pressure:
            _emit_residency_snapshot(
                self,
                reason="pressure_request_finished",
                restore_match_tokens=restore_match_tokens,
                hash_block_size_tokens=block_size_tokens,
            )
        return result

    original_prepare_lazy = (
        SimpleCPUOffloadScheduler._prepare_lazy_store_specs
    )

    @wraps(original_prepare_lazy)
    def observed_prepare_lazy(self):
        result = original_prepare_lazy(self)
        gpu_ids, cpu_ids, request_ids = result
        target_keys = set(
            getattr(self, "_p8_2_k1a_target_store_keys", ()) or ()
        )
        if target_keys and cpu_ids:
            scheduled_keys = {
                self.cpu_block_pool.blocks[block_id].block_hash
                for block_id in cpu_ids
            } & target_keys
            if scheduled_keys:
                cumulative = set(
                    getattr(
                        self,
                        "_p8_2_k1a_target_store_scheduled_keys",
                        set(),
                    )
                    or set()
                )
                cumulative.update(scheduled_keys)
                self._p8_2_k1a_target_store_scheduled_keys = cumulative
                event_summary = {
                    **_target_store_event_overlap(
                        self, tuple(scheduled_keys)
                    ),
                    **_target_store_lineage_residency_summary(self),
                }
                _emit(
                    "target_store_scheduled",
                    component="scheduler",
                    contract_role=_active_contract_role(),
                    store_event_candidate_index=int(
                        getattr(self, "_store_event_counter", 0) or 0
                    ),
                    store_total_block_count=len(cpu_ids),
                    **event_summary,
                )
        return gpu_ids, cpu_ids, request_ids

    original_process_store_event = (
        SimpleCPUOffloadScheduler._process_store_event
    )

    @wraps(original_process_store_event)
    def observed_process_store_event(self, event_idx):
        transfer = self._store_event_to_blocks.get(event_idx)
        target_keys = set(
            getattr(self, "_p8_2_k1a_target_store_keys", ()) or ()
        )
        completed_keys: set[Any] = set()
        if transfer is not None and target_keys:
            completed_keys = {
                self.cpu_block_pool.blocks[block_id].block_hash
                for block_id in transfer.cpu_block_ids
            } & target_keys
        result = original_process_store_event(self, event_idx)
        if completed_keys:
            cumulative = set(
                getattr(
                    self,
                    "_p8_2_k1a_target_store_completed_keys",
                    set(),
                )
                or set()
            )
            cumulative.update(completed_keys)
            self._p8_2_k1a_target_store_completed_keys = cumulative
            event_summary = {
                **_target_store_event_overlap(
                    self, tuple(completed_keys)
                ),
                **_target_store_lineage_residency_summary(self),
            }
            _emit(
                "target_store_completed",
                component="scheduler",
                contract_role=_active_contract_role(),
                store_event_index=int(event_idx),
                **event_summary,
            )
        return result

    original_match = SimpleCPUOffloadScheduler.get_num_new_matched_tokens

    @wraps(original_match)
    def observed_match(self, request, num_computed_tokens):
        _register_pools(self)
        contract_role = _active_contract_role()
        if contract_role == "restore_follower" or str(request.request_id).endswith(
            restore_suffix
        ):
            _emit_residency_snapshot(
                self,
                reason="before_restore_match",
                restore_match_tokens=restore_match_tokens,
                hash_block_size_tokens=block_size_tokens,
            )
        return original_match(self, request, num_computed_tokens)

    original_update = SimpleCPUOffloadScheduler.update_state_after_alloc

    @wraps(original_update)
    def observed_update(self, request, blocks, num_external_tokens):
        result = original_update(self, request, blocks, num_external_tokens)
        _register_pools(self)
        contract_role = _active_contract_role()
        if contract_role == "restore_follower" or str(request.request_id).endswith(
            restore_suffix
        ):
            _emit_residency_snapshot(
                self,
                reason="after_restore_alloc",
                restore_match_tokens=restore_match_tokens,
                hash_block_size_tokens=block_size_tokens,
            )
        return result

    original_build = SimpleCPUOffloadScheduler.build_connector_meta

    @wraps(original_build)
    def observed_build(self, scheduler_output):
        result = original_build(self, scheduler_output)
        _register_pools(self)
        logical_summary = _emit_residency_snapshot(
            self,
            reason="after_connector_meta",
            restore_match_tokens=restore_match_tokens,
            hash_block_size_tokens=block_size_tokens,
        )
        if os.environ.get(REQUEST_LOCAL_PRESSURE_OBSERVER_ENV) == "1":
            progress = build_refreshed_request_local_pressure_progress(
                self,
                scheduler_output,
                contract_role=_active_contract_role(),
                target_block_count=target_block_count,
                restore_match_tokens=restore_match_tokens,
                hash_block_size_tokens=block_size_tokens,
                logical_summary=logical_summary,
            )
            if progress is not None:
                _emit("request_local_pressure_progress", **progress)
        return result

    original_output = SimpleCPUOffloadScheduler.update_connector_output

    @wraps(original_output)
    def observed_output(self, connector_output):
        result = original_output(self, connector_output)
        _register_pools(self)
        _emit_residency_snapshot(
            self,
            reason="after_connector_output",
            restore_match_tokens=restore_match_tokens,
            hash_block_size_tokens=block_size_tokens,
        )
        return result

    original_evict = BlockPool._maybe_evict_cached_block

    @wraps(original_evict)
    def observed_evict(self, block):
        old_hash = block.block_hash
        result = original_evict(self, block)
        owner_ref = _POOL_SCHEDULERS.get(id(self))
        scheduler = owner_ref() if owner_ref is not None else None
        target_hashes = (
            tuple(getattr(scheduler, "_p8_2_k1a_target_hashes", ()))
            if scheduler is not None
            else ()
        )
        if result and old_hash is not None and old_hash in target_hashes:
            tier = _POOL_TIERS.get(id(self), "unknown")
            if scheduler is not None:
                field = (
                    "_p8_2_k1a_target_cpu_evicted_keys"
                    if tier == "cpu"
                    else "_p8_2_k1a_target_gpu_evicted_keys"
                )
                evicted = set(getattr(scheduler, field, set()) or set())
                evicted.add(old_hash)
                setattr(scheduler, field, evicted)
            _emit(
                "target_cache_evicted",
                component="block_pool",
                tier=tier,
                target_evicted_count=1,
                target_cpu_evicted_key_count=len(
                    getattr(
                        scheduler,
                        "_p8_2_k1a_target_cpu_evicted_keys",
                        set(),
                    )
                    or set()
                )
                if scheduler is not None
                else 0,
                target_gpu_evicted_key_count=len(
                    getattr(
                        scheduler,
                        "_p8_2_k1a_target_gpu_evicted_keys",
                        set(),
                    )
                    or set()
                )
                if scheduler is not None
                else 0,
                raw_hash_values_retained=False,
            )
            _emit_residency_snapshot(
                scheduler,
                reason="after_target_eviction",
                restore_match_tokens=restore_match_tokens,
                hash_block_size_tokens=block_size_tokens,
            )
        return result

    SimpleCPUOffloadScheduler.request_finished_all_groups = observed_finished
    SimpleCPUOffloadScheduler._prepare_lazy_store_specs = (
        observed_prepare_lazy
    )
    SimpleCPUOffloadScheduler._process_store_event = (
        observed_process_store_event
    )
    SimpleCPUOffloadScheduler.get_num_new_matched_tokens = observed_match
    SimpleCPUOffloadScheduler.update_state_after_alloc = observed_update
    SimpleCPUOffloadScheduler.build_connector_meta = observed_build
    SimpleCPUOffloadScheduler.update_connector_output = observed_output
    BlockPool._maybe_evict_cached_block = observed_evict
    setattr(SimpleCPUOffloadScheduler, marker, True)
    _emit(
        "h2d_residency_observer_installed",
        component="runtime_patch",
        observer_mode="observe_only_no_decision_request_order_or_copy_mutation",
        raw_hash_values_emitted=False,
    )
    if os.environ.get(REQUEST_LOCAL_PRESSURE_OBSERVER_ENV) == "1":
        _emit(
            "request_local_pressure_observer_installed",
            component="runtime_patch",
            observer_mode="observe_only_no_decision_request_order_or_copy_mutation",
            request_id_retained=False,
            token_ids_retained=False,
            generated_content_retained=False,
        )


def observer_self_test_contract() -> dict[str, Any]:
    return {
        "schema_version": "p8_2_k1a_h2d_residency_observer_contract_v1",
        "observer_mode": "observe_only_no_decision_request_order_or_copy_mutation",
        "wrapped_scheduler_methods": [
            "request_finished_all_groups",
            "_prepare_lazy_store_specs",
            "_process_store_event",
            "get_num_new_matched_tokens",
            "update_state_after_alloc",
            "build_connector_meta",
            "update_connector_output",
        ],
        "wrapped_block_pool_methods": ["_maybe_evict_cached_block"],
        "original_return_values_preserved": True,
        "original_exceptions_preserved": True,
        "scheduling_or_copy_arguments_mutated": False,
        "raw_hash_values_emitted": False,
        "generated_content_or_token_ids_emitted": False,
        "target_block_count_is_explicit_and_bounded": True,
        "restore_eligibility_geometry_is_explicit": True,
        "restore_eligibility_all_kv_groups_observed": True,
        "restore_group_rows_are_bounded_counts_only": True,
        "request_hashes_are_not_assumed_to_be_pool_keys": True,
        "logical_restore_lookup_source": (
            "runtime_cpu_coordinator_find_longest_cache_hit"
        ),
        "logical_restore_lookup_is_read_only": True,
        "runtime_lookup_side_effect_field_restored": True,
        "logical_restore_target_count_unit": "logical_request_hash_blocks",
        "runtime_pool_keys_retained_in_process_only": True,
        "target_group_wrapped_keys_captured_before_request_finish": True,
        "target_lazy_store_schedule_and_completion_attribution": True,
        "zero_key_restore_groups_are_not_counted_complete": True,
        "request_identity_source": "controller_role_marker_not_server_request_id",
        "request_local_pressure_progress_capability": True,
        "request_local_progress_source": (
            "SchedulerOutput.num_scheduled_tokens_and_request_num_computed_tokens"
        ),
        "request_local_progress_requires_single_scheduled_request": True,
        "request_id_retained": False,
    }


def summarize_target_store_lineage_rows(
    rows: list[dict[str, Any]],
    *,
    target_block_count: int,
) -> dict[str, Any]:
    captures = [
        row
        for row in rows
        if row.get("event") == "target_store_lineage_captured"
    ]
    scheduled = [
        row for row in rows if row.get("event") == "target_store_scheduled"
    ]
    completed = [
        row for row in rows if row.get("event") == "target_store_completed"
    ]
    observed = [
        row
        for row in rows
        if row.get("event")
        in {
            "target_store_lineage_captured",
            "target_hashes_captured",
            "target_store_completed",
            "target_residency_snapshot",
            "request_local_pressure_progress",
        }
        and "target_store_lineage_capture_exact" in row
    ]
    evictions = [
        row
        for row in rows
        if row.get("event") == "target_cache_evicted"
    ]

    def maximum(field: str, selected: list[dict[str, Any]]) -> int:
        return max(
            (int(row.get(field) or 0) for row in selected),
            default=0,
        )

    physical_cpu_only = [
        row
        for row in observed
        if row.get("target_store_lineage_capture_exact") is True
        and (
            row.get("physical_target_window_exact") is True
            or (
                "physical_target_window_exact" not in row
                and int(row.get("cpu_target_block_count") or 0)
                == target_block_count
                and int(row.get("gpu_target_block_count") or 0) == 0
                and row.get("restore_group_eligibility_complete") is True
            )
        )
    ]
    logical_and_physical = [
        row
        for row in physical_cpu_only
        if row.get("logical_restore_window_exact") is True
    ]
    latest = observed[-1] if observed else {}
    captured = captures[-1] if captures else {}
    target_store_key_count = int(
        captured.get("target_store_key_count")
        or maximum("target_store_key_count", observed)
    )
    fa_key_count = int(
        captured.get("target_fa_key_count")
        or maximum("target_fa_key_count", observed)
    )
    fa_required_physical_key_count = int(
        captured.get("target_fa_required_physical_key_count")
        or maximum("target_fa_required_physical_key_count", observed)
        or target_block_count
    )
    scheduled_max = max(
        maximum("target_store_scheduled_key_count", scheduled),
        maximum("target_store_scheduled_key_count", observed),
    )
    completed_max = max(
        maximum("target_store_completed_key_count", completed),
        maximum("target_store_completed_key_count", observed),
    )
    fa_scheduled_max = max(
        maximum("target_fa_store_scheduled_key_count", scheduled),
        maximum("target_fa_store_scheduled_key_count", observed),
    )
    fa_completed_max = max(
        maximum("target_fa_store_completed_key_count", completed),
        maximum("target_fa_store_completed_key_count", observed),
    )
    cpu_evicted_count = max(
        maximum("target_cpu_evicted_key_count", evictions),
        maximum("target_cpu_evicted_key_count", observed),
    )
    gpu_evicted_count = max(
        maximum("target_gpu_evicted_key_count", evictions),
        maximum("target_gpu_evicted_key_count", observed),
    )
    if not captures:
        attribution = "target_finish_key_capture_missing"
    elif captured.get("target_store_lineage_capture_exact") is not True:
        attribution = "target_finish_key_capture_incomplete"
    elif scheduled_max == 0:
        attribution = "target_keys_never_scheduled_for_d2h"
    elif completed_max < scheduled_max:
        attribution = "target_d2h_store_completion_incomplete"
    elif fa_completed_max < fa_required_physical_key_count:
        attribution = "full_attention_target_d2h_incomplete"
    elif not physical_cpu_only and cpu_evicted_count > 0:
        attribution = "target_cpu_evicted_before_complete_cpu_only_window"
    elif physical_cpu_only and not logical_and_physical:
        attribution = (
            "physical_cpu_only_window_not_accepted_by_logical_coordinator"
        )
    elif logical_and_physical:
        attribution = "physical_and_logical_restore_window_observed"
    else:
        attribution = "target_d2h_complete_without_cpu_only_window"

    bounded_group_rows = []
    for row in captured.get("restore_group_rows") or ():
        bounded_group_rows.append(
            {
                key: row[key]
                for key in (
                    "group_index",
                    "restore_match_tokens_required",
                    "base_block_size_tokens",
                    "cp_world_size",
                    "compress_ratio",
                    "effective_block_size_tokens",
                    "physical_key_count_required",
                    "theoretical_block_count",
                    "provided_block_id_count",
                    "selected_block_id_count",
                    "non_null_block_count",
                    "hashable_block_count",
                    "unhashable_non_null_block_count",
                    "required_block_count",
                    "captured_block_count",
                    "group_applicable",
                    "capture_exact",
                    "logical_coverage_exact",
                    "effective_geometry_aligned",
                    "effective_geometry_source",
                    "kv_cache_spec_type",
                )
                if key in row
            }
        )
    return {
        "schema_version": (
            "p8_2_k1a_target_store_lineage_summary_v1"
        ),
        "target_lineage_attribution": attribution,
        "target_store_lineage_capture_event_count": len(captures),
        "target_store_lineage_capture_exact": (
            captured.get("target_store_lineage_capture_exact") is True
        ),
        "target_store_key_count": target_store_key_count,
        "target_fa_key_count": fa_key_count,
        "target_fa_required_physical_key_count": (
            fa_required_physical_key_count
        ),
        "target_fa_capture_exact": (
            captured.get("target_fa_capture_exact") is True
        ),
        "target_logical_block_count": int(
            captured.get("target_logical_block_count")
            or maximum("target_logical_block_count", observed)
            or target_block_count
        ),
        "target_logical_coverage_tokens": int(
            captured.get("target_logical_coverage_tokens")
            or maximum("target_logical_coverage_tokens", observed)
        ),
        "target_logical_coverage_exact": (
            captured.get("target_logical_coverage_exact") is True
        ),
        "target_store_schedule_event_count": len(scheduled),
        "target_store_completion_event_count": len(completed),
        "target_store_scheduled_key_count_max": scheduled_max,
        "target_store_completed_key_count_max": completed_max,
        "target_fa_store_scheduled_key_count_max": fa_scheduled_max,
        "target_fa_store_completed_key_count_max": fa_completed_max,
        "target_cpu_evicted_key_count": cpu_evicted_count,
        "target_gpu_evicted_key_count": gpu_evicted_count,
        "cpu_target_block_count_max": maximum(
            "cpu_target_block_count", observed
        ),
        "gpu_target_block_count_min": min(
            (
                int(row.get("gpu_target_block_count") or 0)
                for row in observed
            ),
            default=0,
        ),
        "physical_cpu_only_window_event_count": len(physical_cpu_only),
        "logical_and_physical_window_event_count": len(
            logical_and_physical
        ),
        "first_physical_cpu_only_window_timestamp_ns": min(
            (
                int(row.get("timestamp_ns") or 0)
                for row in physical_cpu_only
            ),
            default=0,
        ),
        "first_logical_and_physical_window_timestamp_ns": min(
            (
                int(row.get("timestamp_ns") or 0)
                for row in logical_and_physical
            ),
            default=0,
        ),
        "latest_cpu_target_block_count": int(
            latest.get("cpu_target_block_count") or 0
        ),
        "latest_gpu_target_block_count": int(
            latest.get("gpu_target_block_count") or 0
        ),
        "restore_group_count": int(
            captured.get("restore_group_count") or 0
        ),
        "restore_group_applicable_count": int(
            captured.get("restore_group_applicable_count") or 0
        ),
        "restore_group_capture_rows": bounded_group_rows,
        "raw_hash_values_retained": False,
        "raw_block_ids_retained": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
        "generated_content_retained": False,
    }


def _read_trace_dir(trace_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(trace_dir.glob("h2d-residency.*.jsonl")):
        rows.extend(
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        )
    return rows


def build_residency_gate(
    rows: list[dict[str, Any]], *, target_block_count: int
) -> dict[str, Any]:
    def capture_exact(row: dict[str, Any]) -> bool:
        return (
            row.get("target_capture_exact") is True
            if "target_capture_exact" in row
            else True
        )

    def keyspace_matchable(row: dict[str, Any]) -> bool:
        return (
            row.get("target_keyspace_matchable") is True
            if "target_keyspace_matchable" in row
            else capture_exact(row)
        )

    captures = [
        row
        for row in rows
        if row.get("event")
        in {"target_hashes_captured", "target_residency_snapshot"}
        and int(row.get("target_block_count") or 0) == target_block_count
        and capture_exact(row)
        and keyspace_matchable(row)
    ]
    snapshots = [
        row
        for row in rows
        if row.get("event") == "target_residency_snapshot"
        and int(row.get("target_block_count") or 0) == target_block_count
    ]
    cpu_evictions = [
        row
        for row in rows
        if row.get("event") == "target_cache_evicted"
        and row.get("tier") == "cpu"
        and int(row.get("target_evicted_count") or 0) > 0
    ]
    latest = snapshots[-1] if snapshots else {}
    cpu_count = int(latest.get("cpu_target_block_count") or 0)
    gpu_count = int(latest.get("gpu_target_block_count") or 0)
    cpu_was_complete = any(
        int(row.get("cpu_target_block_count") or 0) == target_block_count
        and capture_exact(row)
        and keyspace_matchable(row)
        for row in snapshots
    )

    if not captures or not snapshots:
        decision = "unobservable"
    elif cpu_evictions or (cpu_was_complete and cpu_count < target_block_count):
        decision = "cpu_target_lost"
    elif (
        cpu_count == target_block_count
        and gpu_count == 0
        and capture_exact(latest)
        and keyspace_matchable(latest)
    ):
        decision = "trigger_ready"
    else:
        decision = "continue_pressure"
    return {
        "schema_version": "p8_2_k1a_r5_l1_residency_gate_v1",
        "decision": decision,
        "restore_allowed": decision == "trigger_ready",
        "target_hashes_captured_exact": bool(captures),
        "target_keyspace_matchable": keyspace_matchable(latest),
        "target_capture_exact": capture_exact(latest),
        "target_block_count": target_block_count,
        "latest_cpu_target_block_count": cpu_count,
        "latest_gpu_target_block_count": gpu_count,
        "target_cpu_only_residency_observed": decision == "trigger_ready",
        "cpu_target_eviction_observed": bool(cpu_evictions),
        "raw_hash_values_retained": False,
    }


def summarize_h2d_trigger_rows(
    rows: list[dict[str, Any]],
    *,
    target_block_count: int,
    restore_tokens: int,
    expected_world_size: int,
    require_restore_group_eligibility: bool = False,
) -> dict[str, Any]:
    def capture_exact(row: dict[str, Any]) -> bool:
        return (
            row.get("target_capture_exact") is True
            if "target_capture_exact" in row
            else True
        )

    def keyspace_matchable(row: dict[str, Any]) -> bool:
        return (
            row.get("target_keyspace_matchable") is True
            if "target_keyspace_matchable" in row
            else capture_exact(row)
        )

    captures = [
        row
        for row in rows
        if row.get("event")
        in {"target_hashes_captured", "target_residency_snapshot"}
        and int(row.get("target_block_count") or 0) == target_block_count
        and capture_exact(row)
        and keyspace_matchable(row)
    ]
    gpu_evictions = [
        row
        for row in rows
        if row.get("event") == "target_cache_evicted"
        and row.get("tier") == "gpu"
        and int(row.get("target_evicted_count") or 0) > 0
    ]
    cpu_only = [
        row
        for row in rows
        if row.get("event") == "target_residency_snapshot"
        and row.get("reason") == "before_restore_match"
        and int(row.get("cpu_target_block_count") or 0) == target_block_count
        and int(row.get("gpu_target_block_count") or 0) == 0
        and capture_exact(row)
        and keyspace_matchable(row)
        and (
            not require_restore_group_eligibility
            or row.get("restore_group_eligibility_complete") is True
        )
    ]
    cpu_hits = [
        row
        for row in rows
        if row.get("event") == "cpu_hit_matched"
        and (
            row.get("contract_role") == "restore_follower"
            or str(row.get("request_id", "")).endswith("restore_follower")
        )
        and int(row.get("num_new_tokens") or 0) == restore_tokens
    ]
    load_scheduled = [
        row
        for row in rows
        if row.get("event") == "load_scheduled"
        and (
            row.get("contract_role") == "restore_follower"
            or str(row.get("request_id", "")).endswith("restore_follower")
        )
        and int(row.get("block_count") or 0) > 0
    ]
    h2d_workers = {
        str(row.get("rank") if row.get("rank") is not None else row.get("pid"))
        for row in rows
        if row.get("event") == "transfer_completed"
        and row.get("direction") == "h2d"
    }
    load_completed = [
        row
        for row in rows
        if row.get("event") == "load_request_completed"
        and (
            row.get("contract_role") == "restore_follower"
            or str(row.get("request_id", "")).endswith("restore_follower")
        )
    ]
    value = {
        "schema_version": "p8_2_k1a_h2d_residency_summary_v1",
        "target_block_count": target_block_count,
        "restore_tokens": restore_tokens,
        "expected_world_size": expected_world_size,
        "target_hashes_captured_exact": bool(captures),
        "target_gpu_eviction_observed": bool(gpu_evictions),
        "target_cpu_only_residency_observed": bool(cpu_only),
        "restore_group_eligibility_required": require_restore_group_eligibility,
        "restore_group_eligibility_observed": any(
            row.get("restore_group_eligibility_complete") is True
            for row in cpu_only
        ),
        "restore_cpu_hit_exact": bool(cpu_hits),
        "restore_load_scheduled": bool(load_scheduled),
        "h2d_worker_completion_count": len(h2d_workers),
        "h2d_worker_completion_exact": len(h2d_workers) == expected_world_size,
        "restore_load_request_completed": bool(load_completed),
        "raw_hash_values_retained": False,
    }
    value["h2d_restore_mechanism_candidate"] = all(
        (
            value["target_hashes_captured_exact"],
            value["target_gpu_eviction_observed"],
            value["target_cpu_only_residency_observed"],
            value["restore_cpu_hit_exact"],
            value["restore_load_scheduled"],
            value["h2d_worker_completion_exact"],
            value["restore_load_request_completed"],
        )
    )
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("--rows", type=Path, required=True)
    summarize.add_argument("--output", type=Path, required=True)
    summarize.add_argument("--target-block-count", type=int, required=True)
    summarize.add_argument("--restore-tokens", type=int, required=True)
    summarize.add_argument("--expected-world-size", type=int, required=True)
    self_test = subparsers.add_parser("self-test")
    self_test.add_argument("--output", type=Path, required=True)
    gate = subparsers.add_parser("gate")
    gate.add_argument("--trace-dir", type=Path, required=True)
    gate.add_argument("--output", type=Path, required=True)
    gate.add_argument("--target-block-count", type=int, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "summarize":
        rows = json.loads(args.rows.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("rows must be a JSON list of objects")
        summary = summarize_h2d_trigger_rows(
            rows,
            target_block_count=args.target_block_count,
            restore_tokens=args.restore_tokens,
            expected_world_size=args.expected_world_size,
        )
        _write_json(args.output, summary)
        return 0
    if args.command == "self-test":
        _write_json(args.output, observer_self_test_contract())
        return 0
    if args.command == "gate":
        value = build_residency_gate(
            _read_trace_dir(args.trace_dir),
            target_block_count=args.target_block_count,
        )
        _write_json(args.output, value)
        if value["decision"] == "trigger_ready":
            return 0
        if value["decision"] == "continue_pressure":
            return 3
        return 4
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
