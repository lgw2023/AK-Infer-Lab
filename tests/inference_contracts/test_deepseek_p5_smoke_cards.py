from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = REPO_ROOT / "benchmarks" / "deepseek_v4_flash"


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict)
    return data


def test_p5_readiness_card_targets_eight_card_128k_smoke():
    card = load_yaml(BENCHMARK_DIR / "p5_readiness_card.yaml")

    assert card["experiment_id"] == "p5_deepseek_v4_flash_8card_128k_smoke"
    assert card["scenario"] == "eight_card_vllm_startup_and_context_ladder_smoke"
    assert card["runtime"]["container_or_conda"] == "host_conda"
    assert card["runtime"]["vllm_version"] == "0.20.2+empty"
    assert card["runtime"]["vllm_ascend_version"] == "0.20.2rc1"
    assert card["runtime"]["torch_npu_version"] == "2.10.0"
    assert card["parallelism"]["tp"] == 8
    assert card["parallelism"]["ep"] == "enabled"
    assert card["parallelism"]["required_visible_devices"] == "0,1,2,3,4,5,6,7"
    assert card["parallelism"]["resource_gate"] == "waiting_user_confirmed_eight_card_scope"
    assert card["authorized_diagnostic_probe"]["visible_devices"] == "4,5,6,7"
    assert card["authorized_diagnostic_probe"]["tp"] == 4
    assert card["authorized_diagnostic_probe"]["model_object_id"] == "deepseek_v4_flash_official_hf"
    assert card["authorized_diagnostic_probe"]["quantization_argument"] == "omitted_use_checkpoint_config"
    assert card["authorized_diagnostic_probe"]["developer_to_server_ready"] is True
    assert card["authorized_diagnostic_probe"]["canonical_eight_card_gate_unchanged"] is True
    assert card["workload"]["context_ladder_tokens"] == [4096, 32768, 65536, 98304, 131072]
    assert card["workload"]["output_tokens"] == 64

    paths = {item["model_object_id"]: item["server_model_path"] for item in card["model_objects"]}
    assert paths["deepseek_v4_flash_w8a8_mtp_modelscope"] == "/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp"
    assert paths["deepseek_v4_flash_official_hf"] == "/data/node0_disk1/Public/DeepSeek-V4-Flash"


def test_model_registry_records_server_inventory_without_promoting_four_card_probe_to_canonical_p5():
    registry = load_yaml(BENCHMARK_DIR / "deepseek_v4_flash_model_objects.yaml")
    objects = {item["model_object_id"]: item for item in registry["model_objects"]}

    w8a8 = objects["deepseek_v4_flash_w8a8_mtp_modelscope"]
    assert w8a8["server_inventory"]["shard_count"] == 70
    assert w8a8["server_inventory"]["weight_bytes"] == 300013759966
    assert w8a8["server_inventory"]["weight_gib"] == 279.41

    smaller = objects["deepseek_v4_flash_official_hf"]
    assert smaller["server_inventory"]["shard_count"] == 46
    assert smaller["server_inventory"]["weight_bytes"] == 159617149040
    assert smaller["server_inventory"]["weight_gib"] == 148.66
    assert smaller["intended_runtime"]["reference_role"] == "authorized_four_card_format_compatibility_probe"

    assert "Canonical eight-card P5 still uses the W8A8-MTP object." in registry["global_boundaries"]


def test_p5_context_ladder_workload_preserves_official_startup_flags_and_degrade_order():
    workload = load_yaml(BENCHMARK_DIR / "workloads" / "p5_8card_context_ladder.yaml")

    assert workload["workload_id"] == "p5_8card_context_ladder_smoke"
    assert workload["model_object_id"] == "deepseek_v4_flash_w8a8_mtp_modelscope"
    assert workload["runtime_reference"]["max_model_len"] == 135168
    assert workload["runtime_reference"]["tensor_parallel_size"] == 8
    assert workload["runtime_reference"]["enable_expert_parallel"] is True
    assert workload["runtime_reference"]["quantization"] == "ascend"
    assert workload["runtime_reference"]["enable_prefix_caching"] is True
    assert workload["runtime_reference"]["enable_chunked_prefill"] is True
    assert workload["runtime_reference"]["additional_config"]["enable_flashcomm1"] is True
    assert workload["runtime_reference"]["additional_config"]["enable_dsa_cp"] is True
    assert workload["runtime_reference"]["speculative_mtp"]["method"] == "mtp"
    assert workload["resource_gate"]["required_visible_devices"] == "0,1,2,3,4,5,6,7"
    assert workload["runtime_environment"]["vllm_ascend"] == "0.20.2rc1"
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


def test_server_handoff_authorizes_only_bounded_four_card_startup_probe():
    handoff = (REPO_ROOT / "通信模块" / "docs" / "developer-to-server.md").read_text(encoding="utf-8")

    assert "p5_deepseek_v4_flash_4card_small_checkpoint_probe_v0202_2026_0710" in handoff
    assert "当前任务" in handoff
    assert "vLLM-Ascend" in handoff
    assert "0.20.2rc1" in handoff
    assert "ASCEND_RT_VISIBLE_DEVICES=4,5,6,7" in handoff
    assert "server_local/git_pull_remote_wins.sh" in handoff
    assert "git merge --ff-only origin/main" in handoff
    assert "禁止 `cherry-pick`" in handoff
    assert "blocked_resource" in handoff
    assert "--tensor-parallel-size 4" in handoff
    assert "--max-model-len 8192" in handoff
    assert "--max-num-seqs 1" in handoff
    assert "/data/node0_disk1/Public/DeepSeek-V4-Flash" in handoff
    assert "EXCLUDED_W8A8_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp" in handoff
    assert '"enable_flashcomm1":true' in handoff
    assert '"enable_dsa_cp":true' in handoff
    assert '"enable_mlapo":false' in handoff
    assert "VLLM_ASCEND_APPLY_DSV4_PATCH=1" in handoff
    assert "VLLM_ASCEND_ENABLE_MLAPO=0" not in handoff
    assert "    --cpu-offload-gb" not in handoff
    assert "    --quantization" not in handoff
    assert "--tensor-parallel-size 8" not in handoff
    assert "131072" not in handoff
    assert "no_new_server_task_waiting_8card_scope_for_p5_retry_2026_0710" not in handoff
    assert "quantization_format_failure_stop_no_retry" in handoff
    assert "diagnostic_red_quant_format" in handoff
    assert "不添加附件" in handoff
    assert "不执行 upload-api" in handoff
    assert "runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031" not in handoff
