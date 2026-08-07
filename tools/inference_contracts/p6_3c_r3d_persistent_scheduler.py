"""Persistent Prefill-pressure controller for P6.3C-R3D.

R3C capped the scheduler budget only while a Prefill request was in the
waiting queue.  Once the first chunk moved that request into ``running``, the
condition became false and the following iteration used the full 12288-token
budget.  R3D makes that state transition explicit and evaluates a second
policy: keep the cap while any running request still has uncomputed prompt
tokens.

The module is copied into a task-local runtime overlay.  It never changes the
configured ``max_num_batched_tokens`` or KV-cache capacity; it temporarily
changes only ``Scheduler.max_num_scheduled_tokens`` for one ``schedule()``
call and restores the field in ``finally``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable, Iterable


_ORIGINAL_SCHEDULE: Callable[..., Any] | None = None
_TRACE_LOCK = threading.Lock()
_VALID_PRESSURE_SCOPES = {"admission_only", "persistent_prefill"}


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value is not None:
            return value
    return None


def _int_env(names: tuple[str, ...], default: int) -> int:
    raw = _first_env(*names)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{names[0]} must be an integer, got {raw!r}") from error
    if value <= 0:
        raise ValueError(f"{names[0]} must be positive, got {value}")
    return value


def _pressure_scope() -> str:
    value = os.environ.get("P6_3C_R3D_PRESSURE_SCOPE", "persistent_prefill")
    if value not in _VALID_PRESSURE_SCOPES:
        raise ValueError(
            "P6_3C_R3D_PRESSURE_SCOPE must be admission_only or "
            f"persistent_prefill, got {value!r}"
        )
    return value


def _enabled() -> bool:
    # The historical base lifecycle runner owns the R3C-named process switch.
    # Accept it as a compatibility alias while exposing an R3D-native switch
    # for standalone self-tests and future runners.
    return _first_env("P6_3C_R3D_ADAPTIVE_ENABLED", "P6_3C_R3C_ADAPTIVE_ENABLED") == "1"


def _trace_path() -> Path | None:
    raw = _first_env("P6_3C_R3D_CONTROLLER_TRACE_DIR", "P6_3C_R3C_CONTROLLER_TRACE_DIR")
    if not raw:
        return None
    directory = Path(raw)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "schedule_decisions.jsonl"


def _iter_requests(value: Any) -> Iterable[Any]:
    try:
        return tuple(value)
    except (TypeError, RuntimeError):
        return ()


def _request_has_unfinished_prefill(request: Any) -> bool:
    prompt_tokens = int(getattr(request, "num_prompt_tokens", 0) or 0)
    computed_tokens = int(getattr(request, "num_computed_tokens", 0) or 0)
    return prompt_tokens > 0 and computed_tokens < prompt_tokens


def _request_is_decode_resident(request: Any) -> bool:
    prompt_tokens = int(getattr(request, "num_prompt_tokens", 0) or 0)
    computed_tokens = int(getattr(request, "num_computed_tokens", 0) or 0)
    return prompt_tokens > 0 and computed_tokens >= prompt_tokens


def _request_state(scheduler: Any) -> dict[str, int]:
    running = _iter_requests(getattr(scheduler, "running", ()))
    waiting = (
        *_iter_requests(getattr(scheduler, "waiting", ())),
        *_iter_requests(getattr(scheduler, "skipped_waiting", ())),
    )
    return {
        "decode_resident_count": sum(
            _request_is_decode_resident(request) for request in running
        ),
        "waiting_prefill_count": sum(
            _request_has_unfinished_prefill(request) for request in waiting
        ),
        "running_unfinished_prefill_count": sum(
            _request_has_unfinished_prefill(request) for request in running
        ),
    }


def _effective_budget(scheduler: Any) -> dict[str, int | str | bool]:
    configured_budget = int(
        getattr(scheduler, "max_num_scheduled_tokens")
        or getattr(scheduler.scheduler_config, "max_num_batched_tokens")
    )
    state = _request_state(scheduler)
    scope = _pressure_scope()
    decode_quantum = _int_env(
        (
            "P6_3C_R3D_DECODE_QUANTUM_TOKENS",
            "P6_3C_R3C_DECODE_QUANTUM_TOKENS",
        ),
        2,
    )
    active_chunk_target = _int_env(
        (
            "P6_3C_R3D_ACTIVE_CHUNK_TOKENS",
            "P6_3C_R3C_ACTIVE_CHUNK_TOKENS",
        ),
        512,
    )
    active_prefill_count = state["waiting_prefill_count"]
    if scope == "persistent_prefill":
        active_prefill_count += state["running_unfinished_prefill_count"]
    decode_reserve = state["decode_resident_count"] * decode_quantum
    pressure = state["decode_resident_count"] > 0 and active_prefill_count > 0
    selected_budget = (
        min(configured_budget, decode_reserve + active_chunk_target)
        if pressure
        else configured_budget
    )
    return {
        "configured_budget": configured_budget,
        **state,
        "active_prefill_count": active_prefill_count,
        "pressure_scope": scope,
        "decode_quantum_tokens": decode_quantum,
        "decode_reserve_tokens": decode_reserve,
        "active_chunk_target_tokens": active_chunk_target,
        "selected_budget": max(1, selected_budget),
        "pressure_active": pressure,
        "decision": "pressure_capped" if pressure else "full_budget",
    }


def _write_trace(record: dict[str, Any]) -> None:
    path = _trace_path()
    if path is None:
        return
    with _TRACE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def install() -> bool:
    """Install the schedule wrapper once in the real EngineCore process."""

    global _ORIGINAL_SCHEDULE
    if _ORIGINAL_SCHEDULE is not None or not _enabled():
        return False

    from vllm.v1.core.sched.scheduler import Scheduler

    original = Scheduler.schedule

    def persistent_schedule(self: Any, *args: Any, **kwargs: Any) -> Any:
        decision = _effective_budget(self)
        previous_budget = int(self.max_num_scheduled_tokens)
        # The outer read-only observer reads this exact per-step decision after
        # the controller restores the public scheduler field.
        setattr(self, "_p6_3c_r3c_last_decision", dict(decision))
        setattr(self, "_p6_3c_r3d_last_decision", dict(decision))
        self.max_num_scheduled_tokens = int(decision["selected_budget"])
        record = {
            "schema": "p6_3c_r3d_persistent_scheduler_v1",
            "timestamp_ns": time.monotonic_ns(),
            "pid": os.getpid(),
            **decision,
            "previous_budget": previous_budget,
        }
        try:
            return original(self, *args, **kwargs)
        finally:
            self.max_num_scheduled_tokens = previous_budget
            _write_trace(record)

    persistent_schedule.__name__ = "p6_3c_r3d_persistent_schedule"
    persistent_schedule.__doc__ = original.__doc__
    Scheduler.schedule = persistent_schedule
    _ORIGINAL_SCHEDULE = original
    setattr(Scheduler, "_p6_3c_r3d_persistent_installed", True)
    marker = _first_env(
        "P6_3C_R3D_CONTROLLER_MARKER_PATH", "P6_3C_R3C_CONTROLLER_MARKER_PATH"
    )
    if marker:
        marker_path = Path(marker)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(
            json.dumps(
                {
                    "schema": "p6_3c_r3d_persistent_scheduler_v1",
                    "installed": True,
                    "pid": os.getpid(),
                    "pressure_scope": _pressure_scope(),
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return True


def install_from_env() -> bool:
    return install() if _enabled() else False


def controller_contract() -> dict[str, Any]:
    return {
        "schema": "p6_3c_r3d_persistent_scheduler_v1",
        "enabled": _enabled(),
        "configured_budget_preserved": True,
        "pressure_scope": _pressure_scope(),
        "pressure_condition": (
            "decode_resident_count>0 and "
            "(waiting_prefill_count+running_unfinished_prefill_count)>0"
            if _pressure_scope() == "persistent_prefill"
            else "decode_resident_count>0 and waiting_prefill_count>0"
        ),
        "active_chunk_target_tokens": _int_env(
            (
                "P6_3C_R3D_ACTIVE_CHUNK_TOKENS",
                "P6_3C_R3C_ACTIVE_CHUNK_TOKENS",
            ),
            512,
        ),
        "decode_quantum_tokens": _int_env(
            (
                "P6_3C_R3D_DECODE_QUANTUM_TOKENS",
                "P6_3C_R3C_DECODE_QUANTUM_TOKENS",
            ),
            2,
        ),
        "selected_budget": (
            "min(configured_budget, decode_reserve + active_chunk_target)"
        ),
        "scheduler_field_changed": "max_num_scheduled_tokens_only",
        "trace_path": str(_trace_path()) if _trace_path() else None,
    }
