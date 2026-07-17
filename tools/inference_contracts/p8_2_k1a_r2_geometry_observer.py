from __future__ import annotations

from functools import wraps
import json
import os
from pathlib import Path
import threading
import time
from typing import Any


GEOMETRY_SCHEMA_VERSION = "p8_2_k1a_r2_geometry_v1"
RENDEZVOUS_SCHEMA_VERSION = "p8_2_k1a_r2_geometry_rendezvous_v1"
GEOMETRY_DIR_ENV = "P8_2_K1A_R2_GEOMETRY_DIR"
GEOMETRY_ONLY_ENV = "P8_2_K1A_R2_GEOMETRY_ONLY"
PROBE_RUN_ID_ENV = "P8_2_K1A_R2_PROBE_RUN_ID"
RENDEZVOUS_TIMEOUT_ENV = "P8_2_K1A_R2_RENDEZVOUS_TIMEOUT_SECONDS"
GEOMETRY_SENTINEL = "P8_2_K1A_R2_GEOMETRY_PROBE_COMPLETE"


def build_geometry_record(
    *,
    probe_run_id: str,
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
        "schema_version": GEOMETRY_SCHEMA_VERSION,
        "probe_run_id": str(probe_run_id),
        "rank": int(rank),
        "world_size": int(world_size),
        "block_size_tokens": block_size_tokens,
        "required_restore_tokens": required_restore_tokens,
        "required_cpu_blocks": required_cpu_blocks,
        "num_npu_blocks": int(num_npu_blocks),
        "unique_tensor_count": len(ordered),
        "per_tensor_bytes_per_block": [
            {"name": name, "bytes_per_block": value} for name, value in ordered
        ],
        "total_bytes_per_block": total,
        "required_capacity_bytes_per_rank": required_cpu_blocks * total,
        "allocation_attempted": False,
    }


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(
        f".{path.name}.tmp.{os.getpid()}.{threading.get_ident()}"
    )
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_same_run_records(root: Path, run_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for rank in range(8):
        path = root / f"geometry.rank.{rank}.json"
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if value.get("probe_run_id") != run_id:
            raise RuntimeError(f"foreign geometry probe run at rank {rank}")
        records.append(value)
    return records


def _validate_complete_records(
    records: list[dict[str, Any]], run_id: str
) -> dict[str, Any]:
    if len(records) != 8:
        raise ValueError(f"expected 8 geometry records, got {len(records)}")
    if any(row.get("schema_version") != GEOMETRY_SCHEMA_VERSION for row in records):
        raise ValueError("geometry schema mismatch")
    ranks = sorted(int(row["rank"]) for row in records)
    if ranks != list(range(8)):
        raise ValueError(f"rank coverage mismatch: {ranks}")
    if any(int(row["world_size"]) != 8 for row in records):
        raise ValueError("world_size mismatch")
    parity_fields = (
        "block_size_tokens",
        "required_restore_tokens",
        "required_cpu_blocks",
        "total_bytes_per_block",
        "unique_tensor_count",
        "per_tensor_bytes_per_block",
    )
    for field in parity_fields:
        values = {json.dumps(row[field], sort_keys=True) for row in records}
        if len(values) != 1:
            raise ValueError(f"rank geometry drift for {field}")
    if any(row.get("allocation_attempted") is not False for row in records):
        raise ValueError("geometry probe attempted allocation")
    return {
        "schema_version": RENDEZVOUS_SCHEMA_VERSION,
        "probe_run_id": run_id,
        "rank_coverage": ranks,
        "world_size": 8,
        "geometry_parity_exact": True,
        "allocation_attempted": False,
    }


def publish_and_wait_for_geometry_rendezvous(
    root: Path,
    record: dict[str, Any],
    *,
    timeout_seconds: float,
    poll_interval_seconds: float = 0.05,
) -> dict[str, Any]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    run_id = str(record.get("probe_run_id", ""))
    rank = int(record["rank"])
    if not run_id:
        raise ValueError("probe_run_id is required")
    if rank not in range(8):
        raise ValueError(f"rank outside frozen world: {rank}")
    _atomic_write_json(root / f"geometry.rank.{rank}.json", record)

    marker_path = root / "geometry.rendezvous.complete.json"
    deadline = time.monotonic() + float(timeout_seconds)
    while time.monotonic() < deadline:
        records = _load_same_run_records(root, run_id)
        if len(records) == 8:
            marker = _validate_complete_records(records, run_id)
            _atomic_write_json(marker_path, marker)
            return marker
        time.sleep(float(poll_interval_seconds))
    raise TimeoutError(
        f"eight-rank geometry rendezvous timed out: got "
        f"{len(_load_same_run_records(root, run_id))}/8"
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

    marker = "_p8_2_k1a_r2_geometry_installed"
    if getattr(SimpleCPUOffloadNPUWorker, marker, False):
        return
    original = SimpleCPUOffloadNPUWorker.register_kv_caches

    @wraps(original)
    def observed_register(self, kv_caches):
        root_value = os.environ.get(GEOMETRY_DIR_ENV)
        if not root_value:
            return original(self, kv_caches)
        if os.environ.get(GEOMETRY_ONLY_ENV) != "1":
            raise RuntimeError("K1A-R2 observer is restricted to geometry-only mode")
        run_id = os.environ.get(PROBE_RUN_ID_ENV, "")
        if not run_id:
            raise RuntimeError(f"{PROBE_RUN_ID_ENV} is required")
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
            probe_run_id=run_id,
            rank=rank,
            world_size=world_size,
            num_npu_blocks=num_blocks,
            descriptors=descriptors,
        )
        publish_and_wait_for_geometry_rendezvous(
            Path(root_value),
            record,
            timeout_seconds=float(os.environ.get(RENDEZVOUS_TIMEOUT_ENV, "180")),
        )
        raise RuntimeError(GEOMETRY_SENTINEL)

    SimpleCPUOffloadNPUWorker.register_kv_caches = observed_register
    setattr(SimpleCPUOffloadNPUWorker, marker, True)
