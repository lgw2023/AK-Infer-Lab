from __future__ import annotations

import os
from pathlib import Path
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_replay_audit.yaml"
)
WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_replay.yaml"
)
RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r3_r2_r2_r1_r1_r1_simple_cpu_offload.sh"
)
HANDOFF = REPO_ROOT / "通信模块/docs/developer-to-server.md"
READINESS = REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"


def test_causal_exception_contract_preserves_parent_and_allows_only_one_conditional_replay(
    tmp_path: Path,
) -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))

    assert audit["stage"] == "P8.2-K1A-R3-R2-R2-R1-R1-R1"
    parent = audit["parent_r3_r2_r2_r1_r1"]
    assert parent["server_grade"] == (
        "blocked_p8_2_k1a_r3_r2_r2_r1_r1_offline_provenance_gate"
    )
    assert parent["server_grade_preserved_as_provenance"] is True
    assert parent["bounded_evidence_file_count"] == 15
    assert parent["bounded_evidence_total_bytes"] == 62093
    assert parent["bounded_evidence_set_sha256"] == (
        "9df4b6fc0bee05a05644284a58ff9f29d2af5f1789aeae267251f14ba59d8fa0"
    )
    causal = audit["causal_exception_contract"]
    assert causal["schema_version"] == (
        "p8_2_k1a_runtime_exception_causal_provenance_v2"
    )
    assert causal["expected_exception_count"] == 35
    assert causal["expected_root_known_observer_defect_count"] == 32
    assert causal["expected_derived_worker_runtime_wrapper_count"] == 1
    assert causal["expected_derived_engine_dead_wrapper_count"] == 2
    assert causal["independent_unknown_exception_count_required"] == 0
    assert causal["required_vllm_source_template_file_count"] == 3
    assert causal["compact_exact_grouping_required"] is True
    assert causal["allowed_runtime_log_gate"] == (
        "pass_known_retired_observer_defect_with_deterministic_wrappers"
    )

    assert workload["task_id"] == (
        "p8_2_k1a_r3_r2_r2_r1_r1_r1_deepseek_v4_flash_causal_"
        "exception_replay_2026_0720"
    )
    offline = workload["offline_causal_refinalization"]
    assert offline["parent_bounded_file_count"] == 15
    assert offline["source_log_unchanged_required"] is True
    assert offline["exception_record_count_exact_required"] is True
    assert offline["frozen_wrapper_source_template_gate_required"] is True
    conditional = workload["conditional_lifecycle"]
    assert conditional["formal_model_lifecycle_count_max"] == 1
    assert conditional["model_request_count_max"] == 6
    assert conditional["request_retry_count"] == 0
    assert conditional["first_failure_stop"] is True
    assert conditional["capacity_search_authorized"] is False
    assert workload["execution_state"]["k2_authorized"] is False
    assert workload["execution_state"]["p8_3_i1_authorized"] is False
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
    values = dict(
        line.split("=", 1)
        for line in completed.stdout.splitlines()
        if "=" in line
    )
    assert values["task_id"] == workload["task_id"]
    assert values["execution_mode"] == (
        "authorized_offline_causal_exception_refinalization_then_one_"
        "same_capacity_lifecycle"
    )
    assert values["cpu_bytes_to_use_per_rank"] == "430604288"
    assert values["cpu_bytes_to_use"] == "3444834304"
    assert values["lifecycle_count"] == "1"
    assert values["request_count"] == "6"


def test_causal_lifecycle_is_consumed_and_r5_f0_feasibility_is_current() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert handoff.count("\ntask_id: ") == 1
    for exact in (
        "task_id: p8_2_k1a_r5_f1_r8_target_store_lineage_2026_0723",
        "execution_mode: authorized_single_lifecycle_target_store_lineage",
        "npu_execution_authorized: true",
        "formal_model_lifecycle_count_exact: 1",
        "model_request_count_max: 4",
        "result_transfer_authorized: true",
        "transfer_method_selected: false",
        "next_task_authorized: false",
        "offline_parent_gate_required: true",
        "full_request_window_watch_required: true",
        "parent_successful_request_count=3",
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
        "p8_2_k1a_r5_f1_r8_target_store_lineage_2026_0723"
    )
    assert artifacts["next_workload"].endswith(
        "p8_2_k1a_r5_f1_r8_target_store_lineage.yaml"
    )
    acceptance = readiness["acceptance"]
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_r1_grade"] == (
        "blocked_p8_2_k1a_r3_r2_r2_r1_r1_offline_provenance_gate"
    )
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_r1_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_r1_r1_grade"] == (
        "red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete"
    )
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_r1_r1_developer_refinalized_grade"] == (
        "yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_store_only_no_restore"
    )
    assert acceptance["p8_2_k1a_r4_offline_closeout_authorized"] is True
    assert acceptance[
        "p8_2_k1a_r3_r2_r2_r1_r1_r1_formal_model_lifecycle_count_max"
    ] == 1
    assert acceptance["current_task_scoped_authorization"] == (
        "P8.2-K1A-R5-F1-R8_single_lifecycle_target_store_lineage"
    )
    assert acceptance["next_task_authorized"] is False
