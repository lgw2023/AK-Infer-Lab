from __future__ import annotations

from pathlib import Path
import subprocess

import yaml

from tools.inference_contracts.p8_2_k1a_h2d_residency_observer import (
    summarize_h2d_trigger_rows,
)
from tools.inference_contracts.p8_2_k1a_simple_cpu_offload_observer import (
    classify_restore_hit_to_load_gap,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "p8_2_k1a_r5_f1_r15_restore_step_lineage_2026_0725"
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    / "p8_2_k1a_r5_f1_r15_restore_step_lineage_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    / "p8_2_k1a_r5_f1_r15_restore_step_lineage.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    / "run_deepseek_p8_2_k1a_r5_f1_r15_restore_step_lineage.py"
)
LIFECYCLE = (
    ROOT
    / "tools/inference_contracts/"
    / "run_deepseek_p8_2_k1a_r5_f1_r15_restore_step_lineage.sh"
)
SERVER_TASK = (
    ROOT
    / "tools/inference_contracts/"
    / "run_deepseek_p8_2_k1a_r5_f1_r15_server_task.sh"
)
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"


def test_audit_freezes_r14_last_decode_parent() -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    parent = audit["accepted_f1_r14_result"]
    decision = audit["developer_decision"]
    assert audit["task_id"] == TASK_ID
    assert parent["experimental_terminal"] == "restore_request_completed"
    assert parent["restore_num_external_tokens_at_alloc"] == 0
    assert parent["restore_num_new_tokens_at_alloc"] == 2
    assert parent["restore_pairing_repair_skip_reason"] == (
        "frozen_geometry_not_index_overflow"
    )
    assert parent["restore_load_scheduled"] is True
    assert parent["restore_entered_reqs_to_load"] is False
    assert parent["h2d_bytes_total"] == 1076510720
    assert decision["restore_step_lineage_required"] is True
    assert decision["physical_fa_cpu_only_gate_required"] is True


def test_classify_detects_last_decode_masking_earlier_prefill() -> None:
    rows = [
        {
            "event": "cpu_hit_matched",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_new_tokens": 16384,
            "is_async": True,
            "pending_non_null_block_count": 40,
        },
        {
            "event": "allocate_slots_observed",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_new_tokens": 0,
            "num_external_computed_tokens": 16384,
            "delay_cache_blocks": True,
            "allocate_slots_ok": True,
        },
        {
            "event": "update_state_after_alloc_observed",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_external_tokens": 16384,
            "pending_present": True,
            "pending_non_null_block_count": 40,
            "early_return_reason": "success",
            "entered_reqs_to_load": True,
            "gpu_block_ids_count": 40,
            "cpu_block_ids_count": 40,
            "pairing_repair_enabled": True,
            "pairing_repair_eligible": True,
            "pairing_repair_applied": True,
            "pairing_repair_skip_reason": "none",
            "manager_source_sha_matched": True,
            "compress_aware_geometry_status": "ok",
            "geometry_preflight_failure_class": "index_error_gpu_cpu_pairing",
            "first_pairing_overflow_group_index": 0,
            "first_overflow_needed_index": 96,
            "first_overflow_gpu_len": 32,
        },
        {
            "event": "load_scheduled",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "block_count": 40,
            "gpu_block_ids_count": 40,
            "cpu_block_ids_count": 40,
            "num_external_tokens": 16384,
            "pairing_repair_applied": True,
        },
        {
            "event": "allocate_slots_observed",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_new_tokens": 2,
            "num_external_computed_tokens": 0,
            "delay_cache_blocks": False,
            "allocate_slots_ok": True,
        },
        {
            "event": "update_state_after_alloc_observed",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_external_tokens": 0,
            "pending_present": False,
            "pending_non_null_block_count": 0,
            "early_return_reason": "num_external_zero",
            "entered_reqs_to_load": False,
            "gpu_block_ids_count": 0,
            "cpu_block_ids_count": 0,
            "pairing_repair_enabled": True,
            "pairing_repair_eligible": False,
            "pairing_repair_applied": False,
            "pairing_repair_skip_reason": "frozen_geometry_not_index_overflow",
            "manager_source_sha_matched": True,
            "compress_aware_geometry_status": "not_applicable",
            "geometry_preflight_failure_class": "none",
        },
    ]
    summary = classify_restore_hit_to_load_gap(rows)
    assert summary["schema_version"] == "p8_2_k1a_hit_to_load_gap_v4"
    assert summary["restore_allocate_slots_observed_count"] == 2
    assert summary["restore_update_observed_count"] == 2
    assert summary["restore_last_alloc_step_class"] == "decode_like"
    assert summary["restore_alloc_step_classes"] == [
        "delayed_external_prefill",
        "decode_like",
    ]
    assert summary["restore_first_delayed_external_alloc_index"] == 0
    assert summary["restore_first_delayed_external_num_external"] == 16384
    assert summary["restore_first_entered_reqs_to_load_update_index"] == 0
    assert summary["restore_any_entered_reqs_to_load"] is True
    assert summary["restore_any_pairing_repair_applied"] is True
    assert summary["restore_last_step_masks_earlier_delayed_external"] is True
    assert summary["restore_step_lineage_primary_class"] == (
        "delayed_external_then_reqs_to_load"
    )
    assert summary["restore_h2d_path_class"] == "via_reqs_to_load"
    assert summary["restore_hit_to_load_gap_class"] == "load_scheduled"
    assert summary["restore_num_external_tokens_at_alloc"] == 0
    assert summary["restore_num_new_tokens_at_alloc"] == 2
    assert summary["restore_pairing_repair_applied"] is True


def test_classify_marks_load_without_reqs_to_load_lineage() -> None:
    rows = [
        {
            "event": "cpu_hit_matched",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_new_tokens": 16384,
            "is_async": True,
        },
        {
            "event": "allocate_slots_observed",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_new_tokens": 2,
            "num_external_computed_tokens": 0,
            "delay_cache_blocks": False,
            "allocate_slots_ok": True,
        },
        {
            "event": "update_state_after_alloc_observed",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_external_tokens": 0,
            "pending_present": False,
            "early_return_reason": "num_external_zero",
            "entered_reqs_to_load": False,
            "pairing_repair_enabled": True,
            "pairing_repair_applied": False,
            "pairing_repair_skip_reason": "frozen_geometry_not_index_overflow",
            "compress_aware_geometry_status": "not_applicable",
        },
        {
            "event": "load_scheduled",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "block_count": 8,
            "gpu_block_ids_count": 8,
        },
    ]
    summary = classify_restore_hit_to_load_gap(rows)
    assert summary["restore_hit_to_load_gap_class"] == (
        "load_scheduled_without_reqs_to_load_lineage"
    )
    assert summary["restore_h2d_path_class"] == "load_event_without_reqs_to_load"
    assert summary["restore_step_lineage_primary_class"] == (
        "decode_only_no_delayed_external"
    )
    assert summary["restore_any_entered_reqs_to_load"] is False
    assert summary["restore_first_delayed_external_alloc_index"] == -1


def test_physical_fa_cpu_only_gate_accepts_runtime_unit() -> None:
    rows: list[dict] = [
        {
            "event": "target_hashes_captured",
            "target_block_count": 128,
            "capture_exact": True,
            "target_keyspace_matchable": True,
        },
        {
            "event": "target_cache_evicted",
            "tier": "gpu",
            "target_evicted_count": 40,
        },
        {
            "event": "target_residency_snapshot",
            "reason": "before_restore_match",
            "cpu_target_block_count": 32,
            "gpu_target_block_count": 0,
            "cpu_target_count_unit": "physical_full_attention_group_keys",
            "physical_target_window_exact": True,
            "restore_group_eligibility_complete": True,
            "capture_exact": True,
            "target_keyspace_matchable": True,
        },
        {
            "event": "cpu_hit_matched",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_new_tokens": 16384,
        },
        {
            "event": "load_scheduled",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "block_count": 40,
        },
    ]
    rows.extend(
        {
            "event": "transfer_completed",
            "direction": "h2d",
            "rank": str(index),
        }
        for index in range(8)
    )
    rows.append(
        {
            "event": "load_request_completed",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
        }
    )
    summary = summarize_h2d_trigger_rows(
        rows,
        target_block_count=128,
        restore_tokens=16384,
        expected_world_size=8,
        require_restore_group_eligibility=True,
    )
    assert summary["target_cpu_only_residency_observed"] is True
    assert summary["restore_group_eligibility_observed"] is True
    assert summary["h2d_restore_mechanism_candidate"] is True


def test_handoff_and_runners_point_at_r15() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")
    lifecycle = LIFECYCLE.read_text(encoding="utf-8")
    server = SERVER_TASK.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    workload = WORKLOAD.read_text(encoding="utf-8")
    assert TASK_ID in handoff
    assert "authorized_single_lifecycle_restore_step_lineage" in handoff
    assert "restore_step_lineage" in handoff
    assert "restore_h2d_path_class" in handoff
    assert "physical_fa_cpu_only_gate" in handoff
    assert TASK_ID in lifecycle
    assert "P8_2_K1A_F1_R14_ROOT" in lifecycle
    assert TASK_ID in server
    assert "P8_2_K1A_RESTORE_STEP_LINEAGE" in runner
    assert "restore_follower_with_step_lineage_attribution" in workload


def test_lifecycle_audit_only_smoke(tmp_path: Path) -> None:
    completed = subprocess.run(
        ["bash", str(LIFECYCLE), str(tmp_path / "audit")],
        cwd=ROOT,
        env={
            **dict(**{k: v for k, v in __import__("os").environ.items()}),
            "P8_2_K1A_LIFECYCLE_AUDIT_ONLY": "1",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "restore_step_lineage=1" in completed.stdout
    assert "physical_fa_cpu_only_gate=1" in completed.stdout
    assert TASK_ID in completed.stdout
