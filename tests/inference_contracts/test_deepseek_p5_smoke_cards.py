from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = REPO_ROOT / "benchmarks" / "deepseek_v4_flash"


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict)
    return data


def test_p5_readiness_card_records_w8a8_route_and_no_mtp_tokenizer_mro_retry_task():
    card = load_yaml(BENCHMARK_DIR / "p5_readiness_card.yaml")

    assert card["experiment_id"] == "p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry"
    assert card["scenario"] == "w8a8_eight_card_no_mtp_tokenizer_mro_retry_authorized"
    assert card["target_runtime"]["container_or_conda"] == "host_conda"
    assert card["target_runtime"]["vllm_version"] == "0.22.1+empty"
    assert card["target_runtime"]["vllm_ascend_version"] == "0.22.1rc1"
    assert card["target_runtime"]["torch_npu_version"] == "2.10.0"
    assert card["mixed_checkpoint_final_result"]["probe_grade"] == "diagnostic_yellow_acl_path_fixed"
    assert card["mixed_checkpoint_final_result"]["acl_path_gate"] == "diagnostic_green_acl_path_gate"
    assert card["mixed_checkpoint_final_result"]["shards_loaded"] == 46
    assert card["mixed_checkpoint_final_result"]["first_failure_stage"] == "process_weights_after_loading"
    assert card["mixed_checkpoint_final_result"]["first_failure"] == "customize_dtype_is_not_supported_by_the_current_soc_version"
    assert card["route_decision"]["decision"] == "stop_mixed_fp8_fp4_and_use_w8a8_only"
    assert card["route_decision"]["build_mixed_checkpoint_adapter"] is False
    assert card["route_decision"]["selected_model_object_id"] == "deepseek_v4_flash_w8a8_mtp_modelscope"
    assert card["prior_eight_card_result"]["task_status"] == "red_deterministic_mtp_dsa_cp_graph_capture"
    assert card["prior_eight_card_result"]["model_shards_loaded"] == 70
    assert card["prior_eight_card_result"]["successful_requests"] == 0
    assert card["prior_no_mtp_result"]["task_status"] == (
        "red_graph_ready_request_client_tokenizer_error"
    )
    assert card["prior_no_mtp_result"]["server_ready"] is True
    assert card["prior_no_mtp_result"]["main_model_graph_capture"] == "summary_reported_success_all_eight_ranks"
    assert card["prior_no_mtp_result"]["successful_requests"] == 0
    assert card["prior_no_mtp_result"]["http_requests_dispatched"] == 0
    assert card["prior_tokenizer_retry_result"]["task_status"] == (
        "red_client_tokenizer_class_assertion"
    )
    assert card["prior_tokenizer_retry_result"]["tokenizer_runtime_class"] == (
        "CachedDSV4TokenizersBackend"
    )
    assert card["prior_tokenizer_retry_result"]["tokenizer_runtime_mro_contains_dsv4_backend"] is True
    assert card["prior_tokenizer_retry_result"]["generated_token_count"] == 4096
    assert card["prior_tokenizer_retry_result"]["all_token_ids_in_vocab"] is True
    assert card["prior_tokenizer_retry_result"]["payload_artifact_written"] is False
    assert card["prior_tokenizer_retry_result"]["successful_requests"] == 0
    assert card["authorized_runtime_gate"]["task_id"] == (
        "p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712"
    )
    assert card["authorized_runtime_gate"]["visible_devices"] == "0,1,2,3,4,5,6,7"
    assert card["authorized_runtime_gate"]["authorization_date"] == "2026-07-12"
    assert card["authorized_runtime_gate"]["developer_to_server_ready"] is False
    assert card["successful_no_mtp_result"]["task_status"] == (
        "yellow_no_mtp_graph_request_success"
    )
    assert card["successful_no_mtp_result"]["successful_requests"] == 1
    assert card["successful_no_mtp_result"]["generated_token_count"] == 64
    assert card["successful_no_mtp_result"]["mtp_enabled"] is False
    assert card["completed_eight_card_smoke"]["visible_devices"] == "0,1,2,3,4,5,6,7"
    assert card["completed_eight_card_smoke"]["model_object_id"] == "deepseek_v4_flash_w8a8_mtp_modelscope"
    assert card["completed_eight_card_smoke"]["quantization_argument"] == "ascend"
    assert card["completed_eight_card_smoke"]["resource_gate"] == (
        "authorized_but_execute_only_if_all_eight_devices_healthy_idle_and_conflict_free"
    )
    assert card["completed_eight_card_smoke"]["input_tokens"] == 4096
    assert card["completed_eight_card_smoke"]["output_tokens"] == 64
    assert card["completed_eight_card_smoke"]["max_num_seqs"] == 1
    assert card["completed_eight_card_smoke"]["client_tokenizer"] == (
        "vllm.tokenizers.deepseek_v4.DeepseekV4Tokenizer"
    )
    assert card["completed_eight_card_smoke"]["client_tokenizer_runtime_identity_check"] == (
        "mro_contains_dsv4_backend"
    )
    assert card["completed_eight_card_smoke"]["profiles"] == [
        "base_no_mtp_graph_maxseq1_tokenizer_mro_fixed"
    ]
    assert card["features"]["mtp"] == "disabled_for_failure_isolation"

    paths = {item["model_object_id"]: item["server_model_path"] for item in card["model_objects"]}
    assert paths["deepseek_v4_flash_w8a8_mtp_modelscope"] == "/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp"
    assert paths["deepseek_v4_flash_official_hf"] == "/data/node0_disk1/Public/DeepSeek-V4-Flash"


def test_model_registry_promotes_w8a8_and_retires_mixed_checkpoint_on_910b1():
    registry = load_yaml(BENCHMARK_DIR / "deepseek_v4_flash_model_objects.yaml")
    objects = {item["model_object_id"]: item for item in registry["model_objects"]}

    w8a8 = objects["deepseek_v4_flash_w8a8_mtp_modelscope"]
    assert w8a8["server_inventory"]["shard_count"] == 70
    assert w8a8["server_inventory"]["weight_bytes"] == 300013759966
    assert w8a8["server_inventory"]["weight_gib"] == 279.41
    assert w8a8["model_role"] == "project_primary_runtime_object"
    assert w8a8["intended_runtime"]["quantization"] == "ascend"
    assert "p5_8card_context_ladder_smoke_authorized" in w8a8["expected_scenarios"]

    smaller = objects["deepseek_v4_flash_official_hf"]
    assert smaller["server_inventory"]["shard_count"] == 46
    assert smaller["server_inventory"]["weight_bytes"] == 159617149040
    assert smaller["server_inventory"]["weight_gib"] == 148.66
    assert smaller["model_role"] == "retired_for_current_910b1_execution_by_project_decision"
    assert smaller["intended_runtime"]["runtime"] == "none_on_current_910b1_route"
    assert "loaded_46_of_46" in smaller["server_inventory"]["inventory_status"]
    assert all(scenario.startswith("historical_") for scenario in smaller["expected_scenarios"])

    assert "The project primary runtime object is now the W8A8-MTP checkpoint." in registry["global_boundaries"]


def test_p5_context_ladder_workload_preserves_official_startup_flags_and_degrade_order():
    workload = load_yaml(BENCHMARK_DIR / "workloads" / "p5_8card_context_ladder.yaml")

    assert workload["workload_id"] == "p5_8card_context_ladder_smoke"
    assert workload["model_object_id"] == "deepseek_v4_flash_w8a8_mtp_modelscope"
    assert workload["server_model_path"] == "/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp"
    assert workload["runtime_reference"]["max_model_len"] == 135168
    assert workload["runtime_reference"]["tensor_parallel_size"] == 8
    assert workload["runtime_reference"]["enable_expert_parallel"] is True
    assert workload["runtime_reference"]["quantization"] == "ascend"
    assert workload["runtime_reference"]["explicit_quantization_argument"] == "required"
    assert workload["runtime_reference"]["enable_prefix_caching"] is True
    assert workload["runtime_reference"]["enable_chunked_prefill"] is True
    assert workload["runtime_reference"]["additional_config"]["enable_flashcomm1"] is True
    assert workload["runtime_reference"]["additional_config"]["enable_dsa_cp"] is True
    assert workload["runtime_reference"]["speculative_mtp"]["method"] == "mtp"
    assert workload["resource_gate"]["required_visible_devices"] == "0,1,2,3,4,5,6,7"
    assert workload["resource_gate"]["user_confirmed_scope"] is True
    assert workload["resource_gate"]["authorization_date"] == "2026-07-12"
    assert workload["runtime_environment"]["vllm_ascend"] == "0.22.1rc1"
    assert workload["request_plan"]["context_ladder_tokens"] == [4096, 32768, 65536, 98304, 131072]
    assert workload["request_plan"]["output_len_tokens"] == 64
    assert workload["degrade_policy"]["max_num_seqs_order"] == [16, 4, 1]
    assert workload["degrade_policy"]["disable_mtp_after_max_num_seqs_exhausted"] is True


def test_p5_no_mtp_isolation_keeps_one_request_and_conditional_eager_fallback():
    workload = load_yaml(BENCHMARK_DIR / "workloads" / "p5_8card_no_mtp_isolation.yaml")

    assert workload["workload_id"] == "p5_8card_no_mtp_isolation"
    assert workload["prior_result"]["grade"] == "red_deterministic_mtp_dsa_cp_graph_capture"
    assert workload["prior_result"]["model_shards_loaded"] == 70
    assert workload["request_plan"]["input_tokens"] == 4096
    assert workload["request_plan"]["output_tokens"] == 64
    assert workload["runtime_fixed"]["max_num_seqs"] == 1
    assert workload["runtime_fixed"]["tensor_parallel_size"] == 8
    assert workload["runtime_fixed"]["enable_expert_parallel"] is True
    assert workload["runtime_fixed"]["quantization"] == "ascend"
    assert workload["runtime_fixed"]["speculative_mtp"] == "disabled"
    assert [profile["name"] for profile in workload["profiles"]] == [
        "base_no_mtp_graph_maxseq1",
        "base_no_mtp_eager_maxseq1",
    ]
    assert workload["profiles"][1]["run_only_if"] == (
        "first_profile_fails_in_main_model_graph_capture"
    )
    assert workload["stop_policy"]["stop_after_first_successful_request"] is True
    assert workload["stop_policy"]["no_context_ladder"] is True
    assert workload["execution_result"]["task_status"] == (
        "red_graph_ready_request_client_tokenizer_error"
    )
    assert workload["execution_result"]["server_ready"] is True
    assert workload["execution_result"]["http_requests_dispatched"] == 0
    assert workload["execution_result"]["superseded_by"] == (
        "p5_8card_no_mtp_tokenizer_retry.yaml"
    )


def test_p5_no_mtp_tokenizer_retry_preflights_payload_before_one_graph_request():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p5_8card_no_mtp_tokenizer_retry.yaml"
    )

    assert workload["workload_id"] == "p5_8card_no_mtp_tokenizer_retry"
    assert workload["prior_result"]["task_status"] == (
        "red_graph_ready_request_client_tokenizer_error"
    )
    assert workload["prior_result"]["server_ready"] is True
    assert workload["prior_result"]["http_requests_dispatched"] == 0
    assert workload["client_preflight"]["must_pass_before_npu_server_start"] is True
    assert workload["client_preflight"]["tokenizer_class"] == (
        "vllm.tokenizers.deepseek_v4.DeepseekV4Tokenizer"
    )
    assert workload["client_preflight"]["forbidden_tokenizer_class"] == (
        "transformers.AutoTokenizer"
    )
    assert workload["client_preflight"]["expected_prompt_token_count"] == 4096
    assert workload["request_plan"]["input_tokens"] == 4096
    assert workload["request_plan"]["output_tokens"] == 64
    assert workload["request_plan"]["request_count"] == 1
    assert workload["runtime_fixed"]["speculative_mtp"] == "disabled"
    assert workload["runtime_fixed"]["enforce_eager"] is False
    assert [profile["name"] for profile in workload["profiles"]] == [
        "base_no_mtp_graph_maxseq1_tokenizer_fixed"
    ]
    assert workload["stop_policy"]["no_eager_fallback"] is True
    assert workload["stop_policy"]["no_context_ladder"] is True
    assert workload["execution_result"]["task_status"] == (
        "red_client_tokenizer_class_assertion"
    )
    assert workload["execution_result"]["tokenizer_runtime_class"] == (
        "CachedDSV4TokenizersBackend"
    )
    assert workload["execution_result"]["generated_token_count"] == 4096
    assert workload["execution_result"]["all_token_ids_in_vocab"] is True
    assert workload["execution_result"]["payload_artifact_written"] is False
    assert workload["execution_result"]["server_started"] is False
    assert workload["execution_result"]["successful_requests"] == 0
    assert workload["execution_result"]["superseded_by"] == (
        "p5_8card_no_mtp_tokenizer_mro_retry.yaml"
    )


def test_p5_no_mtp_tokenizer_mro_retry_changes_only_runtime_identity_gate():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p5_8card_no_mtp_tokenizer_mro_retry.yaml"
    )

    assert workload["workload_id"] == "p5_8card_no_mtp_tokenizer_mro_retry"
    assert workload["prior_result"]["task_status"] == (
        "red_client_tokenizer_class_assertion"
    )
    assert workload["prior_result"]["generated_token_count"] == 4096
    assert workload["prior_result"]["all_token_ids_in_vocab"] is True
    assert workload["prior_result"]["payload_artifact_written"] is False
    assert workload["client_preflight"]["runtime_identity_check"] == (
        "mro_contains_class_name_starting_with_DSV4"
    )
    assert workload["client_preflight"]["top_level_runtime_class_prefix_check"] == (
        "forbidden_because_get_cached_tokenizer_adds_Cached_prefix"
    )
    assert workload["client_preflight"]["expected_prompt_token_count"] == 4096
    assert workload["request_plan"]["request_count"] == 1
    assert workload["request_plan"]["input_tokens"] == 4096
    assert workload["request_plan"]["output_tokens"] == 64
    assert workload["runtime_fixed"]["speculative_mtp"] == "disabled"
    assert workload["runtime_fixed"]["enforce_eager"] is False
    assert [profile["name"] for profile in workload["profiles"]] == [
        "base_no_mtp_graph_maxseq1_tokenizer_mro_fixed"
    ]
    assert workload["stop_policy"]["no_eager_fallback"] is True
    assert workload["execution_result"]["task_status"] == (
        "yellow_no_mtp_graph_request_success"
    )
    assert workload["execution_result"]["server_ready"] is True
    assert workload["execution_result"]["successful_requests"] == 1
    assert workload["execution_result"]["generated_token_count"] == 64


def test_p5_four_card_startup_probe_is_bounded_capacity_diagnostic():
    probe = load_yaml(BENCHMARK_DIR / "workloads" / "p5_4card_startup_probe.yaml")

    assert probe["workload_id"] == "p5_deepseek_v4_flash_4card_startup_probe_v0202"
    assert probe["scenario"] == "four_card_runtime_format_compatibility_and_capacity_probe"
    assert probe["model_object_id"] == "deepseek_v4_flash_official_hf"
    assert probe["server_model_path"] == "/data/node0_disk1/Public/DeepSeek-V4-Flash"
    assert probe["resource_gate"]["authorized_visible_devices"] == "4,5,6,7"
    assert probe["capacity_prior"]["selected_checkpoint_weight_size_gib"] == 148.66
    assert probe["capacity_prior"]["static_capacity_margin_gib"] == 107.34
    assert probe["capacity_prior"]["excluded_w8a8_checkpoint_weight_size_gib"] == 279.41
    assert probe["format_prior"]["checkpoint_expert_dtype"] == "fp4"
    assert probe["format_prior"]["vllm_target_tag_detection"] == "deepseek_v4_fp8"
    assert probe["runtime_reference"]["tensor_parallel_size"] == 4
    assert probe["runtime_reference"]["enable_expert_parallel"] is True
    assert probe["runtime_reference"]["max_model_len"] == 8192
    assert probe["runtime_reference"]["max_num_seqs"] == 1
    assert probe["runtime_reference"]["additional_config"]["enable_flashcomm1"] is True
    assert probe["runtime_reference"]["additional_config"]["enable_dsa_cp"] is True
    assert probe["runtime_reference"]["additional_config"]["enable_mlapo"] is False
    assert probe["runtime_reference"]["cpu_offload_gb"] == 0
    assert probe["runtime_reference"]["quantization"] == "auto_from_checkpoint_config"
    assert probe["runtime_reference"]["explicit_quantization_argument"] == "forbidden_for_this_probe"
    assert probe["request_plan"]["input_tokens"] == 4096
    assert probe["request_plan"]["output_tokens"] == 64
    assert probe["fallback_policy"]["mtp_off_only_after_explicit_mtp_failure"] is True
    assert probe["fallback_policy"]["stop_after_capacity_failure"] is True
    assert probe["fallback_policy"]["stop_after_quantization_format_failure"] is True
    assert probe["fallback_policy"]["no_w8a8_checkpoint_attempt"] is True
    assert probe["boundaries"]["canonical_p5_eight_card_gate_unchanged"] is True
    assert probe["execution_result"]["probe_grade"] == "diagnostic_red_quant_format"
    assert probe["execution_result"]["weight_load_started"] is False


def test_p5_four_card_fp8_stack_upgrade_probe_is_isolated_and_bounded():
    probe = load_yaml(BENCHMARK_DIR / "workloads" / "p5_4card_fp8_stack_upgrade_probe.yaml")

    assert probe["workload_id"] == "p5_deepseek_v4_flash_4card_fp8_stack_upgrade_probe_v0221rc1"
    assert probe["model_object_id"] == "deepseek_v4_flash_official_hf"
    assert probe["target_runtime"]["vllm_commit"] == "0decac0d96c42b49572498019f0a0e3600f50398"
    assert probe["target_runtime"]["vllm_ascend_commit"] == "5f6faa0cb8830f667266f3b8121cd1383606f2a1"
    assert probe["target_runtime"]["vllm_ascend_commit"] == "5f6faa0cb8830f667266f3b8121cd1383606f2a1"
    assert probe["target_runtime"]["vllm_expected_version"] == "0.22.1+empty"
    assert probe["target_runtime"]["vllm_ascend_expected_version"] == "0.22.1rc1"
    assert probe["target_runtime"]["torch_npu"] == "2.10.0"
    assert probe["source_evidence"]["npu_platform_supported_quantization"][-1] == "deepseek_v4_fp8"
    assert probe["resource_gate"]["authorized_visible_devices"] == "4,5,6,7"
    assert probe["runtime_reference"]["explicit_quantization_argument"] == "forbidden"
    assert probe["runtime_reference"]["tensor_parallel_size"] == 4
    assert probe["runtime_reference"]["additional_config"]["enable_flashcomm1"] is True
    assert probe["runtime_reference"]["additional_config"]["enable_dsa_cp"] is True
    assert [profile["name"] for profile in probe["profiles"]] == ["base_no_mtp", "mtp_on"]
    assert probe["profiles"][1]["run_only_if"] == "base_no_mtp_request_succeeds"
    assert probe["stop_policy"]["no_w8a8_checkpoint_attempt"] is True
    assert probe["stop_policy"]["no_source_patch"] is True
    assert probe["execution_result"]["reported_probe_grade"] == "blocked_environment"
    assert probe["execution_result"]["environment_functionally_built"] is True
    assert probe["execution_result"]["pip_check"]["involves_inference_core_packages"] is False
    assert probe["execution_result"]["runtime_profiles_executed"] is False
    assert probe["execution_result"]["superseded_by"] == "p5_4card_fp8_runtime_resume_probe.yaml"


def test_p5_four_card_fp8_runtime_resume_probe_reuses_core_stack_and_bounds_dependency_gate():
    probe = load_yaml(BENCHMARK_DIR / "workloads" / "p5_4card_fp8_runtime_resume_probe.yaml")

    assert probe["workload_id"] == "p5_deepseek_v4_flash_4card_fp8_runtime_resume_probe_v0221rc1"
    assert probe["target_runtime"]["lifecycle"] == "reuse_read_only_no_rebuild_or_package_changes"
    assert probe["target_runtime"]["vllm_commit"] == "0decac0d96c42b49572498019f0a0e3600f50398"
    assert probe["environment_gate"]["full_pip_check"] == "diagnostic_not_global_hard_gate"
    assert probe["environment_gate"]["block_on_any_unlisted_dependent_or_requirement_conflict"] is True
    allowed = probe["environment_gate"]["allowed_preexisting_non_core_conflicts"]
    assert set(allowed) == {
        "mindstudio-kpp",
        "ms-service-profiler",
        "te",
        "pyvers",
        "opencv-python-headless",
    }
    assert set(allowed["ms-service-profiler"]) == {
        "matplotlib",
        "msguard",
        "openpyxl",
        "opentelemetry-exporter-otlp-proto-grpc",
        "opentelemetry-exporter-otlp-proto-http",
        "pandas",
    }
    assert probe["resource_gate"]["authorized_visible_devices"] == "4,5,6,7"
    assert probe["runtime_reference"]["explicit_quantization_argument"] == "forbidden"
    assert probe["runtime_reference"]["tensor_parallel_size"] == 4
    assert [profile["name"] for profile in probe["profiles"]] == ["base_no_mtp", "mtp_on"]
    assert probe["profiles"][1]["run_only_if"] == "base_no_mtp_request_succeeds"
    assert probe["stop_policy"]["no_w8a8_checkpoint_attempt"] is True
    assert probe["execution_result"]["probe_grade"] == "diagnostic_red_runtime"
    assert probe["execution_result"]["first_failure_stage"] == "worker_init_memory_snapshot_allocator"
    assert probe["execution_result"]["base_no_mtp"]["weight_load_started"] is False
    assert probe["execution_result"]["approved_prior_artifact_transfer"]["method"] == "upload-api"


def test_p5_allocator_patch_delivery_probe_is_conditional_and_bounded():
    probe = load_yaml(BENCHMARK_DIR / "workloads" / "p5_4card_fp8_allocator_patch_delivery_probe.yaml")

    assert probe["workload_id"] == "p5_deepseek_v4_flash_4card_fp8_allocator_patch_delivery_probe_v0221rc1"
    assert probe["prior_runtime_result"]["first_failure_stage"] == "worker_init_memory_snapshot_allocator"
    assert probe["source_evidence"]["official_patch_module"] == "vllm_ascend.patch.platform.patch_torch_accelerator"
    redirects = probe["source_evidence"]["official_redirects"]
    assert redirects["torch.accelerator.memory_stats"] == "torch.npu.memory_stats"
    assert redirects["torch.accelerator.memory_reserved"] == "torch.npu.memory_reserved"
    assert probe["prior_artifact_transfer"]["confirmed_method"] == "upload-api"
    assert probe["prior_artifact_transfer"]["total_bytes"] == 12728
    assert len(probe["prior_artifact_transfer"]["files"]) == 6
    assert probe["allocator_probe"]["visible_device"] == "4"
    assert probe["allocator_probe"]["multiprocessing_method"] == "spawn"
    assert probe["allocator_probe"]["conditional_workaround"]["type"] == "session_scoped_sitecustomize"
    assert probe["four_card_retry"]["authorized_visible_devices"] == "4,5,6,7"
    assert probe["four_card_retry"]["profile"] == "base_no_mtp_only"
    assert probe["four_card_retry"]["explicit_quantization_argument"] == "forbidden"
    assert probe["stop_policy"]["mtp_on_forbidden"] is True
    assert probe["stop_policy"]["no_package_source_or_system_changes"] is True


def test_p5_plugin_activation_probe_is_fresh_process_bounded_and_overlay_free():
    probe = load_yaml(BENCHMARK_DIR / "workloads" / "p5_4card_fp8_plugin_activation_probe.yaml")

    assert probe["workload_id"] == "p5_deepseek_v4_flash_4card_fp8_plugin_activation_probe_v0221rc1"
    assert probe["prior_probe_result"]["probe_grade"] == "diagnostic_yellow_allocator_bypass"
    assert probe["prior_probe_result"]["selected_model_module"] == "vllm.models.deepseek_v4.nvidia.model"
    assert probe["source_evidence"]["current_restrictive_value"] == "ascend"
    assert probe["source_evidence"]["deepseek_v4_registry_target"] == (
        "vllm_ascend.models.deepseek_v4:AscendDeepseekV4ForCausalLM"
    )
    hashes = probe["source_evidence"]["target_file_sha256"]
    assert len(hashes) == 6
    assert hashes["vllm/plugins/__init__.py"] == (
        "4be66190ceaee9d0465f62ade801a8e94a907d7ab9fdb0a67fa14ce87448ae9f"
    )
    assert hashes["vllm_ascend/models/deepseek_v4.py"] == (
        "9398e49d7206ba5a62629409405be057318e0657e40a25cf15c43304f78d01a4"
    )
    assert hashes["vllm_ascend/patch/platform/patch_torch_accelerator.py"] == (
        "76ca48d51c8af6552828076797ad20b7eed044a8e53be918bd12719152fdc026"
    )
    provenance = probe["installed_content_provenance_gate"]
    assert provenance["run_before_plugin_probe"] is True
    assert provenance["mismatch_policy"] == (
        "blocked_provenance_stop_before_npu_plugin_matrix_or_model_start"
    )
    modes = {item["name"]: item for item in probe["plugin_probe"]["modes"]}
    assert modes["restrictive_current"]["vllm_plugins"] == "ascend"
    assert modes["explicit_official_ascend_plugins"]["expected_registry_module"] == (
        "vllm_ascend.models.deepseek_v4"
    )
    assert probe["plugin_probe"]["result_transport"] == "write_json_to_dedicated_file_not_stdout"
    assert probe["four_card_retry"]["authorized_visible_devices"] == "4,5,6,7"
    assert probe["four_card_retry"]["session_sitecustomize_or_pythonpath_overlay"] == "forbidden"
    assert probe["four_card_retry"]["profile"] == "base_no_mtp_only"
    assert probe["four_card_retry"]["explicit_quantization_argument"] == "forbidden"
    assert probe["stop_policy"]["mtp_on_forbidden"] is True
    assert probe["stop_policy"]["no_sitecustomize_or_pythonpath_overlay"] is True
    assert probe["execution_result"]["probe_grade"] == "diagnostic_yellow_plugin_route_fixed"
    assert probe["execution_result"]["installed_content_provenance_all_match"] is True
    assert probe["execution_result"]["plugin_activation_hypothesis_supported"] is True
    assert probe["execution_result"]["base_no_mtp"]["first_failure"] == "ModuleNotFoundError_No_module_named_acl"
    assert probe["execution_result"]["task_environment_detail"]["pythonpath_unset_after_sourcing"] is True
    assert probe["execution_result"]["repeat_confirmation"]["attempts_observed"] == 2
    assert probe["execution_result"]["repeat_confirmation"]["plugin_matrix_summary_byte_identical"] is True
    assert probe["execution_result"]["repeat_confirmation"]["installed_content_provenance_byte_identical"] is True
    assert probe["execution_result"]["repeat_confirmation"]["first_failure_call_chain_identical"] is True
    assert probe["execution_result"]["superseded_by"] == "p5_4card_fp8_acl_path_probe.yaml"


def test_p5_acl_path_probe_preserves_only_official_cann_path_and_bounds_retry():
    probe = load_yaml(BENCHMARK_DIR / "workloads" / "p5_4card_fp8_acl_path_probe.yaml")

    assert probe["workload_id"] == "p5_deepseek_v4_flash_4card_fp8_acl_path_probe_v0221rc1"
    assert probe["prior_probe_result"]["probe_grade"] == "diagnostic_yellow_plugin_route_fixed"
    assert probe["prior_probe_result"]["first_failure"] == "ModuleNotFoundError_No_module_named_acl"
    assert probe["prior_probe_result"]["pythonpath_unset_after_sourcing"] is True
    assert probe["hypothesis"]["pip_install_acl"] == "forbidden"
    assert probe["acl_path_probe"]["visible_device"] == "4"
    assert probe["acl_path_probe"]["clean_shell_rule"] == "unset_PYTHONPATH_before_sourcing_CANN_and_ATB"
    modes = {item["name"]: item for item in probe["acl_path_probe"]["modes"]}
    assert set(modes) == {
        "stripped_after_source_control",
        "clean_CANN_generated_path",
        "spawned_worker_inheritance",
    }
    assert modes["clean_CANN_generated_path"]["expected_acl_origin_prefix"] == "/usr/local/Ascend"
    assert probe["four_card_retry"]["authorized_visible_devices"] == "4,5,6,7"
    assert probe["four_card_retry"]["pythonpath"] == "exact_clean_CANN_and_ATB_generated_value_from_probe"
    assert probe["four_card_retry"]["profile"] == "base_no_mtp_only"
    assert probe["four_card_retry"]["explicit_quantization_argument"] == "forbidden"
    assert probe["stop_policy"]["mtp_on_forbidden"] is True
    assert probe["stop_policy"]["no_package_source_or_system_changes"] is True


def test_server_handoff_contains_only_the_server_local_git_recovery_task():
    handoff = (REPO_ROOT / "通信模块" / "docs" / "developer-to-server.md").read_text(encoding="utf-8")

    assert "server_local_git_worktree_policy_recover_2026_0712" in handoff
    assert "execution_codebase: main-readonly" in handoff
    assert "/data/node0_disk1/liguowei/AK-Infer-Lab-server-local" in handoff
    assert "server-local/runtime-adaptations" in handoff
    assert "server_local_git_sync.sh\" init" in handoff
    assert "git status --porcelain --untracked-files=no" in handoff
    assert "git restore --worktree --" in handoff
    assert "21afc388efd88374ac3c78d82551b7f9c74498913fd7dbffee73a9f5278f4110" in handoff
    assert "服务器不得修改受 Git 跟踪的工作记录" in handoff
    assert "same_path_overlap.txt" in handoff
    assert "conflict_paths.txt" in handoff
    assert "merge_tree.txt" in handoff
    assert "禁止对任何 remote 执行 `git push`" in handoff
    assert "ours/theirs" in handoff
    assert "自动选择" in handoff
    assert "不使用 NPU" in handoff
    assert "尚未获得 `email`、`upload-api` 或 `server-local` 选择" in handoff
    assert "p8_1_deepseek_v4_flash_vllm_ascend_observe_only_trace_2026_0712" not in handoff
