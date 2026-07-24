from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r3_r2_r2_forensic_replay_audit.yaml"
)
WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r3_r2_r2_forensic_replay.yaml"
)
RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r3_r2_r2_simple_cpu_offload.sh"
)
HANDOFF = REPO_ROOT / "通信模块/docs/developer-to-server.md"
READINESS = REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"


def test_r3_r2_r2_contract_accepts_parent_yellow_and_gates_one_forensic_replay(
    tmp_path: Path,
) -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))

    assert audit["stage"] == "P8.2-K1A-R3-R2-R2"
    assert audit["parent_r3_r2_r1"]["developer_grade"] == (
        "yellow_p8_2_k1a_r3_r2_r1_partial"
    )
    assert audit["parent_r3_r2_r1"]["successful_request_count"] == 1
    assert audit["parent_r3_r2_r1"]["request_count"] == 2
    assert audit["parent_r3_r2_r1"]["planned_request_count"] == 6
    assert audit["parent_r3_r2_r1"]["d2h_worker_count"] == 8
    assert audit["parent_r3_r2_r1"]["d2h_completed_worker_count"] == 0
    assert audit["parent_r3_r2_r1"]["h2d_worker_count"] == 0
    assert audit["evidence_gap"]["first_failure_excerpt_contains_only_grade"] is True
    assert audit["evidence_gap"]["raw_parent_evidence_required"] is True
    assert audit["accepted_capacity"] == {
        "cpu_bytes_to_use_per_rank": 430604288,
        "cpu_bytes_to_use_total": 3444834304,
        "required_cpu_blocks": 128,
        "required_restore_tokens": 16384,
        "world_size": 8,
    }
    assert audit["decision"]["offline_parent_forensics_authorized"] is True
    assert audit["decision"]["source_semantics_audit_authorized"] is True
    assert audit["decision"]["formal_replay_conditionally_authorized"] is True
    assert audit["decision"]["formal_lifecycle_count_max"] == 1
    assert audit["decision"]["request_count_max"] == 6
    assert audit["decision"]["request_retry_count"] == 0
    assert audit["decision"]["capacity_search_authorized"] is False
    assert audit["decision"]["runtime_behavior_patch_authorized"] is False

    assert workload["task_id"] == (
        "p8_2_k1a_r3_r2_r2_deepseek_v4_flash_forensic_replay_2026_0720"
    )
    assert workload["stage_contract"]["stage"] == "P8.2-K1A-R3-R2-R2"
    assert workload["parent_forensics"]["source_evidence_unchanged_required"] is True
    assert workload["parent_forensics"]["generated_content_allowed"] is False
    assert workload["source_semantics_gate"]["required_file_count"] == 4
    assert workload["source_semantics_gate"]["frozen_installed_source_hash_gate_required"] is True
    assert workload["source_semantics_gate"]["frozen_installed_source_file_count"] == 9
    assert workload["conditional_replay"]["allowed_failure_classes"] == [
        "transfer_completion_absent_without_direct_exception",
        "insufficient_parent_evidence",
    ]
    assert workload["conditional_replay"]["stop_failure_classes"] == [
        "http_or_client_error",
        "server_process_or_health_loss",
        "offload_runtime_exception",
    ]
    assert workload["conditional_replay"]["formal_model_lifecycle_count_max"] == 1
    assert workload["conditional_replay"]["model_request_count_max"] == 6
    assert workload["conditional_replay"]["request_retry_count"] == 0
    assert workload["runtime_fixed"]["cpu_bytes_to_use_per_rank"] == 430604288
    assert workload["runtime_fixed"]["cpu_bytes_to_use"] == 3444834304
    assert workload["execution_state"]["npu_execution_authorized"] is True
    assert workload["execution_state"]["next_task_authorized"] is False
    assert workload["execution_state"]["result_transfer_authorized"] is True
    assert workload["execution_state"]["transfer_method_selected"] is False

    env = os.environ.copy()
    env["P8_2_K1A_AUDIT_ONLY"] = "1"
    completed = subprocess.run(
        ["bash", str(RUNNER), str(tmp_path / "result")],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    runner_audit = dict(
        line.split("=", 1)
        for line in completed.stdout.splitlines()
        if "=" in line
    )
    assert runner_audit["task_id"] == workload["task_id"]
    assert runner_audit["execution_mode"] == (
        "authorized_parent_forensics_source_semantics_and_conditional_same_"
        "capacity_single_lifecycle"
    )
    assert runner_audit["cpu_bytes_to_use"] == "3444834304"
    assert runner_audit["cpu_bytes_to_use_per_rank"] == "430604288"
    assert runner_audit["server_command_sha256"] == (
        "8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6"
    )
    assert runner_audit["lifecycle_count"] == "1"
    assert runner_audit["request_count"] == "6"
    assert runner_audit["next_task_authorized"] == "false"


def test_consumed_r3_r2_r2_contract_remains_preserved_but_is_not_current() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert handoff.count("\ntask_id: ") == 1
    assert "task_id: p8_2_k1a_r3_r2_r2_deepseek_v4_flash_forensic_replay_2026_0720" not in handoff
    assert "candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility" in handoff
    assert 'test ! -e "${RESULT_DIR}"' in handoff
    assert "npu_execution_authorized: true" in handoff
    assert "parent_cleanup=clean" in handoff
    assert "upload_file.py" not in handoff
    assert "--confirmed-method" not in handoff
    for forbidden in ("reset --hard", "git stash", "bash sync.sh", "git push origin"):
        assert forbidden not in handoff

    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    artifacts = readiness["artifacts"]
    acceptance = readiness["acceptance"]
    assert artifacts["current_server_handoff_task"] != workload_task_id()
    assert artifacts["next_workload"] == (
        "workloads/p8_2_k1a_r5_f1_r12_hit_to_load_admission.yaml"
    )
    assert acceptance["p8_2_k1a_r3_r2_r1_grade"] == (
        "yellow_p8_2_k1a_r3_r2_r1_partial"
    )
    assert acceptance["p8_2_k1a_r3_r2_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_formal_model_lifecycle_count_max"] == 1
    assert acceptance["p8_2_k1a_r3_r2_r2_model_request_count_max"] == 6
    assert acceptance["current_task_scoped_authorization"] == (
        "P8.2-K1A-R5-F1-R12_single_lifecycle_hit_to_load_admission"
    )
    assert acceptance["next_task_authorized"] is False


def workload_task_id() -> str:
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    return str(workload["task_id"])
