from __future__ import annotations

from pathlib import Path
import subprocess

import yaml

from tools.inference_contracts.p8_2_k1a_simple_cpu_offload_observer import (
    classify_restore_hit_to_load_gap,
    summarize_trace_rows,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "p8_2_k1a_r5_f1_r12_hit_to_load_admission_2026_0724"
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r12_hit_to_load_admission_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r12_hit_to_load_admission.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r12_hit_to_load_admission.py"
)
LIFECYCLE = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r12_hit_to_load_admission.sh"
)
SERVER_TASK = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r12_server_task.sh"
)
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"


def test_audit_freezes_r11_parent_and_admission_gap() -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    parent = audit["accepted_f1_r11_result"]
    decision = audit["developer_decision"]

    assert audit["task_id"] == TASK_ID
    assert parent["restore_cpu_hit_exact"] is True
    assert parent["restore_load_scheduled"] is False
    assert parent["h2d_worker_count"] == 0
    assert parent["restore_cpu_hit_tokens_max"] == 16384
    assert decision["hit_to_load_admission_lineage_required"] is True
    assert decision["capacity_change_authorized"] is False
    assert "allocate_slots_observed" in decision["required_observe_events"]
    assert (
        "allocate_slots_failed_after_hit" in decision["required_gap_classes"]
    )


def test_classify_allocate_slots_failed_after_hit() -> None:
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
            "allocate_slots_ok": False,
            "gpu_free_block_count_before": 12,
        },
    ]
    gap = classify_restore_hit_to_load_gap(rows)
    assert gap["restore_hit_to_load_gap_class"] == (
        "allocate_slots_failed_after_hit"
    )
    assert gap["restore_allocate_slots_none"] is True
    assert gap["restore_update_after_alloc_called"] is False
    assert gap["restore_load_scheduled"] is False


def test_classify_num_external_zero_after_hit() -> None:
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
            "num_external_tokens": 0,
            "pending_present": True,
            "pending_non_null_block_count": 40,
            "early_return_reason": "num_external_zero",
            "entered_reqs_to_load": False,
            "gpu_block_ids_count": 0,
            "cpu_block_ids_count": 0,
        },
    ]
    gap = classify_restore_hit_to_load_gap(rows)
    assert gap["restore_hit_to_load_gap_class"] == "num_external_zero"
    assert gap["restore_update_after_alloc_called"] is True
    assert gap["restore_num_external_tokens_at_update"] == 0


def test_classify_empty_transfer_after_null_filter() -> None:
    rows = [
        {
            "event": "cpu_hit_matched",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_new_tokens": 16384,
            "is_async": True,
            "pending_non_null_block_count": 0,
        },
        {
            "event": "allocate_slots_observed",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "allocate_slots_ok": True,
            "num_external_computed_tokens": 16384,
            "num_new_tokens": 0,
            "delay_cache_blocks": True,
        },
        {
            "event": "update_state_after_alloc_observed",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_external_tokens": 16384,
            "pending_present": True,
            "pending_non_null_block_count": 0,
            "early_return_reason": "empty_transfer_after_null_filter",
            "entered_reqs_to_load": False,
            "gpu_block_ids_count": 0,
            "cpu_block_ids_count": 0,
            "null_cpu_blocks_skipped": 0,
        },
    ]
    gap = classify_restore_hit_to_load_gap(rows)
    assert gap["restore_hit_to_load_gap_class"] == (
        "empty_transfer_after_null_filter"
    )


def test_summarize_trace_includes_hit_to_load_gap() -> None:
    rows = [
        {
            "event": "cpu_hit_matched",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_new_tokens": 16384,
            "is_async": True,
            "pid": 11,
        },
        {
            "event": "allocate_slots_observed",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "allocate_slots_ok": False,
            "num_external_computed_tokens": 16384,
            "num_new_tokens": 0,
            "delay_cache_blocks": True,
            "pid": 11,
        },
    ]
    summary = summarize_trace_rows(
        rows,
        expected_world_size=8,
        restore_request_suffix="restore_follower",
    )
    assert summary["restore_cpu_hit_tokens_max"] == 16384
    assert summary["restore_load_scheduled_count"] == 0
    assert summary["restore_hit_to_load_gap_class"] == (
        "allocate_slots_failed_after_hit"
    )


def test_handoff_and_runners_point_at_r12() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    assert TASK_ID in handoff
    assert "authorized_single_lifecycle_hit_to_load_admission" in handoff
    assert "restore_hit_to_load_gap_class" in handoff
    assert "allocate_slots_observed" in handoff
    assert workload["task_id"] == TASK_ID
    assert RUNNER.is_file()
    assert LIFECYCLE.is_file()
    assert SERVER_TASK.is_file()


def test_lifecycle_audit_only_emits_r12_contract() -> None:
    result = subprocess.run(
        ["bash", str(LIFECYCLE), "/tmp/ak-r12-hit-to-load-audit"],
        check=True,
        capture_output=True,
        text=True,
        env={
            **dict(**{k: v for k, v in __import__("os").environ.items()}),
            "P8_2_K1A_LIFECYCLE_AUDIT_ONLY": "1",
        },
    )
    assert f"task_id={TASK_ID}" in result.stdout
    assert "hit_to_load_admission_lineage=1" in result.stdout
    assert "allocate_slots_observation_required=true" in result.stdout
    assert "parent_f1_r11_cpu_hit_exact=true" in result.stdout
