from pathlib import Path

from tools.inference_contracts.validation import (
    REQUIRED_EVENT_FIELDS,
    REQUIRED_JOIN_KEYS,
    REQUIRED_WORKLOAD_FIELDS,
    load_yaml,
    validate_trace_fixture,
    validate_contract_dir,
)
from tools.observability_profile.catalog import build_field_catalog


CONTRACT_DIR = Path("工作记录与进度笔记本/p1_inference_contracts")
SERVER_TRACE_SMOKE_HANDOFF = CONTRACT_DIR / "server_runtime_trace_smoke_handoff.md"
LONG_WORKLOAD_MANIFEST = CONTRACT_DIR / "workload_long_manifest.yaml"
LONG_PROMPT_TRACE_SMOKE_HANDOFF = CONTRACT_DIR / "server_runtime_long_prompt_trace_smoke_handoff.md"
LONG_PROMPT_TRACE_MATRIX_HANDOFF = CONTRACT_DIR / "server_runtime_long_prompt_matrix_handoff.md"
LONG_PROMPT_ENVELOPE_HANDOFF = CONTRACT_DIR / "server_runtime_long_prompt_envelope_handoff.md"
VLLM_ENGINE_SINGLE_REQUEST_HANDOFF = CONTRACT_DIR / "server_runtime_vllm_engine_single_request_smoke_handoff.md"
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


def test_long_workload_manifest_materializes_prompt_paths():
    manifest = load_yaml(LONG_WORKLOAD_MANIFEST)
    prompts = manifest["prompts"]
    prompt_ids = {prompt["prompt_id"] for prompt in prompts}
    measured_tokens = {
        "P000": 1184,
        "P001": 1764,
        "P002": 5556,
        "P003": 11144,
        "P004": 11656,
        "P005": 21569,
        "P006": 22490,
        "P007": 5972,
        "P008": 5975,
        "P009": 11094,
        "P010": 43216,
        "P011": 5972,
        "P012": 11128,
    }

    assert manifest["base_manifest"] == "workload_manifest.yaml"
    assert manifest["token_policy"] == "server_tokenizer_calibrated"
    assert manifest["token_calibration"]["status"] == "success"
    assert manifest["token_calibration"]["run_id"] == "runtime_long_prompt_calibration_2026_0706_p1_012"
    assert manifest["token_calibration"]["tokenizer_class"] == "Qwen2Tokenizer"
    assert manifest["token_calibration"]["success_prompt_count"] == 13
    assert manifest["token_calibration"]["bucket_miss_count"] == 13
    assert prompt_ids == {f"P{index:03d}" for index in range(13)}

    for prompt in prompts:
        assert set(REQUIRED_WORKLOAD_FIELDS).issubset(prompt)
        assert prompt["materialization_policy"] == "deterministic_static_blocks"
        assert prompt["measured_prompt_tokens_qwen3_5_4b"] == measured_tokens[prompt["prompt_id"]]
        assert prompt["calibration_bucket_status_qwen3_5_4b"] == "above_range"
        assert prompt["truncated_prompt_tokens_4096"] <= 4096
        assert prompt["truncated_prompt_tokens_8192"] <= 8192
        assert prompt["truncated_prompt_tokens_16384"] <= 16384
        assert prompt["truncated_prompt_tokens_32768"] <= 32768
        assert prompt["shape_fixture_measured_prompt_tokens_qwen3_5_4b"] > 0
        assert prompt["prompt_path"].startswith("prompts_long/")
        assert prompt["base_prompt_path"].startswith("prompts/")

        prompt_path = CONTRACT_DIR / prompt["prompt_path"]
        assert prompt_path.is_file()
        text = prompt_path.read_text(encoding="utf-8")
        assert "deterministic static prompt fixture" in text
        assert len(text) == prompt["materialized_char_count"]
        assert len(text) >= prompt["estimated_prompt_tokens"] * 3

    assert any(prompt["context_len_bucket"] == "32K" for prompt in prompts)
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


def test_minimal_runtime_trace_fixture_validates_without_errors():
    report = validate_trace_fixture(CONTRACT_DIR / "fixtures/minimal_runtime_trace.jsonl")

    assert report.errors == []


def test_trace_fixture_links_required_profile_pairs():
    trace_path = CONTRACT_DIR / "fixtures/minimal_runtime_trace.jsonl"
    report = validate_trace_fixture(trace_path)
    events = report.metadata["events"]

    request_phases = {
        event["phase"]
        for event in events
        if event["resource_scope"] == "request_runtime_profile"
    }
    operator_layers = {
        event["layer_id"]
        for event in events
        if event["resource_scope"] == "operator_timeline_profile"
        and event["phase"] in {"prefill", "decode"}
    }
    object_ids = {
        event["object_id"]
        for event in events
        if event["resource_scope"] == "state_object_profile"
        and event["object_type"] in {"kv", "prefix"}
    }
    copy_object_ids = {
        event["object_id"]
        for event in events
        if event["resource_scope"] == "transfer_overlap_profile" and event["event_type"] == "span_end"
    }

    assert {"enqueue", "prefill", "decode"}.issubset(request_phases)
    assert 0 in operator_layers
    assert {"kv:req_0001:L00", "prefix:group_a"}.issubset(object_ids)
    assert "kv:req_0001:L00" in copy_object_ids


def test_trace_fixture_reports_missing_join_keys(tmp_path):
    trace_path = tmp_path / "broken_trace.jsonl"
    trace_path.write_text(
        '{"schema_version":"p1.1","event_id":"evt_missing","timestamp_ns":1,'
        '"time_base":"host_monotonic_ns","trace_id":"trace_missing","request_id":"req_missing",'
        '"session_id":"session_missing","phase":"prefill","event_type":"span_start",'
        '"resource_scope":"operator_timeline_profile","layer_id":"","op_name":"attention",'
        '"kernel_name":"","stream_id":"","device_id":"npu:0","object_type":"kv",'
        '"object_id":"","source_tier":"hbm","target_tier":"hbm","bytes_read":0,'
        '"bytes_write":0,"latency_us":0,"queue_wait_us":0,"overlap_ratio":0.0,'
        '"policy_decision":"none","hit_or_miss":"unknown","stall_reason":"unknown",'
        '"evidence_source":"fixture","artifact_path":"fixtures/broken_trace.jsonl"}\n',
        encoding="utf-8",
    )

    report = validate_trace_fixture(trace_path)

    assert any("event evt_missing missing join key: layer_id" in error for error in report.errors)
    assert any("event evt_missing missing join key: object_id" in error for error in report.errors)
    assert any("event evt_missing missing join key: stream_id" in error for error in report.errors)


def test_server_runtime_trace_smoke_handoff_defines_required_boundaries():
    handoff = SERVER_TRACE_SMOKE_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_trace_smoke_2026_0705_p1_001",
        "git pull --ff-only",
        "fixtures/minimal_runtime_trace.jsonl",
        "trace_id",
        "request_id",
        "layer_id",
        "object_id",
        "stream_id",
        "host_monotonic_ns",
        "cann_device_timeline",
        "不要在服务器上修改、提交或 push 项目代码",
        "不要发送 `.env`",
        "回传要求",
        "成功口径",
    ]
    for text in required_text:
        assert text in handoff


def test_long_prompt_trace_smoke_handoff_defines_required_boundaries():
    handoff = LONG_PROMPT_TRACE_SMOKE_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_long_prompt_trace_smoke_2026_0706_p1_013",
        "Qwen3.5-4B + transformers + torch_npu",
        "P002@4096",
        "P003@8192",
        "P007@4096",
        "P008@4096",
        "不运行 vLLM",
        "不安装、升级、卸载或修复任何包",
        "不运行 16K/32K full prompt",
        "不能声称 CANN device timeline pairing 已完成",
    ]
    for text in required_text:
        assert text in handoff


def test_long_prompt_trace_matrix_handoff_defines_required_boundaries():
    handoff = LONG_PROMPT_TRACE_MATRIX_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_long_prompt_trace_matrix_2026_0706_p1_014",
        "Qwen3.5-4B + transformers + torch_npu",
        "P000-P012",
        "P000_cap4096",
        "P010_cap8192",
        "cap 为 8192 tokens",
        "AK_LONG_PROMPT_MATRIX_ENABLE_PROFILER=1",
        "不运行 vLLM",
        "不安装、升级、卸载或修复任何包",
        "不运行 16K/32K full prompt",
        "不能声称 CANN device timeline pairing 已完成",
    ]
    for text in required_text:
        assert text in handoff


def test_long_prompt_envelope_handoff_defines_required_boundaries():
    handoff = LONG_PROMPT_ENVELOPE_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_long_prompt_envelope_decode_2026_0706_p1_015",
        "Qwen3.5-4B + transformers + torch_npu",
        "P002_cap4096_gen32",
        "P006_cap12288_gen32",
        "P010_cap16384_gen32",
        "P012_cap8192_gen128",
        "max_new_tokens",
        "不运行 vLLM",
        "不安装、升级、卸载或修复任何包",
        "不运行 full 32K",
        "不启用 profiler 导出",
        "不能声称 CANN device timeline pairing 已完成",
    ]
    for text in required_text:
        assert text in handoff


def test_long_prompt_envelope_runner_case_plan_is_bounded():
    from tools.inference_contracts.run_long_prompt_envelope import ENVELOPE_CASES

    assert len(ENVELOPE_CASES) == 8
    assert max(case["cap_tokens"] for case in ENVELOPE_CASES) == 16384
    assert max(case["max_new_tokens"] for case in ENVELOPE_CASES) == 128
    assert {case["prompt_id"] for case in ENVELOPE_CASES} == {
        "P002",
        "P003",
        "P005",
        "P006",
        "P007",
        "P008",
        "P010",
        "P012",
    }


def test_vllm_engine_single_request_handoff_defines_required_boundaries():
    handoff = VLLM_ENGINE_SINGLE_REQUEST_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_vllm_engine_single_request_smoke_2026_0706_p1_016",
        "vLLM/vLLM-Ascend engine smoke",
        "P002_cap4096_gen32",
        "P003_cap8192_gen32",
        "LLM.generate",
        "不安装、升级、卸载或修复任何包",
        "不运行 `vllm serve`",
        "不运行并发、burst、continuous batching 或 prefix cache",
        "不启用 profiler 导出",
        "不能声称 vLLM 并发、prefix cache、continuous batching、性能瓶颈或 CANN device timeline pairing 已经验证",
    ]
    for text in required_text:
        assert text in handoff


def test_vllm_engine_single_request_runner_case_plan_is_bounded():
    from tools.inference_contracts.run_vllm_engine_single_request_smoke import VLLM_SMOKE_CASES

    assert len(VLLM_SMOKE_CASES) == 2
    assert max(case["cap_tokens"] for case in VLLM_SMOKE_CASES) == 8192
    assert max(case["max_new_tokens"] for case in VLLM_SMOKE_CASES) == 32
    assert {case["prompt_id"] for case in VLLM_SMOKE_CASES} == {"P002", "P003"}
