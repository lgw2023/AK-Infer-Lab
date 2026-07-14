from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTEXTS = (4096, 65536, 131072)
OUTPUT_TOKENS = (64, 256)
CONCURRENCIES = (1, 4, 8)
PILOT_CELLS = (
    (4096, 64, 1),
    (65536, 64, 4),
    (131072, 64, 1),
)
METRIC_NAMES = {
    "vllm:spec_decode_num_drafts_total": "num_drafts",
    "vllm:spec_decode_num_draft_tokens_total": "num_draft_tokens",
    "vllm:spec_decode_num_accepted_tokens_total": "num_accepted_tokens",
    "vllm:num_requests_running": "num_requests_running",
    "vllm:num_requests_waiting": "num_requests_waiting",
}


def build_run_plan() -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []

    def add_batch(
        phase: str,
        context_tokens: int,
        output_tokens: int,
        concurrency: int,
        repeat_index: int,
    ) -> None:
        batch_index = len(plan) + 1
        batch_id = f"{phase}_b{batch_index:02d}_ctx{context_tokens}_out{output_tokens}_c{concurrency}_r{repeat_index}"
        plan.append(
            {
                "batch_id": batch_id,
                "phase": phase,
                "context_tokens": context_tokens,
                "output_tokens": output_tokens,
                "concurrency": concurrency,
                "repeat_index": repeat_index,
                "requests": [
                    {
                        "request_id": f"{batch_id}_q{request_index:02d}",
                        "request_index": request_index,
                    }
                    for request_index in range(1, concurrency + 1)
                ],
            }
        )

    add_batch("warmup", 4096, 64, 1, 1)
    for context, output, concurrency in PILOT_CELLS:
        for repeat_index in range(1, 4):
            add_batch("pilot", context, output, concurrency, repeat_index)
    for context in CONTEXTS:
        for output in OUTPUT_TOKENS:
            for concurrency in CONCURRENCIES:
                if (context, output, concurrency) in PILOT_CELLS:
                    continue
                add_batch("matrix", context, output, concurrency, 1)
    return plan


def _common_prefix_length(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    for index, (left_token, right_token) in enumerate(zip(left, right, strict=True)):
        if left_token != right_token:
            return index
    return len(left)


def _select_offsets(source_tokens: list[int], count: int) -> list[tuple[int, int]]:
    prefixes: list[tuple[int, ...]] = []
    selected: list[tuple[int, int]] = []
    for offset in range(len(source_tokens)):
        prefix = tuple(
            source_tokens[(offset + index) % len(source_tokens)] for index in range(128)
        )
        if prefix in prefixes:
            continue
        max_common = max(
            (_common_prefix_length(prefix, prior) for prior in prefixes),
            default=0,
        )
        if max_common >= 128:
            continue
        prefixes.append(prefix)
        selected.append((offset, max_common))
        if len(selected) == count:
            return selected
    raise ValueError(f"source payload provides only {len(selected)} distinct prefix rotations")


def _repeat_and_truncate(tokens: list[int], size: int, offset: int) -> list[int]:
    rotated = tokens[offset:] + tokens[:offset]
    repeats = math.ceil(size / len(rotated))
    return (rotated * repeats)[:size]


def prepare_artifacts(
    source_payload: Path,
    artifact_dir: Path,
    model_name: str,
) -> dict[str, Any]:
    source = json.loads(source_payload.read_text(encoding="utf-8"))
    source_tokens = source.get("prompt")
    if not isinstance(source_tokens, list) or len(source_tokens) != 4096:
        raise ValueError("source payload must contain exactly 4096 prompt token IDs")
    if not all(isinstance(token, int) and not isinstance(token, bool) for token in source_tokens):
        raise ValueError("source prompt must contain integer token IDs")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    body_dir = artifact_dir / "bodies"
    body_dir.mkdir(parents=True, exist_ok=True)
    plan = build_run_plan()
    request_count = sum(len(batch["requests"]) for batch in plan)
    offsets = iter(_select_offsets(source_tokens, request_count))
    records: list[dict[str, Any]] = []

    for batch in plan:
        for request_item in batch["requests"]:
            offset, max_common = next(offsets)
            prompt = _repeat_and_truncate(
                source_tokens,
                int(batch["context_tokens"]),
                offset,
            )
            body = {
                "ignore_eos": True,
                "max_tokens": int(batch["output_tokens"]),
                "min_tokens": int(batch["output_tokens"]),
                "model": model_name,
                "prompt": prompt,
                "return_token_ids": True,
                "stream": True,
                "stream_options": {"include_usage": True},
                "temperature": 0.0,
            }
            raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            relative_path = Path("bodies") / f"{request_item['request_id']}.json"
            path = artifact_dir / relative_path
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            request_item.update(
                {
                    "body_relative_path": str(relative_path),
                    "request_body_sha256": digest,
                    "cyclic_offset": offset,
                }
            )
            records.append(
                {
                    "request_id": request_item["request_id"],
                    "batch_id": batch["batch_id"],
                    "context_tokens": batch["context_tokens"],
                    "output_tokens": batch["output_tokens"],
                    "concurrency": batch["concurrency"],
                    "repeat_index": batch["repeat_index"],
                    "body_bytes": len(raw),
                    "request_body_sha256": digest,
                    "common_prefix_upper_bound_tokens": max_common,
                }
            )

    manifest = {
        "source_prompt_tokens": len(source_tokens),
        "request_count": len(records),
        "pairwise_common_prefix_tokens_less_than": 128,
        "all_request_body_sha256_unique": len({item["request_body_sha256"] for item in records})
        == len(records),
        "generated_text_retained": False,
        "token_ids_retained": False,
        "records": records,
    }
    if not manifest["all_request_body_sha256_unique"]:
        raise ValueError("request body hashes are not unique")
    (artifact_dir / "run_plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "request_body_manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = fraction * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def calculate_request_metrics(
    *,
    request_start_ns: int,
    token_arrival_ns: list[int],
    request_end_ns: int,
) -> dict[str, int | float]:
    token_count = len(token_arrival_ns)
    ttft_ns = token_arrival_ns[0] - request_start_ns if token_arrival_ns else 0
    tpot_ns = (
        (token_arrival_ns[-1] - token_arrival_ns[0]) / (token_count - 1)
        if token_count > 1
        else 0.0
    )
    e2el_ns = request_end_ns - request_start_ns
    itl_ms = [
        (right - left) / 1_000_000
        for left, right in zip(token_arrival_ns, token_arrival_ns[1:])
    ]
    return {
        "ttft_ms": round(ttft_ns / 1_000_000, 6),
        "tpot_ms": round(tpot_ns / 1_000_000, 6),
        "e2el_ms": round(e2el_ns / 1_000_000, 6),
        "output_tokens_per_second": round(
            token_count / (e2el_ns / 1_000_000_000), 6
        )
        if e2el_ns > 0
        else 0.0,
        "itl_count": len(itl_ms),
        "itl_p50_ms": round(percentile(itl_ms, 0.50), 6),
        "itl_p95_ms": round(percentile(itl_ms, 0.95), 6),
        "itl_p99_ms": round(percentile(itl_ms, 0.99), 6),
    }


def grade_evidence(
    request_rows: list[dict[str, Any]],
    batch_rows: list[dict[str, Any]],
    *,
    cleanup_status: str,
) -> dict[str, Any]:
    warmup_requests = [row for row in request_rows if row.get("phase") == "warmup"]
    measured_requests = [row for row in request_rows if row.get("phase") != "warmup"]
    pilot_requests = [row for row in request_rows if row.get("phase") == "pilot"]
    measured_batches = [row for row in batch_rows if row.get("phase") != "warmup"]
    pilot_batches = [row for row in batch_rows if row.get("phase") == "pilot"]
    successful_measured = [row for row in measured_requests if row.get("status") == "success"]
    successful_pilot = [row for row in pilot_requests if row.get("status") == "success"]
    represented_cells = {
        (
            int(row["context_tokens"]),
            int(row["output_tokens"]),
            int(row["concurrency"]),
        )
        for row in successful_measured
    }
    expected_cells = {
        (context, output, concurrency)
        for context in CONTEXTS
        for output in OUTPUT_TOKENS
        for concurrency in CONCURRENCIES
    }
    counter_evidence_ok = bool(measured_batches) and all(
        row.get("counter_evidence_ok") is True for row in measured_batches
    )
    counter_continuity_ok = bool(measured_batches) and all(
        row.get("counter_continuity_ok") is True for row in measured_batches
    )
    accepted_delta_total = sum(
        float(row.get("accepted_token_delta") or 0.0) for row in measured_batches
    )
    warmup_ok = len(warmup_requests) == 1 and warmup_requests[0].get("status") == "success"
    pilot_complete = (
        len(pilot_requests) == 18
        and len(successful_pilot) == 18
        and len(pilot_batches) == 9
        and all(row.get("status") == "success" for row in pilot_batches)
    )
    all_measured_complete = (
        len(measured_requests) == 90
        and len(successful_measured) == 90
        and len(measured_batches) == 24
        and all(row.get("status") == "success" for row in measured_batches)
    )
    all_cells = represented_cells == expected_cells

    if cleanup_status != "clean":
        grade = "red_cleanup_incomplete"
    elif not warmup_ok or not successful_pilot:
        grade = "red_mtp_unprofiled_pilot_no_success"
    elif not pilot_complete:
        grade = "yellow_mtp_unprofiled_pilot_partial"
    elif not counter_evidence_ok or not counter_continuity_ok or accepted_delta_total <= 0:
        grade = "red_mtp_unprofiled_evidence_incomplete"
    elif all_measured_complete and all_cells:
        grade = "candidate_green_mtp_unprofiled_baseline"
    else:
        grade = "yellow_mtp_unprofiled_matrix_partial"

    return {
        "server_grade": grade,
        "warmup_ok": warmup_ok,
        "pilot_complete": pilot_complete,
        "measured_request_count": len(measured_requests),
        "successful_measured_request_count": len(successful_measured),
        "measured_batch_count": len(measured_batches),
        "all_18_cells_represented": all_cells,
        "represented_cells": [list(cell) for cell in sorted(represented_cells)],
        "counter_evidence_ok": counter_evidence_ok,
        "counter_continuity_ok": counter_continuity_ok,
        "accepted_token_delta_total": accepted_delta_total,
        "cleanup_status": cleanup_status,
        "performance_reference_baseline": False,
        "developer_review_required": True,
        "official_functional_reference_baseline_remains_true": True,
        "claim_boundary": "mtp_unprofiled_streaming_performance_baseline_only",
    }


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _get(base_url: str, path: str, timeout: float = 10.0) -> tuple[int | None, bytes]:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=timeout) as response:
            return int(response.status), response.read()
    except Exception:
        return None, b""


def _parse_metrics(raw: bytes) -> dict[str, Any]:
    values = {alias: 0.0 for alias in METRIC_NAMES.values()}
    found = {alias: False for alias in METRIC_NAMES.values()}
    for raw_line in raw.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        metric_name = parts[0].split("{", 1)[0]
        alias = METRIC_NAMES.get(metric_name)
        if alias is None:
            continue
        try:
            values[alias] += float(parts[1])
            found[alias] = True
        except ValueError:
            continue
    values["all_required_metrics_present"] = all(found.values())
    return values


def _metrics_snapshot(
    base_url: str,
    raw_path: Path,
) -> tuple[int | None, dict[str, Any]]:
    status, raw = _get(base_url, "/metrics")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)
    parsed = _parse_metrics(raw) if status == 200 else {
        **{alias: 0.0 for alias in METRIC_NAMES.values()},
        "all_required_metrics_present": False,
    }
    parsed["http_status"] = status
    parsed["raw_server_path"] = str(raw_path)
    return status, parsed


def _wait_for_idle(
    base_url: str,
    raw_path: Path,
    timeout_seconds: float = 60.0,
) -> tuple[bool, dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    status: int | None = None
    while time.monotonic() < deadline:
        status, last = _metrics_snapshot(base_url, raw_path)
        if (
            status == 200
            and last.get("all_required_metrics_present")
            and last.get("num_requests_running") == 0
            and last.get("num_requests_waiting") == 0
        ):
            return True, last
        time.sleep(0.5)
    return False, last


def _stream_request(
    *,
    artifact_dir: Path,
    base_url: str,
    server_pid: int,
    batch: dict[str, Any],
    request_item: dict[str, Any],
    start_barrier: threading.Barrier,
) -> dict[str, Any]:
    body_path = artifact_dir / request_item["body_relative_path"]
    body = body_path.read_bytes()
    body_sha256 = hashlib.sha256(body).hexdigest()
    expected_hash = request_item["request_body_sha256"]
    payload = json.loads(body)
    expected_prompt = int(batch["context_tokens"])
    expected_output = int(batch["output_tokens"])
    if body_sha256 != expected_hash:
        raise ValueError(f"body hash drift for {request_item['request_id']}")
    if len(payload["prompt"]) != expected_prompt:
        raise ValueError(f"prompt length drift for {request_item['request_id']}")

    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/completions",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    token_arrival_ns: list[int] = []
    usage: dict[str, Any] = {}
    finish_reason: str | None = None
    saw_done = False
    http_status: int | None = None
    max_token_chunk_width = 0
    bounded_error_path: Path | None = None
    start_barrier.wait()
    request_start_ns = time.monotonic_ns()
    try:
        with urllib.request.urlopen(request, timeout=7200) as response:
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
                    token_ids = choice.get("token_ids") or []
                    max_token_chunk_width = max(max_token_chunk_width, len(token_ids))
                    token_arrival_ns.extend([now_ns] * len(token_ids))
                    if choice.get("finish_reason") is not None:
                        finish_reason = str(choice["finish_reason"])
    except urllib.error.HTTPError as error:
        http_status = int(error.code)
        bounded_error_path = artifact_dir / "request_errors" / f"{request_item['request_id']}.body"
        bounded_error_path.parent.mkdir(parents=True, exist_ok=True)
        bounded_error_path.write_bytes(error.read(8192))
    except Exception as error:
        bounded_error_path = artifact_dir / "request_errors" / f"{request_item['request_id']}.txt"
        bounded_error_path.parent.mkdir(parents=True, exist_ok=True)
        bounded_error_path.write_text(
            f"{type(error).__name__}: {str(error)[:2048]}\n",
            encoding="utf-8",
        )
    request_end_ns = time.monotonic_ns()
    prompt_tokens = usage.get("prompt_tokens")
    generated_tokens = usage.get("completion_tokens")
    timing = calculate_request_metrics(
        request_start_ns=request_start_ns,
        token_arrival_ns=token_arrival_ns,
        request_end_ns=request_end_ns,
    )
    checks = {
        "server_alive": _process_alive(server_pid),
        "http_200": http_status == 200,
        "prompt_tokens_exact": prompt_tokens == expected_prompt,
        "generated_tokens_exact": generated_tokens == expected_output,
        "streamed_tokens_exact": len(token_arrival_ns) == expected_output,
        "finish_reason_length": finish_reason == "length",
        "saw_done": saw_done,
        "exact_token_arrival_count": len(token_arrival_ns) == expected_output,
        "token_chunk_width_within_mtp_bound": max_token_chunk_width <= 2,
    }
    return {
        "request_id": request_item["request_id"],
        "batch_id": batch["batch_id"],
        "phase": batch["phase"],
        "context_tokens": expected_prompt,
        "output_tokens": expected_output,
        "concurrency": int(batch["concurrency"]),
        "repeat_index": int(batch["repeat_index"]),
        "request_index": int(request_item["request_index"]),
        "request_body_sha256": body_sha256,
        "status": "success" if all(checks.values()) else "failed",
        "http_status": http_status,
        "prompt_tokens": prompt_tokens,
        "generated_token_count": generated_tokens,
        "streamed_token_count": len(token_arrival_ns),
        "finish_reason": finish_reason,
        "saw_done": saw_done,
        "max_token_chunk_width": max_token_chunk_width,
        "request_start_ns": request_start_ns,
        "token_arrival_ns": token_arrival_ns,
        "request_end_ns": request_end_ns,
        **timing,
        "bounded_error_server_path": str(bounded_error_path) if bounded_error_path else None,
        "checks": checks,
        "generated_text_retained": False,
        "token_ids_retained": False,
    }


def _failed_pre_batch_rows(
    batch: dict[str, Any],
    reason: str,
) -> list[dict[str, Any]]:
    return [
        {
            "request_id": request_item["request_id"],
            "batch_id": batch["batch_id"],
            "phase": batch["phase"],
            "context_tokens": batch["context_tokens"],
            "output_tokens": batch["output_tokens"],
            "concurrency": batch["concurrency"],
            "repeat_index": batch["repeat_index"],
            "request_index": request_item["request_index"],
            "request_body_sha256": request_item["request_body_sha256"],
            "status": "failed_pre_batch_gate",
            "failure_reason": reason,
            "generated_text_retained": False,
            "token_ids_retained": False,
        }
        for request_item in batch["requests"]
    ]


def _run_batch(
    *,
    artifact_dir: Path,
    base_url: str,
    server_pid: int,
    batch: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    batch_id = batch["batch_id"]
    raw_metrics_dir = artifact_dir / "raw_metrics"
    health_before, _ = _get(base_url, "/health", timeout=5)
    idle_before, metrics_before = _wait_for_idle(
        base_url,
        raw_metrics_dir / f"{batch_id}_before.prom",
    )
    pre_checks = {
        "server_alive": _process_alive(server_pid),
        "health_before_200": health_before == 200,
        "metrics_before_complete": metrics_before.get("all_required_metrics_present") is True,
        "queue_idle_before": idle_before,
    }
    if not all(pre_checks.values()):
        rows = _failed_pre_batch_rows(batch, "pre_batch_health_metrics_or_queue_gate")
        return rows, {
            "batch_id": batch_id,
            "phase": batch["phase"],
            "context_tokens": batch["context_tokens"],
            "output_tokens": batch["output_tokens"],
            "concurrency": batch["concurrency"],
            "repeat_index": batch["repeat_index"],
            "status": "failed_pre_batch_gate",
            "counter_evidence_ok": False,
            "accepted_token_delta": 0.0,
            "server_healthy_and_idle_after": False,
            "checks": pre_checks,
        }

    barrier = threading.Barrier(len(batch["requests"]) + 1)
    rows: list[dict[str, Any] | None] = [None] * len(batch["requests"])

    def worker(index: int, request_item: dict[str, Any]) -> None:
        try:
            rows[index] = _stream_request(
                artifact_dir=artifact_dir,
                base_url=base_url,
                server_pid=server_pid,
                batch=batch,
                request_item=request_item,
                start_barrier=barrier,
            )
        except Exception as error:
            try:
                barrier.abort()
            except threading.BrokenBarrierError:
                pass
            failed = _failed_pre_batch_rows(batch, f"runner_exception:{type(error).__name__}")[index]
            failed["failure_detail"] = str(error)[:2048]
            rows[index] = failed

    threads = [
        threading.Thread(target=worker, args=(index, request_item), daemon=True)
        for index, request_item in enumerate(batch["requests"])
    ]
    for thread in threads:
        thread.start()
    batch_start_ns = time.monotonic_ns()
    try:
        barrier.wait(timeout=10)
    except threading.BrokenBarrierError:
        pass
    deadline = time.monotonic() + 7260
    for thread in threads:
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
    batch_end_ns = time.monotonic_ns()
    completed_rows = [
        row
        if row is not None
        else _failed_pre_batch_rows(batch, "request_thread_timeout")[index]
        for index, row in enumerate(rows)
    ]

    health_after, _ = _get(base_url, "/health", timeout=5)
    idle_after, metrics_after = _wait_for_idle(
        base_url,
        raw_metrics_dir / f"{batch_id}_after.prom",
    )
    delta = {
        name: float(metrics_after.get(name) or 0.0) - float(metrics_before.get(name) or 0.0)
        for name in ("num_drafts", "num_draft_tokens", "num_accepted_tokens")
    }
    counter_evidence_ok = (
        metrics_before.get("all_required_metrics_present") is True
        and metrics_after.get("all_required_metrics_present") is True
        and delta["num_drafts"] > 0
        and delta["num_draft_tokens"] > 0
        and all(value >= 0 for value in delta.values())
    )
    batch_duration_seconds = (batch_end_ns - batch_start_ns) / 1_000_000_000
    generated_total = sum(int(row.get("generated_token_count") or 0) for row in completed_rows)
    checks = {
        **pre_checks,
        "health_after_200": health_after == 200,
        "metrics_after_complete": metrics_after.get("all_required_metrics_present") is True,
        "queue_idle_after": idle_after,
        "all_requests_success": all(row.get("status") == "success" for row in completed_rows),
        "counter_evidence_ok": counter_evidence_ok,
    }
    batch_row = {
        "batch_id": batch_id,
        "phase": batch["phase"],
        "context_tokens": batch["context_tokens"],
        "output_tokens": batch["output_tokens"],
        "concurrency": batch["concurrency"],
        "repeat_index": batch["repeat_index"],
        "status": "success" if all(checks.values()) else "failed",
        "request_count": len(completed_rows),
        "successful_request_count": sum(row.get("status") == "success" for row in completed_rows),
        "batch_start_ns": batch_start_ns,
        "batch_end_ns": batch_end_ns,
        "batch_output_tokens_per_second": round(generated_total / batch_duration_seconds, 6)
        if batch_duration_seconds > 0
        else 0.0,
        "batch_requests_per_second": round(len(completed_rows) / batch_duration_seconds, 6)
        if batch_duration_seconds > 0
        else 0.0,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "counter_delta": delta,
        "counter_evidence_ok": counter_evidence_ok,
        "accepted_token_delta": delta["num_accepted_tokens"],
        "server_healthy_and_idle_after": (
            _process_alive(server_pid) and health_after == 200 and idle_after
        ),
        "checks": checks,
    }
    return completed_rows, batch_row


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def execute_artifacts(artifact_dir: Path, base_url: str, server_pid: int) -> int:
    plan = json.loads((artifact_dir / "run_plan.json").read_text(encoding="utf-8"))
    request_rows: list[dict[str, Any]] = []
    batch_rows: list[dict[str, Any]] = []
    pilot_green = True

    for batch in plan:
        if batch["phase"] == "matrix" and not pilot_green:
            break
        rows, batch_row = _run_batch(
            artifact_dir=artifact_dir,
            base_url=base_url,
            server_pid=server_pid,
            batch=batch,
        )
        if not batch_rows:
            continuity_ok = True
        else:
            previous_after = batch_rows[-1].get("metrics_after") or {}
            current_before = batch_row.get("metrics_before") or {}
            continuity_ok = all(
                float(current_before.get(name) or 0.0)
                >= float(previous_after.get(name) or 0.0)
                for name in ("num_drafts", "num_draft_tokens", "num_accepted_tokens")
            ) and bool(previous_after) and bool(current_before)
        batch_row["counter_continuity_ok"] = continuity_ok
        batch_row.setdefault("checks", {})["counter_continuity_ok"] = continuity_ok
        if not continuity_ok:
            batch_row["counter_evidence_ok"] = False
            batch_row["status"] = "failed"
        request_rows.extend(rows)
        batch_rows.append(batch_row)
        _write_jsonl(artifact_dir / "raw_request_results.jsonl", request_rows)
        _write_jsonl(artifact_dir / "raw_batch_results.jsonl", batch_rows)
        if batch["phase"] == "warmup" and batch_row["status"] != "success":
            break
        if batch["phase"] == "pilot" and batch_row["status"] != "success":
            pilot_green = False
        if not batch_row.get("server_healthy_and_idle_after"):
            break

    _write_result_tables(artifact_dir, request_rows, batch_rows)
    measured_requests = [row for row in request_rows if row.get("phase") != "warmup"]
    measured_batches = [row for row in batch_rows if row.get("phase") != "warmup"]
    all_request_evidence = len(measured_requests) == 90 and all(
        row.get("status") == "success" for row in measured_requests
    )
    all_batch_evidence = len(measured_batches) == 24 and all(
        row.get("status") == "success" for row in measured_batches
    )
    return 0 if all_request_evidence and all_batch_evidence else 2


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    mean = statistics.fmean(values)
    return {
        "n": len(values),
        "min": round(min(values), 6),
        "median": round(statistics.median(values), 6),
        "max": round(max(values), 6),
        "mean": round(mean, 6),
        "cv": round(statistics.pstdev(values) / mean, 6) if len(values) > 1 and mean else 0.0,
    }


def _write_result_tables(
    artifact_dir: Path,
    request_rows: list[dict[str, Any]],
    batch_rows: list[dict[str, Any]],
) -> None:
    compact_fields = [
        "request_id", "batch_id", "phase", "context_tokens", "output_tokens",
        "concurrency", "repeat_index", "request_body_sha256", "status", "http_status",
        "prompt_tokens", "generated_token_count", "streamed_token_count", "finish_reason",
        "saw_done", "ttft_ms", "tpot_ms", "e2el_ms", "output_tokens_per_second",
        "itl_count", "itl_p50_ms", "itl_p95_ms", "itl_p99_ms",
    ]
    with (artifact_dir / "request_results_compact.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=compact_fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in request_rows:
            writer.writerow({field: row.get(field, "") for field in compact_fields})

    measured = [row for row in request_rows if row.get("phase") != "warmup"]
    cell_rows: list[dict[str, Any]] = []
    for context in CONTEXTS:
        for output in OUTPUT_TOKENS:
            for concurrency in CONCURRENCIES:
                group = [
                    row for row in measured
                    if (
                        row.get("context_tokens"), row.get("output_tokens"), row.get("concurrency")
                    ) == (context, output, concurrency)
                ]
                group_batches = [
                    row for row in batch_rows
                    if row.get("phase") != "warmup" and (
                        row.get("context_tokens"), row.get("output_tokens"), row.get("concurrency")
                    ) == (context, output, concurrency)
                ]
                itl_values: list[float] = []
                for row in group:
                    arrivals = row.get("token_arrival_ns") or []
                    itl_values.extend(
                        (right - left) / 1_000_000
                        for left, right in zip(arrivals, arrivals[1:])
                    )
                cell_rows.append(
                    {
                        "context_tokens": context,
                        "output_tokens": output,
                        "concurrency": concurrency,
                        "request_n": len(group),
                        "request_success_n": sum(row.get("status") == "success" for row in group),
                        "batch_n": len(group_batches),
                        "batch_success_n": sum(row.get("status") == "success" for row in group_batches),
                        "ttft_ms": json.dumps(_summary([float(row.get("ttft_ms") or 0) for row in group]), separators=(",", ":")),
                        "tpot_ms": json.dumps(_summary([float(row.get("tpot_ms") or 0) for row in group]), separators=(",", ":")),
                        "e2el_ms": json.dumps(_summary([float(row.get("e2el_ms") or 0) for row in group]), separators=(",", ":")),
                        "output_tokens_per_second": json.dumps(_summary([float(row.get("output_tokens_per_second") or 0) for row in group]), separators=(",", ":")),
                        "batch_output_tokens_per_second": json.dumps(_summary([float(row.get("batch_output_tokens_per_second") or 0) for row in group_batches]), separators=(",", ":")),
                        "itl_n": len(itl_values),
                        "itl_p50_ms": round(percentile(itl_values, 0.50), 6),
                        "itl_p95_ms": round(percentile(itl_values, 0.95), 6),
                        "itl_p99_ms": round(percentile(itl_values, 0.99), 6),
                    }
                )
    with (artifact_dir / "matrix_cell_summary.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cell_rows[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(cell_rows)

    pilot_requests = [row for row in request_rows if row.get("phase") == "pilot"]
    pilot_batches = [row for row in batch_rows if row.get("phase") == "pilot"]
    pilot = {
        "request_count": len(pilot_requests),
        "successful_request_count": sum(row.get("status") == "success" for row in pilot_requests),
        "batch_count": len(pilot_batches),
        "successful_batch_count": sum(row.get("status") == "success" for row in pilot_batches),
        "auto_expand_gate_pass": (
            len(pilot_requests) == 18
            and all(row.get("status") == "success" for row in pilot_requests)
            and len(pilot_batches) == 9
            and all(row.get("status") == "success" for row in pilot_batches)
        ),
        "variability_is_diagnostic": True,
    }
    (artifact_dir / "pilot_summary.json").write_text(
        json.dumps(pilot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(REPO_ROOT), *args], text=True).strip()
    except Exception:
        return ""


def finalize_artifacts(
    artifact_dir: Path,
    cleanup_status: str,
    run_exit: int,
) -> dict[str, Any]:
    request_rows = _read_jsonl(artifact_dir / "raw_request_results.jsonl")
    batch_rows = _read_jsonl(artifact_dir / "raw_batch_results.jsonl")
    grading = grade_evidence(request_rows, batch_rows, cleanup_status=cleanup_status)
    prior_grade_path = artifact_dir / "server_grade.txt"
    if not request_rows and prior_grade_path.exists():
        prior_grade = prior_grade_path.read_text(encoding="utf-8").strip()
        if prior_grade in {
            "blocked_protocol_or_resource_gate",
            "red_mtp_unprofiled_server_not_ready",
        }:
            grading["server_grade"] = prior_grade
    grading["run_exit"] = run_exit
    prior_grade_path.write_text(grading["server_grade"] + "\n", encoding="utf-8")
    (artifact_dir / "grading_inputs.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    environment = {
        "git_head": _git_value("rev-parse", "HEAD"),
        "origin_main": _git_value("rev-parse", "origin/main"),
        "tracked_status": _git_value("status", "--porcelain", "--untracked-files=no"),
        "source_payload_sha256": (artifact_dir / "source_payload_sha256.txt").read_text(encoding="utf-8").split()[0]
        if (artifact_dir / "source_payload_sha256.txt").exists()
        else None,
        "server_command_sha256": (artifact_dir / "server_command_sha256.txt").read_text(encoding="utf-8").split()[0]
        if (artifact_dir / "server_command_sha256.txt").exists()
        else None,
        "server_lifecycle_count": int((artifact_dir / "server_lifecycle_count.txt").read_text().strip())
        if (artifact_dir / "server_lifecycle_count.txt").exists()
        else None,
        "profiler_run": False,
        "hbm_sampler_run": False,
    }
    (artifact_dir / "environment_and_hashes.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# P6.1 MTP unprofiled baseline server result",
        "",
        f"- task_id: p6_1_deepseek_v4_flash_w8a8_mtp_unprofiled_baseline_2026_0714",
        f"- server_grade: {grading['server_grade']}",
        f"- measured_requests: {grading['successful_measured_request_count']}/{grading['measured_request_count']} successful",
        f"- measured_batches: {grading['measured_batch_count']}",
        f"- all_18_cells_represented: {str(grading['all_18_cells_represented']).lower()}",
        f"- accepted_token_delta_total: {grading['accepted_token_delta_total']}",
        f"- cleanup: {cleanup_status}",
        "- performance_reference_baseline: false (developer review required)",
        "- claim_boundary: mtp_unprofiled_streaming_performance_baseline_only",
        f"- raw_result_root_server_local: {artifact_dir}",
        "- generated_text_retained: false",
        "- token_ids_retained: false",
    ]
    (artifact_dir / "result_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if grading["server_grade"] != "candidate_green_mtp_unprofiled_baseline":
        first_failed = next((row for row in request_rows if row.get("status") != "success"), None)
        if first_failed is not None:
            bounded = {key: value for key, value in first_failed.items() if key not in {"token_arrival_ns"}}
            (artifact_dir / "first_failure_excerpt.txt").write_text(
                json.dumps(bounded, indent=2, sort_keys=True)[:8192] + "\n",
                encoding="utf-8",
            )

    candidate_names = [
        "result_summary.md",
        "environment_and_hashes.json",
        "request_body_manifest.json",
        "pilot_summary.json",
        "matrix_cell_summary.tsv",
        "request_results_compact.tsv",
        "grading_inputs.json",
        "cleanup_status.txt",
        "first_failure_excerpt.txt",
    ]
    candidate_rows = []
    total = 0
    for name in candidate_names:
        path = artifact_dir / name
        if not path.exists():
            continue
        size = path.stat().st_size
        total += size
        sensitivity = "bounded_structured_performance_evidence_no_generated_content_or_token_ids"
        candidate_rows.append((str(path), size, hashlib.sha256(path.read_bytes()).hexdigest(), sensitivity))
    with (artifact_dir / "delivery_candidates.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["path", "bytes", "sha256", "sensitivity"])
        writer.writerows(candidate_rows)
    (artifact_dir / "delivery_candidates_total_bytes.txt").write_text(f"{total}\n", encoding="utf-8")
    if total > 71680:
        grading["candidate_size_gate_pass"] = False
        grading["candidate_total_bytes"] = total
        (artifact_dir / "grading_inputs.json").write_text(
            json.dumps(grading, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return grading


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the DeepSeek P6.1 MTP unprofiled baseline client.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--artifact-dir", type=Path, required=True)
    run.add_argument("--base-url", required=True)
    run.add_argument("--server-pid", type=int, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    finalize.add_argument("--cleanup-status", required=True)
    finalize.add_argument("--run-exit", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        prepare_artifacts(args.source_payload, args.artifact_dir, args.model_name)
        return 0
    if args.command == "run":
        return execute_artifacts(args.artifact_dir, args.base_url, args.server_pid)
    if args.command == "finalize":
        finalize_artifacts(args.artifact_dir, args.cleanup_status, args.run_exit)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
