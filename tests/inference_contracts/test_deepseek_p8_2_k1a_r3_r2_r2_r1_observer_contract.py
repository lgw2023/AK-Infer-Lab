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
    "p8_2_k1a_r3_r2_r2_r1_observer_contract_audit.yaml"
)
WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r3_r2_r2_r1_observer_contract_replay.yaml"
)
RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r3_r2_r2_r1_simple_cpu_offload.sh"
)
HANDOFF = REPO_ROOT / "通信模块/docs/developer-to-server.md"
READINESS = REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"


def test_r3_r2_r2_r1_repairs_the_observer_contract_before_one_conditional_lifecycle(
    tmp_path: Path,
) -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))

    assert audit["stage"] == "P8.2-K1A-R3-R2-R2-R1"
    assert audit["parent_r3_r2_r2"]["server_grade"] == (
        "blocked_p8_2_k1a_r3_r2_r2_deterministic_parent_failure"
    )
    assert audit["parent_r3_r2_r2"]["server_grade_preserved_as_provenance"] is True
    assert audit["developer_review"]["source_semantics_false_negative"] is True
    assert audit["developer_review"]["cause_proven_as_unique"] is False
    assert audit["developer_review"]["observer_wait_event_extra_parameter"] is True
    assert audit["developer_review"]["parent_enqueue_only_trace"] is True
    assert audit["accepted_capacity"]["cpu_bytes_to_use_per_rank"] == 430604288
    assert audit["accepted_capacity"]["cpu_bytes_to_use_total"] == 3444834304
    assert audit["decision"]["offline_refinalization_required"] is True
    assert audit["decision"]["inheritance_aware_source_gate_required"] is True
    assert audit["decision"]["observer_signature_gate_required"] is True
    assert audit["decision"]["formal_lifecycle_count_max"] == 1
    assert audit["decision"]["request_count_max"] == 6
    assert audit["decision"]["request_retry_count"] == 0

    assert workload["task_id"] == (
        "p8_2_k1a_r3_r2_r2_r1_deepseek_v4_flash_observer_contract_replay_"
        "2026_0720"
    )
    assert workload["stage_contract"]["stage"] == "P8.2-K1A-R3-R2-R2-R1"
    assert workload["offline_refinalization"]["source_evidence_unchanged_required"] is True
    assert workload["source_and_observer_gate"]["required_source_file_count"] == 5
    assert workload["source_and_observer_gate"]["inherited_poll_required"] is True
    assert workload["source_and_observer_gate"]["frozen_launch_signature_exact"] == [
        "self",
        "src_blocks",
        "dst_blocks",
        "is_store",
        "event_idx",
        "events_list",
    ]
    assert workload["source_and_observer_gate"]["observer_extra_parameters"] == []
    assert workload["conditional_lifecycle"]["allowed_failure_classes"] == [
        "request_health_loss_without_direct_exception",
        "transfer_completion_absent_without_direct_exception",
        "insufficient_parent_evidence",
    ]
    assert workload["conditional_lifecycle"]["formal_model_lifecycle_count_max"] == 1
    assert workload["conditional_lifecycle"]["model_request_count_max"] == 6
    assert workload["conditional_lifecycle"]["request_retry_count"] == 0
    assert workload["async_copy_evidence"]["copy_thread_started_all_workers"] is True
    assert workload["async_copy_evidence"]["copy_blocks_entered_returned_all_workers"] is True
    assert workload["async_copy_evidence"]["poll_saw_appended_event_all_workers"] is True
    assert workload["execution_state"]["npu_execution_authorized"] is True
    assert workload["execution_state"]["result_transfer_authorized"] is True
    assert workload["execution_state"]["next_task_authorized"] is False

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
        "authorized_offline_refinalization_inheritance_observer_contract_gate_"
        "then_one_same_capacity_lifecycle"
    )
    assert values["cpu_bytes_to_use"] == "3444834304"
    assert values["cpu_bytes_to_use_per_rank"] == "430604288"
    assert values["server_command_sha256"] == (
        "8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6"
    )
    assert values["lifecycle_count"] == "1"
    assert values["request_count"] == "6"


def test_current_handoff_is_a_multi_section_conditional_task_not_an_unconditional_rerun() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert handoff.count("\ntask_id: ") == 1
    for exact in (
        "task_id: p8_2_k1a_r3_r2_r2_r1_deepseek_v4_flash_observer_contract_replay_2026_0720",
        "execution_mode: authorized_offline_refinalization_inheritance_observer_contract_gate_then_one_same_capacity_lifecycle",
        "npu_execution_authorized: true",
        "formal_model_lifecycle_count_max: 1",
        "model_request_count_max: 6",
        "request_retry_count_exact: 0",
        "result_transfer_authorized: true",
        "transfer_method_selected: false",
        "next_task_authorized: false",
        "source_semantics_false_negative",
        "observer_wait_event_extra_parameter",
        "request_health_loss_without_direct_exception",
        "inherited_from_frozen_vllm",
        "observer_signature_compatible",
        "copy_thread_started",
        "copy_blocks_entered",
        "copy_blocks_returned",
        "transfer_poll_entered",
        "device_copy_enqueued",
        "candidate_manifest.server_local.json",
        "email / upload-api / server-local",
        "不得进入 K2",
        "不得进入 P8.3-I1",
    ):
        assert exact in handoff
    assert "if test \"${FORMAL_LIFECYCLE_ALLOWED}\" = true" in handoff
    assert "trap cleanup EXIT" in handoff
    assert "upload_file.py" not in handoff
    assert "--confirmed-method" not in handoff
    for forbidden in ("reset --hard", "git stash", "sync.sh", "git push"):
        assert forbidden not in handoff

    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    assert readiness["artifacts"]["current_server_handoff_task"] == (
        "p8_2_k1a_r3_r2_r2_r1_deepseek_v4_flash_observer_contract_replay_"
        "2026_0720"
    )
    assert readiness["artifacts"]["next_workload"].endswith(
        "p8_2_k1a_r3_r2_r2_r1_observer_contract_replay.yaml"
    )
    acceptance = readiness["acceptance"]
    assert acceptance["p8_2_k1a_r3_r2_r2_grade"] == (
        "blocked_p8_2_k1a_r3_r2_r2_deterministic_parent_failure"
    )
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_execution_authorized"] is True
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_formal_model_lifecycle_count_max"] == 1
    assert acceptance["current_task_scoped_authorization"] == (
        "P8.2-K1A-R3-R2-R2-R1_only"
    )
    assert acceptance["next_task_authorized"] is False


def test_observer_contract_audit_uses_frozen_inheritance_and_exact_signature() -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    frozen = audit["frozen_source_contract"]
    assert frozen["vllm_commit"] == "0decac0d96c42b49572498019f0a0e3600f50398"
    assert frozen["vllm_ascend_commit"] == (
        "5f6faa0cb8830f667266f3b8121cd1383606f2a1"
    )
    assert frozen["ascend_worker_inherits_upstream"] is True
    assert frozen["poll_method_origin"] == "vllm.v1.simple_kv_offload.worker"
    assert frozen["launch_copy_is_queue_enqueue_only"] is True
    assert frozen["copy_executes_in_background_loop"] is True
    assert frozen["observer_mode"] == "observe_only_rethrow_original_exceptions"
    assert frozen["runtime_behavior_patch_authorized"] is False
    assert audit["claim_boundary"] == (
        "offline_observer_contract_correction_and_conditionally_reproduced_same_"
        "capacity_store_pressure_restore_mechanism_only"
    )


def test_no_generated_content_or_token_ids_are_authorized_in_the_new_contract() -> None:
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    evidence = workload["result_contract"]
    assert evidence["generated_content_allowed"] is False
    assert evidence["token_ids_allowed"] is False
    assert evidence["max_candidate_total_bytes"] == 71680
    assert evidence["automatic_transfer_allowed"] is False
    text = "\n".join(
        (AUDIT.read_text(encoding="utf-8"), WORKLOAD.read_text(encoding="utf-8"))
    )
    for forbidden in ("UPLOAD_API_TOKEN=", "Authorization: Bearer", "smtp.send"):
        assert forbidden not in text
