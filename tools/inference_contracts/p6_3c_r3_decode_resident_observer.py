"""Read-only scheduler observer for P6.3C-R3 staged-arrival experiments.

The server runtime overlay imports this file under the historical module name
``p6_3c_r1_scheduler_observer``.  Keep the public installer and marker names
compatible with that overlay while emitting the richer R3 evidence schema.
"""

from __future__ import annotations

from functools import wraps
import json
import os
from pathlib import Path
import time
from typing import Any


TRACE_DIR_ENV = "P6_3C_R1_SCHEDULER_TRACE_DIR"
MODE_ENV = "P6_3C_R1_MODE"
TRACK_ENV = "P6_3C_R1_TRACK"
REQUEST_MARKER_ENV = "P6_3C_R3_REQUEST_MARKER"
DEFAULT_REQUEST_MARKER = "p6_3c_r3a_"


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
    with (root / f"trace.{os.getpid()}.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")


def _request_id(request: object) -> str:
    return str(getattr(request, "request_id", ""))


def _ordered_request_ids(requests: object) -> list[str]:
    try:
        return [_request_id(request) for request in requests]
    except (TypeError, RuntimeError):
        return []


def request_phase(request_id: str, remaining_prompt_tokens: int) -> str:
    """Classify task-local requests without depending on runtime ID suffixes."""

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
    """Build a compact mechanism summary from observer output."""

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


def install_p6_3c_r1_scheduler_observer() -> None:
    """Wrap ``Scheduler.schedule`` and return its exact original output."""

    from vllm.v1.core.sched.scheduler import Scheduler

    if getattr(Scheduler, "_p6_3c_r1_observer_installed", False):
        return

    original_schedule = Scheduler.schedule

    @wraps(original_schedule)
    def observed_schedule(self):
        step_index = int(getattr(self, "_p6_3c_r3_step_index", 0) or 0)
        setattr(self, "_p6_3c_r3_step_index", step_index + 1)

        before = {
            request_id: _request_snapshot(request)
            for request_id, request in dict(self.requests).items()
        }
        waiting_before = _ordered_request_ids(self.waiting)
        running_before = _ordered_request_ids(self.running)
        result = original_schedule(self)

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
            scheduled_prefill_tokens = min(scheduled_tokens_int, remaining_prompt)
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
        marker = os.environ.get(REQUEST_MARKER_ENV, DEFAULT_REQUEST_MARKER)
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
        if any(marker in request_id for request_id in relevant_ids):
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
            _emit(
                "scheduler_step",
                step_index=step_index,
                enable_chunked_prefill=bool(
                    self.scheduler_config.enable_chunked_prefill
                ),
                enable_prefix_caching=bool(self.cache_config.enable_prefix_caching),
                max_model_len=int(self.max_model_len),
                max_num_batched_tokens=int(
                    self.scheduler_config.max_num_batched_tokens
                ),
                max_num_seqs=int(self.scheduler_config.max_num_seqs),
                token_budget=int(self.max_num_scheduled_tokens),
                effective_token_budget=effective_token_budget,
                controller_decision=controller_decision,
                total_num_scheduled_tokens=int(result.total_num_scheduled_tokens),
                waiting_count_before=len(waiting_before),
                running_count_before=len(running_before),
                waiting_order_before=waiting_before,
                waiting_order_after=waiting_after,
                running_order_before=running_before,
                running_order_after=running_after,
                resident_decode_tokens=resident_decode_tokens,
                injected_prefill_tokens=injected_prefill_tokens,
                mixed_decode_prefill=(
                    resident_decode_tokens > 0 and injected_prefill_tokens > 0
                ),
                preempted_request_ids=sorted(
                    str(value) for value in (result.preempted_req_ids or set())
                ),
                scheduled_requests=scheduled_rows,
            )
        return result

    Scheduler.schedule = observed_schedule
    Scheduler._p6_3c_r1_observer_installed = True
    Scheduler._p6_3c_r3_observer_installed = True
    _emit(
        "observer_installed",
        component="vllm.v1.core.sched.scheduler.Scheduler.schedule",
        schema="p6_3c_r3_decode_resident_v1",
        mutation="observe_only_wrapper_returns_original_result",
    )
