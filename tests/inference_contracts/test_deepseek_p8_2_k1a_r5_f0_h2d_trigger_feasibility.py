from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/inference_contracts/p8_2_k1a_h2d_trigger_feasibility.py"
OBSERVER = ROOT / "tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py"
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f0_h2d_trigger_feasibility_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f0_h2d_trigger_feasibility.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f0_h2d_trigger_feasibility.sh"
)
READINESS = ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_r4_r1_package(root: Path) -> None:
    payloads = {
        "result_summary.md": b"candidate closeout\n",
        "grading_summary.json": json.dumps(
            {
                "task_grade": (
                    "candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout"
                ),
                "store_only_refinalization_accepted": True,
                "refinalized_runtime_grade": (
                    "yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_store_only_no_restore"
                ),
                "capacity_churn_proven_for_parent_lifecycle": False,
                "h2d_absence_cause_proven_as_unique": False,
                "formal_h2d_trigger_lifecycle_allowed": False,
                "performance_reference_accepted": False,
            },
            sort_keys=True,
        ).encode(),
        "task_grade.txt": (
            b"candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout\n"
        ),
    }
    files = []
    for relative, content in payloads.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        files.append(
            {
                "relative_path": relative,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "sensitivity": "bounded_operational_metadata_no_content_or_token_ids",
            }
        )
    _write_json(
        root / "candidate_manifest.server_local.json",
        {
            "schema_version": "p8_2_k1a_r4_offline_closeout_manifest_v1",
            "files": files,
            "payload_file_count": len(files),
            "payload_total_bytes": sum(row["bytes"] for row in files),
            "generated_content_retained": False,
            "token_ids_retained": False,
            "result_transfer_authorized": True,
            "transfer_method_selected": False,
        },
    )


def test_r5_f0_cli_builds_a_bounded_non_runtime_h2d_trigger_plan(
    tmp_path: Path,
) -> None:
    package = tmp_path / "r4-r1"
    _make_r4_r1_package(package)
    geometry = tmp_path / "geometry.json"
    rendezvous = tmp_path / "rendezvous.json"
    allocator = tmp_path / "allocator.json"
    manager = tmp_path / "manager.py"
    block_pool = tmp_path / "block_pool.py"
    output = tmp_path / "result"

    _write_json(
        geometry,
        {
            "schema_version": "p8_2_k1a_r2_geometry_summary_v1",
            "probe_run_id": "probe-1",
            "rank_count": 8,
            "rank_coverage": list(range(8)),
            "geometry_gate_ok": True,
            "rendezvous_gate_ok": True,
            "block_size_tokens": 128,
            "required_restore_tokens": 16384,
            "required_cpu_blocks": 128,
            "total_bytes_per_block": 3364096,
            "required_capacity_bytes_per_rank": 430604288,
            "required_capacity_bytes_total": 3444834304,
            "num_npu_blocks": 5048,
        },
    )
    _write_json(
        rendezvous,
        {
            "schema_version": "p8_2_k1a_r2_geometry_rendezvous_v1",
            "probe_run_id": "probe-1",
            "world_size": 8,
            "rank_coverage": list(range(8)),
            "geometry_parity_exact": True,
            "allocation_attempted": False,
        },
    )
    _write_json(
        allocator,
        {
            "schema_version": "p8_2_k1a_r2_allocator_envelope_v1",
            "grade": "candidate_ready_p8_2_k1a_r2_allocator_capacity",
            "highest_eight_rank_clean_blocks": 128,
            "required_cpu_blocks": 128,
            "candidate_cpu_bytes_per_rank": 430604288,
            "candidate_cpu_bytes_total": 3444834304,
            "acl_pinned_host_allocator_gate_ok": True,
            "capacity_candidate_ready": True,
            "formal_lifecycle_allowed": False,
        },
    )
    manager.write_text(
        """
class SimpleCPUOffloadScheduler:
    def get_num_new_matched_tokens(self):
        return self.cpu_coordinator.find_longest_cache_hit()
    def update_state_after_alloc(self):
        self._reqs_to_load[\"x\"] = True
    def build_connector_meta(self):
        load_event = self._load_event_counter
        return load_event
    def _prepare_eager_store_specs(self):
        num_free = self.cpu_block_pool.get_num_free_blocks()
        return self.cpu_block_pool.get_new_blocks(num_free)
    def _prepare_lazy_store_specs(self):
        node = self._cursor.next_free_block
        return self.cpu_block_pool.get_new_blocks(1)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    block_pool.write_text(
        """
class BlockPool:
    def get_new_blocks(self, num_blocks):
        ret = self.free_block_queue.popleft_n(num_blocks)
        for block in ret:
            self._maybe_evict_cached_block(block)
        return ret
    def _maybe_evict_cached_block(self, block):
        self.cached_block_hash_to_block.pop(block.block_hash, block.block_id)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "analyze",
            "--r4-r1-root",
            str(package),
            "--geometry-summary",
            str(geometry),
            "--rendezvous-summary",
            str(rendezvous),
            "--allocator-summary",
            str(allocator),
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

    assert completed.returncode == 0, completed.stderr or completed.stdout
    plan = json.loads((output / "trigger_geometry_plan.json").read_text())
    grading = json.loads((output / "grading_summary.json").read_text())
    assert plan["gpu_blocks_per_rank"] == 5048
    assert plan["cpu_blocks_per_rank"] == 128
    assert plan["target_prefix_tokens"] == 8192
    assert plan["target_prefix_blocks"] == 64
    assert plan["pressure_context_tokens"] == 131072
    assert plan["pressure_blocks_per_request"] == 1024
    assert plan["minimum_pressure_request_count_to_exceed_gpu_pool"] == 5
    assert plan["eager_mode_can_preserve_target_cpu_residency"] is False
    assert plan["lazy_mode_requires_runtime_residency_observer"] is True
    assert grading["server_grade"] == (
        "candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility"
    )
    assert grading["formal_h2d_trigger_lifecycle_allowed"] is False
    assert grading["npu_started"] is False
    assert grading["model_request_sent"] is False


def test_r5_f0_rejects_parent_drift_without_creating_a_result_root(
    tmp_path: Path,
) -> None:
    package = tmp_path / "r4-r1"
    _make_r4_r1_package(package)
    (package / "task_grade.txt").write_text("drifted\n", encoding="utf-8")
    output = tmp_path / "result"

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "analyze",
            "--r4-r1-root",
            str(package),
            "--geometry-summary",
            str(tmp_path / "missing-geometry.json"),
            "--rendezvous-summary",
            str(tmp_path / "missing-rendezvous.json"),
            "--allocator-summary",
            str(tmp_path / "missing-allocator.json"),
            "--manager-source",
            str(tmp_path / "missing-manager.py"),
            "--block-pool-source",
            str(tmp_path / "missing-block-pool.py"),
            "--output-dir",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode != 0
    assert not output.exists()


def test_h2d_residency_observer_requires_the_complete_cpu_only_restore_chain(
    tmp_path: Path,
) -> None:
    rows = [
        {
            "event": "target_hashes_captured",
            "request_id": "run-target_prime",
            "target_block_count": 64,
        },
        {
            "event": "target_cache_evicted",
            "tier": "gpu",
            "target_evicted_count": 64,
        },
        {
            "event": "target_residency_snapshot",
            "reason": "before_restore_match",
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 0,
        },
        {
            "event": "cpu_hit_matched",
            "request_id": "run-restore_follower",
            "num_new_tokens": 8192,
        },
        {
            "event": "load_scheduled",
            "request_id": "run-restore_follower",
            "block_count": 64,
        },
        *[
            {
                "event": "transfer_completed",
                "direction": "h2d",
                "pid": 1000 + rank,
                "rank": str(rank),
            }
            for rank in range(8)
        ],
        {
            "event": "load_request_completed",
            "request_id": "run-restore_follower",
        },
    ]
    rows_path = tmp_path / "rows.json"
    output_path = tmp_path / "summary.json"
    _write_json(rows_path, rows)

    completed = subprocess.run(
        [
            sys.executable,
            str(OBSERVER),
            "summarize",
            "--rows",
            str(rows_path),
            "--output",
            str(output_path),
            "--target-block-count",
            "64",
            "--restore-tokens",
            "8192",
            "--expected-world-size",
            "8",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    summary = json.loads(output_path.read_text())
    assert summary["target_hashes_captured_exact"] is True
    assert summary["target_gpu_eviction_observed"] is True
    assert summary["target_cpu_only_residency_observed"] is True
    assert summary["restore_cpu_hit_exact"] is True
    assert summary["restore_load_scheduled"] is True
    assert summary["h2d_worker_completion_count"] == 8
    assert summary["restore_load_request_completed"] is True
    assert summary["h2d_restore_mechanism_candidate"] is True
    assert summary["raw_hash_values_retained"] is False
    assert "target_hash_values" not in summary


def test_h2d_residency_observer_rejects_partial_worker_completion(
    tmp_path: Path,
) -> None:
    rows = [
        {
            "event": "target_hashes_captured",
            "request_id": "run-target_prime",
            "target_block_count": 64,
        },
        {
            "event": "target_cache_evicted",
            "tier": "gpu",
            "target_evicted_count": 64,
        },
        {
            "event": "target_residency_snapshot",
            "reason": "before_restore_match",
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 0,
        },
        {
            "event": "cpu_hit_matched",
            "request_id": "run-restore_follower",
            "num_new_tokens": 8192,
        },
        {
            "event": "load_scheduled",
            "request_id": "run-restore_follower",
            "block_count": 64,
        },
        *[
            {
                "event": "transfer_completed",
                "direction": "h2d",
                "rank": str(rank),
            }
            for rank in range(7)
        ],
        {
            "event": "load_request_completed",
            "request_id": "run-restore_follower",
        },
    ]
    rows_path = tmp_path / "rows.json"
    output_path = tmp_path / "summary.json"
    _write_json(rows_path, rows)

    completed = subprocess.run(
        [
            sys.executable,
            str(OBSERVER),
            "summarize",
            "--rows",
            str(rows_path),
            "--output",
            str(output_path),
            "--target-block-count",
            "64",
            "--restore-tokens",
            "8192",
            "--expected-world-size",
            "8",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    summary = json.loads(output_path.read_text())
    assert summary["h2d_worker_completion_count"] == 7
    assert summary["h2d_worker_completion_exact"] is False
    assert summary["h2d_restore_mechanism_candidate"] is False


def test_h2d_residency_observer_self_test_is_observe_only(tmp_path: Path) -> None:
    output = tmp_path / "observer-self-test.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(OBSERVER),
            "self-test",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(output.read_text())
    assert result["observer_mode"] == (
        "observe_only_no_decision_request_order_or_copy_mutation"
    )
    assert result["wrapped_scheduler_methods"] == [
        "request_finished_all_groups",
        "get_num_new_matched_tokens",
        "update_state_after_alloc",
        "build_connector_meta",
        "update_connector_output",
    ]
    assert result["wrapped_block_pool_methods"] == [
        "_maybe_evict_cached_block"
    ]
    assert result["original_return_values_preserved"] is True
    assert result["original_exceptions_preserved"] is True
    assert result["scheduling_or_copy_arguments_mutated"] is False
    assert result["raw_hash_values_emitted"] is False


def test_r5_f0_is_preserved_in_the_current_r5_l1_r1_lineage() -> None:
    import yaml

    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    task_id = "p8_2_k1a_r5_f0_h2d_trigger_feasibility_2026_0721"

    assert audit["stage"] == "P8.2-K1A-R5-F0"
    assert audit["received_r4_r1_package"]["file_count"] == 10
    assert audit["received_r4_r1_package"]["total_bytes"] == 32546
    assert audit["received_r4_r1_package"]["manifest_sha256"] == (
        "008f753135f087201c0e8f0f53662dede1124691a2a551064f89e65a7a23ddde"
    )
    assert audit["developer_decision"]["r4_r1_offline_closeout_accepted"] is True
    assert audit["developer_decision"]["h2d_restore_mechanism_accepted"] is False
    assert audit["developer_decision"]["formal_h2d_trigger_lifecycle_allowed"] is False

    assert workload["task_id"] == task_id
    assert workload["stage_contract"]["stage"] == "P8.2-K1A-R5-F0"
    assert workload["trigger_geometry"]["gpu_blocks_per_rank"] == 5048
    assert workload["trigger_geometry"]["target_prefix_tokens"] == 8192
    assert workload["trigger_geometry"]["pressure_context_tokens"] == 131072
    assert workload["trigger_geometry"]["pressure_request_count_candidate"] == 5
    state = workload["execution_state"]
    assert state["npu_execution_authorized"] is False
    assert state["keep_alive_stop_authorized"] is False
    assert state["vllm_server_start_authorized"] is False
    assert state["model_requests_authorized"] is False
    assert state["formal_model_lifecycle_count_exact"] == 0
    assert state["model_request_count_exact"] == 0
    assert state["result_transfer_authorized"] is True
    assert state["transfer_method_selected"] is False
    assert state["next_task_authorized"] is False
    assert workload["result_contract"]["payload_file_count_exact"] == 8
    assert workload["result_contract"]["transfer_file_count_including_manifest"] == 9

    audit_only = subprocess.run(
        ["bash", str(RUNNER)],
        cwd=ROOT,
        env={"P8_2_K1A_R5_F0_AUDIT_ONLY": "1"},
        text=True,
        capture_output=True,
    )
    assert audit_only.returncode == 0, audit_only.stderr or audit_only.stdout
    assert f"task_id={task_id}" in audit_only.stdout
    assert "npu_execution_authorized=false" in audit_only.stdout
    assert "formal_model_lifecycle_count=0" in audit_only.stdout
    assert "model_request_count=0" in audit_only.stdout
    assert "result_transfer_authorized=true" in audit_only.stdout
    assert "next_task_authorized=false" in audit_only.stdout

    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    artifacts = readiness["artifacts"]
    assert artifacts["current_server_handoff_task"] == (
        "p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_2026_0722"
    )
    assert artifacts["next_workload"].endswith(
        "p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.yaml"
    )
    assert artifacts["current_p8_2_k1a_r5_f0_runner"].endswith(RUNNER.name)

    handoff = HANDOFF.read_text(encoding="utf-8")
    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert handoff.count("\ntask_id: ") == 1
    assert "candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility" in handoff
    assert "task_id: p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_2026_0722" in handoff
    assert "npu_execution_authorized: true" in handoff
    assert "keep_alive_stop_authorized: true" in handoff
    assert "vllm_server_start_authorized: true" in handoff
    assert "model_requests_authorized: true" in handoff
    assert "result_transfer_authorized: true" in handoff
    assert "transfer_method_selected: false" in handoff
    assert "next_task_authorized: false" in handoff
    assert "model_request_count_exact: 4" in handoff
    assert "CPU=64/GPU=0" in handoff
