from pathlib import Path

from tools.inference_contracts.validation import (
    REQUIRED_EVENT_FIELDS,
    REQUIRED_JOIN_KEYS,
    REQUIRED_WORKLOAD_FIELDS,
    load_yaml,
    validate_contract_dir,
)
from tools.observability_profile.catalog import build_field_catalog


CONTRACT_DIR = Path("工作记录与进度笔记本/p1_inference_contracts")
EXPECTED_PHASES = {
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
}
EXPECTED_OBJECT_TYPES = {
    "weight",
    "kv",
    "prefix",
    "expert",
    "activation",
    "workspace",
    "logits",
}
EXPECTED_BOTTLENECK_REASONS = {
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
}


def test_missing_contract_dir_reports_schema_errors(tmp_path):
    report = validate_contract_dir(tmp_path)

    assert any("missing required file: unified_event_schema.yaml" in error for error in report.errors)
    assert any("missing required file: workload_manifest.yaml" in error for error in report.errors)


def test_p1_contract_assets_validate_without_errors():
    report = validate_contract_dir(CONTRACT_DIR)

    assert report.errors == []


def test_unified_event_schema_declares_minimum_fields_and_enums():
    schema = load_yaml(CONTRACT_DIR / "unified_event_schema.yaml")
    field_names = {field["name"] for field in schema["fields"]}

    assert set(REQUIRED_EVENT_FIELDS).issubset(field_names)
    assert set(schema["phase_enum"]) == EXPECTED_PHASES
    assert set(schema["object_type_enum"]) == EXPECTED_OBJECT_TYPES


def test_bottleneck_reason_enum_matches_p1_plan():
    reasons = load_yaml(CONTRACT_DIR / "bottleneck_reason.yaml")
    reason_names = {reason["name"] for reason in reasons["bottleneck_reasons"]}

    assert reason_names == EXPECTED_BOTTLENECK_REASONS


def test_workload_manifest_has_required_prompts_and_coverage():
    manifest = load_yaml(CONTRACT_DIR / "workload_manifest.yaml")
    prompts = manifest["prompts"]
    prompt_ids = {prompt["prompt_id"] for prompt in prompts}

    assert prompt_ids == {f"P{index:03d}" for index in range(13)}
    for prompt in prompts:
        assert set(REQUIRED_WORKLOAD_FIELDS).issubset(prompt)
        assert (CONTRACT_DIR / prompt["prompt_path"]).is_file()

    assert {"512", "1K", "4K", "8K", "16K", "32K"}.issubset(
        {prompt["context_len_bucket"] for prompt in prompts}
    )
    assert "W5_repeated_prefix" in {prompt["scenario"] for prompt in prompts}
    assert "W7_burst_queue" in {prompt["scenario"] for prompt in prompts}
    assert "W7_continuous_batching" in {prompt["scenario"] for prompt in prompts}
    assert any(prompt["turn_count"] > 1 for prompt in prompts)
    assert sum(1 for prompt in prompts if prompt["prefix_reuse_group"] == "prefix_group_a") >= 2


def test_runtime_hook_design_names_required_join_keys():
    design = (CONTRACT_DIR / "runtime_hook_join_key_design.md").read_text(encoding="utf-8")

    for key in REQUIRED_JOIN_KEYS:
        assert key in design
    assert "request_runtime_profile + operator_timeline_profile" in design
    assert "state_object_profile + transfer_overlap_profile" in design
    assert "moe_expert_profile + operator_timeline_profile" in design
    assert "不下发服务器任务" in design


def test_event_schema_evidence_sources_map_to_observability_catalog():
    schema = load_yaml(CONTRACT_DIR / "unified_event_schema.yaml")
    catalog_profiles = {field["profile"] for field in build_field_catalog()}

    for source in schema["evidence_sources"]:
        assert source["profile"] in catalog_profiles
