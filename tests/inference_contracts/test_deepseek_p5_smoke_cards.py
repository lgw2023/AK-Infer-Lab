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
    assert card["runtime"]["vllm_ascend_version"] == "0.18.0"
    assert card["parallelism"]["tp"] == 8
    assert card["parallelism"]["ep"] == "enabled"
    assert card["workload"]["context_ladder_tokens"] == [4096, 32768, 65536, 98304, 131072]
    assert card["workload"]["output_tokens"] == 64

    paths = {item["model_object_id"]: item["server_model_path"] for item in card["model_objects"]}
    assert paths["deepseek_v4_flash_w8a8_mtp_modelscope"] == "/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp"
    assert paths["deepseek_v4_flash_official_hf"] == "/data/node0_disk1/Public/DeepSeek-V4-Flash"


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
    assert workload["runtime_reference"]["speculative_mtp"]["method"] == "mtp"
    assert workload["request_plan"]["context_ladder_tokens"] == [4096, 32768, 65536, 98304, 131072]
    assert workload["request_plan"]["output_len_tokens"] == 64
    assert workload["degrade_policy"]["max_num_seqs_order"] == [16, 4, 1]
    assert workload["degrade_policy"]["disable_mtp_after_max_num_seqs_exhausted"] is True


def test_server_handoff_waits_for_runtime_upgrade_feedback_without_reissuing_p5():
    handoff = (REPO_ROOT / "通信模块" / "docs" / "developer-to-server.md").read_text(encoding="utf-8")

    assert "p5_deepseek_v4_flash_8card_128k_smoke_2026_0710" in handoff
    assert "no_new_server_task_waiting_vllm_0202_upgrade_feedback_2026_0710" in handoff
    assert "当前无新增服务器任务" in handoff
    assert "vLLM-Ascend" in handoff
    assert "0.20.2rc1" in handoff
    assert "不要重跑" in handoff
    assert "--tensor-parallel-size 8" not in handoff
    assert "runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031" not in handoff
