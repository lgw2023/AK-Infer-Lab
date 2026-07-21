from __future__ import annotations

from functools import wraps
import json
import os
from pathlib import Path
import time
from typing import Any


TRACE_ENV = "P8_2_K1A_TRANSFER_TRACE_DIR"
ACTIVE_ROLE_PATH_ENV = "P8_2_K1A_H2D_ACTIVE_ROLE_PATH"


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


def install_p8_2_k1a_simple_cpu_offload_observer() -> None:
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
            _emit(
                "cpu_hit_matched",
                component="scheduler",
                direction="h2d",
                request_id=request.request_id,
                contract_role=_active_contract_role(),
                num_new_tokens=num_new_tokens,
                is_async=bool(is_async),
            )
        return result

    original_update = SimpleCPUOffloadScheduler.update_state_after_alloc

    @wraps(original_update)
    def observed_update(self, request, blocks, num_external_tokens):
        result = original_update(self, request, blocks, num_external_tokens)
        state = self._reqs_to_load.get(request.request_id)
        transfer = state.transfer_meta if state is not None else None
        if transfer is not None:
            _emit(
                "load_scheduled",
                component="scheduler",
                direction="h2d",
                request_id=request.request_id,
                contract_role=_active_contract_role(),
                block_count=len(transfer.gpu_block_ids),
                num_external_tokens=num_external_tokens,
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
        if metadata.load_event >= 0 and metadata.load_gpu_blocks:
            _emit(
                "transfer_scheduled",
                component="scheduler",
                direction="h2d",
                event_idx=metadata.load_event,
                block_count=len(metadata.load_gpu_blocks),
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
    SimpleCPUOffloadScheduler.update_state_after_alloc = observed_update
    SimpleCPUOffloadScheduler.build_connector_meta = observed_build
    SimpleCPUOffloadScheduler.update_connector_output = observed_output
    copy_backend_module.copy_blocks = observed_copy_blocks
    NPUDmaCopyBackend._copy_loop = observed_copy_loop
    NPUDmaCopyBackend.launch_copy = observed_launch
    SimpleCPUOffloadNPUWorker._poll_stream_events = observed_poll
    SimpleCPUOffloadScheduler._p8_2_k1a_observer_installed = True
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
    }
