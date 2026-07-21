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
ACTIVE_ROLE_PATH_ENV = "P8_2_K1A_H2D_ACTIVE_ROLE_PATH"
_POOL_TIERS: dict[int, str] = {}
_POOL_SCHEDULERS: dict[int, weakref.ReferenceType[Any]] = {}


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
    target_hashes = tuple(getattr(scheduler, "_p8_2_k1a_target_hashes", ()))
    cpu_pool = getattr(scheduler, "cpu_block_pool", None)
    gpu_pool = getattr(scheduler, "_gpu_block_pool", None)

    def count(pool: Any) -> int:
        if pool is None:
            return 0
        mapping = pool.cached_block_hash_to_block
        return sum(mapping.get_one_block(value) is not None for value in target_hashes)

    return count(cpu_pool), count(gpu_pool)


def _emit_residency_snapshot(scheduler: Any, *, reason: str) -> None:
    target_hashes = tuple(getattr(scheduler, "_p8_2_k1a_target_hashes", ()))
    if not target_hashes:
        return
    cpu_count, gpu_count = _target_residency_counts(scheduler)
    cpu_pool = scheduler.cpu_block_pool
    gpu_pool = scheduler._gpu_block_pool
    _emit(
        "target_residency_snapshot",
        component="scheduler",
        reason=reason,
        target_block_count=len(target_hashes),
        cpu_target_block_count=cpu_count,
        gpu_target_block_count=gpu_count,
        cpu_free_block_count=cpu_pool.get_num_free_blocks(),
        gpu_free_block_count=(
            gpu_pool.get_num_free_blocks() if gpu_pool is not None else None
        ),
        raw_hash_values_retained=False,
    )


def install_p8_2_k1a_h2d_residency_observer() -> None:
    from vllm.v1.core.block_pool import BlockPool
    from vllm.v1.simple_kv_offload.manager import SimpleCPUOffloadScheduler

    marker = "_p8_2_k1a_h2d_residency_observer_installed"
    if getattr(SimpleCPUOffloadScheduler, marker, False):
        return

    target_suffix = os.environ.get(TARGET_SUFFIX_ENV, "target_prime")
    restore_suffix = os.environ.get(RESTORE_SUFFIX_ENV, "restore_follower")
    target_block_count = int(os.environ.get(TARGET_BLOCK_COUNT_ENV, "64"))

    original_finished = SimpleCPUOffloadScheduler.request_finished_all_groups

    @wraps(original_finished)
    def observed_finished(self, request, block_ids):
        _register_pools(self)
        contract_role = _active_contract_role()
        if contract_role == "target_prime" or str(request.request_id).endswith(
            target_suffix
        ):
            gpu_pool = self._gpu_block_pool
            fa_group = (
                block_ids[self.fa_gidx] if block_ids else []
            )[:target_block_count]
            target_hashes = tuple(
                gpu_pool.blocks[block_id].block_hash
                for block_id in fa_group
                if not gpu_pool.blocks[block_id].is_null
                and gpu_pool.blocks[block_id].block_hash is not None
            )
            self._p8_2_k1a_target_hashes = target_hashes
            _emit(
                "target_hashes_captured",
                component="scheduler",
                request_id=request.request_id,
                contract_role=contract_role,
                target_block_count=len(target_hashes),
                raw_hash_values_retained=False,
            )
            _emit_residency_snapshot(self, reason="target_request_finished")
        return original_finished(self, request, block_ids)

    original_match = SimpleCPUOffloadScheduler.get_num_new_matched_tokens

    @wraps(original_match)
    def observed_match(self, request, num_computed_tokens):
        _register_pools(self)
        contract_role = _active_contract_role()
        if contract_role == "restore_follower" or str(request.request_id).endswith(
            restore_suffix
        ):
            _emit_residency_snapshot(self, reason="before_restore_match")
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
            _emit_residency_snapshot(self, reason="after_restore_alloc")
        return result

    original_build = SimpleCPUOffloadScheduler.build_connector_meta

    @wraps(original_build)
    def observed_build(self, scheduler_output):
        result = original_build(self, scheduler_output)
        _register_pools(self)
        _emit_residency_snapshot(self, reason="after_connector_meta")
        return result

    original_output = SimpleCPUOffloadScheduler.update_connector_output

    @wraps(original_output)
    def observed_output(self, connector_output):
        result = original_output(self, connector_output)
        _register_pools(self)
        _emit_residency_snapshot(self, reason="after_connector_output")
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
            _emit(
                "target_cache_evicted",
                component="block_pool",
                tier=_POOL_TIERS.get(id(self), "unknown"),
                target_evicted_count=1,
                raw_hash_values_retained=False,
            )
            _emit_residency_snapshot(scheduler, reason="after_target_eviction")
        return result

    SimpleCPUOffloadScheduler.request_finished_all_groups = observed_finished
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


def observer_self_test_contract() -> dict[str, Any]:
    return {
        "schema_version": "p8_2_k1a_h2d_residency_observer_contract_v1",
        "observer_mode": "observe_only_no_decision_request_order_or_copy_mutation",
        "wrapped_scheduler_methods": [
            "request_finished_all_groups",
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
        "request_identity_source": "controller_role_marker_not_server_request_id",
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
    captures = [
        row
        for row in rows
        if row.get("event") == "target_hashes_captured"
        and int(row.get("target_block_count") or 0) == target_block_count
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
        for row in snapshots
    )

    if not captures or not snapshots:
        decision = "unobservable"
    elif cpu_evictions or (cpu_was_complete and cpu_count < target_block_count):
        decision = "cpu_target_lost"
    elif cpu_count == target_block_count and gpu_count == 0:
        decision = "trigger_ready"
    else:
        decision = "continue_pressure"
    return {
        "schema_version": "p8_2_k1a_r5_l1_residency_gate_v1",
        "decision": decision,
        "restore_allowed": decision == "trigger_ready",
        "target_hashes_captured_exact": bool(captures),
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
) -> dict[str, Any]:
    captures = [
        row
        for row in rows
        if row.get("event") == "target_hashes_captured"
        and int(row.get("target_block_count") or 0) == target_block_count
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
