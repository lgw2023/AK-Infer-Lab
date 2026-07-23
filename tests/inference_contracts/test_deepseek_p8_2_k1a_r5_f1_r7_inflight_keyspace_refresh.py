from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

from tools.inference_contracts.p8_2_k1a_h2d_residency_observer import (
    build_refreshed_request_local_pressure_progress,
)
from tools.inference_contracts.run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore import (
    build_pre_pressure_admission,
    build_post_abort_revalidation_gate,
    summarize_logical_keyspace_probe_diagnostics,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh_2026_0723"
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.py"
)
LIFECYCLE = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.sh"
)
SERVER_TASK = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r7_server_task.sh"
)


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
    def __init__(self, keys: list[object]) -> None:
        self.keys = keys
        self.calls: list[tuple[list[object], int]] = []
        self.num_uncached_common_prefix_tokens = 17

    def find_longest_cache_hit(
        self, request_hashes: list[object], max_length: int
    ) -> tuple[tuple[list[_Block], ...], int, int]:
        self.calls.append((request_hashes, max_length))
        self.num_uncached_common_prefix_tokens = 99
        return ([_Block(key) for key in self.keys],), max_length, 0


def test_pressure_progress_refreshes_runtime_keyspace_after_async_d2h() -> None:
    request_hashes = [f"logical-{index}" for index in range(128)]
    pool_keys = [f"runtime-group0-{index}" for index in range(64)]
    coordinator = _Coordinator(pool_keys)
    scheduler = type("Scheduler", (), {})()
    scheduler.cpu_coordinator = coordinator
    scheduler.cpu_block_pool = _Pool(set(pool_keys))
    scheduler._gpu_block_pool = _Pool(set())
    scheduler._p8_2_k1a_target_request_hashes = tuple(request_hashes)
    scheduler._p8_2_k1a_target_pool_keys = ()
    scheduler._p8_2_k1a_target_hashes = ()
    scheduler._p8_2_k1a_target_capture_summary = {
        "target_capture_cardinality_exact": True,
        "target_keyspace_matchable": False,
        "target_capture_exact": False,
    }
    new_request = type(
        "NewRequest", (), {"req_id": "pressure", "num_computed_tokens": 32768}
    )()
    output = type(
        "SchedulerOutput",
        (),
        {
            "num_scheduled_tokens": {"pressure": 4032},
            "scheduled_new_reqs": (new_request,),
            "scheduled_cached_reqs": None,
        },
    )()

    progress = build_refreshed_request_local_pressure_progress(
        scheduler,
        output,
        contract_role="pressure_01",
        target_block_count=128,
        restore_match_tokens=16384,
        hash_block_size_tokens=128,
    )

    assert coordinator.calls == [(request_hashes, 16384)]
    assert coordinator.num_uncached_common_prefix_tokens == 17
    assert progress is not None
    assert progress["request_local_progress_exact"] is True
    assert progress["logical_keyspace_probe_reason"] == (
        "pressure_request_local_progress"
    )
    assert progress["target_capture_cardinality_exact"] is True
    assert progress["target_keyspace_matchable"] is True
    assert progress["target_capture_exact"] is True
    assert progress["logical_restore_match_tokens"] == 16384
    assert progress["cpu_target_block_count"] == 128
    assert progress["gpu_target_block_count"] == 0
    assert progress["target_pool_key_count"] == 64
    assert progress["cpu_target_pool_key_match_count"] == 64
    assert progress["gpu_target_pool_key_match_count"] == 0
    assert progress["raw_hash_values_retained"] is False


def test_pre_pressure_gate_admits_fixed_pressure_for_inflight_refresh() -> None:
    rows = [
        {
            "event": "target_hashes_captured",
            "timestamp_ns": 100,
            "target_block_count": 128,
            "request_hash_candidate_count": 128,
            "target_capture_cardinality_exact": True,
            "target_keyspace_matchable": False,
            "target_capture_exact": False,
            "target_pool_key_count": 0,
            "cpu_target_pool_key_match_count": 0,
            "gpu_target_pool_key_match_count": 0,
        }
    ]

    admitted = build_pre_pressure_admission(
        rows,
        d2h_store_complete=True,
        target_block_count=128,
        allow_inflight_keyspace_refresh=True,
    )
    legacy = build_pre_pressure_admission(
        rows,
        d2h_store_complete=True,
        target_block_count=128,
        allow_inflight_keyspace_refresh=False,
    )

    assert admitted["decision"] == "pressure_admitted_for_inflight_refresh"
    assert admitted["pressure_allowed"] is True
    assert admitted["d2h_store_complete_before_pressure"] is True
    assert admitted["target_capture_cardinality_exact"] is True
    assert admitted["target_keyspace_matchable"] is False
    assert admitted["target_capture_exact"] is False
    assert admitted["request_hash_candidate_count"] == 128
    assert legacy["decision"] == "target_keyspace_unobservable_before_pressure"
    assert legacy["pressure_allowed"] is False


def test_post_abort_gate_requires_a_fresh_retained_key_snapshot() -> None:
    exact = {
        "event": "target_residency_snapshot",
        "target_block_count": 128,
        "cpu_target_block_count": 128,
        "gpu_target_block_count": 0,
        "target_capture_cardinality_exact": True,
        "target_keyspace_matchable": True,
        "target_capture_exact": True,
        "restore_group_count": 2,
        "restore_groups_captured_exact": True,
        "restore_group_eligibility_complete": True,
    }

    stale = build_post_abort_revalidation_gate(
        [{**exact, "timestamp_ns": 199}],
        abort_requested_timestamp_ns=200,
        required_restore_block_count=128,
        require_restore_group_eligibility=True,
    )
    fresh = build_post_abort_revalidation_gate(
        [
            {**exact, "timestamp_ns": 199},
            {**exact, "timestamp_ns": 201, "reason": "after_connector_output"},
        ],
        abort_requested_timestamp_ns=200,
        required_restore_block_count=128,
        require_restore_group_eligibility=True,
    )

    assert stale["decision"] == "post_abort_revalidation_unobservable"
    assert stale["restore_allowed"] is False
    assert stale["post_abort_candidate_event_count"] == 0
    assert fresh["decision"] == "trigger_ready"
    assert fresh["restore_allowed"] is True
    assert fresh["post_abort_candidate_event_count"] == 1
    assert fresh["post_abort_revalidation_fresh"] is True


def test_bounded_probe_diagnostics_explain_near_miss_and_exact_transition() -> None:
    rows = [
        {
            "event": "target_hashes_captured",
            "timestamp_ns": 100,
            "contract_role": "target_prime",
            "target_capture_source": "runtime_cpu_coordinator_longest_hit",
            "request_hash_candidate_count": 128,
            "logical_restore_match_tokens": 0,
            "target_pool_key_count": 0,
            "cpu_target_pool_key_match_count": 0,
            "gpu_target_pool_key_match_count": 0,
            "target_keyspace_matchable": False,
            "target_capture_exact": False,
            "target_keyspace_probe_error_type": "LookupMiss",
        },
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 200,
            "contract_role": "pressure_01",
            "logical_keyspace_probe_reason": "pressure_request_local_progress",
            "target_capture_source": "runtime_cpu_coordinator_longest_hit",
            "request_hash_candidate_count": 128,
            "logical_restore_match_tokens": 8192,
            "target_pool_key_count": 0,
            "cpu_target_pool_key_match_count": 0,
            "gpu_target_pool_key_match_count": 0,
            "restore_group_count": 1,
            "target_keyspace_matchable": False,
            "target_capture_exact": False,
        },
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 300,
            "contract_role": "pressure_01",
            "logical_keyspace_probe_reason": "pressure_request_local_progress",
            "target_capture_source": "runtime_cpu_coordinator_longest_hit",
            "request_hash_candidate_count": 128,
            "logical_restore_match_tokens": 16384,
            "target_pool_key_count": 66,
            "cpu_target_pool_key_match_count": 66,
            "gpu_target_pool_key_match_count": 0,
            "restore_group_count": 2,
            "target_keyspace_matchable": True,
            "target_capture_exact": True,
        },
    ]

    summary = summarize_logical_keyspace_probe_diagnostics(rows)

    assert summary["probe_event_count"] == 3
    assert summary["pressure_probe_event_count"] == 2
    assert summary["exact_probe_event_count"] == 1
    assert summary["near_miss_probe_event_count"] == 2
    assert summary["probe_error_event_count"] == 1
    assert summary["probe_error_type_histogram"] == {"LookupMiss": 1}
    assert summary["logical_restore_match_tokens_max"] == 16384
    assert summary["target_pool_key_count_max"] == 66
    assert summary["cpu_target_pool_key_match_count_max"] == 66
    assert summary["gpu_target_pool_key_match_count_min"] == 0
    assert summary["first_probe_timestamp_ns"] == 100
    assert summary["first_exact_probe_timestamp_ns"] == 300
    assert summary["latest_probe_timestamp_ns"] == 300
    assert [stage["stage"] for stage in summary["stage_rows"]] == [
        "target_prime",
        "pressure_01",
    ]
    assert summary["raw_hash_values_retained"] is False
    assert summary["request_ids_retained"] is False
    assert summary["token_ids_retained"] is False


def test_r7_contract_keeps_accepted_capacity_and_requires_pressure_refresh() -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))

    assert audit["stage"] == "P8.2-K1A-R5-F1-R7"
    assert audit["task_id"] == TASK_ID
    assert audit["accepted_f1_r6_result"]["pressure_request_count_executed"] == 0
    assert audit["developer_diagnosis"]["circular_wait_proven_from_repo_control_flow"] is True
    decision = audit["developer_decision"]
    assert decision["cpu_blocks_per_rank"] == 128
    assert decision["pressure_context_tokens"] == 36800
    assert decision["pre_pressure_requires_runtime_keyspace_exact"] is False
    assert decision["fixed_pressure_must_execute_after_pre_pressure_gate"] is True
    assert decision["refresh_runtime_keyspace_on_every_pressure_progress"] is True
    assert decision["continue_after_unobservable_or_near_miss"] is True
    assert decision["continue_after_temporary_cpu_target_loss"] is True
    assert decision["capacity_change_authorized"] is False

    assert workload["task_id"] == TASK_ID
    assert workload["runtime_config"]["cpu_blocks_per_rank"] == 128
    assert workload["runtime_config"]["pressure_context_tokens"] == 36800
    pre_gate = workload["pre_pressure_admission"]
    assert pre_gate["d2h_store_complete_required"] is True
    assert pre_gate["request_hash_candidate_count_exact"] == 128
    assert pre_gate["runtime_keyspace_exact_required"] is False
    inflight = workload["inflight_logical_restore_keyspace_gate"]
    assert inflight["refresh_hook"] == "every_request_local_pressure_progress"
    assert inflight["unobservable_probe_stops_pressure"] is False
    assert inflight["keyspace_near_miss_stops_pressure"] is False
    assert inflight["temporary_cpu_target_loss_stops_pressure"] is False
    assert workload["execution_state"]["request_retry_count_exact"] == 0
    assert workload["execution_state"]["capacity_search_authorized"] is False
    assert workload["result_contract"][
        "logical_keyspace_probe_diagnostic_summary_required"
    ] is True


def test_r7_runner_and_audit_only_freeze_the_inflight_refresh(tmp_path: Path) -> None:
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
    assert manifest["target_prefix_tokens"] == 16384

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
        "execution_mode=authorized_single_lifecycle_inflight_keyspace_refresh",
        "parent_f1_r6_prepressure_circular_wait=true",
        "accepted_capacity_invalidated=false",
        "pressure_before_keyspace_exact_allowed=1",
        "pressure_progress_runtime_keyspace_refresh_required=true",
        "logical_keyspace_diagnostics=1",
        "pressure_context_tokens=36800",
        "logical_target_block_count=128",
        "request_retry_count_exact=0",
        "capacity_or_context_change_authorized=false",
        "result_transfer_authorized=true",
        "automatic_transfer_allowed=false",
    ):
        assert line in audited.stdout


def test_r7_server_driver_is_one_routine_keep_alive_safe_entrypoint(
    tmp_path: Path,
) -> None:
    audited = subprocess.run(
        ["bash", str(SERVER_TASK), str(tmp_path / "unused")],
        cwd=ROOT,
        env={
            **os.environ,
            "P8_2_K1A_F1_R7_SERVER_TASK_AUDIT_ONLY": "1",
        },
        text=True,
        capture_output=True,
    )
    assert audited.returncode == 0, audited.stderr or audited.stdout
    for line in (
        f"task_id={TASK_ID}",
        "server_task_driver=preflight_stop_run_cleanup_restore_probe_record_finalize",
        "keep_alive_card_ids=0,1,2,3,4,5,6,7",
        "same_card_set_restore_on_every_exit=true",
        "pressure_before_keyspace_exact_allowed=1",
        "pressure_progress_runtime_keyspace_refresh_required=true",
        "logical_keyspace_diagnostics=1",
    ):
        assert line in audited.stdout

    source = SERVER_TASK.read_text(encoding="utf-8")
    assert "run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh" in source
    assert "P8_2_K1A_LIFECYCLE_RUNNER" in source
    assert "P8_2_K1A_F1_R7_SERVER_TASK_AUDIT_ONLY" in source

    observer = (
        ROOT
        / "tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py"
    ).read_text(encoding="utf-8")
    assert 'reason="pressure_request_finished"' in observer
