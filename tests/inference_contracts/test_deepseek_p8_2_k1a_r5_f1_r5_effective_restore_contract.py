from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import yaml
import pytest

from tools.inference_contracts.p8_2_k1a_h2d_residency_observer import (
    validate_effective_restore_contract,
)
from tools.inference_contracts.run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore import (
    build_inflight_trigger_state,
    classify_inflight_grades,
)


ROOT = Path(__file__).resolve().parents[2]
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r5_effective_restore_contract_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r5_effective_restore_contract.yaml"
)
TASK_ID = "p8_2_k1a_r5_f1_r5_effective_restore_contract_2026_0722"
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.py"
)
LIFECYCLE = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.sh"
)
SERVER_TASK = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r5_server_task.sh"
)
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"


def test_f1_r5_contract_accepts_r4_as_invalid_runtime_configuration_evidence() -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))

    assert audit["stage"] == "P8.2-K1A-R5-F1-R5"
    assert audit["task_id"] == TASK_ID
    assert audit["accepted_f1_r4_result"]["server_grade"] == (
        "red_p8_2_k1a_r5_f1_r4_cleanup_or_recovery_incomplete"
    )
    assert audit["accepted_f1_r4_result"]["experimental_terminal"] == (
        "pressure_completed_without_trigger"
    )
    assert audit["accepted_f1_r4_result"]["configured_target_blocks"] == 128
    assert audit["accepted_f1_r4_result"]["effective_runtime_target_blocks"] == 64
    assert audit["developer_decision"]["accepted_capacity_invalidated"] is False
    assert audit["developer_decision"]["rerun_same_fixed_lifecycle"] is True
    assert workload["task_id"] == TASK_ID
    assert workload["runtime_config"]["cpu_blocks_per_rank"] == 128
    assert workload["runtime_config"]["effective_target_block_count"] == 128
    assert workload["runtime_config"]["restore_match_tokens"] == 16384
    assert workload["runtime_config"]["pressure_context_tokens"] == 36800
    assert workload["execution_state"]["request_retry_count_exact"] == 0
    assert workload["execution_state"]["capacity_search_authorized"] is False


def test_f1_r5_prepare_freezes_the_effective_128_block_contract(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source_payload.json"
    source.write_text(
        json.dumps({"prompt": list(range(4096))}, separators=(",", ":")),
        encoding="utf-8",
    )
    artifact = tmp_path / "artifact"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "prepare",
            "--source-payload",
            str(source),
            "--artifact-dir",
            str(artifact),
            "--model-name",
            "deepseek-v4-flash-w8a8-mtp",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    manifest = json.loads(
        (artifact / "request_body_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["task_id"] == TASK_ID
    assert manifest["target_prefix_blocks"] == 128
    assert manifest["target_prefix_tokens"] == 16384
    assert manifest["restore_group_eligibility_required"] is True
    assert manifest["legacy_64_block_subset_authorizes_restore"] is False


def test_f1_r5_audit_only_is_explicit_and_requires_no_parent_or_npu(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        ["bash", str(LIFECYCLE), str(tmp_path / "unused")],
        cwd=ROOT,
        env={**os.environ, "P8_2_K1A_F1_R5_AUDIT_ONLY": "1"},
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    for line in (
        f"task_id={TASK_ID}",
        "parent_f1_r4_runtime_contract_invalid=true",
        "effective_target_block_count=128",
        "restore_match_tokens=16384",
        "block_size_tokens=128",
        "restore_target_geometry_exact=true",
        "target_capture_source_and_count_required=true",
        "group_capture_geometry_required=true",
        "same_card_set_recovery_driver_required=true",
        "structured_resource_recovery_artifact_required=true",
        "pressure_context_tokens=36800",
        "request_retry_count_exact=0",
        "capacity_search_authorized=false",
        "result_transfer_authorized=true",
        "automatic_transfer_allowed=false",
        "next_task_authorized=false",
    ):
        assert line in completed.stdout


def test_server_task_driver_audits_effective_contract_and_owns_recovery(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        ["bash", str(SERVER_TASK), str(tmp_path / "unused")],
        cwd=ROOT,
        env={**os.environ, "P8_2_K1A_F1_R5_SERVER_TASK_AUDIT_ONLY": "1"},
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    for line in (
        f"task_id={TASK_ID}",
        "server_task_driver=stop_run_cleanup_restore_record_finalize",
        "keep_alive_card_ids=0,1,2,3,4,5,6,7",
        "same_card_set_restore_on_every_exit=true",
        "request_count_min=3",
        "request_count_max=4",
        "cpu_bytes_to_use=3444834304",
        "cpu_bytes_to_use_per_rank=430604288",
        "lazy_offload=true",
        "observer_mode=observe_only_with_controller_role_marker_no_runtime_decision_or_copy_mutation",
        "h2d_target_block_count=128",
        "restore_match_tokens=16384",
        "restore_target_geometry_exact=true",
        "server_command_sha256=89a9a105da5a04a3207c638b6999858ed32bff0f438c2cfb617b03905d1efe2f",
        "resource_recovery_summary_always_recorded=true",
        "finalize_after_recovery=true",
    ):
        assert line in completed.stdout

    source = SERVER_TASK.read_text(encoding="utf-8")
    assert "npu_stop.sh\" \"${CARD_IDS[@]}\"" in source
    assert "npu_keep_alive.sh\" \"${CARD_IDS[@]}\"" in source
    assert (
        "keep_alive_stopped=true\nset +e\n"
        'bash "/data/node0_disk1/Public/npu_stop.sh" "${CARD_IDS[@]}"'
    ) in source
    assert 'trap finish EXIT INT TERM' in source
    assert source.index("\nrun_parent_and_effective_preflight\n") < source.index(
        "\nkeep_alive_stopped=false\n"
    )
    assert 'P8_2_K1A_MODE_AUDIT_ONLY=1 bash "${LIFECYCLE}" "${RESULT_DIR}"' in source
    assert 'if test ! -d "${RESULT_DIR}"; then\n    mkdir -p "${RESULT_DIR}"\n  fi' in source
    assert '"${REQUEST_RUNNER}" record-recovery' in source
    assert '"${REQUEST_RUNNER}" finalize' in source


def test_observer_rejects_an_effective_target_count_that_does_not_match_restore_geometry() -> None:
    with pytest.raises(ValueError, match="effective target block count"):
        validate_effective_restore_contract(
            target_block_count=64,
            restore_match_tokens=16384,
            block_size_tokens=128,
            require_restore_group_eligibility=True,
        )

    assert validate_effective_restore_contract(
        target_block_count=128,
        restore_match_tokens=16384,
        block_size_tokens=128,
        require_restore_group_eligibility=True,
    )["effective_restore_contract_exact"] is True


def test_grade_keeps_experimental_terminal_visible_when_recovery_is_incomplete() -> None:
    grades = classify_inflight_grades(
        grade_prefix="red_p8_2_k1a_r5_f1_r5",
        candidate_green="candidate_green",
        terminal="pressure_completed_without_trigger",
        cleanup="clean",
        recovery_ok=False,
        evidence_exact=False,
    )

    assert grades == {
        "experimental_grade": (
            "red_p8_2_k1a_r5_f1_r5_pressure_completed_without_trigger"
        ),
        "operational_grade": (
            "red_p8_2_k1a_r5_f1_r5_cleanup_or_recovery_incomplete"
        ),
        "server_grade": (
            "red_p8_2_k1a_r5_f1_r5_cleanup_or_recovery_incomplete"
        ),
    }


def test_best_near_miss_keeps_bounded_group_geometry_without_hashes() -> None:
    state = build_inflight_trigger_state(
        [
            {
                "event": "request_local_pressure_progress",
                "timestamp_ns": 120,
                "contract_role": "pressure_01",
                "scheduled_request_count": 1,
                "request_local_progress_exact": True,
                "target_block_count": 128,
                "cpu_target_block_count": 127,
                "gpu_target_block_count": 0,
                "configured_target_block_count": 128,
                "request_hash_candidate_count": 128,
                "fa_group_hash_candidate_count": 64,
                "selected_target_hash_count": 128,
                "target_capture_source": "request_block_hashes",
                "target_capture_exact": True,
                "restore_group_count": 1,
                "restore_groups_captured_exact": True,
                "restore_groups_cpu_complete_count": 0,
                "restore_groups_gpu_absent_count": 1,
                "restore_group_eligibility_complete": False,
                "restore_group_rows": [
                    {
                        "group_index": 0,
                        "theoretical_block_count": 128,
                        "selected_block_id_count": 65,
                        "non_null_block_count": 65,
                        "hashable_block_count": 64,
                        "unhashable_non_null_block_count": 1,
                        "required_block_count": 64,
                        "captured_block_count": 64,
                        "cpu_block_count": 63,
                        "gpu_block_count": 0,
                        "raw_hash_values_retained": False,
                    }
                ],
            }
        ],
        pressure_start_timestamp_ns=100,
        target_block_count=128,
        require_restore_group_eligibility=True,
        stop_on_first_cpu_target_eviction=False,
    )

    near_miss = state["best_restore_eligibility_near_miss"]
    assert near_miss["configured_target_block_count"] == 128
    assert near_miss["request_hash_candidate_count"] == 128
    assert near_miss["fa_group_hash_candidate_count"] == 64
    assert near_miss["target_capture_source"] == "request_block_hashes"
    assert near_miss["target_capture_exact"] is True
    assert near_miss["restore_group_rows"][0]["hashable_block_count"] == 64
    assert near_miss["restore_group_rows"][0]["cpu_block_count"] == 63
    assert near_miss["raw_hash_values_retained"] is False


def test_f1_r5_is_preserved_in_the_current_r7_handoff_lineage() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")
    current_task = "p8_2_k1a_r5_f1_r8_target_store_lineage_2026_0723"

    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert handoff.count("\ntask_id: ") == 1
    assert f"task_id: {current_task}" in handoff
    assert f"parent_f1_r5_task={TASK_ID}" in handoff
    for marker in (
        "F1-R6 的实验 RED、运维 GREEN",
        "不要手工拆内部步骤",
        "run_deepseek_p8_2_k1a_r5_f1_r8_server_task.sh",
        "P8_2_K1A_F1_R7_SERVER_TASK_AUDIT_ONLY=1",
        "logical_target_block_count=128",
        "pressure_progress_runtime_keyspace_refresh_required=true",
        "request_hash_candidate_count",
        "logical_restore_match_tokens",
        "target_pool_key_count",
        "resource_recovery_summary.json",
        "experimental_grade",
        "operational_grade",
        "npu_stop.sh 0 1 2 3 4 5 6 7",
        "npu_keep_alive.sh 0 1 2 3 4 5 6 7",
        "成功、失败、中断或提前退出",
        "result_transfer_authorized: true",
        "transfer_method_selected: false",
        "automatic_transfer_allowed: false",
        "email / upload-api / server-local",
    ):
        assert marker in handoff
