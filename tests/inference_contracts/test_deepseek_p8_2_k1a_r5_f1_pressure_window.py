from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[2]
TOOL = (
    ROOT
    / "tools/inference_contracts/"
    "p8_2_k1a_r5_f1_pressure_window.py"
)
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_pressure_window_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_pressure_window_conditional_lifecycle.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_pressure_window.sh"
)
LIFECYCLE_RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_l2_fixed_pressure.sh"
)
READINESS = ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"
TASK_ID = "p8_2_k1a_r5_f1_pressure_window_conditional_l2_2026_0721"
PARENT_GRADE = "red_p8_2_k1a_r5_l1_r1_cpu_target_lost"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_parent_package(root: Path) -> None:
    values: dict[str, object] = {
        "result_summary.md": "R5-L1-R1 red\n",
        "environment_and_hashes.json": {
            "task_id": (
                "p8_2_k1a_r5_f1_pressure_window_conditional_l2_2026_0721"
            ),
            "head": "b2c23ef5b151d130ff0fbbfaa50257c3136f519c",
            "origin_main": "b2c23ef5b151d130ff0fbbfaa50257c3136f519c",
            "tracked_worktree_clean": True,
        },
        "request_body_manifest.json": {
            "lifecycle_count": 1,
            "pressure_context_tokens": 131072,
            "target_prefix_blocks": 64,
            "generated_text_retained": False,
            "token_ids_retained": False,
        },
        "request_summary.tsv": (
            "request_id\tk1a_role\tstatus\n"
            "lifecycle_01_warmup\twarmup\tsuccess\n"
            "lifecycle_01_target_prime\ttarget_prime\tsuccess\n"
            "lifecycle_01_pressure_01\tpressure_01\tsuccess\n"
        ),
        "residency_gate_timeline.json": {
            "pressure_request_count_executed": 1,
            "restore_sent": False,
            "terminal_decision": "cpu_target_lost",
        },
        "h2d_trigger_summary.json": {
            "target_hashes_captured_exact": True,
            "target_cpu_only_residency_observed": False,
            "target_gpu_eviction_observed": True,
            "h2d_restore_mechanism_candidate": False,
        },
        "transfer_trace_summary.json": {
            "d2h_store_complete": True,
            "d2h_completed_worker_count": 8,
            "h2d_restore_complete": False,
            "h2d_completed_worker_count": 0,
        },
        "connector_resolution_summary.json": {
            "resolved_connector_exact": True,
            "resolved_cpu_capacity_exact": True,
            "resolved_lazy_offload_exact": True,
        },
        "mtp_queue_health_summary.json": {"request_count": 3},
        "repair_diagnostic_summary.json": {"hybrid_diagnostic_ok": True},
        "host_memory_summary.json": {"preflight_gate_ok": True},
        "grading_summary.json": {
            "server_grade": "red_p8_2_k1a_r5_l1_r1_cpu_target_lost",
            "successful_request_count": 3,
            "request_evidence_exact": True,
            "cleanup": "clean",
            "actual_cpu_eviction_proven": False,
            "h2d_restore_mechanism_candidate": False,
            "performance_reference_accepted": False,
            "k2_authorized": False,
            "p8_3_i1_authorized": False,
            "next_task_authorized": False,
        },
        "cleanup_status.txt": "clean\n",
        "resource_recovery_summary.json": {"resource_recovery_exact": True},
    }
    files = {}
    for relative, value in values.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, str):
            path.write_text(value, encoding="utf-8")
        else:
            _write_json(path, value)
        files[relative] = {
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "sensitivity": "bounded_operational_metadata_no_content_or_token_ids",
        }
    _write_json(
        root / "candidate_manifest.server_local.json",
        {
            "schema_version": "p8_2_k1a_r5_l1_bounded_candidate_manifest_v1",
            "files": files,
            "payload_file_count": 14,
            "candidate_total_bytes": sum(row["bytes"] for row in files.values()),
            "generated_content_retained": False,
            "token_ids_retained": False,
            "result_transfer_authorized": True,
            "transfer_method_selected": False,
        },
    )


def _make_raw_result(root: Path, snapshots: list[dict[str, object]]) -> None:
    control = root / "runtime/request_control"
    rows = [
        {"request_id": "lifecycle_01_warmup", "k1a_role": "warmup"},
        {
            "request_id": "lifecycle_01_target_prime",
            "k1a_role": "target_prime",
        },
        {
            "request_id": "lifecycle_01_pressure_01",
            "k1a_role": "pressure_01",
        },
    ]
    path = control / "raw_request_results.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    windows = {
        "lifecycle_01_warmup": (100, 190),
        "lifecycle_01_target_prime": (200, 290),
        "lifecycle_01_pressure_01": (300, 490),
    }
    metrics = control / "raw_metrics"
    metrics.mkdir(parents=True)
    for request_id, (start, end) in windows.items():
        before = metrics / f"{request_id}_before.prom"
        after = metrics / f"{request_id}_after.prom"
        before.write_text("before\n", encoding="utf-8")
        after.write_text("after\n", encoding="utf-8")
        os.utime(before, ns=(start, start))
        os.utime(after, ns=(end, end))

    trace = root / "runtime/offload_trace/h2d-residency.1.jsonl"
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.write_text(
        "".join(json.dumps(row) + "\n" for row in snapshots),
        encoding="utf-8",
    )


def _make_source(manager: Path, block_pool: Path) -> None:
    manager.write_text(
        """
class SimpleCPUOffloadScheduler:
    def _prepare_lazy_store_specs(self):
        return self.cpu_block_pool.get_new_blocks(1)
    def get_num_new_matched_tokens(self):
        return self.cpu_coordinator.find_longest_cache_hit()
""".strip()
        + "\n",
        encoding="utf-8",
    )
    block_pool.write_text(
        """
class BlockPool:
    def get_new_blocks(self, num_blocks):
        blocks = self.free_block_queue.popleft_n(num_blocks)
        for block in blocks:
            self._maybe_evict_cached_block(block)
        return blocks
    def _maybe_evict_cached_block(self, block):
        self.cached_block_hash_to_block.pop(block.block_hash, block.block_id)
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _run_tool(
    parent: Path,
    raw: Path,
    manager: Path,
    block_pool: Path,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "analyze",
            "--parent-package",
            str(parent),
            "--raw-result-root",
            str(raw),
            "--manager-source",
            str(manager),
            "--block-pool-source",
            str(block_pool),
            "--output-dir",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_f1_blocks_without_an_exact_cpu_only_pressure_window(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    raw = tmp_path / "raw"
    output = tmp_path / "output"
    manager = tmp_path / "manager.py"
    block_pool = tmp_path / "block_pool.py"
    _make_parent_package(parent)
    _make_source(manager, block_pool)
    _make_raw_result(
        raw,
        [
            {
                "event": "target_hashes_captured",
                "timestamp_ns": 220,
                "target_block_count": 64,
                "raw_hash_values_retained": False,
            },
            {
                "event": "target_residency_snapshot",
                "timestamp_ns": 250,
                "target_block_count": 64,
                "cpu_target_block_count": 0,
                "gpu_target_block_count": 64,
                "cpu_free_block_count": 128,
                "gpu_free_block_count": 1000,
                "raw_hash_values_retained": False,
            },
            {
                "event": "target_cache_evicted",
                "timestamp_ns": 350,
                "tier": "cpu",
                "target_evicted_count": 1,
                "raw_hash_values_retained": False,
            },
            {
                "event": "target_residency_snapshot",
                "timestamp_ns": 360,
                "target_block_count": 64,
                "cpu_target_block_count": 0,
                "gpu_target_block_count": 0,
                "cpu_free_block_count": 0,
                "gpu_free_block_count": 936,
                "raw_hash_values_retained": False,
            },
        ],
    )

    completed = _run_tool(parent, raw, manager, block_pool, output)

    assert completed.returncode == 0, completed.stderr or completed.stdout
    attribution = json.loads((output / "pressure_window_attribution.json").read_text())
    grading = json.loads((output / "grading_summary.json").read_text())
    assert attribution["target_prime_terminal_cpu_blocks"] == 0
    assert attribution["target_prime_terminal_gpu_blocks"] == 64
    assert attribution["pressure_cpu_only_exact_snapshot_count"] == 0
    assert attribution["cpu_target_eviction_event_count"] == 1
    assert attribution["safe_pressure_window_proven"] is False
    assert grading["server_grade"] == (
        "blocked_p8_2_k1a_r5_f1_no_exact_pressure_window"
    )
    assert grading["formal_conditional_lifecycle_allowed"] is False
    assert grading["npu_started"] is False
    assert grading["model_request_sent"] is False


def test_f1_rejects_a_pool_delta_even_with_one_exact_pressure_window(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    raw = tmp_path / "raw"
    output = tmp_path / "output"
    manager = tmp_path / "manager.py"
    block_pool = tmp_path / "block_pool.py"
    _make_parent_package(parent)
    _make_source(manager, block_pool)
    _make_raw_result(
        raw,
        [
            {
                "event": "target_hashes_captured",
                "timestamp_ns": 220,
                "target_block_count": 64,
                "raw_hash_values_retained": False,
            },
            {
                "event": "target_residency_snapshot",
                "timestamp_ns": 250,
                "target_block_count": 64,
                "cpu_target_block_count": 0,
                "gpu_target_block_count": 64,
                "cpu_free_block_count": 128,
                "gpu_free_block_count": 1000,
                "raw_hash_values_retained": False,
            },
            {
                "event": "target_residency_snapshot",
                "timestamp_ns": 340,
                "target_block_count": 64,
                "cpu_target_block_count": 64,
                "gpu_target_block_count": 0,
                "cpu_free_block_count": 64,
                "gpu_free_block_count": 936,
                "raw_hash_values_retained": False,
            },
            {
                "event": "target_cache_evicted",
                "timestamp_ns": 370,
                "tier": "cpu",
                "target_evicted_count": 1,
                "raw_hash_values_retained": False,
            },
            {
                "event": "target_residency_snapshot",
                "timestamp_ns": 380,
                "target_block_count": 64,
                "cpu_target_block_count": 63,
                "gpu_target_block_count": 0,
                "cpu_free_block_count": 0,
                "gpu_free_block_count": 900,
                "raw_hash_values_retained": False,
            },
        ],
    )

    completed = _run_tool(parent, raw, manager, block_pool, output)

    assert completed.returncode == 0, completed.stderr or completed.stdout
    attribution = json.loads((output / "pressure_window_attribution.json").read_text())
    candidate = json.loads((output / "pressure_candidate.json").read_text())
    grading = json.loads((output / "grading_summary.json").read_text())
    assert attribution["pressure_cpu_only_exact_snapshot_count"] == 1
    assert attribution["safe_pressure_window_proven"] is False
    assert attribution["gpu_free_blocks_before_pressure"] == 1000
    assert attribution["gpu_free_blocks_at_first_exact_window"] == 936
    assert attribution["gpu_free_block_net_delta_at_first_exact_window"] == 64
    assert attribution["request_local_pressure_progress_present"] is False
    assert attribution["pressure_allocated_blocks_at_first_exact_window"] is None
    assert candidate["candidate_pressure_total_blocks"] is None
    assert candidate["candidate_output_tokens"] == 64
    assert candidate["candidate_pressure_context_tokens"] is None
    assert candidate["candidate_is_fixed_not_search"] is False
    assert candidate["formal_conditional_lifecycle_allowed"] is False
    assert candidate["reason"] == (
        "exact CPU=64 GPU=0 window exists, but GPU free-block net delta "
        "is not request-local allocation or progress evidence"
    )
    assert grading["server_grade"] == (
        "blocked_p8_2_k1a_r5_f1_no_exact_pressure_window"
    )
    assert grading["formal_conditional_lifecycle_allowed"] is False
    assert grading["npu_started"] is False
    assert grading["model_request_sent"] is False


def test_f1_rejects_target_prime_residency_drift_before_creating_output(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    raw = tmp_path / "raw"
    output = tmp_path / "output"
    manager = tmp_path / "manager.py"
    block_pool = tmp_path / "block_pool.py"
    _make_parent_package(parent)
    _make_source(manager, block_pool)
    _make_raw_result(
        raw,
        [
            {
                "event": "target_hashes_captured",
                "timestamp_ns": 220,
                "target_block_count": 64,
                "raw_hash_values_retained": False,
            },
            {
                "event": "target_residency_snapshot",
                "timestamp_ns": 250,
                "target_block_count": 64,
                "cpu_target_block_count": 1,
                "gpu_target_block_count": 63,
                "cpu_free_block_count": 127,
                "gpu_free_block_count": 1000,
                "raw_hash_values_retained": False,
            },
            {
                "event": "target_residency_snapshot",
                "timestamp_ns": 340,
                "target_block_count": 64,
                "cpu_target_block_count": 0,
                "gpu_target_block_count": 0,
                "cpu_free_block_count": 0,
                "gpu_free_block_count": 936,
                "raw_hash_values_retained": False,
            },
        ],
    )

    completed = _run_tool(parent, raw, manager, block_pool, output)

    assert completed.returncode != 0
    assert "target-prime residency drift" in completed.stderr
    assert not output.exists()


def test_f1_contract_is_offline_first_and_allows_only_one_fixed_lifecycle(
    tmp_path: Path,
) -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    parent = audit["received_r5_l1_r1_package"]
    state = workload["execution_state"]
    conditional = workload["conditional_lifecycle"]

    assert audit["stage"] == "P8.2-K1A-R5-F1"
    assert parent["server_grade"] == PARENT_GRADE
    assert parent["file_count"] == 15
    assert parent["payload_file_count"] == 14
    assert parent["payload_bytes"] == 15788
    assert parent["manifest_bytes"] == 3578
    assert parent["total_bytes"] == 19366
    assert parent["manifest_sha256"] == (
        "1209e22dc67aa1c15e80efcd26b453d7303665a5cd1a982ca2c41152334bb022"
    )
    assert parent["successful_request_count"] == 3
    assert parent["d2h_completed_worker_count"] == 8
    assert parent["pressure_request_count_executed"] == 1
    assert parent["target_terminal_cpu_blocks"] == 0
    assert parent["target_terminal_gpu_blocks"] == 0
    assert parent["actual_cpu_eviction_proven"] is False

    assert workload["task_id"] == TASK_ID
    assert workload["offline_first_gate"]["npu_started"] is False
    assert workload["offline_first_gate"]["model_request_sent"] is False
    assert conditional["requires_exact_cpu_only_window"] is True
    assert conditional["requires_unique_free_block_delta"] is True
    assert conditional["candidate_is_fixed_not_search"] is True
    assert conditional["pressure_request_count_exact"] == 1
    assert conditional["request_order"] == [
        "warmup",
        "target_prime",
        "fixed_pressure",
        "restore_follower",
    ]
    assert conditional["request_count_min"] == 3
    assert conditional["request_count_max"] == 4
    assert conditional["request_count_exact_if_trigger_observed"] == 4
    assert conditional["terminal_pre_restore_request_count"] == 3
    assert conditional["request_retry_count"] == 0
    assert conditional["cpu_bytes_to_use_per_rank"] == 430604288
    assert conditional["capacity_search_allowed"] is False
    assert state["formal_model_lifecycle_count_max"] == 1
    assert state["npu_execution_authorized"] is True
    assert state["conditional_on_offline_ready_grade"] is True
    assert state["second_lifecycle_authorized"] is False
    assert state["result_transfer_authorized"] is True
    assert state["transfer_method_selected"] is False
    assert state["next_task_authorized"] is False
    assert state["k2_authorized"] is False
    assert state["p8_3_i1_authorized"] is False

    completed = subprocess.run(
        ["bash", str(RUNNER), str(tmp_path / "analysis")],
        cwd=ROOT,
        env={**os.environ, "P8_2_K1A_R5_F1_AUDIT_ONLY": "1"},
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    for line in (
        f"task_id={TASK_ID}",
        "offline_first=true",
        "npu_execution_authorized=conditional",
        "formal_model_lifecycle_count_max=1",
        "pressure_request_count_exact=1",
        "request_count_min=3",
        "request_count_max=4",
        "request_count_exact_if_trigger_observed=4",
        "terminal_pre_restore_request_count=3",
        "request_retry_count=0",
        "result_transfer_authorized=true",
        "transfer_method_selected=false",
        "next_task_authorized=false",
    ):
        assert line in completed.stdout

    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    artifacts = readiness["artifacts"]
    current_task_id = "p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722"
    assert artifacts["current_server_handoff_task"] == current_task_id
    assert artifacts["completed_p8_2_k1a_r5_f1_runner"].endswith(RUNNER.name)
    assert artifacts["completed_p8_2_k1a_r5_l2_runner"].endswith(
        LIFECYCLE_RUNNER.name
    )
    assert readiness["acceptance"]["p8_2_k1a_r5_f1_pool_delta_gate_permanent_fail_closed"] is True

    handoff = HANDOFF.read_text(encoding="utf-8")
    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert handoff.count("\ntask_id: ") == 1
    assert f"task_id: {current_task_id}" in handoff
    assert "parent_f1_pool_delta_gate_fail_closed: true" in handoff
    for field in (
        "offline_first: true",
        "npu_execution_authorized: conditional",
        "formal_model_lifecycle_count_max: 2",
        "pressure_request_count_exact: 1",
        "model_request_count_min: 3",
        "model_request_count_max: 4",
        "request_retry_count_exact: 0",
        "result_transfer_authorized: true",
        "transfer_method_selected: false",
        "next_task_authorized: false",
        "k2_authorized: false",
        "p8_3_i1_authorized: false",
    ):
        assert field in handoff


def test_l2_wrapper_requires_the_exact_ready_analysis_candidate(
    tmp_path: Path,
) -> None:
    result = tmp_path / "result"
    base_env = {
        **os.environ,
        "P8_2_K1A_FIXED_PRESSURE_CONTEXT_TOKENS": "8128",
        "P8_2_K1A_AUDIT_ONLY": "1",
    }
    missing = subprocess.run(
        ["bash", str(LIFECYCLE_RUNNER), str(result)],
        cwd=ROOT,
        env=base_env,
        text=True,
        capture_output=True,
    )
    assert missing.returncode != 0
    assert "P8_2_K1A_R5_F1_ANALYSIS_ROOT" in missing.stderr

    analysis = tmp_path / "analysis"
    _write_json(
        analysis / "grading_summary.json",
        {
            "server_grade": (
                "candidate_ready_p8_2_k1a_r5_f1_exact_pressure_window"
            ),
            "formal_conditional_lifecycle_allowed": True,
        },
    )
    _write_json(
        analysis / "pressure_candidate.json",
        {
            "candidate_pressure_context_tokens": 8128,
            "candidate_pressure_total_blocks": 64,
            "candidate_output_tokens": 64,
            "candidate_is_fixed_not_search": True,
            "formal_conditional_lifecycle_allowed": True,
        },
    )
    (analysis / "task_grade.txt").write_text(
        "candidate_ready_p8_2_k1a_r5_f1_exact_pressure_window\n",
        encoding="utf-8",
    )
    ready = subprocess.run(
        ["bash", str(LIFECYCLE_RUNNER), str(result)],
        cwd=ROOT,
        env={**base_env, "P8_2_K1A_R5_F1_ANALYSIS_ROOT": str(analysis)},
        text=True,
        capture_output=True,
    )
    assert ready.returncode == 0, ready.stderr or ready.stdout
    for line in (
        "offline_ready_grade_verified=true",
        "fixed_pressure_context_tokens=8128",
        f"task_id={TASK_ID}",
        "lifecycle_count=1",
        "request_count_min=3",
        "request_count_max=4",
        "pressure_request_count_max=1",
        "npu_execution_authorized=true",
        "next_task_authorized=false",
    ):
        assert line in ready.stdout
