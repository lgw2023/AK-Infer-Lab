from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.inference_contracts.p8_2_k1a_h2d_residency_observer import (
    build_restore_eligibility_gate,
    build_residency_gate,
    summarize_h2d_trigger_rows,
    summarize_target_store_lineage_rows,
)
from tools.inference_contracts.p8_2_k1a_simple_cpu_offload_observer import (
    summarize_trace_rows,
)
from tools.inference_contracts.run_deepseek_p6_1_unprofiled_baseline import (
    calculate_request_metrics,
)
from tools.inference_contracts.run_deepseek_p6_3b_prefix_cache_ab import (
    _get,
    _process_alive,
    _wait_for_idle,
    _write_jsonl,
)
from tools.inference_contracts.run_deepseek_p8_2_k1a_r5_l1_lazy_h2d import (
    BLOCK_SIZE_TOKENS,
    OUTPUT_TOKENS,
    RESTORE_MATCH_TOKENS,
    TARGET_PREFIX_BLOCKS,
    _execute_one_request,
    _read_json,
    _read_jsonl,
    _read_trace_rows,
    _request_evidence_exact,
    _write_active_role,
    _write_json,
    prepare_lazy_h2d_artifacts,
)
from tools.inference_contracts import (
    run_deepseek_p8_2_k1a_r5_l1_lazy_h2d as lazy_h2d_runner,
)


TASK_ID = os.environ.get(
    "P8_2_K1A_TASK_ID",
    "p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722",
)
STAGE_LABEL = os.environ.get("P8_2_K1A_STAGE_LABEL", "P8.2-K1A-R5-F1-R3")
CONTRACT_SCHEMA_TAG = os.environ.get(
    "P8_2_K1A_F1_SCHEMA_TAG", "p8_2_k1a_r5_f1_r3"
)
GRADE_PREFIX = os.environ.get(
    "P8_2_K1A_F1_GRADE_PREFIX", "red_p8_2_k1a_r5_f1_r3"
)
ELIGIBILITY_TARGET_BLOCKS = int(
    os.environ.get("P8_2_K1A_H2D_TARGET_BLOCK_COUNT", str(TARGET_PREFIX_BLOCKS))
)
REQUIRE_RESTORE_GROUP_ELIGIBILITY = (
    os.environ.get("P8_2_K1A_REQUIRE_RESTORE_GROUP_ELIGIBILITY", "0") == "1"
)
STOP_ON_FIRST_CPU_TARGET_EVICTION = (
    os.environ.get("P8_2_K1A_STOP_ON_FIRST_CPU_TARGET_EVICTION", "1") == "1"
)
ALLOW_INFLIGHT_KEYSPACE_REFRESH = (
    os.environ.get(
        "P8_2_K1A_ALLOW_PRESSURE_BEFORE_KEYSPACE_EXACT", "0"
    )
    == "1"
)
REQUIRE_POST_ABORT_FRESH_REVALIDATION = (
    os.environ.get("P8_2_K1A_REQUIRE_POST_ABORT_FRESH_REVALIDATION", "0")
    == "1"
)
REQUIRE_EFFECTIVE_GROUP_GEOMETRY = (
    os.environ.get("P8_2_K1A_REQUIRE_EFFECTIVE_GROUP_GEOMETRY", "0") == "1"
)
PRESSURE_CONTEXT_TOKENS = 36800
PRESSURE_ROLE = "pressure_01"
TRIGGER_POLL_SECONDS = float(
    os.environ.get("P8_2_K1A_INFLIGHT_TRIGGER_POLL_SECONDS", "0.02")
)
TRIGGER_TIMEOUT_SECONDS = float(
    os.environ.get("P8_2_K1A_INFLIGHT_TRIGGER_TIMEOUT_SECONDS", "120")
)
ABORT_JOIN_TIMEOUT_SECONDS = float(
    os.environ.get("P8_2_K1A_PRESSURE_ABORT_JOIN_TIMEOUT_SECONDS", "30")
)
IDLE_TIMEOUT_SECONDS = float(
    os.environ.get("P8_2_K1A_PRESSURE_ABORT_IDLE_TIMEOUT_SECONDS", "60")
)
CANDIDATE_GREEN = os.environ.get(
    "P8_2_K1A_CANDIDATE_GREEN",
    "candidate_green_p8_2_k1a_r5_f1_r3_inflight_abort_restore",
)
LOGICAL_KEYSPACE_DIAGNOSTICS = (
    os.environ.get("P8_2_K1A_LOGICAL_KEYSPACE_DIAGNOSTICS", "0") == "1"
)
TARGET_STORE_LINEAGE_DIAGNOSTICS = (
    os.environ.get("P8_2_K1A_TARGET_STORE_LINEAGE_DIAGNOSTICS", "0")
    == "1"
)
REQUIRE_TARGET_STORE_LINEAGE = (
    os.environ.get("P8_2_K1A_REQUIRE_TARGET_STORE_LINEAGE", "0") == "1"
)
REQUIRE_LOGICAL_RESTORE_WINDOW = (
    os.environ.get(
        "P8_2_K1A_REQUIRE_LOGICAL_RESTORE_WINDOW_FOR_RESTORE", "0"
    )
    == "1"
)
RESULT_SUMMARY_TITLE = os.environ.get(
    "P8_2_K1A_RESULT_SUMMARY_TITLE",
    "request-local pressure and conditional restore",
)
CLAIM_BOUNDARY = os.environ.get(
    "P8_2_K1A_CLAIM_BOUNDARY",
    (
        "accepted_capacity_single_lifecycle_inflight_trigger_abort_idle_and_"
        "conditional_restore_h2d_mechanism_candidate_only"
    ),
)

BOUNDED_CANDIDATE_FILES = (
    "result_summary.md",
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
) + (
    ("logical_keyspace_probe_diagnostic_summary.json",)
    if LOGICAL_KEYSPACE_DIAGNOSTICS
    else ()
) + (
    ("target_store_lineage_summary.json",)
    if TARGET_STORE_LINEAGE_DIAGNOSTICS
    else ()
)


def _sanitized_trigger(row: dict[str, Any]) -> dict[str, Any]:
    value = {
        "timestamp_ns": int(row.get("timestamp_ns") or 0),
        "contract_role": str(row.get("contract_role") or ""),
        "scheduled_request_count": int(row.get("scheduled_request_count") or 0),
        "request_local_progress_exact": row.get("request_local_progress_exact")
        is True,
        "num_computed_tokens_before_schedule": row.get(
            "num_computed_tokens_before_schedule"
        ),
        "num_scheduled_tokens": row.get("num_scheduled_tokens"),
        "num_computed_tokens_after_schedule": row.get(
            "num_computed_tokens_after_schedule"
        ),
        "target_block_count": int(row.get("target_block_count") or 0),
        "cpu_target_block_count": int(row.get("cpu_target_block_count") or 0),
        "gpu_target_block_count": int(row.get("gpu_target_block_count") or 0),
        "raw_hash_values_retained": False,
        "request_id_retained": False,
        "token_ids_retained": False,
        "generated_content_retained": False,
    }
    for field in (
        "configured_target_block_count",
        "request_hash_candidate_count",
        "fa_group_hash_candidate_count",
        "selected_target_hash_count",
        "logical_restore_match_tokens",
        "raw_logical_restore_match_tokens",
        "legacy_capped_logical_restore_match_tokens",
        "logical_lookup_probe_horizon_tokens",
        "logical_lookup_lookahead_tokens",
        "eagle_lookahead_delta_tokens",
        "eagle_lookahead_required_tokens",
        "target_pool_key_count",
        "cpu_target_pool_key_match_count",
        "gpu_target_pool_key_match_count",
        "coordinator_returned_pool_key_count",
        "coordinator_cpu_pool_key_match_count",
        "coordinator_gpu_pool_key_match_count",
        "target_store_key_count",
        "target_store_scheduled_key_count",
        "target_store_completed_key_count",
        "target_cpu_evicted_key_count",
        "target_gpu_evicted_key_count",
        "target_fa_group_index",
        "target_fa_key_count",
        "target_fa_required_physical_key_count",
        "target_logical_block_count",
        "target_logical_coverage_tokens",
        "target_fa_store_scheduled_key_count",
        "target_fa_store_completed_key_count",
        "target_fa_cpu_evicted_key_count",
        "target_fa_gpu_evicted_key_count",
        "logical_lookup_first_reduction_attention_group_index",
        "logical_lookup_first_zero_attention_group_index",
    ):
        if field in row:
            value[field] = int(row.get(field) or 0)
    if "target_capture_source" in row:
        value["target_capture_source"] = str(row["target_capture_source"])
    if "logical_probe_source" in row:
        value["logical_probe_source"] = str(row["logical_probe_source"])
    if "logical_lookup_horizon_basis" in row:
        value["logical_lookup_horizon_basis"] = str(
            row["logical_lookup_horizon_basis"]
        )
    if "target_capture_exact" in row:
        value["target_capture_exact"] = row.get("target_capture_exact") is True
    for field in (
        "target_capture_cardinality_exact",
        "target_keyspace_matchable",
        "logical_restore_window_exact",
        "legacy_capped_logical_restore_window_exact",
        "legacy_capped_false_negative_candidate",
        "eagle_aware_logical_lookup_enabled",
        "logical_lookup_group_lineage_observable",
        "cpu_coordinator_use_eagle",
        "eagle_lookahead_sufficient",
        "target_store_lineage_capture_exact",
        "target_fa_capture_exact",
        "target_logical_coverage_exact",
        "physical_target_window_exact",
    ):
        if field in row:
            value[field] = row.get(field) is True
    for field in (
        "target_count_unit",
        "cpu_target_count_unit",
        "gpu_target_count_unit",
        "target_pool_key_count_unit",
        "logical_lookup_first_reduction_spec_type",
        "logical_lookup_first_zero_spec_type",
    ):
        if field in row:
            value[field] = str(row[field])
    if "logical_lookup_iteration_rows" in row:
        bounded_lookup_rows = []
        for lookup in row.get("logical_lookup_iteration_rows") or ():
            bounded = {
                field: int(lookup.get(field) or 0)
                for field in (
                    "lookup_iteration_index",
                    "attention_group_index",
                    "candidate_in_tokens",
                    "manager_max_length_tokens",
                    "base_block_size_tokens",
                    "effective_block_size_tokens",
                    "alignment_tokens",
                    "eagle_lookahead_delta_tokens",
                    "eagle_lookahead_required_tokens",
                    "eagle_inner_readable_blocks",
                    "returned_block_count",
                    "returned_hit_tokens",
                )
                if field in lookup
            }
            for field in (
                "use_eagle",
                "eagle_lookahead_requested",
                "eagle_lookahead_suppressed_by_horizon",
                "eagle_lookahead_sufficient",
                "candidate_reduced",
            ):
                if field in lookup:
                    bounded[field] = lookup.get(field) is True
            if "kv_cache_spec_type" in lookup:
                bounded["kv_cache_spec_type"] = str(lookup["kv_cache_spec_type"])
            if "manager_type" in lookup:
                bounded["manager_type"] = str(lookup["manager_type"])
            bounded["raw_hash_values_retained"] = False
            bounded_lookup_rows.append(bounded)
        value["logical_lookup_iteration_rows"] = bounded_lookup_rows
    if "logical_lookup_group_contract_rows" in row:
        bounded_contract_rows = []
        for group in row.get("logical_lookup_group_contract_rows") or ():
            bounded = {
                field: int(group.get(field) or 0)
                for field in (
                    "attention_group_index",
                    "base_block_size_tokens",
                    "effective_block_size_tokens",
                )
                if field in group
            }
            if "kv_cache_spec_type" in group:
                bounded["kv_cache_spec_type"] = str(group["kv_cache_spec_type"])
            if "coordinator_use_eagle" in group:
                bounded["coordinator_use_eagle"] = (
                    group.get("coordinator_use_eagle") is True
                )
            bounded["raw_hash_values_retained"] = False
            bounded_contract_rows.append(bounded)
        value["logical_lookup_group_contract_rows"] = bounded_contract_rows
    if "restore_group_count" in row:
        value.update(
            {
                "restore_group_count": int(
                    row.get("restore_group_count") or 0
                ),
                "restore_group_applicable_count": int(
                    row.get("restore_group_applicable_count") or 0
                ),
                "restore_groups_captured_exact_count": int(
                    row.get("restore_groups_captured_exact_count") or 0
                ),
                "restore_groups_captured_exact": row.get(
                    "restore_groups_captured_exact"
                ) is True,
                "restore_groups_cpu_complete_count": int(
                    row.get("restore_groups_cpu_complete_count") or 0
                ),
                "restore_groups_gpu_absent_count": int(
                    row.get("restore_groups_gpu_absent_count") or 0
                ),
                "restore_group_eligibility_complete": row.get(
                    "restore_group_eligibility_complete"
                ) is True,
            }
        )
        bounded_group_rows = []
        integer_fields = (
            "group_index",
            "restore_match_tokens_required",
            "effective_block_size_tokens",
            "base_block_size_tokens",
            "cp_world_size",
            "compress_ratio",
            "physical_key_count_required",
            "theoretical_block_count",
            "provided_block_id_count",
            "selected_block_id_count",
            "non_null_block_count",
            "hashable_block_count",
            "unhashable_non_null_block_count",
            "required_block_count",
            "captured_block_count",
            "cpu_block_count",
            "gpu_block_count",
        )
        for group in row.get("restore_group_rows") or ():
            bounded = {
                field: int(group.get(field) or 0)
                for field in integer_fields
                if field in group
            }
            if "capture_basis" in group:
                bounded["capture_basis"] = str(group["capture_basis"])
            for field in (
                "group_applicable",
                "capture_exact",
                "selected_geometry_exact",
                "hash_capture_exact",
                "cpu_complete",
                "gpu_absent",
            ):
                if field in group:
                    bounded[field] = group.get(field) is True
            bounded.update(
                {
                    "raw_block_ids_retained": False,
                    "raw_hash_values_retained": False,
                }
            )
            bounded_group_rows.append(bounded)
        if bounded_group_rows:
            value["restore_group_rows"] = bounded_group_rows
    return value


def build_inflight_trigger_state(
    rows: list[dict[str, Any]],
    *,
    pressure_start_timestamp_ns: int,
    target_block_count: int | None = None,
    require_restore_group_eligibility: bool | None = None,
    stop_on_first_cpu_target_eviction: bool | None = None,
    require_effective_group_geometry: bool | None = None,
) -> dict[str, Any]:
    required_blocks = (
        ELIGIBILITY_TARGET_BLOCKS
        if target_block_count is None
        else target_block_count
    )
    require_groups = (
        REQUIRE_RESTORE_GROUP_ELIGIBILITY
        if require_restore_group_eligibility is None
        else require_restore_group_eligibility
    )
    stop_on_eviction = (
        STOP_ON_FIRST_CPU_TARGET_EVICTION
        if stop_on_first_cpu_target_eviction is None
        else stop_on_first_cpu_target_eviction
    )
    require_runtime_geometry = (
        REQUIRE_EFFECTIVE_GROUP_GEOMETRY
        if require_effective_group_geometry is None
        else require_effective_group_geometry
    )
    current = [
        row
        for row in rows
        if int(row.get("timestamp_ns") or 0) >= pressure_start_timestamp_ns
    ]
    pressure_progress = [
        row
        for row in current
        if row.get("event") == "request_local_pressure_progress"
        and row.get("contract_role") == PRESSURE_ROLE
    ]
    ambiguous = [
        row
        for row in pressure_progress
        if row.get("request_local_progress_exact") is not True
        or int(row.get("scheduled_request_count") or 0) != 1
    ]
    cpu_evictions = [
        row
        for row in current
        if row.get("event") == "target_cache_evicted"
        and row.get("tier") == "cpu"
        and int(row.get("target_evicted_count") or 0) > 0
    ]
    exact_cpu_only = [
        row
        for row in pressure_progress
        if row.get("request_local_progress_exact") is True
        and int(row.get("scheduled_request_count") or 0) == 1
        and int(row.get("target_block_count") or 0) == required_blocks
        and (
            (
                require_runtime_geometry
                and row.get("target_logical_coverage_exact") is True
                and row.get("physical_target_window_exact") is True
            )
            or (
                not require_runtime_geometry
                and int(row.get("cpu_target_block_count") or 0)
                == required_blocks
                and int(row.get("gpu_target_block_count") or 0) == 0
            )
        )
        and (
            "target_capture_exact" not in row
            or row.get("target_capture_exact") is True
        )
        and (
            "target_keyspace_matchable" not in row
            or row.get("target_keyspace_matchable") is True
        )
        and (
            not require_groups
            or row.get("restore_group_eligibility_complete") is True
        )
    ]
    best_near_miss = (
        max(
            pressure_progress,
            key=lambda row: (
                int(row.get("restore_groups_cpu_complete_count") or 0),
                int(row.get("cpu_target_block_count") or 0),
                -int(row.get("gpu_target_block_count") or 0),
                int(row.get("timestamp_ns") or 0),
            ),
        )
        if pressure_progress
        else None
    )

    if ambiguous:
        decision = "request_local_progress_ambiguous"
    elif cpu_evictions and stop_on_eviction:
        decision = "cpu_target_lost"
    elif exact_cpu_only:
        decision = "trigger_ready"
    else:
        decision = "continue_pressure"

    trigger = _sanitized_trigger(exact_cpu_only[0]) if exact_cpu_only else None
    return {
        "schema_version": f"{CONTRACT_SCHEMA_TAG}_inflight_trigger_state_v1",
        "decision": decision,
        "abort_allowed": decision == "trigger_ready",
        "pressure_start_timestamp_ns": pressure_start_timestamp_ns,
        "pressure_progress_event_count": len(pressure_progress),
        "ambiguous_progress_event_count": len(ambiguous),
        "cpu_target_eviction_event_count": len(cpu_evictions),
        "exact_cpu_only_progress_event_count": len(exact_cpu_only),
        "effective_group_geometry_required": require_runtime_geometry,
        "trigger": trigger,
        "best_restore_eligibility_near_miss": (
            _sanitized_trigger(best_near_miss) if best_near_miss else None
        ),
        "raw_hash_values_retained": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
        "generated_content_retained": False,
    }


@dataclass
class AbortableRequestHandle:
    abort_event: threading.Event = field(default_factory=threading.Event)
    finished_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    connection: http.client.HTTPConnection | None = None
    response: http.client.HTTPResponse | None = None
    row: dict[str, Any] | None = None
    abort_requested_monotonic_ns: int | None = None

    def bind_connection(self, connection: http.client.HTTPConnection) -> None:
        with self.lock:
            self.connection = connection

    def bind_response(self, response: http.client.HTTPResponse) -> None:
        with self.lock:
            self.response = response

    def abort(self) -> None:
        self.abort_requested_monotonic_ns = time.monotonic_ns()
        self.abort_event.set()
        with self.lock:
            connection = self.connection
            response = self.response
        sock = connection.sock if connection is not None else None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if response is not None:
            try:
                response.close()
            except OSError:
                pass
        if connection is not None:
            connection.close()


def _stream_abortable_request(
    *,
    handle: AbortableRequestHandle,
    artifact_dir: Path,
    base_url: str,
    server_pid: int,
    batch: dict[str, Any],
    request_item: dict[str, Any],
) -> None:
    body_path = artifact_dir / str(request_item["body_relative_path"])
    body = body_path.read_bytes()
    body_sha256 = hashlib.sha256(body).hexdigest()
    expected_hash = str(request_item["request_body_sha256"])
    payload = json.loads(body)
    expected_prompt = int(batch["context_tokens"])
    expected_output = int(batch["output_tokens"])
    if body_sha256 != expected_hash:
        raise ValueError(f"body hash drift for {request_item['request_id']}")
    if len(payload["prompt"]) != expected_prompt:
        raise ValueError(f"prompt length drift for {request_item['request_id']}")

    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError("abortable controller requires an explicit http base URL")
    connection = http.client.HTTPConnection(
        parsed.hostname,
        parsed.port or 80,
        timeout=7200,
    )
    handle.bind_connection(connection)
    token_arrival_ns: list[int] = []
    usage: dict[str, Any] = {}
    finish_reason: str | None = None
    saw_done = False
    http_status: int | None = None
    max_token_chunk_width = 0
    unexpected_error: str | None = None
    request_start_ns = time.monotonic_ns()
    request_start_timestamp_ns = time.time_ns()
    try:
        endpoint = (parsed.path.rstrip("/") if parsed.path else "") + "/v1/completions"
        connection.request(
            "POST",
            endpoint,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )
        response = connection.getresponse()
        handle.bind_response(response)
        http_status = int(response.status)
        while True:
            raw_line = response.readline()
            if not raw_line:
                break
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
    except Exception as error:  # the expected socket shutdown also arrives here
        if not handle.abort_event.is_set():
            unexpected_error = f"{type(error).__name__}: {str(error)[:2048]}"
    finally:
        connection.close()

    request_end_ns = time.monotonic_ns()
    generated_tokens = usage.get("completion_tokens")
    aborted_on_trigger = all(
        (
            handle.abort_event.is_set(),
            not saw_done,
            generated_tokens != expected_output,
            len(token_arrival_ns) != expected_output,
        )
    )
    if unexpected_error is not None:
        error_path = (
            artifact_dir
            / "request_errors"
            / f"{request_item['request_id']}.txt"
        )
        error_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.write_text(unexpected_error + "\n", encoding="utf-8")
    else:
        error_path = None
    status = (
        "aborted_on_trigger"
        if aborted_on_trigger
        else "success"
        if all(
            (
                http_status == 200,
                usage.get("prompt_tokens") == expected_prompt,
                generated_tokens == expected_output,
                len(token_arrival_ns) == expected_output,
                finish_reason == "length",
                saw_done,
            )
        )
        else "failed"
    )
    handle.row = {
        "request_id": request_item["request_id"],
        "batch_id": batch["batch_id"],
        "phase": batch["phase"],
        "k1a_role": request_item["k1a_role"],
        "group_id": request_item["group_id"],
        "context_tokens": expected_prompt,
        "output_tokens": expected_output,
        "concurrency": 1,
        "repeat_index": int(request_item["repeat_index"]),
        "request_index": 1,
        "request_body_sha256": body_sha256,
        "status": status,
        "http_status": http_status,
        "prompt_tokens": usage.get("prompt_tokens"),
        "generated_token_count": generated_tokens,
        "streamed_token_count": len(token_arrival_ns),
        "finish_reason": finish_reason,
        "saw_done": saw_done,
        "max_token_chunk_width": max_token_chunk_width,
        "request_start_ns": request_start_ns,
        "request_start_timestamp_ns": request_start_timestamp_ns,
        "request_end_ns": request_end_ns,
        "abort_requested": handle.abort_event.is_set(),
        "abort_requested_monotonic_ns": handle.abort_requested_monotonic_ns,
        "abort_confirmed_by_client_exit": aborted_on_trigger,
        "full_response_observed": saw_done,
        "server_alive_after_client_exit": _process_alive(server_pid),
        **calculate_request_metrics(
            request_start_ns=request_start_ns,
            token_arrival_ns=token_arrival_ns,
            request_end_ns=request_end_ns,
        ),
        "bounded_error_server_path": str(error_path) if error_path else None,
        "generated_text_retained": False,
        "token_ids_retained": False,
    }
    handle.finished_event.set()


def _counter_delta(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, float]:
    return {
        name: float(after.get(name) or 0.0) - float(before.get(name) or 0.0)
        for name in (
            "prefix_queries",
            "prefix_hits",
            "num_drafts",
            "num_draft_tokens",
            "num_accepted_tokens",
        )
    }


def _finish_pressure_row(
    *,
    handle: AbortableRequestHandle,
    base_url: str,
    control_dir: Path,
    item: dict[str, Any],
    metrics_before: dict[str, Any],
    previous_after: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    row = dict(handle.row or {**item, "status": "client_thread_missing_result"})
    health_after, _ = _get(base_url, "/health", timeout=5)
    idle_after, metrics_after = _wait_for_idle(
        base_url,
        control_dir / "raw_metrics" / f"{item['request_id']}_after.prom",
        timeout_seconds=IDLE_TIMEOUT_SECONDS,
    )
    delta = _counter_delta(metrics_before, metrics_after)
    continuity_ok = previous_after is None or all(
        float(metrics_before.get(name) or 0.0)
        >= float(previous_after.get(name) or 0.0)
        for name in delta
    )
    queue_ok = all(
        (
            metrics_before.get("queue_metrics_present") is True,
            metrics_after.get("queue_metrics_present") is True,
            idle_after,
        )
    )
    row.update(
        {
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "prefix_hits_delta": delta["prefix_hits"],
            "accepted_token_delta": delta["num_accepted_tokens"],
            "queue_metrics_ok": queue_ok,
            "counter_continuity_ok": continuity_ok,
            "spec_activity_ok": delta["num_drafts"] >= 0,
            "prefix_evidence_ok": delta["prefix_queries"] >= 0,
            "health_after_200": health_after == 200,
            "queue_idle_after_abort": idle_after,
        }
    )
    return row, metrics_after, idle_after


def prepare_inflight_abort_restore_artifacts(
    source_payload: Path, artifact_dir: Path, model_name: str
) -> dict[str, Any]:
    previous_context = lazy_h2d_runner.PRESSURE_CONTEXT_TOKENS
    previous_count = lazy_h2d_runner.PRESSURE_REQUEST_COUNT_MAX
    lazy_h2d_runner.PRESSURE_CONTEXT_TOKENS = PRESSURE_CONTEXT_TOKENS
    lazy_h2d_runner.PRESSURE_REQUEST_COUNT_MAX = 1
    try:
        manifest = prepare_lazy_h2d_artifacts(
            source_payload, artifact_dir, model_name
        )
    finally:
        lazy_h2d_runner.PRESSURE_CONTEXT_TOKENS = previous_context
        lazy_h2d_runner.PRESSURE_REQUEST_COUNT_MAX = previous_count
    if int(manifest["pressure_request_count_max"]) != 1:
        raise ValueError(f"{STAGE_LABEL} requires exactly one pressure request")
    if int(manifest["pressure_context_tokens"]) != PRESSURE_CONTEXT_TOKENS:
        raise ValueError(f"{STAGE_LABEL} pressure context must remain fixed at 36800")
    manifest.update(
        {
            "schema_version": f"{CONTRACT_SCHEMA_TAG}_request_body_manifest_v1",
            "task_id": TASK_ID,
            "fixed_request_count": 4,
            "request_count_max": 4,
            "request_order_contract": [
                "warmup",
                "target_prime",
                "pressure_01_abort_on_request_local_cpu_only_trigger",
                "restore_follower_after_abort_and_idle_if_window_still_valid",
            ],
            "pressure_request_count_is_runtime_fact": True,
            "pressure_request_abort_is_conditional": True,
            "pressure_request_must_not_complete_before_abort": True,
            "restore_requires_abort_confirmed_idle_and_window_still_valid": True,
            "target_prefix_tokens": (
                ELIGIBILITY_TARGET_BLOCKS * BLOCK_SIZE_TOKENS
            ),
            "target_prefix_blocks": ELIGIBILITY_TARGET_BLOCKS,
            "restore_group_eligibility_required": (
                REQUIRE_RESTORE_GROUP_ELIGIBILITY
            ),
            "legacy_64_block_subset_authorizes_restore": (
                ELIGIBILITY_TARGET_BLOCKS == 64
                and not REQUIRE_RESTORE_GROUP_ELIGIBILITY
            ),
        }
    )
    (artifact_dir / "request_body_manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_pre_pressure_admission(
    rows: list[dict[str, Any]],
    *,
    d2h_store_complete: bool,
    target_block_count: int,
    allow_inflight_keyspace_refresh: bool,
    require_target_store_lineage: bool = False,
    require_effective_group_geometry: bool = False,
) -> dict[str, Any]:
    candidates = [
        row
        for row in rows
        if row.get("event")
        in {"target_hashes_captured", "target_residency_snapshot"}
        and int(row.get("target_block_count") or 0) == target_block_count
    ]
    latest = candidates[-1] if candidates else {}
    request_hash_candidate_count = int(
        latest.get("request_hash_candidate_count") or 0
    )
    cardinality_exact = (
        latest.get("target_capture_cardinality_exact") is True
        and request_hash_candidate_count == target_block_count
    )
    keyspace_matchable = latest.get("target_keyspace_matchable") is True
    capture_exact = latest.get("target_capture_exact") is True
    target_store_lineage_capture_exact = (
        latest.get("target_store_lineage_capture_exact") is True
    )
    target_fa_key_count = int(latest.get("target_fa_key_count") or 0)
    target_store_key_count = int(
        latest.get("target_store_key_count") or 0
    )
    target_fa_required_physical_key_count = int(
        latest.get("target_fa_required_physical_key_count") or 0
    )
    target_logical_coverage_exact = (
        latest.get("target_logical_coverage_exact") is True
    )
    if not d2h_store_complete:
        decision = "d2h_store_incomplete_before_pressure"
    elif not cardinality_exact:
        decision = "target_candidates_unobservable_before_pressure"
    elif require_target_store_lineage and not all(
        (
            target_store_lineage_capture_exact,
            (
                target_logical_coverage_exact
                and target_fa_required_physical_key_count > 0
                and target_fa_key_count
                == target_fa_required_physical_key_count
                if require_effective_group_geometry
                else target_fa_key_count == target_block_count
            ),
            target_store_key_count > 0,
        )
    ):
        decision = "target_store_lineage_unobservable_before_pressure"
    elif capture_exact and keyspace_matchable:
        decision = "target_keyspace_exact_before_pressure"
    elif allow_inflight_keyspace_refresh:
        decision = "pressure_admitted_for_inflight_refresh"
    else:
        decision = "target_keyspace_unobservable_before_pressure"
    return {
        "decision": decision,
        "pressure_allowed": decision
        in {
            "target_keyspace_exact_before_pressure",
            "pressure_admitted_for_inflight_refresh",
        },
        "d2h_store_complete_before_pressure": d2h_store_complete,
        "request_hash_candidate_count": request_hash_candidate_count,
        "target_capture_cardinality_exact": cardinality_exact,
        "target_keyspace_matchable": keyspace_matchable,
        "target_capture_exact": capture_exact,
        "target_store_lineage_required": require_target_store_lineage,
        "target_store_lineage_capture_exact": (
            target_store_lineage_capture_exact
        ),
        "target_fa_key_count": target_fa_key_count,
        "target_fa_required_physical_key_count": (
            target_fa_required_physical_key_count
        ),
        "target_logical_coverage_exact": target_logical_coverage_exact,
        "effective_group_geometry_required": (
            require_effective_group_geometry
        ),
        "target_store_key_count": target_store_key_count,
        "target_pool_key_count": int(latest.get("target_pool_key_count") or 0),
        "cpu_target_pool_key_match_count": int(
            latest.get("cpu_target_pool_key_match_count") or 0
        ),
        "gpu_target_pool_key_match_count": int(
            latest.get("gpu_target_pool_key_match_count") or 0
        ),
        "allow_inflight_keyspace_refresh": allow_inflight_keyspace_refresh,
        "raw_hash_values_retained": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
        "generated_content_retained": False,
    }


def summarize_logical_keyspace_probe_diagnostics(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    probes = [
        row
        for row in rows
        if (
            row.get("logical_probe_source")
            == "runtime_cpu_coordinator_longest_hit"
            or (
                "logical_probe_source" not in row
                and row.get("target_capture_source")
                == "runtime_cpu_coordinator_longest_hit"
            )
        )
        and row.get("event")
        in {
            "target_hashes_captured",
            "target_residency_snapshot",
            "request_local_pressure_progress",
        }
    ]

    def histogram(values: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            if value:
                counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items()))

    def maximum(field: str, selected: list[dict[str, Any]] = probes) -> int:
        return max((int(row.get(field) or 0) for row in selected), default=0)

    def stage_name(row: dict[str, Any]) -> str:
        return str(
            row.get("contract_role")
            or row.get("logical_keyspace_probe_reason")
            or row.get("reason")
            or row.get("event")
            or "unknown"
        )

    stage_names: list[str] = []
    for row in probes:
        name = stage_name(row)
        if name not in stage_names:
            stage_names.append(name)
    stage_rows = []
    for name in stage_names:
        selected = [row for row in probes if stage_name(row) == name]
        timestamps = [int(row.get("timestamp_ns") or 0) for row in selected]
        exact_count = sum(row.get("target_capture_exact") is True for row in selected)
        stage_rows.append(
            {
                "stage": name,
                "probe_event_count": len(selected),
                "exact_probe_event_count": exact_count,
                "near_miss_probe_event_count": len(selected) - exact_count,
                "logical_restore_match_tokens_max": maximum(
                    "logical_restore_match_tokens", selected
                ),
                "raw_logical_restore_match_tokens_max": maximum(
                    "raw_logical_restore_match_tokens", selected
                ),
                "legacy_capped_logical_restore_match_tokens_max": maximum(
                    "legacy_capped_logical_restore_match_tokens", selected
                ),
                "logical_lookup_probe_horizon_tokens_max": maximum(
                    "logical_lookup_probe_horizon_tokens", selected
                ),
                "legacy_capped_false_negative_candidate_count": sum(
                    row.get("legacy_capped_false_negative_candidate") is True
                    for row in selected
                ),
                "target_pool_key_count_max": maximum(
                    "target_pool_key_count", selected
                ),
                "cpu_target_pool_key_match_count_max": maximum(
                    "cpu_target_pool_key_match_count", selected
                ),
                "gpu_target_pool_key_match_count_max": maximum(
                    "gpu_target_pool_key_match_count", selected
                ),
                "restore_group_count_max": maximum(
                    "restore_group_count", selected
                ),
                "first_probe_timestamp_ns": min(timestamps, default=0),
                "latest_probe_timestamp_ns": max(timestamps, default=0),
                "probe_error_type_histogram": histogram(
                    [
                        str(row.get("target_keyspace_probe_error_type") or "")
                        for row in selected
                    ]
                ),
                "raw_hash_values_retained": False,
            }
        )

    timestamps = [int(row.get("timestamp_ns") or 0) for row in probes]
    exact_timestamps = [
        int(row.get("timestamp_ns") or 0)
        for row in probes
        if row.get("target_capture_exact") is True
    ]
    error_types = [
        str(row.get("target_keyspace_probe_error_type") or "")
        for row in probes
        if row.get("target_keyspace_probe_error_type")
    ]
    reasons = [
        str(
            row.get("logical_keyspace_probe_reason")
            or row.get("reason")
            or row.get("event")
            or "unknown"
        )
        for row in probes
    ]
    exact_count = sum(row.get("target_capture_exact") is True for row in probes)
    gpu_counts = [
        int(row.get("gpu_target_pool_key_match_count") or 0) for row in probes
    ]
    best_probe = max(
        probes,
        key=lambda row: (
            int(row.get("logical_restore_match_tokens") or 0),
            int(row.get("timestamp_ns") or 0),
        ),
        default={},
    )
    return {
        "schema_version": (
            f"{CONTRACT_SCHEMA_TAG}_logical_keyspace_probe_diagnostic_v1"
        ),
        "probe_event_count": len(probes),
        "pressure_probe_event_count": sum(
            row.get("event") == "request_local_pressure_progress"
            for row in probes
        ),
        "exact_probe_event_count": exact_count,
        "near_miss_probe_event_count": len(probes) - exact_count,
        "probe_error_event_count": len(error_types),
        "probe_error_type_histogram": histogram(error_types),
        "probe_reason_histogram": histogram(reasons),
        "request_hash_candidate_count_max": maximum(
            "request_hash_candidate_count"
        ),
        "logical_restore_match_tokens_max": maximum(
            "logical_restore_match_tokens"
        ),
        "raw_logical_restore_match_tokens_max": maximum(
            "raw_logical_restore_match_tokens"
        ),
        "legacy_capped_logical_restore_match_tokens_max": maximum(
            "legacy_capped_logical_restore_match_tokens"
        ),
        "logical_lookup_probe_horizon_tokens_max": maximum(
            "logical_lookup_probe_horizon_tokens"
        ),
        "logical_lookup_lookahead_tokens_max": maximum(
            "logical_lookup_lookahead_tokens"
        ),
        "legacy_capped_false_negative_candidate_count": sum(
            row.get("legacy_capped_false_negative_candidate") is True
            for row in probes
        ),
        "group_lineage_observable_event_count": sum(
            row.get("logical_lookup_group_lineage_observable") is True
            for row in probes
        ),
        "best_probe_first_reduction_attention_group_index": int(
            best_probe.get(
                "logical_lookup_first_reduction_attention_group_index", -1
            )
        ),
        "best_probe_first_reduction_spec_type": best_probe.get(
            "logical_lookup_first_reduction_spec_type"
        ),
        "best_probe_first_zero_attention_group_index": int(
            best_probe.get(
                "logical_lookup_first_zero_attention_group_index", -1
            )
        ),
        "best_probe_first_zero_spec_type": best_probe.get(
            "logical_lookup_first_zero_spec_type"
        ),
        "best_probe_group_contract_rows": list(
            best_probe.get("logical_lookup_group_contract_rows", ()) or ()
        ),
        "best_probe_lookup_iteration_rows": list(
            best_probe.get("logical_lookup_iteration_rows", ()) or ()
        ),
        "target_pool_key_count_max": maximum("target_pool_key_count"),
        "cpu_target_pool_key_match_count_max": maximum(
            "cpu_target_pool_key_match_count"
        ),
        "gpu_target_pool_key_match_count_min": min(gpu_counts, default=0),
        "gpu_target_pool_key_match_count_max": max(gpu_counts, default=0),
        "restore_group_count_max": maximum("restore_group_count"),
        "first_probe_timestamp_ns": min(timestamps, default=0),
        "first_exact_probe_timestamp_ns": min(exact_timestamps, default=0),
        "latest_probe_timestamp_ns": max(timestamps, default=0),
        "stage_rows": stage_rows,
        "raw_hash_values_retained": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
        "generated_content_retained": False,
    }


def build_post_abort_revalidation_gate(
    rows: list[dict[str, Any]],
    *,
    abort_requested_timestamp_ns: int,
    required_restore_block_count: int,
    require_restore_group_eligibility: bool,
    require_logical_restore_window: bool = False,
    require_effective_group_geometry: bool = False,
) -> dict[str, Any]:
    fresh = [
        row
        for row in rows
        if int(row.get("timestamp_ns") or 0) >= abort_requested_timestamp_ns
        and row.get("event")
        in {"target_residency_snapshot", "request_local_pressure_progress"}
    ]
    if not fresh:
        return {
            "decision": "post_abort_revalidation_unobservable",
            "restore_allowed": False,
            "post_abort_candidate_event_count": 0,
            "post_abort_revalidation_fresh": False,
            "abort_requested_timestamp_ns": abort_requested_timestamp_ns,
            "raw_hash_values_retained": False,
        }
    gate = (
        build_restore_eligibility_gate(
            fresh,
            required_restore_block_count=required_restore_block_count,
            require_effective_group_geometry=(
                require_effective_group_geometry
            ),
        )
        if require_restore_group_eligibility
        else build_residency_gate(
            fresh, target_block_count=required_restore_block_count
        )
    )
    latest = fresh[-1]
    logical_exact = latest.get("logical_restore_window_exact") is True
    physical_ready = (
        gate.get("decision") == "trigger_ready"
        and gate.get("restore_allowed") is True
    )
    if (
        physical_ready
        and require_logical_restore_window
        and not logical_exact
    ):
        gate = {
            **gate,
            "decision": (
                "logical_restore_hit_incomplete_after_physical_window"
            ),
            "restore_allowed": False,
        }
    return {
        **gate,
        "post_abort_candidate_event_count": len(fresh),
        "post_abort_revalidation_fresh": True,
        "abort_requested_timestamp_ns": abort_requested_timestamp_ns,
        "logical_restore_window_required": (
            require_logical_restore_window
        ),
        "logical_restore_window_exact": logical_exact,
        "logical_restore_match_tokens": int(
            latest.get("logical_restore_match_tokens") or 0
        ),
        "raw_logical_restore_match_tokens": int(
            latest.get("raw_logical_restore_match_tokens") or 0
        ),
        "legacy_capped_logical_restore_match_tokens": int(
            latest.get("legacy_capped_logical_restore_match_tokens") or 0
        ),
        "logical_lookup_probe_horizon_tokens": int(
            latest.get("logical_lookup_probe_horizon_tokens") or 0
        ),
        "logical_lookup_lookahead_tokens": int(
            latest.get("logical_lookup_lookahead_tokens") or 0
        ),
        "legacy_capped_false_negative_candidate": latest.get(
            "legacy_capped_false_negative_candidate"
        )
        is True,
        "cpu_coordinator_use_eagle": latest.get("cpu_coordinator_use_eagle")
        is True,
        "eagle_lookahead_delta_tokens": int(
            latest.get("eagle_lookahead_delta_tokens") or 0
        ),
        "eagle_lookahead_required_tokens": int(
            latest.get("eagle_lookahead_required_tokens") or 0
        ),
        "eagle_lookahead_sufficient": latest.get("eagle_lookahead_sufficient")
        is True,
        "logical_lookup_first_reduction_attention_group_index": int(
            latest.get("logical_lookup_first_reduction_attention_group_index")
            or -1
        ),
        "logical_lookup_first_zero_attention_group_index": int(
            latest.get("logical_lookup_first_zero_attention_group_index") or -1
        ),
        "logical_probe_source": str(latest.get("logical_probe_source") or ""),
        "raw_hash_values_retained": False,
    }


def _wait_for_eligibility_target_observable(
    trace_dir: Path, *, timeout_seconds: float
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        trace_rows = _read_trace_rows(trace_dir)
        transfer = summarize_trace_rows(
            trace_rows,
            expected_world_size=8,
            restore_request_suffix="restore_follower",
        )
        last = build_pre_pressure_admission(
            trace_rows,
            d2h_store_complete=transfer["d2h_store_complete"] is True,
            target_block_count=ELIGIBILITY_TARGET_BLOCKS,
            allow_inflight_keyspace_refresh=ALLOW_INFLIGHT_KEYSPACE_REFRESH,
            require_target_store_lineage=REQUIRE_TARGET_STORE_LINEAGE,
            require_effective_group_geometry=(
                REQUIRE_EFFECTIVE_GROUP_GEOMETRY
            ),
        )
        if last["pressure_allowed"] is True:
            return last
        time.sleep(1)
    return last


def execute_inflight_abort_restore(
    artifact_dir: Path, base_url: str, server_pid: int
) -> int:
    plan = json.loads((artifact_dir / "run_plan.json").read_text(encoding="utf-8"))
    by_role = {str(row["k1a_role"]): row for row in plan}
    if set(by_role) != {"warmup", "target_prime", PRESSURE_ROLE, "restore_follower"}:
        raise ValueError(f"{STAGE_LABEL} run plan must contain four fixed roles")
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
    timeline: dict[str, Any] = {
        "schema_version": f"{CONTRACT_SCHEMA_TAG}_residency_gate_timeline_v1",
        "pressure_request_count_executed": 0,
        "pressure_request_count_max": 1,
        "trigger_poll_seconds": TRIGGER_POLL_SECONDS,
        "restore_sent": False,
        "trigger_observed_before_abort": False,
        "pressure_abort_requested": False,
        "pressure_abort_confirmed": False,
        "pressure_idle_after_abort": False,
        "window_valid_after_abort": False,
        "raw_hash_values_retained": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
        "generated_content_retained": False,
    }

    def persist_timeline(terminal: str) -> int:
        timeline["terminal_decision"] = terminal
        _write_json(control_dir / "residency_gate_timeline.json", timeline)
        return 0 if terminal == "restore_request_completed" else 3

    def run_success_role(role: str) -> bool:
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
        if not run_success_role(role):
            return persist_timeline(f"{role}_request_failure")

    initial_gate = _wait_for_eligibility_target_observable(
        trace_dir,
        timeout_seconds=float(
            os.environ.get("P8_2_K1A_H2D_RESIDENCY_TIMEOUT_SECONDS", "180")
        ),
    )
    timeline["initial_gate"] = initial_gate
    if initial_gate.get("d2h_store_complete_before_pressure") is not True:
        return persist_timeline("d2h_store_incomplete_before_pressure")
    if initial_gate.get("pressure_allowed") is not True:
        return persist_timeline(str(initial_gate.get("decision") or "unobservable"))

    pressure = by_role[PRESSURE_ROLE]
    request_id = str(pressure["request_id"])
    health_before, _ = _get(base_url, "/health", timeout=5)
    idle_before, metrics_before = _wait_for_idle(
        base_url,
        control_dir / "raw_metrics" / f"{request_id}_before.prom",
    )
    if not all(
        (
            _process_alive(server_pid),
            health_before == 200,
            idle_before,
            metrics_before.get("queue_metrics_present") is True,
            metrics_before.get("spec_metrics_present") is True,
            metrics_before.get("prefix_metrics_present") is True,
        )
    ):
        rows.append({**pressure, "status": "failed_pre_request_gate"})
        _write_jsonl(control_dir / "raw_request_results.jsonl", rows)
        return persist_timeline("pressure_pre_request_gate_failure")

    _write_active_role(role_path, PRESSURE_ROLE)
    pressure_start_timestamp_ns = time.time_ns()
    batch = {
        "batch_id": request_id,
        "phase": pressure["request_role"],
        "cell_id": pressure["group_id"],
        "context_tokens": pressure["context_tokens"],
        "output_tokens": pressure["output_tokens"],
        "concurrency": 1,
        "repeat_index": pressure["repeat_index"],
        "requests": [{**pressure, "request_index": 1}],
    }
    handle = AbortableRequestHandle()
    thread = threading.Thread(
        target=_stream_abortable_request,
        kwargs={
            "handle": handle,
            "artifact_dir": artifact_dir,
            "base_url": base_url,
            "server_pid": server_pid,
            "batch": batch,
            "request_item": batch["requests"][0],
        },
        name=f"{CONTRACT_SCHEMA_TAG}_pressure_01",
        daemon=True,
    )
    thread.start()
    timeline["pressure_request_count_executed"] = 1
    timeline["pressure_start_timestamp_ns"] = pressure_start_timestamp_ns
    timeline["pressure_start_monotonic_ns"] = time.monotonic_ns()
    deadline = time.monotonic() + TRIGGER_TIMEOUT_SECONDS
    state: dict[str, Any] = {}
    while time.monotonic() < deadline and thread.is_alive():
        state = build_inflight_trigger_state(
            _read_trace_rows(trace_dir),
            pressure_start_timestamp_ns=pressure_start_timestamp_ns,
        )
        if state["decision"] != "continue_pressure":
            break
        time.sleep(TRIGGER_POLL_SECONDS)
    trigger_timed_out_while_running = (
        time.monotonic() >= deadline
        and thread.is_alive()
        and state.get("decision", "continue_pressure") == "continue_pressure"
    )
    if not state:
        state = build_inflight_trigger_state(
            _read_trace_rows(trace_dir),
            pressure_start_timestamp_ns=pressure_start_timestamp_ns,
        )
    timeline["inflight_trigger_state"] = state

    if state.get("decision") != "trigger_ready" or not thread.is_alive():
        if thread.is_alive():
            handle.abort()
            timeline["cleanup_abort_requested_without_restore"] = True
        thread.join(timeout=ABORT_JOIN_TIMEOUT_SECONDS)
        pressure_row, previous_after, _ = _finish_pressure_row(
            handle=handle,
            base_url=base_url,
            control_dir=control_dir,
            item=pressure,
            metrics_before=metrics_before,
            previous_after=previous_after,
        )
        rows.append(pressure_row)
        _write_jsonl(control_dir / "raw_request_results.jsonl", rows)
        terminal = (
            str(state.get("decision"))
            if state.get("decision") != "continue_pressure"
            else "inflight_trigger_timeout"
            if trigger_timed_out_while_running
            else "pressure_completed_without_trigger"
            if not thread.is_alive()
            else "inflight_trigger_state_incomplete"
        )
        return persist_timeline(terminal)

    timeline["trigger_observed_before_abort"] = True
    timeline["trigger"] = state.get("trigger")
    timeline["trigger_latched_monotonic_ns"] = time.monotonic_ns()
    timeline["pressure_abort_requested_timestamp_ns"] = time.time_ns()
    handle.abort()
    timeline["pressure_abort_requested"] = True
    timeline["pressure_abort_requested_monotonic_ns"] = (
        handle.abort_requested_monotonic_ns
    )
    thread.join(timeout=ABORT_JOIN_TIMEOUT_SECONDS)
    timeline["pressure_abort_confirmed"] = not thread.is_alive()
    if not thread.is_alive():
        timeline["pressure_client_exit_observed_monotonic_ns"] = (
            time.monotonic_ns()
        )
    pressure_row, previous_after, idle_after = _finish_pressure_row(
        handle=handle,
        base_url=base_url,
        control_dir=control_dir,
        item=pressure,
        metrics_before=metrics_before,
        previous_after=previous_after,
    )
    rows.append(pressure_row)
    _write_jsonl(control_dir / "raw_request_results.jsonl", rows)
    timeline["pressure_idle_after_abort"] = idle_after
    if idle_after:
        timeline["engine_idle_confirmed_monotonic_ns"] = time.monotonic_ns()
    if thread.is_alive() or pressure_row.get("status") != "aborted_on_trigger":
        return persist_timeline("pressure_abort_not_confirmed")
    if not idle_after:
        return persist_timeline("pressure_not_idle_after_abort")

    post_abort_rows = _read_trace_rows(trace_dir)
    if REQUIRE_POST_ABORT_FRESH_REVALIDATION:
        post_abort_gate = build_post_abort_revalidation_gate(
            post_abort_rows,
            abort_requested_timestamp_ns=int(
                timeline["pressure_abort_requested_timestamp_ns"]
            ),
            required_restore_block_count=ELIGIBILITY_TARGET_BLOCKS,
            require_restore_group_eligibility=(
                REQUIRE_RESTORE_GROUP_ELIGIBILITY
            ),
            require_logical_restore_window=(
                REQUIRE_LOGICAL_RESTORE_WINDOW
            ),
            require_effective_group_geometry=(
                REQUIRE_EFFECTIVE_GROUP_GEOMETRY
            ),
        )
    elif REQUIRE_RESTORE_GROUP_ELIGIBILITY:
        post_abort_gate = build_restore_eligibility_gate(
            post_abort_rows,
            required_restore_block_count=ELIGIBILITY_TARGET_BLOCKS,
            require_effective_group_geometry=(
                REQUIRE_EFFECTIVE_GROUP_GEOMETRY
            ),
        )
    else:
        post_abort_gate = build_residency_gate(
            post_abort_rows, target_block_count=ELIGIBILITY_TARGET_BLOCKS
        )
    timeline["post_abort_gate_checked_monotonic_ns"] = time.monotonic_ns()
    timeline["post_abort_gate"] = post_abort_gate
    timeline["window_valid_after_abort"] = (
        post_abort_gate.get("decision") == "trigger_ready"
        and post_abort_gate.get("restore_allowed") is True
    )
    if timeline["window_valid_after_abort"] is not True:
        decision = str(post_abort_gate.get("decision") or "")
        return persist_timeline(
            decision
            if decision
            == "logical_restore_hit_incomplete_after_physical_window"
            else "window_lost_after_abort"
        )

    timeline["restore_sent"] = True
    timeline["restore_dispatched_monotonic_ns"] = time.monotonic_ns()
    restore_ok = run_success_role("restore_follower")
    timeline["restore_request_completed"] = restore_ok
    timeline["restore_completed_monotonic_ns"] = time.monotonic_ns()
    return persist_timeline(
        "restore_request_completed" if restore_ok else "restore_request_failure"
    )


def _pressure_abort_evidence_exact(row: dict[str, Any]) -> bool:
    return all(
        (
            row.get("k1a_role") == PRESSURE_ROLE,
            row.get("status") == "aborted_on_trigger",
            row.get("http_status") == 200,
            int(row.get("context_tokens") or 0) == PRESSURE_CONTEXT_TOKENS,
            int(row.get("output_tokens") or 0) == OUTPUT_TOKENS,
            row.get("abort_requested") is True,
            row.get("abort_confirmed_by_client_exit") is True,
            row.get("full_response_observed") is False,
            row.get("queue_idle_after_abort") is True,
            row.get("queue_metrics_ok") is True,
            row.get("counter_continuity_ok") is True,
            row.get("health_after_200") is True,
            len(str(row.get("request_body_sha256") or "")) == 64,
        )
    )


def summarize_inflight_request_outcomes(
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    http_success = [
        row
        for row in rows
        if row.get("status") == "success"
        and row.get("http_status") == 200
        and row.get("saw_done") is True
    ]
    contract_completed = [
        row
        for row in rows
        if (
            str(row.get("k1a_role") or "")
            in {"warmup", "target_prime", "restore_follower"}
            and row.get("status") == "success"
        )
        or (
            str(row.get("k1a_role") or "").startswith("pressure_")
            and row.get("status") == "aborted_on_trigger"
        )
    ]
    intentional_aborts = [
        row
        for row in rows
        if str(row.get("k1a_role") or "").startswith("pressure_")
        and row.get("status") == "aborted_on_trigger"
        and row.get("abort_requested") is True
    ]
    pressure_completed = [
        row
        for row in rows
        if str(row.get("k1a_role") or "").startswith("pressure_")
        and row.get("status") == "success"
        and row.get("http_status") == 200
        and row.get("saw_done") is True
        and row.get("abort_requested") is not True
    ]
    return {
        "request_count": len(rows),
        "http_transport_success_count": len(http_success),
        "contract_completed_role_count": len(contract_completed),
        "intentional_pressure_abort_count": len(intentional_aborts),
        "pressure_full_response_without_trigger_count": len(
            pressure_completed
        ),
    }


def _timeline_order_exact(timeline: dict[str, Any]) -> bool:
    timestamp_fields = (
        "pressure_start_monotonic_ns",
        "trigger_latched_monotonic_ns",
        "pressure_abort_requested_monotonic_ns",
        "pressure_client_exit_observed_monotonic_ns",
        "engine_idle_confirmed_monotonic_ns",
        "post_abort_gate_checked_monotonic_ns",
        "restore_dispatched_monotonic_ns",
        "restore_completed_monotonic_ns",
    )
    timestamps = [timeline.get(field) for field in timestamp_fields]
    timestamps_exact = all(
        type(value) is int and value > 0 for value in timestamps
    ) and all(
        int(before) <= int(after)
        for before, after in zip(timestamps, timestamps[1:])
    )
    return all(
        (
            timeline.get("terminal_decision") == "restore_request_completed",
            timeline.get("trigger_observed_before_abort") is True,
            timeline.get("pressure_abort_requested") is True,
            timeline.get("pressure_abort_confirmed") is True,
            timeline.get("pressure_idle_after_abort") is True,
            timeline.get("window_valid_after_abort") is True,
            timeline.get("restore_sent") is True,
            timeline.get("restore_request_completed") is True,
            timestamps_exact,
        )
    )


def _write_bounded_request_summary(
    path: Path, rows: list[dict[str, Any]]
) -> None:
    fields = (
        "k1a_role",
        "status",
        "http_status",
        "context_tokens",
        "output_tokens",
        "generated_token_count",
        "streamed_token_count",
        "finish_reason",
        "saw_done",
        "abort_requested",
        "abort_confirmed_by_client_exit",
        "full_response_observed",
        "queue_idle_after_abort",
        "prefix_hits_delta",
        "accepted_token_delta",
        "queue_metrics_ok",
        "counter_continuity_ok",
        "spec_activity_ok",
        "ttft_ms",
        "e2el_ms",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def build_inflight_result_summary(
    *,
    stage_label: str,
    grade: str,
    request_count: int,
    completed_request_count: int,
    intentional_pressure_abort_count: int,
    terminal_decision: str,
    resource_recovery_exact: bool,
) -> str:
    return (
        f"# {stage_label} {RESULT_SUMMARY_TITLE}\n\n"
        f"- grade: `{grade}`\n"
        f"- terminal: `{terminal_decision}`\n"
        f"- requests: `{completed_request_count} completed + "
        f"{intentional_pressure_abort_count} intentional pressure abort / "
        f"{request_count}`\n"
        f"- resource recovery exact: `{str(resource_recovery_exact).lower()}`\n"
        f"- fixed pressure context: `{PRESSURE_CONTEXT_TOKENS}`\n"
        "- claim: one accepted-capacity in-flight trigger/abort/idle/restore "
        "H2D mechanism candidate only.\n"
        "- no performance, unique-cause, K2, or P8.3-I1 claim.\n"
    )


def build_resource_recovery_summary(
    *,
    stopped_card_ids: list[int],
    restored_card_ids: list[int],
    stop_exit_code: int,
    restart_exit_code: int,
    keep_alive_marker_count: int,
    expected_keep_alive_marker_count: int | None = None,
    keep_alive_marker_card_ids: list[int] | None = None,
    port_7000_listener_count: int,
    vllm_residual_process_count: int,
    healthy_card_ids: list[int],
    tracked_worktree_clean: bool,
) -> dict[str, Any]:
    stopped = sorted(set(stopped_card_ids))
    restored = sorted(set(restored_card_ids))
    healthy = sorted(set(healthy_card_ids))
    marker_cards = sorted(set(keep_alive_marker_card_ids or []))
    same_card_set = bool(stopped) and stopped == restored
    marker_coverage_exact = (
        keep_alive_marker_count > 0
        if expected_keep_alive_marker_count is None
        else keep_alive_marker_count == expected_keep_alive_marker_count
        and marker_cards == stopped
    )
    keep_alive_restored = all(
        (
            same_card_set,
            stop_exit_code == 0,
            restart_exit_code == 0,
            marker_coverage_exact,
        )
    )
    port_free = port_7000_listener_count == 0
    all_eight_healthy = healthy == list(range(8))
    recovery_exact = all(
        (
            keep_alive_restored,
            port_free,
            vllm_residual_process_count == 0,
            all_eight_healthy,
            tracked_worktree_clean,
        )
    )
    return {
        "schema_version": f"{CONTRACT_SCHEMA_TAG}_resource_recovery_v1",
        "stopped_card_ids": stopped,
        "restored_card_ids": restored,
        "same_card_set_restored": same_card_set,
        "stop_exit_code": stop_exit_code,
        "restart_exit_code": restart_exit_code,
        "keep_alive_marker_count": keep_alive_marker_count,
        "expected_keep_alive_marker_count": expected_keep_alive_marker_count,
        "keep_alive_marker_card_ids": marker_cards,
        "keep_alive_marker_coverage_exact": marker_coverage_exact,
        "keep_alive_restored_exact": keep_alive_restored,
        "port_7000_listener_count": port_7000_listener_count,
        "port_7000_free": port_free,
        "vllm_residual_process_count": vllm_residual_process_count,
        "healthy_card_ids": healthy,
        "all_eight_npu_healthy": all_eight_healthy,
        "tracked_worktree_clean": tracked_worktree_clean,
        "resource_recovery_exact": recovery_exact,
        "generated_content_retained": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
    }


def classify_inflight_grades(
    *,
    grade_prefix: str,
    candidate_green: str,
    terminal: str,
    cleanup: str,
    recovery_ok: bool,
    evidence_exact: bool,
) -> dict[str, str]:
    explicit_terminal_grades = {
        "request_local_progress_ambiguous",
        "cpu_target_lost",
        "target_store_lineage_unobservable_before_pressure",
        "pressure_completed_without_trigger",
        "inflight_trigger_timeout",
        "pressure_abort_not_confirmed",
        "pressure_not_idle_after_abort",
        "window_lost_after_abort",
        "logical_restore_hit_incomplete_after_physical_window",
    }
    if terminal in explicit_terminal_grades:
        experimental_grade = f"{grade_prefix}_{terminal}"
    elif not evidence_exact:
        experimental_grade = f"{grade_prefix}_h2d_evidence_incomplete"
    else:
        experimental_grade = candidate_green
    operational_grade = (
        f"{grade_prefix}_cleanup_or_recovery_incomplete"
        if cleanup != "clean" or not recovery_ok
        else "operational_recovery_clean"
    )
    return {
        "experimental_grade": experimental_grade,
        "operational_grade": operational_grade,
        "server_grade": (
            operational_grade
            if operational_grade != "operational_recovery_clean"
            else experimental_grade
        ),
    }


def _build_inflight_candidate_manifest(
    artifact_dir: Path,
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    total = 0
    for name in BOUNDED_CANDIDATE_FILES:
        path = artifact_dir / name
        if not path.is_file():
            continue
        size = path.stat().st_size
        total += size
        files[name] = {
            "bytes": size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "sensitivity": (
                "bounded_operational_metadata_no_content_or_token_ids"
            ),
        }
    return {
        "schema_version": f"{CONTRACT_SCHEMA_TAG}_bounded_candidate_manifest_v1",
        "files": files,
        "payload_file_count": len(files),
        "transfer_file_count_including_manifest": len(files) + 1,
        "payload_file_count_max": 15,
        "transfer_file_count_including_manifest_max": 16,
        "candidate_total_bytes": total,
        "max_transfer_total_bytes": 71680,
        "generated_content_retained": False,
        "token_ids_retained": False,
        "request_ids_retained": False,
        "raw_request_or_trace_hash_values_retained": False,
        "manifest_integrity_digests_only": True,
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "automatic_transfer_allowed": False,
    }


def finalize_inflight_abort_restore(artifact_dir: Path) -> int:
    control_dir = artifact_dir / "runtime/request_control"
    request_rows = _read_jsonl(control_dir / "raw_request_results.jsonl")
    timeline = _read_json(control_dir / "residency_gate_timeline.json")
    trace_rows = _read_trace_rows(artifact_dir / "runtime/offload_trace")
    trigger_summary = summarize_h2d_trigger_rows(
        trace_rows,
        target_block_count=ELIGIBILITY_TARGET_BLOCKS,
        restore_tokens=RESTORE_MATCH_TOKENS,
        expected_world_size=8,
        require_restore_group_eligibility=REQUIRE_RESTORE_GROUP_ELIGIBILITY,
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
    by_role = {str(row.get("k1a_role") or ""): row for row in request_rows}
    roles_exact = [str(row.get("k1a_role") or "") for row in request_rows] == [
        "warmup",
        "target_prime",
        PRESSURE_ROLE,
        "restore_follower",
    ]
    completed_roles_exact = all(
        _request_evidence_exact(by_role.get(role, {}))
        for role in ("warmup", "target_prime", "restore_follower")
    )
    pressure_abort_exact = _pressure_abort_evidence_exact(
        by_role.get(PRESSURE_ROLE, {})
    )
    timeline_exact = _timeline_order_exact(timeline)
    connector_ok = all(
        (
            connector.get("resolved_connector_exact") is True,
            connector.get("resolved_lazy_offload_exact") is True,
        )
    )
    repair_ok = repair.get("hybrid_diagnostic_ok") is True or repair.get(
        "all_required_managers_resolved"
    ) is True
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
    evidence_exact = all(
        (
            roles_exact,
            completed_roles_exact,
            pressure_abort_exact,
            timeline_exact,
            connector_ok,
            repair_ok,
            host.get("preflight_gate_ok") is True,
            recovery_ok,
            cleanup == "clean",
            mechanism_ok,
        )
    )
    terminal = str(timeline.get("terminal_decision") or "missing")
    request_outcomes = summarize_inflight_request_outcomes(request_rows)
    logical_keyspace_diagnostics = (
        summarize_logical_keyspace_probe_diagnostics(trace_rows)
        if LOGICAL_KEYSPACE_DIAGNOSTICS
        else None
    )
    target_store_lineage = (
        summarize_target_store_lineage_rows(
            trace_rows,
            target_block_count=ELIGIBILITY_TARGET_BLOCKS,
        )
        if TARGET_STORE_LINEAGE_DIAGNOSTICS
        else None
    )
    target_store_lineage_ok = (
        not REQUIRE_TARGET_STORE_LINEAGE
        or all(
            (
                (target_store_lineage or {}).get(
                    "target_store_lineage_capture_exact"
                )
                is True,
                int(
                    (target_store_lineage or {}).get(
                        "target_fa_store_completed_key_count_max"
                    )
                    or 0
                )
                == (
                    int(
                        (target_store_lineage or {}).get(
                            "target_fa_required_physical_key_count"
                        )
                        or 0
                    )
                    if REQUIRE_EFFECTIVE_GROUP_GEOMETRY
                    else ELIGIBILITY_TARGET_BLOCKS
                ),
                int(
                    (target_store_lineage or {}).get(
                        "logical_and_physical_window_event_count"
                    )
                    or 0
                )
                > 0,
            )
        )
    )
    evidence_exact = evidence_exact and target_store_lineage_ok
    grades = classify_inflight_grades(
        grade_prefix=GRADE_PREFIX,
        candidate_green=CANDIDATE_GREEN,
        terminal=terminal,
        cleanup=cleanup,
        recovery_ok=recovery_ok,
        evidence_exact=evidence_exact,
    )
    grade = grades["server_grade"]

    grading = {
        "schema_version": f"{CONTRACT_SCHEMA_TAG}_grading_v1",
        "server_grade": grade,
        "experimental_grade": grades["experimental_grade"],
        "operational_grade": grades["operational_grade"],
        "experimental_terminal": terminal,
        "request_count": request_outcomes["request_count"],
        "successful_request_count": request_outcomes[
            "http_transport_success_count"
        ],
        "http_transport_success_count": request_outcomes[
            "http_transport_success_count"
        ],
        "contract_completed_role_count": request_outcomes[
            "contract_completed_role_count"
        ],
        "pressure_full_response_without_trigger_count": request_outcomes[
            "pressure_full_response_without_trigger_count"
        ],
        "pressure_request_count_executed": int(
            timeline.get("pressure_request_count_executed") or 0
        ),
        "inflight_keyspace_refresh_required": (
            ALLOW_INFLIGHT_KEYSPACE_REFRESH
        ),
        "logical_keyspace_probe_event_count": int(
            (logical_keyspace_diagnostics or {}).get("probe_event_count") or 0
        ),
        "logical_keyspace_exact_probe_event_count": int(
            (logical_keyspace_diagnostics or {}).get("exact_probe_event_count")
            or 0
        ),
        "target_store_lineage_required": REQUIRE_TARGET_STORE_LINEAGE,
        "target_store_lineage_capture_exact": (
            (target_store_lineage or {}).get(
                "target_store_lineage_capture_exact"
            )
            is True
        ),
        "target_store_lineage_attribution": str(
            (target_store_lineage or {}).get(
                "target_lineage_attribution"
            )
            or "not_enabled"
        ),
        "target_store_key_count": int(
            (target_store_lineage or {}).get("target_store_key_count")
            or 0
        ),
        "target_store_scheduled_key_count": int(
            (target_store_lineage or {}).get(
                "target_store_scheduled_key_count_max"
            )
            or 0
        ),
        "target_store_completed_key_count": int(
            (target_store_lineage or {}).get(
                "target_store_completed_key_count_max"
            )
            or 0
        ),
        "target_fa_store_completed_key_count": int(
            (target_store_lineage or {}).get(
                "target_fa_store_completed_key_count_max"
            )
            or 0
        ),
        "physical_cpu_only_window_event_count": int(
            (target_store_lineage or {}).get(
                "physical_cpu_only_window_event_count"
            )
            or 0
        ),
        "logical_and_physical_window_event_count": int(
            (target_store_lineage or {}).get(
                "logical_and_physical_window_event_count"
            )
            or 0
        ),
        "roles_exact": roles_exact,
        "completed_roles_exact": completed_roles_exact,
        "pressure_abort_evidence_exact": pressure_abort_exact,
        "trigger_abort_idle_restore_order_exact": timeline_exact,
        "window_valid_after_abort": timeline.get("window_valid_after_abort") is True,
        "h2d_restore_mechanism_candidate": mechanism_ok,
        "resolved_connector_and_lazy_mode_exact": connector_ok,
        "repair_diagnostic_ok": repair_ok,
        "host_memory_gate_ok": host.get("preflight_gate_ok") is True,
        "resource_recovery_exact": recovery_ok,
        "cleanup": cleanup,
        "context_search_or_sweep_used": False,
        "pressure_context_tokens": PRESSURE_CONTEXT_TOKENS,
        "required_restore_block_count": ELIGIBILITY_TARGET_BLOCKS,
        "restore_group_eligibility_required": (
            REQUIRE_RESTORE_GROUP_ELIGIBILITY
        ),
        "logical_restore_window_required_for_restore": (
            REQUIRE_LOGICAL_RESTORE_WINDOW
        ),
        "actual_cpu_eviction_proven": int(
            (target_store_lineage or {}).get(
                "target_cpu_evicted_key_count"
            )
            or 0
        )
        > 0,
        "cause_proven_as_unique": False,
        "performance_reference_accepted": False,
        "k2_authorized": False,
        "p8_3_i1_authorized": False,
        "next_task_authorized": False,
        "developer_review_required": True,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    mtp_queue_health = {
        "schema_version": f"{CONTRACT_SCHEMA_TAG}_mtp_queue_health_v1",
        "request_count": request_outcomes["request_count"],
        "completed_request_count": request_outcomes[
            "http_transport_success_count"
        ],
        "http_transport_success_count": request_outcomes[
            "http_transport_success_count"
        ],
        "contract_completed_role_count": request_outcomes[
            "contract_completed_role_count"
        ],
        "intentional_pressure_abort_count": request_outcomes[
            "intentional_pressure_abort_count"
        ],
        "pressure_full_response_without_trigger_count": request_outcomes[
            "pressure_full_response_without_trigger_count"
        ],
        "queue_idle_after_abort": timeline.get("pressure_idle_after_abort") is True,
        "counter_continuity_ok_all": bool(request_rows)
        and all(row.get("counter_continuity_ok") is True for row in request_rows),
    }
    _write_bounded_request_summary(
        artifact_dir / "request_summary.tsv", request_rows
    )
    _write_json(artifact_dir / "residency_gate_timeline.json", timeline)
    _write_json(artifact_dir / "h2d_trigger_summary.json", trigger_summary)
    _write_json(artifact_dir / "transfer_trace_summary.json", transfer_summary)
    _write_json(artifact_dir / "mtp_queue_health_summary.json", mtp_queue_health)
    _write_json(artifact_dir / "grading_summary.json", grading)
    if logical_keyspace_diagnostics is not None:
        _write_json(
            artifact_dir / "logical_keyspace_probe_diagnostic_summary.json",
            logical_keyspace_diagnostics,
        )
    if target_store_lineage is not None:
        _write_json(
            artifact_dir / "target_store_lineage_summary.json",
            target_store_lineage,
        )
    (artifact_dir / "result_summary.md").write_text(
        build_inflight_result_summary(
            stage_label=STAGE_LABEL,
            grade=grade,
            request_count=len(request_rows),
            completed_request_count=mtp_queue_health["completed_request_count"],
            intentional_pressure_abort_count=mtp_queue_health[
                "intentional_pressure_abort_count"
            ],
            terminal_decision=terminal,
            resource_recovery_exact=recovery_ok,
        ),
        encoding="utf-8",
    )
    manifest = _build_inflight_candidate_manifest(artifact_dir)
    manifest_path = artifact_dir / "candidate_manifest.server_local.json"
    _write_json(manifest_path, manifest)
    transfer_total_bytes = manifest["candidate_total_bytes"] + manifest_path.stat().st_size
    bounded = all(
        (
            manifest["payload_file_count"] <= 15,
            manifest["transfer_file_count_including_manifest"] <= 16,
            transfer_total_bytes <= 71680,
        )
    )
    return 0 if grade == CANDIDATE_GREEN and bounded else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    execute = subparsers.add_parser("execute")
    execute.add_argument("--artifact-dir", type=Path, required=True)
    execute.add_argument("--base-url", required=True)
    execute.add_argument("--server-pid", type=int, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    recovery = subparsers.add_parser("record-recovery")
    recovery.add_argument("--artifact-dir", type=Path, required=True)
    recovery.add_argument("--stopped-card-ids", required=True)
    recovery.add_argument("--restored-card-ids", required=True)
    recovery.add_argument("--stop-exit-code", type=int, required=True)
    recovery.add_argument("--restart-exit-code", type=int, required=True)
    recovery.add_argument("--keep-alive-marker-count", type=int, required=True)
    recovery.add_argument("--expected-keep-alive-marker-count", type=int)
    recovery.add_argument("--keep-alive-marker-card-ids", default="")
    recovery.add_argument("--port-7000-listener-count", type=int, required=True)
    recovery.add_argument(
        "--vllm-residual-process-count", type=int, required=True
    )
    recovery.add_argument("--healthy-card-ids", required=True)
    recovery.add_argument(
        "--tracked-worktree-clean", choices=("true", "false"), required=True
    )
    return parser


def _parse_card_ids(raw: str) -> list[int]:
    return [int(value) for value in raw.split(",") if value != ""]


def main() -> int:
    args = _parser().parse_args()
    if args.command == "prepare":
        prepare_inflight_abort_restore_artifacts(
            args.source_payload, args.artifact_dir, args.model_name
        )
        return 0
    if args.command == "execute":
        return execute_inflight_abort_restore(
            args.artifact_dir, args.base_url, args.server_pid
        )
    if args.command == "finalize":
        return finalize_inflight_abort_restore(args.artifact_dir)
    if args.command == "record-recovery":
        value = build_resource_recovery_summary(
            stopped_card_ids=_parse_card_ids(args.stopped_card_ids),
            restored_card_ids=_parse_card_ids(args.restored_card_ids),
            stop_exit_code=args.stop_exit_code,
            restart_exit_code=args.restart_exit_code,
            keep_alive_marker_count=args.keep_alive_marker_count,
            expected_keep_alive_marker_count=(
                args.expected_keep_alive_marker_count
            ),
            keep_alive_marker_card_ids=_parse_card_ids(
                args.keep_alive_marker_card_ids
            ),
            port_7000_listener_count=args.port_7000_listener_count,
            vllm_residual_process_count=args.vllm_residual_process_count,
            healthy_card_ids=_parse_card_ids(args.healthy_card_ids),
            tracked_worktree_clean=args.tracked_worktree_clean == "true",
        )
        _write_json(args.artifact_dir / "resource_recovery_summary.json", value)
        return 0 if value["resource_recovery_exact"] is True else 2
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
