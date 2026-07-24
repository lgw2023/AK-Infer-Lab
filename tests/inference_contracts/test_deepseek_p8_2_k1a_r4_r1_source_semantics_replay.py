from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/p8_2_k1a_r4_r1_source_semantics_replay_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r4_r1_store_only_source_semantics_replay.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/run_deepseek_p8_2_k1a_r4_r1_offline_closeout.sh"
)
READINESS = ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"
RECEIVED = Path(
    "/Volumes/SSD1/Inbox/2026-07-21/p8_2_k1a_r4_store_only_20260720_run01"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_r4_r1_audit_matches_received_r4_package_and_preserves_claim_boundary() -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    expected_files = audit["received_r4_package"]["files"]
    actual_files = sorted(path.name for path in RECEIVED.iterdir() if path.is_file())

    assert actual_files == sorted(expected_files)
    assert sum((RECEIVED / name).stat().st_size for name in actual_files) == 27943
    assert {
        name: _sha256(RECEIVED / name) for name in actual_files
    } == expected_files
    assert audit["r4_review"]["server_grade_preserved"] == (
        "blocked_p8_2_k1a_r4_offline_closeout_gate"
    )
    assert audit["r4_review"]["trace_attribution_gate"] == "pass"
    assert audit["r4_review"]["store_only_refinalization_accepted"] is True
    assert audit["r4_review"]["source_semantics_false_negative"] == (
        "popleft_n_not_recognized_by_popleft_only_matcher"
    )
    assert audit["decision"]["actual_cpu_eviction_proven"] is False
    assert audit["decision"]["h2d_restore_mechanism_accepted"] is False
    assert audit["decision"]["performance_reference_accepted"] is False
    assert audit["decision"]["next_task_authorized"] is False


def test_r4_r1_contract_is_preserved_while_r5_f0_is_current() -> None:
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    historical_task_id = (
        "p8_2_k1a_r4_r1_store_only_source_semantics_replay_2026_0721"
    )
    current_task_id = "p8_2_k1a_r5_f1_r12_hit_to_load_admission_2026_0724"

    assert workload["task_id"] == historical_task_id
    assert workload["source_gate"]["parent_r4_grade"] == (
        "blocked_p8_2_k1a_r4_offline_closeout_gate"
    )
    assert workload["source_gate"]["frozen_block_pool_dequeue_method"] == (
        "popleft_n"
    )
    assert workload["acceptance"]["candidate_green_grade"] == (
        "candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout"
    )
    assert workload["execution_state"]["npu_execution_authorized"] is False
    assert workload["execution_state"]["keep_alive_stop_authorized"] is False
    assert workload["execution_state"]["vllm_server_start_authorized"] is False
    assert workload["execution_state"]["model_requests_authorized"] is False
    assert workload["execution_state"]["result_transfer_authorized"] is True
    assert workload["execution_state"]["transfer_method_selected"] is False
    assert workload["execution_state"]["next_task_authorized"] is False
    assert workload["result_contract"]["payload_file_count_exact"] == 9
    assert workload["result_contract"]["transfer_file_count_including_manifest"] == 10

    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    artifacts = readiness["artifacts"]
    assert artifacts["next_workload"].endswith(
        "p8_2_k1a_r5_f1_r12_hit_to_load_admission.yaml"
    )
    assert artifacts["current_server_handoff_task"] == current_task_id
    assert artifacts["current_p8_2_k1a_r4_r1_runner"].endswith(RUNNER.name)

    handoff = HANDOFF.read_text(encoding="utf-8")
    assert handoff.count("当前唯一服务器动作") == 1
    assert f"task_id: {current_task_id}" in handoff
    assert "npu_execution_authorized: true" in handoff
    assert "keep_alive_stop_authorized: true" in handoff
    assert "vllm_server_start_authorized: true" in handoff
    assert "model_requests_authorized: true" in handoff
    assert "result_transfer_authorized: true" in handoff
    assert "transfer_method_selected: false" in handoff
    assert "next_task_authorized: false" in handoff
    assert "candidate_manifest.server_local.json" in handoff
    assert "kill -TERM" not in handoff
    assert "vllm serve" not in handoff
    assert "curl " not in handoff
    subprocess.run(["bash", "-n", str(RUNNER)], check=True)

    audit_only = subprocess.run(
        ["bash", str(RUNNER)],
        check=True,
        text=True,
        capture_output=True,
        env={"P8_2_K1A_R4_R1_AUDIT_ONLY": "1"},
    ).stdout
    assert f"task_id={historical_task_id}" in audit_only
    assert "expected_dequeue_method=popleft_n" in audit_only
    assert "npu_execution_authorized=false" in audit_only
    assert "model_requests_authorized=false" in audit_only
    assert "result_transfer_authorized=true" in audit_only
    assert "next_task_authorized=false" in audit_only
