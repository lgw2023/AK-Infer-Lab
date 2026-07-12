from pathlib import Path

import yaml


CONTRACT_PATH = Path(
    "benchmarks/deepseek_v4_flash/p8/p8_baseline_contract.yaml"
)


def test_pending_baseline_contract_keeps_runtime_adapter_gate_closed() -> None:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["schema_name"] == "ak_p8_baseline_contract"
    assert contract["schema_version"] == "0.1.0"
    assert contract["contract_status"] == "pending"
    assert contract["claim_ceiling"] == "runtime_prerequisites_only"
    assert contract["selected_workload"] == {
        "model_id": "deepseek-ai/DeepSeek-V4-Flash-w8a8-mtp",
        "request_success": False,
        "successful_cell": None,
        "validated": False,
    }
    assert contract["gate"]["baseline_freeze"] == (
        "waiting_w8a8_successful_request"
    )
    assert contract["gate"]["real_vllm_ascend_adapter"] == (
        "waiting_selected_workload_runtime_gate"
    )
    assert contract["adapter"]["implementation_status"] == "not_created"
    assert contract["adapter"]["mode_after_unlock"] == "observe_only"


def test_pending_baseline_contract_records_only_proven_prerequisites() -> None:
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
        "w8a8_successful_request",
    }
    for evidence_id in (
        "source_capability_probe_v0221",
        "installed_content_provenance",
        "official_plugin_activation",
        "fresh_process_worker_memory_snapshot",
        "cann_acl_parent_spawn_path",
    ):
        assert evidence[evidence_id]["status"] == "passed"
        assert evidence[evidence_id]["selected_workload_validated"] is False
    assert evidence["w8a8_successful_request"]["status"] == "pending"
    assert evidence["w8a8_successful_request"][
        "selected_workload_validated"
    ] is False


def test_pending_baseline_contract_excludes_mixed_checkpoint() -> None:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["excluded_paths"] == [
        {
            "path_id": "mixed_fp8_fp4_checkpoint",
            "reason": "ascend_910b1_soc_does_not_support_required_customize_dtype",
            "adapter_work_authorized": False,
        }
    ]
