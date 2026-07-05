from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


REQUIRED_FILES = [
    "unified_event_schema.yaml",
    "inference_stage_schema.yaml",
    "hardware_resource_schema.yaml",
    "state_object_event_schema.yaml",
    "runtime_queue_trace_schema.yaml",
    "copy_overlap_trace_schema.yaml",
    "bottleneck_reason.yaml",
    "workload_manifest.yaml",
    "experiment_card_template.yaml",
    "runtime_hook_join_key_design.md",
    "server_runtime_trace_smoke_handoff.md",
    "fixtures/minimal_runtime_trace.jsonl",
]

REQUIRED_EVENT_FIELDS = [
    "schema_version",
    "event_id",
    "timestamp_ns",
    "time_base",
    "trace_id",
    "request_id",
    "session_id",
    "phase",
    "event_type",
    "resource_scope",
    "layer_id",
    "op_name",
    "kernel_name",
    "stream_id",
    "device_id",
    "object_type",
    "object_id",
    "source_tier",
    "target_tier",
    "bytes_read",
    "bytes_write",
    "latency_us",
    "queue_wait_us",
    "overlap_ratio",
    "policy_decision",
    "hit_or_miss",
    "stall_reason",
    "evidence_source",
    "artifact_path",
]

REQUIRED_PHASES = [
    "enqueue",
    "tokenize",
    "prefill",
    "decode",
    "attention",
    "kv_restore",
    "expert_prefetch",
    "mlp_or_moe",
    "sampling",
    "detokenize",
    "cleanup",
]

REQUIRED_OBJECT_TYPES = [
    "weight",
    "kv",
    "prefix",
    "expert",
    "activation",
    "workspace",
    "logits",
]

REQUIRED_BOTTLENECK_REASONS = [
    "queue_wait",
    "long_prefill",
    "decode_compute_bound",
    "hbm_capacity_pressure",
    "hbm_bandwidth_pressure",
    "h2d_d2h_exposed_copy",
    "ssd_restore_slow",
    "kv_prefix_miss",
    "expert_miss",
    "expert_prefetch_late",
    "cpu_scheduler_wait",
    "cpu_tokenizer_or_sampling",
    "sync_barrier_wait",
    "profiler_unaligned",
    "unknown",
]

REQUIRED_WORKLOAD_FIELDS = [
    "prompt_id",
    "scenario",
    "context_len_bucket",
    "estimated_prompt_tokens",
    "expected_output_tokens",
    "max_new_tokens",
    "arrival_pattern",
    "concurrency_group",
    "prefix_reuse_group",
    "shared_prefix_tokens",
    "reuse_distance",
    "turn_count",
    "contains_code",
    "contains_tool_output_text",
    "tool_text_tokens",
    "tool_output_type",
    "workspace_size_bucket",
    "prompt_path",
    "notes",
]

REQUIRED_JOIN_KEYS = [
    "trace_id",
    "request_id",
    "layer_id",
    "object_id",
    "stream_id",
]

EVENT_TYPES = [
    "span_start",
    "span_end",
    "point",
    "metric_sample",
    "decision",
    "lifecycle",
]

RESOURCE_SCOPES = [
    "request_runtime_profile",
    "scheduler_policy_profile",
    "operator_timeline_profile",
    "npu_hbm_profile",
    "cpu_dram_profile",
    "transfer_overlap_profile",
    "ssd_io_profile",
    "state_object_profile",
    "kv_prefix_profile",
    "moe_expert_profile",
    "microbench_profile",
]


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def validate_contract_dir(base_dir: Path) -> ValidationReport:
    report = ValidationReport()
    for filename in REQUIRED_FILES:
        if not (base_dir / filename).is_file():
            report.errors.append(f"missing required file: {filename}")

    if report.errors:
        return report

    _validate_unified_event_schema(base_dir, report)
    _validate_bottleneck_reasons(base_dir, report)
    _validate_workload_manifest(base_dir, report)
    _validate_runtime_hook_design(base_dir, report)
    _merge_report(report, validate_trace_fixture(base_dir / "fixtures/minimal_runtime_trace.jsonl"))
    return report


def validate_trace_fixture(path: Path) -> ValidationReport:
    report = ValidationReport()
    events = _load_jsonl_events(path, report)
    report.metadata["events"] = events
    if report.errors:
        return report

    for index, event in enumerate(events, start=1):
        event_id = str(event.get("event_id", f"line {index}"))
        _validate_trace_event_fields(event, event_id, report)
        _validate_trace_event_enums(event, event_id, report)
        _validate_trace_join_keys(event, event_id, report)

    _validate_trace_profile_links(events, report)
    return report


def _validate_unified_event_schema(base_dir: Path, report: ValidationReport) -> None:
    schema = load_yaml(base_dir / "unified_event_schema.yaml")
    fields = schema.get("fields", [])
    if not isinstance(fields, list):
        report.errors.append("unified_event_schema.yaml fields must be a list")
        return

    field_names = {field.get("name") for field in fields if isinstance(field, dict)}
    missing_fields = sorted(set(REQUIRED_EVENT_FIELDS) - field_names)
    if missing_fields:
        report.errors.append(f"unified_event_schema missing fields: {missing_fields}")

    _require_members(
        report,
        "unified_event_schema phase_enum",
        schema.get("phase_enum", []),
        REQUIRED_PHASES,
    )
    _require_members(
        report,
        "unified_event_schema object_type_enum",
        schema.get("object_type_enum", []),
        REQUIRED_OBJECT_TYPES,
    )


def _validate_bottleneck_reasons(base_dir: Path, report: ValidationReport) -> None:
    reasons = load_yaml(base_dir / "bottleneck_reason.yaml")
    entries = reasons.get("bottleneck_reasons", [])
    if not isinstance(entries, list):
        report.errors.append("bottleneck_reason.yaml bottleneck_reasons must be a list")
        return

    names = [entry.get("name") for entry in entries if isinstance(entry, dict)]
    missing = sorted(set(REQUIRED_BOTTLENECK_REASONS) - set(names))
    extra = sorted(set(names) - set(REQUIRED_BOTTLENECK_REASONS))
    if missing:
        report.errors.append(f"bottleneck_reason missing reasons: {missing}")
    if extra:
        report.errors.append(f"bottleneck_reason has unexpected reasons: {extra}")


def _validate_workload_manifest(base_dir: Path, report: ValidationReport) -> None:
    manifest = load_yaml(base_dir / "workload_manifest.yaml")
    prompts = manifest.get("prompts", [])
    if not isinstance(prompts, list):
        report.errors.append("workload_manifest.yaml prompts must be a list")
        return

    prompt_ids = {prompt.get("prompt_id") for prompt in prompts if isinstance(prompt, dict)}
    expected_prompt_ids = {f"P{index:03d}" for index in range(13)}
    if prompt_ids != expected_prompt_ids:
        report.errors.append(f"workload prompt ids must be P000-P012, got {sorted(prompt_ids)}")

    for prompt in prompts:
        if not isinstance(prompt, dict):
            report.errors.append("workload prompt entries must be mappings")
            continue
        missing_fields = sorted(set(REQUIRED_WORKLOAD_FIELDS) - set(prompt))
        if missing_fields:
            report.errors.append(f"{prompt.get('prompt_id', '<unknown>')} missing {missing_fields}")
        prompt_path = prompt.get("prompt_path")
        if not isinstance(prompt_path, str) or not (base_dir / prompt_path).is_file():
            report.errors.append(f"{prompt.get('prompt_id', '<unknown>')} prompt_path is missing")

    buckets = {prompt.get("context_len_bucket") for prompt in prompts if isinstance(prompt, dict)}
    _require_members(report, "workload context_len_bucket", buckets, ["512", "1K", "4K", "8K", "16K", "32K"])

    scenarios = {prompt.get("scenario") for prompt in prompts if isinstance(prompt, dict)}
    _require_members(
        report,
        "workload scenario",
        scenarios,
        ["W5_repeated_prefix", "W7_burst_queue", "W7_continuous_batching"],
    )

    prefix_group_count = sum(
        1
        for prompt in prompts
        if isinstance(prompt, dict) and prompt.get("prefix_reuse_group") == "prefix_group_a"
    )
    if prefix_group_count < 2:
        report.errors.append("workload must contain at least two prefix_group_a prompts")

    if not any(isinstance(prompt, dict) and prompt.get("turn_count", 0) > 1 for prompt in prompts):
        report.errors.append("workload must contain at least one multi-turn prompt")


def _validate_runtime_hook_design(base_dir: Path, report: ValidationReport) -> None:
    design = (base_dir / "runtime_hook_join_key_design.md").read_text(encoding="utf-8")
    for key in REQUIRED_JOIN_KEYS:
        if key not in design:
            report.errors.append(f"runtime hook design missing join key: {key}")


def _load_jsonl_events(path: Path, report: ValidationReport) -> list[dict[str, Any]]:
    if not path.is_file():
        report.errors.append(f"missing trace fixture: {path}")
        return []

    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError as exc:
                report.errors.append(f"{path}:{line_number} invalid JSON: {exc.msg}")
                continue
            if not isinstance(event, dict):
                report.errors.append(f"{path}:{line_number} must contain a JSON object")
                continue
            events.append(event)

    if not events:
        report.errors.append(f"{path} must contain at least one event")
    return events


def _validate_trace_event_fields(
    event: dict[str, Any],
    event_id: str,
    report: ValidationReport,
) -> None:
    missing_fields = sorted(set(REQUIRED_EVENT_FIELDS) - set(event))
    if missing_fields:
        report.errors.append(f"event {event_id} missing fields: {missing_fields}")


def _validate_trace_event_enums(
    event: dict[str, Any],
    event_id: str,
    report: ValidationReport,
) -> None:
    _require_value(report, f"event {event_id} phase", event.get("phase"), REQUIRED_PHASES)
    _require_value(report, f"event {event_id} event_type", event.get("event_type"), EVENT_TYPES)
    _require_value(
        report,
        f"event {event_id} resource_scope",
        event.get("resource_scope"),
        RESOURCE_SCOPES,
    )
    object_type = event.get("object_type")
    if object_type is not None:
        _require_value(
            report,
            f"event {event_id} object_type",
            object_type,
            REQUIRED_OBJECT_TYPES,
        )


def _validate_trace_join_keys(
    event: dict[str, Any],
    event_id: str,
    report: ValidationReport,
) -> None:
    for key in ["trace_id", "request_id"]:
        if _is_missing(event.get(key)):
            report.errors.append(f"event {event_id} missing join key: {key}")

    resource_scope = event.get("resource_scope")
    object_type = event.get("object_type")
    if resource_scope in {"operator_timeline_profile", "state_object_profile", "transfer_overlap_profile"}:
        for key in ["layer_id", "stream_id"]:
            if _is_missing(event.get(key)):
                report.errors.append(f"event {event_id} missing join key: {key}")

    if resource_scope in {"state_object_profile", "transfer_overlap_profile"} or object_type in REQUIRED_OBJECT_TYPES:
        if _is_missing(event.get("object_id")):
            report.errors.append(f"event {event_id} missing join key: object_id")


def _validate_trace_profile_links(
    events: list[dict[str, Any]],
    report: ValidationReport,
) -> None:
    scopes = {event.get("resource_scope") for event in events}
    _require_members(
        report,
        "trace fixture resource_scope",
        scopes,
        [
            "request_runtime_profile",
            "operator_timeline_profile",
            "state_object_profile",
            "transfer_overlap_profile",
        ],
    )

    request_pairs = {
        (event.get("trace_id"), event.get("request_id"))
        for event in events
        if event.get("resource_scope") == "request_runtime_profile"
    }
    non_request_pairs = {
        (event.get("trace_id"), event.get("request_id"))
        for event in events
        if event.get("resource_scope") != "request_runtime_profile"
    }
    if request_pairs and non_request_pairs and not request_pairs.intersection(non_request_pairs):
        report.errors.append("trace fixture must share trace_id/request_id across profiles")

    state_object_ids = {
        event.get("object_id")
        for event in events
        if event.get("resource_scope") == "state_object_profile" and not _is_missing(event.get("object_id"))
    }
    copy_object_ids = {
        event.get("object_id")
        for event in events
        if event.get("resource_scope") == "transfer_overlap_profile" and not _is_missing(event.get("object_id"))
    }
    missing_copy_links = sorted(copy_object_ids - state_object_ids)
    if missing_copy_links:
        report.errors.append(
            f"copy events reference object_id without state object event: {missing_copy_links}"
        )

    operator_layers = {
        event.get("layer_id")
        for event in events
        if event.get("resource_scope") == "operator_timeline_profile"
        and not _is_missing(event.get("layer_id"))
    }
    state_layers = {
        event.get("layer_id")
        for event in events
        if event.get("resource_scope") == "state_object_profile"
        and not _is_missing(event.get("layer_id"))
    }
    missing_state_layers = sorted(operator_layers - state_layers)
    if missing_state_layers:
        report.errors.append(
            f"operator events reference layer_id without state object event: {missing_state_layers}"
        )


def _require_members(
    report: ValidationReport,
    label: str,
    actual_values: list[str] | set[str],
    required_values: list[str],
) -> None:
    missing = sorted(set(required_values) - set(actual_values))
    if missing:
        report.errors.append(f"{label} missing values: {missing}")


def _require_value(
    report: ValidationReport,
    label: str,
    actual_value: Any,
    allowed_values: list[str],
) -> None:
    if actual_value not in allowed_values:
        report.errors.append(f"{label} has unexpected value: {actual_value}")


def _is_missing(value: Any) -> bool:
    return value is None or value == ""


def _merge_report(target: ValidationReport, source: ValidationReport) -> None:
    target.errors.extend(source.errors)
    target.metadata.update(source.metadata)
