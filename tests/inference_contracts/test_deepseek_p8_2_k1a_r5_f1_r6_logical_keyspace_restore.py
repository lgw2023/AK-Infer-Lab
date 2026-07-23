from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

from tools.inference_contracts.p8_2_k1a_h2d_residency_observer import (
    build_residency_gate,
    build_restore_eligibility_gate,
    probe_logical_restore_window,
    refresh_logical_restore_window,
    summarize_h2d_trigger_rows,
)
from tools.inference_contracts.run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore import (
    build_resource_recovery_summary,
    build_inflight_trigger_state,
    summarize_inflight_request_outcomes,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723"
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r6_logical_keyspace_restore_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r6_logical_keyspace_restore.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.py"
)
LIFECYCLE = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh"
)
SERVER_TASK = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh"
)
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"


@dataclass
class _Block:
    block_hash: object | None
    is_null: bool = False


class _Mapping:
    def __init__(self, keys: set[object]) -> None:
        self.keys = keys

    def get_one_block(self, key: object) -> object | None:
        return object() if key in self.keys else None


class _Pool:
    def __init__(self, keys: set[object]) -> None:
        self.cached_block_hash_to_block = _Mapping(keys)


class _Coordinator:
    def __init__(self, groups: tuple[list[_Block], ...], hit_tokens: int) -> None:
        self.groups = groups
        self.hit_tokens = hit_tokens
        self.calls: list[tuple[list[object], int]] = []

    def find_longest_cache_hit(
        self, request_hashes: list[object], max_length: int
    ) -> tuple[tuple[list[_Block], ...], int, int]:
        self.calls.append((request_hashes, max_length))
        return self.groups, self.hit_tokens, 0


def test_logical_restore_probe_uses_runtime_keyspace_not_plain_request_hashes() -> None:
    request_hashes = [f"plain-{index}" for index in range(128)]
    group0_keys = [f"group0-{index}" for index in range(32)]
    group1_keys = ["group1-0"]
    pool_keys = set(group0_keys + group1_keys)
    coordinator = _Coordinator(
        (
            [_Block(key) for key in group0_keys],
            [_Block(key) for key in group1_keys],
            [_Block(None, is_null=True)],
        ),
        hit_tokens=16384,
    )

    summary, retained_keys = probe_logical_restore_window(
        cpu_coordinator=coordinator,
        request_hashes=request_hashes,
        restore_match_tokens=16384,
        hash_block_size_tokens=128,
        cpu_pool=_Pool(pool_keys),
        gpu_pool=_Pool(set()),
    )

    assert coordinator.calls == [(request_hashes, 16384)]
    assert retained_keys == tuple(group0_keys + group1_keys)
    assert summary["configured_target_block_count"] == 128
    assert summary["request_hash_candidate_count"] == 128
    assert summary["logical_restore_match_tokens"] == 16384
    assert summary["cpu_target_block_count"] == 128
    assert summary["gpu_target_block_count"] == 0
    assert summary["target_pool_key_count"] == 33
    assert summary["cpu_target_pool_key_match_count"] == 33
    assert summary["gpu_target_pool_key_match_count"] == 0
    assert summary["target_capture_source"] == (
        "runtime_cpu_coordinator_longest_hit"
    )
    assert summary["target_capture_cardinality_exact"] is True
    assert summary["target_keyspace_matchable"] is True
    assert summary["target_capture_exact"] is True
    assert summary["cpu_target_count_unit"] == "logical_request_hash_blocks"
    assert summary["gpu_target_count_unit"] == "runtime_group_pool_keys"
    assert summary["target_pool_key_count_unit"] == "runtime_group_pool_keys"
    assert summary["logical_restore_window_exact"] is True
    assert summary["restore_group_eligibility_complete"] is True
    assert [
        row["required_block_count"] for row in summary["restore_group_rows"]
    ] == [32, 1, 0]
    assert summary["raw_hash_values_retained"] is False


def test_scheduler_refresh_retains_runtime_pool_keys_for_later_eviction_checks() -> None:
    request_hashes = [f"plain-{index}" for index in range(128)]
    exact_keys = [f"group0-{index}" for index in range(32)]
    scheduler = type("Scheduler", (), {})()
    scheduler.cpu_coordinator = _Coordinator(
        ([_Block(key) for key in exact_keys],), hit_tokens=16384
    )
    scheduler.cpu_block_pool = _Pool(set(exact_keys))
    scheduler._gpu_block_pool = _Pool(set())
    scheduler._p8_2_k1a_target_request_hashes = tuple(request_hashes)
    scheduler._p8_2_k1a_target_pool_keys = ()

    exact = refresh_logical_restore_window(
        scheduler,
        restore_match_tokens=16384,
        hash_block_size_tokens=128,
    )

    assert exact["target_capture_exact"] is True
    assert scheduler._p8_2_k1a_target_pool_keys == tuple(exact_keys)
    assert scheduler._p8_2_k1a_target_hashes == tuple(exact_keys)

    scheduler.cpu_coordinator = _Coordinator(
        ([_Block(key) for key in exact_keys[:16]],), hit_tokens=8192
    )
    scheduler.cpu_block_pool = _Pool(set(exact_keys[:-1]))
    lost = refresh_logical_restore_window(
        scheduler,
        restore_match_tokens=16384,
        hash_block_size_tokens=128,
    )

    assert lost["logical_restore_window_exact"] is False
    assert lost["cpu_target_block_count"] == 64
    assert lost["target_pool_key_count"] == 32
    assert lost["cpu_target_pool_key_match_count"] == 31
    assert scheduler._p8_2_k1a_target_pool_keys == tuple(exact_keys)
    assert scheduler._p8_2_k1a_target_hashes == tuple(exact_keys)


def test_restore_gate_rejects_cardinality_only_capture_without_pool_key_alignment() -> None:
    gate = build_restore_eligibility_gate(
        [
            {
                "event": "request_local_pressure_progress",
                "target_block_count": 128,
                "cpu_target_block_count": 128,
                "gpu_target_block_count": 0,
                "target_capture_cardinality_exact": True,
                "target_keyspace_matchable": False,
                "target_capture_exact": False,
                "restore_group_count": 2,
                "restore_groups_captured_exact": True,
                "restore_group_eligibility_complete": True,
            }
        ],
        required_restore_block_count=128,
    )

    assert gate["decision"] == "target_keyspace_unaligned"
    assert gate["restore_allowed"] is False
    assert gate["target_capture_cardinality_exact"] is True
    assert gate["target_keyspace_matchable"] is False
    assert gate["target_capture_exact"] is False


def test_legacy_gate_and_trigger_summary_reject_unaligned_logical_keyspace() -> None:
    rows = [
        {
            "event": "target_hashes_captured",
            "target_block_count": 128,
            "target_capture_exact": False,
            "target_keyspace_matchable": False,
        },
        {
            "event": "target_residency_snapshot",
            "reason": "before_restore_match",
            "target_block_count": 128,
            "cpu_target_block_count": 128,
            "gpu_target_block_count": 0,
            "target_capture_exact": False,
            "target_keyspace_matchable": False,
            "restore_group_eligibility_complete": True,
        },
    ]

    gate = build_residency_gate(rows, target_block_count=128)
    summary = summarize_h2d_trigger_rows(
        rows,
        target_block_count=128,
        restore_tokens=16384,
        expected_world_size=8,
        require_restore_group_eligibility=True,
    )

    assert gate["decision"] == "unobservable"
    assert gate["target_hashes_captured_exact"] is False
    assert gate["target_keyspace_matchable"] is False
    assert summary["target_hashes_captured_exact"] is False
    assert summary["target_cpu_only_residency_observed"] is False
    assert summary["h2d_restore_mechanism_candidate"] is False


def test_inflight_controller_waits_until_logical_keyspace_is_exact() -> None:
    row = {
        "event": "request_local_pressure_progress",
        "timestamp_ns": 120,
        "contract_role": "pressure_01",
        "scheduled_request_count": 1,
        "request_local_progress_exact": True,
        "target_block_count": 128,
        "cpu_target_block_count": 128,
        "gpu_target_block_count": 0,
        "target_capture_cardinality_exact": True,
        "target_keyspace_matchable": False,
        "target_capture_exact": False,
        "restore_group_count": 2,
        "restore_groups_captured_exact": True,
        "restore_group_eligibility_complete": True,
    }

    state = build_inflight_trigger_state(
        [row],
        pressure_start_timestamp_ns=100,
        target_block_count=128,
        require_restore_group_eligibility=True,
        stop_on_first_cpu_target_eviction=False,
    )

    assert state["decision"] == "continue_pressure"
    assert state["abort_allowed"] is False
    near_miss = state["best_restore_eligibility_near_miss"]
    assert near_miss["target_capture_cardinality_exact"] is True
    assert near_miss["target_keyspace_matchable"] is False
    assert near_miss["target_capture_exact"] is False


def test_request_outcomes_separate_http_success_from_contract_completion() -> None:
    rows = [
        {
            "k1a_role": "warmup",
            "status": "success",
            "http_status": 200,
            "saw_done": True,
        },
        {
            "k1a_role": "target_prime",
            "status": "success",
            "http_status": 200,
            "saw_done": True,
        },
        {
            "k1a_role": "pressure_01",
            "status": "success",
            "http_status": 200,
            "saw_done": True,
            "full_response_observed": True,
            "abort_requested": False,
        },
    ]

    summary = summarize_inflight_request_outcomes(rows)

    assert summary == {
        "request_count": 3,
        "http_transport_success_count": 3,
        "contract_completed_role_count": 2,
        "intentional_pressure_abort_count": 0,
        "pressure_full_response_without_trigger_count": 1,
    }


def test_resource_recovery_requires_real_marker_count_and_card_coverage() -> None:
    common = {
        "stopped_card_ids": list(range(8)),
        "restored_card_ids": list(range(8)),
        "stop_exit_code": 0,
        "restart_exit_code": 0,
        "keep_alive_marker_count": 16,
        "expected_keep_alive_marker_count": 16,
        "port_7000_listener_count": 0,
        "vllm_residual_process_count": 0,
        "healthy_card_ids": list(range(8)),
        "tracked_worktree_clean": True,
    }

    complete = build_resource_recovery_summary(
        **common,
        keep_alive_marker_card_ids=list(range(8)),
    )
    incomplete = build_resource_recovery_summary(
        **common,
        keep_alive_marker_card_ids=list(range(7)),
    )

    assert complete["keep_alive_marker_card_ids"] == list(range(8))
    assert complete["keep_alive_marker_coverage_exact"] is True
    assert complete["keep_alive_restored_exact"] is True
    assert complete["resource_recovery_exact"] is True
    assert incomplete["keep_alive_marker_coverage_exact"] is False
    assert incomplete["keep_alive_restored_exact"] is False


def test_r6_contract_accepts_r5_as_keyspace_and_recovery_false_negative() -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))

    assert audit["stage"] == "P8.2-K1A-R5-F1-R6"
    assert audit["task_id"] == TASK_ID
    accepted = audit["accepted_f1_r5_result"]
    assert accepted["server_grade"] == (
        "red_p8_2_k1a_r5_f1_r5_cleanup_or_recovery_incomplete"
    )
    assert accepted["experimental_terminal"] == (
        "pressure_completed_without_trigger"
    )
    assert accepted["configured_target_blocks"] == 128
    assert accepted["plain_request_hash_candidate_count"] == 128
    assert accepted["observed_cpu_target_blocks"] == 0
    assert accepted["group0_cpu_pool_keys"] == 64
    assert accepted["group1_cpu_pool_keys"] == 2
    diagnosis = audit["developer_diagnosis"]
    assert diagnosis["request_hashes_are_not_runtime_pool_keys"] is True
    assert diagnosis["accepted_capacity_invalidated"] is False
    assert diagnosis["keep_alive_process_name_probe_invalid"] is True
    decision = audit["developer_decision"]
    assert decision["runtime_cpu_coordinator_lookup_required"] is True
    assert decision["logical_target_block_count_required"] == 128
    assert decision["runtime_pool_key_count_may_differ"] is True
    assert decision["same_fixed_capacity_and_context_required"] is True

    assert workload["task_id"] == TASK_ID
    assert workload["runtime_config"]["cpu_blocks_per_rank"] == 128
    assert workload["runtime_config"]["pressure_context_tokens"] == 36800
    keyspace = workload["logical_restore_keyspace_gate"]
    assert keyspace["logical_restore_match_tokens_exact"] == 16384
    assert keyspace["logical_target_block_count_exact"] == 128
    assert keyspace["runtime_pool_key_count_fixed"] is False
    assert keyspace["runtime_lookup_is_observe_only"] is True
    assert workload["execution_state"]["request_retry_count_exact"] == 0
    assert workload["execution_state"]["capacity_search_authorized"] is False


def test_r6_prepare_and_audit_only_freeze_logical_restore_contract(
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

    audited = subprocess.run(
        ["bash", str(LIFECYCLE), str(tmp_path / "unused")],
        cwd=ROOT,
        env={**os.environ, "P8_2_K1A_F1_R6_AUDIT_ONLY": "1"},
        text=True,
        capture_output=True,
    )
    assert audited.returncode == 0, audited.stderr or audited.stdout
    for line in (
        f"task_id={TASK_ID}",
        "parent_f1_r5_keyspace_probe_invalid=true",
        "logical_target_block_count=128",
        "logical_restore_match_tokens=16384",
        "runtime_pool_key_count_fixed=false",
        "runtime_cpu_coordinator_lookup_required=true",
        "same_capacity_and_context=true",
        "request_retry_count_exact=0",
        "result_transfer_authorized=true",
        "automatic_transfer_allowed=false",
    ):
        assert line in audited.stdout


def test_r6_server_driver_owns_real_keep_alive_recovery_probe(tmp_path: Path) -> None:
    completed = subprocess.run(
        ["bash", str(SERVER_TASK), str(tmp_path / "unused")],
        cwd=ROOT,
        env={
            **os.environ,
            "P8_2_K1A_F1_R6_SERVER_TASK_AUDIT_ONLY": "1",
        },
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    for line in (
        f"task_id={TASK_ID}",
        "server_task_driver=preflight_stop_run_cleanup_restore_probe_record_finalize",
        "keep_alive_card_ids=0,1,2,3,4,5,6,7",
        "keep_alive_marker_format=#card_id#",
        "expected_keep_alive_marker_count=16",
        "same_card_set_restore_on_every_exit=true",
        "resource_recovery_summary_always_recorded=true",
        "finalize_after_recovery=true",
    ):
        assert line in completed.stdout

    source = SERVER_TASK.read_text(encoding="utf-8")
    assert 'grep -F "#${card}#"' in source
    assert "npu_keep_alive.py" not in source
    assert "--expected-keep-alive-marker-count 16" in source
    assert '--keep-alive-marker-card-ids "${marker_card_ids}"' in source
    assert 'trap finish EXIT INT TERM' in source
    assert source.index("\nrun_parent_and_contract_preflight\n") < source.index(
        "\nkeep_alive_stopped=false\n"
    )


def test_r6_is_frozen_as_parent_of_the_only_current_r7_entrypoint() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert handoff.count("\ntask_id: ") == 1
    assert (
        "task_id: p8_2_k1a_r5_f1_r8_target_store_lineage_2026_0723"
        in handoff
    )
    assert TASK_ID in handoff
    for marker in (
        "find_longest_cache_hit(request_hashes, 16384)",
        "完整逻辑 128-block CPU-only 窗口",
        "accepted capacity",
        "不要手工拆内部步骤",
        "run_deepseek_p8_2_k1a_r5_f1_r8_server_task.sh",
        "P8_2_K1A_F1_R7_SERVER_TASK_AUDIT_ONLY=1",
        "#0#",
        "expected_keep_alive_marker_count=16",
        "http_transport_success_count",
        "resource_recovery_summary.json",
        "npu_stop.sh 0 1 2 3 4 5 6 7",
        "npu_keep_alive.sh 0 1 2 3 4 5 6 7",
        "成功、失败、中断或提前退出",
        "result_transfer_authorized: true",
        "transfer_method_selected: false",
        "automatic_transfer_allowed: false",
        "email / upload-api / server-local",
    ):
        assert marker in handoff
