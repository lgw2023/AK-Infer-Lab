from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

from tools.inference_contracts.p8_2_k1a_h2d_residency_observer import (
    build_restore_group_residency_summary,
    build_restore_eligibility_gate,
    derive_restore_eligibility_contract,
)
from tools.inference_contracts.run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment import (
    build_restore_eligible_inflight_trigger_state,
)


ROOT = Path(__file__).resolve().parents[2]
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py"
)
LIFECYCLE = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh"
)
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.yaml"
)
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"
TASK_ID = "p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_2026_0722"


def _progress(
    *,
    target_blocks: int,
    cpu_blocks: int,
    gpu_blocks: int,
    groups_complete: bool,
) -> dict[str, object]:
    return {
        "event": "request_local_pressure_progress",
        "timestamp_ns": 120,
        "contract_role": "pressure_01",
        "scheduled_request_count": 1,
        "request_local_progress_exact": True,
        "num_computed_tokens_before_schedule": 32768,
        "num_scheduled_tokens": 4032,
        "num_computed_tokens_after_schedule": 36800,
        "target_block_count": target_blocks,
        "cpu_target_block_count": cpu_blocks,
        "gpu_target_block_count": gpu_blocks,
        "restore_group_count": 2,
        "restore_groups_captured_exact": True,
        "restore_groups_cpu_complete_count": 2 if groups_complete else 1,
        "restore_groups_gpu_absent_count": 2,
        "restore_group_eligibility_complete": groups_complete,
    }


def test_restore_eligibility_contract_derives_full_16k_window() -> None:
    contract = derive_restore_eligibility_contract(
        restore_match_tokens=16384,
        block_size_tokens=128,
    )

    assert contract == {
        "restore_match_tokens_required": 16384,
        "block_size_tokens": 128,
        "required_restore_block_count": 128,
    }


def test_restore_gate_rejects_legacy_64_block_subset() -> None:
    gate = build_restore_eligibility_gate(
        [_progress(target_blocks=64, cpu_blocks=64, gpu_blocks=0, groups_complete=True)],
        required_restore_block_count=128,
    )

    assert gate["decision"] == "insufficient_restore_coverage"
    assert gate["restore_allowed"] is False
    assert gate["observed_target_block_count"] == 64
    assert gate["required_restore_block_count"] == 128


def test_restore_gate_requires_all_group_eligibility() -> None:
    gate = build_restore_eligibility_gate(
        [_progress(target_blocks=128, cpu_blocks=128, gpu_blocks=0, groups_complete=False)],
        required_restore_block_count=128,
    )

    assert gate["decision"] == "restore_groups_incomplete"
    assert gate["restore_allowed"] is False


def test_restore_gate_accepts_full_128_block_cross_group_window() -> None:
    gate = build_restore_eligibility_gate(
        [_progress(target_blocks=128, cpu_blocks=128, gpu_blocks=0, groups_complete=True)],
        required_restore_block_count=128,
    )

    assert gate["decision"] == "trigger_ready"
    assert gate["restore_allowed"] is True
    assert gate["restore_group_eligibility_complete"] is True


def test_inflight_abort_rejects_64_blocks_and_waits_for_all_groups() -> None:
    legacy = build_restore_eligible_inflight_trigger_state(
        [_progress(target_blocks=64, cpu_blocks=64, gpu_blocks=0, groups_complete=True)],
        pressure_start_timestamp_ns=100,
    )
    group_incomplete = build_restore_eligible_inflight_trigger_state(
        [_progress(target_blocks=128, cpu_blocks=128, gpu_blocks=0, groups_complete=False)],
        pressure_start_timestamp_ns=100,
    )
    eligible = build_restore_eligible_inflight_trigger_state(
        [_progress(target_blocks=128, cpu_blocks=128, gpu_blocks=0, groups_complete=True)],
        pressure_start_timestamp_ns=100,
    )

    assert legacy["decision"] == "continue_pressure"
    assert legacy["abort_allowed"] is False
    assert group_incomplete["decision"] == "continue_pressure"
    assert group_incomplete["abort_allowed"] is False
    assert eligible["decision"] == "trigger_ready"
    assert eligible["abort_allowed"] is True
    assert eligible["trigger"]["target_block_count"] == 128
    assert eligible["trigger"]["restore_group_eligibility_complete"] is True


def test_inflight_watch_does_not_stop_on_an_early_cpu_eviction() -> None:
    state = build_restore_eligible_inflight_trigger_state(
        [
            {
                "event": "target_cache_evicted",
                "timestamp_ns": 110,
                "tier": "cpu",
                "target_evicted_count": 1,
            },
            _progress(
                target_blocks=128,
                cpu_blocks=127,
                gpu_blocks=0,
                groups_complete=False,
            )
            | {"timestamp_ns": 120},
        ],
        pressure_start_timestamp_ns=100,
    )

    assert state["decision"] == "continue_pressure"
    assert state["abort_allowed"] is False
    assert state["cpu_target_eviction_event_count"] == 1
    assert state["best_restore_eligibility_near_miss"][
        "cpu_target_block_count"
    ] == 127
    assert "restore_group_rows" not in state["best_restore_eligibility_near_miss"]


def test_post_abort_gate_accepts_a_full_window_after_an_early_eviction() -> None:
    full = _progress(
        target_blocks=128,
        cpu_blocks=128,
        gpu_blocks=0,
        groups_complete=True,
    ) | {"event": "target_residency_snapshot", "timestamp_ns": 120}
    gate = build_restore_eligibility_gate(
        [
            {
                "event": "target_cache_evicted",
                "timestamp_ns": 110,
                "tier": "cpu",
                "target_evicted_count": 1,
            },
            full,
        ],
        required_restore_block_count=128,
    )

    assert gate["decision"] == "trigger_ready"
    assert gate["restore_allowed"] is True
    assert gate["cpu_target_eviction_observed"] is True
    assert gate["cpu_target_eviction_after_full_window_observed"] is False


def test_group_summary_preserves_bounded_near_miss_diagnostics() -> None:
    summary = build_restore_group_residency_summary(
        [
            {
                "group_index": 0,
                "required_block_count": 128,
                "captured_block_count": 128,
                "cpu_block_count": 128,
                "gpu_block_count": 0,
            },
            {
                "group_index": 1,
                "required_block_count": 1,
                "captured_block_count": 1,
                "cpu_block_count": 0,
                "gpu_block_count": 0,
            },
        ]
    )

    assert summary["restore_group_count"] == 2
    assert summary["restore_groups_captured_exact"] is True
    assert summary["restore_groups_cpu_complete_count"] == 1
    assert summary["restore_groups_gpu_absent_count"] == 2
    assert summary["restore_group_eligibility_complete"] is False
    assert summary["restore_group_rows"] == [
        {
            "group_index": 0,
            "required_block_count": 128,
            "captured_block_count": 128,
            "cpu_block_count": 128,
            "gpu_block_count": 0,
            "cpu_complete": True,
            "gpu_absent": True,
        },
        {
            "group_index": 1,
            "required_block_count": 1,
            "captured_block_count": 1,
            "cpu_block_count": 0,
            "gpu_block_count": 0,
            "cpu_complete": False,
            "gpu_absent": True,
        },
    ]


def test_f1_r4_prepare_freezes_128_block_restore_eligibility(tmp_path: Path) -> None:
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
    assert manifest["target_prefix_tokens"] == 16384
    assert manifest["target_prefix_blocks"] == 128
    assert manifest["restore_match_tokens_required"] == 16384
    assert manifest["restore_group_eligibility_required"] is True
    assert manifest["legacy_64_block_subset_authorizes_restore"] is False


def test_f1_r4_contract_and_audit_only_keep_capacity_fixed(tmp_path: Path) -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))

    assert audit["stage"] == "P8.2-K1A-R5-F1-R4"
    assert audit["accepted_f1_r3_result"]["server_grade"] == (
        "red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete"
    )
    assert audit["developer_decision"]["required_restore_block_count"] == 128
    assert audit["developer_decision"]["accepted_cpu_blocks_per_rank"] == 128
    assert audit["developer_decision"]["capacity_change_authorized"] is False
    assert audit["developer_decision"]["full_request_window_watch_required"] is True
    assert workload["task_id"] == TASK_ID
    assert workload["runtime_config"]["cpu_blocks_per_rank"] == 128
    assert workload["request_plan"]["pressure_context_tokens"] == 36800
    assert workload["restore_eligibility_gate"]["required_restore_block_count"] == 128
    assert workload["restore_eligibility_gate"]["legacy_64_block_subset_allowed"] is False
    assert workload["restore_eligibility_gate"]["all_kv_groups_required"] is True

    completed = subprocess.run(
        ["bash", str(LIFECYCLE), str(tmp_path / "unused")],
        cwd=ROOT,
        env={**os.environ, "P8_2_K1A_F1_R4_AUDIT_ONLY": "1"},
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    for line in (
        f"task_id={TASK_ID}",
        "accepted_cpu_blocks_per_rank=128",
        "required_restore_block_count=128",
        "restore_match_tokens_required=16384",
        "legacy_64_block_subset_authorizes_restore=false",
        "all_kv_groups_required=true",
        "pressure_context_tokens=36800",
        "capacity_change_authorized=false",
        "full_request_window_watch_required=true",
        "formal_model_lifecycle_count_exact=1",
        "model_request_count_exact=4",
        "request_retry_count_exact=0",
        "result_transfer_authorized=true",
        "transfer_method_selected=false",
        "next_task_authorized=false",
    ):
        assert line in completed.stdout


def test_f1_r4_is_the_only_current_server_handoff() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")
    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert handoff.count("\ntask_id: ") == 1
    assert f"task_id: {TASK_ID}" in handoff
    for marker in (
        "CPU=128/GPU=0",
        "16384",
        "全部相关 KV group",
        "完整 pressure 生命周期窗口",
        "不得因第一次未形成窗口就提前判定容量不兼容",
        "npu_stop.sh 0 1 2 3 4 5 6 7",
        "npu_keep_alive.sh 0 1 2 3 4 5 6 7",
        "成功、失败、中断或提前退出",
        "result_transfer_authorized: true",
        "transfer_method_selected: false",
        "automatic_transfer_allowed: false",
        "email",
        "upload-api",
        "server-local",
    ):
        assert marker in handoff
