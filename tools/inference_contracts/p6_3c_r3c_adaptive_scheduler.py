"""Runtime-local adaptive scheduler budget controller for P6.3C-R3C.

The controller deliberately leaves ``max_num_batched_tokens`` unchanged.  It
only changes the per-iteration ``Scheduler.max_num_scheduled_tokens`` while a
decode-resident cohort and a waiting prefill coexist.  This separates KV-cache
capacity from the transient prefill chunk selected for the current scheduler
iteration.

The module is installed in a task-local runtime overlay.  It is not a general
vLLM feature and is enabled only when ``P6_3C_R3C_ADAPTIVE_ENABLED=1``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable


_ORIGINAL_SCHEDULE: Callable[..., Any] | None = None
_TRACE_LOCK = threading.Lock()


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer, got {value!r}") from error
    if parsed <= 0:
        raise ValueError(f"{name} must be positive, got {parsed}")
    return parsed


def _trace_path() -> Path | None:
    raw = os.environ.get("P6_3C_R3C_CONTROLLER_TRACE_DIR")
    if not raw:
        return None
    directory = Path(raw)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "schedule_decisions.jsonl"


def _queue_size(queue: Any) -> int:
    try:
        return len(queue)
    except (TypeError, AttributeError):
        return 0


def _decode_resident_count(scheduler: Any) -> int:
    count = 0
    for request in getattr(scheduler, "running", ()):
        prompt_tokens = int(getattr(request, "num_prompt_tokens", 0) or 0)
        computed_tokens = int(getattr(request, "num_computed_tokens", 0) or 0)
        if prompt_tokens > 0 and computed_tokens >= prompt_tokens:
            count += 1
    return count


def _effective_budget(scheduler: Any) -> dict[str, int | str]:
    configured_budget = int(
        getattr(scheduler, "max_num_scheduled_tokens")
        or getattr(scheduler.scheduler_config, "max_num_batched_tokens")
    )
    decode_count = _decode_resident_count(scheduler)
    waiting_count = _queue_size(getattr(scheduler, "waiting", None)) + _queue_size(
        getattr(scheduler, "skipped_waiting", None)
    )
    decode_quantum = _int_env("P6_3C_R3C_DECODE_QUANTUM_TOKENS", 2)
    active_chunk_target = _int_env("P6_3C_R3C_ACTIVE_CHUNK_TOKENS", 4096)
    decode_reserve = decode_count * decode_quantum
    pressure = decode_count > 0 and waiting_count > 0
    selected_budget = (
        min(configured_budget, decode_reserve + active_chunk_target)
        if pressure
        else configured_budget
    )
    return {
        "configured_budget": configured_budget,
        "decode_resident_count": decode_count,
        "waiting_prefill_count": waiting_count,
        "decode_quantum_tokens": decode_quantum,
        "decode_reserve_tokens": decode_reserve,
        "active_chunk_target_tokens": active_chunk_target,
        "selected_budget": max(1, selected_budget),
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
    """Wrap ``Scheduler.schedule`` once and return whether installation ran."""

    global _ORIGINAL_SCHEDULE
    if _ORIGINAL_SCHEDULE is not None:
        return False
    if os.environ.get("P6_3C_R3C_ADAPTIVE_ENABLED") != "1":
        return False

    from vllm.v1.core.sched.scheduler import Scheduler

    original = Scheduler.schedule

    def adaptive_schedule(self: Any, *args: Any, **kwargs: Any) -> Any:
        decision = _effective_budget(self)
        previous_budget = int(self.max_num_scheduled_tokens)
        # The observer overlay may be installed outside this wrapper.  Keep
        # the decision on the Scheduler instance so that an outer observer can
        # record the effective budget after this wrapper restores the public
        # scheduler field.  This is evidence-only state; it does not alter
        # vLLM's scheduling result or configuration.
        setattr(self, "_p6_3c_r3c_last_decision", dict(decision))
        self.max_num_scheduled_tokens = int(decision["selected_budget"])
        record = {
            "schema": "p6_3c_r3c_adaptive_scheduler_v1",
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

    adaptive_schedule.__name__ = "p6_3c_r3c_adaptive_schedule"
    adaptive_schedule.__doc__ = original.__doc__
    Scheduler.schedule = adaptive_schedule
    _ORIGINAL_SCHEDULE = original
    setattr(Scheduler, "_p6_3c_r3c_adaptive_installed", True)
    marker = os.environ.get("P6_3C_R3C_CONTROLLER_MARKER_PATH")
    if marker:
        marker_path = Path(marker)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(
            json.dumps(
                {
                    "schema": "p6_3c_r3c_adaptive_scheduler_v1",
                    "installed": True,
                    "pid": os.getpid(),
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return True


def install_from_env() -> bool:
    """Entry point used by ``sitecustomize`` and the server self-test."""

    if os.environ.get("P6_3C_R3C_ADAPTIVE_ENABLED") != "1":
        return False
    return install()


def controller_contract() -> dict[str, Any]:
    """Return the immutable policy settings recorded in lifecycle evidence."""

    return {
        "schema": "p6_3c_r3c_adaptive_scheduler_v1",
        "enabled": os.environ.get("P6_3C_R3C_ADAPTIVE_ENABLED") == "1",
        "configured_budget_preserved": True,
        "active_chunk_target_tokens": _int_env(
            "P6_3C_R3C_ACTIVE_CHUNK_TOKENS", 4096
        ),
        "decode_quantum_tokens": _int_env(
            "P6_3C_R3C_DECODE_QUANTUM_TOKENS", 2
        ),
        "pressure_condition": "decode_resident_count>0 and waiting_prefill_count>0",
        "selected_budget": "min(configured_budget, decode_reserve + active_chunk_target)",
        "trace_path": os.environ.get("P6_3C_R3C_CONTROLLER_TRACE_DIR"),
    }
