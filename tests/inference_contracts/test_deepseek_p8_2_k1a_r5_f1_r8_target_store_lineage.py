from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

from tools.inference_contracts.p8_2_k1a_h2d_residency_observer import (
    _capture_target_store_lineage,
    _target_store_lineage_residency_summary,
    build_restore_group_residency_summary,
    summarize_target_store_lineage_rows,
)
from tools.inference_contracts.run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore import (
    build_post_abort_revalidation_gate,
    build_pre_pressure_admission,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "p8_2_k1a_r5_f1_r8_target_store_lineage_2026_0723"
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r8_target_store_lineage_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r8_target_store_lineage.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r8_target_store_lineage.py"
)
LIFECYCLE = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r8_target_store_lineage.sh"
)
SERVER_TASK = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r8_server_task.sh"
)


class _Block:
    def __init__(self, block_hash: object) -> None:
        self.block_hash = block_hash
        self.is_null = False


class _Mapping:
    def __init__(self, keys: set[object]) -> None:
        self.keys = keys

    def get_one_block(self, key: object) -> object | None:
        return object() if key in self.keys else None


class _Pool:
    def __init__(
        self,
        *,
        blocks: dict[int, _Block],
        cached_keys: set[object],
    ) -> None:
        self.blocks = blocks
        self.cached_block_hash_to_block = _Mapping(cached_keys)


def _lineage_scheduler() -> tuple[object, tuple[list[int], ...], set[object]]:
    fa_keys = {f"group0-{index}" for index in range(128)}
    state_key = "group1-state"
    blocks = {
        index: _Block(f"group0-{index}") for index in range(128)
    }
    blocks[128] = _Block(state_key)
    gpu_pool = _Pool(
        blocks=blocks,
        cached_keys={*fa_keys, state_key},
    )
    cpu_pool = _Pool(blocks={}, cached_keys=set())
    groups = (
        type(
            "Group",
            (),
            {"kv_cache_spec": type("Spec", (), {"block_size": 128})()},
        )(),
        type(
            "Group",
            (),
            {"kv_cache_spec": type("Spec", (), {"block_size": 16384})()},
        )(),
    )
    scheduler = type("Scheduler", (), {})()
    scheduler._gpu_block_pool = gpu_pool
    scheduler.cpu_block_pool = cpu_pool
    scheduler.cpu_kv_cache_config = type(
        "CPUConfig", (), {"kv_cache_groups": groups}
    )()
    scheduler.cp_world_size = 1
    scheduler.fa_gidx = 0
    scheduler._store_event_to_blocks = {}
    return scheduler, (list(range(128)), [128]), {*fa_keys, state_key}


def test_target_keys_are_captured_before_finish_and_followed_into_cpu() -> None:
    scheduler, block_ids, all_keys = _lineage_scheduler()

    captured = _capture_target_store_lineage(
        scheduler,
        block_ids,
        restore_match_tokens=16384,
        hash_block_size_tokens=128,
    )

    assert captured["target_store_lineage_capture_exact"] is True
    assert captured["target_fa_capture_exact"] is True
    assert captured["target_fa_key_count"] == 128
    assert captured["target_store_key_count"] == 129
    assert captured["cpu_target_block_count"] == 0
    assert captured["gpu_target_block_count"] == 128
    assert captured["restore_group_applicable_count"] == 2

    scheduler.cpu_block_pool.cached_block_hash_to_block.keys = set(all_keys)
    scheduler._gpu_block_pool.cached_block_hash_to_block.keys = set()
    scheduler._p8_2_k1a_target_store_scheduled_keys = set(all_keys)
    scheduler._p8_2_k1a_target_store_completed_keys = set(all_keys)
    moved = _target_store_lineage_residency_summary(scheduler)

    assert moved["cpu_target_block_count"] == 128
    assert moved["gpu_target_block_count"] == 0
    assert moved["target_fa_store_completed_key_count"] == 128
    assert moved["restore_groups_cpu_complete_count"] == 2
    assert moved["restore_groups_gpu_absent_count"] == 2
    assert moved["restore_group_eligibility_complete"] is True


def test_zero_key_groups_are_not_reported_as_complete() -> None:
    summary = build_restore_group_residency_summary(
        [
            {
                "group_index": 0,
                "required_block_count": 0,
                "captured_block_count": 0,
                "cpu_block_count": 0,
                "gpu_block_count": 0,
            },
            {
                "group_index": 1,
                "required_block_count": 1,
                "captured_block_count": 1,
                "cpu_block_count": 1,
                "gpu_block_count": 0,
            },
        ]
    )

    assert summary["restore_group_count"] == 2
    assert summary["restore_group_applicable_count"] == 1
    assert summary["restore_groups_cpu_complete_count"] == 1
    assert summary["restore_groups_gpu_absent_count"] == 1
    assert summary["restore_group_eligibility_complete"] is True
    assert summary["restore_group_rows"][0]["group_applicable"] is False
    assert summary["restore_group_rows"][0]["cpu_complete"] is False
    assert summary["restore_group_rows"][0]["gpu_absent"] is False


def test_lineage_summary_distinguishes_physical_window_from_logical_hit() -> None:
    common = {
        "target_store_lineage_capture_exact": True,
        "target_store_key_count": 129,
        "target_fa_key_count": 128,
        "target_fa_capture_exact": True,
        "restore_group_count": 2,
        "restore_group_applicable_count": 2,
    }
    rows = [
        {
            "event": "target_store_lineage_captured",
            "timestamp_ns": 100,
            **common,
        },
        {
            "event": "target_store_scheduled",
            "timestamp_ns": 200,
            **common,
            "target_store_scheduled_key_count": 129,
            "target_fa_store_scheduled_key_count": 128,
        },
        {
            "event": "target_store_completed",
            "timestamp_ns": 300,
            **common,
            "target_store_scheduled_key_count": 129,
            "target_store_completed_key_count": 129,
            "target_fa_store_scheduled_key_count": 128,
            "target_fa_store_completed_key_count": 128,
        },
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 400,
            **common,
            "cpu_target_block_count": 128,
            "gpu_target_block_count": 0,
            "restore_group_eligibility_complete": True,
            "logical_restore_window_exact": False,
        },
    ]

    summary = summarize_target_store_lineage_rows(
        rows, target_block_count=128
    )

    assert summary["target_store_scheduled_key_count_max"] == 129
    assert summary["target_store_completed_key_count_max"] == 129
    assert summary["target_fa_store_completed_key_count_max"] == 128
    assert summary["physical_cpu_only_window_event_count"] == 1
    assert summary["logical_and_physical_window_event_count"] == 0
    assert summary["target_lineage_attribution"] == (
        "physical_cpu_only_window_not_accepted_by_logical_coordinator"
    )


def test_r8_admission_and_restore_gate_require_the_new_evidence() -> None:
    capture = {
        "event": "target_hashes_captured",
        "target_block_count": 128,
        "request_hash_candidate_count": 128,
        "target_capture_cardinality_exact": True,
        "target_capture_exact": True,
        "target_keyspace_matchable": True,
        "target_store_lineage_capture_exact": True,
        "target_fa_key_count": 128,
        "target_store_key_count": 129,
    }
    admitted = build_pre_pressure_admission(
        [capture],
        d2h_store_complete=True,
        target_block_count=128,
        allow_inflight_keyspace_refresh=True,
        require_target_store_lineage=True,
    )
    blocked = build_pre_pressure_admission(
        [{**capture, "target_store_lineage_capture_exact": False}],
        d2h_store_complete=True,
        target_block_count=128,
        allow_inflight_keyspace_refresh=True,
        require_target_store_lineage=True,
    )

    assert admitted["pressure_allowed"] is True
    assert blocked["decision"] == (
        "target_store_lineage_unobservable_before_pressure"
    )
    assert blocked["pressure_allowed"] is False

    physical_only = {
        "event": "target_residency_snapshot",
        "timestamp_ns": 201,
        "target_block_count": 128,
        "cpu_target_block_count": 128,
        "gpu_target_block_count": 0,
        "target_capture_cardinality_exact": True,
        "target_keyspace_matchable": True,
        "target_capture_exact": True,
        "restore_group_count": 2,
        "restore_groups_captured_exact": True,
        "restore_group_eligibility_complete": True,
        "logical_restore_match_tokens": 0,
        "logical_restore_window_exact": False,
    }
    gate = build_post_abort_revalidation_gate(
        [physical_only],
        abort_requested_timestamp_ns=200,
        required_restore_block_count=128,
        require_restore_group_eligibility=True,
        require_logical_restore_window=True,
    )

    assert gate["decision"] == (
        "logical_restore_hit_incomplete_after_physical_window"
    )
    assert gate["restore_allowed"] is False
    assert gate["logical_restore_window_exact"] is False


def test_r8_contract_keeps_accepted_capacity_and_target_lineage() -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))

    assert audit["stage"] == "P8.2-K1A-R5-F1-R8"
    assert audit["task_id"] == TASK_ID
    assert audit["accepted_f1_r7_result"]["request_count"] == 3
    assert audit["accepted_f1_r7_result"]["logical_exact_probe_event_count"] == 0
    assert audit["developer_diagnosis"][
        "global_d2h_bytes_are_not_target_request_residency_evidence"
    ] is True
    decision = audit["developer_decision"]
    assert decision["cpu_blocks_per_rank"] == 128
    assert decision["pressure_context_tokens"] == 36800
    assert decision["capture_group_wrapped_target_keys_before_request_finish"] is True
    assert decision["attribute_lazy_store_schedule_to_target_keys"] is True
    assert decision["attribute_store_completion_after_all_workers_to_target_keys"] is True
    assert decision["zero_key_groups_are_not_complete"] is True
    assert decision["capacity_change_authorized"] is False

    assert workload["runtime_config"]["cpu_blocks_per_rank"] == 128
    assert workload["runtime_config"]["pressure_context_tokens"] == 36800
    capture = workload["target_store_lineage_capture"]
    assert capture["full_attention_key_count_exact"] == 128
    assert capture["zero_key_groups_classification"] == "not_applicable"
    assert capture["zero_key_groups_count_as_cpu_complete"] is False
    trigger = workload["physical_cpu_only_trigger"]
    assert trigger["full_attention_cpu_target_block_count_exact"] == 128
    assert trigger["logical_coordinator_hit_required_to_abort_pressure"] is False
    assert workload["post_abort_restore_gate"][
        "logical_restore_window_exact_required"
    ] is True
    assert workload["claim_boundary"] == (
        "accepted_capacity_single_lifecycle_target_store_lineage_"
        "physical_cpu_only_window_and_conditional_h2d_candidate_only"
    )


def test_r8_runner_and_single_server_entrypoint_are_frozen(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source_payload.json"
    source.write_text(
        json.dumps({"prompt": list(range(4096))}, separators=(",", ":")),
        encoding="utf-8",
    )
    artifact = tmp_path / "artifact"
    prepared = subprocess.run(
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
    assert prepared.returncode == 0, prepared.stderr or prepared.stdout
    manifest = json.loads(
        (artifact / "request_body_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["task_id"] == TASK_ID
    assert manifest["target_prefix_blocks"] == 128

    audited = subprocess.run(
        ["bash", str(LIFECYCLE), str(tmp_path / "unused")],
        cwd=ROOT,
        env={**os.environ, "P8_2_K1A_LIFECYCLE_AUDIT_ONLY": "1"},
        text=True,
        capture_output=True,
    )
    assert audited.returncode == 0, audited.stderr or audited.stdout
    for line in (
        f"task_id={TASK_ID}",
        "execution_mode=authorized_single_lifecycle_target_store_lineage",
        "parent_f1_r7_pressure_executed_without_trigger=true",
        "accepted_capacity_invalidated=false",
        "target_group_wrapped_keys_captured_before_finish=true",
        "target_lazy_store_schedule_completion_attributed=true",
        "zero_key_groups_counted_complete=false",
        "physical_cpu_only_trigger_required=true",
        "logical_restore_window_required_before_restore=true",
        "pressure_context_tokens=36800",
        "logical_target_block_count=128",
        "request_retry_count_exact=0",
        "capacity_or_context_change_authorized=false",
        "result_transfer_authorized=true",
        "automatic_transfer_allowed=false",
    ):
        assert line in audited.stdout

    server_audit = subprocess.run(
        ["bash", str(SERVER_TASK), str(tmp_path / "unused-server")],
        cwd=ROOT,
        env={
            **os.environ,
            "P8_2_K1A_F1_R8_SERVER_TASK_AUDIT_ONLY": "1",
        },
        text=True,
        capture_output=True,
    )
    assert server_audit.returncode == 0, (
        server_audit.stderr or server_audit.stdout
    )
    assert f"task_id={TASK_ID}" in server_audit.stdout
    assert (
        "server_task_driver=preflight_stop_run_cleanup_restore_probe_record_finalize"
        in server_audit.stdout
    )
    assert "keep_alive_card_ids=0,1,2,3,4,5,6,7" in server_audit.stdout
