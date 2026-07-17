from __future__ import annotations

from functools import wraps
import json
import os
from pathlib import Path
from typing import Any


GEOMETRY_DIR_ENV = "P8_2_K1A_R1_GEOMETRY_DIR"
GEOMETRY_ONLY_ENV = "P8_2_K1A_R1_GEOMETRY_ONLY"
GEOMETRY_SENTINEL = "P8_2_K1A_R1_GEOMETRY_PROBE_COMPLETE"


def build_geometry_record(
    *,
    rank: int,
    world_size: int,
    num_npu_blocks: int,
    descriptors: list[tuple[str, int]],
) -> dict[str, Any]:
    ordered = sorted((str(name), int(value)) for name, value in descriptors)
    total = sum(value for _, value in ordered)
    block_size_tokens = 128
    required_restore_tokens = 16384
    required_cpu_blocks = required_restore_tokens // block_size_tokens
    return {
        "schema_version": "p8_2_k1a_r1_geometry_v1",
        "rank": int(rank),
        "world_size": int(world_size),
        "block_size_tokens": block_size_tokens,
        "required_restore_tokens": required_restore_tokens,
        "required_cpu_blocks": required_cpu_blocks,
        "num_npu_blocks": int(num_npu_blocks),
        "unique_tensor_count": len(ordered),
        "per_tensor_bytes_per_block": [
            {"name": name, "bytes_per_block": value}
            for name, value in ordered
        ],
        "total_bytes_per_block": total,
        "required_capacity_bytes_per_rank": required_cpu_blocks * total,
        "allocation_attempted": False,
    }


def _write_record(record: dict[str, Any]) -> None:
    root_value = os.environ.get(GEOMETRY_DIR_ENV)
    if not root_value:
        raise RuntimeError(f"{GEOMETRY_DIR_ENV} is required")
    root = Path(root_value)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"geometry.rank.{record['rank']}.json"
    path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _runtime_rank_and_world_size() -> tuple[int, int]:
    try:
        import torch.distributed as dist

        if dist.is_available() and dist.is_initialized():
            return int(dist.get_rank()), int(dist.get_world_size())
    except Exception:
        pass
    rank = int(os.environ.get("RANK", os.environ.get("LOCAL_RANK", "-1")))
    world_size = int(os.environ.get("WORLD_SIZE", "8"))
    return rank, world_size


def install_p8_2_k1a_simple_cpu_offload_observer() -> None:
    from vllm_ascend.simple_kv_offload.worker import (
        SimpleCPUOffloadNPUWorker,
        _flatten_kv_value,
    )

    if getattr(SimpleCPUOffloadNPUWorker, "_p8_2_k1a_r1_geometry_installed", False):
        return
    original = SimpleCPUOffloadNPUWorker.register_kv_caches

    @wraps(original)
    def observed_register(self, kv_caches):
        if not os.environ.get(GEOMETRY_DIR_ENV):
            return original(self, kv_caches)
        if not kv_caches:
            raise RuntimeError("geometry probe received no KV caches")
        if self.kv_cache_config is None:
            raise RuntimeError("geometry probe received no KV cache config")

        num_blocks = int(self.kv_cache_config.num_blocks)
        unique: dict[str, Any] = {}
        seen_ptrs: set[int] = set()
        for layer_name, value in kv_caches.items():
            for sub_idx, tensor in enumerate(_flatten_kv_value(value)):
                ptr = int(tensor.untyped_storage().data_ptr())
                if ptr in seen_ptrs:
                    continue
                seen_ptrs.add(ptr)
                key = layer_name if sub_idx == 0 else f"{layer_name}.{sub_idx}"
                unique.update(self._build_block_views(key, tensor, num_blocks))
        descriptors = [
            (name, int(tensor.stride(0) * tensor.element_size()))
            for name, tensor in unique.items()
        ]
        rank, world_size = _runtime_rank_and_world_size()
        record = build_geometry_record(
            rank=rank,
            world_size=world_size,
            num_npu_blocks=num_blocks,
            descriptors=descriptors,
        )
        _write_record(record)
        if os.environ.get(GEOMETRY_ONLY_ENV) == "1":
            raise RuntimeError(GEOMETRY_SENTINEL)
        return original(self, kv_caches)

    SimpleCPUOffloadNPUWorker.register_kv_caches = observed_register
    SimpleCPUOffloadNPUWorker._p8_2_k1a_r1_geometry_installed = True
