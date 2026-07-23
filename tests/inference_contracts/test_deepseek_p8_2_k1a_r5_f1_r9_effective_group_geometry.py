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
    build_restore_eligibility_gate,
    capture_restore_group_hashes,
    derive_runtime_group_geometry,
    summarize_target_store_lineage_rows,
)
from tools.inference_contracts.run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore import (
    build_inflight_trigger_state,
    build_pre_pressure_admission,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "p8_2_k1a_r5_f1_r9_effective_group_geometry_2026_0723"
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r9_effective_group_geometry_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r9_effective_group_geometry.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r9_effective_group_geometry.py"
)
LIFECYCLE = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r9_effective_group_geometry.sh"
)
SERVER_TASK = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r9_server_task.sh"
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


class _Coordinator:
    @staticmethod
    def _get_effective_block_size(spec: object) -> int:
        return int(spec.block_size) * max(
            1, int(getattr(spec, "compress_ratio", 1) or 1)
        )


def _compressed_lineage_scheduler() -> tuple[
    object, tuple[list[int], ...], set[object]
]:
    fa_keys = {f"group0-{index}" for index in range(32)}
    state_key = "group1-state"
    blocks = {
        index: _Block(
            f"group0-{index}" if index < 64 else None
        )
        for index in range(65)
    }
    blocks[65] = _Block(state_key)
    blocks[66] = _Block("group1-tail")
    gpu_pool = _Pool(
        blocks=blocks,
        cached_keys={*fa_keys, state_key},
    )
    cpu_pool = _Pool(blocks={}, cached_keys=set())
    groups = (
        type(
            "Group",
            (),
            {
                "kv_cache_spec": type(
                    "FullAttentionSpec",
                    (),
                    {"block_size": 128, "compress_ratio": 4},
                )()
            },
        )(),
        type(
            "Group",
            (),
            {
                "kv_cache_spec": type(
                    "CompressedStateSpec",
                    (),
                    {"block_size": 128, "compress_ratio": 128},
                )()
            },
        )(),
    )
    scheduler = type("Scheduler", (), {})()
    scheduler._gpu_block_pool = gpu_pool
    scheduler.cpu_block_pool = cpu_pool
    scheduler.cpu_kv_cache_config = type(
        "CPUConfig", (), {"kv_cache_groups": groups}
    )()
    scheduler.cpu_coordinator = _Coordinator()
    scheduler.cp_world_size = 1
    scheduler.fa_gidx = 0
    scheduler._store_event_to_blocks = {}
    return scheduler, (list(range(65)), [65, 66]), {*fa_keys, state_key}


def test_runtime_geometry_maps_logical_128_blocks_to_physical_keys() -> None:
    scheduler, _, _ = _compressed_lineage_scheduler()
    groups = scheduler.cpu_kv_cache_config.kv_cache_groups

    fa = derive_runtime_group_geometry(
        scheduler,
        group_index=0,
        group=groups[0],
        restore_match_tokens=16384,
    )
    state = derive_runtime_group_geometry(
        scheduler,
        group_index=1,
        group=groups[1],
        restore_match_tokens=16384,
    )

    assert fa["effective_block_size_tokens"] == 512
    assert fa["physical_key_count_required"] == 32
    assert fa["effective_geometry_source"] == "runtime_cpu_coordinator"
    assert state["effective_block_size_tokens"] == 16384
    assert state["physical_key_count_required"] == 1


def test_unhashable_supplied_group_cannot_be_reclassified_as_not_applicable() -> None:
    pool = _Pool(blocks={0: _Block(None)}, cached_keys=set())
    hashes, geometry = capture_restore_group_hashes(
        block_lookup=pool.blocks,
        group_block_ids=[0],
        group_index=1,
        restore_match_tokens=16384,
        effective_block_size_tokens=16384,
    )

    assert hashes == ()
    assert geometry["group_applicable"] is True
    assert geometry["required_block_count"] == 1
    assert geometry["hash_capture_exact"] is False
    assert geometry["logical_coverage_exact"] is False


def test_capture_and_pressure_use_logical_coverage_not_physical_128() -> None:
    scheduler, block_ids, all_keys = _compressed_lineage_scheduler()
    captured = _capture_target_store_lineage(
        scheduler,
        block_ids,
        restore_match_tokens=16384,
        hash_block_size_tokens=128,
    )

    assert captured["target_store_lineage_capture_exact"] is True
    assert captured["target_logical_block_count"] == 128
    assert captured["target_logical_coverage_exact"] is True
    assert captured["target_fa_required_physical_key_count"] == 32
    assert captured["target_fa_key_count"] == 32
    assert captured["target_store_key_count"] == 33
    assert captured["cpu_target_block_count"] == 0
    assert captured["gpu_target_block_count"] == 32

    admitted = build_pre_pressure_admission(
        [
            {
                "event": "target_hashes_captured",
                "target_block_count": 128,
                "request_hash_candidate_count": 128,
                "target_capture_cardinality_exact": True,
                "target_capture_exact": True,
                "target_keyspace_matchable": True,
                **captured,
            }
        ],
        d2h_store_complete=True,
        target_block_count=128,
        allow_inflight_keyspace_refresh=True,
        require_target_store_lineage=True,
        require_effective_group_geometry=True,
    )
    assert admitted["pressure_allowed"] is True

    scheduler.cpu_block_pool.cached_block_hash_to_block.keys = set(all_keys)
    scheduler._gpu_block_pool.cached_block_hash_to_block.keys = set()
    scheduler._p8_2_k1a_target_store_scheduled_keys = set(all_keys)
    scheduler._p8_2_k1a_target_store_completed_keys = set(all_keys)
    moved = _target_store_lineage_residency_summary(scheduler)
    assert moved["cpu_target_block_count"] == 32
    assert moved["gpu_target_block_count"] == 0
    assert moved["physical_target_window_exact"] is True


def test_effective_geometry_window_triggers_and_revalidates() -> None:
    row = {
        "event": "request_local_pressure_progress",
        "contract_role": "pressure_01",
        "timestamp_ns": 200,
        "scheduled_request_count": 1,
        "request_local_progress_exact": True,
        "target_block_count": 128,
        "cpu_target_block_count": 32,
        "gpu_target_block_count": 0,
        "target_capture_exact": True,
        "target_keyspace_matchable": True,
        "target_store_lineage_capture_exact": True,
        "target_logical_coverage_exact": True,
        "physical_target_window_exact": True,
        "target_fa_required_physical_key_count": 32,
        "restore_group_count": 2,
        "restore_groups_captured_exact": True,
        "restore_group_eligibility_complete": True,
        "logical_restore_window_exact": True,
        "logical_restore_match_tokens": 16384,
    }
    trigger = build_inflight_trigger_state(
        [row],
        pressure_start_timestamp_ns=100,
        target_block_count=128,
        require_restore_group_eligibility=True,
        stop_on_first_cpu_target_eviction=False,
        require_effective_group_geometry=True,
    )
    gate = build_restore_eligibility_gate(
        [row],
        required_restore_block_count=128,
        require_effective_group_geometry=True,
    )

    assert trigger["decision"] == "trigger_ready"
    assert trigger["exact_cpu_only_progress_event_count"] == 1
    assert gate["decision"] == "trigger_ready"
    assert gate["restore_allowed"] is True
    assert gate["latest_cpu_target_block_count"] == 32


def test_lineage_summary_keeps_logical_and_physical_units_separate() -> None:
    common = {
        "target_store_lineage_capture_exact": True,
        "target_store_key_count": 33,
        "target_fa_key_count": 32,
        "target_fa_required_physical_key_count": 32,
        "target_fa_capture_exact": True,
        "target_logical_block_count": 128,
        "target_logical_coverage_tokens": 16384,
        "target_logical_coverage_exact": True,
        "restore_group_count": 2,
        "restore_group_applicable_count": 2,
    }
    rows = [
        {"event": "target_store_lineage_captured", "timestamp_ns": 100, **common},
        {
            "event": "target_store_completed",
            "timestamp_ns": 200,
            **common,
            "target_store_scheduled_key_count": 33,
            "target_store_completed_key_count": 33,
            "target_fa_store_scheduled_key_count": 32,
            "target_fa_store_completed_key_count": 32,
        },
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 300,
            **common,
            "cpu_target_block_count": 32,
            "gpu_target_block_count": 0,
            "physical_target_window_exact": True,
            "restore_group_eligibility_complete": True,
            "logical_restore_window_exact": True,
        },
    ]
    summary = summarize_target_store_lineage_rows(
        rows, target_block_count=128
    )

    assert summary["target_fa_required_physical_key_count"] == 32
    assert summary["target_logical_block_count"] == 128
    assert summary["target_fa_store_completed_key_count_max"] == 32
    assert summary["physical_cpu_only_window_event_count"] == 1
    assert summary["logical_and_physical_window_event_count"] == 1


def test_r9_contract_and_single_server_entrypoint_are_executable(
    tmp_path: Path,
) -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    assert audit["stage"] == "P8.2-K1A-R5-F1-R9"
    assert audit["task_id"] == TASK_ID
    assert audit["developer_decision"]["cpu_blocks_per_rank"] == 128
    assert audit["developer_decision"]["physical_fa_key_count_fixed"] is False
    geometry = workload["effective_group_geometry"]
    assert geometry["logical_target_block_count_exact"] == 128
    assert geometry["full_attention_physical_key_count_must_equal_logical_128"] is False
    assert workload["runtime_config"]["pressure_context_tokens"] == 36800

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
        "execution_mode=authorized_single_lifecycle_effective_group_geometry",
        "parent_f1_r8_geometry_contract_red_accepted=true",
        "accepted_capacity_invalidated=false",
        "logical_target_block_count=128",
        "runtime_effective_group_geometry_required=true",
        "physical_fa_key_count_fixed=false",
        "fixed_pressure_must_execute_after_geometry_capture=true",
        "pressure_context_tokens=36800",
        "request_retry_count_exact=0",
        "result_transfer_authorized=true",
        "automatic_transfer_allowed=false",
    ):
        assert line in audited.stdout

    server_audit = subprocess.run(
        ["bash", str(SERVER_TASK), str(tmp_path / "unused-server")],
        cwd=ROOT,
        env={
            **os.environ,
            "P8_2_K1A_F1_R9_SERVER_TASK_AUDIT_ONLY": "1",
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
