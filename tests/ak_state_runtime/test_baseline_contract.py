from pathlib import Path

import yaml


CONTRACT_PATH = Path(
    "benchmarks/deepseek_v4_flash/p8/p8_baseline_contract.yaml"
)
ADAPTER_SMOKE_PATH = Path(
    "benchmarks/deepseek_v4_flash/workloads/"
    "p8_1_vllm_ascend_observe_only_adapter_smoke.yaml"
)
OFFICIAL_MTP_CONTRACT_PATH = Path(
    "benchmarks/deepseek_v4_flash/p8/p8_official_mtp_baseline_contract.yaml"
)


def test_frozen_degraded_baseline_opens_only_the_observe_only_adapter() -> None:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["schema_name"] == "ak_p8_baseline_contract"
    assert contract["schema_version"] == "0.1.0"
    assert contract["contract_status"] == "frozen_degraded"
    assert contract["claim_ceiling"] == "selected_workload_runtime_cell"
    assert contract["selected_workload"] == {
        "model_id": "deepseek-ai/DeepSeek-V4-Flash-w8a8-mtp",
        "request_success": True,
        "successful_cell": "base_no_mtp_graph_maxseq1_tokenizer_mro_fixed",
        "validated": True,
    }
    assert contract["gate"]["baseline_freeze"] == (
        "frozen_degraded_no_mtp_4096_64"
    )
    assert contract["gate"]["real_vllm_ascend_adapter"] == (
        "open_observe_only"
    )
    assert contract["adapter"]["implementation_status"] == (
        "observe_only_implemented_local_validation_passed"
    )
    assert contract["adapter"]["mode"] == "observe_only"
    assert contract["adapter"]["payload_move_allowed"] is False
    assert contract["adapter"]["placement_mutation_allowed"] is False


def test_frozen_baseline_records_the_successful_runtime_cell_and_prerequisites() -> None:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    runtime = contract["runtime_baseline"]

    assert runtime["versions"] == {
        "vllm": "0.22.1",
        "vllm_ascend": "0.22.1rc1",
        "cann": "9.0.0",
        "pytorch": "2.10.0",
        "torch_npu": "2.10.0",
        "triton_ascend": "3.2.1",
    }
    assert runtime["target_commits"] == {
        "vllm": "0decac0d96c42b49572498019f0a0e3600f50398",
        "vllm_ascend": "5f6faa0cb8830f667266f3b8121cd1383606f2a1",
    }
    assert runtime["required_plugins"] == [
        "ascend",
        "ascend_kv_connector",
        "ascend_model_loader",
        "ascend_service_profiling",
        "ascend_model",
    ]
    assert runtime["worker_process_model"] == "spawn"
    assert runtime["cann_pythonpath_policy"] == (
        "clear_before_source_then_preserve_exactly_for_parent_and_spawn"
    )

    evidence = {item["evidence_id"]: item for item in contract["evidence"]}
    assert set(evidence) == {
        "source_capability_probe_v0221",
        "installed_content_provenance",
        "official_plugin_activation",
        "fresh_process_worker_memory_snapshot",
        "cann_acl_parent_spawn_path",
        "deepseek_v4_token_ids_4096_validated",
        "w8a8_no_mtp_graph_server_ready",
        "w8a8_successful_request",
    }
    for evidence_id in (
        "source_capability_probe_v0221",
        "installed_content_provenance",
        "official_plugin_activation",
        "fresh_process_worker_memory_snapshot",
        "cann_acl_parent_spawn_path",
        "deepseek_v4_token_ids_4096_validated",
        "w8a8_no_mtp_graph_server_ready",
        "w8a8_successful_request",
    ):
        assert evidence[evidence_id]["status"] == "passed"
    assert evidence["w8a8_successful_request"]["status"] == "passed"
    assert evidence["w8a8_successful_request"][
        "selected_workload_validated"
    ] is True
    assert evidence["deepseek_v4_token_ids_4096_validated"]["result"] == {
        "tokenizer_loader": "vllm.tokenizers.deepseek_v4.DeepseekV4Tokenizer",
        "tokenizer_runtime_class": "CachedDSV4TokenizersBackend",
        "tokenizer_runtime_mro_contains_dsv4_backend": True,
        "generated_token_count": 4096,
        "tokenizer_size": 129283,
        "min_token_id": 16,
        "max_token_id": 90868,
        "all_token_ids_in_vocab": True,
        "payload_artifact_written": False,
        "http_requests_dispatched": 0,
    }
    assert evidence["w8a8_no_mtp_graph_server_ready"]["result"] == {
        "mtp_enabled": False,
        "server_ready": True,
        "main_model_graph_capture": "summary_reported_success_all_eight_ranks",
        "http_requests_dispatched": 0,
        "successful_requests": 0,
        "first_failure_stage": "client_tokenizer_construction_before_http_dispatch",
    }


def test_pending_baseline_contract_excludes_mixed_checkpoint() -> None:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["excluded_paths"] == [
        {
            "path_id": "mixed_fp8_fp4_checkpoint",
            "reason": "ascend_910b1_soc_does_not_support_required_customize_dtype",
            "adapter_work_authorized": False,
        }
    ]


def test_official_mtp_baseline_promotes_only_the_accepted_4096_64_cell() -> None:
    contract = yaml.safe_load(
        OFFICIAL_MTP_CONTRACT_PATH.read_text(encoding="utf-8")
    )

    assert contract["schema_name"] == "ak_p8_baseline_contract"
    assert contract["schema_version"] == "0.2.0"
    assert contract["contract_status"] == "frozen_official"
    assert contract["claim_ceiling"] == "selected_workload_observe_only_cell"
    assert contract["historical_degraded_contract"]["preserved"] is True
    assert contract["selected_workload"] == {
        "model_id": "deepseek-ai/DeepSeek-V4-Flash-w8a8-mtp",
        "request_success": True,
        "successful_cell": "p6_1_short_prefill_4096_64_c1",
        "validated": True,
    }
    cell = contract["runtime_baseline"]["successful_cell"]
    assert cell["grade"] == "green_mtp_unprofiled_baseline"
    assert cell["tensor_parallel_size"] == 8
    assert cell["expert_parallel"] is True
    assert cell["mtp_enabled"] is True
    assert cell["num_speculative_tokens"] == 1
    assert cell["enable_chunked_prefill"] is True
    assert cell["enable_prefix_caching"] is True
    assert cell["cudagraph_mode"] == "FULL_DECODE_ONLY"
    assert cell["max_model_len"] == 135168
    assert cell["max_num_batched_tokens"] == 4096
    assert cell["max_num_seqs"] == 1
    assert cell["input_tokens"] == 4096
    assert cell["output_tokens"] == 64
    assert contract["gate"]["baseline_freeze"] == (
        "frozen_official_mtp_4096_64_c1"
    )
    assert contract["gate"]["real_vllm_ascend_adapter"] == "open_observe_only"
    assert contract["adapter"]["payload_move_allowed"] is False
    assert contract["adapter"]["placement_mutation_allowed"] is False
    assert contract["claim_boundary"]["performance_comparison_allowed"] is False
    assert contract["claim_boundary"]["p8_2_or_offload_authorized"] is False


def test_p8_1_adapter_smoke_reuses_only_the_frozen_degraded_cell() -> None:
    workload = yaml.safe_load(ADAPTER_SMOKE_PATH.read_text(encoding="utf-8"))

    assert workload["task_id"] == (
        "p8_1_deepseek_v4_flash_vllm_ascend_observe_only_trace_2026_0712"
    )
    assert workload["frozen_baseline"]["contract_status"] == "frozen_degraded"
    assert workload["frozen_baseline"]["successful_cell"] == (
        "base_no_mtp_graph_maxseq1_tokenizer_mro_fixed"
    )
    assert workload["runtime_environment"]["visible_devices"] == "0,1,2,3,4,5,6,7"
    assert workload["runtime_fixed"]["speculative_mtp"] == "disabled"
    assert workload["runtime_fixed"]["enforce_eager"] is False
    assert workload["request_plan"]["request_count"] == 1
    assert workload["request_plan"]["input_tokens"] == 4096
    assert workload["request_plan"]["output_tokens"] == 64
    assert workload["observation_contract"]["adapter_mode"] == "observe_only"
    assert workload["observation_contract"]["runtime_imports_allowed"] is False
    assert workload["observation_contract"]["payload_fields_allowed"] is False
    assert workload["observation_contract"]["transfer_observation"]["required"] is False
    assert workload["acceptance"]["trace_validation_errors"] == 0
    assert workload["acceptance"]["placement_decision_count"] == 1
    assert workload["acceptance"]["every_decision_executed"] is False
    assert workload["stop_policy"]["no_profiler"] is True
    assert workload["stop_policy"]["no_offload"] is True
    assert workload["execution_state"]["server_handoff"] == "deferred_preflight"
    assert workload["execution_state"]["server_result"] == "not_executed"
    assert workload["execution_state"]["superseded_active_handoff_by"] == (
        "p6_0_deepseek_v4_flash_w8a8_no_mtp_degraded_stabilization_2026_0713"
    )
