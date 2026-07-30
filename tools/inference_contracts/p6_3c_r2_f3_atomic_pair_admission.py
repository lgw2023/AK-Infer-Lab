from __future__ import annotations

from functools import wraps
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable
import weakref


ENABLE_ENV = "P6_3C_R2_F3_ATOMIC_PAIR_ADMISSION"
REQUEST_PREFIX_ENV = "P6_3C_R2_F3_REQUEST_PREFIX"
TRACE_DIR_ENV = "P6_3C_R2_F3_ATOMIC_PAIR_TRACE_DIR"
TIMEOUT_SECONDS_ENV = "P6_3C_R2_F3_PAIR_TIMEOUT_SECONDS"
DEFAULT_REQUEST_PREFIX = "p6_3c_r2_f3"
DEFAULT_TIMEOUT_SECONDS = 30.0
TIMEOUT_WAKEUP_TAG = "p6_3c_r2_f3_atomic_pair_timeout"


def _enabled() -> bool:
    return os.environ.get(ENABLE_ENV) == "1"


def _request_prefix() -> str:
    return os.environ.get(REQUEST_PREFIX_ENV, DEFAULT_REQUEST_PREFIX)


def _timeout_seconds() -> float:
    value = float(os.environ.get(TIMEOUT_SECONDS_ENV, DEFAULT_TIMEOUT_SECONDS))
    if value <= 0:
        raise ValueError("atomic pair timeout must be positive")
    return value


def _emit(event: str, **fields: Any) -> None:
    raw_root = os.environ.get(TRACE_DIR_ENV)
    if not raw_root:
        return
    root = Path(raw_root)
    root.mkdir(parents=True, exist_ok=True)
    row = {
        "event": event,
        "pid": os.getpid(),
        "mode": os.environ.get("P6_3C_R1_MODE"),
        "track": os.environ.get("P6_3C_R1_TRACK"),
        "timestamp_ns": time.time_ns(),
        "monotonic_ns": time.monotonic_ns(),
        **fields,
    }
    with (root / f"trace.{os.getpid()}.jsonl").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")


def parse_atomic_pair_request_id(request_id: str) -> tuple[str, int] | None:
    prefix = f"cmpl-{_request_prefix()}_"
    if not request_id.startswith(prefix):
        return None
    pair_key, separator, raw_index = request_id.rpartition("-")
    if not separator or raw_index not in {"0", "1"}:
        return None
    return pair_key, int(raw_index)


class _AtomicPairController:
    def __init__(
        self,
        engine_core: object,
        original_add: Callable[..., Any],
        original_abort: Callable[..., Any],
        wakeup_request_type: object,
    ) -> None:
        self._engine_ref = weakref.ref(engine_core)
        self._original_add = original_add
        self._original_abort = original_abort
        self._wakeup_request_type = wakeup_request_type
        self._lock = threading.RLock()
        self._pending: dict[str, dict[int, tuple[object, int, int]]] = {}
        self._request_to_pair: dict[str, str] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._failed_pairs: set[str] = set()
        self._completed_pair_count = 0

    def _arm_timeout(self, pair_key: str) -> None:
        engine_ref = self._engine_ref

        def enqueue_timeout() -> None:
            engine_core = engine_ref()
            if engine_core is None:
                return
            with self._lock:
                if pair_key not in self._pending:
                    return
            input_queue = getattr(engine_core, "input_queue", None)
            if input_queue is None:
                _emit(
                    "pair_timeout_wakeup_unavailable",
                    pair_key=pair_key,
                    reason="engine_core_has_no_input_queue",
                )
                return
            input_queue.put_nowait(
                (
                    self._wakeup_request_type,
                    (TIMEOUT_WAKEUP_TAG, pair_key),
                )
            )

        timer = threading.Timer(_timeout_seconds(), enqueue_timeout)
        timer.daemon = True
        self._timers[pair_key] = timer
        timer.start()

    def _cancel_timer(self, pair_key: str) -> None:
        timer = self._timers.pop(pair_key, None)
        if timer is not None:
            timer.cancel()

    def _drain_pair(
        self, pair_key: str
    ) -> list[tuple[int, object, int, int]]:
        pending = self._pending.pop(pair_key, {})
        self._cancel_timer(pair_key)
        rows = []
        for pair_index, (request, request_wave, buffered_ns) in pending.items():
            self._request_to_pair.pop(str(getattr(request, "request_id", "")), None)
            rows.append((pair_index, request, request_wave, buffered_ns))
        return sorted(rows, key=lambda row: row[0])

    def add(self, request: object, request_wave: int) -> Any:
        request_id = str(getattr(request, "request_id", ""))
        pair = parse_atomic_pair_request_id(request_id)
        engine_core = self._engine_ref()
        if engine_core is None or pair is None:
            return self._original_add(engine_core, request, request_wave)
        pair_key, pair_index = pair
        now_ns = time.monotonic_ns()
        with self._lock:
            if pair_key in self._failed_pairs:
                _emit(
                    "pair_member_rejected_after_pair_failure",
                    pair_key=pair_key,
                    pair_index=pair_index,
                    request_id=request_id,
                )
                self._original_add(engine_core, request, request_wave)
                return self._original_abort(engine_core, [request_id])

            members = self._pending.setdefault(pair_key, {})
            if pair_index in members or request_id in self._request_to_pair:
                _emit(
                    "pair_duplicate_member",
                    pair_key=pair_key,
                    pair_index=pair_index,
                    request_id=request_id,
                )
                raise RuntimeError(f"duplicate atomic pair member: {request_id}")
            members[pair_index] = (request, request_wave, now_ns)
            self._request_to_pair[request_id] = pair_key
            _emit(
                "pair_member_buffered",
                pair_key=pair_key,
                pair_index=pair_index,
                request_id=request_id,
                prompt_tokens=int(getattr(request, "num_prompt_tokens", 0) or 0),
                buffered_member_count=len(members),
            )
            if len(members) == 1:
                self._arm_timeout(pair_key)
                return None
            if set(members) != {0, 1}:
                raise RuntimeError(f"invalid atomic pair membership: {pair_key}")
            release_rows = self._drain_pair(pair_key)

        admitted_ids: list[str] = []
        try:
            for _, member, member_wave, _ in release_rows:
                self._original_add(engine_core, member, member_wave)
                admitted_ids.append(str(getattr(member, "request_id", "")))
        except Exception:
            with self._lock:
                self._failed_pairs.add(pair_key)
            if admitted_ids:
                self._original_abort(engine_core, admitted_ids)
            _emit(
                "pair_release_failed",
                pair_key=pair_key,
                admitted_request_ids=admitted_ids,
            )
            raise

        release_ns = time.monotonic_ns()
        self._completed_pair_count += 1
        _emit(
            "pair_complete_released",
            pair_key=pair_key,
            request_ids=[
                str(getattr(member, "request_id", ""))
                for _, member, _, _ in release_rows
            ],
            pair_indices=[index for index, _, _, _ in release_rows],
            prompt_tokens=[
                int(getattr(member, "num_prompt_tokens", 0) or 0)
                for _, member, _, _ in release_rows
            ],
            member_buffer_wait_ns=[
                release_ns - buffered_ns for _, _, _, buffered_ns in release_rows
            ],
            release_order="pair_index_ascending_before_next_scheduler_step",
        )
        return None

    def abort(self, request_ids: list[str]) -> list[str]:
        engine_core = self._engine_ref()
        if engine_core is None:
            return request_ids
        affected_pairs: set[str] = set()
        with self._lock:
            for request_id in request_ids:
                pair_key = self._request_to_pair.get(str(request_id))
                if pair_key is not None:
                    affected_pairs.add(pair_key)
            drained: list[tuple[int, object, int, int]] = []
            for pair_key in sorted(affected_pairs):
                drained.extend(self._drain_pair(pair_key))
                self._failed_pairs.add(pair_key)

        drained_ids = []
        for _, request, request_wave, _ in drained:
            self._original_add(engine_core, request, request_wave)
            drained_ids.append(str(getattr(request, "request_id", "")))
        if affected_pairs:
            _emit(
                "pair_aborted_before_release",
                pair_keys=sorted(affected_pairs),
                requested_abort_ids=list(request_ids),
                buffered_abort_ids=drained_ids,
            )
        return list(dict.fromkeys([*request_ids, *drained_ids]))

    def expire(self, pair_key: str) -> None:
        engine_core = self._engine_ref()
        if engine_core is None:
            return
        with self._lock:
            drained = self._drain_pair(pair_key)
            if not drained:
                return
            self._failed_pairs.add(pair_key)
        request_ids = []
        for _, request, request_wave, _ in drained:
            self._original_add(engine_core, request, request_wave)
            request_ids.append(str(getattr(request, "request_id", "")))
        self._original_abort(engine_core, request_ids)
        _emit(
            "pair_timeout_aborted",
            pair_key=pair_key,
            request_ids=request_ids,
            timeout_seconds=_timeout_seconds(),
        )

    def shutdown(self) -> None:
        with self._lock:
            pending_pair_count = len(self._pending)
            pending_request_ids = sorted(self._request_to_pair)
            failed_pair_count = len(self._failed_pairs)
            completed_pair_count = self._completed_pair_count
            for pair_key in list(self._timers):
                self._cancel_timer(pair_key)
        _emit(
            "atomic_pair_admission_shutdown_state",
            pending_pair_count=pending_pair_count,
            pending_request_ids=pending_request_ids,
            failed_pair_count=failed_pair_count,
            completed_pair_count=completed_pair_count,
        )


def install_p6_3c_r2_f3_atomic_pair_admission() -> None:
    if not _enabled():
        return

    from vllm.v1.engine import EngineCoreRequestType
    from vllm.v1.engine.core import EngineCore, EngineCoreProc

    if getattr(EngineCore, "_p6_3c_r2_f3_atomic_pair_installed", False):
        return

    original_add = EngineCore.add_request
    original_abort = EngineCore.abort_requests
    original_handle = EngineCoreProc._handle_client_request
    original_shutdown = EngineCore.shutdown

    def controller(self: object) -> _AtomicPairController:
        current = getattr(self, "_p6_3c_r2_f3_atomic_pair_controller", None)
        if current is None:
            current = _AtomicPairController(
                self,
                original_add,
                original_abort,
                EngineCoreRequestType.WAKEUP,
            )
            setattr(self, "_p6_3c_r2_f3_atomic_pair_controller", current)
        return current

    @wraps(original_add)
    def paired_add(self, request, request_wave=0):
        return controller(self).add(request, request_wave)

    @wraps(original_abort)
    def paired_abort(self, request_ids):
        return original_abort(self, controller(self).abort(list(request_ids)))

    @wraps(original_handle)
    def paired_handle(self, request_type, request):
        if (
            request_type == EngineCoreRequestType.WAKEUP
            and isinstance(request, tuple)
            and len(request) == 2
            and request[0] == TIMEOUT_WAKEUP_TAG
        ):
            controller(self).expire(str(request[1]))
            return None
        return original_handle(self, request_type, request)

    @wraps(original_shutdown)
    def paired_shutdown(self):
        current = getattr(self, "_p6_3c_r2_f3_atomic_pair_controller", None)
        if current is not None:
            current.shutdown()
        return original_shutdown(self)

    EngineCore.add_request = paired_add
    EngineCore.abort_requests = paired_abort
    EngineCoreProc._handle_client_request = paired_handle
    EngineCore.shutdown = paired_shutdown
    EngineCore._p6_3c_r2_f3_atomic_pair_installed = True
    EngineCoreProc._p6_3c_r2_f3_atomic_pair_timeout_handler_installed = True
    _emit(
        "atomic_pair_admission_installed",
        component=(
            "vllm.v1.engine.core.EngineCore.add_request+"
            "EngineCoreProc._handle_client_request"
        ),
        scope="tagged_p6_3c_r2_f3_measured_request_pairs_only",
        ordinary_and_warmup_requests="unchanged",
        release_order="pair_index_ascending_before_next_scheduler_step",
        timeout_seconds=_timeout_seconds(),
    )
