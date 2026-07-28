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
    with (root / f"trace.{os.getpid()}.jsonl").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")


def _request_id(request: object) -> str:
    return str(getattr(request, "request_id", ""))


def _ordered_request_ids(requests: object) -> list[str]:
    try:
        return [_request_id(request) for request in requests]
    except (TypeError, RuntimeError):
        return []


def _request_snapshot(request: object) -> dict[str, Any]:
    prompt_tokens = int(getattr(request, "num_prompt_tokens", 0) or 0)
    computed_tokens = int(getattr(request, "num_computed_tokens", 0) or 0)
    return {
        "request_id": _request_id(request),
        "prompt_tokens": prompt_tokens,
        "computed_tokens": computed_tokens,
        "remaining_prompt_tokens": max(prompt_tokens - computed_tokens, 0),
        "status": str(getattr(request, "status", "")),
    }


def summarize_scheduler_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    steps = [row for row in rows if row.get("event") == "scheduler_step"]
    requests: dict[str, dict[str, Any]] = {}
    for step in steps:
        for scheduled in step.get("scheduled_requests") or []:
            if not scheduled.get("prefill_scheduled"):
                continue
            request_id = str(scheduled.get("request_id") or "")
            item = requests.setdefault(
                request_id,
                {
                    "request_id": request_id,
                    "prompt_tokens": int(scheduled.get("prompt_tokens") or 0),
                    "prefill_round_count": 0,
                    "partial_prefill_round_count": 0,
                    "scheduled_prefill_tokens": 0,
                    "first_step_index": int(step.get("step_index") or 0),
                    "last_step_index": int(step.get("step_index") or 0),
                },
            )
            item["prefill_round_count"] += 1
            item["partial_prefill_round_count"] += int(
                scheduled.get("prefill_partial") is True
            )
            item["scheduled_prefill_tokens"] += min(
                int(scheduled.get("scheduled_tokens") or 0),
                int(scheduled.get("remaining_prompt_tokens_before") or 0),
            )
            item["last_step_index"] = int(step.get("step_index") or 0)
    request_rows = sorted(
        requests.values(),
        key=lambda item: (item["first_step_index"], item["request_id"]),
    )
    return {
        "scheduler_step_count": len(steps),
        "prefill_request_count": len(request_rows),
        "partial_prefill_request_count": sum(
            item["partial_prefill_round_count"] > 0 for item in request_rows
        ),
        "request_rows": request_rows,
    }


def install_p6_3c_r1_scheduler_observer() -> None:
    from vllm.v1.core.sched.scheduler import Scheduler

    if getattr(Scheduler, "_p6_3c_r1_observer_installed", False):
        return

    original_schedule = Scheduler.schedule

    @wraps(original_schedule)
    def observed_schedule(self):
        step_index = int(getattr(self, "_p6_3c_r1_step_index", 0) or 0)
        setattr(self, "_p6_3c_r1_step_index", step_index + 1)

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
                "status": "unknown",
            }
            remaining_prompt = int(snapshot["remaining_prompt_tokens"])
            scheduled_tokens_int = int(scheduled_tokens)
            prefill_scheduled = remaining_prompt > 0 and scheduled_tokens_int > 0
            scheduled_rows.append(
                {
                    "request_id": request_id,
                    "schedule_order": schedule_order,
                    "prompt_tokens": int(snapshot["prompt_tokens"]),
                    "computed_tokens_before": int(snapshot["computed_tokens"]),
                    "remaining_prompt_tokens_before": remaining_prompt,
                    "scheduled_tokens": scheduled_tokens_int,
                    "prefill_scheduled": prefill_scheduled,
                    "prefill_partial": (
                        prefill_scheduled and scheduled_tokens_int < remaining_prompt
                    ),
                }
            )

        waiting_after = _ordered_request_ids(self.waiting)
        running_after = _ordered_request_ids(self.running)
        relevant = (
            any(row["prefill_scheduled"] for row in scheduled_rows)
            or any("p6_3c_r1_" in request_id for request_id in waiting_before)
            or any("p6_3c_r1_" in request_id for request_id in waiting_after)
        )
        if relevant:
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
                total_num_scheduled_tokens=int(result.total_num_scheduled_tokens),
                waiting_order_before=waiting_before,
                waiting_order_after=waiting_after,
                running_order_before=running_before,
                running_order_after=running_after,
                scheduled_requests=scheduled_rows,
            )
        return result

    Scheduler.schedule = observed_schedule
    Scheduler._p6_3c_r1_observer_installed = True
    _emit(
        "observer_installed",
        component="vllm.v1.core.sched.scheduler.Scheduler.schedule",
        mutation="observe_only_wrapper_returns_original_result",
    )
