import json
import subprocess
import sys
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


def test_p6_0_degraded_stabilization_repeats_only_the_exact_p5_yellow_cell():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_0_no_mtp_degraded_stabilization.yaml"
    )

    assert workload["task_id"] == (
        "p6_0_deepseek_v4_flash_w8a8_no_mtp_degraded_stabilization_2026_0713"
    )
    assert workload["stage_contract"] == {
        "stage": "P6.0",
        "mode": "degraded_stabilization",
        "p5_status": "yellow_no_mtp_graph_request_success",
        "may_claim_official_baseline": False,
        "may_enter_p6_1_automatically": False,
        "p8_1_server_validation": "deferred_preflight_not_executed",
    }
    assert workload["runtime_environment"]["visible_devices"] == "0,1,2,3,4,5,6,7"
    assert workload["runtime_fixed"]["speculative_mtp"] == "disabled"
    assert workload["runtime_fixed"]["enforce_eager"] is False
    assert workload["runtime_fixed"]["cudagraph_mode"] == "FULL_DECODE_ONLY"
    assert workload["request_fixed"]["input_tokens"] == 4096
    assert workload["request_fixed"]["output_tokens"] == 64
    assert workload["request_fixed"]["payload_bytes"] == 19487
    assert workload["request_fixed"]["payload_sha256"] == (
        "48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1"
    )
    assert workload["repeat_plan"]["prior_accepted_successes"] == 1
    assert workload["repeat_plan"]["new_fresh_server_lifecycles"] == 2
    assert workload["repeat_plan"]["requests_per_lifecycle"] == 1
    assert workload["repeat_plan"]["required_consecutive_successes_total"] == 3
    assert workload["acceptance"]["final_grade"] == "yellow_degraded_baseline_stabilized"
    assert workload["stop_policy"]["no_profiler"] is True
    assert workload["stop_policy"]["no_performance_claim"] is True
    assert workload["stop_policy"]["no_p8_observer_or_adapter_execution"] is True
    assert workload["execution_state"]["server_handoff"] == "completed"
    assert workload["execution_state"]["server_result"] == "yellow_degraded_baseline_stabilized"
    assert workload["execution_result"]["server_git_head"] == (
        "bc94abcc05c79eeea249d2c87fbe465c47a5015e"
    )
    assert workload["execution_result"]["new_successful_lifecycles"] == 2
    assert workload["execution_result"]["consecutive_successes_total"] == 3
    assert workload["execution_result"]["command_drift_count"] == 0
    assert workload["execution_result"]["environment_drift_count"] == 0
    assert workload["execution_result"]["payload_drift_count"] == 0
    assert workload["execution_result"]["official_baseline"] is False


def test_p6_1_minimal_unprofiled_control_is_one_cell_with_bounded_statistics():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1_no_mtp_minimal_unprofiled_control.yaml"
    )

    assert workload["task_id"] == (
        "p6_1_deepseek_v4_flash_w8a8_no_mtp_minimal_unprofiled_control_2026_0713"
    )
    assert workload["stage_contract"] == {
        "stage": "P6.1",
        "mode": "minimal_unprofiled_control",
        "baseline_grade": "yellow_degraded_baseline_stabilized",
        "claim_level": "controlled_benchmark_minimal_control",
        "may_claim_official_baseline": False,
        "full_p6_1_matrix_authorized": False,
        "mtp_remediation_authorized": False,
    }
    assert workload["prior_p6_0_evidence"]["consecutive_successes_total"] == 3
    assert workload["runtime_fixed"]["speculative_mtp"] == "disabled"
    assert workload["runtime_fixed"]["tensor_parallel_size"] == 8
    assert workload["runtime_fixed"]["enable_expert_parallel"] is True
    assert workload["runtime_fixed"]["max_num_seqs"] == 1
    assert workload["runtime_fixed"]["cudagraph_mode"] == "FULL_DECODE_ONLY"
    assert workload["measurement_plan"] == {
        "server_lifecycles": 1,
        "warmup_requests": 1,
        "measured_requests": 3,
        "request_order": "sequential",
        "concurrency": 1,
        "input_tokens": 4096,
        "output_tokens": 64,
        "unprofiled": True,
    }
    assert workload["request_fixed"]["payload_sha256"] == (
        "48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1"
    )
    assert workload["request_fixed"]["temperature"] == 0.0
    assert workload["request_fixed"]["ignore_eos"] is True
    assert workload["request_fixed"]["min_tokens"] == 64
    assert workload["request_fixed"]["max_tokens"] == 64
    assert workload["metrics"]["client_clock"] == "time.monotonic_ns"
    assert workload["metrics"]["exact_token_arrival_timestamps_required"] is True
    assert workload["metrics"]["ttft_definition"] == "first_token_ns-request_start_ns"
    assert workload["metrics"]["tpot_definition"] == (
        "(last_token_ns-first_token_ns)/(completion_tokens-1)"
    )
    assert workload["metrics"]["e2el_definition"] == "request_end_ns-request_start_ns"
    assert workload["statistics"]["report_raw_three_samples"] is True
    assert workload["statistics"]["report_min_median_max"] is True
    assert workload["statistics"]["outlier_removal"] is False
    assert workload["statistics"]["report_p95_p99"] is False
    assert workload["statistics"]["tail_percentile_reason"] == "n3_is_insufficient"
    assert workload["stop_policy"]["no_additional_p6_1_cells"] is True
    assert workload["stop_policy"]["no_profiler"] is True
    assert workload["stop_policy"]["no_mtp_or_128k"] is True
    assert workload["stop_policy"]["no_automatic_mtp_remediation"] is True
    assert workload["execution_state"]["server_handoff"] == "completed"
    assert workload["execution_state"]["server_result"] == (
        "yellow_degraded_minimal_unprofiled_control_measured"
    )
    assert workload["execution_result"]["server_git_head"] == (
        "b798621d904335517f28eebe364a8f06013fc684"
    )
    assert workload["execution_result"]["measured_requests_successful"] == 3
    assert workload["execution_result"]["each_exact_token_arrival_timestamps"] == 64
    assert workload["execution_result"]["cleanup_status"] == "clean"
    assert workload["execution_result"]["official_baseline"] is False


def test_p6_1r_bounded_mtp_repair_has_one_diagnostic_and_one_conditional_validation():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1r_bounded_mtp_reference_repair.yaml"
    )

    assert workload["task_id"] == (
        "p6_1r_deepseek_v4_flash_w8a8_bounded_mtp_reference_repair_retry2_2026_0713"
    )
    assert workload["retry_lineage"] == {
        "attempt": 3,
        "retry_label": "retry2",
        "parent_task_id": (
            "p6_1r_deepseek_v4_flash_w8a8_bounded_mtp_reference_repair_retry1_2026_0713"
        ),
        "parent_result": "yellow_mtp_graph_capture_advanced_new_first_failure",
        "parent_server_ready": True,
        "parent_original_positions_cpu_failure_absent": True,
        "parent_http_status": 400,
        "parent_patch_attempts": 1,
        "parent_server_lifecycles": 1,
        "parent_requests": 1,
        "correction": "completion_endpoint_error_capture_and_overlay_gate",
    }
    assert workload["stage_contract"] == {
        "stage": "P6.1R",
        "mode": "bounded_mtp_reference_repair",
        "prior_control_grade": "yellow_degraded_minimal_unprofiled_control_measured",
        "claim_level": "mtp_minimal_functional_repair",
        "may_claim_official_baseline": False,
        "full_p6_1_matrix_authorized": False,
        "context_ladder_authorized": False,
        "profiler_authorized": False,
    }
    assert workload["historical_failure"]["first_failure_stage"] == (
        "mtp_drafter_dsa_cp_cudagraph_capture"
    )
    assert workload["historical_failure"]["first_failure"] == (
        "positions_cpu_none_type_not_subscriptable"
    )
    assert workload["source_evidence"]["upstream_commit"] == (
        "1930088f960aba65eeaae82e9617d090283edc1f"
    )
    assert workload["source_evidence"]["upstream_pr"] == 11062
    assert workload["source_evidence"]["upstream_tested_vllm"] == "0.23.0"
    assert workload["source_evidence"]["full_upstream_backport_authorized"] is False
    assert workload["repair_artifact"]["task_local_overlay_only"] is True
    assert workload["repair_artifact"]["base_environment_mutation"] is False
    assert workload["repair_artifact"]["changed_files"] == 1
    assert workload["repair_artifact"]["changed_lines"] == 1
    assert workload["runtime_fixed"]["speculative_mtp"] == {
        "method": "mtp",
        "num_speculative_tokens": 1,
    }
    assert workload["request_fixed"]["endpoint"] == "/v1/completions"
    assert workload["validation_plan"] == {
        "read_only_diagnostic_passes": 1,
        "task_local_overlay_patch_attempts_max": 1,
        "server_lifecycles_max": 1,
        "requests_max": 1,
        "input_tokens": 4096,
        "output_tokens": 64,
        "concurrency": 1,
        "unprofiled": True,
    }
    assert workload["stop_policy"]["stop_if_root_cause_not_unique"] is True
    assert workload["stop_policy"]["stop_after_first_post_patch_failure"] is True
    assert workload["stop_policy"]["no_second_patch"] is True
    assert workload["stop_policy"]["no_eager_fallback"] is True
    assert workload["stop_policy"]["no_context_ladder"] is True
    assert workload["stop_policy"]["no_profiler"] is True
    assert workload["execution_state"] == {
        "server_handoff": "completed",
        "server_result": "green_mtp_minimal_request_success",
        "result_received": True,
        "result_package_local": (
            "/Volumes/SSD1/Inbox/2026-07-13/"
            "p6_1r_mtp_repair_retry2_green_2026_0713_161318"
        ),
        "transfer_method": "server_local_result_package_received",
    }
    assert workload["execution_result"] == {
        "git_commit": "5fd6fdb9693e108686b3f8fdea2896d69aede0c0",
        "patch_attempts": 1,
        "server_lifecycles": 1,
        "requests": 1,
        "server_ready": True,
        "endpoint": "/v1/completions",
        "http_status": 200,
        "prompt_tokens": 4096,
        "generated_tokens": 64,
        "streamed_tokens": 64,
        "finish_reason": "length",
        "saw_done": True,
        "original_positions_cpu_failure_absent": True,
        "cleanup_status": "clean",
        "official_baseline": False,
        "context_128k_validated": False,
        "full_p6_1_matrix_validated": False,
        "optimization_gain_validated": False,
    }

    patch = (
        BENCHMARK_DIR
        / "patches"
        / "vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch"
    ).read_text(encoding="utf-8")
    assert patch.count("+                positions_cpu=") == 1
    assert "self.runner._dsa_positions_cpu_buf if self.use_compress else None" in patch
    assert patch.count("diff --git ") == 1


def test_p6_1l_decode_length_ladder_freezes_one_lifecycle_and_six_slots():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1l_mtp_decode_length_ladder.yaml"
    )

    assert workload["task_id"] == (
        "p6_1l_deepseek_v4_flash_w8a8_mtp_decode_length_ladder_2026_0713"
    )
    assert workload["stage_contract"] == {
        "stage": "P6.1L",
        "mode": "mtp_decode_length_stability_ladder",
        "claim_level": "mtp_4096_decode_length_stability_only",
        "may_claim_official_baseline": False,
        "full_p6_1_matrix_authorized": False,
        "context_ladder_authorized": False,
        "profiler_authorized": False,
        "performance_comparison_authorized": False,
    }
    assert workload["prior_mtp_gate"]["grade"] == "green_mtp_minimal_request_success"
    assert workload["prior_mtp_gate"]["input_tokens"] == 4096
    assert workload["prior_mtp_gate"]["output_tokens"] == 64
    assert workload["prior_mtp_gate"]["raw_evidence_audit_required"] is True
    assert workload["runtime_fixed"]["speculative_mtp"] == {
        "method": "mtp",
        "num_speculative_tokens": 1,
    }
    assert workload["experiment_plan"] == {
        "input_tokens": 4096,
        "output_ladder": [512, 1024],
        "slots_per_output": 3,
        "slot_order": [
            "output512_slot1",
            "output512_slot2",
            "output512_slot3",
            "output1024_slot1",
            "output1024_slot2",
            "output1024_slot3",
        ],
        "hidden_warmup_requests": 0,
        "planned_slots": 6,
        "attempts_per_slot_max": 2,
        "attempts_max": 12,
        "retries_max": 6,
        "patch_attempts_max": 1,
        "server_lifecycles_max": 1,
        "concurrency": 1,
        "request_order": "sequential",
        "unprofiled": True,
    }


def test_p6_1l_gates_execution_on_retry2_raw_audit_and_mtp_counter_evidence():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1l_mtp_decode_length_ladder.yaml"
    )

    assert workload["retry2_raw_audit"] == {
        "result_dir": (
            "/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/"
            "p6_1r_deepseek_v4_flash_w8a8_bounded_mtp_reference_repair_"
            "retry2_2026_0713"
        ),
        "expected_patch_attempts": 1,
        "expected_server_lifecycles": 1,
        "expected_requests": 1,
        "expected_http_status": 200,
        "expected_generated_tokens": 64,
        "expected_streamed_tokens": 64,
        "expected_cleanup": "clean",
        "require_mtp_proposer_initialization": True,
        "require_mtp_draft_model_loaded": True,
        "require_graph_capture_completion": True,
        "require_completion_access_200": True,
        "require_original_positions_cpu_failure_absent": True,
        "hard_conflict_policy": "stop_before_new_lifecycle",
        "historical_spec_metrics_optional": True,
        "post_shutdown_errors_classified_separately": True,
        "raw_files_remain_server_local": True,
    }
    assert workload["metrics_evidence"] == {
        "endpoint": "/metrics",
        "snapshot_before_and_after_every_attempt": True,
        "parser_reference": "vllm_v0_22_1_spec_decode_prometheus_counters",
        "spec_counter_names": [
            "vllm:spec_decode_num_drafts_total",
            "vllm:spec_decode_num_draft_tokens_total",
            "vllm:spec_decode_num_accepted_tokens_total",
        ],
        "request_gauge_names": [
            "vllm:num_requests_running",
            "vllm:num_requests_waiting",
        ],
        "successful_attempt_requires_positive_draft_delta": True,
        "zero_accepted_delta_allowed": True,
        "missing_spec_metrics_log_fallback_allowed": True,
        "missing_metrics_and_runtime_log_evidence_stops": True,
        "raw_metrics_remain_server_local": True,
        "optimization_gain_claim_allowed": False,
    }


def test_p6_1l_bounds_same_payload_retries_and_result_grades():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1l_mtp_decode_length_ladder.yaml"
    )

    assert workload["request_protocol"]["endpoint"] == "/v1/completions"
    assert workload["request_protocol"]["input_tokens"] == 4096
    assert workload["request_protocol"]["output_tokens_by_group"] == [512, 1024]
    assert workload["request_protocol"]["temperature"] == 0.0
    assert workload["request_protocol"]["ignore_eos"] is True
    assert workload["request_protocol"]["min_tokens_equals_max_tokens"] is True
    assert workload["request_protocol"]["generated_text_retained"] is False
    assert workload["request_protocol"]["token_ids_retained"] is False
    assert workload["retry_policy"] == {
        "max_retries_per_slot": 1,
        "max_retries_total": 6,
        "same_request_body_sha256_required": True,
        "server_process_must_be_alive": True,
        "health_must_be_200": True,
        "num_requests_running_must_be_zero": True,
        "num_requests_waiting_must_be_zero": True,
        "no_retry_if_idle_state_unproven": True,
        "server_restart_allowed": False,
        "parameter_mutation_allowed": False,
        "patch_mutation_allowed": False,
        "recovered_attempt_fills_slot": True,
        "recovered_run_max_grade": "yellow_mtp_decode_length_ladder_recovered",
        "second_failure_stops_task": True,
        "second_failure_requires_server_local_root_cause_analysis": True,
        "server_may_self_patch_after_failure": False,
    }
    assert workload["attempt_result_schema"]["fields"] == [
        "slot_id",
        "output_tokens",
        "attempt_index",
        "request_body_sha256",
        "status",
        "http_status",
        "prompt_tokens",
        "generated_token_count",
        "streamed_token_count",
        "finish_reason",
        "saw_done",
        "health_before",
        "health_after",
        "request_wall_ms_diagnostic_only",
        "metrics_before",
        "metrics_after",
        "metrics_delta",
        "mtp_activity_evidence",
        "retry_recovery",
    ]
    assert workload["acceptance"]["green_grade"] == (
        "green_mtp_decode_length_ladder_stable"
    )
    assert workload["acceptance"]["green_requires_first_attempt_successes"] == 6
    assert workload["acceptance"]["yellow_recovered_grade"] == (
        "yellow_mtp_decode_length_ladder_recovered"
    )
    assert workload["acceptance"]["yellow_recovered_requires_cleanup"] == "clean"
    assert workload["acceptance"]["yellow_log_only_grade"] == (
        "yellow_mtp_decode_length_success_activity_log_only"
    )
    assert workload["acceptance"]["yellow_log_only_requires_cleanup"] == "clean"
    assert workload["acceptance"]["cleanup_failure_grade"] == "red_cleanup_incomplete"
    assert workload["acceptance"]["red_grade"] == (
        "red_mtp_decode_length_slot_failed_after_retry"
    )
    assert workload["acceptance"]["prior_4096_64_green_remains_valid"] is True
    assert workload["acceptance"]["official_baseline_after_green"] is False


def test_p6_1l_records_measurement_green_and_the_original_protocol_deviation():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1l_mtp_decode_length_ladder.yaml"
    )

    assert workload["execution_state"] == {
        "server_handoff": "completed",
        "server_result": "measurement_green_protocol_deviation",
        "transfer_method": "server_local_result_package_received",
        "superseded_by": (
            "p6_1l_deepseek_v4_flash_w8a8_mtp_decode_length_ladder_"
            "rerun1_2026_0713"
        ),
    }
    result = workload["execution_result"]
    assert result["server_git_head"] == "c5f663385975d95b1f712cbb67556df67b451ba2"
    assert result["measurement_grade"] == "green_mtp_decode_length_ladder_stable"
    assert result["planned_slots"] == 6
    assert result["completed_slots"] == 6
    assert result["attempt_count"] == 6
    assert result["retry_count"] == 0
    assert result["generated_tokens_total"] == 4608
    assert result["spec_draft_tokens_delta_total"] == 2304
    assert result["spec_accepted_tokens_delta_total"] == 2304
    assert result["cleanup_status"] == "clean"
    assert result["retry2_raw_audit_exit_code"] == 2
    assert result["retry2_raw_audit_hard_conflict"] is True
    assert result["execution_contract_clean_pass"] is False
    assert result["original_artifacts_preserved"] is True


def test_p6_1l_rerun_repeats_all_six_slots_with_mandatory_metrics():
    workload = load_yaml(
        BENCHMARK_DIR
        / "workloads"
        / "p6_1l_mtp_decode_length_ladder_rerun1.yaml"
    )

    assert workload["task_id"] == (
        "p6_1l_deepseek_v4_flash_w8a8_mtp_decode_length_ladder_"
        "rerun1_2026_0713"
    )
    assert workload["stage_contract"]["stage"] == "P6.1L-R1"
    assert workload["stage_contract"]["rerun_cost_class"] == (
        "acceptable_full_six_slot_rerun"
    )
    assert workload["experiment_plan"]["slot_order"] == [
        "output512_slot1",
        "output512_slot2",
        "output512_slot3",
        "output1024_slot1",
        "output1024_slot2",
        "output1024_slot3",
    ]
    assert workload["experiment_plan"]["hidden_warmup_requests"] == 0
    assert workload["experiment_plan"]["server_lifecycles_max"] == 1
    assert workload["metrics_evidence"]["spec_metrics_required"] is True
    assert workload["metrics_evidence"]["log_only_fallback_allowed"] is False
    assert workload["metrics_evidence"]["positive_draft_delta_per_success"] is True
    assert workload["metrics_evidence"]["positive_draft_token_delta_per_success"] is True
    assert workload["execution_state"] == {
        "server_handoff": "completed",
        "server_result": "green_mtp_decode_length_ladder_revalidated",
        "transfer_method": "server_local_result_package_received",
    }
    result = workload["execution_result"]
    assert result["server_git_head"] == "bef2d8be182973c8c7c6206b14fad91d906b8efc"
    assert result["grade"] == "green_mtp_decode_length_ladder_revalidated"
    assert result["historical_lineage_audit_v2_exit_code"] == 0
    assert result["historical_lineage_audit_v2_hard_conflict"] is False
    assert result["structured_hard_check_count"] == 22
    assert result["structured_hard_checks_all_true"] is True
    assert result["summary_hard_check_count_reported"] == 21
    assert result["summary_count_mismatch_effect"] == "non_blocking_summary_typo"
    assert result["live_metrics_preflight_exit_code"] == 0
    assert result["planned_slots"] == 6
    assert result["completed_slots"] == 6
    assert result["attempt_count"] == 6
    assert result["retry_count"] == 0
    assert result["generated_tokens_total"] == 4608
    assert result["spec_drafts_delta_total"] == 2304
    assert result["spec_draft_tokens_delta_total"] == 2304
    assert result["spec_accepted_tokens_delta_total"] == 2304
    assert result["cleanup_status"] == "clean"
    assert result["result_package"] == {
        "file_count": 11,
        "total_bytes": 30289,
        "sorted_manifest_sha256": (
            "fb242141cc033633fb0ce5c4950da95005c7c253e239187623eafc2637c3b4fa"
        ),
    }
    assert result["generated_text_retained"] is False
    assert result["token_ids_retained"] is False
    assert result["raw_artifacts_retained_server_local"] is True
    assert result["official_baseline"] is False
    assert result["context_128k_validated"] is False
    assert result["full_p6_1_matrix_validated"] is False
    assert result["optimization_gain_validated"] is False
    assert result["next_task_authorized"] is False


def test_p6_1l_rerun_replaces_logger_string_gate_and_closes_grading_bypass():
    workload = load_yaml(
        BENCHMARK_DIR
        / "workloads"
        / "p6_1l_mtp_decode_length_ladder_rerun1.yaml"
    )

    assert workload["historical_protocol_deviation"] == {
        "prior_task_id": (
            "p6_1l_deepseek_v4_flash_w8a8_mtp_decode_length_ladder_2026_0713"
        ),
        "measurement_grade": "green_mtp_decode_length_ladder_stable",
        "original_retry2_raw_audit_exit_code": 2,
        "original_retry2_hard_conflict": True,
        "original_artifacts_preserved_without_rewrite": True,
        "prior_result_regrading_allowed": False,
    }
    assert workload["historical_lineage_audit_v2"] == {
        "fresh_npu_rerun_required": True,
        "offline_regrade_only_forbidden": True,
        "structured_facts_are_hard_gates": True,
        "exact_init_log_line_is_hard_gate": False,
        "logger_wording_is_informational_only": True,
        "require_prior_patch_lifecycle_request_counts": True,
        "require_prior_overlay_and_base_hashes": True,
        "require_prior_http_and_token_checks": True,
        "require_prior_cleanup_clean": True,
        "require_prior_positions_cpu_failure_absent": True,
        "hard_conflict_policy": "stop_before_fresh_lifecycle",
    }
    assert workload["grading_gate"] == {
        "required_zero_exit_codes": [
            "historical_lineage_audit_v2_exit_code",
            "server_ready_exit_code",
            "live_metrics_preflight_exit_code",
            "ladder_exit_code",
        ],
        "resource_gate_must_pass": True,
        "all_six_slots_must_complete": True,
        "all_successes_require_complete_spec_metrics": True,
        "all_successes_require_positive_draft_deltas": True,
        "cleanup_must_be_clean": True,
        "any_failed_hard_gate_forbids_green_or_yellow": True,
    }
    assert workload["acceptance"]["green_grade"] == (
        "green_mtp_decode_length_ladder_revalidated"
    )
    assert workload["acceptance"]["yellow_recovered_grade"] == (
        "yellow_mtp_decode_length_ladder_revalidated_with_retry"
    )
    assert workload["acceptance"]["missing_spec_metrics_grade"] == (
        "red_mtp_decode_length_metrics_incomplete"
    )
    assert "yellow_log_only_grade" not in workload["acceptance"]


def test_p6_1l_rerun_freezes_runtime_request_retry_and_stop_boundaries():
    workload = load_yaml(
        BENCHMARK_DIR
        / "workloads"
        / "p6_1l_mtp_decode_length_ladder_rerun1.yaml"
    )

    assert workload["runtime_fixed"]["model_path"] == (
        "/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp"
    )
    assert workload["runtime_fixed"]["tensor_parallel_size"] == 8
    assert workload["runtime_fixed"]["enable_expert_parallel"] is True
    assert workload["runtime_fixed"]["speculative_mtp"] == {
        "method": "mtp",
        "num_speculative_tokens": 1,
    }
    assert workload["experiment_plan"]["attempts_max"] == 12
    assert workload["experiment_plan"]["retries_max"] == 6
    assert workload["experiment_plan"]["concurrency"] == 1
    assert workload["request_protocol"]["endpoint"] == "/v1/completions"
    assert workload["request_protocol"]["output_tokens_by_group"] == [512, 1024]
    assert workload["request_protocol"]["min_tokens_equals_max_tokens"] is True
    assert workload["request_protocol"]["generated_text_retained"] is False
    assert workload["request_protocol"]["token_ids_retained"] is False
    assert workload["retry_policy"]["max_retries_per_slot"] == 1
    assert workload["retry_policy"]["same_request_body_sha256_required"] is True
    assert workload["retry_policy"]["server_restart_allowed"] is False
    assert workload["metrics_evidence"]["live_metrics_preflight_required"] is True
    assert workload["metrics_evidence"]["request_gauges_required"] is True
    assert workload["stop_policy"]["no_second_server_lifecycle"] is True
    assert workload["stop_policy"]["no_context_ladder"] is True
    assert workload["stop_policy"]["no_profiler"] is True
    assert workload["stop_policy"]["no_p8_execution"] is True


def test_p6_1c_official_context_ladder_is_closed_before_r1():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1c_mtp_official_context_ladder.yaml"
    )

    assert workload["workload_id"] == (
        "p6_1c_deepseek_v4_flash_mtp_official_context_ladder"
    )
    assert workload["task_id"] == (
        "p6_1c_deepseek_v4_flash_w8a8_mtp_official_context_ladder_2026_0714"
    )
    assert workload["stage_contract"] == {
        "stage": "P6.1C",
        "mode": "mtp_official_context_ladder_with_hbm_sampling_calibration",
        "claim_boundary": "mtp_context_ladder_functional_capacity_and_stability_only",
        "may_claim_performance_baseline": False,
        "profiler_authorized": False,
        "p8_execution_authorized": False,
    }
    assert workload["execution_state"] == {
        "status": "completed_blocked_sampling_calibration",
        "server_handoff": "superseded_by_p6_1c_r1_prepared_not_dispatched",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
    }


def test_p6_1c_completed_as_blocked_sampling_without_official_context_evidence():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1c_mtp_official_context_ladder.yaml"
    )

    result = workload["completed_result"]
    assert result["server_grade"] == "blocked_sampling_calibration"
    assert result["developer_review"] == "accepted_blocked_sampling_calibration"
    assert result["server_git_head"] == (
        "c4bf41c63f4ca094ceb844d14c436e771cc53470"
    )
    assert result["sampling_failure"] == {
        "command": "npu-smi info -t usages",
        "npu_smi_version": "26.0.rc1",
        "raw_sweep_count": 36,
        "all_eight_devices_and_no_parse_failures": False,
        "sweep_wall_seconds_p50": 0.5375788585,
        "sweep_wall_seconds_p95": 0.553860023,
        "selected_interval_seconds": None,
        "first_failure": "command_requires_card_id_and_returns_help_text",
    }
    assert result["official_lifecycle_started"] is False
    assert result["highest_stable_context"] is None
    assert result["official_reference_baseline"] is False
    assert result["cleanup"] == "clean"
    assert result["evidence_boundary"] == {
        "calibration_requests_count_as_official_context_evidence": False,
        "request_success_and_mtp_counters": (
            "server_summary_only_missing_request_results_and_counter_snapshots"
        ),
        "transfer_hash_match": (
            "server_reported_missing_transfer_manifest_in_received_package"
        ),
    }
    assert result["received_package"] == {
        "relative_inbox_path": (
            "2026-07-14/p6_1c_blocked_sampling_calibration_20260714"
        ),
        "file_count": 9,
        "total_bytes": 10267,
        "sorted_name_bytes_sha256_manifest_sha256": (
            "fbfe0aa9f34a5b912de895f42df2a1a8effb83a51155a04fb926a342ace67304"
        ),
    }


def test_p6_1c_r1_sampling_repair_is_closed_as_developer_accepted_green():
    workload = load_yaml(
        BENCHMARK_DIR
        / "workloads"
        / "p6_1c_r1_mtp_official_context_ladder_sampling_repair.yaml"
    )

    assert workload["workload_id"] == (
        "p6_1c_r1_deepseek_v4_flash_mtp_official_context_ladder_sampling_repair"
    )
    assert workload["task_id"] == (
        "p6_1c_r1_deepseek_v4_flash_w8a8_mtp_official_context_ladder_"
        "sampling_repair_2026_0714"
    )
    assert workload["stage_contract"] == {
        "stage": "P6.1C-R1",
        "mode": "mtp_official_context_ladder_hbm_table_sampling_repair",
        "claim_boundary": "mtp_context_ladder_functional_capacity_and_stability_only",
        "may_claim_performance_baseline": False,
        "profiler_authorized": False,
        "p8_execution_authorized": False,
    }
    assert workload["execution_state"] == {
        "status": "completed_developer_accepted_green",
        "server_handoff": "completed_superseded_by_p6_1_unprofiled_baseline",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
    }
    result = workload["completed_result"]
    assert result["server_grade"] == "candidate_green_mtp_official_context_ladder"
    assert result["developer_grade"] == "green_mtp_official_context_ladder"
    assert result["server_git_head"] == (
        "b2e4f14cd739177e90f262b420f25c1cb8de4fa5"
    )
    assert result["highest_stable_context"] == 131072
    assert result["official_reference_baseline"] is True
    assert result["performance_reference_baseline"] is False
    assert result["official_contexts"] == [4096, 32768, 65536, 98304, 131072]
    assert result["all_first_attempt_successes"] is True
    assert result["retry_count"] == 0
    assert result["mtp_counter_totals"] == {
        "drafts": 160.0,
        "draft_tokens": 160.0,
        "accepted_tokens": 160.0,
    }
    assert result["cleanup"] == "clean"
    assert result["received_package"]["file_count"] == 13
    assert result["received_package"]["total_bytes"] == 47955
    assert result["received_package"]["aggregate_sha256"] == (
        "e03639bd43b71112c5027ac79fa44b8b11abeed18a709e1a2659468afbed953f"
    )


def test_p6_1c_r1_preserves_the_blocked_parent_and_requires_a_fresh_rerun():
    workload = load_yaml(
        BENCHMARK_DIR
        / "workloads"
        / "p6_1c_r1_mtp_official_context_ladder_sampling_repair.yaml"
    )

    assert workload["parent_result"] == {
        "task_id": (
            "p6_1c_deepseek_v4_flash_w8a8_mtp_official_context_ladder_"
            "2026_0714"
        ),
        "server_grade": "blocked_sampling_calibration",
        "developer_review": "accepted_blocked_sampling_calibration",
        "failed_command": "npu-smi info -t usages",
        "raw_sweep_count": 36,
        "selected_interval_seconds": None,
        "official_lifecycle_started": False,
        "highest_stable_context": None,
        "cleanup": "clean",
    }
    assert workload["rerun_policy"] == {
        "new_result_lineage_required": True,
        "fresh_calibration_lifecycle_required": True,
        "fresh_official_lifecycle_required_after_calibration_green": True,
        "reuse_prior_calibration_measurements": False,
        "prior_4096_64_green_remains_valid": True,
        "prior_decode_length_green_remains_valid": True,
    }


def test_p6_1_mtp_unprofiled_baseline_freezes_the_accepted_runtime_and_result():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1_mtp_unprofiled_baseline.yaml"
    )

    assert workload["workload_id"] == (
        "p6_1_deepseek_v4_flash_mtp_unprofiled_baseline"
    )
    assert workload["task_id"] == (
        "p6_1_deepseek_v4_flash_w8a8_mtp_unprofiled_baseline_2026_0714"
    )
    assert workload["stage_contract"] == {
        "stage": "P6.1",
        "mode": "mtp_unprofiled_pilot_then_matrix",
        "claim_boundary": "mtp_unprofiled_streaming_performance_baseline_only",
        "official_functional_reference_baseline": True,
        "may_claim_performance_reference_baseline": (
            "only_after_external_developer_review"
        ),
        "profiler_authorized": False,
        "p8_execution_authorized": False,
        "optimization_comparison_authorized": False,
    }
    prerequisite = workload["accepted_prerequisite"]
    assert prerequisite["workload"] == (
        "p6_1c_r1_mtp_official_context_ladder_sampling_repair.yaml"
    )
    assert prerequisite["developer_grade"] == "green_mtp_official_context_ladder"
    assert prerequisite["highest_stable_context"] == 131072
    assert prerequisite["official_reference_baseline"] is True
    runtime = workload["runtime_fixed"]
    assert runtime["server_command_sha256"] == (
        "370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19"
    )
    assert runtime["tensor_parallel_size"] == 8
    assert runtime["enable_expert_parallel"] is True
    assert runtime["max_num_seqs"] == 1
    assert runtime["speculative_mtp"] == {
        "method": "mtp",
        "num_speculative_tokens": 1,
    }
    assert workload["execution_state"] == {
        "status": "completed_developer_accepted_green",
        "server_handoff": "completed",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
    }


def test_p6_1_mtp_unprofiled_baseline_runs_pilot_then_expands_without_a_pause():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1_mtp_unprofiled_baseline.yaml"
    )

    assert workload["lifecycle_plan"] == {
        "server_lifecycles_max": 1,
        "hidden_warmup_requests": 0,
        "explicit_warmup_batches": 1,
        "measured_batches": 24,
        "measured_requests": 90,
        "unprofiled": True,
        "hbm_sampler_enabled": False,
    }
    assert workload["warmup_cell"] == {
        "context_tokens": 4096,
        "output_tokens": 64,
        "concurrency": 1,
        "batches": 1,
        "excluded_from_statistics": True,
    }
    assert workload["pilot_plan"] == {
        "cells": [
            {"context_tokens": 4096, "output_tokens": 64, "concurrency": 1},
            {"context_tokens": 65536, "output_tokens": 64, "concurrency": 4},
            {"context_tokens": 131072, "output_tokens": 64, "concurrency": 1},
        ],
        "batches_per_cell": 3,
        "measured_batches": 9,
        "measured_requests": 18,
        "auto_expand_after_green": True,
        "variability_is_diagnostic_not_an_expansion_gate": True,
    }
    matrix = workload["matrix_plan"]
    assert matrix["contexts_tokens"] == [4096, 65536, 131072]
    assert matrix["output_tokens"] == [64, 256]
    assert matrix["concurrency"] == [1, 4, 8]
    assert matrix["cell_count"] == 18
    assert matrix["pilot_cells_reused_without_rerun"] is True
    assert matrix["remaining_cells_run_once"] == 15
    assert matrix["remaining_measured_requests"] == 72
    assert matrix["continue_after_independent_cell_failure_if_server_healthy"] is True
    assert workload["retry_policy"] == {
        "request_retries": 0,
        "cell_retries": 0,
        "server_restarts": 0,
        "reason": "retries_would_contaminate_the_unprofiled_baseline",
    }


def test_p6_1_mtp_unprofiled_baseline_keeps_metrics_clean_and_results_bounded():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1_mtp_unprofiled_baseline.yaml"
    )

    bodies = workload["canonical_body_policy"]
    assert bodies["freeze_before_server_start"] is True
    assert bodies["construction"] == "repeat_truncate_and_distinct_cyclic_offsets"
    assert bodies["pairwise_common_prefix_tokens_less_than"] == 128
    assert bodies["unique_request_body_sha256_required"] is True
    assert bodies["generated_text_retained"] is False
    assert bodies["token_ids_retained"] is False
    protocol = workload["request_protocol"]
    assert protocol["endpoint"] == "/v1/completions"
    assert protocol["temperature"] == 0.0
    assert protocol["ignore_eos"] is True
    assert protocol["min_tokens_equals_max_tokens"] is True
    assert protocol["streaming"] is True
    assert protocol["return_token_ids"] is True
    metrics = workload["metrics"]
    assert metrics["client_clock"] == "time.monotonic_ns"
    assert metrics["ttft_definition"] == "first_token_ns-request_start_ns"
    assert metrics["tpot_definition"] == (
        "(last_token_ns-first_token_ns)/(completion_tokens-1)"
    )
    assert metrics["e2el_definition"] == "request_end_ns-request_start_ns"
    assert metrics["batch_output_throughput_definition"] == (
        "sum_completion_tokens/(batch_end_ns-batch_start_ns)"
    )
    assert metrics["exact_token_arrival_timestamps_required"] is True
    assert metrics["profiler_or_hbm_sampler_running"] is False
    assert workload["statistics_policy"]["outlier_removal"] is False
    assert workload["statistics_policy"]["request_level_p95_p99_for_n_lt_20"] is False
    assert workload["statistics_policy"]["itl_p50_p95_p99_with_sample_count"] is True
    assert workload["acceptance"]["server_candidate_green_grade"] == (
        "candidate_green_mtp_unprofiled_baseline"
    )
    assert workload["acceptance"]["developer_accepted_green_grade"] == (
        "green_mtp_unprofiled_baseline"
    )
    assert workload["acceptance"]["green_requires_all_90_measured_requests"] is True
    assert workload["acceptance"]["performance_baseline_requires_developer_review"] is True
    package = workload["result_package_policy"]
    assert package["max_total_bytes"] == 71680
    assert package["raw_timestamps_metrics_logs_and_bodies_remain_server_local"] is True
    assert package["generated_text_or_token_ids_allowed"] is False
    assert package["selection_required_before_any_transfer"] is True
    assert package["handoff_contains_transfer_command"] is False
    assert workload["stop_policy"]["profiler_allowed"] is False
    assert workload["stop_policy"]["p8_execution_allowed"] is False
    assert workload["stop_policy"]["runtime_or_parameter_mutation_allowed"] is False


def test_p6_1_mtp_unprofiled_baseline_is_closed_as_developer_green():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1_mtp_unprofiled_baseline.yaml"
    )

    assert workload["execution_result"]["developer_grade"] == (
        "green_mtp_unprofiled_baseline"
    )
    assert workload["execution_result"]["performance_reference_baseline"] is True
    assert workload["execution_result"]["measured_requests"] == 90
    assert workload["execution_result"]["measured_batches"] == 24
    assert workload["execution_result"]["represented_cells"] == 18
    assert workload["execution_result"]["accepted_token_delta_total"] == 6624.0
    assert workload["metrics"]["token_chunk_width_allowed_max"] == 2
    assert workload["metrics"]["same_sse_chunk_tokens_share_arrival_timestamp"] is True
    assert workload["metrics"]["itl_scope"] == "client_observed_sse_delivery_gap"
    assert workload["execution_state"] == {
        "status": "completed_developer_accepted_green",
        "server_handoff": "completed",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
    }


def test_p6_2_mtp_profiled_evidence_uses_three_independent_reference_cells():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_2_mtp_profiled_evidence.yaml"
    )

    assert workload["workload_id"] == (
        "p6_2_deepseek_v4_flash_mtp_profiled_evidence"
    )
    assert workload["task_id"] == (
        "p6_2_deepseek_v4_flash_w8a8_mtp_profiled_evidence_2026_0714"
    )
    assert workload["stage_contract"] == {
        "stage": "P6.2",
        "mode": "mtp_profiled_representative_cells",
        "claim_boundary": (
            "mtp_profiled_operator_memory_transfer_and_request_device_evidence_only"
        ),
        "performance_reference_baseline": True,
        "profiled_latency_is_performance_baseline": False,
        "p8_execution_authorized": False,
        "optimization_comparison_authorized": False,
    }
    assert workload["profiled_cells"] == [
        {
            "cell_id": "short_prefill",
            "context_tokens": 4096,
            "output_tokens": 64,
            "concurrency": 1,
        },
        {
            "cell_id": "long_prefill",
            "context_tokens": 131072,
            "output_tokens": 64,
            "concurrency": 1,
        },
        {
            "cell_id": "decode_heavy",
            "context_tokens": 4096,
            "output_tokens": 256,
            "concurrency": 1,
        },
    ]
    lifecycle = workload["lifecycle_plan"]
    assert lifecycle["server_lifecycles_max"] == 3
    assert lifecycle["one_cell_per_fresh_lifecycle"] is True
    assert lifecycle["warmup_requests_per_cell"] == 1
    assert lifecycle["measured_requests_per_cell"] == 1
    assert lifecycle["request_retries"] == 0
    assert lifecycle["continue_independent_cell_after_clean_failure"] is True
    assert workload["phase_memory"]["sample_interval_seconds"] == 1.0
    assert workload["phase_memory"]["npu_smi_one_table_all_eight_devices"] is True
    assert workload["profiler"]["msprof_enabled"] is True
    assert workload["profiler"]["request_device_aggregate_enabled"] is True
    assert workload["profiler"]["raw_profiler_remains_server_local"] is True
    assert workload["execution_state"] == {
        "status": "completed_developer_accepted_green",
        "server_handoff": "completed",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
    }
    result = workload["execution_result"]
    assert result["server_grade"] == "candidate_green_mtp_profiled_evidence"
    assert result["developer_grade"] == "green_mtp_profiled_evidence"
    assert result["profiled_evidence_baseline"] is True
    assert result["performance_reference_baseline_remains_true"] is True
    assert result["profiled_latency_is_performance_baseline"] is False
    assert result["measured_cells"] == 3
    assert result["accepted_token_delta_total"] == 192.0
    assert result["profiler_sqlite_files_per_cell"] == 136
    assert result["phase_memory_rows"] == 6
    assert result["minimum_device_coverage"] == 8
    assert result["parse_failure_count"] == 0
    assert result["retry_count"] == 0
    assert result["cleanup_status"] == "clean"


def test_p6_1c_r1_uses_one_eight_device_table_sweep_and_feasible_sampling_gates():
    workload = load_yaml(
        BENCHMARK_DIR
        / "workloads"
        / "p6_1c_r1_mtp_official_context_ladder_sampling_repair.yaml"
    )

    preflight = workload["hbm_sampler_preflight"]
    assert preflight == {
        "before_model_server_start": True,
        "command": "npu-smi info",
        "sweeps": 3,
        "required_device_ids": list(range(8)),
        "required_hbm_capacity_mb_per_device": 65536,
        "required_fields": ["device_id", "hbm_used_mb", "hbm_capacity_mb"],
        "all_sweeps_return_code_zero": True,
        "all_sweeps_parse_eight_devices": True,
        "sweep_wall_time_diagnostic_only": True,
        "failure_grade": "blocked_protocol_or_resource_gate",
    }

    calibration = workload["hbm_sampling_calibration"]
    assert calibration["context_tokens"] == 65536
    assert calibration["output_tokens"] == 64
    assert calibration["counts_as_official_context_evidence"] is False
    assert calibration["hbm_sweep"] == {
        "command": "npu-smi info",
        "one_subprocess_per_sweep": True,
        "parses_all_eight_devices_from_one_table": True,
        "source_field": "HBM-Usage(MB)",
        "derived_field": "hbm_usage_pct",
        "record_start_end_wall_time_and_start_gap": True,
    }
    assert calibration["candidate_intervals_seconds"] == [0.5, 1.0, 2.0, 5.0]
    assert calibration["selection_gates"] == {
        "device_coverage_required": 8,
        "parse_failures_allowed": 0,
        "max_hbm_usage_peak_delta_percentage_points": 1.0,
        "min_reference_prefill_samples_per_device": 4,
        "min_selected_prefill_samples_per_device": 2,
    }
    assert calibration["sweep_wall_duty_cycle"] == {
        "record_p50_p95_and_ratio": True,
        "hard_gate": False,
        "reason": "subprocess_wall_time_is_not_inference_interference",
    }
    assert calibration["selected_validation"] == {
        "max_wall_time_increase_ratio": 0.10,
        "hard_interference_gate": True,
        "token_health_queue_and_mtp_gates_required": True,
        "diagnostic_only_not_performance": True,
    }
    assert calibration["selection_policy"] == "largest_interval_passing_all_gates"
    assert calibration["failure_grade"] == "blocked_sampling_calibration"
    assert calibration["failure_stops_before_official_lifecycle"] is True
    assert calibration["raw_traces_remain_server_local"] is True


def test_p6_1c_r1_reuses_the_verified_runtime_and_three_calibration_bodies():
    workload = load_yaml(
        BENCHMARK_DIR
        / "workloads"
        / "p6_1c_r1_mtp_official_context_ladder_sampling_repair.yaml"
    )

    assert workload["accepted_prerequisites"] == {
        "minimal_mtp_task_id": (
            "p6_1r_deepseek_v4_flash_w8a8_bounded_mtp_reference_repair_"
            "retry2_2026_0713"
        ),
        "minimal_mtp_grade": "green_mtp_minimal_request_success",
        "decode_length_task_id": (
            "p6_1l_deepseek_v4_flash_w8a8_mtp_decode_length_ladder_"
            "rerun1_2026_0713"
        ),
        "decode_length_grade": "green_mtp_decode_length_ladder_revalidated",
        "prior_green_results_remain_valid_on_r1_failure": True,
    }
    assert workload["lifecycle_plan"] == {
        "server_lifecycles_max": 2,
        "order": [
            "hbm_sampling_calibration_lifecycle",
            "fresh_official_context_ladder_lifecycle",
        ],
        "official_lifecycle_requires_calibration_green": True,
        "cleanup_between_lifecycles_required": True,
        "calibration_cache_or_counters_may_carry_over": False,
    }
    assert workload["repair_artifact"]["patch_sha256"] == (
        "75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1"
    )
    assert workload["repair_artifact"]["patched_proposer_sha256"] == (
        "7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02"
    )
    runtime = workload["runtime_fixed"]
    assert runtime["model_path"] == "/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp"
    assert runtime["vllm_commit"] == "0decac0d96c42b49572498019f0a0e3600f50398"
    assert runtime["vllm_ascend_commit"] == "5f6faa0cb8830f667266f3b8121cd1383606f2a1"
    assert runtime["server_command_sha256"] == (
        "370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19"
    )
    assert runtime["max_model_len"] == 135168
    assert runtime["max_num_seqs"] == 1
    assert runtime["tensor_parallel_size"] == 8
    assert runtime["enable_expert_parallel"] is True
    assert runtime["enforce_eager"] is False
    assert runtime["cudagraph_mode"] == "FULL_DECODE_ONLY"
    assert runtime["speculative_mtp"] == {"method": "mtp", "num_speculative_tokens": 1}

    calibration = workload["hbm_sampling_calibration"]
    assert calibration["requests"] == [
        {"role": "calibration_control", "sampling_enabled": False},
        {
            "role": "calibration_high_resolution",
            "sampling_enabled": True,
            "requested_min_start_interval_seconds": 0.5,
        },
        {
            "role": "calibration_selected_validation",
            "sampling_enabled": True,
            "interval_source": "selected_interval_from_calibration",
        },
    ]
    assert calibration["payload_construction"] == {
        "source_prompt_tokens": 4096,
        "target_prompt_tokens": 65536,
        "method": "repeat_then_apply_distinct_cyclic_offsets",
        "same_token_multiset_required": True,
        "pairwise_common_prefix_tokens_required": 0,
        "canonical_bodies_frozen_before_server_start": True,
    }


def test_p6_1c_r1_preserves_the_official_ladder_retry_and_grading_boundaries():
    workload = load_yaml(
        BENCHMARK_DIR
        / "workloads"
        / "p6_1c_r1_mtp_official_context_ladder_sampling_repair.yaml"
    )

    ladder = workload["official_context_ladder"]
    assert ladder["contexts_tokens"] == [4096, 32768, 65536, 98304, 131072]
    assert ladder["output_tokens"] == 64
    assert ladder["hidden_warmup_requests"] == 0
    assert ladder["concurrency"] == 1
    assert ladder["selected_hbm_interval_frozen_for_all_attempts"] is True
    assert ladder["highest_stable_context_excludes_calibration"] is True

    request = workload["request_protocol"]
    assert request["endpoint"] == "/v1/completions"
    assert request["temperature"] == 0.0
    assert request["ignore_eos"] is True
    assert request["min_tokens_equals_max_tokens"] is True
    assert request["streaming"] is True
    assert request["generated_text_retained"] is False
    assert request["token_ids_retained"] is False

    metrics = workload["metrics_evidence"]
    assert metrics["snapshot_before_and_after_every_attempt"] is True
    assert metrics["positive_drafts_per_success"] is True
    assert metrics["positive_draft_tokens_per_success"] is True
    assert metrics["positive_accepted_delta_total_required"] is True
    assert metrics["counter_continuity_required"] is True

    retry = workload["retry_policy"]
    assert retry["max_retries_per_context"] == 1
    assert retry["max_retries_total"] == 5
    assert retry["attempts_total_max"] == 10
    assert retry["same_request_body_sha256_required"] is True
    assert retry["selected_hbm_interval_must_remain_frozen"] is True
    assert retry["server_restart_allowed"] is False

    acceptance = workload["acceptance"]
    assert acceptance["blocked_sampling_grade"] == "blocked_sampling_calibration"
    assert acceptance["partial_grade"] == "yellow_mtp_context_ladder_partial"
    assert acceptance["retry_grade"] == (
        "yellow_mtp_official_context_ladder_recovered_with_retry"
    )
    assert acceptance["server_candidate_green_grade"] == (
        "candidate_green_mtp_official_context_ladder"
    )
    assert acceptance["developer_accepted_green_grade"] == (
        "green_mtp_official_context_ladder"
    )
    assert acceptance["official_baseline_requires_external_developer_review"] is True
    assert acceptance["retry_path_may_claim_official_baseline"] is False

    stop = workload["stop_policy"]
    assert stop["server_restart_allowed"] is False
    assert stop["parameter_mutation_allowed"] is False
    assert stop["patch_mutation_allowed"] is False
    assert stop["second_patch_allowed"] is False
    assert stop["mtp_disable_allowed"] is False
    assert stop["context_reduction_allowed"] is False
    assert stop["eager_fallback_allowed"] is False
    assert stop["profiler_allowed"] is False
    assert stop["p8_execution_allowed"] is False


def test_p6_1c_r1_keeps_raw_hbm_and_content_out_of_the_bounded_result_package():
    workload = load_yaml(
        BENCHMARK_DIR
        / "workloads"
        / "p6_1c_r1_mtp_official_context_ladder_sampling_repair.yaml"
    )

    hbm = workload["hbm_resource_evidence"]
    assert hbm["scope"] == "whole_device_hbm_occupancy_not_kv_object_bytes_or_traffic"
    assert hbm["raw_samples_remain_server_local"] is True
    assert hbm["all_eight_devices_required_for_green"] is True
    assert hbm["per_attempt_summary_fields"] == [
        "context_tokens",
        "attempt_index",
        "selected_interval_seconds",
        "device_id",
        "sample_count",
        "hbm_capacity_mb",
        "hbm_used_max_mb",
        "hbm_free_min_mb",
        "hbm_usage_pct_max",
        "parser_ok",
    ]

    schema = workload["attempt_result_schema"]
    assert schema["format"] == "json_lines_one_record_per_attempt"
    assert "request_body_sha256" in schema["fields"]
    assert "selected_hbm_interval_seconds" in schema["fields"]
    assert "request_wall_ms_diagnostic_only" in schema["fields"]
    assert schema["generated_text_field_forbidden"] is True
    assert schema["token_ids_field_forbidden"] is True

    package = workload["result_package_policy"]
    assert package["max_total_bytes"] == 71680
    assert package["raw_logs_metrics_hbm_and_request_bodies_remain_server_local"] is True
    assert package["generated_text_or_token_ids_allowed"] is False
    assert package["selection_required_before_any_transfer"] is True
    assert package["available_methods"] == ["email", "upload-api", "server-local"]
    assert package["methods_are_mutually_exclusive"] is True
    assert package["handoff_contains_transfer_command"] is False
    assert "sampler_preflight.json" in package["bounded_candidates"]
    assert "calibration_request_summary.json" in package["bounded_candidates"]
    assert package["calibration_request_summary_required_for_developer_review"] is True


def test_p6_1c_calibrates_and_freezes_hbm_sampling_before_the_official_ladder():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1c_mtp_official_context_ladder.yaml"
    )

    lifecycle = workload["lifecycle_plan"]
    assert lifecycle["server_lifecycles_max"] == 2
    assert lifecycle["order"] == [
        "hbm_sampling_calibration_lifecycle",
        "fresh_official_context_ladder_lifecycle",
    ]
    assert lifecycle["official_lifecycle_requires_calibration_green"] is True
    assert lifecycle["cleanup_between_lifecycles_required"] is True
    assert lifecycle["calibration_cache_or_counters_may_carry_over"] is False

    calibration = workload["hbm_sampling_calibration"]
    assert calibration["context_tokens"] == 65536
    assert calibration["output_tokens"] == 64
    assert calibration["counts_as_official_context_evidence"] is False
    assert [request["role"] for request in calibration["requests"]] == [
        "calibration_control",
        "calibration_high_resolution",
        "calibration_selected_validation",
    ]
    assert calibration["requests"][0]["sampling_enabled"] is False
    assert calibration["requests"][1]["target_interval_seconds"] == 0.5
    assert calibration["requests"][2]["interval_source"] == (
        "selected_interval_from_calibration"
    )
    assert calibration["payload_construction"] == {
        "source_prompt_tokens": 4096,
        "target_prompt_tokens": 65536,
        "method": "repeat_then_apply_distinct_cyclic_offsets",
        "same_token_multiset_required": True,
        "pairwise_common_prefix_tokens_required": 0,
        "canonical_bodies_frozen_before_server_start": True,
    }
    assert calibration["hbm_sweep"] == {
        "command": "npu-smi info -t usages",
        "required_device_ids": list(range(8)),
        "required_fields": [
            "NPU ID",
            "HBM Capacity(MB)",
            "HBM Usage Rate(%)",
        ],
        "record_start_end_and_wall_time": True,
    }
    assert calibration["candidate_intervals_seconds"] == [0.5, 1.0, 2.0, 5.0]
    assert calibration["selection_policy"] == "largest_interval_passing_all_gates"
    assert calibration["selection_gates"] == {
        "device_coverage_required": 8,
        "parse_failures_allowed": 0,
        "max_hbm_usage_peak_delta_percentage_points": 1.0,
        "min_prefill_samples_per_device": 20,
        "max_p95_sweep_duty_cycle_ratio": 0.05,
    }
    assert calibration["selected_validation"]["max_wall_time_increase_ratio"] == 0.10
    assert calibration["selected_validation"]["diagnostic_only_not_performance"] is True
    assert calibration["failure_grade"] == "blocked_sampling_calibration"
    assert calibration["failure_stops_before_official_lifecycle"] is True
    assert calibration["raw_traces_remain_server_local"] is True


def test_p6_1c_reuses_the_accepted_mtp_runtime_without_fallbacks():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1c_mtp_official_context_ladder.yaml"
    )

    assert workload["accepted_prerequisites"] == {
        "minimal_mtp_task_id": (
            "p6_1r_deepseek_v4_flash_w8a8_bounded_mtp_reference_repair_"
            "retry2_2026_0713"
        ),
        "minimal_mtp_grade": "green_mtp_minimal_request_success",
        "decode_length_task_id": (
            "p6_1l_deepseek_v4_flash_w8a8_mtp_decode_length_ladder_"
            "rerun1_2026_0713"
        ),
        "decode_length_grade": "green_mtp_decode_length_ladder_revalidated",
        "prior_green_results_remain_valid_on_new_task_failure": True,
    }
    assert workload["repair_artifact"] == {
        "path": (
            "benchmarks/deepseek_v4_flash/patches/"
            "vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch"
        ),
        "patch_sha256": (
            "75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1"
        ),
        "patched_proposer_sha256": (
            "7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02"
        ),
        "unchanged_base_proposer_sha256": (
            "0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb"
        ),
        "task_local_overlay_only": True,
        "patch_attempts_per_lifecycle_max": 1,
    }
    runtime = workload["runtime_fixed"]
    assert runtime["model_path"] == "/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp"
    assert runtime["vllm_commit"] == "0decac0d96c42b49572498019f0a0e3600f50398"
    assert runtime["vllm_ascend_commit"] == "5f6faa0cb8830f667266f3b8121cd1383606f2a1"
    assert runtime["server_command_sha256"] == (
        "370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19"
    )
    assert runtime["max_model_len"] == 135168
    assert runtime["max_num_seqs"] == 1
    assert runtime["tensor_parallel_size"] == 8
    assert runtime["enable_expert_parallel"] is True
    assert runtime["enforce_eager"] is False
    assert runtime["cudagraph_mode"] == "FULL_DECODE_ONLY"
    assert runtime["speculative_mtp"] == {"method": "mtp", "num_speculative_tokens": 1}
    assert workload["source_payload"] == {
        "server_path": (
            "工作记录与进度笔记本/runtime_trace_smokes/"
            "p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_"
            "v0221rc1_2026_0712/request_payload.json"
        ),
        "prompt_tokens": 4096,
        "bytes": 19487,
        "sha256": (
            "48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1"
        ),
    }
    assert workload["stop_policy"]["server_restart_allowed"] is False
    assert workload["stop_policy"]["parameter_mutation_allowed"] is False
    assert workload["stop_policy"]["mtp_disable_allowed"] is False
    assert workload["stop_policy"]["context_reduction_allowed"] is False
    assert workload["stop_policy"]["eager_fallback_allowed"] is False
    assert workload["stop_policy"]["version_upgrade_allowed"] is False


def test_p6_1c_freezes_the_five_slot_ladder_and_hard_gate_grading():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1c_mtp_official_context_ladder.yaml"
    )

    ladder = workload["official_context_ladder"]
    assert ladder["contexts_tokens"] == [4096, 32768, 65536, 98304, 131072]
    assert ladder["output_tokens"] == 64
    assert ladder["slots_per_context"] == 1
    assert ladder["hidden_warmup_requests"] == 0
    assert ladder["concurrency"] == 1
    assert ladder["request_order"] == "sequential"
    assert ladder["selected_hbm_interval_frozen_for_all_attempts"] is True
    assert ladder["highest_stable_context_excludes_calibration"] is True
    assert ladder["canonical_body_policy"] == {
        "method": "repeat_and_truncate_frozen_4096_prompt_ids",
        "freeze_before_first_lifecycle": True,
        "record_prompt_tokens_body_bytes_and_sha256_per_context": True,
        "same_body_bytes_required_for_retry": True,
    }

    request = workload["request_protocol"]
    assert request["endpoint"] == "/v1/completions"
    assert request["temperature"] == 0.0
    assert request["ignore_eos"] is True
    assert request["min_tokens_equals_max_tokens"] is True
    assert request["streaming"] is True
    assert request["stream_include_usage"] is True
    assert request["return_token_ids"] is True
    assert request["generated_text_retained"] is False
    assert request["token_ids_retained"] is False

    metrics = workload["metrics_evidence"]
    assert metrics["snapshot_before_and_after_every_attempt"] is True
    assert metrics["spec_counter_names"] == [
        "vllm:spec_decode_num_drafts_total",
        "vllm:spec_decode_num_draft_tokens_total",
        "vllm:spec_decode_num_accepted_tokens_total",
    ]
    assert metrics["request_gauge_names"] == [
        "vllm:num_requests_running",
        "vllm:num_requests_waiting",
    ]
    assert metrics["positive_drafts_per_success"] is True
    assert metrics["positive_draft_tokens_per_success"] is True
    assert metrics["zero_accepted_delta_per_slot_allowed"] is True
    assert metrics["positive_accepted_delta_total_required"] is True
    assert metrics["counter_continuity_required"] is True

    retry = workload["retry_policy"]
    assert retry["max_retries_per_context"] == 1
    assert retry["max_retries_total"] == 5
    assert retry["attempts_total_max"] == 10
    assert retry["same_request_body_sha256_required"] is True
    assert retry["health_200_and_idle_queue_required"] is True
    assert retry["complete_metrics_required"] is True
    assert retry["second_failure_stops_before_higher_contexts"] is True

    acceptance = workload["acceptance"]
    assert acceptance["blocked_sampling_grade"] == "blocked_sampling_calibration"
    assert acceptance["blocked_pre_request_grade"] == "blocked_protocol_or_resource_gate"
    assert acceptance["no_success_grade"] == "red_mtp_context_ladder_no_success"
    assert acceptance["partial_grade"] == "yellow_mtp_context_ladder_partial"
    assert acceptance["retry_grade"] == (
        "yellow_mtp_official_context_ladder_recovered_with_retry"
    )
    assert acceptance["server_candidate_green_grade"] == (
        "candidate_green_mtp_official_context_ladder"
    )
    assert acceptance["developer_accepted_green_grade"] == (
        "green_mtp_official_context_ladder"
    )
    assert acceptance["green_requires_all_five_first_attempt_successes"] is True
    assert acceptance["official_baseline_requires_external_developer_review"] is True
    assert acceptance["retry_path_may_claim_official_baseline"] is False


def test_p6_1c_returns_only_bounded_structured_evidence_after_a_new_transfer_choice():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1c_mtp_official_context_ladder.yaml"
    )

    hbm = workload["hbm_resource_evidence"]
    assert hbm["scope"] == "whole_device_hbm_occupancy_not_kv_object_bytes_or_traffic"
    assert hbm["raw_samples_remain_server_local"] is True
    assert hbm["per_attempt_summary_fields"] == [
        "context_tokens",
        "attempt_index",
        "selected_interval_seconds",
        "device_id",
        "sample_count",
        "hbm_capacity_mb",
        "hbm_used_max_mb",
        "hbm_free_min_mb",
        "hbm_usage_pct_max",
        "parser_ok",
    ]
    assert hbm["all_eight_devices_required_for_green"] is True

    schema = workload["attempt_result_schema"]
    assert schema["format"] == "json_lines_one_record_per_attempt"
    assert "request_body_sha256" in schema["fields"]
    assert "hbm_summary_path" in schema["fields"]
    assert "request_wall_ms_diagnostic_only" in schema["fields"]
    assert schema["generated_text_field_forbidden"] is True
    assert schema["token_ids_field_forbidden"] is True

    package = workload["result_package_policy"]
    assert package["max_total_bytes"] == 71680
    assert package["raw_logs_metrics_hbm_and_request_bodies_remain_server_local"] is True
    assert package["generated_text_or_token_ids_allowed"] is False
    assert package["selection_required_before_any_transfer"] is True
    assert package["available_methods"] == ["email", "upload-api", "server-local"]
    assert package["methods_are_mutually_exclusive"] is True
    assert package["report_before_choice"] == [
        "exact_result_summary_path",
        "complete_candidate_file_list",
        "size_bytes_per_file",
        "sha256_per_file",
        "sensitivity_per_file",
        "available_methods",
        "recommended_method_and_reason",
    ]
    assert package["handoff_contains_transfer_command"] is False


def test_server_handoff_authorizes_the_current_p6_3b_r2_deferred_install_task():
    handoff = (REPO_ROOT / "通信模块" / "docs" / "developer-to-server.md").read_text(
        encoding="utf-8"
    )

    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert "## 当前唯一服务器动作：立即执行 P6.3B-R2 deferred-install 修复验证" in handoff
    assert (
        "task_id: p6_3b_r2_deepseek_v4_flash_w8a8_mtp_prefix_cache_"
        "hybrid_kv_deferred_install_repair_2026_0715"
        in handoff
    )
    assert "execution_mode: authorized_for_execution" in handoff
    assert "npu_execution_authorized: true" in handoff
    assert "next_task_authorized: true" in handoff
    assert (
        "benchmarks/deepseek_v4_flash/workloads/"
        "p6_3b_r2_hybrid_kv_deferred_install_repair.yaml"
        in handoff
    )
    assert "yellow_p6_3b_prefix_cache_matched_ab_partial" in handoff
    assert "NPU_EXECUTION_AUTHORIZED=true" in handoff
    assert "run_deepseek_p6_3b_r2_mode.sh" in handoff
    assert "AscendMLAAttentionSpec" in handoff
    assert "AscendSlidingWindowMLASpec" in handoff
    assert "sitecustomize" in handoff
    assert "server_lifecycle_count.txt" in handoff
    assert "立即执行" in handoff


def test_server_handoff_keeps_p6_3b_r1_bounded_and_stops_before_later_stages():
    handoff = (REPO_ROOT / "通信模块" / "docs" / "developer-to-server.md").read_text(
        encoding="utf-8"
    )

    assert "git fetch origin main" in handoff
    assert "git merge --ff-only origin/main" in handoff
    assert "不得使用 `pull-remote` alias" in handoff
    assert "Prefix Cache" in handoff
    assert "prime" in handoff
    assert "64" in handoff
    assert "12" in handoff
    assert "9/9" in handoff
    assert "profiler" in handoff
    assert "HBM sampler" in handoff
    assert "不得自动进入完整 P6.3B matched A/B、P6.3C、P7 或 P8" in handoff
    assert "不得发送 email" in handoff
    assert "不得调用 upload-api" in handoff
    assert "等待用户对该完整范围重新选择唯一传输方法" in handoff


def test_p6_3b_yellow_and_r1_red_are_preserved_while_r2_is_authorized():
    readiness = load_yaml(BENCHMARK_DIR / "p5_readiness_card.yaml")
    artifacts = readiness["artifacts"]
    acceptance = readiness["acceptance"]

    assert artifacts["completed_p6_1r_workload"] == (
        "workloads/p6_1r_bounded_mtp_reference_repair.yaml"
    )
    assert artifacts["completed_p6_1l_rerun_workload"] == (
        "workloads/p6_1l_mtp_decode_length_ladder_rerun1.yaml"
    )
    assert artifacts["completed_p6_1c_workload"] == (
        "workloads/p6_1c_mtp_official_context_ladder.yaml"
    )
    assert artifacts["completed_p6_1c_r1_workload"] == (
        "workloads/p6_1c_r1_mtp_official_context_ladder_sampling_repair.yaml"
    )
    assert artifacts["completed_p6_1_workload"] == (
        "workloads/p6_1_mtp_unprofiled_baseline.yaml"
    )
    assert artifacts["completed_p6_2_workload"] == (
        "workloads/p6_2_mtp_profiled_evidence.yaml"
    )
    assert artifacts["completed_p6_3a_workload"] == (
        "workloads/p6_3a_mtp_matched_ab.yaml"
    )
    assert artifacts["completed_p6_3b_workload"] == (
        "workloads/p6_3b_prefix_cache_matched_ab.yaml"
    )
    assert artifacts["completed_p6_3b_r1_workload"] == (
        "workloads/p6_3b_r1_hybrid_kv_repair.yaml"
    )
    assert artifacts["next_workload"] == (
        "workloads/p6_3b_r2_hybrid_kv_deferred_install_repair.yaml"
    )
    assert readiness["target_runtime"]["runtime_status"] == (
        "p6_3b_r2_deferred_install_repair_authorized"
    )
    assert acceptance["official_reference_baseline"] is True
    assert acceptance["highest_stable_context"] == 131072
    assert acceptance["performance_reference_baseline"] is True
    assert acceptance["profiled_evidence_baseline"] is True
    assert acceptance["blocked_by"] is None
    assert acceptance["p6_3_plan_review_required"] is False
    assert acceptance["p6_3a_matched_ab_baseline"] is True
    assert acceptance["p6_3b_matched_ab_grade"] == (
        "yellow_p6_3b_prefix_cache_matched_ab_partial"
    )
    assert acceptance["p6_3b_execution_authorized"] is False
    assert acceptance["p6_3b_r1_grade"] == (
        "red_p6_3b_r1_hybrid_kv_repair_no_success"
    )
    assert acceptance["p6_3b_r1_execution_authorized"] is False
    assert acceptance["p6_3b_r2_execution_authorized"] is True
    assert acceptance["next_task_authorized"] is True

    current_surfaces = {
        "next_action": REPO_ROOT / "工作记录与进度笔记本" / "05_下一步行动指导.md",
        "stage_plan": REPO_ROOT / "工作记录与进度笔记本" / "02_阶段计划.md",
        "reordered_plan": REPO_ROOT / "工作记录与进度笔记本" / "12_P5_P9_后续阶段重排计划.md",
        "special_plan": REPO_ROOT / "工作记录与进度笔记本" / "09_DeepSeek_V4_Flash_专项计划.md",
        "stable_plan": REPO_ROOT / "docs" / "EXPERIMENT_PLAN.md",
    }
    for name, path in current_surfaces.items():
        text = path.read_text(encoding="utf-8")
        assert "P6.1C-R1" in text, name
        assert "green_mtp_official_context_ladder" in text, name
        assert "131072" in text, name
        assert "green_mtp_unprofiled_baseline" in text, name
        assert "P6.2" in text, name
        assert "profiled" in text, name
        assert "green_mtp_profiled_evidence" in text, name
        assert "P6.3" in text, name
        assert "P6.3A" in text, name
        assert "green_p6_3a_mtp_matched_ab" in text, name
        assert "P6.3B" in text, name
        assert "P6.3B-R1" in text, name
        assert "red_p6_3b_r1_hybrid_kv_repair_no_success" in text, name
        assert "P6.3B-R2" in text, name
        assert "yellow_p6_3b_prefix_cache_matched_ab_partial" in text, name
        assert "hybrid-KV" in text, name
        assert "已授权" in text, name
        assert "short_prefill" in text, name
        assert "long_prefill" in text, name
        assert "decode_heavy" in text, name
        assert "msprof" in text, name
        assert "request-device" in text, name
        assert "P8" in text, name

    review = (
        REPO_ROOT
        / "工作记录与进度笔记本"
        / "16_P6_阶段复盘与P6_3进入评估.md"
    ).read_text(encoding="utf-8")
    assert "green_mtp_official_context_ladder" in review
    assert "green_mtp_unprofiled_baseline" in review
    assert "green_mtp_profiled_evidence" in review
    assert "P6.3A" in review
    assert "P6.3B" in review
    assert "P6.3B-R1" in review
    assert "red_p6_3b_r1_hybrid_kv_repair_no_success" in review
    assert "P6.3B-R2" in review
    assert "yellow_p6_3b_prefix_cache_matched_ab_partial" in review
    assert "hybrid-KV" in review
    assert "green_p6_3a_mtp_matched_ab" in review
    assert "max_model_len" in review
    assert "npu_execution_authorized:true" in review


def test_p6_3a_workload_defines_the_authorized_matched_mtp_ab_contract():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_3a_mtp_matched_ab.yaml"
    )

    assert workload["workload_id"] == "p6_3a_deepseek_v4_flash_mtp_matched_ab"
    assert workload["task_id"] == (
        "p6_3a_deepseek_v4_flash_w8a8_mtp_matched_ab_2026_0715"
    )
    assert workload["stage_contract"] == {
        "stage": "P6.3A",
        "mode": "matched_mtp_on_off_unprofiled_ab",
        "claim_boundary": "matched_mtp_on_off_mechanism_effect_only",
        "performance_reference_baseline": True,
        "profiled_evidence_baseline": True,
        "profiler_authorized": False,
        "hbm_sampler_authorized": False,
        "p6_3b_execution_authorized": False,
        "p8_execution_authorized": False,
    }
    assert workload["execution_state"] == {
        "status": "completed_developer_accepted_green",
        "server_handoff": "historical_not_current",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
    }


def test_p6_3a_changes_only_mtp_across_an_expanded_matched_cell_set():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_3a_mtp_matched_ab.yaml"
    )

    assert workload["mode_order"] == ["mtp_off", "mtp_on"]
    assert workload["single_variable"] == {
        "name": "speculative_mtp",
        "mtp_off_server_delta": "omit_speculative_config_only",
        "mtp_on_server_delta": {
            "method": "mtp",
            "num_speculative_tokens": 1,
        },
        "all_other_server_arguments_identical": True,
        "same_task_local_overlay_and_environment": True,
        "same_canonical_body_bytes_across_modes": True,
    }
    assert workload["lifecycle_plan"] == {
        "server_lifecycles": 2,
        "one_fresh_lifecycle_per_mode": True,
        "hidden_warmup_requests": 0,
        "explicit_warmup_requests_per_mode": 1,
        "measured_batches_per_mode": 24,
        "measured_requests_per_mode": 54,
        "total_measured_batches": 48,
        "total_measured_requests": 108,
        "retries": 0,
        "unprofiled": True,
    }
    assert workload["matched_cells"] == [
        {"cell_id": "short_prefill", "context_tokens": 4096, "output_tokens": 64, "concurrency": 1},
        {"cell_id": "short_decode", "context_tokens": 4096, "output_tokens": 256, "concurrency": 1},
        {"cell_id": "short_decode_c8", "context_tokens": 4096, "output_tokens": 256, "concurrency": 8},
        {"cell_id": "mid_prefill", "context_tokens": 65536, "output_tokens": 64, "concurrency": 1},
        {"cell_id": "mid_prefill_c4", "context_tokens": 65536, "output_tokens": 64, "concurrency": 4},
        {"cell_id": "mid_decode", "context_tokens": 65536, "output_tokens": 256, "concurrency": 1},
        {"cell_id": "long_prefill", "context_tokens": 131072, "output_tokens": 64, "concurrency": 1},
        {"cell_id": "long_decode", "context_tokens": 131072, "output_tokens": 256, "concurrency": 1},
    ]
    assert workload["batches_per_cell_per_mode"] == 3
    assert workload["runtime_fixed"]["max_num_seqs"] == 1
    assert workload["runtime_fixed"]["enable_prefix_caching"] is True
    assert workload["runtime_fixed"]["enable_chunked_prefill"] is True
    assert workload["runtime_fixed"]["cudagraph_mode"] == "FULL_DECODE_ONLY"


def test_p6_3a_mode_runner_freezes_both_server_commands_and_only_toggles_mtp():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_3a_mtp_matched_ab.yaml"
    )
    runner = (
        REPO_ROOT / "tools" / "inference_contracts" / "run_deepseek_p6_3a_mode.sh"
    ).read_text(encoding="utf-8")

    assert workload["server_command_sha256"] == {
        "mtp_off": "c8490730b269ca2cf8a72704877ab040099341ec5fe576ee010d3613a61902bc",
        "mtp_on": "370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19",
    }
    assert 'if test "${MODE}" = mtp_on; then' in runner
    assert "cmd+=(--speculative-config" in runner
    assert runner.count("--speculative-config") == 1
    assert 'EXPECTED_COMMAND_SHA256[mtp_off]=c8490730' in runner
    assert 'EXPECTED_COMMAND_SHA256[mtp_on]=370f8d25' in runner
    assert 'run-mode' in runner
    assert '--mode "${MODE}"' in runner
    assert "msprof" not in runner
    assert "hbm" not in runner.lower()


def test_p6_3b_workload_preserves_completed_repeated_prefix_matched_ab():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_3b_prefix_cache_matched_ab.yaml"
    )

    assert workload["workload_id"] == (
        "p6_3b_deepseek_v4_flash_mtp_prefix_cache_matched_ab"
    )
    assert workload["task_id"] == (
        "p6_3b_deepseek_v4_flash_w8a8_mtp_prefix_cache_matched_ab_2026_0715"
    )
    assert workload["stage_contract"] == {
        "stage": "P6.3B",
        "mode": "matched_prefix_cache_on_off_unprofiled_ab",
        "claim_boundary": "matched_prefix_cache_on_off_mechanism_effect_only",
        "official_reference_baseline": True,
        "performance_reference_baseline": True,
        "profiled_evidence_baseline": True,
        "mtp_matched_ab_baseline": True,
        "profiler_authorized": False,
        "hbm_sampler_authorized": False,
        "p6_3c_execution_authorized": False,
        "p8_execution_authorized": False,
    }
    assert workload["mode_order"] == ["prefix_cache_off", "prefix_cache_on"]
    assert workload["single_variable"] == {
        "name": "enable_prefix_caching",
        "prefix_cache_off_server_delta": "omit_enable_prefix_caching_only",
        "prefix_cache_on_server_delta": "include_enable_prefix_caching_only",
        "mtp_enabled_in_both_modes": True,
        "all_other_server_arguments_identical": True,
        "same_task_local_overlay_and_environment": True,
        "same_canonical_body_bytes_across_modes": True,
    }
    assert workload["server_command_sha256"] == {
        "prefix_cache_off": "89376c9577dc70671b2b071113397c04de1ee8c1e1e802238ff4b61d753f0b98",
        "prefix_cache_on": "370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19",
    }
    assert len(workload["prefix_groups"]) == 8
    assert {
        (group["context_tokens"], group["target_shared_prefix_ratio_pct"])
        for group in workload["prefix_groups"]
    } == {
        (context, ratio)
        for context in (4096, 32768, 65536, 131072)
        for ratio in (50, 90)
    }
    assert workload["lifecycle_plan"] == {
        "server_lifecycles": 2,
        "one_fresh_lifecycle_per_mode": True,
        "hidden_warmup_requests": 0,
        "prime_requests_per_group_per_mode": 1,
        "measured_reuse_requests_per_group_per_mode": 3,
        "requests_per_mode": 32,
        "total_prime_requests": 16,
        "total_measured_requests": 48,
        "total_requests": 64,
        "retries": 0,
        "unprofiled": True,
    }
    assert workload["execution_state"] == {
        "status": "completed_server_yellow_developer_reviewed",
        "server_handoff": "historical_not_current",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
    }


def test_p6_1l_captures_bounded_request_errors_without_generated_content():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1l_mtp_decode_length_ladder.yaml"
    )
    assert workload["request_protocol"]["http_error_body_bytes_max"] == 8192
    assert workload["request_protocol"]["generated_text_retained"] is False
    assert workload["request_protocol"]["token_ids_retained"] is False
    assert workload["attempt_result_schema"]["generated_text_field_forbidden"] is True
    assert workload["attempt_result_schema"]["token_ids_field_forbidden"] is True


def test_p6_1l_uses_hash_based_overlay_and_health_idle_retry_gate():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_1l_mtp_decode_length_ladder.yaml"
    )
    assert workload["repair_artifact"] == {
        "path": (
            "benchmarks/deepseek_v4_flash/patches/"
            "vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch"
        ),
        "patch_sha256": (
            "75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1"
        ),
        "package_import_required": True,
        "proposer_module_import_required": False,
        "package_root_from_overlay": True,
        "patched_proposer_sha256": (
            "7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02"
        ),
        "unchanged_base_proposer_sha256": (
            "0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb"
        ),
        "task_local_overlay_only": True,
        "base_environment_mutation": False,
        "server_local_worktree_mutation": False,
        "changed_files": 1,
        "changed_lines": 1,
    }


def test_p6_3b_r1_records_bounded_ready_failure_without_revoking_prior_evidence():
    workload = load_yaml(
        BENCHMARK_DIR / "workloads" / "p6_3b_r1_hybrid_kv_repair.yaml"
    )

    assert workload["workload_id"] == (
        "p6_3b_r1_deepseek_v4_flash_mtp_prefix_cache_hybrid_kv_repair"
    )
    assert workload["task_id"] == (
        "p6_3b_r1_deepseek_v4_flash_w8a8_mtp_prefix_cache_"
        "hybrid_kv_repair_2026_0715"
    )
    assert workload["stage_contract"] == {
        "stage": "P6.3B-R1",
        "mode": "hybrid_kv_mtp_prefix_cache_compatibility_repair_validation",
        "claim_boundary": (
            "hybrid_kv_mtp_prefix_cache_compatibility_repair_and_positive_hit_only"
        ),
        "prior_p6_3b_grade": "yellow_p6_3b_prefix_cache_matched_ab_partial",
        "prior_p6_3b_evidence_preserved": True,
        "performance_effect_claim_allowed": False,
        "profiler_authorized": False,
        "hbm_sampler_authorized": False,
        "p6_3c_execution_authorized": False,
        "p8_execution_authorized": False,
    }
    assert workload["runtime_fixed"]["vllm_commit"] == (
        "0decac0d96c42b49572498019f0a0e3600f50398"
    )
    assert workload["runtime_fixed"]["vllm_ascend_commit"] == (
        "5f6faa0cb8830f667266f3b8121cd1383606f2a1"
    )
    assert workload["runtime_fixed"]["prefix_cache_retention_interval"] == (
        "explicitly_unset"
    )
    assert workload["hybrid_kv_repair"]["base_environment_mutation"] is False
    assert workload["hybrid_kv_repair"]["task_local_runtime_patch"] is True
    assert workload["hybrid_kv_repair"]["upstream_semantics"] == [
        "vllm_pull_44082_eagle_swa_write_path",
        "vllm_ascend_pull_11107_eagle_manager_propagation",
    ]
    assert workload["lifecycle_plan"] == {
        "server_lifecycles": 1,
        "hidden_warmup_requests": 0,
        "prime_requests_per_group": 1,
        "measured_reuse_requests_per_group": 3,
        "total_prime_requests": 3,
        "total_measured_requests": 9,
        "total_requests": 12,
        "retries": 0,
        "unprofiled": True,
    }
    assert [group["context_tokens"] for group in workload["prefix_groups"]] == [
        32768,
        65536,
        131072,
    ]
    assert all(
        group["target_shared_prefix_ratio_pct"] == 90
        for group in workload["prefix_groups"]
    )
    assert workload["acceptance"]["green_requires_positive_hit_measured_count"] == 9
    assert workload["execution_result"]["task_status"] == (
        "red_p6_3b_r1_hybrid_kv_repair_no_success"
    )
    assert workload["execution_result"]["server_ready"] is False
    assert workload["execution_result"]["requests_dispatched"] == 0
    assert workload["execution_result"]["cleanup"] == "clean"
    assert workload["execution_result"]["existing_p6_references_remain_true"] is True
    assert workload["execution_state"] == {
        "status": "completed_red_no_request_success",
        "server_handoff": "historical",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
    }


def test_server_handoff_executes_only_the_authorized_p6_3b_r2_repair():
    handoff = (REPO_ROOT / "通信模块/docs/developer-to-server.md").read_text(
        encoding="utf-8"
    )

    assert "## 当前唯一服务器动作：立即执行 P6.3B-R2 deferred-install 修复验证" in handoff
    assert (
        "task_id: p6_3b_r2_deepseek_v4_flash_w8a8_mtp_prefix_cache_"
        "hybrid_kv_deferred_install_repair_2026_0715"
    ) in handoff
    assert "npu_execution_authorized: true" in handoff
    assert "next_task_authorized: true" in handoff
    assert "standing_npu_and_vllm_consumption_authorization: true" in handoff
    assert "p6_3b_r2_hybrid_kv_deferred_install_repair.yaml" in handoff
    assert "run_deepseek_p6_3b_r2_mode.sh" in handoff
    assert "P6_3B_R2_ENABLE_HYBRID_KV_PATCH=1" in handoff
    assert "unset VLLM_PREFIX_CACHE_RETENTION_INTERVAL" in handoff
    assert "32768 / 65536 / 131072" in handoff
    assert "3 prime + 9 measured = 12" in handoff
    assert "candidate_green_p6_3b_r2_hybrid_kv_repair" in handoff
    assert "git merge --ff-only origin/main" in handoff
    assert "upload-api" in handoff
    assert "不得调用 upload-api" in handoff
    assert "不得修改 base environment 或 site-packages" in handoff
    assert "不得自动进入完整 P6.3B matched A/B、P6.3C、P7 或 P8" in handoff
