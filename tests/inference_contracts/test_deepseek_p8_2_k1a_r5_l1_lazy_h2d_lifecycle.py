from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[2]
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py"
)
OBSERVER = (
    ROOT / "tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py"
)
LIFECYCLE_RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh"
)
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_l1_lazy_h2d_lifecycle_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle.yaml"
)
READINESS = ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"


def test_prepare_freezes_a_bounded_dynamic_lazy_lifecycle(tmp_path: Path) -> None:
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
    assert manifest["task_id"] == (
        "p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721"
    )
    assert manifest["lifecycle_count"] == 1
    assert manifest["fixed_request_count"] == 3
    assert manifest["pressure_request_count_max"] == 5
    assert manifest["request_count_max"] == 8
    assert manifest["request_order_contract"] == [
        "warmup",
        "target_prime",
        "pressure_01..pressure_05_until_cpu_present_gpu_absent",
        "restore_follower_if_and_only_if_trigger_observed",
    ]
    assert manifest["target_prefix_tokens"] == 8192
    assert manifest["target_prefix_blocks"] == 64
    assert manifest["restore_match_tokens_required"] == 16384
    assert manifest["pressure_context_tokens"] == 131072
    assert manifest["pressure_request_count_is_runtime_fact"] is False
    assert manifest["restore_body_prepared_but_conditionally_sent"] is True
    assert manifest["generated_text_retained"] is False
    assert manifest["token_ids_retained"] is False
    assert len(manifest["records"]) == 8
    assert len({row["request_body_sha256"] for row in manifest["records"]}) == 8
    for record in manifest["records"]:
        body = artifact / record["body_relative_path"]
        assert hashlib.sha256(body.read_bytes()).hexdigest() == record[
            "request_body_sha256"
        ]


def test_residency_gate_only_releases_restore_for_cpu_present_gpu_absent(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    trace = trace_dir / "h2d-residency.123.jsonl"
    rows = [
        {
            "event": "target_hashes_captured",
            "target_block_count": 64,
            "raw_hash_values_retained": False,
        },
        {
            "event": "target_residency_snapshot",
            "reason": "after_connector_meta",
            "target_block_count": 64,
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 64,
        },
    ]
    trace.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    output = tmp_path / "gate.json"

    waiting = subprocess.run(
        [
            sys.executable,
            str(OBSERVER),
            "gate",
            "--trace-dir",
            str(trace_dir),
            "--output",
            str(output),
            "--target-block-count",
            "64",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert waiting.returncode == 3, waiting.stderr or waiting.stdout
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["decision"] == "continue_pressure"
    assert value["restore_allowed"] is False

    rows.append(
        {
            "event": "target_residency_snapshot",
            "reason": "after_connector_meta",
            "target_block_count": 64,
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 0,
        }
    )
    trace.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    ready = subprocess.run(
        [
            sys.executable,
            str(OBSERVER),
            "gate",
            "--trace-dir",
            str(trace_dir),
            "--output",
            str(output),
            "--target-block-count",
            "64",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert ready.returncode == 0, ready.stderr or ready.stdout
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["decision"] == "trigger_ready"
    assert value["restore_allowed"] is True
    assert value["target_cpu_only_residency_observed"] is True
    assert value["raw_hash_values_retained"] is False


def test_controller_never_sends_restore_before_the_runtime_trigger(
    tmp_path: Path,
) -> None:
    gate = tmp_path / "gate.json"
    output = tmp_path / "decision.json"

    gate.write_text(
        json.dumps({"decision": "continue_pressure", "restore_allowed": False}),
        encoding="utf-8",
    )
    waiting = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "decide-next",
            "--gate",
            str(gate),
            "--pressure-count",
            "2",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert waiting.returncode == 0, waiting.stderr or waiting.stdout
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "action": "send_pressure_03",
        "pressure_count": 2,
        "restore_allowed": False,
    }

    gate.write_text(
        json.dumps({"decision": "trigger_ready", "restore_allowed": True}),
        encoding="utf-8",
    )
    ready = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "decide-next",
            "--gate",
            str(gate),
            "--pressure-count",
            "2",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert ready.returncode == 0, ready.stderr or ready.stdout
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "action": "send_restore_follower",
        "pressure_count": 2,
        "restore_allowed": True,
    }

    gate.write_text(
        json.dumps({"decision": "continue_pressure", "restore_allowed": False}),
        encoding="utf-8",
    )
    exhausted = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "decide-next",
            "--gate",
            str(gate),
            "--pressure-count",
            "5",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert exhausted.returncode == 3
    assert json.loads(output.read_text(encoding="utf-8"))["action"] == (
        "stop_trigger_not_reached"
    )


def test_controller_preserves_observable_not_ready_after_wait_timeout(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    trace = trace_dir / "h2d-residency.123.jsonl"
    trace.write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in (
                {
                    "event": "target_hashes_captured",
                    "target_block_count": 64,
                    "raw_hash_values_retained": False,
                },
                {
                    "event": "target_residency_snapshot",
                    "reason": "target_request_finished",
                    "target_block_count": 64,
                    "cpu_target_block_count": 0,
                    "gpu_target_block_count": 64,
                },
                {"event": "store_event_completed", "event_idx": 1},
                *(
                    event
                    for rank in range(8)
                    for event in (
                        {
                            "event": "device_copy_submitted",
                            "direction": "d2h",
                            "pid": 1000 + rank,
                            "byte_count": 1024,
                        },
                        {
                            "event": "transfer_completed",
                            "direction": "d2h",
                            "pid": 1000 + rank,
                        },
                    )
                ),
            )
        ),
        encoding="utf-8",
    )
    output = tmp_path / "wait.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "wait-for-residency",
            "--trace-dir",
            str(trace_dir),
            "--timeout-seconds",
            "0.01",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 3, completed.stderr or completed.stdout
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["decision"] == "continue_pressure"
    assert value["restore_allowed"] is False
    assert value["target_hashes_captured_exact"] is True
    assert value["latest_cpu_target_block_count"] == 0
    assert value["latest_gpu_target_block_count"] == 64


def test_controller_does_not_apply_pressure_before_target_store_completion(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    (trace_dir / "h2d-residency.123.jsonl").write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in (
                {
                    "event": "target_hashes_captured",
                    "target_block_count": 64,
                },
                {
                    "event": "target_residency_snapshot",
                    "reason": "target_request_finished",
                    "target_block_count": 64,
                    "cpu_target_block_count": 0,
                    "gpu_target_block_count": 64,
                },
            )
        ),
        encoding="utf-8",
    )
    output = tmp_path / "wait.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "wait-for-residency",
            "--trace-dir",
            str(trace_dir),
            "--timeout-seconds",
            "0.01",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 4
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["decision"] == "unobservable"
    assert value["d2h_store_complete_before_pressure"] is False
    assert value["restore_allowed"] is False


def test_finalize_accepts_only_the_complete_dynamic_h2d_chain(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact"
    control = artifact / "runtime/request_control"
    trace_dir = artifact / "runtime/offload_trace"
    control.mkdir(parents=True)
    trace_dir.mkdir(parents=True)
    (artifact / "request_body_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "p8_2_k1a_r5_l1_request_body_manifest_v1",
                "task_id": (
                    "p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721"
                ),
                "request_count_max": 8,
                "generated_text_retained": False,
                "token_ids_retained": False,
                "records": [],
            }
        ),
        encoding="utf-8",
    )
    roles = ["warmup", "target_prime", "pressure_01", "restore_follower"]
    request_rows = [
        {
            "request_id": f"lifecycle_01_{role}",
            "k1a_role": role,
            "status": "success",
            "http_status": 200,
            "prompt_tokens": 131072 if role.startswith("pressure") else (
                4096 if role == "warmup" else 32768
            ),
            "context_tokens": 131072 if role.startswith("pressure") else (
                4096 if role == "warmup" else 32768
            ),
            "output_tokens": 64,
            "generated_token_count": 64,
            "streamed_token_count": 64,
            "finish_reason": "length",
            "saw_done": True,
            "max_token_chunk_width": 2,
            "queue_metrics_ok": True,
            "counter_continuity_ok": True,
            "spec_activity_ok": True,
            "accepted_token_delta": 32,
            "request_body_sha256": "a" * 64,
        }
        for role in roles
    ]
    (control / "raw_request_results.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in request_rows),
        encoding="utf-8",
    )
    (control / "residency_gate_timeline.json").write_text(
        json.dumps(
            {
                "pressure_request_count_executed": 1,
                "restore_sent": True,
                "trigger_observed_before_restore": True,
                "terminal_decision": "trigger_ready",
            }
        ),
        encoding="utf-8",
    )
    transfer_rows = []
    for direction in ("d2h", "h2d"):
        for rank in range(8):
            pid = 1000 + rank
            transfer_rows.extend(
                [
                    {"event": "copy_thread_started", "pid": pid},
                    {
                        "event": "device_copy_submitted",
                        "direction": direction,
                        "pid": pid,
                        "byte_count": 1024,
                    },
                    {
                        "event": "device_copy_enqueued",
                        "direction": direction,
                        "pid": pid,
                    },
                    {
                        "event": "copy_blocks_entered",
                        "direction": direction,
                        "pid": pid,
                    },
                    {
                        "event": "copy_blocks_returned",
                        "direction": direction,
                        "pid": pid,
                    },
                    {
                        "event": "transfer_poll_entered",
                        "direction": direction,
                        "pid": pid,
                        "pending_event_count": 1,
                        "copy_thread_alive": True,
                    },
                    {
                        "event": "transfer_completed",
                        "direction": direction,
                        "rank": str(rank),
                        "pid": pid,
                    },
                ]
            )
    trace_rows = [
        {"event": "target_hashes_captured", "target_block_count": 64},
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
            "request_id": "lifecycle_01_restore_follower",
            "num_new_tokens": 16384,
        },
        {
            "event": "load_scheduled",
            "request_id": "lifecycle_01_restore_follower",
            "block_count": 128,
        },
        {"event": "store_event_completed", "event_idx": 1},
        *transfer_rows,
        {
            "event": "load_request_completed",
            "request_id": "lifecycle_01_restore_follower",
        },
    ]
    (trace_dir / "combined.json").write_text(
        json.dumps(trace_rows), encoding="utf-8"
    )
    for name, value in {
        "cleanup_status.txt": "clean\n",
        "connector_resolution_summary.json": json.dumps(
            {"resolved_connector_exact": True, "resolved_lazy_offload_exact": True}
        ),
        "repair_diagnostic_summary.json": json.dumps(
            {"all_required_managers_resolved": True}
        ),
        "environment_and_hashes.json": json.dumps(
            {"task_id": "p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721"}
        ),
        "host_memory_summary.json": json.dumps({"preflight_gate_ok": True}),
        "resource_recovery_summary.json": json.dumps(
            {
                "keep_alive_restored_exact": True,
                "port_7000_free": True,
                "vllm_residual_process_count": 0,
                "all_eight_npu_healthy": True,
                "tracked_worktree_clean": True,
            }
        ),
    }.items():
        (artifact / name).write_text(value, encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "finalize",
            "--artifact-dir",
            str(artifact),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    grading = json.loads(
        (artifact / "grading_summary.json").read_text(encoding="utf-8")
    )
    assert grading["server_grade"] == (
        "candidate_green_p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle"
    )
    assert grading["successful_request_count"] == 4
    assert grading["pressure_request_count_executed"] == 1
    assert grading["restore_sent_after_trigger_only"] is True
    assert grading["target_gpu_eviction_observed"] is True
    assert grading["target_cpu_only_residency_observed"] is True
    assert grading["h2d_worker_completion_exact"] is True
    assert grading["h2d_restore_mechanism_candidate"] is True
    assert grading["performance_reference_accepted"] is False
    manifest = json.loads(
        (artifact / "candidate_manifest.server_local.json").read_text()
    )
    assert manifest["result_transfer_authorized"] is True
    assert manifest["transfer_method_selected"] is False
    assert manifest["payload_file_count"] <= 15
    assert manifest["transfer_file_count_including_manifest"] <= 16
    manifest_bytes = (
        artifact / "candidate_manifest.server_local.json"
    ).stat().st_size
    assert manifest["candidate_total_bytes"] + manifest_bytes <= 71680


def test_observer_uses_the_controller_role_marker_not_server_request_ids(
    tmp_path: Path,
) -> None:
    rows = [
        {
            "event": "target_hashes_captured",
            "contract_role": "target_prime",
            "request_id": "cmpl-random-a",
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
            "contract_role": "restore_follower",
            "request_id": "cmpl-random-b",
            "num_new_tokens": 16384,
        },
        {
            "event": "load_scheduled",
            "contract_role": "restore_follower",
            "request_id": "cmpl-random-b",
            "block_count": 128,
        },
        *[
            {
                "event": "transfer_completed",
                "direction": "h2d",
                "rank": str(rank),
            }
            for rank in range(8)
        ],
        {
            "event": "load_request_completed",
            "contract_role": "restore_follower",
            "request_id": "cmpl-random-b",
        },
    ]
    rows_path = tmp_path / "rows.json"
    output = tmp_path / "summary.json"
    rows_path.write_text(json.dumps(rows), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(OBSERVER),
            "summarize",
            "--rows",
            str(rows_path),
            "--output",
            str(output),
            "--target-block-count",
            "64",
            "--restore-tokens",
            "16384",
            "--expected-world-size",
            "8",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["restore_cpu_hit_exact"] is True
    assert summary["restore_load_scheduled"] is True
    assert summary["restore_load_request_completed"] is True


def test_mode_audit_freezes_lazy_connector_and_dynamic_request_bounds(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["P8_2_K1A_MODE_AUDIT_ONLY"] = "1"
    completed = subprocess.run(
        ["bash", str(LIFECYCLE_RUNNER), str(tmp_path / "result")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    audit = dict(
        line.split("=", 1)
        for line in completed.stdout.splitlines()
        if "=" in line
    )
    assert audit["task_id"] == (
        "p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721"
    )
    assert audit["lifecycle_count"] == "1"
    assert audit["request_count_min"] == "4"
    assert audit["request_count_max"] == "8"
    assert audit["pressure_request_count_max"] == "5"
    assert audit["lazy_offload"] == "true"
    assert audit["observer_mode"] == (
        "observe_only_with_controller_role_marker_no_runtime_decision_or_copy_mutation"
    )
    argv = shlex.split(audit["server_command"])
    config = json.loads(argv[argv.index("--kv-transfer-config") + 1])
    assert config["kv_connector_extra_config"] == {
        "cpu_bytes_to_use": 3444834304,
        "cpu_bytes_to_use_per_rank": 430604288,
        "lazy_offload": True,
    }
    assert argv.count("--kv-transfer-config") == 1
    assert "--enable-prefix-caching" in argv
    assert "--enable-chunked-prefill" in argv


def test_r5_l1_contract_is_preserved_as_parent_of_current_r1() -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    task_id = "p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721"

    assert audit["stage"] == "P8.2-K1A-R5-L1"
    assert audit["received_r5_f0_package"]["server_grade"] == (
        "candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility"
    )
    assert audit["received_r5_f0_package"]["file_count"] == 9
    assert audit["received_r5_f0_package"]["total_bytes"] == 7122
    assert audit["developer_decision"]["formal_lazy_lifecycle_allowed"] is True
    assert audit["developer_decision"]["k2_authorized"] is False

    assert workload["task_id"] == task_id
    assert workload["stage_contract"]["stage"] == "P8.2-K1A-R5-L1"
    assert workload["runtime_config"]["lazy_offload"] is True
    assert workload["runtime_config"]["cpu_bytes_to_use_per_rank"] == 430604288
    plan = workload["dynamic_request_plan"]
    assert plan["lifecycle_count_exact"] == 1
    assert plan["request_count_min"] == 4
    assert plan["request_count_max"] == 8
    assert plan["pressure_request_count_max"] == 5
    assert plan["pressure_count_is_candidate_not_fixed_runtime_fact"] is True
    assert plan["restore_requires_cpu_present_gpu_absent"] is True
    assert plan["request_retries"] == 0
    state = workload["execution_state"]
    assert state["npu_execution_authorized"] is True
    assert state["keep_alive_stop_and_restore_authorized"] is True
    assert state["vllm_server_start_authorized"] is True
    assert state["model_requests_authorized"] is True
    assert state["result_transfer_authorized"] is True
    assert state["transfer_method_selected"] is False
    assert state["next_task_authorized"] is False
    assert state["k2_authorized"] is False
    assert state["p8_3_i1_authorized"] is False

    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    assert readiness["artifacts"]["current_server_handoff_task"] == (
        "p8_2_k1a_r5_f1_r9_effective_group_geometry_2026_0723"
    )
    assert readiness["artifacts"]["next_workload"].endswith(
        "p8_2_k1a_r5_f1_r9_effective_group_geometry.yaml"
    )

    handoff = HANDOFF.read_text(encoding="utf-8")
    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert handoff.count("\ntask_id: ") == 1
    assert (
        "task_id: p8_2_k1a_r5_f1_r9_effective_group_geometry_2026_0723"
        in handoff
    )
    for field in (
        "npu_execution_authorized: true",
            "formal_model_lifecycle_count_exact: 1",
            "model_request_count_max: 4",
        "result_transfer_authorized: true",
        "transfer_method_selected: false",
        "next_task_authorized: false",
        "k2_authorized: false",
        "p8_3_i1_authorized: false",
    ):
        assert field in handoff
    for marker in (
            "logical_target_block_count_exact: 128",
            "physical_fa_key_count_fixed: false",
            "pressure_01",
            "pressure_request_count_exact: 1",
        "request-local",
        "grading_summary.json",
        "candidate_manifest.server_local.json",
        "upload-api",
    ):
        assert marker in handoff
    assert "automatic_transfer_allowed: false" in handoff
