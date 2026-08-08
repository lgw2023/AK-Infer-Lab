"""P6.3C-R3E mixed Prefill/Decode scheduling-step latency attribution.

R3D showed that persistent chunk targets from 128 to 1024 tokens all exposed
resident Decode to an approximately 420 ms tail-latency floor.  R3E reuses the
same staged-arrival request and controller semantics but makes the EngineCore
step itself the object of study.  Three unprofiled lifecycles measure host
schedule, executor-future and scheduler-update spans; two fresh diagnostic
lifecycles align the representative request windows with msprof device rows.

The observer is read-only.  Its executor span includes RPC, worker execution,
device work and synchronization, so the finalizer never labels that span as
device time without profiler evidence.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts import (  # noqa: E402
    run_deepseek_p6_3c_r3d_persistent_prefill as r3d,
)
from tools.inference_contracts.analyze_msprof_request_device_aggregate import (  # noqa: E402
    analyze_request_device_aggregate,
)


base = r3d.base
TASK_ID = "p6_3c_r3e_mixed_step_latency_floor_attribution_2026_0808_run01"
WORKLOAD_RELATIVE_PATH = (
    "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r3e_mixed_step_latency_floor_attribution.yaml"
)
REQUEST_PREFIX = "p6_3c_r3e"
TRACKS = ("mechanism",)
MODES = ("chunked_prefill_on",)
MAX_MODEL_LEN = 12288
MAX_NUM_SEQS = 9
EXPECTED_MODEL_LIFECYCLES = 5
EXPECTED_ENGINE_REQUESTS = 50
EXPECTED_HTTP_REQUESTS = 15
HOST_LIFECYCLE_IDS = ("host_01", "host_02", "host_03")
PROFILE_LIFECYCLE_IDS = ("profile_01", "profile_02")
EXECUTOR_SHARE_THRESHOLD = 0.80
TARGET_INSENSITIVE_RATIO_LOWER = 0.75
TARGET_INSENSITIVE_RATIO_UPPER = 1.25

CONFIGS = (
    {
        "config_id": "admission_on_t4096",
        "mode": "chunked_prefill_on",
        "max_num_batched_tokens": 12288,
        "policy_type": "adaptive_on",
        "pressure_scope": "admission_only",
        "active_chunk_target_tokens": 4096,
        "decode_quantum_tokens": 2,
    },
    {
        "config_id": "persistent_on_t1024",
        "mode": "chunked_prefill_on",
        "max_num_batched_tokens": 12288,
        "policy_type": "adaptive_on",
        "pressure_scope": "persistent_prefill",
        "active_chunk_target_tokens": 1024,
        "decode_quantum_tokens": 2,
    },
    {
        "config_id": "persistent_on_t128",
        "mode": "chunked_prefill_on",
        "max_num_batched_tokens": 12288,
        "policy_type": "adaptive_on",
        "pressure_scope": "persistent_prefill",
        "active_chunk_target_tokens": 128,
        "decode_quantum_tokens": 2,
    },
)
CONFIG_BY_ID = {row["config_id"]: row for row in CONFIGS}
LIFECYCLE_SCHEDULE = (
    {
        "track": "mechanism",
        "lifecycle_id": "host_01",
        "mirror_round": "host_timing",
        "evidence_track": "host_timing",
        **CONFIG_BY_ID["admission_on_t4096"],
    },
    {
        "track": "mechanism",
        "lifecycle_id": "host_02",
        "mirror_round": "host_timing",
        "evidence_track": "host_timing",
        **CONFIG_BY_ID["persistent_on_t1024"],
    },
    {
        "track": "mechanism",
        "lifecycle_id": "host_03",
        "mirror_round": "host_timing",
        "evidence_track": "host_timing",
        **CONFIG_BY_ID["persistent_on_t128"],
    },
    {
        "track": "mechanism",
        "lifecycle_id": "profile_01",
        "mirror_round": "diagnostic_msprof",
        "evidence_track": "diagnostic_msprof",
        **CONFIG_BY_ID["admission_on_t4096"],
    },
    {
        "track": "mechanism",
        "lifecycle_id": "profile_02",
        "mirror_round": "diagnostic_msprof",
        "evidence_track": "diagnostic_msprof",
        **CONFIG_BY_ID["persistent_on_t128"],
    },
)
LIFECYCLE_BY_ID = {row["lifecycle_id"]: row for row in LIFECYCLE_SCHEDULE}


def _bind_base_globals() -> None:
    """Bind the audited R3 staged-arrival runner to the R3E schedule."""

    r3d._bind_base_globals()  # noqa: SLF001
    base.TASK_ID = TASK_ID
    base.WORKLOAD_RELATIVE_PATH = WORKLOAD_RELATIVE_PATH
    base.REQUEST_PREFIX = REQUEST_PREFIX
    base.MAX_MODEL_LEN = MAX_MODEL_LEN
    base.MAX_NUM_SEQS = MAX_NUM_SEQS
    base.TRACKS = TRACKS
    base.MODES = MODES
    base.CONFIGS = CONFIGS
    base.CONFIG_BY_ID = CONFIG_BY_ID
    base.ON_CONFIG_IDS = tuple(CONFIG_BY_ID)
    base.LIFECYCLE_SCHEDULE = LIFECYCLE_SCHEDULE
    base.MECHANISM_LIFECYCLES = LIFECYCLE_SCHEDULE
    base.PERFORMANCE_LIFECYCLES = ()
    base.EXPECTED_MODEL_LIFECYCLES = EXPECTED_MODEL_LIFECYCLES
    base.EXPECTED_ENGINE_REQUESTS = EXPECTED_ENGINE_REQUESTS
    base.EXPECTED_HTTP_REQUESTS = EXPECTED_HTTP_REQUESTS
    base.EXPECTED_PERFORMANCE_TRIALS = 0
    base.EXPECTED_POLICY_SUMMARY_ROWS = 0
    base.EXPECTED_VALID_TRIALS_PER_SUMMARY = 0
    base.EXPECTED_POLICY_PAIRS = 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_trace(lifecycle_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(
        (lifecycle_dir / "runtime/scheduler_trace").glob("trace.*.jsonl")
    ):
        rows.extend(base.r3a._read_jsonl(path))  # noqa: SLF001
    return rows


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 6)


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 6) if values else None


def _step_class(step: dict[str, Any]) -> str:
    resident = int(step.get("resident_decode_tokens") or 0)
    injected = int(step.get("injected_prefill_tokens") or 0)
    if resident > 0 and injected > 0:
        return "mixed_prefill_decode"
    if resident > 0:
        return "resident_decode_only"
    if injected > 0:
        return "injected_prefill_only"
    return "other"


def build_step_timing_rows(
    artifact_dir: Path,
    lifecycle_ids: tuple[str, ...] = HOST_LIFECYCLE_IDS,
) -> list[dict[str, Any]]:
    """Correlate the four observer events for measured staged-arrival steps."""

    injection_marker = f"cmpl-{base._trial_plan('mechanism')[0]['injected_request_id']}"
    output: list[dict[str, Any]] = []
    for lifecycle_id in lifecycle_ids:
        lifecycle = LIFECYCLE_BY_ID[lifecycle_id]
        events: dict[str, dict[str, dict[str, Any]]] = {}
        for row in _read_trace(artifact_dir / "lifecycles" / lifecycle_id):
            context_id = str(row.get("timing_context_id") or "")
            if context_id:
                events.setdefault(context_id, {})[str(row.get("event"))] = row
        for context_id, by_event in events.items():
            step = by_event.get("scheduler_step")
            if not step or injection_marker not in json.dumps(step, separators=(",", ":")):
                continue
            submit = by_event.get("executor_execute_submit") or {}
            complete = by_event.get("executor_execute_complete") or {}
            update = by_event.get("scheduler_update_complete") or {}
            schedule_ns = int(step.get("scheduler_cpu_ns") or 0)
            submit_ns = int(submit.get("executor_submit_cpu_ns") or 0)
            execute_model_ns = int(complete.get("executor_elapsed_ns") or 0)
            pipeline_ns = int(update.get("engine_pipeline_elapsed_ns") or 0)
            update_ns = int(update.get("scheduler_update_cpu_ns") or 0)
            total_ns = int(update.get("schedule_to_update_complete_ns") or 0)
            complete_timing = all(
                name in by_event
                for name in (
                    "scheduler_step",
                    "executor_execute_submit",
                    "executor_execute_complete",
                    "scheduler_update_complete",
                )
            ) and min(
                schedule_ns,
                execute_model_ns,
                pipeline_ns,
                update_ns,
                total_ns,
            ) > 0
            output.append(
                {
                    "lifecycle_id": lifecycle_id,
                    "evidence_track": lifecycle["evidence_track"],
                    "config_id": lifecycle["config_id"],
                    "pressure_scope": lifecycle["pressure_scope"],
                    "active_chunk_target_tokens": lifecycle[
                        "active_chunk_target_tokens"
                    ],
                    "timing_context_id": context_id,
                    "step_index": step.get("step_index"),
                    "step_class": _step_class(step),
                    "resident_decode_tokens": step.get("resident_decode_tokens"),
                    "injected_prefill_tokens": step.get("injected_prefill_tokens"),
                    "total_num_scheduled_tokens": step.get(
                        "total_num_scheduled_tokens"
                    ),
                    "effective_token_budget": step.get("effective_token_budget"),
                    "scheduler_cpu_ms": round(schedule_ns / 1_000_000, 6),
                    "executor_submit_cpu_ms": round(submit_ns / 1_000_000, 6),
                    "execute_model_future_ms": round(
                        execute_model_ns / 1_000_000, 6
                    ),
                    "engine_pipeline_ms": round(pipeline_ns / 1_000_000, 6),
                    "scheduler_update_cpu_ms": round(update_ns / 1_000_000, 6),
                    "schedule_to_update_complete_ms": round(
                        total_ns / 1_000_000, 6
                    ),
                    "unattributed_host_gap_ms": round(
                        max(total_ns - schedule_ns - pipeline_ns - update_ns, 0)
                        / 1_000_000,
                        6,
                    ),
                    "engine_pipeline_fraction_of_step": round(
                        pipeline_ns / total_ns, 6
                    )
                    if total_ns > 0
                    else None,
                    "timing_complete": complete_timing,
                }
            )
    return output


def summarize_host_timing_rows(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Aggregate timing spans and evaluate project-level attribution probes."""

    groups: list[dict[str, Any]] = []
    for lifecycle_id in HOST_LIFECYCLE_IDS:
        lifecycle = LIFECYCLE_BY_ID[lifecycle_id]
        selected = [row for row in rows if row["lifecycle_id"] == lifecycle_id]
        for step_class in (
            "mixed_prefill_decode",
            "resident_decode_only",
            "injected_prefill_only",
            "other",
        ):
            class_rows = [
                row
                for row in selected
                if row["step_class"] == step_class and row["timing_complete"]
            ]
            if not class_rows:
                continue
            groups.append(
                {
                    "lifecycle_id": lifecycle_id,
                    "config_id": lifecycle["config_id"],
                    "active_chunk_target_tokens": lifecycle[
                        "active_chunk_target_tokens"
                    ],
                    "step_class": step_class,
                    "complete_step_count": len(class_rows),
                    "scheduler_cpu_ms_median": _median(
                        [float(row["scheduler_cpu_ms"]) for row in class_rows]
                    ),
                    "execute_model_future_ms_median": _median(
                        [
                            float(row["execute_model_future_ms"])
                            for row in class_rows
                        ]
                    ),
                    "engine_pipeline_ms_median": _median(
                        [float(row["engine_pipeline_ms"]) for row in class_rows]
                    ),
                    "engine_pipeline_ms_p95": _percentile(
                        [float(row["engine_pipeline_ms"]) for row in class_rows],
                        0.95,
                    ),
                    "scheduler_update_cpu_ms_median": _median(
                        [float(row["scheduler_update_cpu_ms"]) for row in class_rows]
                    ),
                    "step_total_ms_median": _median(
                        [
                            float(row["schedule_to_update_complete_ms"])
                            for row in class_rows
                        ]
                    ),
                    "engine_pipeline_fraction_median": _median(
                        [
                            float(row["engine_pipeline_fraction_of_step"])
                            for row in class_rows
                            if row["engine_pipeline_fraction_of_step"] is not None
                        ]
                    ),
                }
            )

    mixed = {
        row["config_id"]: row
        for row in groups
        if row["step_class"] == "mixed_prefill_decode"
    }
    t128 = mixed.get("persistent_on_t128", {}).get("engine_pipeline_ms_median")
    t1024 = mixed.get("persistent_on_t1024", {}).get("engine_pipeline_ms_median")
    target_ratio = round(float(t128) / float(t1024), 6) if t128 and t1024 else None
    timing_complete = (
        len(rows) > 0
        and all(row.get("timing_complete") is True for row in rows)
        and set(mixed) == {
            "admission_on_t4096",
            "persistent_on_t1024",
            "persistent_on_t128",
        }
    )
    executor_dominant = timing_complete and all(
        float(row.get("engine_pipeline_fraction_median") or 0)
        >= EXECUTOR_SHARE_THRESHOLD
        for row in mixed.values()
    )
    target_insensitive = bool(
        target_ratio is not None
        and TARGET_INSENSITIVE_RATIO_LOWER
        <= target_ratio
        <= TARGET_INSENSITIVE_RATIO_UPPER
    )
    host_overhead_dominant = timing_complete and all(
        float(row.get("engine_pipeline_fraction_median") or 0) < 0.50
        for row in mixed.values()
    )
    summary = {
        "task_id": TASK_ID,
        "schema": "p6_3c_r3e_engine_path_timing_v1",
        "host_lifecycle_count": len(HOST_LIFECYCLE_IDS),
        "timed_step_count": len(rows),
        "complete_timing_step_count": sum(
            row.get("timing_complete") is True for row in rows
        ),
        "host_timing_complete": timing_complete,
        "mixed_engine_pipeline_fraction_at_least_0_80": executor_dominant,
        "persistent_t128_to_t1024_pipeline_median_ratio": target_ratio,
        "target_insensitive_ratio_interval": [
            TARGET_INSENSITIVE_RATIO_LOWER,
            TARGET_INSENSITIVE_RATIO_UPPER,
        ],
        "persistent_mixed_pipeline_target_insensitive": target_insensitive,
        "host_scheduler_and_update_dominant": host_overhead_dominant,
        "engine_pipeline_span_semantics": (
            "scheduler_return_through_update_start_includes_execute_sample_queue_rpc_worker_device_and_sync"
        ),
        "threshold_status": "project_diagnostic_not_external_standard",
    }
    return summary, groups


def write_mechanism_evidence(
    artifact_dir: Path,
    lifecycle_ids: tuple[str, ...] = tuple(row["lifecycle_id"] for row in LIFECYCLE_SCHEDULE),
) -> dict[str, Any]:
    original = base.MECHANISM_LIFECYCLES
    try:
        base.MECHANISM_LIFECYCLES = tuple(
            LIFECYCLE_BY_ID[lifecycle_id] for lifecycle_id in lifecycle_ids
        )
        summary, rows = r3d.mechanism_budget_summary(artifact_dir)
    finally:
        base.MECHANISM_LIFECYCLES = original
    summary.update(
        {
            "task_id": TASK_ID,
            "r3e_lifecycle_ids": list(lifecycle_ids),
            "diagnostic_profiler_does_not_change_scientific_requests": True,
        }
    )
    (artifact_dir / "r3e_mechanism_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "mechanism_scheduler_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    base._write_tsv(artifact_dir / "r3e_mechanism_cells.tsv", rows)
    return summary


def write_host_timing_evidence(artifact_dir: Path) -> dict[str, Any]:
    rows = build_step_timing_rows(artifact_dir)
    summary, groups = summarize_host_timing_rows(rows)
    base._write_tsv(artifact_dir / "r3e_step_timing_rows.tsv", rows)
    base._write_tsv(artifact_dir / "r3e_host_phase_summary.tsv", groups)
    (artifact_dir / "r3e_host_attribution.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def _write_profiler_request_windows(
    artifact_dir: Path, lifecycle_id: str
) -> Path | None:
    lifecycle_dir = artifact_dir / "lifecycles" / lifecycle_id
    request_path = lifecycle_dir / "raw_request_results.jsonl"
    trial_path = lifecycle_dir / "raw_trial_results.jsonl"
    if not request_path.is_file() or not trial_path.is_file():
        return None
    requests = base.r3a._read_jsonl(  # noqa: SLF001
        request_path
    )
    trials = base.r3a._read_jsonl(trial_path)  # noqa: SLF001
    injected = next(
        row
        for row in requests
        if row.get("phase") == "measured" and row.get("request_role") == "injected"
    )
    trial = next(row for row in trials if row.get("phase") == "measured")
    first_token_ns = min(int(value) for value in injected["token_arrival_ns"])
    dispatch_ns = int((trial.get("arrival_contract") or {})["injection_dispatch_ns"])
    rows = [
        {
            "case_id": "injected_ttft_window",
            "prompt_id": lifecycle_id,
            "prefix_reuse_group": "none",
            "request_start_ns": int(injected["request_start_ns"]),
            "response_end_ns": first_token_ns,
            "status": injected["status"],
        },
        {
            "case_id": "resident_interference_window",
            "prompt_id": lifecycle_id,
            "prefix_reuse_group": "none",
            "request_start_ns": dispatch_ns,
            "response_end_ns": first_token_ns,
            "status": "success",
        },
    ]
    result_path = (
        artifact_dir
        / "runtime/r3e_profiler_windows"
        / lifecycle_id
        / "vllm/vllm_api_concurrency_result.json"
    )
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps({"rows": rows}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result_path


def _op_category(op_type: str) -> str:
    value = op_type.lower()
    if any(
        token in value
        for token in (
            "hcom",
            "hccl",
            "allreduce",
            "allgather",
            "reducescatter",
            "alltoall",
        )
    ):
        return "collective_communication"
    if any(token in value for token in ("matmul", "groupedmatmul", "gmm", "moe")):
        return "matmul_or_moe"
    if any(token in value for token in ("attention", "flashattention", "mla")):
        return "attention"
    if any(token in value for token in ("memcpy", "copy", "trans", "sync")):
        return "memory_transfer_or_sync"
    return "other"


def write_profiler_evidence(artifact_dir: Path) -> dict[str, Any]:
    explicit_roots: dict[str, Path] = {}
    for lifecycle_id in PROFILE_LIFECYCLE_IDS:
        request_window = _write_profiler_request_windows(artifact_dir, lifecycle_id)
        if request_window is None:
            continue
        explicit_roots[lifecycle_id] = (
            artifact_dir / "lifecycles" / lifecycle_id / "runtime/msprof"
        )
    analysis_dir = artifact_dir / "runtime/r3e_msprof_analysis"
    result = analyze_request_device_aggregate(
        run_id=TASK_ID,
        source_artifact_dir=artifact_dir / "runtime/r3e_profiler_windows",
        artifact_dir=analysis_dir,
        modes=PROFILE_LIFECYCLE_IDS,
        explicit_roots=explicit_roots,
        top_n_op_types=40,
        workers=1,
        skip_heavy_joins=False,
    )

    category_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    top_op_path = analysis_dir / "request_top_op_type_duration.tsv"
    if top_op_path.is_file():
        with top_op_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = (
                    str(row.get("mode")),
                    str(row.get("case_id")),
                    _op_category(str(row.get("op_type"))),
                )
                aggregate = category_rows.setdefault(
                    key,
                    {
                        "lifecycle_id": key[0],
                        "case_id": key[1],
                        "op_category": key[2],
                        "op_type_count": 0,
                        "task_row_count": 0,
                        "summed_duration_time": 0,
                    },
                )
                aggregate["op_type_count"] += 1
                aggregate["task_row_count"] += int(row.get("task_row_count") or 0)
                aggregate["summed_duration_time"] += int(
                    row.get("total_duration_time") or 0
                )
    compact_categories = list(category_rows.values())
    base._write_tsv(
        artifact_dir / "r3e_profiler_op_categories.tsv", compact_categories
    )

    request_rows: list[dict[str, Any]] = []
    request_summary_path = analysis_dir / "request_device_task_summary.tsv"
    if request_summary_path.is_file():
        with request_summary_path.open(encoding="utf-8", newline="") as handle:
            request_rows = list(csv.DictReader(handle, delimiter="\t"))
    base._write_tsv(
        artifact_dir / "r3e_profiler_request_device_summary.tsv", request_rows
    )

    profiler_complete = (
        result.get("overall_status") == "success"
        and all(
            row.get("aggregate_status") == "request_device_aggregate_available"
            for row in result.get("mode_summaries") or []
        )
        and len(result.get("mode_summaries") or []) == len(PROFILE_LIFECYCLE_IDS)
        and len(request_rows) == 2 * len(PROFILE_LIFECYCLE_IDS)
        and bool(compact_categories)
    )
    summary = {
        "task_id": TASK_ID,
        "schema": "p6_3c_r3e_msprof_request_window_attribution_v1",
        "profiler_lifecycle_ids": list(PROFILE_LIFECYCLE_IDS),
        "profiler_complete": profiler_complete,
        "mode_summaries": result.get("mode_summaries"),
        "request_device_summary_row_count": len(request_rows),
        "operator_category_row_count": len(compact_categories),
        "duration_sum_caveat": (
            "stream_overlap_means_summed_device_task_duration_is_diagnostic_not_wall_time"
        ),
        "performance_comparison_allowed": False,
        "raw_profiler_remains_server_local": True,
    }
    (artifact_dir / "r3e_profiler_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    # The mechanism claim comes from the three completed profiler-off host
    # lifecycles. Missing diagnostic profiler lifecycles must not erase it.
    mechanism = write_mechanism_evidence(artifact_dir, HOST_LIFECYCLE_IDS)
    host = write_host_timing_evidence(artifact_dir)
    profiler = write_profiler_evidence(artifact_dir)
    lifecycle_rows = base._lifecycle_rows(artifact_dir)  # noqa: SLF001
    startup_rows = base._startup_rows(artifact_dir)  # noqa: SLF001
    payload = base._payload_summary(artifact_dir)  # noqa: SLF001
    base._write_tsv(artifact_dir / "lifecycle_summary.tsv", lifecycle_rows)
    base._write_tsv(artifact_dir / "startup_resource_summary.tsv", startup_rows)
    (artifact_dir / "payload_identity_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    base._write_tsv(
        artifact_dir / "performance_mode_cell_summary.tsv",
        [{"diagnostic_track": "not_applicable", "reason": "no_pooled_performance_comparison"}],
    )
    base._write_tsv(
        artifact_dir / "performance_order_balanced_pairs.tsv",
        [{"diagnostic_track": "not_applicable", "reason": "no_order_balanced_performance_claim"}],
    )

    request_count = sum(int(row.get("request_count") or 0) for row in lifecycle_rows)
    successful_count = sum(
        int(row.get("successful_request_count") or 0) for row in lifecycle_rows
    )
    http_count = sum(int(row.get("http_request_count") or 0) for row in lifecycle_rows)
    lifecycle_complete = len(lifecycle_rows) == EXPECTED_MODEL_LIFECYCLES and all(
        row.get("lifecycle_exit_code") == "0"
        and int(row.get("request_count") or 0) == 10
        and int(row.get("successful_request_count") or 0) == 10
        and int(row.get("http_request_count") or 0) == 3
        and row.get("cleanup_status") == "clean"
        for row in lifecycle_rows
    )
    resolved_complete = all(
        row.get("resolved_enable_chunked_prefill") is True
        and row.get("resolved_enable_prefix_caching") is False
        and row.get("resolved_max_model_len") == MAX_MODEL_LEN
        and row.get("resolved_max_num_batched_tokens") == 12288
        and row.get("resolved_max_num_seqs") == MAX_NUM_SEQS
        and row.get("observer_enabled") is True
        for row in lifecycle_rows
    )
    profiler_mode_complete = all(
        _read_json(
            artifact_dir
            / "lifecycles"
            / row["lifecycle_id"]
            / "runtime/resolved_scheduler_config.json"
        ).get("profiler_enabled")
        is (row["evidence_track"] == "diagnostic_msprof")
        for row in LIFECYCLE_SCHEDULE
    )
    recovery = _read_json(artifact_dir / "resource_recovery_summary.json")
    cleanup_status = (
        (artifact_dir / "cleanup_status.txt").read_text(encoding="utf-8").strip()
        if (artifact_dir / "cleanup_status.txt").is_file()
        else "missing"
    )
    cleanup_complete = (
        recovery.get("keep_alive_restored_exact") is True
        and cleanup_status == "clean"
    )
    startup_complete = len(startup_rows) == EXPECTED_MODEL_LIFECYCLES and all(
        row.get("server_ready") is True for row in startup_rows
    )
    evidence_complete = all(
        (
            lifecycle_complete,
            resolved_complete,
            profiler_mode_complete,
            request_count == successful_count == EXPECTED_ENGINE_REQUESTS,
            http_count == EXPECTED_HTTP_REQUESTS,
            mechanism.get("full_prefill_sequence_gate_complete"),
            host.get("host_timing_complete"),
            profiler.get("profiler_complete"),
            payload.get("all_body_files_sha256_exact"),
            startup_complete,
            cleanup_complete,
        )
    )
    if not mechanism.get("full_prefill_sequence_gate_complete"):
        scientific = "latency_floor_mechanism_incomplete"
    elif not host.get("host_timing_complete") or not profiler.get("profiler_complete"):
        scientific = "latency_floor_attribution_incomplete"
    elif host.get("host_scheduler_and_update_dominant"):
        scientific = "host_scheduler_overhead_dominant"
    elif (
        host.get("mixed_engine_pipeline_fraction_at_least_0_80")
        and host.get("persistent_mixed_pipeline_target_insensitive")
    ):
        scientific = "mixed_step_floor_executor_path_supported"
    else:
        scientific = "target_sensitive_or_multifactor_execution_cost"

    grading = {
        "task_id": TASK_ID,
        "source_task_id": r3d.TASK_ID,
        "server_grade": (
            "complete_p6_3c_r3e_latency_floor_attribution"
            if evidence_complete
            else "incomplete_p6_3c_r3e_latency_floor_attribution"
        ),
        "evidence_status": "complete" if evidence_complete else "incomplete",
        "scientific_outcome": scientific,
        "lifecycles_complete": lifecycle_complete,
        "resolved_config_exact": resolved_complete,
        "profiler_mode_identity_complete": profiler_mode_complete,
        "request_count": request_count,
        "successful_request_count": successful_count,
        "expected_request_count": EXPECTED_ENGINE_REQUESTS,
        "http_request_count": http_count,
        "expected_http_request_count": EXPECTED_HTTP_REQUESTS,
        "mechanism_complete": mechanism.get("full_prefill_sequence_gate_complete"),
        "host_timing_complete": host.get("host_timing_complete"),
        "profiler_complete": profiler.get("profiler_complete"),
        "startup_complete": startup_complete,
        "cleanup_complete": cleanup_complete,
        "keep_alive_restore_exact": recovery.get("keep_alive_restored_exact"),
        "diagnostic_profiler_excluded_from_performance_claim": True,
        "scientific_contract_changed_from_r3d": True,
        "parent_r3d_outcome_preserved": (
            "persistent_prefill_tradeoff_no_candidate_within_bounds"
        ),
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "next_task_authorized": False,
        "universal_benefit_claimed": False,
    }
    (artifact_dir / "grading_inputs.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    outcome = {
        "task_id": TASK_ID,
        "source_task_id": r3d.TASK_ID,
        "scientific_outcome": scientific,
        "evidence_complete": evidence_complete,
        "host_attribution": host,
        "profiler_complete": profiler.get("profiler_complete"),
        "claim_boundary": "controlled_decode_resident_mixed_step_attribution_only",
    }
    (artifact_dir / "scientific_outcome.json").write_text(
        json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    environment = {
        "task_id": TASK_ID,
        "source_task_id": r3d.TASK_ID,
        "repo_head": base._git_output("rev-parse", "HEAD"),  # noqa: SLF001
        "repo_origin_main": base._git_output("rev-parse", "origin/main"),  # noqa: SLF001
        "workload_path": WORKLOAD_RELATIVE_PATH,
        "workload_sha256": _sha256(REPO_ROOT / WORKLOAD_RELATIVE_PATH),
        "runner_sha256": _sha256(Path(__file__)),
        "observer_sha256": _sha256(
            REPO_ROOT / "tools/inference_contracts/p6_3c_r3_decode_resident_observer.py"
        ),
        "capacity_contract": {
            "max_model_len": MAX_MODEL_LEN,
            "max_num_batched_tokens": 12288,
            "max_num_seqs": MAX_NUM_SEQS,
            "prefix_cache_enabled": False,
        },
        "host_lifecycles": list(HOST_LIFECYCLE_IDS),
        "diagnostic_msprof_lifecycles": list(PROFILE_LIFECYCLE_IDS),
        "generated_text_retained": False,
        "generated_token_ids_retained": False,
        "runtime_overlay_import_smoke": _read_json(
            artifact_dir / "runtime_overlay_preflight_smoke.json"
        ),
    }
    (artifact_dir / "environment_and_hashes.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    completed_lifecycle_count = sum(
        row.get("lifecycle_exit_code") == "0"
        and row.get("cleanup_status") == "clean"
        for row in lifecycle_rows
    )
    lines = [
        f"# {TASK_ID} 结果摘要",
        "",
        f"- evidence status: `{grading['evidence_status']}`",
        f"- scientific outcome: `{scientific}`",
        f"- lifecycles: `{completed_lifecycle_count}/{EXPECTED_MODEL_LIFECYCLES}`；请求：`{successful_count}/{EXPECTED_ENGINE_REQUESTS}`；HTTP：`{http_count}/{EXPECTED_HTTP_REQUESTS}`。",
        f"- host timing complete: `{host.get('host_timing_complete')}`；diagnostic msprof complete: `{profiler.get('profiler_complete')}`。",
        f"- mixed-step EngineCore pipeline span >=80%: `{host.get('mixed_engine_pipeline_fraction_at_least_0_80')}`；T128/T1024 mixed pipeline median ratio: `{host.get('persistent_t128_to_t1024_pipeline_median_ratio')}`。",
        "- EngineCore pipeline span includes execute/sample futures, queueing, host RPC, worker, device and synchronization; msprof rows are diagnostic attribution evidence, not a profiler-on performance comparison.",
        "- 结论只覆盖受控 decode-resident admission cliff；R3D 性能结论和原始 blocked 审计均保留。",
        "",
    ]
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    failure = artifact_dir / "first_failure_excerpt.txt"
    if evidence_complete:
        failure.write_text("none\n", encoding="utf-8")
    elif not failure.is_file():
        failure.write_text(
            f"scientific_outcome={scientific}\n"
            f"host_timing_complete={host.get('host_timing_complete')}\n"
            f"profiler_complete={profiler.get('profiler_complete')}\n"
            f"successful_request_count={successful_count}/{EXPECTED_ENGINE_REQUESTS}\n",
            encoding="utf-8",
        )
    return grading


BOUNDED_CANDIDATES = (
    "result_summary.md",
    "environment_and_hashes.json",
    "payload_identity_summary.json",
    "lifecycle_summary.tsv",
    "r3e_mechanism_summary.json",
    "r3e_mechanism_cells.tsv",
    "r3e_host_attribution.json",
    "r3e_host_phase_summary.tsv",
    "r3e_profiler_summary.json",
    "r3e_profiler_request_device_summary.tsv",
    "r3e_profiler_op_categories.tsv",
    "scientific_outcome.json",
    "grading_inputs.json",
    "startup_resource_summary.tsv",
    "runtime_overlay_preflight_smoke.json",
    "resource_recovery_summary.json",
    "cleanup_status.txt",
    "first_failure_excerpt.txt",
)


def _activate_contract() -> None:
    _bind_base_globals()
    base.BOUNDED_CANDIDATES = BOUNDED_CANDIDATES


def package_results(artifact_dir: Path) -> dict[str, Any]:
    _activate_contract()
    return base.package_results(artifact_dir)


def main(argv: list[str] | None = None) -> int:
    import argparse

    _activate_contract()
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
    host_gate = sub.add_parser("host-gate")
    host_gate.add_argument("--artifact-dir", type=Path, required=True)
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    package = sub.add_parser("package")
    package.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "prepare":
        base.prepare_artifacts(args.source_payload, args.artifact_dir, args.model_name)
        return 0
    if args.command == "run-mode":
        return base.execute_mode(
            args.artifact_dir,
            args.lifecycle_dir,
            args.base_url,
            args.server_pid,
            args.track,
            args.mode,
        )
    if args.command == "host-gate":
        mechanism = write_mechanism_evidence(args.artifact_dir, HOST_LIFECYCLE_IDS)
        host = write_host_timing_evidence(args.artifact_dir)
        return 0 if all(
            (
                mechanism.get("full_prefill_sequence_gate_complete"),
                host.get("host_timing_complete"),
            )
        ) else 3
    if args.command == "finalize":
        grading = finalize_artifacts(args.artifact_dir)
        return 0 if grading["evidence_status"] == "complete" else 2
    if args.command == "package":
        package_results(args.artifact_dir)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
