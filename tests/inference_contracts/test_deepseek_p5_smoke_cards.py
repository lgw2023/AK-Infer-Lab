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
    assert card["scenario"] == "four_card_stack_upgrade_then_eight_card_context_smoke"
    assert card["target_runtime"]["container_or_conda"] == "host_conda"
    assert card["target_runtime"]["vllm_version"] == "0.22.1+empty"
    assert card["target_runtime"]["vllm_ascend_version"] == "0.22.1rc1"
    assert card["target_runtime"]["torch_npu_version"] == "2.10.0"
    assert card["prior_runtime_result"]["probe_grade"] == "diagnostic_red_quant_format"
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


def test_server_handoff_builds_isolated_fp8_capable_stack_then_runs_only_four_cards():
    handoff = (REPO_ROOT / "通信模块" / "docs" / "developer-to-server.md").read_text(encoding="utf-8")

    assert "p5_deepseek_v4_flash_4card_fp8_stack_upgrade_probe_v0221rc1_2026_0710" in handoff
    assert "当前任务" in handoff
    assert "vLLM-Ascend" in handoff
    assert "vLLM 0.22.1+empty / vLLM-Ascend 0.22.1rc1" in handoff
    assert "ak-infer-lab-vllm-ascend0.22.1rc1" in handoff
    assert "ak-infer-lab-vllm-ascend0.20.2rc1" in handoff
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
    assert "diagnostic_red_quant_format" in handoff
    assert "diagnostic_red_weight_load" in handoff
    assert "blocked_environment" in handoff
    assert "base_no_mtp" in handoff
    assert "mtp_on" in handoff
    assert "不添加附件" in handoff
    assert "不执行 upload-api" in handoff
    assert "runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031" not in handoff
