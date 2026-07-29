from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

GIB = 1 << 30
DEFAULT_TRIGGER_RATIO = 0.7
DEFAULT_RECYCLE_PERCENT = 0.1


def calculate_store_geometry(
    *,
    label: str,
    block_size_bytes: int,
    split_capacity_gib: int,
    data_dir_shard_bytes: int,
    trigger_ratio: float = DEFAULT_TRIGGER_RATIO,
    recycle_percent: float = DEFAULT_RECYCLE_PERCENT,
) -> dict[str, Any]:
    if block_size_bytes <= 0:
        raise ValueError("block_size_bytes must be positive")
    if split_capacity_gib <= 0:
        raise ValueError("split_capacity_gib must be positive")
    if not 0 <= data_dir_shard_bytes <= 5:
        raise ValueError("data_dir_shard_bytes must be in [0, 5]")
    if not 0 < trigger_ratio <= 1:
        raise ValueError("trigger_ratio must be in (0, 1]")
    if not 0 < recycle_percent <= 1:
        raise ValueError("recycle_percent must be in (0, 1]")

    directory_shard_count = 1 if data_dir_shard_bytes == 0 else 16**data_dir_shard_bytes
    capacity_bytes = split_capacity_gib * GIB
    max_file_count = capacity_bytes // block_size_bytes
    files_per_directory_shard = max_file_count // directory_shard_count
    threshold_files_per_shard = int(files_per_directory_shard * trigger_ratio)
    recycle_files_per_shard = int(threshold_files_per_shard * recycle_percent)
    min_files_per_directory_shard = int(1.0 / (trigger_ratio * recycle_percent)) + 1
    minimum_capacity_bytes = (
        min_files_per_directory_shard * directory_shard_count * block_size_bytes
    )
    minimum_capacity_gib = math.ceil(minimum_capacity_bytes / GIB)
    return {
        "label": label,
        "block_size_bytes": block_size_bytes,
        "configured_capacity_gib_after_fawa_split": split_capacity_gib,
        "configured_capacity_bytes_after_fawa_split": capacity_bytes,
        "data_dir_shard_bytes": data_dir_shard_bytes,
        "directory_shard_count": directory_shard_count,
        "gc_trigger_threshold_ratio": trigger_ratio,
        "gc_recycle_percent": recycle_percent,
        "max_file_count": max_file_count,
        "files_per_directory_shard_before_trigger": (files_per_directory_shard),
        "threshold_files_per_directory_shard": threshold_files_per_shard,
        "recycle_files_per_directory_shard": recycle_files_per_shard,
        "minimum_files_per_directory_shard": (min_files_per_directory_shard),
        "minimum_capacity_bytes": minimum_capacity_bytes,
        "minimum_capacity_gib_ceil": minimum_capacity_gib,
        "gc_recycle_nonzero": recycle_files_per_shard > 0,
        "formula_source": (
            "pinned_ucm_shard_gc_cc_ValidateAndInitCapacity_integer_order"
        ),
    }


def extract_parent_worker_block_sizes(
    parent_geometry_path: Path,
) -> dict[str, int]:
    value = json.loads(parent_geometry_path.read_text(encoding="utf-8"))
    observed: dict[str, set[int]] = {"FA": set(), "WA": set()}
    for item in value.get("observations") or []:
        if item.get("role") != "worker" or item.get("parsed") is not True:
            continue
        label = str(item.get("label", "")).upper()
        config = item.get("config") or {}
        block_size = config.get("block_size")
        if label in observed and isinstance(block_size, int):
            observed[label].add(block_size)
    invalid = {
        label: sorted(sizes) for label, sizes in observed.items() if len(sizes) != 1
    }
    if invalid:
        raise ValueError(
            f"parent worker block geometry is missing or ambiguous: {invalid}"
        )
    return {label: next(iter(sizes)) for label, sizes in observed.items()}


def _available_bytes(path: Path) -> int:
    stat = os.statvfs(path)
    return stat.f_bavail * stat.f_frsize


def _mem_available_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, value = line.split(":", 1)
        if key == "MemAvailable":
            return int(value.strip().split()[0]) * 1024
    return 0


def build_preflight_summary(
    *,
    dependency_status: str,
    parent_geometry_path: Path,
    storage_root: Path,
    cache_buffer_gib_per_store: int,
    cache_store_count: int,
    tensor_parallel_size: int,
    cache_headroom_gib: int,
    total_posix_capacity_gib: int,
    fawa_split_count: int,
    posix_headroom_gib: int,
    data_dir_shard_bytes: int,
    expected_fa_block_size_bytes: int,
    expected_wa_block_size_bytes: int,
    cache_load_exclusive_buffer_number: int,
) -> dict[str, Any]:
    if total_posix_capacity_gib % fawa_split_count != 0:
        raise ValueError("total POSIX capacity must split evenly across FA/WA stores")
    parent_blocks = extract_parent_worker_block_sizes(parent_geometry_path)
    expected_blocks = {
        "FA": expected_fa_block_size_bytes,
        "WA": expected_wa_block_size_bytes,
    }
    parent_geometry_exact = parent_blocks == expected_blocks
    split_capacity_gib = total_posix_capacity_gib // fawa_split_count
    stores = [
        calculate_store_geometry(
            label=label,
            block_size_bytes=block_size,
            split_capacity_gib=split_capacity_gib,
            data_dir_shard_bytes=data_dir_shard_bytes,
        )
        for label, block_size in expected_blocks.items()
    ]

    cache_buffer_bytes = cache_buffer_gib_per_store * GIB
    required_cache_buffer_number = max(1024, cache_load_exclusive_buffer_number * 2)
    cache_rows = {
        label: {
            "block_size_bytes": block_size,
            "configured_buffer_number": cache_buffer_bytes // block_size,
            "required_buffer_number": required_cache_buffer_number,
            "geometry_gate_passed": (
                cache_buffer_bytes // block_size >= required_cache_buffer_number
            ),
        }
        for label, block_size in expected_blocks.items()
    }
    cache_geometry_gate = all(
        row["geometry_gate_passed"] for row in cache_rows.values()
    )
    conservative_cache_bytes = (
        cache_buffer_bytes * cache_store_count * tensor_parallel_size
    )
    required_cache_free_bytes = conservative_cache_bytes + cache_headroom_gib * GIB
    shm_available_bytes = _available_bytes(Path("/dev/shm"))
    mem_available_bytes = _mem_available_bytes()
    shm_gate = shm_available_bytes >= required_cache_free_bytes
    host_memory_gate = mem_available_bytes >= required_cache_free_bytes

    storage_available_bytes = _available_bytes(storage_root)
    required_storage_free_bytes = (total_posix_capacity_gib + posix_headroom_gib) * GIB
    filesystem_gate = storage_available_bytes >= required_storage_free_bytes
    posix_geometry_gate = all(row["gc_recycle_nonzero"] for row in stores)
    dependency_ready = dependency_status == "ready"
    gate = all(
        (
            dependency_ready,
            parent_geometry_exact,
            cache_geometry_gate,
            posix_geometry_gate,
            shm_gate,
            host_memory_gate,
            filesystem_gate,
        )
    )
    if not dependency_ready:
        status = "not_evaluated_dependency_failed"
    elif gate:
        status = "ready"
    else:
        status = "insufficient"
    return {
        "status": status,
        "dependency_ready": dependency_ready,
        "pre_npu_capacity_gate_passed": gate,
        "parent_run03_attribution_geometry_path": str(parent_geometry_path),
        "parent_worker_block_sizes": parent_blocks,
        "expected_worker_block_sizes": expected_blocks,
        "parent_worker_geometry_exact": parent_geometry_exact,
        "cache_store": {
            "configured_cache_buffer_gib_per_fawa_store": (cache_buffer_gib_per_store),
            "fawa_store_count": cache_store_count,
            "tensor_parallel_size": tensor_parallel_size,
            "load_exclusive_buffer_number": (cache_load_exclusive_buffer_number),
            "required_buffer_number": required_cache_buffer_number,
            "stores": cache_rows,
            "all_store_geometry_gates_passed": cache_geometry_gate,
            "conservative_total_cache_buffer_bytes": (conservative_cache_bytes),
            "capacity_headroom_gib": cache_headroom_gib,
            "required_free_bytes_with_headroom": (required_cache_free_bytes),
            "dev_shm_available_bytes": shm_available_bytes,
            "dev_shm_gate_passed": shm_gate,
            "host_mem_available_bytes": mem_available_bytes,
            "host_memory_gate_passed": host_memory_gate,
            "allocation_boundary": (
                "conservative_two_store_times_tp8_upper_bound;"
                "not_runtime_allocation_proof"
            ),
        },
        "fawa_posix_gc": {
            "configured_total_posix_capacity_gib_before_fawa_split": (
                total_posix_capacity_gib
            ),
            "fawa_split_count": fawa_split_count,
            "configured_posix_capacity_gib_per_store_after_split": (split_capacity_gib),
            "data_dir_shard_bytes": data_dir_shard_bytes,
            "directory_shard_count": (
                1 if data_dir_shard_bytes == 0 else 16**data_dir_shard_bytes
            ),
            "stores": stores,
            "all_store_gc_recycle_gates_passed": posix_geometry_gate,
            "storage_root": str(storage_root),
            "storage_available_bytes": storage_available_bytes,
            "storage_headroom_gib": posix_headroom_gib,
            "required_storage_free_bytes_with_headroom": (required_storage_free_bytes),
            "filesystem_gate_passed": filesystem_gate,
            "capacity_split_source": (
                "pinned_ucm_hma_connector_base_store_config_integer_half"
            ),
        },
        "claim_boundary": (
            "exact_pinned_source_integer_geometry_and_pre_npu_resource_"
            "preflight;runtime_store_creation_and_external_prefix_requests_"
            "remain_to_be_observed"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dependency-status", required=True)
    parser.add_argument("--parent-geometry", type=Path, required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--cache-buffer-gib-per-store", type=int, required=True)
    parser.add_argument("--cache-store-count", type=int, default=2)
    parser.add_argument("--tensor-parallel-size", type=int, required=True)
    parser.add_argument("--cache-headroom-gib", type=int, required=True)
    parser.add_argument("--total-posix-capacity-gib", type=int, required=True)
    parser.add_argument("--fawa-split-count", type=int, default=2)
    parser.add_argument("--posix-headroom-gib", type=int, required=True)
    parser.add_argument("--data-dir-shard-bytes", type=int, required=True)
    parser.add_argument("--expected-fa-block-size-bytes", type=int, required=True)
    parser.add_argument("--expected-wa-block-size-bytes", type=int, required=True)
    parser.add_argument(
        "--cache-load-exclusive-buffer-number",
        type=int,
        required=True,
    )
    args = parser.parse_args()
    summary = build_preflight_summary(
        dependency_status=args.dependency_status,
        parent_geometry_path=args.parent_geometry,
        storage_root=args.storage_root,
        cache_buffer_gib_per_store=args.cache_buffer_gib_per_store,
        cache_store_count=args.cache_store_count,
        tensor_parallel_size=args.tensor_parallel_size,
        cache_headroom_gib=args.cache_headroom_gib,
        total_posix_capacity_gib=args.total_posix_capacity_gib,
        fawa_split_count=args.fawa_split_count,
        posix_headroom_gib=args.posix_headroom_gib,
        data_dir_shard_bytes=args.data_dir_shard_bytes,
        expected_fa_block_size_bytes=args.expected_fa_block_size_bytes,
        expected_wa_block_size_bytes=args.expected_wa_block_size_bytes,
        cache_load_exclusive_buffer_number=(args.cache_load_exclusive_buffer_number),
    )
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    raise SystemExit(0 if summary["pre_npu_capacity_gate_passed"] else 1)


if __name__ == "__main__":
    main()
