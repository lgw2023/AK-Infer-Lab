from __future__ import annotations

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


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)


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


def _require_members(
    report: ValidationReport,
    label: str,
    actual_values: list[str] | set[str],
    required_values: list[str],
) -> None:
    missing = sorted(set(required_values) - set(actual_values))
    if missing:
        report.errors.append(f"{label} missing values: {missing}")
