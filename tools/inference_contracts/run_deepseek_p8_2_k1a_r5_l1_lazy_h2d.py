from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.inference_contracts.run_deepseek_p6_3b_prefix_cache_ab import (
    _common_prefix_length,
    _get,
    _process_alive,
    _stream_request,
    _wait_for_idle,
    _write_jsonl,
    prepare_artifacts,
)
from tools.inference_contracts.p8_2_k1a_h2d_residency_observer import (
    build_residency_gate,
    summarize_h2d_trigger_rows,
)
from tools.inference_contracts.p8_2_k1a_simple_cpu_offload_observer import (
    summarize_trace_rows,
)


TASK_ID = "p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721"
OUTPUT_TOKENS = 64
BLOCK_SIZE_TOKENS = 128
TARGET_PREFIX_TOKENS = 8192
TARGET_PREFIX_BLOCKS = TARGET_PREFIX_TOKENS // BLOCK_SIZE_TOKENS
RESTORE_MATCH_TOKENS = 16384
PRESSURE_CONTEXT_TOKENS = 131072
PRESSURE_REQUEST_COUNT_MAX = 5


def _plan_row(
    request_id: str,
    group_id: str,
    role: str,
    context_tokens: int,
    shared_tokens: int = 0,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "group_id": group_id,
        "request_role": "measured" if role == "restore_follower" else "prime",
        "k1a_role": role,
        "repeat_index": 1 if role == "restore_follower" else 0,
        "context_tokens": context_tokens,
        "output_tokens": OUTPUT_TOKENS,
        "target_shared_prefix_ratio_pct": (
            shared_tokens * 100 // context_tokens if shared_tokens else 0
        ),
        "target_shared_prefix_tokens": shared_tokens,
    }


def build_run_plan() -> list[dict[str, Any]]:
    plan = [
        _plan_row("lifecycle_01_warmup", "r5_l1_warmup", "warmup", 4096),
        _plan_row(
            "lifecycle_01_target_prime",
            "r5_l1_target",
            "target_prime",
            32768,
            RESTORE_MATCH_TOKENS,
        ),
    ]
    plan.extend(
        _plan_row(
            f"lifecycle_01_pressure_{index:02d}",
            f"r5_l1_pressure_{index:02d}",
            f"pressure_{index:02d}",
            PRESSURE_CONTEXT_TOKENS,
        )
        for index in range(1, PRESSURE_REQUEST_COUNT_MAX + 1)
    )
    plan.append(
        _plan_row(
            "lifecycle_01_restore_follower",
            "r5_l1_target",
            "restore_follower",
            32768,
            RESTORE_MATCH_TOKENS,
        )
    )
    return plan


def prepare_lazy_h2d_artifacts(
    source_payload: Path,
    artifact_dir: Path,
    model_name: str,
) -> dict[str, Any]:
    plan = build_run_plan()
    prepared = prepare_artifacts(
        source_payload,
        artifact_dir,
        model_name,
        plan=plan,
    )
    prepared_by_id = {
        str(row["request_id"]): row for row in prepared["records"]
    }
    records: list[dict[str, Any]] = []
    prompts: dict[str, list[int]] = {}
    for plan_row in plan:
        request_id = str(plan_row["request_id"])
        record = prepared_by_id[request_id]
        body_path = artifact_dir / str(record["body_relative_path"])
        prompts[request_id] = json.loads(
            body_path.read_text(encoding="utf-8")
        )["prompt"]
        records.append({**record, **plan_row})

    prime = prompts["lifecycle_01_target_prime"]
    restore = prompts["lifecycle_01_restore_follower"]
    restore_lcp = _common_prefix_length(prime, restore)
    if restore_lcp // RESTORE_MATCH_TOKENS * RESTORE_MATCH_TOKENS != RESTORE_MATCH_TOKENS:
        raise ValueError("restore follower does not preserve the 16K hybrid match")
    isolated_ids = [
        row["request_id"]
        for row in plan
        if row["k1a_role"] not in {"target_prime", "restore_follower"}
    ]
    cross_group_lcp_max = max(
        _common_prefix_length(prime, prompts[str(request_id)])
        for request_id in isolated_ids
    )
    if cross_group_lcp_max >= BLOCK_SIZE_TOKENS:
        raise ValueError("isolated body shares a cacheable target block")
    body_hashes = {str(row["request_body_sha256"]) for row in records}
    if len(body_hashes) != len(records):
        raise ValueError("request bodies are not unique")

    (artifact_dir / "run_plan.json").write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "p8_2_k1a_r5_l1_request_body_manifest_v1",
        "task_id": TASK_ID,
        "source_payload_sha256": hashlib.sha256(
            source_payload.read_bytes()
        ).hexdigest(),
        "lifecycle_count": 1,
        "fixed_request_count": 3,
        "pressure_request_count_max": PRESSURE_REQUEST_COUNT_MAX,
        "request_count_max": len(records),
        "request_order_contract": [
            "warmup",
            "target_prime",
            "pressure_01..pressure_05_until_cpu_present_gpu_absent",
            "restore_follower_if_and_only_if_trigger_observed",
        ],
        "target_prefix_tokens": TARGET_PREFIX_TOKENS,
        "target_prefix_blocks": TARGET_PREFIX_BLOCKS,
        "restore_match_tokens_required": RESTORE_MATCH_TOKENS,
        "restore_token_lcp": restore_lcp,
        "pressure_context_tokens": PRESSURE_CONTEXT_TOKENS,
        "pressure_request_count_is_runtime_fact": False,
        "restore_body_prepared_but_conditionally_sent": True,
        "cross_group_lcp_max": cross_group_lcp_max,
        "cross_group_lcp_less_than_block_size": True,
        "body_hashes_unique": True,
        "records": records,
        "generated_text_retained": False,
        "token_ids_retained": False,
    }
    (artifact_dir / "request_body_manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def decide_next_action(
    gate: dict[str, Any], *, pressure_count: int
) -> tuple[dict[str, Any], int]:
    decision = str(gate.get("decision") or "unobservable")
    restore_allowed = gate.get("restore_allowed") is True
    if decision == "trigger_ready" and restore_allowed:
        action = "send_restore_follower"
        exit_code = 0
    elif decision == "continue_pressure" and pressure_count < PRESSURE_REQUEST_COUNT_MAX:
        action = f"send_pressure_{pressure_count + 1:02d}"
        exit_code = 0
    elif decision == "continue_pressure":
        action = "stop_trigger_not_reached"
        exit_code = 3
    elif decision == "cpu_target_lost":
        action = "stop_cpu_target_lost"
        exit_code = 4
    else:
        action = "stop_residency_unobservable"
        exit_code = 4
    return {
        "action": action,
        "pressure_count": pressure_count,
        "restore_allowed": action == "send_restore_follower",
    }, exit_code


def _write_active_role(path: Path, role: str) -> None:
    value = {
        "schema_version": "p8_2_k1a_r5_l1_active_role_v1",
        "role": role,
        "raw_hash_values_retained": False,
        "updated_timestamp_ns": time.time_ns(),
    }
    temporary = path.with_suffix(".tmp")
    _write_json(temporary, value)
    temporary.replace(path)


def _execute_one_request(
    *,
    artifact_dir: Path,
    control_dir: Path,
    base_url: str,
    server_pid: int,
    item: dict[str, Any],
    previous_after: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request_id = str(item["request_id"])
    health_before, _ = _get(base_url, "/health", timeout=5)
    idle_before, metrics_before = _wait_for_idle(
        base_url,
        control_dir / "raw_metrics" / f"{request_id}_before.prom",
    )
    pre_checks = {
        "server_alive_before": _process_alive(server_pid),
        "health_before_200": health_before == 200,
        "queue_metrics_before_present": (
            metrics_before.get("queue_metrics_present") is True
        ),
        "queue_idle_before": idle_before,
        "spec_metrics_before_present": (
            metrics_before.get("spec_metrics_present") is True
        ),
        "prefix_metrics_before_present": (
            metrics_before.get("prefix_metrics_present") is True
        ),
    }
    if not all(pre_checks.values()):
        return {
            **item,
            "status": "failed_pre_request_gate",
            "queue_metrics_ok": False,
            "counter_continuity_ok": False,
            "spec_activity_ok": False,
            "accepted_token_delta": 0.0,
            "prefix_hits_delta": 0.0,
            "checks": pre_checks,
            "generated_text_retained": False,
            "token_ids_retained": False,
        }, metrics_before

    batch = {
        "batch_id": request_id,
        "phase": item["request_role"],
        "cell_id": item["group_id"],
        "context_tokens": item["context_tokens"],
        "output_tokens": item["output_tokens"],
        "concurrency": 1,
        "repeat_index": item["repeat_index"],
        "requests": [{**item, "request_index": 1}],
    }
    row = _stream_request(
        artifact_dir=artifact_dir,
        base_url=base_url,
        server_pid=server_pid,
        batch=batch,
        request_item=batch["requests"][0],
        start_barrier=threading.Barrier(1),
    )
    health_after, _ = _get(base_url, "/health", timeout=5)
    idle_after, metrics_after = _wait_for_idle(
        base_url,
        control_dir / "raw_metrics" / f"{request_id}_after.prom",
    )
    names = (
        "prefix_queries",
        "prefix_hits",
        "num_drafts",
        "num_draft_tokens",
        "num_accepted_tokens",
    )
    delta = {
        name: float(metrics_after.get(name) or 0.0)
        - float(metrics_before.get(name) or 0.0)
        for name in names
    }
    continuity_ok = previous_after is None or all(
        float(metrics_before.get(name) or 0.0)
        >= float(previous_after.get(name) or 0.0)
        for name in names
    )
    queue_ok = all(
        (
            metrics_before.get("queue_metrics_present") is True,
            metrics_after.get("queue_metrics_present") is True,
            idle_before,
            idle_after,
        )
    )
    spec_ok = all(
        (
            metrics_before.get("spec_metrics_present") is True,
            metrics_after.get("spec_metrics_present") is True,
            delta["num_drafts"] > 0,
            delta["num_draft_tokens"] > 0,
            delta["num_accepted_tokens"] >= 0,
        )
    )
    prefix_ok = all(
        (
            metrics_before.get("prefix_metrics_present") is True,
            metrics_after.get("prefix_metrics_present") is True,
            delta["prefix_queries"] > 0,
            0 <= delta["prefix_hits"] <= delta["prefix_queries"],
        )
    )
    checks = {
        **pre_checks,
        "health_after_200": health_after == 200,
        "queue_idle_after": idle_after,
        "queue_metrics_ok": queue_ok,
        "counter_continuity_ok": continuity_ok,
        "spec_activity_ok": spec_ok,
        "prefix_metrics_observed": prefix_ok,
    }
    row.update(
        {
            "k1a_role": item["k1a_role"],
            "group_id": item["group_id"],
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "prefix_hits_delta": delta["prefix_hits"],
            "accepted_token_delta": delta["num_accepted_tokens"],
            "queue_metrics_ok": queue_ok,
            "counter_continuity_ok": continuity_ok,
            "spec_activity_ok": spec_ok,
            "prefix_evidence_ok": prefix_ok,
            "checks": {**row.get("checks", {}), **checks},
        }
    )
    if row.get("status") != "success" or not all(checks.values()):
        row["status"] = "failed"
    return row, metrics_after


def _current_residency_gate(trace_dir: Path) -> dict[str, Any]:
    return build_residency_gate(
        _read_trace_rows(trace_dir), target_block_count=TARGET_PREFIX_BLOCKS
    )


def _wait_for_target_cpu_presence(
    trace_dir: Path, *, timeout_seconds: float
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _current_residency_gate(trace_dir)
        if last.get("decision") == "cpu_target_lost":
            return last
        if (
            last.get("target_hashes_captured_exact") is True
            and int(last.get("latest_cpu_target_block_count") or 0)
            == TARGET_PREFIX_BLOCKS
        ):
            return last
        time.sleep(1)
    return {**last, "decision": "unobservable", "restore_allowed": False}


def execute_lazy_h2d_lifecycle(
    artifact_dir: Path, base_url: str, server_pid: int
) -> int:
    plan = json.loads((artifact_dir / "run_plan.json").read_text(encoding="utf-8"))
    by_role = {str(row["k1a_role"]): row for row in plan}
    control_dir = artifact_dir / "runtime/request_control"
    trace_dir = artifact_dir / "runtime/offload_trace"
    control_dir.mkdir(parents=True, exist_ok=True)
    role_path = Path(
        os.environ.get(
            "P8_2_K1A_H2D_ACTIVE_ROLE_PATH",
            str(control_dir / "active_role.json"),
        )
    )
    rows: list[dict[str, Any]] = []
    previous_after: dict[str, Any] | None = None
    gate_samples: list[dict[str, Any]] = []

    def run_role(role: str) -> bool:
        nonlocal previous_after
        _write_active_role(role_path, role)
        row, previous_after = _execute_one_request(
            artifact_dir=artifact_dir,
            control_dir=control_dir,
            base_url=base_url,
            server_pid=server_pid,
            item=by_role[role],
            previous_after=previous_after,
        )
        rows.append(row)
        _write_jsonl(control_dir / "raw_request_results.jsonl", rows)
        return row.get("status") == "success"

    for role in ("warmup", "target_prime"):
        if not run_role(role):
            _write_json(
                control_dir / "residency_gate_timeline.json",
                {
                    "pressure_request_count_executed": 0,
                    "restore_sent": False,
                    "trigger_observed_before_restore": False,
                    "terminal_decision": "request_failure",
                    "gate_samples": gate_samples,
                },
            )
            return 2

    timeout = float(os.environ.get("P8_2_K1A_H2D_RESIDENCY_TIMEOUT_SECONDS", "180"))
    initial_gate = _wait_for_target_cpu_presence(trace_dir, timeout_seconds=timeout)
    gate_samples.append({"after_role": "target_prime", **initial_gate})
    if initial_gate.get("decision") in {"unobservable", "cpu_target_lost"}:
        _write_json(
            control_dir / "residency_gate_timeline.json",
            {
                "pressure_request_count_executed": 0,
                "restore_sent": False,
                "trigger_observed_before_restore": False,
                "terminal_decision": initial_gate["decision"],
                "gate_samples": gate_samples,
            },
        )
        return 4

    pressure_count = 0
    terminal = "trigger_not_reached"
    for pressure_count in range(1, PRESSURE_REQUEST_COUNT_MAX + 1):
        role = f"pressure_{pressure_count:02d}"
        if not run_role(role):
            terminal = "request_failure"
            break
        gate = _wait_for_target_cpu_presence(trace_dir, timeout_seconds=timeout)
        gate_samples.append({"after_role": role, **gate})
        decision, _ = decide_next_action(gate, pressure_count=pressure_count)
        action = decision["action"]
        if action == "send_restore_follower":
            terminal = "trigger_ready"
            break
        if action.startswith("stop_"):
            terminal = action.removeprefix("stop_")
            break

    restore_sent = False
    if terminal == "trigger_ready":
        restore_sent = run_role("restore_follower")
        if not restore_sent:
            terminal = "request_failure"
    timeline = {
        "schema_version": "p8_2_k1a_r5_l1_residency_gate_timeline_v1",
        "pressure_request_count_executed": pressure_count,
        "pressure_request_count_max": PRESSURE_REQUEST_COUNT_MAX,
        "restore_sent": restore_sent,
        "trigger_observed_before_restore": terminal == "trigger_ready" and restore_sent,
        "terminal_decision": terminal,
        "gate_samples": gate_samples,
        "raw_hash_values_retained": False,
    }
    _write_json(control_dir / "residency_gate_timeline.json", timeline)
    return 0 if terminal == "trigger_ready" and restore_sent else 3


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _read_trace_rows(trace_dir: Path) -> list[dict[str, Any]]:
    combined = trace_dir / "combined.json"
    if combined.is_file():
        value = json.loads(combined.read_text(encoding="utf-8"))
        if isinstance(value, list) and all(isinstance(row, dict) for row in value):
            return value
    rows: list[dict[str, Any]] = []
    for path in sorted(trace_dir.glob("*.jsonl")):
        rows.extend(_read_jsonl(path))
    return rows


def _request_evidence_exact(row: dict[str, Any]) -> bool:
    role = str(row.get("k1a_role") or "")
    if role == "warmup":
        expected_context = 4096
    elif role == "target_prime" or role == "restore_follower":
        expected_context = 32768
    elif role.startswith("pressure_"):
        expected_context = PRESSURE_CONTEXT_TOKENS
    else:
        return False
    return all(
        (
            row.get("status") == "success",
            row.get("http_status") == 200,
            int(row.get("prompt_tokens") or 0) == expected_context,
            int(row.get("context_tokens") or 0) == expected_context,
            int(row.get("output_tokens") or 0) == OUTPUT_TOKENS,
            int(row.get("generated_token_count") or 0) == OUTPUT_TOKENS,
            int(row.get("streamed_token_count") or 0) == OUTPUT_TOKENS,
            row.get("finish_reason") == "length",
            row.get("saw_done") is True,
            0 < int(row.get("max_token_chunk_width") or 0) <= 2,
            row.get("queue_metrics_ok") is True,
            row.get("counter_continuity_ok") is True,
            row.get("spec_activity_ok") is True,
            float(row.get("accepted_token_delta") or 0) > 0,
            len(str(row.get("request_body_sha256") or "")) == 64,
        )
    )


def _write_request_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = (
        "request_id",
        "k1a_role",
        "status",
        "http_status",
        "context_tokens",
        "output_tokens",
        "generated_token_count",
        "streamed_token_count",
        "finish_reason",
        "saw_done",
        "prefix_hits_delta",
        "accepted_token_delta",
        "queue_metrics_ok",
        "counter_continuity_ok",
        "spec_activity_ok",
        "ttft_ms",
        "e2el_ms",
        "request_body_sha256",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def _build_candidate_manifest(artifact_dir: Path) -> dict[str, Any]:
    names = (
        "result_summary.md",
        "environment_and_hashes.json",
        "request_body_manifest.json",
        "request_summary.tsv",
        "residency_gate_timeline.json",
        "h2d_trigger_summary.json",
        "transfer_trace_summary.json",
        "connector_resolution_summary.json",
        "mtp_queue_health_summary.json",
        "repair_diagnostic_summary.json",
        "host_memory_summary.json",
        "grading_summary.json",
        "cleanup_status.txt",
        "resource_recovery_summary.json",
        "first_failure_excerpt.txt",
    )
    files: dict[str, dict[str, Any]] = {}
    total = 0
    for name in names:
        path = artifact_dir / name
        if not path.is_file():
            continue
        size = path.stat().st_size
        total += size
        files[name] = {
            "bytes": size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "sensitivity": "bounded_operational_metadata_no_content_or_token_ids",
        }
    return {
        "schema_version": "p8_2_k1a_r5_l1_bounded_candidate_manifest_v1",
        "files": files,
        "payload_file_count": len(files),
        "transfer_file_count_including_manifest": len(files) + 1,
        "payload_file_count_max": 15,
        "transfer_file_count_including_manifest_max": 16,
        "candidate_total_bytes": total,
        "max_transfer_total_bytes": 71680,
        "generated_content_retained": False,
        "token_ids_retained": False,
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
    }


def finalize_lazy_h2d_artifacts(artifact_dir: Path) -> int:
    control_dir = artifact_dir / "runtime/request_control"
    request_rows = _read_jsonl(control_dir / "raw_request_results.jsonl")
    timeline = _read_json(control_dir / "residency_gate_timeline.json")
    trace_rows = _read_trace_rows(artifact_dir / "runtime/offload_trace")
    trigger_summary = summarize_h2d_trigger_rows(
        trace_rows,
        target_block_count=TARGET_PREFIX_BLOCKS,
        restore_tokens=RESTORE_MATCH_TOKENS,
        expected_world_size=8,
    )
    transfer_summary = summarize_trace_rows(
        trace_rows,
        expected_world_size=8,
        restore_request_suffix="restore_follower",
    )
    connector = _read_json(artifact_dir / "connector_resolution_summary.json")
    repair = _read_json(artifact_dir / "repair_diagnostic_summary.json")
    host = _read_json(artifact_dir / "host_memory_summary.json")
    recovery = _read_json(artifact_dir / "resource_recovery_summary.json")
    cleanup = (
        (artifact_dir / "cleanup_status.txt").read_text(encoding="utf-8").strip()
        if (artifact_dir / "cleanup_status.txt").is_file()
        else "missing"
    )

    roles = [str(row.get("k1a_role") or "") for row in request_rows]
    pressure_roles = [role for role in roles if role.startswith("pressure_")]
    pressure_count = int(
        timeline.get("pressure_request_count_executed")
        if "pressure_request_count_executed" in timeline
        else len(pressure_roles)
    )
    restore_sent_after_trigger_only = all(
        (
            timeline.get("restore_sent") is True,
            timeline.get("trigger_observed_before_restore") is True,
            roles[:2] == ["warmup", "target_prime"],
            roles[-1:] == ["restore_follower"],
            1 <= pressure_count <= PRESSURE_REQUEST_COUNT_MAX,
            len(pressure_roles) == pressure_count,
        )
    )
    request_evidence_exact = bool(request_rows) and all(
        _request_evidence_exact(row) for row in request_rows
    )
    connector_ok = all(
        (
            connector.get("resolved_connector_exact") is True,
            connector.get("resolved_lazy_offload_exact") is True,
        )
    )
    repair_ok = (
        repair.get("hybrid_diagnostic_ok") is True
        or repair.get("all_required_managers_resolved") is True
    )
    host_ok = host.get("preflight_gate_ok") is True
    recovery_ok = all(
        (
            recovery.get("keep_alive_restored_exact") is True,
            recovery.get("port_7000_free") is True,
            recovery.get("vllm_residual_process_count") == 0,
            recovery.get("all_eight_npu_healthy") is True,
            recovery.get("tracked_worktree_clean") is True,
        )
    )
    mechanism_ok = all(
        (
            trigger_summary["h2d_restore_mechanism_candidate"] is True,
            transfer_summary["d2h_store_complete"] is True,
            transfer_summary["h2d_restore_complete"] is True,
            transfer_summary["d2h_async_copy_pipeline_exact"] is True,
            transfer_summary["h2d_async_copy_pipeline_exact"] is True,
        )
    )
    successful_count = sum(
        _request_evidence_exact(row) for row in request_rows
    )
    mtp_queue_health = {
        "schema_version": "p8_2_k1a_r5_l1_mtp_queue_health_v1",
        "request_count": len(request_rows),
        "spec_activity_ok_all": bool(request_rows)
        and all(row.get("spec_activity_ok") is True for row in request_rows),
        "accepted_token_delta_positive_all": bool(request_rows)
        and all(
            float(row.get("accepted_token_delta") or 0) > 0
            for row in request_rows
        ),
        "queue_metrics_ok_all": bool(request_rows)
        and all(row.get("queue_metrics_ok") is True for row in request_rows),
        "counter_continuity_ok_all": bool(request_rows)
        and all(
            row.get("counter_continuity_ok") is True for row in request_rows
        ),
    }
    if not successful_count:
        grade = "red_p8_2_k1a_r5_l1_lazy_h2d_no_success"
    elif timeline.get("terminal_decision") == "cpu_target_lost":
        grade = "red_p8_2_k1a_r5_l1_cpu_target_lost"
    elif timeline.get("terminal_decision") == "trigger_not_reached":
        grade = "yellow_p8_2_k1a_r5_l1_trigger_not_reached"
    elif not all(
        (
            request_evidence_exact,
            restore_sent_after_trigger_only,
            connector_ok,
            repair_ok,
            host_ok,
            recovery_ok,
            mechanism_ok,
            cleanup == "clean",
        )
    ):
        grade = "red_p8_2_k1a_r5_l1_h2d_evidence_incomplete"
    else:
        grade = "candidate_green_p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle"

    grading = {
        "schema_version": "p8_2_k1a_r5_l1_grading_v1",
        "server_grade": grade,
        "successful_request_count": successful_count,
        "request_count": len(request_rows),
        "request_evidence_exact": request_evidence_exact,
        "pressure_request_count_executed": pressure_count,
        "pressure_request_count_is_runtime_fact": True,
        "restore_sent_after_trigger_only": restore_sent_after_trigger_only,
        "target_gpu_eviction_observed": trigger_summary[
            "target_gpu_eviction_observed"
        ],
        "target_cpu_only_residency_observed": trigger_summary[
            "target_cpu_only_residency_observed"
        ],
        "h2d_worker_completion_exact": trigger_summary[
            "h2d_worker_completion_exact"
        ],
        "h2d_restore_mechanism_candidate": mechanism_ok,
        "resolved_connector_and_lazy_mode_exact": connector_ok,
        "repair_diagnostic_ok": repair_ok,
        "host_memory_gate_ok": host_ok,
        "resource_recovery_exact": recovery_ok,
        "cleanup": cleanup,
        "actual_cpu_eviction_proven": False,
        "cause_proven_as_unique": False,
        "performance_reference_accepted": False,
        "k2_authorized": False,
        "p8_3_i1_authorized": False,
        "next_task_authorized": False,
        "developer_review_required": True,
        "claim_boundary": (
            "accepted_capacity_single_lazy_lifecycle_cpu_only_trigger_and_"
            "d2h_h2d_mechanism_candidate_only"
        ),
    }
    _write_request_summary(artifact_dir / "request_summary.tsv", request_rows)
    _write_json(artifact_dir / "residency_gate_timeline.json", timeline)
    _write_json(artifact_dir / "h2d_trigger_summary.json", trigger_summary)
    _write_json(artifact_dir / "transfer_trace_summary.json", transfer_summary)
    _write_json(
        artifact_dir / "mtp_queue_health_summary.json", mtp_queue_health
    )
    _write_json(artifact_dir / "grading_summary.json", grading)
    (artifact_dir / "result_summary.md").write_text(
        "# P8.2-K1A-R5-L1 lazy H2D trigger lifecycle\n\n"
        f"- grade: `{grade}`\n"
        f"- requests: `{successful_count}/{len(request_rows)}`\n"
        f"- pressure requests executed: `{pressure_count}`\n"
        "- claim: one accepted-capacity lazy D2H/H2D mechanism candidate only.\n"
        "- no performance, unique-cause, K2, or P8.3-I1 claim.\n",
        encoding="utf-8",
    )
    manifest = _build_candidate_manifest(artifact_dir)
    manifest_path = artifact_dir / "candidate_manifest.server_local.json"
    _write_json(manifest_path, manifest)
    transfer_total_bytes = (
        manifest["candidate_total_bytes"] + manifest_path.stat().st_size
    )
    bounded = all(
        (
            manifest["payload_file_count"] <= 15,
            manifest["transfer_file_count_including_manifest"] <= 16,
            transfer_total_bytes <= 71680,
        )
    )
    return 0 if grade.startswith("candidate_green_") and bounded else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    decide = subparsers.add_parser("decide-next")
    decide.add_argument("--gate", type=Path, required=True)
    decide.add_argument("--pressure-count", type=int, required=True)
    decide.add_argument("--output", type=Path, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    execute = subparsers.add_parser("execute")
    execute.add_argument("--artifact-dir", type=Path, required=True)
    execute.add_argument("--base-url", required=True)
    execute.add_argument("--server-pid", type=int, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "prepare":
        prepare_lazy_h2d_artifacts(
            args.source_payload,
            args.artifact_dir,
            args.model_name,
        )
        return 0
    if args.command == "decide-next":
        value, exit_code = decide_next_action(
            json.loads(args.gate.read_text(encoding="utf-8")),
            pressure_count=args.pressure_count,
        )
        _write_json(args.output, value)
        return exit_code
    if args.command == "finalize":
        return finalize_lazy_h2d_artifacts(args.artifact_dir)
    if args.command == "execute":
        return execute_lazy_h2d_lifecycle(
            args.artifact_dir, args.base_url, args.server_pid
        )
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
