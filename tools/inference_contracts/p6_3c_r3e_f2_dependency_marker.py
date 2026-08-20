"""Task-local dependency marker for the P6.3C-R3E-F2 canary.

The module is copied into the runtime overlay under the historical
``p6_3c_r1_scheduler_observer`` name.  It preserves the R3 scheduler timing
observer and adds one deliberately small propagation path:

``SchedulerOutput`` receives a private, pickle-safe context dictionary and
``WorkerWrapperBase.execute_model`` opens a ``torch.profiler.record_function``
range whose name contains only lifecycle/policy/step/rank identifiers.

No prompt, generated text, token ID, or request ID is included in the marker.
The range is a structured execution scope.  It is not itself proof that a
contained runtime event or device kernel is on the causal critical path.
"""

from __future__ import annotations

from functools import wraps
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any


TRACE_DIR_ENV = "P6_3C_R1_SCHEDULER_TRACE_DIR"
MODE_ENV = "P6_3C_R1_MODE"
TRACK_ENV = "P6_3C_R1_TRACK"
REQUEST_MARKER_ENV = "P6_3C_R3_REQUEST_MARKER"
DEFAULT_REQUEST_MARKER = "p6_3c_r3e_f2_"
F2_ENABLED_ENV = "P6_3C_R3E_F2_ENABLED"
F2_LIFECYCLE_ENV = "P6_3C_R3E_F2_LIFECYCLE_ID"
F2_POLICY_ENV = "P6_3C_R3E_F2_POLICY_ID"
F2_MAX_PRESSURE_MARKERS_ENV = "P6_3C_R3E_F2_MAX_PRESSURE_MARKERS"
MARKER_ATTRIBUTE = "_p6_3c_r3e_f2_dependency_context"
MARKER_PREFIX = "AK_P6_R3E_F2"
MARKER_SCHEMA = "p6_3c_r3e_f2_dependency_marker_v1"
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
MARKER_PATTERN = re.compile(
    rf"^{MARKER_PREFIX}"
    r"\|v=1"
    r"\|l=(?P<lifecycle>[A-Za-z0-9_.:-]{1,160})"
    r"\|p=(?P<policy>[A-Za-z0-9_.:-]{1,160})"
    r"\|c=(?P<context>[A-Za-z0-9_.:-]{1,160})"
    r"\|s=(?P<step>[0-9]+)"
    r"\|r=(?P<rank>[0-9]+)$"
)

_TRACE_LOCK = threading.Lock()
_CONTEXT_LOCK = threading.Lock()
_STEP_CONTEXTS: dict[int, dict[str, Any]] = {}


def _emit(event: str, **fields: Any) -> None:
    raw_root = os.environ.get(TRACE_DIR_ENV)
    if not raw_root:
        return
    root = Path(raw_root)
    root.mkdir(parents=True, exist_ok=True)
    row = {
        "event": event,
        "pid": os.getpid(),
        "mode": os.environ.get(MODE_ENV),
        "track": os.environ.get(TRACK_ENV),
        "timestamp_ns": time.time_ns(),
        "monotonic_ns": time.monotonic_ns(),
        **fields,
    }
    with _TRACE_LOCK:
        with (root / f"trace.{os.getpid()}.jsonl").open(
            "a", encoding="utf-8"
        ) as handle:
            handle.write(
                json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n"
            )


def _safe_component(value: object, field: str) -> str:
    text = str(value)
    if SAFE_COMPONENT.fullmatch(text) is None:
        raise ValueError(f"unsafe F2 marker {field}: {text!r}")
    return text


def marker_context(
    *, lifecycle_id: str, policy_id: str, timing_context_id: str, step_index: int
) -> dict[str, Any]:
    """Return the only payload allowed to cross the EngineCore worker RPC."""

    return {
        "schema": MARKER_SCHEMA,
        "lifecycle_id": _safe_component(lifecycle_id, "lifecycle_id"),
        "policy_id": _safe_component(policy_id, "policy_id"),
        "timing_context_id": _safe_component(
            timing_context_id, "timing_context_id"
        ),
        "step_index": int(step_index),
    }


def build_marker_name(context: dict[str, Any], worker_rank: int) -> str:
    """Build a parseable marker with no request payload or token content."""

    if context.get("schema") != MARKER_SCHEMA:
        raise ValueError("F2 dependency marker schema mismatch")
    lifecycle_id = _safe_component(context.get("lifecycle_id"), "lifecycle_id")
    policy_id = _safe_component(context.get("policy_id"), "policy_id")
    timing_context_id = _safe_component(
        context.get("timing_context_id"), "timing_context_id"
    )
    step_index = int(context.get("step_index"))
    rank = int(worker_rank)
    if step_index < 0 or rank < 0:
        raise ValueError("F2 step and rank must be non-negative")
    return (
        f"{MARKER_PREFIX}|v=1|l={lifecycle_id}|p={policy_id}|"
        f"c={timing_context_id}|s={step_index}|r={rank}"
    )


def parse_marker_name(name: str) -> dict[str, Any] | None:
    match = MARKER_PATTERN.fullmatch(name)
    if match is None:
        return None
    return {
        "schema": MARKER_SCHEMA,
        "lifecycle_id": match.group("lifecycle"),
        "policy_id": match.group("policy"),
        "timing_context_id": match.group("context"),
        "step_index": int(match.group("step")),
        "worker_rank": int(match.group("rank")),
    }


def attach_marker_context(scheduler_output: object, context: dict[str, Any]) -> None:
    """Attach a private field without changing vLLM's public dataclass schema."""

    build_marker_name(context, 0)
    setattr(scheduler_output, MARKER_ATTRIBUTE, dict(context))


def _request_id(request: object) -> str:
    return str(getattr(request, "request_id", ""))


def _ordered_request_ids(requests: object) -> list[str]:
    try:
        return [_request_id(request) for request in requests]
    except (TypeError, RuntimeError):
        return []


def request_phase(request_id: str, remaining_prompt_tokens: int) -> str:
    if "_resident" in request_id:
        return "resident_prefill" if remaining_prompt_tokens > 0 else "resident_decode"
    if "_injected" in request_id:
        return "injected_prefill" if remaining_prompt_tokens > 0 else "injected_decode"
    if "_warmup" in request_id:
        return "warmup_prefill" if remaining_prompt_tokens > 0 else "warmup_decode"
    return "other"


def _request_snapshot(request: object) -> dict[str, Any]:
    prompt_tokens = int(getattr(request, "num_prompt_tokens", 0) or 0)
    computed_tokens = int(getattr(request, "num_computed_tokens", 0) or 0)
    remaining_prompt_tokens = max(prompt_tokens - computed_tokens, 0)
    request_id = _request_id(request)
    return {
        "request_id": request_id,
        "prompt_tokens": prompt_tokens,
        "computed_tokens": computed_tokens,
        "remaining_prompt_tokens": remaining_prompt_tokens,
        "phase": request_phase(request_id, remaining_prompt_tokens),
        "status": str(getattr(request, "status", "")),
        "num_preemptions": int(getattr(request, "num_preemptions", 0) or 0),
    }


def summarize_r3_scheduler_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    steps = [row for row in rows if row.get("event") == "scheduler_step"]
    mixed_steps = [
        row
        for row in steps
        if int(row.get("resident_decode_tokens") or 0) > 0
        and int(row.get("injected_prefill_tokens") or 0) > 0
    ]
    injected_partial_steps = [
        row
        for row in steps
        if any(
            item.get("phase") == "injected_prefill"
            and item.get("prefill_partial") is True
            for item in row.get("scheduled_requests") or []
        )
    ]
    return {
        "scheduler_step_count": len(steps),
        "mixed_decode_prefill_step_count": len(mixed_steps),
        "injected_partial_prefill_step_count": len(injected_partial_steps),
        "preempted_request_count": sum(
            len(row.get("preempted_request_ids") or []) for row in steps
        ),
        "max_running_count_before": max(
            (int(row.get("running_count_before") or 0) for row in steps),
            default=0,
        ),
        "max_waiting_count_before": max(
            (int(row.get("waiting_count_before") or 0) for row in steps),
            default=0,
        ),
    }


def _max_pressure_markers() -> int:
    raw = os.environ.get(F2_MAX_PRESSURE_MARKERS_ENV, "1")
    value = int(raw)
    if value < 1 or value > 8:
        raise ValueError(f"invalid {F2_MAX_PRESSURE_MARKERS_ENV}: {raw!r}")
    return value


def install_p6_3c_r1_scheduler_observer() -> None:
    """Install scheduler timing plus worker-side structured profiler ranges."""

    from vllm.v1.core.sched.scheduler import Scheduler
    from vllm.v1.executor.multiproc_executor import MultiprocExecutor
    from vllm.v1.worker.worker_base import WorkerWrapperBase

    if not getattr(Scheduler, "_p6_3c_r3e_f2_scheduler_installed", False):
        original_schedule = Scheduler.schedule

        @wraps(original_schedule)
        def observed_schedule(self):
            schedule_start_ns = time.monotonic_ns()
            step_index = int(getattr(self, "_p6_3c_r3_step_index", 0) or 0)
            setattr(self, "_p6_3c_r3_step_index", step_index + 1)

            before = {
                request_id: _request_snapshot(request)
                for request_id, request in dict(self.requests).items()
            }
            waiting_before = _ordered_request_ids(self.waiting)
            running_before = _ordered_request_ids(self.running)
            result = original_schedule(self)
            schedule_end_ns = time.monotonic_ns()

            scheduled_rows: list[dict[str, Any]] = []
            for schedule_order, (request_id, scheduled_tokens) in enumerate(
                result.num_scheduled_tokens.items(), start=1
            ):
                snapshot = before.get(request_id) or {
                    "request_id": request_id,
                    "prompt_tokens": 0,
                    "computed_tokens": 0,
                    "remaining_prompt_tokens": 0,
                    "phase": request_phase(request_id, 0),
                    "status": "unknown",
                    "num_preemptions": 0,
                }
                remaining_prompt = int(snapshot["remaining_prompt_tokens"])
                scheduled_tokens_int = int(scheduled_tokens)
                scheduled_prefill_tokens = min(
                    scheduled_tokens_int, remaining_prompt
                )
                scheduled_decode_tokens = max(
                    scheduled_tokens_int - scheduled_prefill_tokens, 0
                )
                scheduled_rows.append(
                    {
                        **snapshot,
                        "schedule_order": schedule_order,
                        "scheduled_tokens": scheduled_tokens_int,
                        "scheduled_prefill_tokens": scheduled_prefill_tokens,
                        "scheduled_decode_tokens": scheduled_decode_tokens,
                        "prefill_scheduled": scheduled_prefill_tokens > 0,
                        "prefill_partial": (
                            scheduled_prefill_tokens > 0
                            and scheduled_prefill_tokens < remaining_prompt
                        ),
                    }
                )

            waiting_after = _ordered_request_ids(self.waiting)
            running_after = _ordered_request_ids(self.running)
            request_marker = os.environ.get(
                REQUEST_MARKER_ENV, DEFAULT_REQUEST_MARKER
            )
            controller_decision = getattr(
                self, "_p6_3c_r3c_last_decision", None
            ) or {}
            effective_token_budget = int(
                controller_decision.get("selected_budget")
                or self.max_num_scheduled_tokens
            )
            relevant_ids = [
                *waiting_before,
                *running_before,
                *waiting_after,
                *running_after,
                *(row["request_id"] for row in scheduled_rows),
            ]
            if any(request_marker in request_id for request_id in relevant_ids):
                timing_context_id = f"{os.getpid()}:{step_index}:{id(result)}"
                resident_decode_tokens = sum(
                    int(row["scheduled_decode_tokens"])
                    for row in scheduled_rows
                    if row["phase"] == "resident_decode"
                )
                injected_prefill_tokens = sum(
                    int(row["scheduled_prefill_tokens"])
                    for row in scheduled_rows
                    if row["phase"] == "injected_prefill"
                )
                context = {
                    "timing_context_id": timing_context_id,
                    "step_index": step_index,
                    "schedule_start_monotonic_ns": schedule_start_ns,
                    "schedule_end_monotonic_ns": schedule_end_ns,
                }
                with _CONTEXT_LOCK:
                    _STEP_CONTEXTS[id(result)] = context

                marker_selected = False
                if (
                    os.environ.get(F2_ENABLED_ENV) == "1"
                    and resident_decode_tokens > 0
                    and injected_prefill_tokens > 0
                ):
                    selected_count = int(
                        getattr(self, "_p6_3c_r3e_f2_selected_count", 0) or 0
                    )
                    if selected_count < _max_pressure_markers():
                        dependency_context = marker_context(
                            lifecycle_id=os.environ[F2_LIFECYCLE_ENV],
                            policy_id=os.environ[F2_POLICY_ENV],
                            timing_context_id=timing_context_id,
                            step_index=step_index,
                        )
                        attach_marker_context(result, dependency_context)
                        setattr(
                            self,
                            "_p6_3c_r3e_f2_selected_count",
                            selected_count + 1,
                        )
                        marker_selected = True
                        _emit(
                            "dependency_marker_scheduled",
                            **dependency_context,
                            worker_rank_expected_count=8,
                            selection_reason="bounded_mixed_prefill_decode_pressure_step",
                        )

                _emit(
                    "scheduler_step",
                    step_index=step_index,
                    timing_context_id=timing_context_id,
                    schedule_start_monotonic_ns=schedule_start_ns,
                    schedule_end_monotonic_ns=schedule_end_ns,
                    scheduler_cpu_ns=schedule_end_ns - schedule_start_ns,
                    enable_chunked_prefill=bool(
                        self.scheduler_config.enable_chunked_prefill
                    ),
                    enable_prefix_caching=bool(
                        self.cache_config.enable_prefix_caching
                    ),
                    max_model_len=int(self.max_model_len),
                    max_num_batched_tokens=int(
                        self.scheduler_config.max_num_batched_tokens
                    ),
                    max_num_seqs=int(self.scheduler_config.max_num_seqs),
                    token_budget=int(self.max_num_scheduled_tokens),
                    effective_token_budget=effective_token_budget,
                    controller_decision=controller_decision,
                    total_num_scheduled_tokens=int(
                        result.total_num_scheduled_tokens
                    ),
                    waiting_count_before=len(waiting_before),
                    running_count_before=len(running_before),
                    waiting_order_before=waiting_before,
                    waiting_order_after=waiting_after,
                    running_order_before=running_before,
                    running_order_after=running_after,
                    resident_decode_tokens=resident_decode_tokens,
                    injected_prefill_tokens=injected_prefill_tokens,
                    mixed_decode_prefill=(
                        resident_decode_tokens > 0
                        and injected_prefill_tokens > 0
                    ),
                    dependency_marker_selected=marker_selected,
                    preempted_request_ids=sorted(
                        str(value) for value in (result.preempted_req_ids or set())
                    ),
                    scheduled_requests=scheduled_rows,
                )
            return result

        Scheduler.schedule = observed_schedule
        Scheduler._p6_3c_r1_observer_installed = True
        Scheduler._p6_3c_r3_observer_installed = True
        Scheduler._p6_3c_r3e_timing_observer_installed = True
        Scheduler._p6_3c_r3e_f2_scheduler_installed = True

    if not getattr(
        MultiprocExecutor, "_p6_3c_r3e_f2_executor_installed", False
    ):
        original_execute_model = MultiprocExecutor.execute_model

        @wraps(original_execute_model)
        def observed_execute_model(self, scheduler_output, *args, **kwargs):
            submit_start_ns = time.monotonic_ns()
            result = original_execute_model(self, scheduler_output, *args, **kwargs)
            submit_end_ns = time.monotonic_ns()
            with _CONTEXT_LOCK:
                context = dict(_STEP_CONTEXTS.get(id(scheduler_output)) or {})
            if context:
                _emit(
                    "executor_execute_submit",
                    **context,
                    submit_start_monotonic_ns=submit_start_ns,
                    submit_end_monotonic_ns=submit_end_ns,
                    executor_submit_cpu_ns=submit_end_ns - submit_start_ns,
                    non_block=bool(kwargs.get("non_block", False)),
                )

                def completed(future) -> None:
                    complete_ns = time.monotonic_ns()
                    _emit(
                        "executor_execute_complete",
                        **context,
                        executor_complete_monotonic_ns=complete_ns,
                        executor_elapsed_ns=complete_ns - submit_start_ns,
                        future_cancelled=bool(future.cancelled()),
                        future_exception_present=(
                            future.exception() is not None
                            if not future.cancelled()
                            else False
                        ),
                    )

                add_done_callback = getattr(result, "add_done_callback", None)
                if callable(add_done_callback):
                    add_done_callback(completed)
                else:
                    complete_ns = time.monotonic_ns()
                    _emit(
                        "executor_execute_complete",
                        **context,
                        executor_complete_monotonic_ns=complete_ns,
                        executor_elapsed_ns=complete_ns - submit_start_ns,
                        future_cancelled=False,
                        future_exception_present=False,
                        synchronous_return=True,
                    )
            return result

        MultiprocExecutor.execute_model = observed_execute_model
        MultiprocExecutor._p6_3c_r3e_timing_observer_installed = True
        MultiprocExecutor._p6_3c_r3e_f2_executor_installed = True

    if not getattr(
        WorkerWrapperBase, "_p6_3c_r3e_f2_worker_marker_installed", False
    ):
        original_worker_execute = WorkerWrapperBase.execute_model

        @wraps(original_worker_execute)
        def observed_worker_execute(self, scheduler_output, *args, **kwargs):
            raw_context = getattr(scheduler_output, MARKER_ATTRIBUTE, None)
            if not isinstance(raw_context, dict):
                return original_worker_execute(
                    self, scheduler_output, *args, **kwargs
                )
            worker_rank = int(
                getattr(
                    self,
                    "global_rank",
                    getattr(getattr(self, "worker", None), "rank", -1),
                )
            )
            marker_name = build_marker_name(raw_context, worker_rank)
            from torch.profiler import record_function

            range_start_ns = time.monotonic_ns()
            _emit(
                "dependency_marker_worker_enter",
                **raw_context,
                worker_rank=worker_rank,
                marker_name=marker_name,
                worker_range_start_monotonic_ns=range_start_ns,
            )
            try:
                with record_function(marker_name):
                    return original_worker_execute(
                        self, scheduler_output, *args, **kwargs
                    )
            finally:
                range_end_ns = time.monotonic_ns()
                _emit(
                    "dependency_marker_worker_exit",
                    **raw_context,
                    worker_rank=worker_rank,
                    marker_name=marker_name,
                    worker_range_end_monotonic_ns=range_end_ns,
                    worker_range_elapsed_ns=range_end_ns - range_start_ns,
                )

        WorkerWrapperBase.execute_model = observed_worker_execute
        WorkerWrapperBase._p6_3c_r3e_f2_worker_marker_installed = True

    if not getattr(Scheduler, "_p6_3c_r3e_f2_update_installed", False):
        original_update_from_output = Scheduler.update_from_output

        @wraps(original_update_from_output)
        def observed_update_from_output(self, scheduler_output, *args, **kwargs):
            update_start_ns = time.monotonic_ns()
            result = original_update_from_output(
                self, scheduler_output, *args, **kwargs
            )
            update_end_ns = time.monotonic_ns()
            with _CONTEXT_LOCK:
                context = _STEP_CONTEXTS.pop(id(scheduler_output), None)
            if context:
                _emit(
                    "scheduler_update_complete",
                    **context,
                    update_start_monotonic_ns=update_start_ns,
                    update_end_monotonic_ns=update_end_ns,
                    scheduler_update_cpu_ns=update_end_ns - update_start_ns,
                    engine_pipeline_elapsed_ns=(
                        update_start_ns - context["schedule_end_monotonic_ns"]
                    ),
                    schedule_to_update_complete_ns=(
                        update_end_ns - context["schedule_start_monotonic_ns"]
                    ),
                )
            return result

        Scheduler.update_from_output = observed_update_from_output
        Scheduler._p6_3c_r3e_f2_update_installed = True

    _emit(
        "observer_installed",
        component=(
            "Scheduler.schedule,MultiprocExecutor.execute_model,"
            "WorkerWrapperBase.execute_model,Scheduler.update_from_output"
        ),
        schema="p6_3c_r3_decode_resident_v1",
        timing_schema="p6_3c_r3e_engine_path_timing_v1",
        dependency_marker_schema=MARKER_SCHEMA,
        mutation=(
            "private_scheduler_output_context_plus_worker_record_function_range"
        ),
    )
