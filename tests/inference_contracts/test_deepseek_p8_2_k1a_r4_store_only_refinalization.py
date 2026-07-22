from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
R4_AUDIT = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/p8_2_k1a_r4_store_only_refinalization_audit.yaml"
)
R4_WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r4_store_only_refinalization_and_trace_attribution.yaml"
)
R4_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/run_deepseek_p8_2_k1a_r4_offline_closeout.sh"
)
READINESS = REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
HANDOFF = REPO_ROOT / "通信模块/docs/developer-to-server.md"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _write_bounded_parent(source: Path) -> None:
    source.mkdir()
    roles = (
        ("warmup", 4096, "success", 0),
        ("prime", 32768, "success", 0),
        ("pressure", 131072, "success", 0),
        ("restore_follower", 32768, "failed", 0),
        ("repeat_follower", 32768, "success", 16384),
        ("isolated_control", 32768, "success", 0),
    )
    header = (
        "request_id\tk1a_role\tstatus\thttp_status\tcontext_tokens\t"
        "output_tokens\tprompt_tokens\tgenerated_token_count\t"
        "streamed_token_count\tfinish_reason\tsaw_done\tmax_token_chunk_width\t"
        "prefix_hits_delta\taccepted_token_delta\tqueue_metrics_ok\t"
        "counter_continuity_ok\tspec_activity_ok\tfirst_failed_predicate\t"
        "request_body_sha256\n"
    )
    rows = []
    for index, (role, context, status, hits) in enumerate(roles, start=1):
        predicate = "prefix_evidence_ok" if role == "restore_follower" else ""
        rows.append(
            f"lifecycle_01_{role}\t{role}\t{status}\t200\t{context}\t64\t"
            f"{context}\t64\t64\tlength\tTrue\t2\t{hits}\t32\tTrue\t"
            f"True\tTrue\t{predicate}\t{index:064d}\n"
        )
    (source / "request_summary.tsv").write_text(
        header + "".join(rows), encoding="utf-8"
    )
    trace = {
        "d2h_store_complete": True,
        "d2h_async_copy_pipeline_exact": True,
        "h2d_restore_complete": False,
        "runtime_evidence_exact": False,
        "d2h_bytes_total": 7239534592,
        "h2d_bytes_total": 0,
        "store_event_completed_count": 41,
    }
    _write_json(source / "transfer_trace_summary.json", trace)
    _write_json(
        source / "grading_inputs.json",
        {
            "server_grade": (
                "red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete"
            ),
            "connector_resolution_ok": True,
            "repair_diagnostic_ok": True,
            "host_memory_gate_ok": True,
            "accepted_capacity_exact": True,
            "cpu_bytes_to_use": 3444834304,
            "cpu_bytes_to_use_per_rank": 430604288,
            "trace_summary": trace,
        },
    )
    _write_json(
        source / "repair_diagnostic_summary.json",
        {"hybrid_diagnostic_ok": True, "lcm_block_sizes": [16384]},
    )
    (source / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
    (source / "task_grade.txt").write_text(
        "red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete\n",
        encoding="utf-8",
    )
    files = []
    for path in sorted(source.iterdir()):
        files.append(
            {
                "absolute_path": f"/server/{path.name}",
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "sensitivity": "bounded_operational_metadata_no_content_or_token_ids",
            }
        )
    _write_json(
        source / "candidate_manifest.server_local.json",
        {
            "schema_version": "p8_2_k1a_bounded_candidate_manifest_v1",
            "task_id": (
                "p8_2_k1a_r3_r2_r2_r1_r1_r1_deepseek_v4_flash_"
                "causal_exception_replay_2026_0720"
            ),
            "files": files,
            "payload_file_count": len(files),
            "payload_total_bytes": sum(row["bytes"] for row in files),
            "generated_content_retained": False,
            "token_ids_retained": False,
        },
    )


def test_r4_refinalizes_bounded_parent_as_store_only_without_mutating_source(
    tmp_path: Path,
) -> None:
    from tools.inference_contracts import (
        run_deepseek_p8_2_k1a_simple_cpu_offload as runner,
    )

    source = tmp_path / "bounded_parent"
    output = tmp_path / "r4_refinalized"
    _write_bounded_parent(source)
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source.iterdir()
    }

    grading = runner.refinalize_k1a_bounded_evidence(source, output)

    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source.iterdir()
    }
    assert after == before
    assert grading["source_server_grade"] == (
        "red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete"
    )
    assert grading["refinalized_grade"] == (
        "yellow_p8_2_k1a_store_only_no_restore"
    )
    assert grading["successful_request_count"] == 6
    assert grading["producer_status_success_count"] == 5
    assert grading["request_transport_evidence_exact"] is True
    assert grading["offload_store_evidence_candidate"] is True
    assert grading["offload_restore_evidence_candidate"] is False
    assert grading["cpu_bytes_to_use"] == 3444834304
    assert grading["cpu_bytes_to_use_per_rank"] == 430604288
    assert grading["d2h_bytes_total_semantics"] == "cumulative_submitted_copy_volume"
    assert grading["unique_cpu_residency_bytes_observed"] is False
    assert grading["failure_classification"] == "h2d_restore_not_observed"
    assert grading["cause_proven_as_unique"] is False
    assert grading["lcm_block_sizes"] == [16384]
    assert grading["scheduler_block_size_tokens"] == 128
    assert grading["source_evidence_unchanged"] is True
    assert (output / "candidate_manifest.server_local.json").is_file()


def test_r4_refinalizer_resolves_server_manifest_payloads_across_result_roots(
    tmp_path: Path,
) -> None:
    from tools.inference_contracts import (
        run_deepseek_p8_2_k1a_simple_cpu_offload as runner,
    )

    manifest_root = tmp_path / "server_local"
    payload_root = tmp_path / "runtime_result"
    output = tmp_path / "r4_refinalized"
    _write_bounded_parent(manifest_root)
    payload_root.mkdir()
    manifest_path = manifest_root / "candidate_manifest.server_local.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        name = Path(entry["absolute_path"]).name
        destination = payload_root / name
        (manifest_root / name).rename(destination)
        entry["absolute_path"] = str(destination)
    _write_json(manifest_path, manifest)

    grading = runner.refinalize_k1a_bounded_evidence(manifest_root, output)

    assert grading["refinalized_grade"] == (
        "yellow_p8_2_k1a_store_only_no_restore"
    )
    assert grading["source_evidence_unchanged"] is True


def test_r4_attributes_raw_transfer_events_to_request_windows_without_claiming_residency(
    tmp_path: Path,
) -> None:
    from tools.inference_contracts.p8_2_k1a_trace_attribution import (
        build_trace_attribution,
    )

    source = tmp_path / "raw_parent"
    metrics = source / "modes/prefix_cache_on/raw_metrics"
    traces = source / "runtime/offload_trace"
    metrics.mkdir(parents=True)
    traces.mkdir(parents=True)
    roles = (
        "warmup",
        "prime",
        "pressure",
        "restore_follower",
        "repeat_follower",
        "isolated_control",
    )
    raw_rows = []
    for index, role in enumerate(roles):
        request_id = f"lifecycle_01_{role}"
        raw_rows.append(
            {
                "request_id": request_id,
                "k1a_role": role,
                "prefix_hits_delta": 16384 if role == "repeat_follower" else 0,
            }
        )
        before = metrics / f"{request_id}_before.prom"
        after = metrics / f"{request_id}_after.prom"
        before.write_text("before\n", encoding="utf-8")
        after.write_text("after\n", encoding="utf-8")
        os.utime(before, ns=(1000 + index * 2000, 1000 + index * 2000))
        os.utime(after, ns=(2000 + index * 2000, 2000 + index * 2000))
    request_root = source / "modes/prefix_cache_on"
    (request_root / "raw_request_results.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in raw_rows), encoding="utf-8"
    )
    trace_rows = [
        {
            "event": "transfer_scheduled",
            "direction": "d2h",
            "event_idx": 1,
            "block_count": 16,
            "timestamp_ns": 3200,
        },
        {
            "event": "device_copy_submitted",
            "direction": "d2h",
            "event_idx": 1,
            "byte_count": 100,
            "pid": 10,
            "timestamp_ns": 3300,
        },
        {
            "event": "store_event_completed",
            "direction": "d2h",
            "event_idx": 1,
            "block_count": 16,
            "timestamp_ns": 3500,
        },
        {
            "event": "device_copy_submitted",
            "direction": "d2h",
            "event_idx": 2,
            "byte_count": 200,
            "pid": 10,
            "timestamp_ns": 5300,
        },
        {
            "event": "store_event_completed",
            "direction": "d2h",
            "event_idx": 2,
            "block_count": 32,
            "timestamp_ns": 5500,
        },
    ]
    (traces / "trace.10.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in trace_rows), encoding="utf-8"
    )
    output = tmp_path / "attribution"

    result = build_trace_attribution(source, output)

    assert result["request_window_gate"] == "pass"
    assert result["request_windows_exact"] is True
    assert result["by_role"]["prime"]["d2h_submitted_copy_bytes"] == 100
    assert result["by_role"]["prime"]["store_event_completed_count"] == 1
    assert result["by_role"]["pressure"]["d2h_submitted_copy_bytes"] == 200
    assert result["by_role"]["restore_follower"]["cpu_hit_matched_count"] == 0
    assert result["by_role"]["restore_follower"]["load_scheduled_count"] == 0
    assert result["restore_miss_then_repeat_gpu_hit_pattern"] is True
    assert result["unique_cpu_residency_bytes_observed"] is False
    assert result["prime_blocks_resident_at_restore_proven"] is False
    assert result["pressure_evicted_prime_from_cpu_tier_proven"] is False
    assert result["h2d_absence_cause_proven_as_unique"] is False
    assert result["source_evidence_unchanged"] is True
    assert (output / "trace_attribution_summary.json").is_file()


def test_r4_audits_cpu_tier_capacity_churn_semantics_without_claiming_actual_eviction(
    tmp_path: Path,
) -> None:
    from tools.inference_contracts.p8_2_k1a_trace_attribution import (
        audit_cpu_tier_source_semantics,
    )

    vllm_root = tmp_path / "vllm"
    manager = vllm_root / "v1/simple_kv_offload/manager.py"
    block_pool = vllm_root / "v1/core/block_pool.py"
    manager.parent.mkdir(parents=True)
    block_pool.parent.mkdir(parents=True)
    manager.write_text(
        """
class SimpleCPUOffloadScheduler:
    def get_num_new_matched_tokens(self, request, num_computed_tokens):
        return self.cpu_coordinator.find_longest_cache_hit([], 0)

    def _prepare_eager_store_specs(self, scheduler_output):
        num_free = self.cpu_block_pool.get_num_free_blocks()
        return self.cpu_block_pool.get_new_blocks(num_free)
""".lstrip(),
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
        return self.cached_block_hash_to_block.pop(block.block_hash, block.block_id)
""".lstrip(),
        encoding="utf-8",
    )
    output = tmp_path / "source_semantics.json"

    result = audit_cpu_tier_source_semantics(vllm_root, output)

    assert result["source_semantics_gate"] == "pass"
    assert result["cpu_match_uses_find_longest_cache_hit"] is True
    assert result["eager_store_allocates_from_cpu_block_pool"] is True
    assert result["free_block_queue_dequeue_method"] == "popleft_n"
    assert result["cpu_pool_allocation_may_evict_cached_hash_entry"] is True
    assert result["capacity_churn_hypothesis_supported"] is True
    assert result["pressure_evicted_prime_from_cpu_tier_proven"] is False
    assert result["h2d_absence_cause_proven_as_unique"] is False
    assert output.is_file()


def test_r4_trace_tool_exposes_trace_and_source_audit_commands() -> None:
    script = (
        Path(__file__).resolve().parents[2]
        / "tools/inference_contracts/p8_2_k1a_trace_attribution.py"
    )
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "trace-attribution" in completed.stdout
    assert "source-audit" in completed.stdout


def test_r4_composes_refinalization_trace_and_source_gates_into_offline_green(
    tmp_path: Path,
) -> None:
    from tools.inference_contracts import (
        run_deepseek_p8_2_k1a_simple_cpu_offload as runner,
    )
    from tools.inference_contracts.p8_2_k1a_trace_attribution import (
        finalize_r4_offline_closeout,
    )

    result_root = tmp_path / "result"
    refinalization = result_root / "refinalization"
    trace = result_root / "trace_attribution"
    source = result_root / "source_semantics"
    parent = tmp_path / "parent"
    _write_bounded_parent(parent)
    runner.refinalize_k1a_bounded_evidence(parent, refinalization)
    trace.mkdir(parents=True)
    _write_json(
        trace / "trace_attribution_summary.json",
        {
            "request_window_gate": "pass",
            "request_windows_exact": True,
            "source_evidence_unchanged": True,
            "restore_miss_then_repeat_gpu_hit_pattern": True,
            "unique_cpu_residency_bytes_observed": False,
            "pressure_evicted_prime_from_cpu_tier_proven": False,
            "h2d_absence_cause_proven_as_unique": False,
        },
    )
    _write_json(
        trace / "trace_source_provenance.json",
        {"source_evidence_unchanged": True},
    )
    source.mkdir()
    _write_json(
        source / "cpu_tier_source_semantics.json",
        {
            "source_semantics_gate": "pass",
            "capacity_churn_hypothesis_supported": True,
            "pressure_evicted_prime_from_cpu_tier_proven": False,
            "h2d_absence_cause_proven_as_unique": False,
        },
    )

    task_id = "p8_2_k1a_r4_r1_store_only_source_semantics_replay_2026_0721"
    result = finalize_r4_offline_closeout(
        result_root,
        task_id=task_id,
        candidate_green_grade=(
            "candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout"
        ),
    )

    assert result["task_grade"] == (
        "candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout"
    )
    assert result["task_id"] == task_id
    assert result["parent_runtime_grade_preserved"] is True
    assert result["store_only_refinalization_accepted"] is True
    assert result["trace_attribution_gate"] == "pass"
    assert result["source_semantics_gate"] == "pass"
    assert result["formal_h2d_trigger_lifecycle_allowed"] is False
    assert result["npu_started"] is False
    assert result["model_request_sent"] is False
    assert result["next_task_authorized"] is False
    manifest = json.loads(
        (result_root / "candidate_manifest.server_local.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["payload_file_count"] == 9
    assert manifest["manifest_is_transfer_control_file"] is True
    assert manifest["transfer_file_count_including_manifest"] == 10
    assert f"- task_id: `{task_id}`" in (
        result_root / "result_summary.md"
    ).read_text(encoding="utf-8")


def test_r4_finalize_cli_returns_nonzero_for_a_blocked_joint_grade(
    monkeypatch,
) -> None:
    from tools.inference_contracts import p8_2_k1a_trace_attribution as tool

    monkeypatch.setattr(
        tool,
        "finalize_r4_offline_closeout",
        lambda _result_root, **_kwargs: {
            "task_grade": "blocked_p8_2_k1a_r4_offline_closeout_gate",
            "source_semantics_gate": "pass",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["p8_2_k1a_trace_attribution.py", "finalize-closeout", "--result-root", "/tmp/r4"],
    )

    assert tool.main() == 2


def test_r4_finalize_cli_accepts_r4_r1_task_and_grade_identity(monkeypatch) -> None:
    from tools.inference_contracts import p8_2_k1a_trace_attribution as tool

    captured = {}
    candidate_grade = (
        "candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout"
    )

    def fake_finalize(_result_root, **kwargs):
        captured.update(kwargs)
        return {"task_grade": candidate_grade}

    monkeypatch.setattr(tool, "finalize_r4_offline_closeout", fake_finalize)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "p8_2_k1a_trace_attribution.py",
            "finalize-closeout",
            "--result-root",
            "/tmp/r4-r1",
            "--task-id",
            "p8_2_k1a_r4_r1_store_only_source_semantics_replay_2026_0721",
            "--candidate-green-grade",
            candidate_grade,
            "--blocked-grade",
            "blocked_p8_2_k1a_r4_r1_offline_closeout_gate",
        ],
    )

    assert tool.main() == 0
    assert captured == {
        "task_id": (
            "p8_2_k1a_r4_r1_store_only_source_semantics_replay_2026_0721"
        ),
        "candidate_green_grade": candidate_grade,
        "blocked_grade": "blocked_p8_2_k1a_r4_r1_offline_closeout_gate",
    }


def test_r4_contract_is_read_only_and_preserved_as_historical_provenance() -> None:
    audit = yaml.safe_load(R4_AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(R4_WORKLOAD.read_text(encoding="utf-8"))
    assert audit["decision"]["parent_server_grade_preserved"] == (
        "red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete"
    )
    assert audit["decision"]["developer_refinalized_grade"] == (
        "yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_store_only_no_restore"
    )
    assert audit["evidence_interpretation"]["d2h_bytes_total_semantics"] == (
        "cumulative_submitted_copy_volume"
    )
    assert audit["evidence_interpretation"]["lcm_block_size_tokens"] == 16384
    assert audit["evidence_interpretation"]["scheduler_block_size_tokens"] == 128
    task_id = (
        "p8_2_k1a_r4_store_only_refinalization_and_trace_attribution_2026_0720"
    )
    assert workload["task_id"] == task_id
    assert workload["execution_state"]["npu_execution_authorized"] is False
    assert workload["execution_state"]["vllm_server_start_authorized"] is False
    assert workload["execution_state"]["model_requests_authorized"] is False
    assert workload["execution_state"]["result_transfer_authorized"] is True
    assert workload["execution_state"]["next_task_authorized"] is False
    assert workload["source_gate"]["parent_manifest_sha256"] == (
        "6463f2f13e5c7149e6fcbb502caad5edfce1f9b7d82c16c74a72babd64035498"
    )
    assert workload["source_gate"]["frozen_manager_sha256"] == (
        "fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b"
    )
    assert workload["source_gate"]["frozen_block_pool_sha256"] == (
        "36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283"
    )
    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    artifacts = readiness["artifacts"]
    assert artifacts["p8_2_k1a_r4_store_only_refinalization_audit"].endswith(
        R4_AUDIT.name
    )
    assert artifacts["next_workload"].endswith(
        "p8_2_k1a_r5_f1_r3_inflight_abort_restore.yaml"
    )
    assert artifacts["current_server_handoff_task"] != task_id
    assert artifacts["current_p8_2_k1a_r4_runner"].endswith(R4_RUNNER.name)
    handoff = HANDOFF.read_text(encoding="utf-8")
    assert f"task_id: {task_id}" not in handoff
    assert "kill -TERM" not in handoff
    assert "vllm serve" not in handoff
    assert "curl " not in handoff
    subprocess.run(["bash", "-n", str(R4_RUNNER)], check=True)
