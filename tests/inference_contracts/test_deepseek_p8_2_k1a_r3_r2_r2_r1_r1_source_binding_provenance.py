from __future__ import annotations

import os
from pathlib import Path
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r3_r2_r2_r1_r1_source_binding_provenance_audit.yaml"
)
WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r3_r2_r2_r1_r1_source_binding_provenance_replay.yaml"
)
RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r3_r2_r2_r1_r1_simple_cpu_offload.sh"
)
HANDOFF = REPO_ROOT / "通信模块/docs/developer-to-server.md"
READINESS = REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"


def test_r1_r1_requires_exact_source_binding_and_exception_provenance_before_replay(
    tmp_path: Path,
) -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))

    assert audit["stage"] == "P8.2-K1A-R3-R2-R2-R1-R1"
    assert audit["parent_r3_r2_r2_r1"]["server_grade"] == (
        "blocked_p8_2_k1a_r3_r2_r2_r1_source_or_observer_gate"
    )
    assert audit["developer_review"]["source_semantics_false_negative"] is True
    assert audit["developer_review"]["parent_exception_provenance_incomplete"] is True
    assert audit["frozen_source_contract"]["required_source_file_count"] == 6
    assert audit["frozen_source_contract"]["copy_blocks_binding_kind"] == (
        "import_from"
    )
    assert audit["decision"]["runtime_copy_primitive_identity_required"] is True
    assert audit["decision"]["runtime_exception_provenance_required"] is True
    assert audit["decision"]["formal_lifecycle_count_max"] == 1
    assert audit["decision"]["request_count_max"] == 6
    assert audit["decision"]["request_retry_count"] == 0

    assert workload["task_id"] == (
        "p8_2_k1a_r3_r2_r2_r1_r1_deepseek_v4_flash_source_binding_"
        "provenance_replay_2026_0720"
    )
    gate = workload["source_binding_and_exception_gate"]
    assert gate["required_source_file_count"] == 6
    assert gate["copy_blocks_import_module"] == (
        "vllm_ascend.simple_kv_offload.npu_mem_ops"
    )
    assert gate["runtime_identity_expression"] == (
        "copy_backend.copy_blocks is npu_mem_ops.copy_blocks"
    )
    assert gate["allowed_runtime_log_gates"] == [
        "pass_no_direct_runtime_exception",
        "pass_known_retired_observer_defect",
    ]
    assert gate["unknown_runtime_exception_count_required"] == 0
    conditional = workload["conditional_lifecycle"]
    assert conditional["formal_model_lifecycle_count_max"] == 1
    assert conditional["model_request_count_max"] == 6
    assert conditional["request_retry_count"] == 0
    assert conditional["first_failure_stop"] is True

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
    values = dict(
        line.split("=", 1)
        for line in completed.stdout.splitlines()
        if "=" in line
    )
    assert values["task_id"] == workload["task_id"]
    assert values["execution_mode"] == (
        "authorized_offline_source_binding_exception_provenance_gate_then_one_"
        "same_capacity_lifecycle"
    )
    assert values["cpu_bytes_to_use"] == "3444834304"
    assert values["cpu_bytes_to_use_per_rank"] == "430604288"
    assert values["server_command_sha256"] == (
        "8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6"
    )
    assert values["lifecycle_count"] == "1"
    assert values["request_count"] == "6"


def test_source_binding_task_is_consumed_and_r5_f0_is_current() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert handoff.count("\ntask_id: ") == 1
    for exact in (
        "task_id: p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_2026_0722",
        "execution_mode: authorized_single_lifecycle_full_restore_eligibility_alignment",
        "npu_execution_authorized: true",
        "formal_model_lifecycle_count_exact: 1",
        "model_request_count_exact: 4",
        "result_transfer_authorized: true",
        "transfer_method_selected: false",
        "next_task_authorized: false",
        "offline_parent_gate_required: true",
        "full_request_window_watch_required: true",
        "parent_d2h_store_complete=true",
        "parent_h2d_worker_count=0",
        "candidate_manifest.server_local.json",
        "email / upload-api / server-local",
        "不得进入 K2",
        "不得进入 P8.3-I1",
    ):
        assert exact in handoff
    assert "trap cleanup EXIT" not in handoff
    assert "upload_file.py" not in handoff
    assert "--confirmed-method" not in handoff
    for forbidden in ("reset --hard", "git stash", "bash sync.sh", "git push origin"):
        assert forbidden not in handoff

    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    artifacts = readiness["artifacts"]
    assert artifacts["current_server_handoff_task"] == (
        "p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_2026_0722"
    )
    assert artifacts["next_workload"].endswith(
        "p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.yaml"
    )
    acceptance = readiness["acceptance"]
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_grade"] == (
        "blocked_p8_2_k1a_r3_r2_r2_r1_source_or_observer_gate"
    )
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_r1_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_r1_r1_developer_refinalized_grade"] == (
        "yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_store_only_no_restore"
    )
    assert acceptance["p8_2_k1a_r4_offline_closeout_authorized"] is True
    assert acceptance[
        "p8_2_k1a_r3_r2_r2_r1_r1_formal_model_lifecycle_count_max"
    ] == 1
    assert acceptance["current_task_scoped_authorization"] == (
        "P8.2-K1A-R5-F1-R4_single_lifecycle_full_restore_eligibility_alignment"
    )
    assert acceptance["next_task_authorized"] is False
