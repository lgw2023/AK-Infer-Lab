"""P6.3C-R3 staged-arrival Chunked Prefill experiment driver.

This driver separates the scientific mechanism gate from the performance
measurement.  Two observer-enabled lifecycles first establish the actual
decode-resident admission cliff.  Four observer-free lifecycles run only when
that scout gate is satisfied.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Iterable
import urllib.error
import urllib.request


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts import (  # noqa: E402
    run_deepseek_p6_3c_r1_scheduler_pressure as base,
)
from tools.inference_contracts.p6_3c_local_http_transport import (  # noqa: E402
    open_loopback,
)


TASK_ID = "p6_3c_r3a_decode_resident_admission_cliff_2026_0803_run01"
WORKLOAD_RELATIVE_PATH = (
    "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r3a_decode_resident_admission_cliff_matched_ab.yaml"
)
REQUEST_PREFIX = "p6_3c_r3a"
MODES = ("chunked_prefill_off", "chunked_prefill_on")
TRACKS = ("mechanism", "performance")
MAX_MODEL_LEN = 12288
MAX_NUM_BATCHED_TOKENS = 12288
MAX_NUM_SEQS = 9
RESIDENT_COUNT = 8
RESIDENT_PROMPT_TOKENS = 256
RESIDENT_OUTPUT_TOKENS = 128
RESIDENT_INJECTION_GATE_TOKENS = 16
INJECTED_OUTPUT_TOKENS = 4
CELLS = (
    {
        "cell_id": "resident_only",
        "injected_prompt_tokens": None,
        "role": "decode_interference_baseline",
    },
    {
        "cell_id": "fit_control_12000",
        "injected_prompt_tokens": 12000,
        "role": "whole_prefill_admission_control",
    },
    {
        "cell_id": "admission_cliff_12281",
        "injected_prompt_tokens": 12281,
        "role": "decode_resident_admission_cliff",
    },
)
LIFECYCLE_SCHEDULE = (
    {
        "track": "mechanism",
        "lifecycle_id": "mechanism_01",
        "pair_id": "mechanism_pair",
        "pair_position": "first",
        "mode": "chunked_prefill_off",
    },
    {
        "track": "mechanism",
        "lifecycle_id": "mechanism_02",
        "pair_id": "mechanism_pair",
        "pair_position": "second",
        "mode": "chunked_prefill_on",
    },
    {
        "track": "performance",
        "lifecycle_id": "performance_01",
        "pair_id": "pair_01",
        "pair_position": "first",
        "mode": "chunked_prefill_off",
    },
    {
        "track": "performance",
        "lifecycle_id": "performance_02",
        "pair_id": "pair_01",
        "pair_position": "second",
        "mode": "chunked_prefill_on",
    },
    {
        "track": "performance",
        "lifecycle_id": "performance_03",
        "pair_id": "pair_02",
        "pair_position": "first",
        "mode": "chunked_prefill_on",
    },
    {
        "track": "performance",
        "lifecycle_id": "performance_04",
        "pair_id": "pair_02",
        "pair_position": "second",
        "mode": "chunked_prefill_off",
    },
)
PERFORMANCE_CELL_SEQUENCE = (
    "resident_only",
    "fit_control_12000",
    "admission_cliff_12281",
    "admission_cliff_12281",
    "fit_control_12000",
    "resident_only",
) * 3
EXPECTED_ENGINE_REQUESTS = 682
EXPECTED_HTTP_REQUESTS = 136
BOUNDED_CANDIDATES = (
    "result_summary.md",
    "environment_and_hashes.json",
    "payload_identity_summary.json",
    "lifecycle_summary.tsv",
    "r3_s0_mechanism_scout_summary.json",
    "r3_s0_mechanism_cells.tsv",
    "performance_mode_cell_summary.tsv",
    "performance_paired_effects.tsv",
    "scientific_outcome.json",
    "grading_inputs.json",
    "startup_resource_summary.tsv",
    "resource_recovery_summary.json",
    "cleanup_status.txt",
    "first_failure_excerpt.txt",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repeat_and_truncate(source: list[int], length: int, offset: int) -> list[int]:
    if not source or length <= 0:
        raise ValueError("source tokens and requested length must be non-empty")
    rotated = source[offset:] + source[:offset]
    return (rotated * math.ceil(length / len(rotated)))[:length]


def _cell(cell_id: str) -> dict[str, Any]:
    return next(item for item in CELLS if item["cell_id"] == cell_id)


def build_trial_plan(track: str) -> list[dict[str, Any]]:
    if track == "mechanism":
        sequence = [item["cell_id"] for item in CELLS]
    elif track == "performance":
        sequence = list(PERFORMANCE_CELL_SEQUENCE)
    else:
        raise ValueError(f"unsupported track: {track}")
    repeats = {item["cell_id"]: 0 for item in CELLS}
    trials: list[dict[str, Any]] = []
    for order_index, cell_id in enumerate(sequence, start=1):
        repeats[cell_id] += 1
        repeat_index = repeats[cell_id]
        trial_id = f"{REQUEST_PREFIX}_{track}_{cell_id}_r{repeat_index:02d}"
        trials.append(
            {
                "track": track,
                "phase": "measured",
                "order_index": order_index,
                "trial_id": trial_id,
                "cell_id": cell_id,
                "repeat_index": repeat_index,
                "resident_request_id": f"{trial_id}_resident",
                "injected_request_id": (
                    f"{trial_id}_injected"
                    if _cell(cell_id)["injected_prompt_tokens"] is not None
                    else None
                ),
                "injected_prompt_tokens": _cell(cell_id)["injected_prompt_tokens"],
            }
        )
    return trials


def build_run_plan() -> dict[str, Any]:
    return {
        "warmups": {
            track: {
                "track": track,
                "phase": "warmup",
                "request_id": f"{REQUEST_PREFIX}_{track}_warmup",
                "body_relative_path": f"bodies/{track}_warmup.json",
                "prompt_tokens": 512,
                "output_tokens": 32,
            }
            for track in TRACKS
        },
        "trials": {track: build_trial_plan(track) for track in TRACKS},
    }


def _completion_body(
    *,
    model_name: str,
    request_id: str,
    prompts: list[list[int]],
    output_tokens: int,
) -> dict[str, Any]:
    return {
        "ignore_eos": True,
        "max_tokens": output_tokens,
        "min_tokens": output_tokens,
        "model": model_name,
        "prompt": prompts[0] if len(prompts) == 1 else prompts,
        "request_id": request_id,
        "return_token_ids": True,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": 0.0,
    }


def _write_body(
    artifact_dir: Path,
    relative_path: str,
    body: dict[str, Any],
) -> tuple[str, int]:
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    path = artifact_dir / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return _sha256_bytes(encoded), len(encoded)


def prepare_artifacts(
    source_payload: Path,
    artifact_dir: Path,
    model_name: str,
) -> dict[str, Any]:
    source = json.loads(source_payload.read_text(encoding="utf-8"))
    source_tokens = source.get("prompt")
    if (
        not isinstance(source_tokens, list)
        or len(source_tokens) != 4096
        or not all(
            isinstance(item, int) and not isinstance(item, bool)
            for item in source_tokens
        )
    ):
        raise ValueError("source payload must contain exactly 4096 integer token IDs")
    artifact_dir.mkdir(parents=True, exist_ok=False)
    plan = build_run_plan()
    records: list[dict[str, Any]] = []
    body_index = 0

    for track, warmup in plan["warmups"].items():
        prompt = _repeat_and_truncate(source_tokens, 512, body_index * 131)
        body_index += 1
        body = _completion_body(
            model_name=model_name,
            request_id=warmup["request_id"],
            prompts=[prompt],
            output_tokens=32,
        )
        digest, size = _write_body(artifact_dir, warmup["body_relative_path"], body)
        warmup["request_body_sha256"] = digest
        records.append(
            {
                "track": track,
                "phase": "warmup",
                "request_role": "warmup",
                "request_id": warmup["request_id"],
                "body_relative_path": warmup["body_relative_path"],
                "body_bytes": size,
                "request_body_sha256": digest,
                "prompt_token_lengths": [512],
                "output_tokens_per_choice": 32,
            }
        )

    for track, trials in plan["trials"].items():
        for trial in trials:
            resident_prompts = []
            for choice_index in range(RESIDENT_COUNT):
                offset = (body_index * 521 + choice_index * 977) % len(source_tokens)
                resident_prompts.append(
                    _repeat_and_truncate(source_tokens, RESIDENT_PROMPT_TOKENS, offset)
                )
            resident_relative = f"bodies/{trial['trial_id']}.resident.json"
            resident_body = _completion_body(
                model_name=model_name,
                request_id=trial["resident_request_id"],
                prompts=resident_prompts,
                output_tokens=RESIDENT_OUTPUT_TOKENS,
            )
            digest, size = _write_body(artifact_dir, resident_relative, resident_body)
            trial["resident_body_relative_path"] = resident_relative
            trial["resident_body_sha256"] = digest
            records.append(
                {
                    "track": track,
                    "phase": "measured",
                    "trial_id": trial["trial_id"],
                    "cell_id": trial["cell_id"],
                    "repeat_index": trial["repeat_index"],
                    "request_role": "resident",
                    "request_id": trial["resident_request_id"],
                    "body_relative_path": resident_relative,
                    "body_bytes": size,
                    "request_body_sha256": digest,
                    "prompt_token_lengths": [RESIDENT_PROMPT_TOKENS] * RESIDENT_COUNT,
                    "output_tokens_per_choice": RESIDENT_OUTPUT_TOKENS,
                }
            )
            injected_prompt_tokens = trial["injected_prompt_tokens"]
            if injected_prompt_tokens is not None:
                offset = (body_index * 521 + 313) % len(source_tokens)
                injected_prompt = _repeat_and_truncate(
                    source_tokens, int(injected_prompt_tokens), offset
                )
                injected_relative = f"bodies/{trial['trial_id']}.injected.json"
                injected_body = _completion_body(
                    model_name=model_name,
                    request_id=trial["injected_request_id"],
                    prompts=[injected_prompt],
                    output_tokens=INJECTED_OUTPUT_TOKENS,
                )
                injected_digest, injected_size = _write_body(
                    artifact_dir, injected_relative, injected_body
                )
                trial["injected_body_relative_path"] = injected_relative
                trial["injected_body_sha256"] = injected_digest
                records.append(
                    {
                        "track": track,
                        "phase": "measured",
                        "trial_id": trial["trial_id"],
                        "cell_id": trial["cell_id"],
                        "repeat_index": trial["repeat_index"],
                        "request_role": "injected",
                        "request_id": trial["injected_request_id"],
                        "body_relative_path": injected_relative,
                        "body_bytes": injected_size,
                        "request_body_sha256": injected_digest,
                        "prompt_token_lengths": [injected_prompt_tokens],
                        "output_tokens_per_choice": INJECTED_OUTPUT_TOKENS,
                    }
                )
            body_index += 1

    (artifact_dir / "run_plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "task_id": TASK_ID,
        "source_prompt_tokens": len(source_tokens),
        "resident_count": RESIDENT_COUNT,
        "resident_prompt_tokens": RESIDENT_PROMPT_TOKENS,
        "resident_output_tokens": RESIDENT_OUTPUT_TOKENS,
        "resident_injection_gate_tokens": RESIDENT_INJECTION_GATE_TOKENS,
        "injected_output_tokens": INJECTED_OUTPUT_TOKENS,
        "mechanism_trial_count": len(plan["trials"]["mechanism"]),
        "performance_trial_count_per_lifecycle": len(plan["trials"]["performance"]),
        "body_record_count": len(records),
        "bodies_reused_byte_identically_across_matched_lifecycles": True,
        "generated_text_retained": False,
        "generated_token_ids_retained": False,
        "records": records,
    }
    (artifact_dir / "request_body_manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


class ResidentGate:
    def __init__(self, choice_count: int, threshold: int):
        self.choice_count = choice_count
        self.threshold = threshold
        self.counts = [0] * choice_count
        self.gate_open_ns: int | None = None
        self.done = False
        self.error: str | None = None
        self.condition = threading.Condition()

    def add_tokens(self, choice_index: int, count: int, timestamp_ns: int) -> None:
        with self.condition:
            self.counts[choice_index] += count
            if self.gate_open_ns is None and all(
                value >= self.threshold for value in self.counts
            ):
                self.gate_open_ns = timestamp_ns
            self.condition.notify_all()

    def finish(self, error: str | None) -> None:
        with self.condition:
            self.done = True
            self.error = error
            self.condition.notify_all()

    def wait(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        with self.condition:
            while self.gate_open_ns is None and not self.done:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.condition.wait(timeout=remaining)
            return self.gate_open_ns is not None


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _load_body(artifact_dir: Path, relative_path: str, expected_sha: str) -> bytes:
    body = (artifact_dir / relative_path).read_bytes()
    if _sha256_bytes(body) != expected_sha:
        raise ValueError(f"request body hash drift: {relative_path}")
    return body


def _stream_body(
    *,
    artifact_dir: Path,
    base_url: str,
    server_pid: int,
    relative_path: str,
    expected_sha: str,
    request_role: str,
    expected_choice_count: int,
    expected_output_tokens: int,
    on_tokens: Callable[[int, int, int], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    body = _load_body(artifact_dir, relative_path, expected_sha)
    payload = json.loads(body)
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/completions",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    arrivals: list[list[int]] = [[] for _ in range(expected_choice_count)]
    finish_reasons: list[str | None] = [None] * expected_choice_count
    finish_ns: list[int | None] = [None] * expected_choice_count
    max_chunk_widths = [0] * expected_choice_count
    usage: dict[str, Any] = {}
    saw_done = False
    http_status: int | None = None
    error_text: str | None = None
    request_start_ns = time.monotonic_ns()
    try:
        with open_loopback(request, timeout=7200) as response:
            http_status = int(response.status)
            for raw_line in response:
                now_ns = time.monotonic_ns()
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    saw_done = True
                    continue
                item = json.loads(data)
                if isinstance(item.get("usage"), dict):
                    usage = item["usage"]
                for choice in item.get("choices") or []:
                    choice_index = int(choice["index"])
                    if choice_index < 0 or choice_index >= expected_choice_count:
                        raise ValueError(f"unexpected choice index {choice_index}")
                    token_count = len(choice.get("token_ids") or [])
                    arrivals[choice_index].extend([now_ns] * token_count)
                    max_chunk_widths[choice_index] = max(
                        max_chunk_widths[choice_index], token_count
                    )
                    if on_tokens is not None and token_count:
                        on_tokens(choice_index, token_count, now_ns)
                    if choice.get("finish_reason") is not None:
                        finish_reasons[choice_index] = str(choice["finish_reason"])
                        finish_ns[choice_index] = now_ns
    except urllib.error.HTTPError as error:
        http_status = int(error.code)
        error_text = f"HTTPError:{error.code}:{error.read(4096)!r}"
    except Exception as error:  # Server evidence preserves a bounded exception.
        error_text = f"{type(error).__name__}:{str(error)[:2048]}"
    request_end_ns = time.monotonic_ns()

    prompt_field = payload["prompt"]
    prompts = [prompt_field] if expected_choice_count == 1 else prompt_field
    expected_prompt_total = sum(len(prompt) for prompt in prompts)
    expected_completion_total = expected_choice_count * expected_output_tokens
    rows = []
    for choice_index in range(expected_choice_count):
        token_arrivals = arrivals[choice_index]
        actual_end_ns = finish_ns[choice_index] or request_end_ns
        metrics = base.calculate_request_metrics(
            request_start_ns, token_arrivals, actual_end_ns
        )
        checks = {
            "server_alive": _process_alive(server_pid),
            "http_200": http_status == 200,
            "streamed_tokens_exact": len(token_arrivals) == expected_output_tokens,
            "finish_reason_length": finish_reasons[choice_index] == "length",
            "saw_done": saw_done,
            "max_token_chunk_width_within_mtp_bound": max_chunk_widths[choice_index]
            <= 2,
            "usage_prompt_total_exact": usage.get("prompt_tokens")
            == expected_prompt_total,
            "usage_completion_total_exact": (
                usage.get("completion_tokens") == expected_completion_total
            ),
        }
        rows.append(
            {
                "request_role": request_role,
                "choice_index": choice_index,
                "prompt_tokens": len(prompts[choice_index]),
                "output_tokens": expected_output_tokens,
                "request_body_sha256": expected_sha,
                "status": "success" if all(checks.values()) else "failed",
                "failure_reason": error_text,
                "http_status": http_status,
                "streamed_token_count": len(token_arrivals),
                "finish_reason": finish_reasons[choice_index],
                "max_token_chunk_width": max_chunk_widths[choice_index],
                "request_start_ns": request_start_ns,
                "token_arrival_ns": token_arrivals,
                "request_end_ns": actual_end_ns,
                **metrics,
                "checks": checks,
                "generated_text_retained": False,
                "generated_token_ids_retained": False,
            }
        )
    duration_seconds = (request_end_ns - request_start_ns) / 1_000_000_000
    summary = {
        "request_role": request_role,
        "request_start_ns": request_start_ns,
        "request_end_ns": request_end_ns,
        "first_token_ns": min(
            (values[0] for values in arrivals if values), default=None
        ),
        "status": "success"
        if all(row["status"] == "success" for row in rows)
        else "failed",
        "choice_count": expected_choice_count,
        "output_tokens_per_second": (
            round(expected_completion_total / duration_seconds, 6)
            if duration_seconds > 0
            else 0.0
        ),
        "http_status": http_status,
        "error": error_text,
    }
    return rows, summary


def _window_tbt(
    arrivals: list[int], start_ns: int | None, end_ns: int | None
) -> list[float]:
    values = []
    for left, right in zip(arrivals, arrivals[1:]):
        if start_ns is not None and right < start_ns:
            continue
        if end_ns is not None and right > end_ns:
            continue
        values.append((right - left) / 1_000_000)
    return values


def _max_token_stall_ms(rows: Iterable[dict[str, Any]]) -> float:
    """Return the largest observed adjacent-token gap across request rows."""

    stalls = [
        (right - left) / 1_000_000
        for row in rows
        for left, right in zip(
            row.get("token_arrival_ns") or [],
            (row.get("token_arrival_ns") or [])[1:],
        )
    ]
    return round(max(stalls), 6) if stalls else 0.0


def _summarize_values(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "median": None, "p95": None, "p99": None, "max": None}
    return {
        "n": len(values),
        "median": round(statistics.median(values), 6),
        "p95": round(base.percentile(values, 0.95), 6),
        "p99": round(base.percentile(values, 0.99), 6),
        "max": round(max(values), 6),
    }


def run_staged_trial(
    artifact_dir: Path,
    base_url: str,
    server_pid: int,
    trial: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gate = ResidentGate(RESIDENT_COUNT, RESIDENT_INJECTION_GATE_TOKENS)
    holder: dict[str, Any] = {}

    def run_residents() -> None:
        try:
            rows, summary = _stream_body(
                artifact_dir=artifact_dir,
                base_url=base_url,
                server_pid=server_pid,
                relative_path=trial["resident_body_relative_path"],
                expected_sha=trial["resident_body_sha256"],
                request_role="resident",
                expected_choice_count=RESIDENT_COUNT,
                expected_output_tokens=RESIDENT_OUTPUT_TOKENS,
                on_tokens=gate.add_tokens,
            )
            holder["rows"] = rows
            holder["summary"] = summary
            gate.finish(summary.get("error"))
        except Exception as error:  # A bounded failure becomes trial evidence.
            holder["error"] = f"{type(error).__name__}:{str(error)[:2048]}"
            gate.finish(holder["error"])

    resident_thread = threading.Thread(target=run_residents, daemon=True)
    resident_thread.start()
    gate_reached = gate.wait(timeout_seconds=900)
    resident_alive_at_injection = resident_thread.is_alive()
    injection_dispatch_ns: int | None = None
    injected_rows: list[dict[str, Any]] = []
    injected_summary: dict[str, Any] | None = None
    if trial["injected_request_id"] is not None and gate_reached:
        injection_dispatch_ns = time.monotonic_ns()
        injected_rows, injected_summary = _stream_body(
            artifact_dir=artifact_dir,
            base_url=base_url,
            server_pid=server_pid,
            relative_path=trial["injected_body_relative_path"],
            expected_sha=trial["injected_body_sha256"],
            request_role="injected",
            expected_choice_count=1,
            expected_output_tokens=INJECTED_OUTPUT_TOKENS,
        )
    resident_thread.join(timeout=7200)
    if resident_thread.is_alive():
        holder["error"] = "resident_stream_join_timeout"

    resident_rows = list(holder.get("rows") or [])
    resident_summary = dict(holder.get("summary") or {})
    injection_first_token_ns = (
        injected_summary.get("first_token_ns") if injected_summary else None
    )
    all_pre_tbt: list[float] = []
    all_interference_tbt: list[float] = []
    all_recovery_tbt: list[float] = []
    for row in resident_rows:
        arrivals = list(row.get("token_arrival_ns") or [])
        if injection_dispatch_ns is None:
            pre = _window_tbt(arrivals, None, None)
            interference = []
            recovery = []
        else:
            pre = _window_tbt(arrivals, None, injection_dispatch_ns)
            interference = _window_tbt(
                arrivals, injection_dispatch_ns, injection_first_token_ns
            )
            recovery = _window_tbt(arrivals, injection_first_token_ns, None)
        all_pre_tbt.extend(pre)
        all_interference_tbt.extend(interference)
        all_recovery_tbt.extend(recovery)
        row.update(
            {
                "pre_injection_tbt": _summarize_values(pre),
                "prefill_interference_tbt": _summarize_values(interference),
                "post_prefill_tbt": _summarize_values(recovery),
            }
        )

    arrival_contract = {
        "all_residents_reached_gate": gate_reached,
        "resident_gate_token_threshold": RESIDENT_INJECTION_GATE_TOKENS,
        "resident_token_counts_at_gate_or_finish": list(gate.counts),
        "gate_open_ns": gate.gate_open_ns,
        "injection_dispatch_ns": injection_dispatch_ns,
        "injection_after_gate": (
            injection_dispatch_ns is None
            or (
                gate.gate_open_ns is not None
                and injection_dispatch_ns >= gate.gate_open_ns
            )
        ),
        "resident_stream_alive_at_injection": (
            True if injection_dispatch_ns is None else resident_alive_at_injection
        ),
        "resident_stream_error": gate.error or holder.get("error"),
    }
    arrival_contract_exact = all(
        (
            arrival_contract["all_residents_reached_gate"],
            arrival_contract["injection_after_gate"],
            arrival_contract["resident_stream_alive_at_injection"],
            arrival_contract["resident_stream_error"] is None,
        )
    )
    all_rows = resident_rows + injected_rows
    for row in all_rows:
        row.update(
            {
                "track": trial["track"],
                "phase": "measured",
                "trial_id": trial["trial_id"],
                "cell_id": trial["cell_id"],
                "repeat_index": trial["repeat_index"],
            }
        )
    request_start_values = [
        int(row["request_start_ns"]) for row in all_rows if row.get("request_start_ns")
    ]
    request_end_values = [
        int(row["request_end_ns"]) for row in all_rows if row.get("request_end_ns")
    ]
    makespan_seconds = (
        (max(request_end_values) - min(request_start_values)) / 1_000_000_000
        if request_start_values and request_end_values
        else 0.0
    )
    total_output_tokens = RESIDENT_COUNT * RESIDENT_OUTPUT_TOKENS + (
        INJECTED_OUTPUT_TOKENS if trial["injected_request_id"] is not None else 0
    )
    trial_status = (
        "success"
        if arrival_contract_exact
        and len(resident_rows) == RESIDENT_COUNT
        and all(row.get("status") == "success" for row in all_rows)
        and (trial["injected_request_id"] is None or len(injected_rows) == 1)
        else "failed"
    )
    trial_row = {
        **{
            key: trial[key]
            for key in ("track", "trial_id", "cell_id", "repeat_index", "order_index")
        },
        "status": trial_status,
        "arrival_contract": arrival_contract,
        "arrival_contract_exact": arrival_contract_exact,
        "resident_request_status": resident_summary.get("status"),
        "injected_request_status": (
            injected_summary.get("status") if injected_summary else None
        ),
        "injected_ttft_ms": (
            injected_rows[0].get("ttft_ms") if injected_rows else None
        ),
        "injected_e2el_ms": (
            injected_rows[0].get("e2el_ms") if injected_rows else None
        ),
        "resident_pre_injection_tbt": _summarize_values(all_pre_tbt),
        "resident_prefill_interference_tbt": _summarize_values(all_interference_tbt),
        "resident_post_prefill_tbt": _summarize_values(all_recovery_tbt),
        # This is the literal maximum adjacent-token gap.  Earlier revisions
        # accidentally stored max(per-request ITL p99) under this name.
        "resident_max_stall_ms": _max_token_stall_ms(resident_rows),
        "trial_makespan_ms": round(makespan_seconds * 1000, 6),
        "aggregate_output_tokens_per_second": (
            round(total_output_tokens / makespan_seconds, 6)
            if makespan_seconds > 0
            else 0.0
        ),
        "request_count": len(all_rows),
        "http_request_count": 1 + int(trial["injected_request_id"] is not None),
    }
    return all_rows, trial_row


def _warmup(
    artifact_dir: Path,
    base_url: str,
    server_pid: int,
    warmup: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows, summary = _stream_body(
        artifact_dir=artifact_dir,
        base_url=base_url,
        server_pid=server_pid,
        relative_path=warmup["body_relative_path"],
        expected_sha=warmup["request_body_sha256"],
        request_role="warmup",
        expected_choice_count=1,
        expected_output_tokens=int(warmup["output_tokens"]),
    )
    for row in rows:
        row.update(
            {
                "track": warmup["track"],
                "phase": "warmup",
                "trial_id": warmup["request_id"],
                "cell_id": "warmup",
                "repeat_index": 0,
            }
        )
    return rows, {
        "track": warmup["track"],
        "phase": "warmup",
        "trial_id": warmup["request_id"],
        "cell_id": "warmup",
        "repeat_index": 0,
        "status": summary["status"],
        "request_count": 1,
        "http_request_count": 1,
    }


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def execute_mode(
    artifact_dir: Path,
    lifecycle_dir: Path,
    base_url: str,
    server_pid: int,
    track: str,
    mode: str,
) -> int:
    if track not in TRACKS or mode not in MODES:
        raise ValueError(f"unsupported track/mode: {track}/{mode}")
    plan = json.loads((artifact_dir / "run_plan.json").read_text(encoding="utf-8"))
    raw_metrics_dir = lifecycle_dir / "runtime" / "raw_metrics"
    request_rows: list[dict[str, Any]] = []
    trial_rows: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = [plan["warmups"][track], *plan["trials"][track]]
    for item in items:
        health_before, _ = base._get(base_url, "/health", timeout=5)  # noqa: SLF001
        idle_before, metrics_before = base._wait_for_idle(  # noqa: SLF001
            base_url,
            raw_metrics_dir
            / f"{item.get('trial_id', item.get('request_id'))}.before.prom",
        )
        if (
            health_before != 200
            or not idle_before
            or metrics_before.get("spec_metrics_present") is not True
        ):
            rows = []
            trial_row = {
                "track": track,
                "phase": item["phase"],
                "trial_id": item.get("trial_id", item.get("request_id")),
                "cell_id": item.get("cell_id", "warmup"),
                "repeat_index": item.get("repeat_index", 0),
                "status": "failed",
                "failure_reason": "pre_trial_health_queue_or_mtp_metric_gate",
                "request_count": 0,
                "http_request_count": 0,
            }
        elif item["phase"] == "warmup":
            rows, trial_row = _warmup(artifact_dir, base_url, server_pid, item)
        else:
            rows, trial_row = run_staged_trial(artifact_dir, base_url, server_pid, item)
        health_after, _ = base._get(base_url, "/health", timeout=5)  # noqa: SLF001
        idle_after, metrics_after = base._wait_for_idle(  # noqa: SLF001
            base_url,
            raw_metrics_dir
            / f"{item.get('trial_id', item.get('request_id'))}.after.prom",
        )
        spec_delta = {
            name: float(metrics_after.get(name) or 0)
            - float(metrics_before.get(name) or 0)
            for name in ("num_drafts", "num_draft_tokens", "num_accepted_tokens")
        }
        execution_health = (
            health_after == 200
            and idle_after
            and metrics_after.get("queue_metrics_present") is True
            and metrics_after.get("spec_metrics_present") is True
            and spec_delta["num_drafts"] > 0
            and spec_delta["num_draft_tokens"] > 0
            and _process_alive(server_pid)
        )
        trial_row.update(
            {
                "lifecycle_id": lifecycle_dir.name,
                "mode": mode,
                "server_healthy_and_idle_after": execution_health,
                "mtp_counter_delta": spec_delta,
            }
        )
        if not execution_health:
            trial_row["status"] = "failed"
        for row in rows:
            row["lifecycle_id"] = lifecycle_dir.name
            row["mode"] = mode
        request_rows.extend(rows)
        trial_rows.append(trial_row)
        _write_jsonl(lifecycle_dir / "raw_request_results.jsonl", request_rows)
        _write_jsonl(lifecycle_dir / "raw_trial_results.jsonl", trial_rows)
        if trial_row["status"] != "success":
            break

    expected_trial_count = 4 if track == "mechanism" else 19
    expected_request_count = 27 if track == "mechanism" else 157
    expected_http_count = 6 if track == "mechanism" else 31
    complete = (
        len(trial_rows) == expected_trial_count
        and len(request_rows) == expected_request_count
        and sum(int(row.get("http_request_count") or 0) for row in trial_rows)
        == expected_http_count
        and all(row.get("status") == "success" for row in trial_rows)
        and all(row.get("status") == "success" for row in request_rows)
    )
    return 0 if complete else 2


def _read_trace_rows(lifecycle_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(
        (lifecycle_dir / "runtime/scheduler_trace").glob("trace.*.jsonl")
    ):
        rows.extend(_read_jsonl(path))
    return rows


def _contains_marker(row: dict[str, Any], marker: str) -> bool:
    return marker in json.dumps(row, separators=(",", ":"))


def mechanism_scout_summary(
    artifact_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for lifecycle in LIFECYCLE_SCHEDULE[:2]:
        lifecycle_dir = artifact_dir / "lifecycles" / lifecycle["lifecycle_id"]
        trace = _read_trace_rows(lifecycle_dir)
        observer_installed = any(
            item.get("event") == "observer_installed"
            and item.get("schema") == "p6_3c_r3_decode_resident_v1"
            for item in trace
        )
        for trial in build_trial_plan("mechanism"):
            resident_marker = f"cmpl-{trial['resident_request_id']}-"
            injection_marker = (
                f"cmpl-{trial['injected_request_id']}"
                if trial["injected_request_id"]
                else None
            )
            relevant = [
                item
                for item in trace
                if item.get("event") == "scheduler_step"
                and _contains_marker(item, injection_marker or resident_marker)
            ]
            relevant.sort(key=lambda item: int(item.get("step_index") or 0))
            first = relevant[0] if relevant else {}
            injected_scheduled = [
                item
                for item in first.get("scheduled_requests") or []
                if injection_marker
                and injection_marker in str(item.get("request_id") or "")
            ]
            injected_tokens = sum(
                int(item.get("scheduled_prefill_tokens") or 0)
                for item in injected_scheduled
            )
            injected_partial = any(
                item.get("prefill_partial") is True for item in injected_scheduled
            )
            resident_running_count = sum(
                resident_marker in request_id
                for request_id in first.get("running_order_before") or []
            )
            injected_waiting = bool(
                injection_marker
                and any(
                    injection_marker in request_id
                    for request_id in first.get("waiting_order_before") or []
                )
            )
            preempted = sorted(
                {
                    str(request_id)
                    for item in relevant
                    for request_id in item.get("preempted_request_ids") or []
                }
            )
            rows.append(
                {
                    "lifecycle_id": lifecycle["lifecycle_id"],
                    "mode": lifecycle["mode"],
                    "cell_id": trial["cell_id"],
                    "observer_installed": observer_installed,
                    "relevant_step_count": len(relevant),
                    "first_relevant_step": first.get("step_index"),
                    "resident_running_count_first_step": resident_running_count,
                    "resident_decode_tokens_first_step": int(
                        first.get("resident_decode_tokens") or 0
                    ),
                    "injected_prompt_tokens": trial["injected_prompt_tokens"],
                    "injected_waiting_first_step": injected_waiting,
                    "injected_scheduled_tokens_first_step": injected_tokens,
                    "injected_partial_first_step": injected_partial,
                    "mixed_decode_prefill_first_step": first.get(
                        "mixed_decode_prefill"
                    ),
                    "preempted_request_ids": preempted,
                }
            )

    by_key = {(row["mode"], row["cell_id"]): row for row in rows}
    off_fit = by_key.get(("chunked_prefill_off", "fit_control_12000"), {})
    on_fit = by_key.get(("chunked_prefill_on", "fit_control_12000"), {})
    off_cliff = by_key.get(("chunked_prefill_off", "admission_cliff_12281"), {})
    on_cliff = by_key.get(("chunked_prefill_on", "admission_cliff_12281"), {})
    all_observed = len(rows) == 6 and all(
        row["observer_installed"] and row["relevant_step_count"] > 0 for row in rows
    )
    resident_state_exact = all(
        row["resident_running_count_first_step"] == RESIDENT_COUNT
        and row["resident_decode_tokens_first_step"] > 0
        for row in rows
        if row["cell_id"] != "resident_only"
    )
    fit_control_exact = all(
        row.get("injected_scheduled_tokens_first_step") == 12000
        and row.get("injected_partial_first_step") is False
        for row in (off_fit, on_fit)
    )
    cliff_off_wait_exact = (
        off_cliff.get("injected_waiting_first_step") is True
        and off_cliff.get("injected_scheduled_tokens_first_step") == 0
    )
    cliff_on_partial_exact = (
        on_cliff.get("injected_waiting_first_step") is True
        and 0 < int(on_cliff.get("injected_scheduled_tokens_first_step") or 0) < 12281
        and on_cliff.get("injected_partial_first_step") is True
        and on_cliff.get("mixed_decode_prefill_first_step") is True
    )
    no_preemption = all(not row["preempted_request_ids"] for row in rows)
    gate = all(
        (
            all_observed,
            resident_state_exact,
            fit_control_exact,
            cliff_off_wait_exact,
            cliff_on_partial_exact,
            no_preemption,
        )
    )
    summary = {
        "task_id": TASK_ID,
        "scout_cell_count": len(rows),
        "observer_and_steps_observed": all_observed,
        "eight_residents_running_with_positive_decode_budget": resident_state_exact,
        "fit_control_whole_admission_both_modes": fit_control_exact,
        "off_cliff_waits_with_zero_prefill_tokens": cliff_off_wait_exact,
        "on_cliff_partial_mixed_admission": cliff_on_partial_exact,
        "no_preemption_observed": no_preemption,
        "r3_s0_gate_complete": gate,
        "formal_performance_authorized_by_scout": gate,
        "scientific_contract_changed": False,
    }
    return summary, rows


def _write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def write_scout_evidence(artifact_dir: Path) -> dict[str, Any]:
    summary, rows = mechanism_scout_summary(artifact_dir)
    (artifact_dir / "r3_s0_mechanism_scout_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    fields = list(rows[0]) if rows else ["lifecycle_id", "mode", "cell_id"]
    _write_tsv(artifact_dir / "r3_s0_mechanism_cells.tsv", rows, fields)
    return summary


def _relative_change(new: float | None, old: float | None) -> float | None:
    if new is None or old in (None, 0):
        return None
    return round((float(new) - float(old)) / float(old), 6)


def paired_bootstrap_median_ci(
    differences: list[float],
    *,
    samples: int = 10000,
    seed: int = 633,
) -> dict[str, Any]:
    if not differences:
        return {"n": 0, "median": None, "ci95_low": None, "ci95_high": None}
    rng = random.Random(seed)
    boot = []
    for _ in range(samples):
        draw = [differences[rng.randrange(len(differences))] for _ in differences]
        boot.append(statistics.median(draw))
    return {
        "n": len(differences),
        "median": round(statistics.median(differences), 6),
        "ci95_low": round(base.percentile(boot, 0.025), 6),
        "ci95_high": round(base.percentile(boot, 0.975), 6),
        "bootstrap_samples": samples,
        "seed": seed,
    }


def _performance_evidence(
    artifact_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    trial_rows: list[dict[str, Any]] = []
    for lifecycle in LIFECYCLE_SCHEDULE[2:]:
        path = (
            artifact_dir
            / "lifecycles"
            / lifecycle["lifecycle_id"]
            / "raw_trial_results.jsonl"
        )
        for row in _read_jsonl(path):
            if row.get("phase") != "warmup":
                row["pair_id"] = lifecycle["pair_id"]
                trial_rows.append(row)

    mode_cell_rows: list[dict[str, Any]] = []
    for mode in MODES:
        for cell in CELLS:
            selected = [
                row
                for row in trial_rows
                if row.get("mode") == mode
                and row.get("cell_id") == cell["cell_id"]
                and row.get("status") == "success"
            ]
            injected_ttft = [
                float(row["injected_ttft_ms"])
                for row in selected
                if row.get("injected_ttft_ms") is not None
            ]
            interference_p99 = [
                float(row["resident_prefill_interference_tbt"]["p99"])
                for row in selected
                if row.get("resident_prefill_interference_tbt", {}).get("p99")
                is not None
            ]
            throughput = [
                float(row["aggregate_output_tokens_per_second"]) for row in selected
            ]
            mode_cell_rows.append(
                {
                    "mode": mode,
                    "cell_id": cell["cell_id"],
                    "valid_trial_count": len(selected),
                    "injected_ttft_ms_median": (
                        round(statistics.median(injected_ttft), 6)
                        if injected_ttft
                        else None
                    ),
                    "injected_ttft_ms_p95": (
                        round(base.percentile(injected_ttft, 0.95), 6)
                        if injected_ttft
                        else None
                    ),
                    "resident_interference_tbt_p99_ms_median": (
                        round(statistics.median(interference_p99), 6)
                        if interference_p99
                        else None
                    ),
                    "aggregate_output_tps_median": (
                        round(statistics.median(throughput), 6) if throughput else None
                    ),
                }
            )

    paired_rows: list[dict[str, Any]] = []
    paired_differences: dict[str, list[float]] = {
        cell["cell_id"]: [] for cell in CELLS if cell["injected_prompt_tokens"]
    }
    for pair_id in ("pair_01", "pair_02"):
        pair_lifecycles = [
            row for row in LIFECYCLE_SCHEDULE if row["pair_id"] == pair_id
        ]
        off_lifecycle = next(
            row["lifecycle_id"]
            for row in pair_lifecycles
            if row["mode"] == "chunked_prefill_off"
        )
        on_lifecycle = next(
            row["lifecycle_id"]
            for row in pair_lifecycles
            if row["mode"] == "chunked_prefill_on"
        )
        for cell in CELLS:
            if cell["injected_prompt_tokens"] is None:
                continue
            for repeat_index in range(1, 7):
                off = next(
                    (
                        row
                        for row in trial_rows
                        if row["lifecycle_id"] == off_lifecycle
                        and row["cell_id"] == cell["cell_id"]
                        and int(row["repeat_index"]) == repeat_index
                    ),
                    None,
                )
                on = next(
                    (
                        row
                        for row in trial_rows
                        if row["lifecycle_id"] == on_lifecycle
                        and row["cell_id"] == cell["cell_id"]
                        and int(row["repeat_index"]) == repeat_index
                    ),
                    None,
                )
                valid = bool(
                    off
                    and on
                    and off.get("status") == "success"
                    and on.get("status") == "success"
                    and off.get("injected_ttft_ms") is not None
                    and on.get("injected_ttft_ms") is not None
                )
                delta = (
                    float(on["injected_ttft_ms"]) - float(off["injected_ttft_ms"])
                    if valid
                    else None
                )
                if delta is not None:
                    paired_differences[cell["cell_id"]].append(delta)
                paired_rows.append(
                    {
                        "pair_id": pair_id,
                        "cell_id": cell["cell_id"],
                        "repeat_index": repeat_index,
                        "off_lifecycle_id": off_lifecycle,
                        "on_lifecycle_id": on_lifecycle,
                        "valid_pair": valid,
                        "off_injected_ttft_ms": (
                            off.get("injected_ttft_ms") if off else None
                        ),
                        "on_injected_ttft_ms": (
                            on.get("injected_ttft_ms") if on else None
                        ),
                        "on_minus_off_ttft_ms": delta,
                    }
                )

    by_key = {(row["mode"], row["cell_id"]): row for row in mode_cell_rows}
    effects = {}
    for cell in CELLS:
        cell_id = cell["cell_id"]
        off = by_key.get(("chunked_prefill_off", cell_id), {})
        on = by_key.get(("chunked_prefill_on", cell_id), {})
        effects[cell_id] = {
            "injected_ttft_relative_change_on_vs_off": _relative_change(
                on.get("injected_ttft_ms_median"),
                off.get("injected_ttft_ms_median"),
            ),
            "resident_interference_p99_relative_change_on_vs_off": _relative_change(
                on.get("resident_interference_tbt_p99_ms_median"),
                off.get("resident_interference_tbt_p99_ms_median"),
            ),
            "aggregate_output_tps_relative_change_on_vs_off": _relative_change(
                on.get("aggregate_output_tps_median"),
                off.get("aggregate_output_tps_median"),
            ),
            "paired_bootstrap_on_minus_off_ttft_ms": paired_bootstrap_median_ci(
                paired_differences.get(cell_id, [])
            ),
        }
    return mode_cell_rows, paired_rows, effects


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), *args],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unavailable"


def _lifecycle_rows(artifact_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for expected in LIFECYCLE_SCHEDULE:
        lifecycle_dir = artifact_dir / "lifecycles" / expected["lifecycle_id"]
        requests = _read_jsonl(lifecycle_dir / "raw_request_results.jsonl")
        trials = _read_jsonl(lifecycle_dir / "raw_trial_results.jsonl")
        attempted = (lifecycle_dir / "lifecycle_attempted.txt").is_file()
        resolved_path = lifecycle_dir / "runtime/resolved_scheduler_config.json"
        resolved = (
            json.loads(resolved_path.read_text(encoding="utf-8"))
            if resolved_path.is_file()
            else {}
        )
        cleanup_path = lifecycle_dir / "cleanup_status.txt"
        exit_path = lifecycle_dir / "lifecycle_exit_code.txt"
        rows.append(
            {
                **expected,
                "request_count": len(requests),
                "successful_request_count": sum(
                    row.get("status") == "success" for row in requests
                ),
                "trial_count": len(trials),
                "successful_trial_count": sum(
                    row.get("status") == "success" for row in trials
                ),
                "http_request_count": sum(
                    int(row.get("http_request_count") or 0) for row in trials
                ),
                "resolved_enable_chunked_prefill": resolved.get(
                    "resolved_enable_chunked_prefill"
                ),
                "resolved_enable_prefix_caching": resolved.get(
                    "resolved_enable_prefix_caching"
                ),
                "max_num_seqs": resolved.get("max_num_seqs"),
                "observer_enabled": resolved.get("observer_enabled"),
                "lifecycle_attempted": attempted,
                "cleanup_status": (
                    cleanup_path.read_text(encoding="utf-8").strip()
                    if cleanup_path.is_file()
                    else ("missing" if attempted else "not_run")
                ),
                "lifecycle_exit_code": (
                    exit_path.read_text(encoding="utf-8").strip()
                    if exit_path.is_file()
                    else ("missing" if attempted else "not_run")
                ),
            }
        )
    return rows


def _argv_single_variable_exact(
    artifact_dir: Path,
) -> tuple[bool, list[dict[str, Any]]]:
    evidence = base._argv_evidence(list(LIFECYCLE_SCHEDULE), artifact_dir)  # noqa: SLF001
    return bool(evidence["all_single_variable_exact"]), evidence["pair_checks"]


def _startup_rows(artifact_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for lifecycle in LIFECYCLE_SCHEDULE:
        path = (
            artifact_dir
            / "lifecycles"
            / lifecycle["lifecycle_id"]
            / "runtime/startup_resource_summary.json"
        )
        if path.is_file():
            rows.append({**lifecycle, **json.loads(path.read_text(encoding="utf-8"))})
    return rows


def _payload_identity_summary(artifact_dir: Path) -> dict[str, Any]:
    manifest = json.loads(
        (artifact_dir / "request_body_manifest.json").read_text(encoding="utf-8")
    )
    records = manifest["records"]
    files_exact = all(
        (artifact_dir / row["body_relative_path"]).is_file()
        and _sha256_path(artifact_dir / row["body_relative_path"])
        == row["request_body_sha256"]
        for row in records
    )
    return {
        key: manifest[key]
        for key in (
            "task_id",
            "source_prompt_tokens",
            "resident_count",
            "resident_prompt_tokens",
            "resident_output_tokens",
            "resident_injection_gate_tokens",
            "injected_output_tokens",
            "mechanism_trial_count",
            "performance_trial_count_per_lifecycle",
            "body_record_count",
            "bodies_reused_byte_identically_across_matched_lifecycles",
            "generated_text_retained",
            "generated_token_ids_retained",
        )
    } | {
        "manifest_sha256": _sha256_path(artifact_dir / "request_body_manifest.json"),
        "all_body_files_sha256_exact": files_exact,
    }


def _scientific_outcome(
    scout: dict[str, Any],
    effects: dict[str, Any],
    performance_complete: bool,
) -> dict[str, Any]:
    cliff = effects.get("admission_cliff_12281", {})
    ttft_change = cliff.get("injected_ttft_relative_change_on_vs_off")
    decode_change = cliff.get("resident_interference_p99_relative_change_on_vs_off")
    throughput_change = cliff.get("aggregate_output_tps_relative_change_on_vs_off")
    practical_benefit = ttft_change is not None and ttft_change <= -0.20
    decode_cost_ok = decode_change is not None and decode_change <= 0.10
    throughput_cost_ok = throughput_change is not None and throughput_change >= -0.05
    ci = cliff.get("paired_bootstrap_on_minus_off_ttft_ms", {})
    confidence_directional = ci.get("ci95_high") is not None and ci["ci95_high"] < 0
    if not scout.get("r3_s0_gate_complete"):
        outcome = "mechanism_not_identified"
    elif not performance_complete:
        outcome = "mechanism_confirmed_performance_incomplete"
    elif practical_benefit and decode_cost_ok and throughput_cost_ok:
        outcome = "mechanism_confirmed_user_benefit_observed"
    elif practical_benefit:
        outcome = "mechanism_confirmed_tradeoff_only"
    else:
        outcome = "mechanism_confirmed_no_material_benefit"
    return {
        "task_id": TASK_ID,
        "scientific_outcome": outcome,
        "mechanism_confirmed": scout.get("r3_s0_gate_complete") is True,
        "performance_complete": performance_complete,
        "admission_cliff_ttft_relative_change_on_vs_off": ttft_change,
        "resident_p99_tbt_relative_change_on_vs_off": decode_change,
        "aggregate_output_tps_relative_change_on_vs_off": throughput_change,
        "practical_benefit_threshold": "median_injected_ttft_reduction_at_least_20_percent",
        "practical_benefit_threshold_met": practical_benefit,
        "paired_bootstrap_ci_supports_direction": confidence_directional,
        "deployment_cost_bound_resident_p99_tbt": "increase_at_most_10_percent",
        "deployment_cost_bound_resident_p99_tbt_met": decode_cost_ok,
        "deployment_cost_bound_aggregate_output_tps": "decrease_at_most_5_percent",
        "deployment_cost_bound_aggregate_output_tps_met": throughput_cost_ok,
        "claim_boundary": (
            "controlled_decode_resident_staged_arrival_only_no_natural_traffic_"
            "or_universal_benefit_claim"
        ),
    }


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    scout = write_scout_evidence(artifact_dir)
    lifecycle_rows = _lifecycle_rows(artifact_dir)
    mode_cell_rows, paired_rows, effects = _performance_evidence(artifact_dir)
    payload = _payload_identity_summary(artifact_dir)
    (artifact_dir / "payload_identity_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    single_variable_exact, argv_evidence = _argv_single_variable_exact(artifact_dir)
    startup_rows = _startup_rows(artifact_dir)

    request_count = sum(row["request_count"] for row in lifecycle_rows)
    successful_request_count = sum(
        row["successful_request_count"] for row in lifecycle_rows
    )
    http_count = sum(row["http_request_count"] for row in lifecycle_rows)
    performance_complete = all(
        row["lifecycle_exit_code"] == "0"
        and row["request_count"] == 157
        and row["successful_request_count"] == 157
        and row["trial_count"] == 19
        and row["successful_trial_count"] == 19
        and row["http_request_count"] == 31
        for row in lifecycle_rows[2:]
    )
    mechanism_complete = all(
        row["lifecycle_exit_code"] == "0"
        and row["request_count"] == 27
        and row["successful_request_count"] == 27
        and row["trial_count"] == 4
        and row["successful_trial_count"] == 4
        and row["http_request_count"] == 6
        for row in lifecycle_rows[:2]
    )
    resolved_exact = all(
        row["resolved_enable_chunked_prefill"] == (row["mode"] == "chunked_prefill_on")
        and row["resolved_enable_prefix_caching"] is False
        and row["max_num_seqs"] == MAX_NUM_SEQS
        and row["observer_enabled"] == (row["track"] == "mechanism")
        for row in lifecycle_rows
    )
    observer_absent_performance = all(
        not list(
            (
                artifact_dir
                / "lifecycles"
                / row["lifecycle_id"]
                / "runtime/scheduler_trace"
            ).glob("trace.*.jsonl")
        )
        for row in lifecycle_rows[2:]
    )
    lifecycle_cleanup = all(row["cleanup_status"] == "clean" for row in lifecycle_rows)
    recovery_path = artifact_dir / "resource_recovery_summary.json"
    recovery = (
        json.loads(recovery_path.read_text(encoding="utf-8"))
        if recovery_path.is_file()
        else {}
    )
    global_cleanup = (
        (artifact_dir / "cleanup_status.txt").read_text(encoding="utf-8").strip()
        if (artifact_dir / "cleanup_status.txt").is_file()
        else "missing"
    )
    cleanup_complete = (
        lifecycle_cleanup
        and recovery.get("keep_alive_restored_exact") is True
        and global_cleanup == "clean"
    )
    full_counts = (
        request_count == EXPECTED_ENGINE_REQUESTS
        and successful_request_count == EXPECTED_ENGINE_REQUESTS
        and http_count == EXPECTED_HTTP_REQUESTS
    )
    startup_complete = len(startup_rows) == 6 and all(
        row.get("server_ready") is True for row in startup_rows
    )
    evidence_complete = all(
        (
            mechanism_complete,
            scout["r3_s0_gate_complete"],
            performance_complete,
            full_counts,
            single_variable_exact,
            resolved_exact,
            observer_absent_performance,
            payload["all_body_files_sha256_exact"],
            startup_complete,
            cleanup_complete,
        )
    )
    outcome = _scientific_outcome(scout, effects, performance_complete)
    (artifact_dir / "scientific_outcome.json").write_text(
        json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    evidence_status = (
        "complete"
        if evidence_complete
        else (
            "scout_complete_formal_performance_not_authorized"
            if mechanism_complete and not scout["r3_s0_gate_complete"]
            else "incomplete"
        )
    )
    grading = {
        "task_id": TASK_ID,
        "server_grade": (
            "complete_p6_3c_r3a_decode_resident_matched_ab_evidence"
            if evidence_complete
            else "incomplete_p6_3c_r3a_decode_resident_evidence"
        ),
        "evidence_status": evidence_status,
        "scientific_outcome": outcome["scientific_outcome"],
        "parent_p6_3c_grade_preserved": "blocked_p6_3c_not_strict_single_variable",
        "parent_f4_outcome_preserved": (
            "accepted_chunked_prefill_scheduler_mechanism_observed"
        ),
        "parent_results_overwritten": False,
        "r3_s0_gate_complete": scout["r3_s0_gate_complete"],
        "formal_performance_authorized_by_scout": scout[
            "formal_performance_authorized_by_scout"
        ],
        "mechanism_lifecycles_complete": mechanism_complete,
        "performance_lifecycles_complete": performance_complete,
        "evidence_complete": evidence_complete,
        "single_variable_argv_exact": single_variable_exact,
        "resolved_config_exact": resolved_exact,
        "observer_absent_performance": observer_absent_performance,
        "payload_identity_exact": payload["all_body_files_sha256_exact"],
        "startup_complete": startup_complete,
        "request_count": request_count,
        "successful_request_count": successful_request_count,
        "expected_request_count": EXPECTED_ENGINE_REQUESTS,
        "http_request_count": http_count,
        "expected_http_request_count": EXPECTED_HTTP_REQUESTS,
        "cleanup_complete": cleanup_complete,
        "keep_alive_restore_exact": recovery.get("keep_alive_restored_exact"),
        "adaptive_execution_allowed": True,
        "scientific_contract_changed": False,
        "developer_review_required": True,
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "next_task_authorized": False,
        "universal_benefit_claimed": False,
        "argv_evidence": argv_evidence,
    }
    (artifact_dir / "grading_inputs.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lifecycle_fields = list(lifecycle_rows[0])
    _write_tsv(artifact_dir / "lifecycle_summary.tsv", lifecycle_rows, lifecycle_fields)
    mode_fields = list(mode_cell_rows[0]) if mode_cell_rows else ["mode", "cell_id"]
    pair_fields = list(paired_rows[0]) if paired_rows else ["pair_id", "cell_id"]
    _write_tsv(
        artifact_dir / "performance_mode_cell_summary.tsv",
        mode_cell_rows,
        mode_fields,
    )
    _write_tsv(
        artifact_dir / "performance_paired_effects.tsv", paired_rows, pair_fields
    )
    _write_tsv(
        artifact_dir / "performance_order_balanced_pairs.tsv",
        paired_rows,
        pair_fields,
    )
    startup_fields = list(startup_rows[0]) if startup_rows else ["lifecycle_id"]
    _write_tsv(
        artifact_dir / "startup_resource_summary.tsv", startup_rows, startup_fields
    )
    environment = {
        "task_id": TASK_ID,
        "repo_head": _git_output("rev-parse", "HEAD"),
        "repo_origin_main": _git_output("rev-parse", "origin/main"),
        "workload_path": WORKLOAD_RELATIVE_PATH,
        "workload_sha256": _sha256_path(REPO_ROOT / WORKLOAD_RELATIVE_PATH),
        "runner_sha256": _sha256_path(Path(__file__)),
        "observer_sha256": _sha256_path(
            REPO_ROOT / "tools/inference_contracts/p6_3c_r3_decode_resident_observer.py"
        ),
        "model": "DeepSeek-V4-Flash-w8a8-mtp",
        "vllm": "0.22.1+empty",
        "vllm_ascend": "0.22.1rc1",
        "max_model_len": MAX_MODEL_LEN,
        "max_num_batched_tokens": MAX_NUM_BATCHED_TOKENS,
        "max_num_seqs": MAX_NUM_SEQS,
        "prefix_cache_enabled": False,
        "mtp_num_speculative_tokens": 1,
        "profiler_enabled": False,
        "observer_enabled_tracks": ["mechanism"],
        "generated_text_retained": False,
        "generated_token_ids_retained": False,
    }
    (artifact_dir / "environment_and_hashes.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "mechanism_scheduler_summary.json").write_text(
        json.dumps(scout, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        f"# {TASK_ID} 结果摘要",
        "",
        f"- evidence status: `{evidence_status}`",
        f"- scientific outcome: `{outcome['scientific_outcome']}`",
        (
            "- R3-S0 先确认八个 resident Decode 下的真实调度余量；"
            f"scout gate=`{scout['r3_s0_gate_complete']}`。"
        ),
        (
            f"- 正式请求 `{successful_request_count}/{EXPECTED_ENGINE_REQUESTS}`；"
            f"HTTP 生命周期调用 `{http_count}/{EXPECTED_HTTP_REQUESTS}`；"
            f"keep-alive 精确恢复 `{recovery.get('keep_alive_restored_exact')}`。"
        ),
        "",
        "## 实验结论",
        "",
        (
            "- 主要收益指标是临界长 Prefill 的注入后 TTFT；"
            "主要代价指标是 resident Decode 干扰窗口 P99 TBT 与总输出吞吐。"
        ),
        (
            "- admission-cliff On/Off TTFT 相对变化："
            f"`{outcome['admission_cliff_ttft_relative_change_on_vs_off']}`。"
        ),
        (
            "- resident P99 TBT 相对变化："
            f"`{outcome['resident_p99_tbt_relative_change_on_vs_off']}`；"
            "aggregate output TPS 相对变化："
            f"`{outcome['aggregate_output_tps_relative_change_on_vs_off']}`。"
        ),
        "",
        "## 结论边界",
        "",
        "- 该证据只覆盖受控 resident-decode staged arrival，不外推自然 API 流量。",
        "- F4 机制结论和原 135168/4096/1 blocked 审计均保留，不被本任务覆盖。",
        "- 自动 evidence status 只表示材料完整性；科学 outcome 由结构化效应量决定。",
        "- 未经用户选择 email / upload-api / server-local，不传输候选结果。",
        "",
    ]
    (artifact_dir / "result_summary.md").write_text("\n".join(lines), encoding="utf-8")
    failure_path = artifact_dir / "first_failure_excerpt.txt"
    if evidence_complete:
        failure_path.write_text("none\n", encoding="utf-8")
    elif not failure_path.is_file():
        failure_path.write_text(
            f"evidence_status={evidence_status}\n"
            f"r3_s0_gate_complete={scout['r3_s0_gate_complete']}\n"
            f"successful_request_count={successful_request_count}/"
            f"{EXPECTED_ENGINE_REQUESTS}\n"
            f"keep_alive_restore_exact={recovery.get('keep_alive_restored_exact')}\n",
            encoding="utf-8",
        )
    return grading


def package_results(artifact_dir: Path) -> dict[str, Any]:
    candidates = []
    for name in BOUNDED_CANDIDATES:
        path = artifact_dir / name
        if path.is_file():
            candidates.append(
                {
                    "path": name,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256_path(path),
                    "sensitivity": "internal_project_evidence_no_generated_content",
                }
            )
    total_bytes = sum(item["bytes"] for item in candidates)
    manifest = {
        "task_id": TASK_ID,
        "result_summary_path": str(artifact_dir / "result_summary.md"),
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "automatic_transfer_allowed": False,
        "available_methods": ["email", "upload-api", "server-local"],
        "recommended_method": "upload-api",
        "recommended_reason": "atomic_multi_file_session_with_hash_validation",
        "bounded_transfer_max_bytes": 71680,
        "candidate_file_count": len(candidates),
        "candidate_total_bytes": total_bytes,
        "candidate_total_within_limit": total_bytes <= 71680,
        "candidates": candidates,
        "raw_token_timestamps_and_logs_remain_server_local": True,
        "selection_required_before_any_transfer": True,
    }
    (artifact_dir / "candidate_manifest.server_local.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_tsv(
        artifact_dir / "delivery_candidates.tsv",
        candidates,
        ["path", "bytes", "sha256", "sensitivity"],
    )
    if total_bytes > 71680:
        raise ValueError(f"bounded candidates exceed 70KB: {total_bytes}")
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    run_mode = sub.add_parser("run-mode")
    run_mode.add_argument("--artifact-dir", type=Path, required=True)
    run_mode.add_argument("--lifecycle-dir", type=Path, required=True)
    run_mode.add_argument("--base-url", required=True)
    run_mode.add_argument("--server-pid", type=int, required=True)
    run_mode.add_argument("--track", choices=TRACKS, required=True)
    run_mode.add_argument("--mode", choices=MODES, required=True)
    scout = sub.add_parser("scout-gate")
    scout.add_argument("--artifact-dir", type=Path, required=True)
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    package = sub.add_parser("package")
    package.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "prepare":
        prepare_artifacts(args.source_payload, args.artifact_dir, args.model_name)
        return 0
    if args.command == "run-mode":
        return execute_mode(
            args.artifact_dir,
            args.lifecycle_dir,
            args.base_url,
            args.server_pid,
            args.track,
            args.mode,
        )
    if args.command == "scout-gate":
        summary = write_scout_evidence(args.artifact_dir)
        return 0 if summary["r3_s0_gate_complete"] else 3
    if args.command == "finalize":
        grading = finalize_artifacts(args.artifact_dir)
        return 0 if grading["evidence_complete"] else 2
    if args.command == "package":
        package_results(args.artifact_dir)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
