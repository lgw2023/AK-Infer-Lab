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
VLLM_BATCHED_PREFIX_HANDOFF = CONTRACT_DIR / "server_runtime_vllm_batched_prefix_smoke_handoff.md"
VLLM_API_CONCURRENCY_HANDOFF = CONTRACT_DIR / "server_runtime_vllm_api_concurrency_smoke_handoff.md"
VLLM_API_BURST_QUEUE_HANDOFF = CONTRACT_DIR / "server_runtime_vllm_api_burst_queue_smoke_handoff.md"
VLLM_API_CONTINUOUS16_MIXED_HANDOFF = CONTRACT_DIR / "server_runtime_vllm_api_continuous16_mixed_handoff.md"
VLLM_API_CONTINUOUS16_MIXED_RETRY_HANDOFF = (
    CONTRACT_DIR / "server_runtime_vllm_api_continuous16_mixed_retry_handoff.md"
)
VLLM_API_PREFIX_CACHE_AB_HANDOFF = CONTRACT_DIR / "server_runtime_vllm_api_prefix_cache_ab_handoff.md"
VLLM_API_MSPROF_SQLITE_WINDOW_ANALYSIS_HANDOFF = (
    CONTRACT_DIR / "server_runtime_vllm_api_msprof_sqlite_window_analysis_handoff.md"
)
VLLM_API_MSPROF_REQUEST_DEVICE_AGGREGATE_HANDOFF = (
    CONTRACT_DIR / "server_runtime_vllm_api_msprof_request_device_aggregate_handoff.md"
)
VLLM_API_MSPROF_REQUEST_DEVICE_AGGREGATE_FAST_HANDOFF = (
    CONTRACT_DIR / "server_runtime_vllm_api_msprof_request_device_aggregate_fast_handoff.md"
)
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


def test_vllm_batched_prefix_handoff_defines_required_boundaries():
    handoff = VLLM_BATCHED_PREFIX_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_vllm_batched_prefix_smoke_2026_0706_p1_017",
        "vLLM Batched Prefix Smoke",
        "VLLM_PLUGINS=ascend",
        "source `/usr/local/Ascend/cann-9.0.0/set_env.sh`",
        "source `/usr/local/Ascend/nnal/atb/set_env.sh`",
        "P007_prefix_a_first_cap4096_gen32",
        "P008_prefix_a_second_cap4096_gen32",
        "llm.generate([text_for_P007, text_for_P008]",
        "enable_prefix_caching=True",
        "candidate_only_no_runtime_hit_signal",
        "不安装、升级、卸载或修复任何包",
        "不运行 `vllm serve`",
        "不运行多 worker 并发客户端、burst 压测或连续到达流量",
        "不输出性能 benchmark、吞吐结论、瓶颈归因、优化建议、prefix cache 命中结论或 CANN device timeline pairing 结论",
    ]
    for text in required_text:
        assert text in handoff


def test_vllm_batched_prefix_runner_case_plan_is_bounded():
    from tools.inference_contracts.run_vllm_batched_prefix_smoke import VLLM_BATCHED_PREFIX_CASES

    assert len(VLLM_BATCHED_PREFIX_CASES) == 2
    assert max(case["cap_tokens"] for case in VLLM_BATCHED_PREFIX_CASES) == 4096
    assert max(case["max_new_tokens"] for case in VLLM_BATCHED_PREFIX_CASES) == 32
    assert {case["prompt_id"] for case in VLLM_BATCHED_PREFIX_CASES} == {"P007", "P008"}
    assert {case["prefix_reuse_group"] for case in VLLM_BATCHED_PREFIX_CASES} == {"prefix_group_a"}
    assert {case["batch_id"] for case in VLLM_BATCHED_PREFIX_CASES} == {"batch_prefix_a_0001"}


def test_vllm_api_concurrency_handoff_defines_required_boundaries():
    handoff = VLLM_API_CONCURRENCY_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_vllm_api_concurrency_smoke_2026_0706_p1_018",
        "vLLM OpenAI API server",
        "/v1/completions",
        "P007_api_prefix_first_cap4096_gen32",
        "P008_api_prefix_second_cap4096_gen32",
        "P012_api_continuous_candidate_cap4096_gen32",
        "3 个错开 100ms",
        "VLLM_PLUGINS=ascend",
        "source `/usr/local/Ascend/cann-9.0.0/set_env.sh`",
        "source `/usr/local/Ascend/nnal/atb/set_env.sh`",
        "不安装、升级、卸载或修复任何包",
        "不运行 benchmark、吞吐测试、压测或长时间服务",
        "不运行 8 请求 burst，不运行 16 请求 continuous batching workload",
        "不输出性能 benchmark、吞吐结论、调度效率结论、瓶颈归因、优化建议、prefix cache 命中结论或 CANN device timeline pairing 结论",
    ]
    for text in required_text:
        assert text in handoff


def test_vllm_api_concurrency_runner_case_plan_is_bounded():
    from tools.inference_contracts.run_vllm_api_concurrency_smoke import VLLM_API_CONCURRENCY_CASES

    assert len(VLLM_API_CONCURRENCY_CASES) == 3
    assert max(case["cap_tokens"] for case in VLLM_API_CONCURRENCY_CASES) == 4096
    assert max(case["max_new_tokens"] for case in VLLM_API_CONCURRENCY_CASES) == 32
    assert max(case["arrival_delay_ms"] for case in VLLM_API_CONCURRENCY_CASES) == 200
    assert {case["prompt_id"] for case in VLLM_API_CONCURRENCY_CASES} == {"P007", "P008", "P012"}
    assert {case["concurrency_group"] for case in VLLM_API_CONCURRENCY_CASES} == {
        "api_concurrency_smoke_0001"
    }


def test_vllm_api_burst_queue_handoff_defines_required_boundaries():
    handoff = VLLM_API_BURST_QUEUE_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_vllm_api_burst_queue_smoke_2026_0706_p1_019",
        "vLLM API Burst Queue Smoke",
        "/v1/completions",
        "--case-plan burst8",
        "P007_api_burst_prefix_first_cap4096_gen32",
        "P008_api_burst_prefix_second_cap4096_gen32",
        "P011_api_burst_001_cap4096_gen32",
        "P011_api_burst_002_cap4096_gen32",
        "P011_api_burst_003_cap4096_gen32",
        "P012_api_continuous_001_cap4096_gen32",
        "P012_api_continuous_002_cap4096_gen32",
        "P012_api_continuous_003_cap4096_gen32",
        "VLLM_PLUGINS=ascend",
        "source `/usr/local/Ascend/cann-9.0.0/set_env.sh`",
        "source `/usr/local/Ascend/nnal/atb/set_env.sh`",
        "不安装、升级、卸载或修复任何包",
        "不运行 16 请求 continuous workload",
        "不输出性能 benchmark、吞吐结论、调度效率结论、瓶颈归因、优化建议、prefix cache 命中结论或 CANN device timeline pairing 结论",
    ]
    for text in required_text:
        assert text in handoff


def test_vllm_api_burst_queue_runner_case_plan_is_bounded():
    from tools.inference_contracts.run_vllm_api_concurrency_smoke import (
        VLLM_API_BURST_QUEUE_CASES,
        VLLM_API_CONCURRENCY_CASES,
        VLLM_API_CONTINUOUS16_MIXED_CASES,
        select_cases,
    )

    assert select_cases("three_request_smoke") == VLLM_API_CONCURRENCY_CASES
    assert select_cases("burst8") == VLLM_API_BURST_QUEUE_CASES
    assert select_cases("continuous16_mixed") == VLLM_API_CONTINUOUS16_MIXED_CASES
    assert len(VLLM_API_BURST_QUEUE_CASES) == 8
    assert max(case["cap_tokens"] for case in VLLM_API_BURST_QUEUE_CASES) == 4096
    assert max(case["max_new_tokens"] for case in VLLM_API_BURST_QUEUE_CASES) == 32
    assert max(case["arrival_delay_ms"] for case in VLLM_API_BURST_QUEUE_CASES) == 700
    assert {case["prompt_id"] for case in VLLM_API_BURST_QUEUE_CASES} == {
        "P007",
        "P008",
        "P011",
        "P012",
    }
    assert {case["concurrency_group"] for case in VLLM_API_BURST_QUEUE_CASES} == {
        "api_burst_queue_smoke_0001"
    }


def test_vllm_api_continuous16_mixed_handoff_defines_required_boundaries():
    handoff = VLLM_API_CONTINUOUS16_MIXED_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_vllm_api_continuous16_mixed_2026_0706_p1_020",
        "vLLM API Continuous16 Mixed Smoke",
        "/v1/completions",
        "--case-plan continuous16_mixed",
        "P007_api_continuous16_prefix_first_cap8192_gen64",
        "P008_api_continuous16_prefix_second_cap8192_gen64",
        "P011_api_continuous16_burst_001_cap4096_gen64",
        "P012_api_continuous16_006_cap8192_gen64",
        "P003_api_continuous16_system_002_cap8192_gen64",
        "P009_api_continuous16_moe_002_cap8192_gen64",
        "vllm_api_server_stats_summary.tsv",
        "VLLM_PLUGINS=ascend",
        "source `/usr/local/Ascend/cann-9.0.0/set_env.sh`",
        "source `/usr/local/Ascend/nnal/atb/set_env.sh`",
        "不安装、升级、卸载或修复任何包",
        "不运行 benchmark、吞吐测试、压测或长时间服务",
        "不运行 full 16K/32K 或 full `P010=43216` tokens",
        "不输出性能 benchmark、吞吐结论、调度效率结论、瓶颈归因、优化建议或 CANN device timeline pairing 结论",
    ]
    for text in required_text:
        assert text in handoff


def test_vllm_api_continuous16_mixed_retry_handoff_defines_required_boundaries():
    handoff = VLLM_API_CONTINUOUS16_MIXED_RETRY_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_vllm_api_continuous16_mixed_retry_2026_0707_p1_021",
        "P1.20 的部分失败",
        "--max-model-len 9216",
        "AK_VLLM_MAX_MODEL_LEN=9216",
        "vllm_api_server_command.json",
        "run_context.txt",
        "不静默降低",
        "不删减 case",
        "不安装、升级、卸载或修复任何包",
        "不输出性能 benchmark、吞吐结论、调度效率结论、瓶颈归因、优化建议或 CANN device timeline pairing 结论",
    ]
    for text in required_text:
        assert text in handoff


def test_vllm_api_prefix_cache_ab_handoff_defines_required_boundaries():
    handoff = VLLM_API_PREFIX_CACHE_AB_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_vllm_api_prefix_cache_ab_2026_0707_p1_022",
        "prefix_cache_on",
        "prefix_cache_off",
        "--enable-prefix-caching",
        "--case-plan continuous16_mixed",
        "--max-model-len 9216",
        "P007_api_continuous16_prefix_first_cap8192_gen64",
        "P012_api_continuous16_006_cap8192_gen64",
        "P009_api_continuous16_moe_002_cap8192_gen64",
        "prefix_cache_ab_summary.tsv",
        "vllm_api_server_stats_summary.tsv",
        "AK_COMM_MAIL_TO=yilili1023@gmail.com",
        "VLLM_PLUGINS=ascend",
        "source `/usr/local/Ascend/cann-9.0.0/set_env.sh`",
        "source `/usr/local/Ascend/nnal/atb/set_env.sh`",
        "不安装、升级、卸载或修复任何包",
        "不运行 benchmark、吞吐测试、压测或长时间服务",
        "不启用 profiler 导出",
        "不输出性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因、优化建议或 CANN device timeline pairing 结论",
    ]
    for text in required_text:
        assert text in handoff


def test_vllm_api_msprof_sqlite_window_analysis_handoff_defines_required_boundaries():
    handoff = VLLM_API_MSPROF_SQLITE_WINDOW_ANALYSIS_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024",
        "runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023",
        "tools/inference_contracts/analyze_msprof_sqlite_windows.py",
        "request_window_summary.tsv",
        "profiler_sqlite_table_inventory.tsv",
        "profiler_time_range_summary.tsv",
        "request_profiler_overlap_summary.tsv",
        "profiler_group_count_summary.tsv",
        "msprof_sqlite_window_analysis_result.json",
        "mail_attachment_candidates.tsv",
        "70KB",
        "优先复用 P1.23 raw msprof",
        "如果 raw profiler 目录不存在",
        "不安装、升级、卸载或修复任何包",
        "不输出性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因或优化建议",
    ]
    for text in required_text:
        assert text in handoff


def test_vllm_api_msprof_request_device_aggregate_handoff_defines_required_boundaries():
    handoff = VLLM_API_MSPROF_REQUEST_DEVICE_AGGREGATE_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_vllm_api_msprof_request_device_aggregate_2026_0707_p1_025",
        "runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024",
        "runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023",
        "tools/inference_contracts/analyze_msprof_request_device_aggregate.py",
        "request_device_task_summary.tsv",
        "request_device_task_type_summary.tsv",
        "request_top_op_type_duration.tsv",
        "request_ai_core_metric_summary.tsv",
        "prefix_cache_mode_request_delta.tsv",
        "prefix_pair_candidate_delta.tsv",
        "msprof_request_device_aggregate_result.json",
        "mail_attachment_candidates.tsv",
        "70KB",
        "优先复用 P1.23 raw msprof",
        "不安装、升级、卸载或修复任何包",
        "不重启 vLLM API server",
        "不输出性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因或优化建议",
    ]
    for text in required_text:
        assert text in handoff


def test_vllm_api_msprof_request_device_aggregate_fast_handoff_defines_required_boundaries():
    handoff = VLLM_API_MSPROF_REQUEST_DEVICE_AGGREGATE_FAST_HANDOFF.read_text(encoding="utf-8")

    required_text = [
        "runtime_vllm_api_msprof_request_device_aggregate_fast_2026_0707_p1_025b",
        "runtime_vllm_api_msprof_request_device_aggregate_2026_0707_p1_025",
        "runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024",
        "runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023",
        "bulk_temp_window_join_parallel_modes",
        "--workers 2",
        "--skip-heavy-joins",
        "timeout 45m",
        "timeout 15m",
        "analysis_mode",
        "full_analysis_exit_code",
        "fallback_analysis_exit_code",
        "request_device_task_summary.tsv",
        "request_device_task_type_summary.tsv",
        "request_top_op_type_duration.tsv",
        "request_ai_core_metric_summary.tsv",
        "prefix_cache_mode_request_delta.tsv",
        "prefix_pair_candidate_delta.tsv",
        "msprof_request_device_aggregate_result.json",
        "old_p1_25_process_status.txt",
        "mail_attachment_candidates.tsv",
        "70KB",
        "不重启 vLLM API server",
        "不运行新的模型推理请求",
        "不安装、升级、卸载或修复任何包",
        "不终止非 P1.25 离线聚合进程",
        "不把 raw counter delta 解释为性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因或优化建议",
    ]
    for text in required_text:
        assert text in handoff


def test_vllm_api_continuous16_mixed_runner_case_plan_is_bounded():
    from tools.inference_contracts.run_vllm_api_concurrency_smoke import (
        VLLM_API_CONTINUOUS16_MIXED_CASES,
        default_max_model_len_for,
    )

    assert len(VLLM_API_CONTINUOUS16_MIXED_CASES) == 16
    assert max(case["cap_tokens"] for case in VLLM_API_CONTINUOUS16_MIXED_CASES) == 8192
    assert max(case["max_new_tokens"] for case in VLLM_API_CONTINUOUS16_MIXED_CASES) == 64
    assert max(case["arrival_delay_ms"] for case in VLLM_API_CONTINUOUS16_MIXED_CASES) == 2400
    assert default_max_model_len_for("three_request_smoke") == 6144
    assert default_max_model_len_for("burst8") == 6144
    assert default_max_model_len_for("continuous16_mixed") == 9216
    assert {case["prompt_id"] for case in VLLM_API_CONTINUOUS16_MIXED_CASES} == {
        "P003",
        "P007",
        "P008",
        "P009",
        "P011",
        "P012",
    }
    assert {case["concurrency_group"] for case in VLLM_API_CONTINUOUS16_MIXED_CASES} == {
        "api_continuous16_mixed_0001"
    }


def test_vllm_api_server_stats_parser_extracts_vllm_log_samples(tmp_path):
    from tools.inference_contracts.run_vllm_api_concurrency_smoke import write_server_stats_summary

    log_path = tmp_path / "vllm_api_server.log"
    output_path = tmp_path / "vllm_api_server_stats_summary.tsv"
    log_path.write_text(
        "(APIServer pid=1) INFO Engine 000: Avg prompt throughput: 745.0 tokens/s, "
        "Avg generation throughput: 3.3 tokens/s, Running: 8 reqs, Waiting: 1 reqs, "
        "GPU KV cache usage: 4.0%, Prefix cache hit rate: 39.1%\n",
        encoding="utf-8",
    )

    summary = write_server_stats_summary(log_path, output_path)

    assert summary == {
        "sample_count": 1,
        "max_running_reqs": 8,
        "max_waiting_reqs": 1,
        "max_kv_cache_usage_pct": 4.0,
        "max_prefix_cache_hit_rate_pct": 39.1,
    }
    assert "prefix_cache_hit_rate_pct" in output_path.read_text(encoding="utf-8")


def test_msprof_sqlite_window_analyzer_extracts_request_overlap(tmp_path):
    import json
    import sqlite3

    from tools.inference_contracts.analyze_msprof_sqlite_windows import analyze_msprof_windows

    source_dir = tmp_path / "source"
    mode_dir = source_dir / "msprof_prefix_cache_on" / "vllm"
    mode_dir.mkdir(parents=True)
    result_path = mode_dir / "vllm_api_concurrency_result.json"
    result_path.write_text(
        json.dumps(
            {
                "status": "success",
                "rows": [
                    {
                        "case_id": "case_a",
                        "prompt_id": "P007",
                        "prefix_reuse_group": "prefix_group_a",
                        "arrival_delay_ms": 0,
                        "cap_tokens": 8192,
                        "max_new_tokens": 64,
                        "input_token_count": 5972,
                        "generated_token_count": 64,
                        "request_start_ns": 1000,
                        "response_end_ns": 3000,
                        "client_wall_us": 2,
                        "status": "success",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    msprof_root = tmp_path / "prof"
    msprof_root.mkdir()
    msprof_db = msprof_root / "msprof_test.db"
    with sqlite3.connect(msprof_db) as conn:
        conn.execute("CREATE TABLE CANN_API(startNs INTEGER, endNs INTEGER, type TEXT)")
        conn.execute("INSERT INTO CANN_API VALUES (1200, 1800, 'aclrtLaunchKernel')")
        conn.execute("CREATE TABLE TASK(startNs INTEGER, endNs INTEGER)")
        conn.execute("INSERT INTO TASK VALUES (1300, 1700)")

    device_db_dir = msprof_root / "device_6" / "sqlite"
    device_db_dir.mkdir(parents=True)
    device_db = device_db_dir / "ascend_task.db"
    with sqlite3.connect(device_db) as conn:
        conn.execute(
            "CREATE TABLE AscendTask(start_time INTEGER, duration INTEGER, device_task_type TEXT)"
        )
        conn.execute("INSERT INTO AscendTask VALUES (1400, 200, 'AI_CORE')")

    output_dir = tmp_path / "out"
    result = analyze_msprof_windows(
        run_id="test_run",
        source_artifact_dir=source_dir,
        artifact_dir=output_dir,
        modes=("msprof_prefix_cache_on",),
        explicit_roots={"msprof_prefix_cache_on": msprof_root},
    )

    assert result["overall_status"] == "success"
    summary = result["mode_summaries"][0]
    assert summary["sqlite_db_count"] == 2
    assert summary["direct_overlap_candidate_count"] == 3
    assert summary["time_alignment_status"] == "direct_request_window_overlap"
    assert "CANN_API" in (output_dir / "profiler_time_range_summary.tsv").read_text(encoding="utf-8")
    assert "AI_CORE" in (output_dir / "profiler_group_count_summary.tsv").read_text(encoding="utf-8")


def test_msprof_request_device_aggregate_extracts_request_level_metrics(tmp_path):
    import csv
    import json
    import sqlite3

    from tools.inference_contracts.analyze_msprof_request_device_aggregate import (
        analyze_request_device_aggregate,
    )

    source_dir = tmp_path / "source"
    mode_dir = source_dir / "msprof_prefix_cache_on" / "vllm"
    mode_dir.mkdir(parents=True)
    (mode_dir / "vllm_api_concurrency_result.json").write_text(
        json.dumps(
            {
                "status": "success",
                "rows": [
                    {
                        "case_id": "case_a",
                        "prompt_id": "P007",
                        "prefix_reuse_group": "prefix_group_a",
                        "arrival_delay_ms": 0,
                        "cap_tokens": 8192,
                        "max_new_tokens": 64,
                        "input_token_count": 5972,
                        "generated_token_count": 64,
                        "request_start_ns": 1000,
                        "response_end_ns": 3000,
                        "client_wall_us": 2,
                        "status": "success",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    sqlite_dir = tmp_path / "prof" / "device_6" / "sqlite"
    sqlite_dir.mkdir(parents=True)
    ai_core_db = sqlite_dir / "ai_core_op_summary.db"
    with sqlite3.connect(ai_core_db) as conn:
        conn.execute(
            "CREATE TABLE task_time("
            "task_id INTEGER, stream_id INTEGER, start_time INTEGER, duration_time INTEGER, "
            "wait_time INTEGER, task_type TEXT, index_id INTEGER, model_id INTEGER, "
            "batch_id INTEGER, subtask_id INTEGER)"
        )
        conn.execute("INSERT INTO task_time VALUES (1, 7, 1200, 100, 3, 'AI_CORE', 9, 1, 0, 0)")
        conn.execute("INSERT INTO task_time VALUES (2, 7, 1500, 200, 5, 'AI_CORE', 10, 1, 0, 0)")
        conn.execute("INSERT INTO task_time VALUES (3, 7, 5000, 100, 1, 'AI_CORE', 11, 1, 0, 0)")
        conn.execute(
            "CREATE TABLE ge_summary("
            "model_id INTEGER, task_id INTEGER, stream_id INTEGER, op_name TEXT, op_type TEXT, "
            "task_type TEXT, index_id INTEGER, batch_id INTEGER, context_id INTEGER)"
        )
        conn.execute("INSERT INTO ge_summary VALUES (1, 1, 7, 'matmul_a', 'MatMulV2', 'AI_CORE', 9, 0, 0)")
        conn.execute("INSERT INTO ge_summary VALUES (1, 2, 7, 'slice_a', 'Slice', 'AI_CORE', 10, 0, 0)")
        conn.execute(
            "CREATE TABLE ai_core_metrics("
            "task_id INTEGER, stream_id INTEGER, subtask_id INTEGER, batch_id INTEGER, "
            "aic_total_time REAL, aiv_total_time REAL, aic_mac_time REAL, "
            "aiv_vec_time REAL, aic_mac_ratio_extra REAL, aiv_vec_ratio REAL)"
        )
        conn.execute("INSERT INTO ai_core_metrics VALUES (1, 7, 0, 0, 10, 20, 3, 4, 0.1, 0.2)")
        conn.execute("INSERT INTO ai_core_metrics VALUES (2, 7, 0, 0, 30, 40, 5, 6, 0.3, 0.4)")

    ascend_task_db = sqlite_dir / "ascend_task.db"
    with sqlite3.connect(ascend_task_db) as conn:
        conn.execute(
            "CREATE TABLE AscendTask("
            "start_time INTEGER, duration INTEGER, device_task_type TEXT, host_task_type TEXT)"
        )
        conn.execute("INSERT INTO AscendTask VALUES (1300, 100, 'AI_CORE', 'aclrtLaunchKernel')")

    output_dir = tmp_path / "out"
    result = analyze_request_device_aggregate(
        run_id="test_request_device",
        source_artifact_dir=source_dir,
        artifact_dir=output_dir,
        modes=("msprof_prefix_cache_on",),
        explicit_roots={"msprof_prefix_cache_on": tmp_path / "prof"},
    )

    assert result["overall_status"] == "success"
    request_rows = list(
        csv.DictReader((output_dir / "request_device_task_summary.tsv").open(encoding="utf-8"), delimiter="\t")
    )
    assert request_rows[0]["task_row_count"] == "2"
    assert request_rows[0]["total_duration_time"] == "300"
    assert "MatMulV2" in (output_dir / "request_top_op_type_duration.tsv").read_text(encoding="utf-8")
    assert "AI_CORE" in (output_dir / "request_device_task_type_summary.tsv").read_text(encoding="utf-8")
    metric_rows = list(
        csv.DictReader((output_dir / "request_ai_core_metric_summary.tsv").open(encoding="utf-8"), delimiter="\t")
    )
    assert metric_rows[0]["aic_total_time_sum"] == "40"


def test_msprof_request_device_aggregate_parallel_modes_builds_mode_delta(tmp_path):
    import csv
    import json
    import sqlite3

    from tools.inference_contracts.analyze_msprof_request_device_aggregate import (
        analyze_request_device_aggregate,
    )

    source_dir = tmp_path / "source"
    for mode in ("msprof_prefix_cache_on", "msprof_prefix_cache_off"):
        mode_dir = source_dir / mode / "vllm"
        mode_dir.mkdir(parents=True)
        (mode_dir / "vllm_api_concurrency_result.json").write_text(
            json.dumps(
                {
                    "status": "success",
                    "rows": [
                        {
                            "case_id": "case_a",
                            "prompt_id": "P007",
                            "prefix_reuse_group": "prefix_group_a",
                            "arrival_delay_ms": 0,
                            "cap_tokens": 8192,
                            "max_new_tokens": 64,
                            "input_token_count": 5972,
                            "generated_token_count": 64,
                            "request_start_ns": 1000,
                            "response_end_ns": 3000,
                            "client_wall_us": 2,
                            "status": "success",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    roots = {
        "msprof_prefix_cache_on": tmp_path / "prof_on",
        "msprof_prefix_cache_off": tmp_path / "prof_off",
    }
    for mode, root in roots.items():
        sqlite_dir = root / "device_6" / "sqlite"
        sqlite_dir.mkdir(parents=True)
        duration = 100 if mode == "msprof_prefix_cache_on" else 250
        with sqlite3.connect(sqlite_dir / "ai_core_op_summary.db") as conn:
            conn.execute(
                "CREATE TABLE task_time("
                "task_id INTEGER, stream_id INTEGER, start_time INTEGER, duration_time INTEGER, "
                "wait_time INTEGER, task_type TEXT, index_id INTEGER, model_id INTEGER, "
                "batch_id INTEGER, subtask_id INTEGER)"
            )
            conn.execute(f"INSERT INTO task_time VALUES (1, 7, 1200, {duration}, 3, 'AI_CORE', 9, 1, 0, 0)")

    output_dir = tmp_path / "out"
    result = analyze_request_device_aggregate(
        run_id="test_request_device_parallel",
        source_artifact_dir=source_dir,
        artifact_dir=output_dir,
        explicit_roots=roots,
        workers=2,
    )

    assert result["overall_status"] == "success"
    assert result["workers"] == 2
    delta_rows = list(
        csv.DictReader((output_dir / "prefix_cache_mode_request_delta.tsv").open(encoding="utf-8"), delimiter="\t")
    )
    assert delta_rows[0]["delta_total_duration_time_on_minus_off"] == "-150"


def test_msprof_request_device_aggregate_skip_heavy_joins_keeps_base_summary(tmp_path):
    import csv
    import json
    import sqlite3

    from tools.inference_contracts.analyze_msprof_request_device_aggregate import (
        analyze_request_device_aggregate,
    )

    source_dir = tmp_path / "source"
    mode_dir = source_dir / "msprof_prefix_cache_on" / "vllm"
    mode_dir.mkdir(parents=True)
    (mode_dir / "vllm_api_concurrency_result.json").write_text(
        json.dumps(
            {
                "status": "success",
                "rows": [
                    {
                        "case_id": "case_a",
                        "prompt_id": "P007",
                        "prefix_reuse_group": "prefix_group_a",
                        "arrival_delay_ms": 0,
                        "cap_tokens": 8192,
                        "max_new_tokens": 64,
                        "input_token_count": 5972,
                        "generated_token_count": 64,
                        "request_start_ns": 1000,
                        "response_end_ns": 3000,
                        "client_wall_us": 2,
                        "status": "success",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    sqlite_dir = tmp_path / "prof" / "device_6" / "sqlite"
    sqlite_dir.mkdir(parents=True)
    with sqlite3.connect(sqlite_dir / "ai_core_op_summary.db") as conn:
        conn.execute(
            "CREATE TABLE task_time("
            "task_id INTEGER, stream_id INTEGER, start_time INTEGER, duration_time INTEGER, "
            "wait_time INTEGER, task_type TEXT, index_id INTEGER, model_id INTEGER, "
            "batch_id INTEGER, subtask_id INTEGER)"
        )
        conn.execute("INSERT INTO task_time VALUES (1, 7, 1200, 100, 3, 'AI_CORE', 9, 1, 0, 0)")
        conn.execute(
            "CREATE TABLE ge_summary("
            "model_id INTEGER, task_id INTEGER, stream_id INTEGER, op_type TEXT, index_id INTEGER, batch_id INTEGER)"
        )
        conn.execute("INSERT INTO ge_summary VALUES (1, 1, 7, 'MatMulV2', 9, 0)")
        conn.execute(
            "CREATE TABLE ai_core_metrics("
            "task_id INTEGER, stream_id INTEGER, subtask_id INTEGER, batch_id INTEGER, aic_total_time REAL)"
        )
        conn.execute("INSERT INTO ai_core_metrics VALUES (1, 7, 0, 0, 10)")

    output_dir = tmp_path / "out"
    result = analyze_request_device_aggregate(
        run_id="test_request_device_skip_heavy",
        source_artifact_dir=source_dir,
        artifact_dir=output_dir,
        modes=("msprof_prefix_cache_on",),
        explicit_roots={"msprof_prefix_cache_on": tmp_path / "prof"},
        skip_heavy_joins=True,
    )

    assert result["overall_status"] == "success"
    assert result["heavy_joins_skipped"] is True
    request_rows = list(
        csv.DictReader((output_dir / "request_device_task_summary.tsv").open(encoding="utf-8"), delimiter="\t")
    )
    assert request_rows[0]["task_row_count"] == "1"
    assert (output_dir / "request_top_op_type_duration.tsv").read_text(encoding="utf-8") == ""
    assert (output_dir / "request_ai_core_metric_summary.tsv").read_text(encoding="utf-8") == ""
