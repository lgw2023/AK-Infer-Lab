from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = REPO_ROOT / "benchmarks" / "deepseek_v4_flash"


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict)
    return data


def test_p5_readiness_card_targets_official_fp8_runtime_gate():
    card = load_yaml(BENCHMARK_DIR / "p5_readiness_card.yaml")

    assert card["experiment_id"] == "p5_deepseek_v4_flash_official_fp8_runtime_gate"
    assert card["scenario"] == "four_card_plugin_activation_then_eight_card_context_smoke"
    assert card["target_runtime"]["container_or_conda"] == "host_conda"
    assert card["target_runtime"]["vllm_version"] == "0.22.1+empty"
    assert card["target_runtime"]["vllm_ascend_version"] == "0.22.1rc1"
    assert card["target_runtime"]["torch_npu_version"] == "2.10.0"
    assert card["prior_runtime_result"]["probe_grade"] == "diagnostic_red_quant_format"
    assert card["latest_environment_result"]["reported_probe_grade"] == "blocked_environment"
    assert card["latest_environment_result"]["environment_functionally_built"] is True
    assert card["latest_environment_result"]["runtime_attempted"] is False
    assert "upstream_nvidia_model_route" in card["target_runtime"]["runtime_status"]
    assert card["latest_runtime_result"]["probe_grade"] == "diagnostic_yellow_allocator_bypass"
    assert card["latest_runtime_result"]["first_failure_stage"] == "deepseek_v4_model_construction_platform_route"
    assert card["authorized_runtime_gate"]["workload"] == "workloads/p5_4card_fp8_plugin_activation_probe.yaml"
    assert card["authorized_runtime_gate"]["task_id"] == "p5_deepseek_v4_flash_4card_fp8_plugin_activation_probe_v0221rc1_2026_0711"
    assert card["authorized_runtime_gate"]["visible_devices"] == "4,5,6,7"
    assert card["authorized_runtime_gate"]["tp"] == 4
    assert card["authorized_runtime_gate"]["model_object_id"] == "deepseek_v4_flash_official_hf"
    assert card["authorized_runtime_gate"]["quantization_argument"] == "omitted_use_checkpoint_config"
    assert card["authorized_runtime_gate"]["developer_to_server_ready"] is True
    assert card["future_eight_card_smoke"]["visible_devices"] == "0,1,2,3,4,5,6,7"
    assert card["future_eight_card_smoke"]["resource_gate"] == "waiting_separate_user_authorization_after_four_card_success"
    assert card["future_eight_card_smoke"]["context_ladder_tokens"] == [4096, 32768, 65536, 98304, 131072]
    assert card["future_eight_card_smoke"]["output_tokens"] == 64

    paths = {item["model_object_id"]: item["server_model_path"] for item in card["model_objects"]}
    assert paths["deepseek_v4_flash_w8a8_mtp_modelscope"] == "/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp"
    assert paths["deepseek_v4_flash_official_hf"] == "/data/node0_disk1/Public/DeepSeek-V4-Flash"


def test_model_registry_retires_w8a8_and_promotes_official_mixed_checkpoint():
    registry = load_yaml(BENCHMARK_DIR / "deepseek_v4_flash_model_objects.yaml")
    objects = {item["model_object_id"]: item for item in registry["model_objects"]}

    w8a8 = objects["deepseek_v4_flash_w8a8_mtp_modelscope"]
    assert w8a8["server_inventory"]["shard_count"] == 70
    assert w8a8["server_inventory"]["weight_bytes"] == 300013759966
    assert w8a8["server_inventory"]["weight_gib"] == 279.41
    assert w8a8["model_role"] == "retired_by_project_decision"
    assert w8a8["expected_scenarios"] == []

    smaller = objects["deepseek_v4_flash_official_hf"]
    assert smaller["server_inventory"]["shard_count"] == 46
    assert smaller["server_inventory"]["weight_bytes"] == 159617149040
    assert smaller["server_inventory"]["weight_gib"] == 148.66
    assert smaller["model_role"] == "project_primary_runtime_object"
    assert smaller["intended_runtime"]["runtime"] == "vllm_0_22_1_plus_vllm_ascend_0_22_1rc1"
    assert smaller["intended_runtime"]["reference_role"] == "project_primary_p5_runtime_and_future_p6_baseline_candidate"
    assert "ascend_plugin_activation_pending" in smaller["server_inventory"]["inventory_status"]
    assert "p5_4card_fp8_runtime_resume_probe" in smaller["expected_scenarios"]
    assert "p5_4card_fp8_allocator_patch_delivery_probe" in smaller["expected_scenarios"]
    assert "p5_4card_fp8_plugin_activation_probe" in smaller["expected_scenarios"]

    assert "The W8A8-MTP object is retired from future project execution and remains inventory-only." in registry["global_boundaries"]


def test_p5_context_ladder_workload_preserves_official_startup_flags_and_degrade_order():
    workload = load_yaml(BENCHMARK_DIR / "workloads" / "p5_8card_context_ladder.yaml")

    assert workload["workload_id"] == "p5_8card_context_ladder_smoke"
    assert workload["model_object_id"] == "deepseek_v4_flash_official_hf"
    assert workload["server_model_path"] == "/data/node0_disk1/Public/DeepSeek-V4-Flash"
    assert workload["runtime_reference"]["max_model_len"] == 135168
    assert workload["runtime_reference"]["tensor_parallel_size"] == 8
    assert workload["runtime_reference"]["enable_expert_parallel"] is True
    assert workload["runtime_reference"]["quantization"] == "auto_from_checkpoint_config"
    assert workload["runtime_reference"]["explicit_quantization_argument"] == "forbidden"
    assert workload["runtime_reference"]["enable_prefix_caching"] is True
    assert workload["runtime_reference"]["enable_chunked_prefill"] is True
    assert workload["runtime_reference"]["additional_config"]["enable_flashcomm1"] is True
    assert workload["runtime_reference"]["additional_config"]["enable_dsa_cp"] is True
    assert workload["runtime_reference"]["speculative_mtp"]["method"] == "mtp"
    assert workload["resource_gate"]["required_visible_devices"] == "0,1,2,3,4,5,6,7"
    assert workload["runtime_environment"]["vllm_ascend"] == "0.22.1rc1"
    assert workload["request_plan"]["context_ladder_tokens"] == [4096, 32768, 65536, 98304, 131072]
    assert workload["request_plan"]["output_len_tokens"] == 64
    assert workload["degrade_policy"]["max_num_seqs_order"] == [16, 4, 1]
    assert workload["degrade_policy"]["disable_mtp_after_max_num_seqs_exhausted"] is True


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


def test_server_handoff_probes_plugin_activation_then_runs_overlay_free_base():
    handoff = (REPO_ROOT / "通信模块" / "docs" / "developer-to-server.md").read_text(encoding="utf-8")

    assert "p5_deepseek_v4_flash_4card_fp8_plugin_activation_probe_v0221rc1_2026_0711" in handoff
    assert "当前任务" in handoff
    assert "vLLM-Ascend" in handoff
    assert "ak-infer-lab-vllm-ascend0.22.1rc1" in handoff
    assert "0decac0d96c42b49572498019f0a0e3600f50398" in handoff
    assert "5f6faa0cb8830f667266f3b8121cd1383606f2a1" in handoff
    assert "ASCEND_RT_VISIBLE_DEVICES=4,5,6,7" in handoff
    assert "server_local/git_pull_remote_wins.sh" in handoff
    assert "git merge --ff-only origin/main" in handoff
    assert "禁止 `cherry-pick`" in handoff
    assert "blocked_resource" in handoff
    assert "--tensor-parallel-size 4" in handoff
    assert "--max-model-len 8192" in handoff
    assert "--max-num-seqs 1" in handoff
    assert "/data/node0_disk1/Public/DeepSeek-V4-Flash" in handoff
    assert "RETIRED_W8A8_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp" in handoff
    assert '"enable_flashcomm1":true' in handoff
    assert '"enable_dsa_cp":true' in handoff
    assert '"enable_mlapo":false' not in handoff
    assert "VLLM_ASCEND_APPLY_DSV4_PATCH=1" not in handoff
    assert "VLLM_ASCEND_ENABLE_MLAPO=0" not in handoff
    assert "    --cpu-offload-gb" not in handoff
    assert "    --quantization" not in handoff
    assert "    --tensor-parallel-size 8" not in handoff
    assert "131072" not in handoff
    assert "no_new_server_task_waiting_8card_scope_for_p5_retry_2026_0710" not in handoff
    assert "base_failed_stop_no_fallback" in handoff
    assert "blocked_preflight" in handoff
    assert "禁止 `conda create`、`pip install`" in handoff
    assert '"${PYTHON_BIN}" -m pip install' not in handoff
    assert "base_no_mtp" in handoff
    assert "sitecustomize.py" in handoff
    assert "torch.accelerator.memory_stats" in handoff
    assert "torch.npu.memory_stats" in handoff
    assert "ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model" in handoff
    assert "vllm_ascend.models.deepseek_v4:AscendDeepseekV4ForCausalLM" in handoff
    assert "vllm.models.deepseek_v4" in handoff
    assert "fresh_plugin_probe.py" in handoff
    assert "plugin_matrix_summary.json" in handoff
    assert "installed_content_provenance.json" in handoff
    assert "blocked_provenance" in handoff
    assert "vllm_ascend/models/deepseek_v4.py" in handoff
    assert "9398e49d7206ba5a62629409405be057318e0657e40a25cf15c43304f78d01a4" in handoff
    assert "4be66190ceaee9d0465f62ade801a8e94a907d7ab9fdb0a67fa14ce87448ae9f" in handoff
    assert "stdout/stderr 只进入 `.log`" in handoff
    assert "unset PYTHONPATH" in handoff
    assert "diagnostic_red_plugin_filter_hypothesis_mismatch" in handoff
    assert "diagnostic_red_ascend_model_registration" in handoff
    assert "diagnostic_red_global_patch" in handoff
    assert "diagnostic_yellow_plugin_route_fixed" in handoff
    assert "diagnostic_green_base_runtime" in handoff
    assert "不得自动添加附件或执行 upload-api" in handoff
    assert "email" in handoff
    assert "upload-api" in handoff
    assert "server-local" in handoff
    assert "SHA-256" in handoff
    assert "不添加附件" not in handoff
    assert "不执行 upload-api" not in handoff
    assert "runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031" not in handoff
