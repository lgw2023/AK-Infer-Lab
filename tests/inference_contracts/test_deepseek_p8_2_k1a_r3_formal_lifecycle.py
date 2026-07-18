from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import re
import shlex
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/p8_2_k1a_r3_formal_lifecycle_audit.yaml"
)
WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r3_simple_cpu_offload_store_restore.yaml"
)
R3_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r3_simple_cpu_offload.sh"
)
REQUEST_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py"
)
HANDOFF = REPO_ROOT / "通信模块/docs/developer-to-server.md"
READINESS = REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"


def test_r3_contract_uses_only_the_developer_accepted_r2_capacity() -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))

    assert audit["stage"] == "P8.2-K1A-R3"
    assert audit["parent"]["developer_grade"] == (
        "ready_p8_2_k1a_r2_allocator_capacity"
    )
    assert audit["parent"]["offline_provenance_replay"] == "pass"
    assert audit["accepted_capacity"] == {
        "block_size_tokens": 128,
        "required_restore_tokens": 16384,
        "required_cpu_blocks": 128,
        "bytes_per_block": 3364096,
        "cpu_bytes_to_use_per_rank": 430604288,
        "cpu_bytes_to_use_total": 3444834304,
        "world_size": 8,
    }
    assert audit["decision"]["formal_lifecycle_authorized"] is True
    assert audit["decision"]["capacity_search_authorized"] is False
    assert audit["decision"]["k2_authorized"] is False

    assert workload["task_id"] == (
        "p8_2_k1a_r3_deepseek_v4_flash_simple_cpu_offload_store_restore_"
        "2026_0718"
    )
    assert workload["stage_contract"]["stage"] == "P8.2-K1A-R3"
    runtime = workload["runtime_fixed"]
    assert runtime["cpu_bytes_to_use_per_rank"] == 430604288
    assert runtime["cpu_bytes_to_use"] == 3444834304
    assert runtime["cpu_bytes_to_use"] == (
        runtime["cpu_bytes_to_use_per_rank"] * runtime["tensor_parallel_size"]
    )
    assert workload["capacity_contract"]["runtime_capacity_equals_r2_candidate"] is True
    assert workload["capacity_contract"]["capacity_search_authorized"] is False
    assert workload["execution_state"]["result_transfer_authorized"] is True
    assert workload["result_package_policy"]["automatic_transfer_allowed"] is False
    assert workload["result_package_policy"]["selection_required_before_any_transfer"] is True


def test_r3_runner_audit_exposes_the_exact_resolved_capacity(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["P8_2_K1A_AUDIT_ONLY"] = "1"
    audit_run = subprocess.run(
        ["bash", str(R3_RUNNER), str(tmp_path / "result")],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    audit = dict(
        line.split("=", 1)
        for line in audit_run.stdout.splitlines()
        if "=" in line
    )
    assert audit["task_id"] == (
        "p8_2_k1a_r3_deepseek_v4_flash_simple_cpu_offload_store_restore_"
        "2026_0718"
    )
    assert audit["execution_mode"] == (
        "authorized_accepted_capacity_single_lifecycle_six_request_mechanism"
    )
    assert audit["cpu_bytes_to_use"] == "3444834304"
    assert audit["cpu_bytes_to_use_per_rank"] == "430604288"
    assert len(audit["server_command_sha256"]) == 64

    env.pop("P8_2_K1A_AUDIT_ONLY")
    env["P8_2_K1A_MODE_AUDIT_ONLY"] = "1"
    mode_run = subprocess.run(
        ["bash", str(R3_RUNNER), str(tmp_path / "result")],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    mode = dict(
        line.split("=", 1)
        for line in mode_run.stdout.splitlines()
        if "=" in line
    )
    argv = shlex.split(mode["server_command"])
    config = json.loads(argv[argv.index("--kv-transfer-config") + 1])
    assert config == {
        "kv_connector": "SimpleCPUOffloadConnector",
        "kv_role": "kv_both",
        "kv_connector_extra_config": {
            "cpu_bytes_to_use": 3444834304,
            "cpu_bytes_to_use_per_rank": 430604288,
            "lazy_offload": False,
        },
    }
    assert mode["task_id"] == audit["task_id"]
    assert mode["cpu_bytes_to_use"] == audit["cpu_bytes_to_use"]
    assert mode["cpu_bytes_to_use_per_rank"] == audit["cpu_bytes_to_use_per_rank"]
    assert mode["lifecycle_count"] == "1"
    assert mode["request_count"] == "6"


def test_r3_finalizer_requires_exact_capacity_and_closes_store_restore(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact"
    request_root = artifact / "modes/prefix_cache_on"
    trace_root = artifact / "runtime/offload_trace"
    request_root.mkdir(parents=True)
    trace_root.mkdir(parents=True)

    roles = (
        ("warmup", 4096),
        ("prime", 32768),
        ("pressure", 131072),
        ("restore_follower", 32768),
        ("repeat_follower", 32768),
        ("isolated_control", 32768),
    )
    request_rows = [
        {
            "request_id": f"lifecycle_01_{role}",
            "status": "success",
            "http_status": 200,
            "prompt_tokens": context,
            "context_tokens": context,
            "output_tokens": 64,
            "generated_token_count": 64,
            "streamed_token_count": 64,
            "finish_reason": "length",
            "saw_done": True,
            "max_token_chunk_width": 2,
            "queue_metrics_ok": True,
            "counter_continuity_ok": True,
            "spec_activity_ok": True,
            "accepted_token_delta": 64,
            "request_body_sha256": f"{index:064x}",
            "ttft_ms": 1.0,
            "e2el_ms": 2.0,
        }
        for index, (role, context) in enumerate(roles, start=1)
    ]
    (request_root / "raw_request_results.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in request_rows),
        encoding="utf-8",
    )

    trace_rows: list[dict[str, object]] = []
    for pid in range(100, 108):
        trace_rows.extend(
            [
                {
                    "event": "device_copy_submitted",
                    "direction": "d2h",
                    "pid": pid,
                    "event_idx": 1,
                    "block_count": 128,
                    "byte_count": 430604288,
                },
                {
                    "event": "transfer_completed",
                    "direction": "d2h",
                    "pid": pid,
                    "event_hwm": 1,
                },
                {
                    "event": "device_copy_submitted",
                    "direction": "h2d",
                    "pid": pid,
                    "event_idx": 2,
                    "block_count": 128,
                    "byte_count": 430604288,
                },
                {
                    "event": "transfer_completed",
                    "direction": "h2d",
                    "pid": pid,
                    "event_hwm": 2,
                },
            ]
        )
    trace_rows.extend(
        [
            {"event": "store_event_completed", "pid": 90},
            {
                "event": "cpu_hit_matched",
                "pid": 90,
                "request_id": "lifecycle_01_restore_follower",
                "num_new_tokens": 16384,
            },
            {
                "event": "load_scheduled",
                "pid": 90,
                "request_id": "lifecycle_01_restore_follower",
                "block_count": 128,
            },
            {
                "event": "load_request_completed",
                "pid": 90,
                "request_id": "lifecycle_01_restore_follower",
            },
        ]
    )
    (trace_root / "trace.test.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in trace_rows),
        encoding="utf-8",
    )
    (artifact / "connector_resolution_summary.json").write_text(
        json.dumps(
            {
                "resolved_connector_exact": True,
                "resolved_cpu_capacity_exact": True,
                "cpu_bytes_to_use": 3444834304,
                "cpu_bytes_to_use_per_rank": 430604288,
            }
        ),
        encoding="utf-8",
    )
    (artifact / "repair_diagnostic_summary.json").write_text(
        json.dumps({"hybrid_diagnostic_ok": True}), encoding="utf-8"
    )
    (artifact / "host_memory_summary.json").write_text(
        json.dumps(
            {
                "preflight_gate_ok": True,
                "configured_cpu_tier_bytes_total": 3444834304,
                "configured_cpu_tier_bytes_per_rank": 430604288,
            }
        ),
        encoding="utf-8",
    )
    (artifact / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "P8_2_K1A_TASK_ID": (
                "p8_2_k1a_r3_deepseek_v4_flash_simple_cpu_offload_store_"
                "restore_2026_0718"
            ),
            "P8_2_K1A_CPU_BYTES_TO_USE": "3444834304",
            "P8_2_K1A_CPU_BYTES_TO_USE_PER_RANK": "430604288",
            "P8_2_K1A_CANDIDATE_GREEN": (
                "candidate_green_p8_2_k1a_r3_simple_cpu_offload_store_restore"
            ),
            "P8_2_K1A_NO_SUCCESS_GRADE": "red_p8_2_k1a_r3_no_success",
            "P8_2_K1A_PARTIAL_GRADE": "yellow_p8_2_k1a_r3_partial",
            "P8_2_K1A_STORE_ONLY_GRADE": (
                "yellow_p8_2_k1a_r3_store_only_no_restore"
            ),
            "P8_2_K1A_EVIDENCE_INCOMPLETE_GRADE": (
                "red_p8_2_k1a_r3_transfer_evidence_incomplete"
            ),
        }
    )
    completed = subprocess.run(
        [
            "python3",
            str(REQUEST_RUNNER),
            "finalize",
            "--artifact-dir",
            str(artifact),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    grading = json.loads((artifact / "grading_inputs.json").read_text())
    assert grading["task_id"] == env["P8_2_K1A_TASK_ID"]
    assert grading["server_grade"] == env["P8_2_K1A_CANDIDATE_GREEN"]
    assert grading["accepted_capacity_exact"] is True
    assert grading["cpu_bytes_to_use"] == 3444834304
    assert grading["cpu_bytes_to_use_per_rank"] == 430604288
    assert grading["successful_request_count"] == 6
    assert grading["offload_store_evidence_candidate"] is True
    assert grading["offload_restore_evidence_candidate"] is True
    assert grading["runtime_evidence_exact"] is True


def test_r3_r2_is_the_only_current_server_handoff_and_keeps_next_stages_closed() -> None:
    task_id = (
        "p8_2_k1a_r3_r2_deepseek_v4_flash_simple_cpu_offload_store_restore_"
        "2026_0719"
    )
    handoff = HANDOFF.read_text(encoding="utf-8")
    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert f"task_id: {task_id}" in handoff
    for field in (
        "execution_mode: authorized_portable_argv_same_accepted_capacity_single_lifecycle_six_request_mechanism",
        "npu_execution_authorized: true",
        "vllm_server_start_authorized: true",
        "model_requests_authorized: true",
        "formal_model_lifecycle_count_exact: 1",
        "model_request_count_exact: 6",
        "request_retry_count_exact: 0",
        "capacity_search_authorized: false",
        "profiler_authorized: false",
        "result_transfer_authorized: true",
        "next_task_authorized: false",
    ):
        assert field in handoff
    for marker in (
        "ready_p8_2_k1a_r2_allocator_capacity",
        "blocked_p8_2_k1a_r3_source_or_provenance_gate",
        "green_p8_3_i0_r1_unclassified_taxonomy",
        "cpu_bytes_to_use_per_rank=430604288",
        "cpu_bytes_to_use=3444834304",
        "run_deepseek_p8_2_k1a_r3_r2_simple_cpu_offload.sh",
        "candidate_green_p8_2_k1a_r3_r2_simple_cpu_offload_store_restore",
        "不得进入 K2",
        "P8.3-I1",
    ):
        assert marker in handoff

    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    artifacts = readiness["artifacts"]
    acceptance = readiness["acceptance"]
    assert artifacts["current_server_handoff_task"] == task_id
    assert artifacts["next_workload"] == (
        "benchmarks/deepseek_v4_flash/workloads/"
        "p8_2_k1a_r3_simple_cpu_offload_store_restore.yaml"
    )
    assert acceptance["p8_2_k1a_r2_grade"] == (
        "ready_p8_2_k1a_r2_allocator_capacity"
    )
    assert acceptance["p8_2_k1a_r2_allocator_probe_authorized"] is False
    assert acceptance["p8_2_k1a_r3_grade"] == (
        "blocked_p8_2_k1a_r3_source_or_provenance_gate"
    )
    assert acceptance["p8_2_k1a_r3_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r1_grade"] == (
        "red_p8_2_k1a_r3_r1_no_success"
    )
    assert acceptance["p8_2_k1a_r3_r2_execution_authorized"] is True
    assert acceptance["p8_2_k1a_r3_r2_formal_model_lifecycle_count_exact"] == 1
    assert acceptance["p8_2_k1a_r3_r2_model_request_count_exact"] == 6
    assert acceptance["p8_3_i0_r1_grade"] == (
        "green_p8_3_i0_r1_unclassified_taxonomy"
    )
    assert acceptance["current_task_scoped_authorization"] == "P8.2-K1A-R3-R2_only"
    assert acceptance["p8_3_i1_server_execution_authorized"] is False
    assert acceptance["next_task_authorized"] is False


def test_r3_r2_handoff_freezes_all_direct_contract_inputs_without_placeholders() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")
    assert "__R3_" not in handoff
    assert "__REQUEST_" not in handoff
    assert "__MODE_" not in handoff
    assert "__TOP_" not in handoff

    frozen_paths = (
        "benchmarks/deepseek_v4_flash/p8_2_k1a_r3_formal_lifecycle_audit.yaml",
        "benchmarks/deepseek_v4_flash/"
        "p8_2_k1a_r3_r1_provenance_gate_audit.yaml",
        "benchmarks/deepseek_v4_flash/"
        "p8_2_k1a_r3_r2_portable_argv_audit.yaml",
        "benchmarks/deepseek_v4_flash/workloads/"
        "p8_2_k1a_r3_simple_cpu_offload_store_restore.yaml",
        "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py",
        "tools/inference_contracts/canonicalize_server_argv.py",
        "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh",
        "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh",
        "tools/inference_contracts/run_deepseek_p8_2_k1a_r3_simple_cpu_offload.sh",
        "tools/inference_contracts/"
        "run_deepseek_p8_2_k1a_r3_r2_simple_cpu_offload.sh",
        "tests/inference_contracts/test_deepseek_p8_2_k1a_r3_formal_lifecycle.py",
        "tests/inference_contracts/"
        "test_deepseek_p8_2_k1a_r3_r2_portable_argv.py",
    )
    for relative in frozen_paths:
        expected = hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()
        pattern = rf'"{re.escape(relative)}": "{expected}"'
        assert re.search(pattern, handoff), relative
