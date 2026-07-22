from __future__ import annotations

import os
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_l1_r1_lazy_h2d_lifecycle_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_l1_r1_lazy_h2d.sh"
)
READINESS = ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"
TASK_ID = "p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721"


def test_r5_l1_r1_accepts_parent_transport_and_d2h_only() -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    received = audit["received_r5_l1_package"]
    decision = audit["developer_decision"]

    assert audit["stage"] == "P8.2-K1A-R5-L1-R1"
    assert received["server_grade"] == (
        "red_p8_2_k1a_r5_l1_h2d_evidence_incomplete"
    )
    assert received["file_count"] == 15
    assert received["payload_file_count"] == 14
    assert received["payload_bytes"] == 14291
    assert received["total_bytes"] == 17868
    assert received["manifest_sha256"] == (
        "a80231f8268c239016f7b2ed1d8b2a7521e250b52728e9e123f8d344eddf1725"
    )
    assert received["successful_request_count"] == 2
    assert received["d2h_completed_worker_count"] == 8
    assert received["d2h_store_complete"] is True
    assert received["latest_cpu_target_block_count"] == 0
    assert received["latest_gpu_target_block_count"] == 64
    assert received["pressure_request_count_executed"] == 0
    assert received["restore_sent"] is False
    assert decision["parent_grade_preserved"] is True
    assert decision["parent_d2h_store_mechanism_accepted"] is True
    assert decision["parent_h2d_restore_mechanism_accepted"] is False
    assert decision["controller_timeout_overwrite_defect_confirmed"] is True
    assert decision["one_corrected_lifecycle_allowed"] is True
    assert decision["k2_authorized"] is False


def test_r5_l1_r1_contract_preserves_valid_observation_and_restore_gate() -> None:
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    controller = workload["controller_and_observer"]
    state = workload["execution_state"]

    assert workload["task_id"] == TASK_ID
    assert workload["stage_contract"]["stage"] == "P8.2-K1A-R5-L1-R1"
    assert workload["runtime_config"]["cpu_bytes_to_use_per_rank"] == 430604288
    assert workload["runtime_config"]["lazy_offload"] is True
    assert controller["observable_not_ready_is_continue_pressure"] is True
    assert controller["wait_timeout_may_overwrite_valid_gate"] is False
    assert controller["snapshot_after_connector_output"] is True
    assert controller["pressure_requires_d2h_store_complete"] is True
    assert controller["restore_requires_target_cpu_present_and_gpu_absent"] is True
    assert controller["restore_without_runtime_trigger_allowed"] is False
    assert state["formal_model_lifecycle_count_max"] == 1
    assert state["model_request_count_min"] == 4
    assert state["model_request_count_max"] == 8
    assert state["npu_execution_authorized"] is True
    assert state["result_transfer_authorized"] is True
    assert state["transfer_method_selected"] is False
    assert state["next_task_authorized"] is False
    assert state["k2_authorized"] is False
    assert state["p8_3_i1_authorized"] is False


def test_r5_l1_r1_runner_is_preserved_while_f1_is_the_current_task(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["P8_2_K1A_AUDIT_ONLY"] = "1"
    completed = subprocess.run(
        ["bash", str(RUNNER), str(tmp_path / "result")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert f"task_id={TASK_ID}" in completed.stdout
    assert "lifecycle_count=1" in completed.stdout
    assert "request_count_min=4" in completed.stdout
    assert "request_count_max=8" in completed.stdout
    assert "npu_execution_authorized=true" in completed.stdout

    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    artifacts = readiness["artifacts"]
    current_task_id = "p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722"
    assert artifacts["current_server_handoff_task"] == current_task_id
    assert artifacts["next_workload"].endswith(
        "p8_2_k1a_r5_f1_r1_request_local_pressure_conditional_lifecycle.yaml"
    )
    assert artifacts["completed_p8_2_k1a_r5_l1_r1_runner"].endswith(RUNNER.name)

    handoff = HANDOFF.read_text(encoding="utf-8")
    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert handoff.count("\ntask_id: ") == 1
    assert f"parent_task_id={TASK_ID}" in handoff
    assert f"task_id: {current_task_id}" in handoff
    for field in (
        "offline_first: true",
        "npu_execution_authorized: conditional",
        "formal_model_lifecycle_count_max: 2",
        "model_request_count_min: 3",
        "model_request_count_max: 4",
                "request_retry_count_exact: 0",
        "result_transfer_authorized: true",
        "transfer_method_selected: false",
        "next_task_authorized: false",
        "k2_authorized: false",
        "p8_3_i1_authorized: false",
    ):
        assert field in handoff
    for marker in (
        "request-local",
        "candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure",
        "CPU=64/GPU=0",
        "pressure_01",
        "pressure_request_count_exact=1",
        "candidate_manifest.server_local.json",
        "upload-api",
    ):
        assert marker in handoff
    assert "automatic_transfer_allowed: false" in handoff


def test_r5_l1_r1_controller_contract_is_bounded_operational_metadata() -> None:
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    result = workload["result_contract"]
    assert result["max_transfer_total_bytes"] == 71680
    assert result["generated_content_allowed"] is False
    assert result["token_ids_allowed"] is False
    assert result["raw_hash_values_allowed"] is False
    assert result["raw_logs_metrics_request_bodies_and_trace_remain_server_local"] is True
    assert result["result_transfer_authorized"] is True
    assert result["transfer_method_selected"] is False
    assert result["automatic_transfer_allowed"] is False
