from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.run_deepseek_p6_1_unprofiled_baseline import (
    _get,
    _process_alive,
    _repeat_and_truncate,
    _select_offsets,
    _stream_request,
)


MODES = ("mtp_off", "mtp_on")
CELLS = (
    ("short_prefill", 4096, 64, 1),
    ("short_decode", 4096, 256, 1),
    ("short_decode_c8", 4096, 256, 8),
    ("mid_prefill", 65536, 64, 1),
    ("mid_prefill_c4", 65536, 64, 4),
    ("mid_decode", 65536, 256, 1),
    ("long_prefill", 131072, 64, 1),
    ("long_decode", 131072, 256, 1),
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
        cell_id: str,
        context_tokens: int,
        output_tokens: int,
        concurrency: int,
        repeat_index: int,
    ) -> None:
        batch_id = (
            f"{phase}_{cell_id}_r{repeat_index}_ctx{context_tokens}"
            f"_out{output_tokens}_c{concurrency}"
        )
        plan.append(
            {
                "batch_id": batch_id,
                "phase": phase,
                "cell_id": cell_id,
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

    add_batch("warmup", "warmup", 4096, 64, 1, 1)
    for cell_id, context, output, concurrency in CELLS:
        for repeat_index in range(1, 4):
            add_batch(
                "measured",
                cell_id,
                context,
                output,
                concurrency,
                repeat_index,
            )
    return plan


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
            (artifact_dir / relative_path).write_bytes(raw)
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
                    "cell_id": batch["cell_id"],
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
        "all_request_body_sha256_unique": (
            len({item["request_body_sha256"] for item in records}) == len(records)
        ),
        "modes_reuse_identical_body_bytes": True,
        "mode_order": list(MODES),
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


def grade_evidence(
    request_rows: list[dict[str, Any]],
    batch_rows: list[dict[str, Any]],
    *,
    cleanup_by_mode: dict[str, str],
) -> dict[str, Any]:
    measured_requests = [row for row in request_rows if row.get("phase") == "measured"]
    measured_batches = [row for row in batch_rows if row.get("phase") == "measured"]
    warmup_requests = [row for row in request_rows if row.get("phase") == "warmup"]
    successful_measured = [row for row in measured_requests if row.get("status") == "success"]
    successful_batches = [row for row in measured_batches if row.get("status") == "success"]
    expected_cells = {(context, output, concurrency) for _, context, output, concurrency in CELLS}
    represented_by_mode = {
        mode: {
            (
                int(row["context_tokens"]),
                int(row["output_tokens"]),
                int(row["concurrency"]),
            )
            for row in successful_measured
            if row.get("mode") == mode
        }
        for mode in MODES
    }
    all_cells_matched = all(
        represented_by_mode[mode] == expected_cells for mode in MODES
    )
    bodies_by_mode = {
        mode: {
            (str(row.get("batch_id")), int(row.get("request_index") or 0)): str(
                row.get("request_body_sha256")
            )
            for row in measured_requests
            if row.get("mode") == mode
        }
        for mode in MODES
    }
    body_pairing_ok = (
        len(bodies_by_mode["mtp_off"]) == 54
        and bodies_by_mode["mtp_off"] == bodies_by_mode["mtp_on"]
    )
    warmup_ok = all(
        sum(
            row.get("mode") == mode and row.get("status") == "success"
            for row in warmup_requests
        )
        == 1
        for mode in MODES
    )
    queue_metrics_ok = len(batch_rows) == 50 and all(
        row.get("queue_metrics_ok") is True for row in batch_rows
    )
    counter_continuity_ok = len(batch_rows) == 50 and all(
        row.get("counter_continuity_ok") is True for row in batch_rows
    )
    spec_activity_ok = len(batch_rows) == 50 and all(
        row.get("spec_activity_ok") is True for row in batch_rows
    )
    accepted_total = sum(
        float(row.get("accepted_token_delta") or 0.0)
        for row in measured_batches
        if row.get("mode") == "mtp_on"
    )
    complete = (
        warmup_ok
        and len(measured_requests) == 108
        and len(successful_measured) == 108
        and len(measured_batches) == 48
        and len(successful_batches) == 48
        and all_cells_matched
        and body_pairing_ok
    )
    any_matched_success = all(
        any(row.get("mode") == mode for row in successful_measured) for mode in MODES
    )

    if any(cleanup_by_mode.get(mode) != "clean" for mode in MODES):
        grade = "red_cleanup_incomplete"
    elif not any_matched_success:
        grade = "red_p6_3a_mtp_matched_ab_no_success"
    elif not complete:
        grade = "yellow_p6_3a_mtp_matched_ab_partial"
    elif not queue_metrics_ok or not counter_continuity_ok or not spec_activity_ok or accepted_total <= 0:
        grade = "red_p6_3a_mtp_matched_ab_evidence_incomplete"
    else:
        grade = "candidate_green_p6_3a_mtp_matched_ab"

    return {
        "server_grade": grade,
        "warmup_ok": warmup_ok,
        "measured_request_count": len(measured_requests),
        "successful_measured_request_count": len(successful_measured),
        "measured_batch_count": len(measured_batches),
        "successful_measured_batch_count": len(successful_batches),
        "all_eight_cells_matched": all_cells_matched,
        "represented_cells_by_mode": {
            mode: [list(cell) for cell in sorted(cells)]
            for mode, cells in represented_by_mode.items()
        },
        "body_pairing_ok": body_pairing_ok,
        "queue_metrics_ok": queue_metrics_ok,
        "counter_continuity_ok": counter_continuity_ok,
        "spec_activity_ok": spec_activity_ok,
        "mtp_on_accepted_token_delta_total": accepted_total,
        "cleanup_by_mode": cleanup_by_mode,
        "mechanism_effect_accepted": False,
        "developer_review_required": True,
        "existing_p6_references_remain_true": True,
        "claim_boundary": "matched_mtp_on_off_mechanism_effect_only",
    }


def parse_metrics(raw: bytes) -> dict[str, Any]:
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
    values["queue_metrics_present"] = (
        found["num_requests_running"] and found["num_requests_waiting"]
    )
    values["spec_metrics_present"] = all(
        found[name]
        for name in ("num_drafts", "num_draft_tokens", "num_accepted_tokens")
    )
    return values


def _metrics_snapshot(base_url: str, raw_path: Path) -> dict[str, Any]:
    status, raw = _get(base_url, "/metrics")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)
    parsed = parse_metrics(raw) if status == 200 else {
        **{alias: 0.0 for alias in METRIC_NAMES.values()},
        "queue_metrics_present": False,
        "spec_metrics_present": False,
    }
    parsed["http_status"] = status
    parsed["raw_server_path"] = str(raw_path)
    return parsed


def _wait_for_idle(
    base_url: str,
    raw_path: Path,
    timeout_seconds: float = 60.0,
) -> tuple[bool, dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _metrics_snapshot(base_url, raw_path)
        if (
            last.get("http_status") == 200
            and last.get("queue_metrics_present") is True
            and last.get("num_requests_running") == 0
            and last.get("num_requests_waiting") == 0
        ):
            return True, last
        time.sleep(0.5)
    return False, last


def _failed_rows(
    batch: dict[str, Any],
    mode: str,
    reason: str,
) -> list[dict[str, Any]]:
    return [
        {
            "mode": mode,
            "request_id": request["request_id"],
            "batch_id": batch["batch_id"],
            "phase": batch["phase"],
            "cell_id": batch["cell_id"],
            "context_tokens": batch["context_tokens"],
            "output_tokens": batch["output_tokens"],
            "concurrency": batch["concurrency"],
            "repeat_index": batch["repeat_index"],
            "request_index": request["request_index"],
            "request_body_sha256": request["request_body_sha256"],
            "status": "failed_pre_batch_gate",
            "failure_reason": reason,
            "generated_text_retained": False,
            "token_ids_retained": False,
        }
        for request in batch["requests"]
    ]


def _run_batch(
    *,
    artifact_dir: Path,
    base_url: str,
    server_pid: int,
    mode: str,
    batch: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    mode_dir = artifact_dir / "modes" / mode
    batch_id = batch["batch_id"]
    health_before, _ = _get(base_url, "/health", timeout=5)
    idle_before, metrics_before = _wait_for_idle(
        base_url,
        mode_dir / "raw_metrics" / f"{batch_id}_before.prom",
    )
    pre_checks = {
        "server_alive": _process_alive(server_pid),
        "health_before_200": health_before == 200,
        "queue_metrics_before_present": metrics_before.get("queue_metrics_present") is True,
        "queue_idle_before": idle_before,
        "mtp_on_spec_metrics_before_present": (
            mode == "mtp_off" or metrics_before.get("spec_metrics_present") is True
        ),
    }
    if not all(pre_checks.values()):
        return _failed_rows(batch, mode, "pre_batch_health_metrics_or_queue_gate"), {
            "mode": mode,
            "batch_id": batch_id,
            "phase": batch["phase"],
            "cell_id": batch["cell_id"],
            "context_tokens": batch["context_tokens"],
            "output_tokens": batch["output_tokens"],
            "concurrency": batch["concurrency"],
            "repeat_index": batch["repeat_index"],
            "status": "failed_pre_batch_gate",
            "queue_metrics_ok": False,
            "spec_activity_ok": False,
            "accepted_token_delta": 0.0,
            "server_healthy_and_idle_after": False,
            "checks": pre_checks,
        }

    barrier = threading.Barrier(len(batch["requests"]) + 1)
    rows: list[dict[str, Any] | None] = [None] * len(batch["requests"])

    def worker(index: int, request_item: dict[str, Any]) -> None:
        try:
            row = _stream_request(
                artifact_dir=artifact_dir,
                base_url=base_url,
                server_pid=server_pid,
                batch=batch,
                request_item=request_item,
                start_barrier=barrier,
            )
            row["mode"] = mode
            row["cell_id"] = batch["cell_id"]
            rows[index] = row
        except Exception as error:
            try:
                barrier.abort()
            except threading.BrokenBarrierError:
                pass
            failed = _failed_rows(
                batch,
                mode,
                f"runner_exception:{type(error).__name__}",
            )[index]
            failed["failure_detail"] = str(error)[:2048]
            rows[index] = failed

    threads = [
        threading.Thread(target=worker, args=(index, item), daemon=True)
        for index, item in enumerate(batch["requests"])
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
        row if row is not None else _failed_rows(batch, mode, "request_thread_timeout")[index]
        for index, row in enumerate(rows)
    ]

    health_after, _ = _get(base_url, "/health", timeout=5)
    idle_after, metrics_after = _wait_for_idle(
        base_url,
        mode_dir / "raw_metrics" / f"{batch_id}_after.prom",
    )
    delta = {
        name: float(metrics_after.get(name) or 0.0) - float(metrics_before.get(name) or 0.0)
        for name in ("num_drafts", "num_draft_tokens", "num_accepted_tokens")
    }
    if mode == "mtp_on":
        spec_activity_ok = (
            metrics_before.get("spec_metrics_present") is True
            and metrics_after.get("spec_metrics_present") is True
            and delta["num_drafts"] > 0
            and delta["num_draft_tokens"] > 0
            and delta["num_accepted_tokens"] >= 0
        )
    else:
        spec_activity_ok = all(value == 0 for value in delta.values())
    queue_metrics_ok = (
        metrics_before.get("queue_metrics_present") is True
        and metrics_after.get("queue_metrics_present") is True
        and idle_before
        and idle_after
    )
    duration_seconds = (batch_end_ns - batch_start_ns) / 1_000_000_000
    generated_total = sum(
        int(row.get("generated_token_count") or 0) for row in completed_rows
    )
    checks = {
        **pre_checks,
        "health_after_200": health_after == 200,
        "queue_metrics_after_present": metrics_after.get("queue_metrics_present") is True,
        "queue_idle_after": idle_after,
        "all_requests_success": all(row.get("status") == "success" for row in completed_rows),
        "spec_activity_ok": spec_activity_ok,
    }
    batch_row = {
        "mode": mode,
        "batch_id": batch_id,
        "phase": batch["phase"],
        "cell_id": batch["cell_id"],
        "context_tokens": batch["context_tokens"],
        "output_tokens": batch["output_tokens"],
        "concurrency": batch["concurrency"],
        "repeat_index": batch["repeat_index"],
        "status": "success" if all(checks.values()) else "failed",
        "request_count": len(completed_rows),
        "successful_request_count": sum(row.get("status") == "success" for row in completed_rows),
        "batch_start_ns": batch_start_ns,
        "batch_end_ns": batch_end_ns,
        "batch_output_tokens_per_second": round(generated_total / duration_seconds, 6)
        if duration_seconds > 0
        else 0.0,
        "batch_requests_per_second": round(len(completed_rows) / duration_seconds, 6)
        if duration_seconds > 0
        else 0.0,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "counter_delta": delta,
        "queue_metrics_ok": queue_metrics_ok,
        "spec_activity_ok": spec_activity_ok,
        "accepted_token_delta": delta["num_accepted_tokens"],
        "server_healthy_and_idle_after": (
            _process_alive(server_pid) and health_after == 200 and idle_after
        ),
        "checks": checks,
    }
    return completed_rows, batch_row


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def execute_mode(
    artifact_dir: Path,
    base_url: str,
    server_pid: int,
    mode: str,
) -> int:
    if mode not in MODES:
        raise ValueError(f"unsupported mode: {mode}")
    plan = json.loads((artifact_dir / "run_plan.json").read_text(encoding="utf-8"))
    request_rows: list[dict[str, Any]] = []
    batch_rows: list[dict[str, Any]] = []
    mode_dir = artifact_dir / "modes" / mode

    for batch in plan:
        rows, batch_row = _run_batch(
            artifact_dir=artifact_dir,
            base_url=base_url,
            server_pid=server_pid,
            mode=mode,
            batch=batch,
        )
        if not batch_rows:
            continuity_ok = True
        else:
            previous_after = batch_rows[-1].get("metrics_after") or {}
            current_before = batch_row.get("metrics_before") or {}
            continuity_ok = bool(previous_after) and bool(current_before) and all(
                float(current_before.get(name) or 0.0)
                >= float(previous_after.get(name) or 0.0)
                for name in ("num_drafts", "num_draft_tokens", "num_accepted_tokens")
            )
        batch_row["counter_continuity_ok"] = continuity_ok
        batch_row.setdefault("checks", {})["counter_continuity_ok"] = continuity_ok
        if not continuity_ok:
            batch_row["status"] = "failed"
        request_rows.extend(rows)
        batch_rows.append(batch_row)
        _write_jsonl(mode_dir / "raw_request_results.jsonl", request_rows)
        _write_jsonl(mode_dir / "raw_batch_results.jsonl", batch_rows)
        if batch["phase"] == "warmup" and batch_row["status"] != "success":
            break
        if not batch_row.get("server_healthy_and_idle_after"):
            break

    measured_requests = [row for row in request_rows if row.get("phase") == "measured"]
    measured_batches = [row for row in batch_rows if row.get("phase") == "measured"]
    complete = (
        len(request_rows) == 55
        and all(row.get("status") == "success" for row in request_rows)
        and len(measured_requests) == 54
        and len(batch_rows) == 25
        and len(measured_batches) == 24
        and all(row.get("status") == "success" for row in batch_rows)
    )
    return 0 if complete else 2


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
        "cv": round(statistics.pstdev(values) / mean, 6)
        if len(values) > 1 and mean
        else 0.0,
    }


def _paired_delta(on_value: float, off_value: float) -> tuple[float, float | None]:
    absolute = on_value - off_value
    relative = absolute / off_value if off_value else None
    return round(absolute, 6), round(relative, 6) if relative is not None else None


def _write_comparison_tables(
    artifact_dir: Path,
    request_rows: list[dict[str, Any]],
    batch_rows: list[dict[str, Any]],
) -> None:
    measured_requests = [row for row in request_rows if row.get("phase") == "measured"]
    measured_batches = [row for row in batch_rows if row.get("phase") == "measured"]
    cell_rows: list[dict[str, Any]] = []
    request_metric_names = (
        "ttft_ms",
        "tpot_ms",
        "e2el_ms",
        "output_tokens_per_second",
    )
    batch_metric_names = (
        "batch_output_tokens_per_second",
        "batch_requests_per_second",
    )
    for mode in MODES:
        for cell_id, context, output, concurrency in CELLS:
            requests = [
                row
                for row in measured_requests
                if row.get("mode") == mode and row.get("cell_id") == cell_id
            ]
            batches = [
                row
                for row in measured_batches
                if row.get("mode") == mode and row.get("cell_id") == cell_id
            ]
            row: dict[str, Any] = {
                "mode": mode,
                "cell_id": cell_id,
                "context_tokens": context,
                "output_tokens": output,
                "concurrency": concurrency,
                "request_n": len(requests),
                "request_success_n": sum(item.get("status") == "success" for item in requests),
                "batch_n": len(batches),
                "batch_success_n": sum(item.get("status") == "success" for item in batches),
            }
            for metric in request_metric_names:
                row[metric] = json.dumps(
                    _summary([float(item.get(metric) or 0.0) for item in requests]),
                    separators=(",", ":"),
                )
            for metric in batch_metric_names:
                row[metric] = json.dumps(
                    _summary([float(item.get(metric) or 0.0) for item in batches]),
                    separators=(",", ":"),
                )
            cell_rows.append(row)
    with (artifact_dir / "mode_cell_summary.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(cell_rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(cell_rows)

    request_by_batch = {
        (mode, batch_id): [
            row
            for row in measured_requests
            if row.get("mode") == mode and row.get("batch_id") == batch_id
        ]
        for mode in MODES
        for batch_id in {str(row.get("batch_id")) for row in measured_batches}
    }
    batch_by_key = {
        (str(row["mode"]), str(row["cell_id"]), int(row["repeat_index"])): row
        for row in measured_batches
    }
    paired_rows: list[dict[str, Any]] = []
    for cell_id, context, output, concurrency in CELLS:
        for repeat_index in range(1, 4):
            off = batch_by_key.get(("mtp_off", cell_id, repeat_index), {})
            on = batch_by_key.get(("mtp_on", cell_id, repeat_index), {})
            row: dict[str, Any] = {
                "cell_id": cell_id,
                "context_tokens": context,
                "output_tokens": output,
                "concurrency": concurrency,
                "repeat_index": repeat_index,
                "mtp_off_batch_status": off.get("status"),
                "mtp_on_batch_status": on.get("status"),
            }
            for metric in batch_metric_names:
                off_value = float(off.get(metric) or 0.0)
                on_value = float(on.get(metric) or 0.0)
                absolute, relative = _paired_delta(on_value, off_value)
                row[f"mtp_off_{metric}"] = off_value
                row[f"mtp_on_{metric}"] = on_value
                row[f"on_minus_off_{metric}"] = absolute
                row[f"on_minus_off_relative_{metric}"] = relative
            for metric in request_metric_names:
                off_values = [
                    float(item.get(metric) or 0.0)
                    for item in request_by_batch.get(("mtp_off", str(off.get("batch_id"))), [])
                ]
                on_values = [
                    float(item.get(metric) or 0.0)
                    for item in request_by_batch.get(("mtp_on", str(on.get("batch_id"))), [])
                ]
                off_value = statistics.median(off_values) if off_values else 0.0
                on_value = statistics.median(on_values) if on_values else 0.0
                absolute, relative = _paired_delta(on_value, off_value)
                row[f"mtp_off_batch_request_median_{metric}"] = round(off_value, 6)
                row[f"mtp_on_batch_request_median_{metric}"] = round(on_value, 6)
                row[f"on_minus_off_batch_request_median_{metric}"] = absolute
                row[f"on_minus_off_relative_batch_request_median_{metric}"] = relative
            paired_rows.append(row)
    with (artifact_dir / "paired_batch_summary.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(paired_rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(paired_rows)


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), *args], text=True
        ).strip()
    except Exception:
        return ""


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    request_rows = [
        row
        for mode in MODES
        for row in _read_jsonl(artifact_dir / "modes" / mode / "raw_request_results.jsonl")
    ]
    batch_rows = [
        row
        for mode in MODES
        for row in _read_jsonl(artifact_dir / "modes" / mode / "raw_batch_results.jsonl")
    ]
    cleanup_by_mode = {
        mode: (artifact_dir / "modes" / mode / "cleanup_status.txt").read_text(
            encoding="utf-8"
        ).strip()
        if (artifact_dir / "modes" / mode / "cleanup_status.txt").exists()
        else "incomplete"
        for mode in MODES
    }
    grading = grade_evidence(
        request_rows,
        batch_rows,
        cleanup_by_mode=cleanup_by_mode,
    )
    _write_comparison_tables(artifact_dir, request_rows, batch_rows)
    (artifact_dir / "grading_inputs.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "server_grade.txt").write_text(
        grading["server_grade"] + "\n", encoding="utf-8"
    )
    environment = {
        "git_head": _git_value("rev-parse", "HEAD"),
        "origin_main": _git_value("rev-parse", "origin/main"),
        "tracked_status": _git_value("status", "--porcelain", "--untracked-files=no"),
        "source_payload_sha256": (
            (artifact_dir / "source_payload_sha256.txt").read_text(encoding="utf-8").split()[0]
            if (artifact_dir / "source_payload_sha256.txt").exists()
            else None
        ),
        "server_command_sha256_by_mode": {
            mode: (
                (artifact_dir / "modes" / mode / "server_command_sha256.txt")
                .read_text(encoding="utf-8")
                .split()[0]
                if (artifact_dir / "modes" / mode / "server_command_sha256.txt").exists()
                else None
            )
            for mode in MODES
        },
        "server_lifecycle_count": 2,
        "profiler_run": False,
        "hbm_sampler_run": False,
        "mode_order": list(MODES),
        "fixed_mode_order_is_a_reported_limitation": True,
    }
    (artifact_dir / "environment_and_hashes.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# P6.3A matched MTP on/off server result",
        "",
        "- task_id: p6_3a_deepseek_v4_flash_w8a8_mtp_matched_ab_2026_0715",
        f"- server_grade: {grading['server_grade']}",
        f"- measured_requests: {grading['successful_measured_request_count']}/{grading['measured_request_count']} successful",
        f"- measured_batches: {grading['successful_measured_batch_count']}/{grading['measured_batch_count']} successful",
        f"- all_eight_cells_matched: {str(grading['all_eight_cells_matched']).lower()}",
        f"- body_pairing_ok: {str(grading['body_pairing_ok']).lower()}",
        f"- mtp_on_accepted_token_delta_total: {grading['mtp_on_accepted_token_delta_total']}",
        f"- cleanup_by_mode: {json.dumps(cleanup_by_mode, sort_keys=True)}",
        "- mechanism_effect_accepted: false (developer review required)",
        "- green_means_evidence_complete_not_mtp_faster: true",
        "- fixed_mode_order_limitation: mtp_off_then_mtp_on",
        "- claim_boundary: matched_mtp_on_off_mechanism_effect_only",
        f"- raw_result_root_server_local: {artifact_dir}",
        "- generated_text_retained: false",
        "- token_ids_retained: false",
    ]
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    if grading["server_grade"] != "candidate_green_p6_3a_mtp_matched_ab":
        first_failed = next(
            (row for row in request_rows if row.get("status") != "success"),
            None,
        )
        if first_failed is not None:
            bounded = {
                key: value
                for key, value in first_failed.items()
                if key not in {"token_arrival_ns"}
            }
            (artifact_dir / "first_failure_excerpt.txt").write_text(
                json.dumps(bounded, indent=2, sort_keys=True)[:8192] + "\n",
                encoding="utf-8",
            )

    candidate_names = (
        "result_summary.md",
        "environment_and_hashes.json",
        "request_body_manifest.json",
        "mode_cell_summary.tsv",
        "paired_batch_summary.tsv",
        "grading_inputs.json",
        "cleanup_status.txt",
        "first_failure_excerpt.txt",
    )
    candidates: list[tuple[str, int, str, str]] = []
    total = 0
    for name in candidate_names:
        path = artifact_dir / name
        if not path.exists():
            continue
        size = path.stat().st_size
        total += size
        candidates.append(
            (
                str(path),
                size,
                hashlib.sha256(path.read_bytes()).hexdigest(),
                "bounded_structured_matched_ab_evidence_no_generated_content_or_token_ids",
            )
        )
    with (artifact_dir / "delivery_candidates.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["path", "bytes", "sha256", "sensitivity"])
        writer.writerows(candidates)
    (artifact_dir / "delivery_candidates_total_bytes.txt").write_text(
        f"{total}\n", encoding="utf-8"
    )
    grading["candidate_total_bytes"] = total
    grading["candidate_size_gate_pass"] = total <= 71680
    return grading


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the DeepSeek P6.3A matched MTP on/off client."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    run_mode = subparsers.add_parser("run-mode")
    run_mode.add_argument("--artifact-dir", type=Path, required=True)
    run_mode.add_argument("--base-url", required=True)
    run_mode.add_argument("--server-pid", type=int, required=True)
    run_mode.add_argument("--mode", choices=MODES, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        prepare_artifacts(args.source_payload, args.artifact_dir, args.model_name)
        return 0
    if args.command == "run-mode":
        return execute_mode(args.artifact_dir, args.base_url, args.server_pid, args.mode)
    if args.command == "finalize":
        finalize_artifacts(args.artifact_dir)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
