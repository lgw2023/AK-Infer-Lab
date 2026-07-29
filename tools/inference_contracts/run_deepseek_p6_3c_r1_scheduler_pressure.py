from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Iterable
import urllib.error
import urllib.request

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.p6_3c_r1_scheduler_observer import (
    summarize_scheduler_rows,
)


TASK_ID = "p6_3c_r1_chunked_prefill_scheduler_pressure_2026_0728_run01"
MODES = ("chunked_prefill_off", "chunked_prefill_on")
TRACKS = ("mechanism", "performance")
CELLS = (
    {
        "cell_id": "no_pressure_32k_32k",
        "prompt_tokens": (32768, 32768),
        "request_roles": ("peer_a", "peer_b"),
        "total_prefill_tokens": 65536,
        "pressure": False,
    },
    {
        "cell_id": "asymmetric_pressure_64k_32k",
        "prompt_tokens": (65536, 32768),
        "request_roles": ("long", "short"),
        "total_prefill_tokens": 98304,
        "pressure": True,
    },
    {
        "cell_id": "symmetric_pressure_48k_48k",
        "prompt_tokens": (49152, 49152),
        "request_roles": ("peer_a", "peer_b"),
        "total_prefill_tokens": 98304,
        "pressure": True,
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
METRIC_NAMES = {
    "vllm:spec_decode_num_drafts_total": "num_drafts",
    "vllm:spec_decode_num_draft_tokens_total": "num_draft_tokens",
    "vllm:spec_decode_num_accepted_tokens_total": "num_accepted_tokens",
    "vllm:num_requests_running": "num_requests_running",
    "vllm:num_requests_waiting": "num_requests_waiting",
}
BOUNDED_CANDIDATES = (
    "result_summary.md",
    "environment_and_hashes.json",
    "request_body_manifest.json",
    "lifecycle_summary.tsv",
    "mechanism_scheduler_summary.json",
    "mechanism_request_chunk_summary.tsv",
    "performance_mode_cell_summary.tsv",
    "performance_order_balanced_pairs.tsv",
    "grading_inputs.json",
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
    repeats = math.ceil(length / len(rotated))
    return (rotated * repeats)[:length]


def build_run_plan() -> dict[str, list[dict[str, Any]]]:
    plan: dict[str, list[dict[str, Any]]] = {}
    for track in TRACKS:
        repeats = 1 if track == "mechanism" else 3
        warmup_id = f"p6_3c_r1_{track}_warmup"
        batches: list[dict[str, Any]] = [
            {
                "track": track,
                "phase": "warmup",
                "batch_id": warmup_id,
                "request_id": warmup_id,
                "cell_id": "warmup_4k",
                "repeat_index": 1,
                "prompt_tokens": [4096],
                "request_roles": ["warmup"],
                "total_prefill_tokens": 4096,
                "pressure": False,
                "output_tokens": 64,
            }
        ]
        for cell in CELLS:
            for repeat_index in range(1, repeats + 1):
                batch_id = (
                    f"p6_3c_r1_{track}_{cell['cell_id']}_r{repeat_index:02d}"
                )
                batches.append(
                    {
                        "track": track,
                        "phase": "measured",
                        "batch_id": batch_id,
                        "request_id": batch_id,
                        "cell_id": cell["cell_id"],
                        "repeat_index": repeat_index,
                        "prompt_tokens": list(cell["prompt_tokens"]),
                        "request_roles": list(cell["request_roles"]),
                        "total_prefill_tokens": cell["total_prefill_tokens"],
                        "pressure": cell["pressure"],
                        "output_tokens": 64,
                    }
                )
        plan[track] = batches
    return plan


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
            isinstance(token, int) and not isinstance(token, bool)
            for token in source_tokens
        )
    ):
        raise ValueError("source payload must contain exactly 4096 integer token IDs")

    artifact_dir.mkdir(parents=True, exist_ok=False)
    body_dir = artifact_dir / "bodies"
    body_dir.mkdir()
    plan = build_run_plan()
    records: list[dict[str, Any]] = []
    body_index = 0
    for track_batches in plan.values():
        for batch in track_batches:
            prompts = []
            choices = []
            for choice_index, (prompt_tokens, role) in enumerate(
                zip(batch["prompt_tokens"], batch["request_roles"], strict=True)
            ):
                offset = (body_index * 521 + choice_index * 977) % len(source_tokens)
                prompt = _repeat_and_truncate(source_tokens, int(prompt_tokens), offset)
                prompts.append(prompt)
                choices.append(
                    {
                        "choice_index": choice_index,
                        "request_role": role,
                        "prompt_tokens": prompt_tokens,
                        "cyclic_offset": offset,
                    }
                )
            body_index += 1
            prompt_field: list[int] | list[list[int]]
            prompt_field = prompts[0] if len(prompts) == 1 else prompts
            body = {
                "ignore_eos": True,
                "max_tokens": int(batch["output_tokens"]),
                "min_tokens": int(batch["output_tokens"]),
                "model": model_name,
                "prompt": prompt_field,
                "request_id": batch["request_id"],
                "return_token_ids": True,
                "stream": True,
                "stream_options": {"include_usage": True},
                "temperature": 0.0,
            }
            encoded = json.dumps(
                body, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            relative = Path("bodies") / f"{batch['batch_id']}.json"
            (artifact_dir / relative).write_bytes(encoded)
            digest = _sha256_bytes(encoded)
            batch["body_relative_path"] = str(relative)
            batch["request_body_sha256"] = digest
            batch["choices"] = choices
            records.append(
                {
                    "track": batch["track"],
                    "phase": batch["phase"],
                    "batch_id": batch["batch_id"],
                    "cell_id": batch["cell_id"],
                    "repeat_index": batch["repeat_index"],
                    "prompt_tokens": batch["prompt_tokens"],
                    "request_roles": batch["request_roles"],
                    "output_tokens": batch["output_tokens"],
                    "choice_count": len(choices),
                    "body_relative_path": str(relative),
                    "body_bytes": len(encoded),
                    "request_body_sha256": digest,
                    "request_id": batch["request_id"],
                }
            )

    (artifact_dir / "run_plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "task_id": TASK_ID,
        "source_prompt_tokens": len(source_tokens),
        "canonical_batch_body_count": len(records),
        "mechanism_batch_body_count": len(plan["mechanism"]),
        "performance_batch_body_count": len(plan["performance"]),
        "bodies_reused_byte_identically_across_modes_and_lifecycles": True,
        "one_http_request_contains_both_measured_prompt_token_arrays": True,
        "generated_text_retained": False,
        "generated_token_ids_retained": False,
        "records": records,
    }
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
    request_start_ns: int,
    token_arrival_ns: list[int],
    request_end_ns: int,
) -> dict[str, float | int]:
    count = len(token_arrival_ns)
    ttft_ns = token_arrival_ns[0] - request_start_ns if token_arrival_ns else 0
    tpot_ns = (
        (token_arrival_ns[-1] - token_arrival_ns[0]) / (count - 1)
        if count > 1
        else 0.0
    )
    e2el_ns = request_end_ns - request_start_ns
    itl = [
        (right - left) / 1_000_000
        for left, right in zip(token_arrival_ns, token_arrival_ns[1:])
    ]
    return {
        "ttft_ms": round(ttft_ns / 1_000_000, 6),
        "tpot_ms": round(tpot_ns / 1_000_000, 6),
        "e2el_ms": round(e2el_ns / 1_000_000, 6),
        "itl_count": len(itl),
        "itl_p50_ms": round(percentile(itl, 0.50), 6),
        "itl_p95_ms": round(percentile(itl, 0.95), 6),
        "itl_p99_ms": round(percentile(itl, 0.99), 6),
        "output_tokens_per_second": (
            round(count / (e2el_ns / 1_000_000_000), 6)
            if e2el_ns > 0
            else 0.0
        ),
    }


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _get(base_url: str, path: str, timeout: float = 10.0) -> tuple[int | None, bytes]:
    try:
        with urllib.request.urlopen(
            base_url.rstrip("/") + path, timeout=timeout
        ) as response:
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
    values["queue_metrics_present"] = all(
        found[name] for name in ("num_requests_running", "num_requests_waiting")
    )
    values["spec_metrics_present"] = all(
        found[name]
        for name in ("num_drafts", "num_draft_tokens", "num_accepted_tokens")
    )
    return values


def _metrics_snapshot(
    base_url: str, output_path: Path
) -> tuple[int | None, dict[str, Any]]:
    status, raw = _get(base_url, "/metrics")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(raw)
    values = _parse_metrics(raw) if status == 200 else {
        **{alias: 0.0 for alias in METRIC_NAMES.values()},
        "queue_metrics_present": False,
        "spec_metrics_present": False,
    }
    values["http_status"] = status
    return status, values


def _wait_for_idle(
    base_url: str, output_path: Path, timeout_seconds: float = 90.0
) -> tuple[bool, dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status, last = _metrics_snapshot(base_url, output_path)
        if (
            status == 200
            and last.get("queue_metrics_present") is True
            and float(last.get("num_requests_running") or 0) == 0
            and float(last.get("num_requests_waiting") or 0) == 0
        ):
            return True, last
        time.sleep(0.5)
    return False, last


def _failed_rows(batch: dict[str, Any], reason: str) -> list[dict[str, Any]]:
    return [
        {
            "track": batch["track"],
            "phase": batch["phase"],
            "batch_id": batch["batch_id"],
            "cell_id": batch["cell_id"],
            "repeat_index": batch["repeat_index"],
            "choice_index": choice["choice_index"],
            "request_role": choice["request_role"],
            "prompt_tokens": choice["prompt_tokens"],
            "output_tokens": batch["output_tokens"],
            "request_body_sha256": batch["request_body_sha256"],
            "status": "failed",
            "failure_reason": reason,
            "generated_text_retained": False,
            "generated_token_ids_retained": False,
        }
        for choice in batch["choices"]
    ]


def _stream_batched_request(
    artifact_dir: Path,
    base_url: str,
    server_pid: int,
    batch: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    body_path = artifact_dir / batch["body_relative_path"]
    body = body_path.read_bytes()
    body_sha256 = _sha256_bytes(body)
    if body_sha256 != batch["request_body_sha256"]:
        raise ValueError(f"body hash drift for {batch['batch_id']}")
    payload = json.loads(body)
    raw_prompts = payload["prompt"]
    if len(batch["choices"]) == 1:
        prompts = [raw_prompts]
    else:
        prompts = raw_prompts
    if [len(prompt) for prompt in prompts] != [
        int(choice["prompt_tokens"]) for choice in batch["choices"]
    ]:
        raise ValueError(f"prompt length drift for {batch['batch_id']}")

    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/completions",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    arrivals: list[list[int]] = [[] for _ in batch["choices"]]
    finish_reasons: list[str | None] = [None] * len(batch["choices"])
    finish_ns: list[int | None] = [None] * len(batch["choices"])
    max_chunk_widths = [0] * len(batch["choices"])
    usage: dict[str, Any] = {}
    saw_done = False
    http_status: int | None = None
    bounded_error_path: Path | None = None
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
                    choice_index = int(choice["index"])
                    if choice_index < 0 or choice_index >= len(arrivals):
                        raise ValueError(
                            f"unexpected choice index {choice_index} "
                            f"for {batch['batch_id']}"
                        )
                    token_ids = choice.get("token_ids") or []
                    arrivals[choice_index].extend([now_ns] * len(token_ids))
                    max_chunk_widths[choice_index] = max(
                        max_chunk_widths[choice_index], len(token_ids)
                    )
                    if choice.get("finish_reason") is not None:
                        finish_reasons[choice_index] = str(choice["finish_reason"])
                        finish_ns[choice_index] = now_ns
    except urllib.error.HTTPError as error:
        http_status = int(error.code)
        bounded_error_path = (
            artifact_dir
            / "request_errors"
            / f"{batch['batch_id']}.http_error.body"
        )
        bounded_error_path.parent.mkdir(parents=True, exist_ok=True)
        bounded_error_path.write_bytes(error.read(8192))
    except Exception as error:
        bounded_error_path = (
            artifact_dir / "request_errors" / f"{batch['batch_id']}.txt"
        )
        bounded_error_path.parent.mkdir(parents=True, exist_ok=True)
        bounded_error_path.write_text(
            f"{type(error).__name__}: {str(error)[:2048]}\n", encoding="utf-8"
        )
    request_end_ns = time.monotonic_ns()

    expected_output = int(batch["output_tokens"])
    expected_prompt_total = sum(
        int(choice["prompt_tokens"]) for choice in batch["choices"]
    )
    expected_completion_total = expected_output * len(batch["choices"])
    usage_prompt_total = usage.get("prompt_tokens")
    usage_completion_total = usage.get("completion_tokens")
    rows: list[dict[str, Any]] = []
    for choice, token_arrival_ns, reason, end_ns, width in zip(
        batch["choices"],
        arrivals,
        finish_reasons,
        finish_ns,
        max_chunk_widths,
        strict=True,
    ):
        actual_end_ns = end_ns or request_end_ns
        metrics = calculate_request_metrics(
            request_start_ns, token_arrival_ns, actual_end_ns
        )
        checks = {
            "server_alive": _process_alive(server_pid),
            "http_200": http_status == 200,
            "streamed_tokens_exact": len(token_arrival_ns) == expected_output,
            "finish_reason_length": reason == "length",
            "saw_done": saw_done,
            "max_token_chunk_width_within_mtp_bound": width <= 2,
            "batched_usage_prompt_total_exact": (
                usage_prompt_total == expected_prompt_total
            ),
            "batched_usage_completion_total_exact": (
                usage_completion_total == expected_completion_total
            ),
        }
        rows.append(
            {
                "track": batch["track"],
                "phase": batch["phase"],
                "batch_id": batch["batch_id"],
                "cell_id": batch["cell_id"],
                "repeat_index": batch["repeat_index"],
                "choice_index": choice["choice_index"],
                "request_role": choice["request_role"],
                "engine_request_id_expected_suffix": (
                    f"cmpl-{batch['request_id']}-{choice['choice_index']}"
                ),
                "prompt_tokens": choice["prompt_tokens"],
                "output_tokens": expected_output,
                "request_body_sha256": body_sha256,
                "status": "success" if all(checks.values()) else "failed",
                "http_status": http_status,
                "streamed_token_count": len(token_arrival_ns),
                "finish_reason": reason,
                "saw_done": saw_done,
                "max_token_chunk_width": width,
                "batched_usage_prompt_tokens": usage_prompt_total,
                "batched_usage_completion_tokens": usage_completion_total,
                "request_start_ns": request_start_ns,
                "token_arrival_ns": token_arrival_ns,
                "request_end_ns": actual_end_ns,
                **metrics,
                "bounded_error_server_path": (
                    str(bounded_error_path) if bounded_error_path else None
                ),
                "checks": checks,
                "generated_text_retained": False,
                "generated_token_ids_retained": False,
            }
        )
    duration_seconds = (request_end_ns - request_start_ns) / 1_000_000_000
    completion_gap_ms = (
        abs(int(finish_ns[0] or request_end_ns) - int(finish_ns[1] or request_end_ns))
        / 1_000_000
        if len(finish_ns) == 2
        else 0.0
    )
    batch_row = {
        "track": batch["track"],
        "phase": batch["phase"],
        "batch_id": batch["batch_id"],
        "cell_id": batch["cell_id"],
        "repeat_index": batch["repeat_index"],
        "prompt_tokens": batch["prompt_tokens"],
        "total_prefill_tokens": batch["total_prefill_tokens"],
        "pressure": batch["pressure"],
        "choice_count": len(batch["choices"]),
        "request_start_ns": request_start_ns,
        "request_end_ns": request_end_ns,
        "status": "success" if all(row["status"] == "success" for row in rows) else "failed",
        "batch_output_tokens_per_second": (
            round(expected_completion_total / duration_seconds, 6)
            if duration_seconds > 0
            else 0.0
        ),
        "two_request_completion_gap_ms": round(completion_gap_ms, 6),
        "single_http_batched_prompt_request": True,
        "body_sha256": body_sha256,
    }
    return rows, batch_row


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
    batches = plan[track]
    raw_metrics_dir = lifecycle_dir / "runtime" / "raw_metrics"
    all_request_rows: list[dict[str, Any]] = []
    all_batch_rows: list[dict[str, Any]] = []

    for batch in batches:
        health_before, _ = _get(base_url, "/health", timeout=5)
        idle_before, metrics_before = _wait_for_idle(
            base_url, raw_metrics_dir / f"{batch['batch_id']}.before.prom"
        )
        if (
            health_before != 200
            or not idle_before
            or metrics_before.get("spec_metrics_present") is not True
        ):
            rows = _failed_rows(batch, "pre_batch_health_queue_or_mtp_metric_gate")
            batch_row = {
                "track": track,
                "phase": batch["phase"],
                "batch_id": batch["batch_id"],
                "cell_id": batch["cell_id"],
                "repeat_index": batch["repeat_index"],
                "status": "failed",
                "failure_reason": "pre_batch_health_queue_or_mtp_metric_gate",
            }
        else:
            rows, batch_row = _stream_batched_request(
                artifact_dir, base_url, server_pid, batch
            )
        health_after, _ = _get(base_url, "/health", timeout=5)
        idle_after, metrics_after = _wait_for_idle(
            base_url, raw_metrics_dir / f"{batch['batch_id']}.after.prom"
        )
        delta = {
            name: float(metrics_after.get(name) or 0)
            - float(metrics_before.get(name) or 0)
            for name in ("num_drafts", "num_draft_tokens", "num_accepted_tokens")
        }
        spec_activity_ok = (
            metrics_before.get("spec_metrics_present") is True
            and metrics_after.get("spec_metrics_present") is True
            and delta["num_drafts"] > 0
            and delta["num_draft_tokens"] > 0
            and delta["num_accepted_tokens"] >= 0
        )
        queue_health_ok = (
            idle_before
            and idle_after
            and metrics_before.get("queue_metrics_present") is True
            and metrics_after.get("queue_metrics_present") is True
        )
        batch_row.update(
            {
                "mode": mode,
                "health_after_200": health_after == 200,
                "queue_health_ok": queue_health_ok,
                "spec_activity_ok": spec_activity_ok,
                "mtp_counter_delta": delta,
                "server_healthy_and_idle_after": (
                    _process_alive(server_pid)
                    and health_after == 200
                    and idle_after
                ),
            }
        )
        if not (
            batch_row.get("status") == "success"
            and health_after == 200
            and queue_health_ok
            and spec_activity_ok
        ):
            batch_row["status"] = "failed"
        for row in rows:
            row["mode"] = mode
        all_request_rows.extend(rows)
        all_batch_rows.append(batch_row)
        _write_jsonl(lifecycle_dir / "raw_request_results.jsonl", all_request_rows)
        _write_jsonl(lifecycle_dir / "raw_batch_results.jsonl", all_batch_rows)
        if batch_row["status"] != "success":
            break

    expected_request_count = 7 if track == "mechanism" else 19
    expected_batch_count = 4 if track == "mechanism" else 10
    complete = (
        len(all_request_rows) == expected_request_count
        and len(all_batch_rows) == expected_batch_count
        and all(row.get("status") == "success" for row in all_request_rows)
        and all(row.get("status") == "success" for row in all_batch_rows)
    )
    return 0 if complete else 2


def _read_trace_rows(lifecycle_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    trace_root = lifecycle_dir / "runtime" / "scheduler_trace"
    for path in sorted(trace_root.glob("trace.*.jsonl")):
        rows.extend(_read_jsonl(path))
    return rows


def _write_tsv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "min": round(min(values), 6),
        "median": round(statistics.median(values), 6),
        "mean": round(statistics.fmean(values), 6),
        "p95": round(percentile(values, 0.95), 6),
        "max": round(max(values), 6),
    }


def _normalized_chunked_argv(argv: list[str]) -> list[str]:
    return [
        (
            "<chunked-prefill-control>"
            if value in ("--no-enable-chunked-prefill", "--enable-chunked-prefill")
            else value
        )
        for value in argv
    ]


def _argv_evidence(
    lifecycle_rows: list[dict[str, Any]], artifact_dir: Path
) -> dict[str, Any]:
    argv_by_lifecycle: dict[str, list[str]] = {}
    for schedule in lifecycle_rows:
        path = (
            artifact_dir
            / "lifecycles"
            / schedule["lifecycle_id"]
            / "runtime"
            / "server_argv.json"
        )
        if path.is_file():
            argv_by_lifecycle[schedule["lifecycle_id"]] = json.loads(
                path.read_text(encoding="utf-8")
            )["argv"]
    checks = []
    for track in TRACKS:
        track_rows = [row for row in lifecycle_rows if row["track"] == track]
        off_rows = [row for row in track_rows if row["mode"] == MODES[0]]
        on_rows = [row for row in track_rows if row["mode"] == MODES[1]]
        for off in off_rows:
            for on in on_rows:
                off_argv = argv_by_lifecycle.get(off["lifecycle_id"], [])
                on_argv = argv_by_lifecycle.get(on["lifecycle_id"], [])
                differences = [
                    [index, left, right]
                    for index, (left, right) in enumerate(
                        zip(off_argv, on_argv, strict=False)
                    )
                    if left != right
                ]
                checks.append(
                    {
                        "track": track,
                        "off_lifecycle": off["lifecycle_id"],
                        "on_lifecycle": on["lifecycle_id"],
                        "argv_length_equal": len(off_argv) == len(on_argv),
                        "delta_count": len(differences),
                        "differences": differences,
                        "normalized_equal": (
                            _normalized_chunked_argv(off_argv)
                            == _normalized_chunked_argv(on_argv)
                            and bool(off_argv)
                        ),
                        "off_flag_exact": (
                            off_argv.count("--no-enable-chunked-prefill") == 1
                            and "--enable-chunked-prefill" not in off_argv
                        ),
                        "on_flag_exact": (
                            on_argv.count("--enable-chunked-prefill") == 1
                            and "--no-enable-chunked-prefill" not in on_argv
                        ),
                        "prefix_cache_off_both": (
                            "--no-enable-prefix-caching" in off_argv
                            and "--no-enable-prefix-caching" in on_argv
                        ),
                    }
                )
    return {
        "by_lifecycle": argv_by_lifecycle,
        "pair_checks": checks,
        "all_single_variable_exact": bool(checks)
        and all(
            check["argv_length_equal"]
            and check["delta_count"] == 1
            and check["normalized_equal"]
            and check["off_flag_exact"]
            and check["on_flag_exact"]
            and check["prefix_cache_off_both"]
            for check in checks
        ),
    }


def _mechanism_evidence(
    artifact_dir: Path,
    schedule: list[dict[str, Any]],
    plan: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summaries: list[dict[str, Any]] = []
    request_rows: list[dict[str, Any]] = []
    for lifecycle in [item for item in schedule if item["track"] == "mechanism"]:
        lifecycle_dir = artifact_dir / "lifecycles" / lifecycle["lifecycle_id"]
        trace_rows = _read_trace_rows(lifecycle_dir)
        installed = any(row.get("event") == "observer_installed" for row in trace_rows)
        for batch in [
            item for item in plan["mechanism"] if item["phase"] == "measured"
        ]:
            request_marker = f"cmpl-{batch['request_id']}-"
            selected_steps = []
            for row in trace_rows:
                if row.get("event") != "scheduler_step":
                    continue
                serialized = json.dumps(row, separators=(",", ":"))
                if request_marker in serialized:
                    selected_steps.append(row)
            summary = summarize_scheduler_rows(selected_steps)
            partial_count = int(summary["partial_prefill_request_count"])
            waiting_observed = any(
                any(
                    request_marker in request_id
                    for request_id in (
                        (step.get("waiting_order_before") or [])
                        + (step.get("waiting_order_after") or [])
                    )
                )
                for step in selected_steps
            )
            cell_summary = {
                "lifecycle_id": lifecycle["lifecycle_id"],
                "mode": lifecycle["mode"],
                "cell_id": batch["cell_id"],
                "pressure": bool(batch["pressure"]),
                "observer_installed": installed,
                "scheduler_step_count": summary["scheduler_step_count"],
                "prefill_request_count": summary["prefill_request_count"],
                "partial_prefill_request_count": partial_count,
                "waiting_observed": waiting_observed,
                "chunking_observed": partial_count > 0,
            }
            summaries.append(cell_summary)
            for row in summary["request_rows"]:
                request_rows.append(
                    {
                        "lifecycle_id": lifecycle["lifecycle_id"],
                        "mode": lifecycle["mode"],
                        "cell_id": batch["cell_id"],
                        **row,
                    }
                )

    off_rows = [row for row in summaries if row["mode"] == MODES[0]]
    on_rows = [row for row in summaries if row["mode"] == MODES[1]]
    off_no_partial = len(off_rows) == 3 and all(
        row["partial_prefill_request_count"] == 0 for row in off_rows
    )
    on_pressure_chunked = all(
        any(
            row["cell_id"] == cell["cell_id"]
            and row["partial_prefill_request_count"] > 0
            for row in on_rows
        )
        for cell in CELLS
        if cell["pressure"]
    )
    low_pressure_no_partial = all(
        any(
            row["cell_id"] == "no_pressure_32k_32k"
            and row["mode"] == mode
            and row["partial_prefill_request_count"] == 0
            for row in summaries
        )
        for mode in MODES
    )
    observer_exact = len(summaries) == 6 and all(
        row["observer_installed"] for row in summaries
    )
    return (
        {
            "track": "mechanism",
            "cell_summaries": summaries,
            "observer_installed_both_modes": observer_exact,
            "off_prefill_partial_absent_all_cells": off_no_partial,
            "on_prefill_partial_present_both_pressure_cells": on_pressure_chunked,
            "low_pressure_partial_absent_both_modes": low_pressure_no_partial,
            "mechanism_gate_complete": (
                observer_exact
                and off_no_partial
                and on_pressure_chunked
                and low_pressure_no_partial
            ),
            "claim_boundary": (
                "direct_scheduler_mechanism_evidence_in_three_frozen_cells_only"
            ),
        },
        request_rows,
    )


def _performance_tables(
    artifact_dir: Path,
    schedule: list[dict[str, Any]],
    request_rows: list[dict[str, Any]],
    batch_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    measured_requests = [
        row
        for row in request_rows
        if row.get("track") == "performance" and row.get("phase") == "measured"
    ]
    measured_batches = [
        row
        for row in batch_rows
        if row.get("track") == "performance" and row.get("phase") == "measured"
    ]
    lifecycle_by_id = {item["lifecycle_id"]: item for item in schedule}
    for row in measured_requests + measured_batches:
        row.update(lifecycle_by_id.get(str(row.get("lifecycle_id")), {}))

    mode_cell_rows: list[dict[str, Any]] = []
    request_metrics = (
        "ttft_ms",
        "e2el_ms",
        "tpot_ms",
        "itl_p50_ms",
        "itl_p95_ms",
        "itl_p99_ms",
    )
    batch_metrics = (
        "batch_output_tokens_per_second",
        "two_request_completion_gap_ms",
    )
    for mode in MODES:
        for cell in CELLS:
            selected_requests = [
                row
                for row in measured_requests
                if row.get("mode") == mode and row.get("cell_id") == cell["cell_id"]
            ]
            selected_batches = [
                row
                for row in measured_batches
                if row.get("mode") == mode and row.get("cell_id") == cell["cell_id"]
            ]
            row: dict[str, Any] = {
                "mode": mode,
                "cell_id": cell["cell_id"],
                "request_n": len(selected_requests),
                "batch_n": len(selected_batches),
            }
            for metric in request_metrics:
                summary = _summary(
                    [float(item.get(metric) or 0) for item in selected_requests]
                )
                row[f"{metric}_mean"] = summary.get("mean")
                row[f"{metric}_median"] = summary.get("median")
            short_rows = [
                item for item in selected_requests if item.get("request_role") == "short"
            ]
            row["short_request_ttft_ms_mean"] = _summary(
                [float(item.get("ttft_ms") or 0) for item in short_rows]
            ).get("mean")
            for metric in batch_metrics:
                summary = _summary(
                    [float(item.get(metric) or 0) for item in selected_batches]
                )
                row[f"{metric}_mean"] = summary.get("mean")
                row[f"{metric}_median"] = summary.get("median")
            mode_cell_rows.append(row)

    paired_rows: list[dict[str, Any]] = []
    for pair_id in ("pair_01", "pair_02"):
        pair_schedule = [
            item
            for item in schedule
            if item["track"] == "performance" and item["pair_id"] == pair_id
        ]
        if len(pair_schedule) != 2:
            continue
        for cell in CELLS:
            row = {"pair_id": pair_id, "cell_id": cell["cell_id"]}
            for mode in MODES:
                lifecycle_ids = [
                    item["lifecycle_id"]
                    for item in pair_schedule
                    if item["mode"] == mode
                ]
                selected_requests = [
                    item
                    for item in measured_requests
                    if item.get("lifecycle_id") in lifecycle_ids
                    and item.get("cell_id") == cell["cell_id"]
                ]
                selected_batches = [
                    item
                    for item in measured_batches
                    if item.get("lifecycle_id") in lifecycle_ids
                    and item.get("cell_id") == cell["cell_id"]
                ]
                row[f"{mode}_ttft_ms_mean"] = _summary(
                    [float(item.get("ttft_ms") or 0) for item in selected_requests]
                ).get("mean")
                row[f"{mode}_short_ttft_ms_mean"] = _summary(
                    [
                        float(item.get("ttft_ms") or 0)
                        for item in selected_requests
                        if item.get("request_role") == "short"
                    ]
                ).get("mean")
                row[f"{mode}_batch_output_tps_mean"] = _summary(
                    [
                        float(item.get("batch_output_tokens_per_second") or 0)
                        for item in selected_batches
                    ]
                ).get("mean")
                row[f"{mode}_completion_gap_ms_mean"] = _summary(
                    [
                        float(item.get("two_request_completion_gap_ms") or 0)
                        for item in selected_batches
                    ]
                ).get("mean")
            for metric in (
                "ttft_ms_mean",
                "short_ttft_ms_mean",
                "batch_output_tps_mean",
                "completion_gap_ms_mean",
            ):
                off = row.get(f"{MODES[0]}_{metric}")
                on = row.get(f"{MODES[1]}_{metric}")
                row[f"on_minus_off_{metric}"] = (
                    round(float(on) - float(off), 6)
                    if on is not None and off is not None
                    else None
                )
            paired_rows.append(row)
    return mode_cell_rows, paired_rows


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    plan_path = artifact_dir / "run_plan.json"
    plan = (
        json.loads(plan_path.read_text(encoding="utf-8"))
        if plan_path.is_file()
        else build_run_plan()
    )
    schedule_path = artifact_dir / "executed_lifecycle_schedule.tsv"
    schedule: list[dict[str, Any]] = []
    if schedule_path.is_file():
        with schedule_path.open(encoding="utf-8", newline="") as handle:
            schedule = list(csv.DictReader(handle, delimiter="\t"))

    all_request_rows: list[dict[str, Any]] = []
    all_batch_rows: list[dict[str, Any]] = []
    lifecycle_rows: list[dict[str, Any]] = []
    for expected in LIFECYCLE_SCHEDULE:
        lifecycle_dir = artifact_dir / "lifecycles" / expected["lifecycle_id"]
        attempted_path = lifecycle_dir / "lifecycle_attempted.txt"
        attempted = attempted_path.is_file()
        requests = _read_jsonl(lifecycle_dir / "raw_request_results.jsonl")
        batches = _read_jsonl(lifecycle_dir / "raw_batch_results.jsonl")
        for row in requests + batches:
            row["lifecycle_id"] = expected["lifecycle_id"]
            row["track"] = expected["track"]
            row["mode"] = expected["mode"]
            row["pair_id"] = expected["pair_id"]
            row["pair_position"] = expected["pair_position"]
        all_request_rows.extend(requests)
        all_batch_rows.extend(batches)
        cleanup_path = lifecycle_dir / "cleanup_status.txt"
        resolved_path = lifecycle_dir / "runtime" / "resolved_scheduler_config.json"
        resolved = (
            json.loads(resolved_path.read_text(encoding="utf-8"))
            if resolved_path.is_file()
            else {}
        )
        lifecycle_rows.append(
            {
                **expected,
                "request_count": len(requests),
                "successful_request_count": sum(
                    row.get("status") == "success" for row in requests
                ),
                "batch_count": len(batches),
                "successful_batch_count": sum(
                    row.get("status") == "success" for row in batches
                ),
                "lifecycle_attempted": attempted,
                "cleanup_status": (
                    cleanup_path.read_text(encoding="utf-8").strip()
                    if cleanup_path.is_file()
                    else ("missing" if attempted else "not_run")
                ),
                "resolved_enable_chunked_prefill": resolved.get(
                    "resolved_enable_chunked_prefill"
                ),
                "resolved_enable_prefix_caching": resolved.get(
                    "resolved_enable_prefix_caching"
                ),
                "observer_enabled": resolved.get("observer_enabled"),
                "lifecycle_exit_code": (
                    (lifecycle_dir / "lifecycle_exit_code.txt")
                    .read_text(encoding="utf-8")
                    .strip()
                    if (lifecycle_dir / "lifecycle_exit_code.txt").is_file()
                    else ("missing" if attempted else "not_run")
                ),
            }
        )

    expected_schedule = [
        {
            key: str(item[key])
            for key in ("track", "lifecycle_id", "pair_id", "pair_position", "mode")
        }
        for item in LIFECYCLE_SCHEDULE
    ]
    actual_schedule = [
        {
            key: str(item.get(key))
            for key in ("track", "lifecycle_id", "pair_id", "pair_position", "mode")
        }
        for item in schedule
    ]
    schedule_exact = actual_schedule == expected_schedule
    argv = _argv_evidence(list(LIFECYCLE_SCHEDULE), artifact_dir)
    mechanism, mechanism_request_rows = _mechanism_evidence(
        artifact_dir, list(LIFECYCLE_SCHEDULE), plan
    )
    mode_cell_rows, paired_rows = _performance_tables(
        artifact_dir,
        list(LIFECYCLE_SCHEDULE),
        all_request_rows,
        all_batch_rows,
    )

    manifest_path = artifact_dir / "request_body_manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else {"records": []}
    )
    manifest_records = manifest.get("records") or []
    expected_hash_by_batch = {
        str(record["batch_id"]): str(record["request_body_sha256"])
        for record in manifest_records
    }
    manifest_files_exact = len(manifest_records) == 14 and all(
        (artifact_dir / str(record["body_relative_path"])).is_file()
        and _sha256_path(artifact_dir / str(record["body_relative_path"]))
        == str(record["request_body_sha256"])
        for record in manifest_records
    )
    body_pairing_observed = bool(all_request_rows)
    body_pairing_exact = (
        manifest_files_exact
        and all(
            row.get("request_body_sha256")
            == expected_hash_by_batch.get(str(row.get("batch_id")))
            for row in all_request_rows
        )
        if body_pairing_observed
        else None
    )
    expected_request_keys = {
        (
            lifecycle["lifecycle_id"],
            batch["batch_id"],
            int(choice["choice_index"]),
        )
        for lifecycle in LIFECYCLE_SCHEDULE
        for batch in plan[lifecycle["track"]]
        for choice in batch["choices"]
    }
    actual_request_keys = [
        (
            str(row.get("lifecycle_id")),
            str(row.get("batch_id")),
            int(row.get("choice_index", -1)),
        )
        for row in all_request_rows
    ]
    request_matrix_exact = (
        len(actual_request_keys) == len(expected_request_keys)
        and set(actual_request_keys) == expected_request_keys
    )
    expected_batch_keys = {
        (lifecycle["lifecycle_id"], batch["batch_id"])
        for lifecycle in LIFECYCLE_SCHEDULE
        for batch in plan[lifecycle["track"]]
    }
    actual_batch_keys = [
        (str(row.get("lifecycle_id")), str(row.get("batch_id")))
        for row in all_batch_rows
    ]
    batch_matrix_exact = (
        len(actual_batch_keys) == len(expected_batch_keys)
        and set(actual_batch_keys) == expected_batch_keys
    )
    cleanup_all = len(lifecycle_rows) == 6 and all(
        row["cleanup_status"] == "clean" for row in lifecycle_rows
    )
    attempted_lifecycle_rows = [
        row for row in lifecycle_rows if row["lifecycle_attempted"]
    ]
    attempted_cleanup_all = bool(attempted_lifecycle_rows) and all(
        row["cleanup_status"] == "clean" for row in attempted_lifecycle_rows
    )
    resolved_exact = len(lifecycle_rows) == 6 and all(
        row["resolved_enable_chunked_prefill"]
        == (row["mode"] == "chunked_prefill_on")
        and row["resolved_enable_prefix_caching"] is False
        and row["observer_enabled"] == (row["track"] == "mechanism")
        for row in lifecycle_rows
    )
    observer_absent_performance = all(
        not list(
            (
                artifact_dir
                / "lifecycles"
                / row["lifecycle_id"]
                / "runtime"
                / "scheduler_trace"
            ).glob("trace.*.jsonl")
        )
        for row in lifecycle_rows
        if row["track"] == "performance"
    )
    request_success = sum(
        row.get("status") == "success" for row in all_request_rows
    )
    batch_success = sum(row.get("status") == "success" for row in all_batch_rows)
    all_lifecycles_success = all(
        row["lifecycle_exit_code"] == "0" for row in lifecycle_rows
    )

    recovery_path = artifact_dir / "resource_recovery_summary.json"
    recovery = (
        json.loads(recovery_path.read_text(encoding="utf-8"))
        if recovery_path.is_file()
        else {}
    )
    keep_alive_restore_exact = recovery.get("keep_alive_restored_exact") is True
    global_cleanup_path = artifact_dir / "cleanup_status.txt"
    global_cleanup_status = (
        global_cleanup_path.read_text(encoding="utf-8").strip()
        if global_cleanup_path.is_file()
        else "missing"
    )
    cleanup_failure = (
        any(
            row.get("cleanup_status") not in {"", "clean"}
            for row in attempted_lifecycle_rows
        )
        or global_cleanup_status == "incomplete"
        or (
            bool(recovery)
            and recovery.get("keep_alive_restored_exact") is not True
        )
    )
    complete = (
        schedule_exact
        and argv["all_single_variable_exact"]
        and mechanism["mechanism_gate_complete"]
        and observer_absent_performance
        and body_pairing_exact is True
        and request_matrix_exact
        and batch_matrix_exact
        and cleanup_all
        and resolved_exact
        and all_lifecycles_success
        and len(all_request_rows) == 90
        and request_success == 90
        and len(all_batch_rows) == 48
        and batch_success == 48
        and keep_alive_restore_exact
    )
    any_success = request_success > 0
    if cleanup_failure:
        grade = "red_cleanup_incomplete"
    elif complete:
        grade = (
            "candidate_green_p6_3c_r1_chunked_prefill_"
            "scheduler_pressure_matched_ab"
        )
    elif not any_success:
        grade = "red_p6_3c_r1_scheduler_pressure_no_success"
    elif (
        request_success < 90
        or not all_lifecycles_success
        or not cleanup_all
        or not keep_alive_restore_exact
    ):
        grade = "yellow_p6_3c_r1_scheduler_pressure_partial"
    else:
        grade = "red_p6_3c_r1_scheduler_pressure_evidence_incomplete"

    _write_tsv(
        artifact_dir / "lifecycle_summary.tsv",
        lifecycle_rows,
        [
            "track",
            "lifecycle_id",
            "pair_id",
            "pair_position",
            "mode",
            "request_count",
            "successful_request_count",
            "batch_count",
            "successful_batch_count",
            "resolved_enable_chunked_prefill",
            "resolved_enable_prefix_caching",
            "observer_enabled",
            "lifecycle_attempted",
            "cleanup_status",
            "lifecycle_exit_code",
        ],
    )
    (artifact_dir / "mechanism_scheduler_summary.json").write_text(
        json.dumps(mechanism, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_tsv(
        artifact_dir / "mechanism_request_chunk_summary.tsv",
        mechanism_request_rows,
        [
            "lifecycle_id",
            "mode",
            "cell_id",
            "request_id",
            "prompt_tokens",
            "prefill_round_count",
            "partial_prefill_round_count",
            "scheduled_prefill_tokens",
            "first_step_index",
            "last_step_index",
        ],
    )
    mode_fields = list(mode_cell_rows[0]) if mode_cell_rows else ["mode", "cell_id"]
    _write_tsv(
        artifact_dir / "performance_mode_cell_summary.tsv",
        mode_cell_rows,
        mode_fields,
    )
    pair_fields = list(paired_rows[0]) if paired_rows else ["pair_id", "cell_id"]
    _write_tsv(
        artifact_dir / "performance_order_balanced_pairs.tsv",
        paired_rows,
        pair_fields,
    )

    grading = {
        "task_id": TASK_ID,
        "server_grade": grade,
        "parent_p6_3c_grade_preserved": "blocked_p6_3c_not_strict_single_variable",
        "parent_p6_3c_overwritten": False,
        "schedule_exact": schedule_exact,
        "single_variable_argv_exact": argv["all_single_variable_exact"],
        "resolved_config_exact": resolved_exact,
        "observer_present_only_mechanism": observer_absent_performance
        and mechanism["observer_installed_both_modes"],
        "mechanism_gate_complete": mechanism["mechanism_gate_complete"],
        "manifest_files_exact": manifest_files_exact,
        "body_pairing_observed": body_pairing_observed,
        "body_pairing_exact": body_pairing_exact,
        "request_matrix_exact": request_matrix_exact,
        "batch_matrix_exact": batch_matrix_exact,
        "request_count": len(all_request_rows),
        "successful_request_count": request_success,
        "batch_count": len(all_batch_rows),
        "successful_batch_count": batch_success,
        "all_lifecycles_success": all_lifecycles_success,
        "cleanup_all_lifecycles_clean": cleanup_all,
        "attempted_lifecycle_cleanup_all_clean": attempted_cleanup_all,
        "cleanup_failure": cleanup_failure,
        "global_cleanup_status": global_cleanup_status,
        "keep_alive_restore_exact": keep_alive_restore_exact,
        "performance_is_descriptive_only": True,
        "universal_benefit_claimed": False,
        "developer_review_required": True,
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "next_task_authorized": False,
        "argv_evidence": argv["pair_checks"],
    }
    (artifact_dir / "grading_inputs.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    environment = {
        "task_id": TASK_ID,
        "repo_head": _git_output(artifact_dir, "rev-parse", "HEAD"),
        "repo_origin_main": _git_output(artifact_dir, "rev-parse", "origin/main"),
        "workload_path": (
            "benchmarks/deepseek_v4_flash/workloads/"
            "p6_3c_r1_chunked_prefill_scheduler_pressure_matched_ab.yaml"
        ),
        "workload_sha256": _optional_repo_sha256(
            "benchmarks/deepseek_v4_flash/workloads/"
            "p6_3c_r1_chunked_prefill_scheduler_pressure_matched_ab.yaml"
        ),
        "runner_sha256": _sha256_path(Path(__file__)),
        "observer_sha256": _optional_repo_sha256(
            "tools/inference_contracts/p6_3c_r1_scheduler_observer.py"
        ),
        "model": "DeepSeek-V4-Flash-w8a8-mtp",
        "vllm": "0.22.1+empty",
        "vllm_ascend": "0.22.1rc1",
        "max_model_len": 69632,
        "max_num_batched_tokens": 69632,
        "max_num_seqs": 2,
        "prefix_cache_enabled": False,
        "mtp_enabled": True,
        "profiler_enabled": False,
        "generated_text_retained": False,
        "generated_token_ids_retained": False,
    }
    (artifact_dir / "environment_and_hashes.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_result_summary(artifact_dir, grade, grading, mechanism, mode_cell_rows)
    if grade.startswith("candidate_green"):
        (artifact_dir / "first_failure_excerpt.txt").write_text(
            "none\n", encoding="utf-8"
        )
    elif not (artifact_dir / "first_failure_excerpt.txt").is_file():
        (artifact_dir / "first_failure_excerpt.txt").write_text(
            f"server_grade={grade}\n"
            f"successful_request_count={request_success}/90\n"
            f"mechanism_gate_complete={mechanism['mechanism_gate_complete']}\n"
            f"keep_alive_restore_exact={keep_alive_restore_exact}\n",
            encoding="utf-8",
        )
    return grading


def _optional_repo_sha256(relative: str) -> str | None:
    path = REPO_ROOT / relative
    return _sha256_path(path) if path.is_file() else None


def _git_output(artifact_dir: Path, *args: str) -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), *args],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unavailable"


def _write_result_summary(
    artifact_dir: Path,
    grade: str,
    grading: dict[str, Any],
    mechanism: dict[str, Any],
    mode_cell_rows: list[dict[str, Any]],
) -> None:
    short_rows = [
        row
        for row in mode_cell_rows
        if row.get("cell_id") == "asymmetric_pressure_64k_32k"
    ]
    lines = [
        f"# {TASK_ID} 结果摘要",
        "",
        f"- server grade: `{grade}`",
        "- 原 P6.3C 审计保持 `blocked_p6_3c_not_strict_single_variable`，本任务未覆盖该记录。",
        (
            "- 冻结环境：`max_model_len=69632`、"
            "`max_num_batched_tokens=69632`、`max_num_seqs=2`、"
            "Prefix Cache 显式关闭。"
        ),
        (
            f"- 请求：`{grading['successful_request_count']}/90` 成功；"
            f"机制门：`{mechanism['mechanism_gate_complete']}`；"
            f"keep-alive 精确恢复：`{grading['keep_alive_restore_exact']}`。"
        ),
        "",
        "## 机制轨道",
        "",
        (
            "- Off 三个 cell 均无 partial prefill："
            f"`{mechanism['off_prefill_partial_absent_all_cells']}`。"
        ),
        (
            "- On 两个压力 cell 均观测到 partial prefill："
            f"`{mechanism['on_prefill_partial_present_both_pressure_cells']}`。"
        ),
        (
            "- 32K+32K 两侧均无 partial prefill："
            f"`{mechanism['low_pressure_partial_absent_both_modes']}`。"
        ),
        "",
        "## 性能轨道",
        "",
        "- 采用 Off→On→On→Off 四个 fresh lifecycle；observer 与 profiler 均关闭。",
    ]
    for row in short_rows:
        lines.append(
            f"- `{row['mode']}` 非对称压力短请求 TTFT mean="
            f"`{row.get('short_request_ttft_ms_mean')}` ms，"
            "仅作冻结样本内描述。"
        )
    lines.extend(
        [
            "",
            "## 结论边界",
            "",
            "- 该包是候选服务器结果，必须由开发机复核后才能接受为项目结论。",
            "- 不声明普遍性能收益、统计显著性、生产吞吐或任意请求顺序下的短请求改善。",
            "- 在完整清单得到用户明确 `email` / `upload-api` / `server-local` 选择前，不外发任何文件。",
            "",
        ]
    )
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


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
        "recommended_reason": (
            "multi_file_atomic_session_with_per_file_hash_validation"
        ),
        "bounded_transfer_max_bytes": 71680,
        "candidate_file_count": len(candidates),
        "candidate_total_bytes": total_bytes,
        "candidate_total_within_limit": total_bytes <= 71680,
        "candidates": candidates,
        "raw_artifacts_remain_server_local": True,
        "selection_required_before_any_transfer": True,
    }
    manifest_path = artifact_dir / "candidate_manifest.server_local.json"
    manifest_path.write_text(
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
    if args.command == "finalize":
        grading = finalize_artifacts(args.artifact_dir)
        return 0 if str(grading["server_grade"]).startswith("candidate_green") else 2
    if args.command == "package":
        package_results(args.artifact_dir)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
