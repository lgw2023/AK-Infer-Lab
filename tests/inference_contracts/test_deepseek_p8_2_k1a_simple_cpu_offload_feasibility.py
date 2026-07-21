from __future__ import annotations

import json
import hashlib
from pathlib import Path
import subprocess
import sys
import yaml
import os
import shlex


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/p8_2_k1a_simple_cpu_offload_feasibility_audit.yaml"
)
AUDITOR = (
    REPO_ROOT
    / "tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py"
)
OBSERVER = (
    REPO_ROOT
    / "tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py"
)
WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_simple_cpu_offload_store_restore.yaml"
)
RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh"
)
MODE_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh"
)
REQUEST_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py"
)
HANDOFF = REPO_ROOT / "通信模块/docs/developer-to-server.md"
READINESS = REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"


def test_k1a_exact_frozen_source_path_is_a_conditional_candidate():
    assert AUDIT.is_file()
    completed = subprocess.run(
        [
            "python3",
            str(AUDITOR),
            "source-audit",
            "--vllm-repo",
            str(REPO_ROOT / "reference_repos/vllm"),
            "--vllm-ascend-repo",
            str(REPO_ROOT / "reference_repos/vllm-ascend"),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["audit_grade"] == (
        "conditional_p8_2_k1a_simple_cpu_offload_source_candidate"
    )
    assert result["source_hash_gate"] is True
    assert result["ascend_connector_override_present"] is True
    assert result["supports_hma_present"] is True
    assert result["hybrid_multi_group_source_support_present"] is True
    assert result["npu_d2h_h2d_backend_present"] is True
    assert result["formal_k1a_runtime_allowed_after_server_probe"] is True
    assert result["runtime_evidence_accepted"] is False
    assert result["performance_reference_accepted"] is False


def test_k1a_installed_source_tree_must_match_all_runtime_files(tmp_path: Path):
    vllm_root = tmp_path / "vllm_root"
    ascend_root = tmp_path / "ascend_root"
    specs = (
        (
            REPO_ROOT / "reference_repos/vllm",
            "0decac0d96c42b49572498019f0a0e3600f50398",
            vllm_root,
            (
                "vllm/distributed/kv_transfer/kv_connector/v1/simple_cpu_offload_connector.py",
                "vllm/v1/simple_kv_offload/manager.py",
                "vllm/v1/simple_kv_offload/metadata.py",
                "vllm/v1/simple_kv_offload/worker.py",
            ),
        ),
        (
            REPO_ROOT / "reference_repos/vllm-ascend",
            "5f6faa0cb8830f667266f3b8121cd1383606f2a1",
            ascend_root,
            (
                "vllm_ascend/distributed/kv_transfer/__init__.py",
                "vllm_ascend/distributed/kv_transfer/kv_pool/simple_cpu_offload/simple_cpu_offload_connector.py",
                "vllm_ascend/simple_kv_offload/worker.py",
                "vllm_ascend/simple_kv_offload/copy_backend.py",
                "vllm_ascend/simple_kv_offload/npu_mem_ops.py",
            ),
        ),
    )
    for repo, commit, destination, relative_paths in specs:
        for relative_path in relative_paths:
            target = destination / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(
                subprocess.run(
                    ["git", "-C", str(repo), "show", f"{commit}:{relative_path}"],
                    check=True,
                    capture_output=True,
                ).stdout
            )

    completed = subprocess.run(
        [
            "python3",
            str(AUDITOR),
            "installed-source-audit",
            "--vllm-root",
            str(vllm_root),
            "--vllm-ascend-root",
            str(ascend_root),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["audit_grade"] == (
        "conditional_p8_2_k1a_simple_cpu_offload_source_candidate"
    )
    assert result["source_hash_gate"] is True
    assert len(result["source_inventory"]) == 9


def test_k1a_runtime_probe_is_import_registration_and_config_only(tmp_path: Path):
    fake_python = tmp_path / "runtime-python"
    payload = {
        "kv_transfer_config": {
            "kv_connector": "SimpleCPUOffloadConnector",
            "kv_role": "kv_both",
            "kv_connector_extra_config": {
                "cpu_bytes_to_use": 274877906944,
                "cpu_bytes_to_use_per_rank": 34359738368,
                "lazy_offload": False,
            },
        },
        "registry_module": (
            "vllm_ascend.distributed.kv_transfer.kv_pool."
            "simple_cpu_offload.simple_cpu_offload_connector"
        ),
        "registry_class": "AscendSimpleCPUOffloadConnector",
        "connector_import": "success",
        "worker_import": "success",
        "copy_backend_import": "success",
        "ascend_connector_inherits_upstream": True,
        "npu_started": False,
        "vllm_server_started": False,
        "model_request_sent": False,
    }
    fake_python.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        f"payload = {payload!r}\n"
        "print('P8K1A_RUNTIME_JSON=' + json.dumps(payload, sort_keys=True))\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    completed = subprocess.run(
        [
            "python3",
            str(AUDITOR),
            "runtime-import-probe",
            "--runtime-python",
            str(fake_python),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["subprocess_exit"] == 0
    assert result["probe"] == payload
    assert result["npu_started"] is False
    assert result["vllm_server_started"] is False
    assert result["model_request_sent"] is False

    source = AUDITOR.read_text(encoding="utf-8")
    for marker in (
        "KVTransferConfig",
        "inspect.signature",
        "register_connector()",
        "KVConnectorFactory.get_connector_class_by_name",
        "AscendSimpleCPUOffloadConnector",
        "SimpleCPUOffloadNPUWorker",
        "NPUDmaCopyBackend",
        '"poll_method_owner"',
        '"launch_copy_parameters"',
    ):
        assert marker in source


def test_k1a_trace_summary_requires_real_store_and_restore_on_every_worker():
    sys.path.insert(0, str(REPO_ROOT))
    from tools.inference_contracts.p8_2_k1a_simple_cpu_offload_observer import (
        summarize_trace_rows,
    )

    rows = []
    for pid in (101, 102):
        rows.extend(
            [
                {
                    "event": "copy_thread_started",
                    "pid": pid,
                },
                {
                    "event": "device_copy_submitted",
                    "direction": "d2h",
                    "pid": pid,
                    "event_idx": 3,
                    "block_count": 8,
                    "byte_count": 4096,
                },
                {"event": "device_copy_enqueued", "direction": "d2h", "pid": pid},
                {"event": "copy_blocks_entered", "direction": "d2h", "pid": pid},
                {"event": "copy_blocks_returned", "direction": "d2h", "pid": pid},
                {
                    "event": "transfer_poll_entered",
                    "direction": "d2h",
                    "pid": pid,
                    "pending_event_count": 1,
                    "copy_thread_alive": True,
                },
                {
                    "event": "transfer_completed",
                    "direction": "d2h",
                    "pid": pid,
                    "event_hwm": 3,
                },
                {
                    "event": "device_copy_submitted",
                    "direction": "h2d",
                    "pid": pid,
                    "event_idx": 1,
                    "block_count": 4,
                    "byte_count": 2048,
                },
                {"event": "device_copy_enqueued", "direction": "h2d", "pid": pid},
                {"event": "copy_blocks_entered", "direction": "h2d", "pid": pid},
                {"event": "copy_blocks_returned", "direction": "h2d", "pid": pid},
                {
                    "event": "transfer_poll_entered",
                    "direction": "h2d",
                    "pid": pid,
                    "pending_event_count": 1,
                    "copy_thread_alive": True,
                },
                {
                    "event": "transfer_completed",
                    "direction": "h2d",
                    "pid": pid,
                    "event_hwm": 1,
                },
            ]
        )
    rows.extend(
        [
            {
                "event": "store_event_completed",
                "direction": "d2h",
                "pid": 90,
                "event_idx": 3,
                "block_count": 8,
            },
            {
                "event": "cpu_hit_matched",
                "direction": "h2d",
                "pid": 90,
                "request_id": "lifecycle_01_restore_follower",
                "num_new_tokens": 16384,
            },
            {
                "event": "load_scheduled",
                "direction": "h2d",
                "pid": 90,
                "request_id": "lifecycle_01_restore_follower",
                "block_count": 256,
            },
            {
                "event": "load_request_completed",
                "direction": "h2d",
                "pid": 90,
                "request_id": "lifecycle_01_restore_follower",
            },
        ]
    )

    summary = summarize_trace_rows(
        rows,
        expected_world_size=2,
        restore_request_suffix="restore_follower",
    )
    assert summary["d2h_store_complete"] is True
    assert summary["h2d_restore_complete"] is True
    assert summary["d2h_worker_count"] == 2
    assert summary["h2d_worker_count"] == 2
    assert summary["d2h_bytes_total"] == 8192
    assert summary["h2d_bytes_total"] == 4096
    assert summary["restore_cpu_hit_tokens_max"] == 16384
    assert summary["runtime_evidence_exact"] is True


def test_k1a_observer_preserves_the_frozen_launch_signature_without_wait_event():
    source = OBSERVER.read_text(encoding="utf-8")
    observed_launch = source[source.index("def observed_launch(") :]
    observed_launch = observed_launch[: observed_launch.index("original_poll =")]
    assert "wait_event" not in observed_launch
    assert "events_list,\n            )" in observed_launch


def test_k1a_observer_covers_the_background_copy_pipeline_without_swallowing_errors():
    source = OBSERVER.read_text(encoding="utf-8")
    for marker in (
        "copy_thread_started",
        "copy_thread_failed",
        "copy_thread_exited",
        "device_copy_enqueued",
        "copy_blocks_entered",
        "copy_blocks_returned",
        "copy_blocks_failed",
        "transfer_poll_entered",
        "transfer_poll_returned",
        "copy_backend_module.copy_blocks = observed_copy_blocks",
        "NPUDmaCopyBackend._copy_loop = observed_copy_loop",
    ):
        assert marker in source
    assert source.count("raise\n") >= 4


def test_k1a_workload_freezes_one_six_request_store_pressure_restore_lifecycle():
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    assert workload["task_id"] == (
        "p8_2_k1a_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0717"
    )
    assert workload["stage_contract"] == {
        "stage": "P8.2-K1A",
        "mode": "conditional_simple_cpu_offload_real_store_restore_mechanism",
        "claim_boundary": (
            "deepseek_tp8_ep_mtp_single_lifecycle_d2h_store_h2d_restore_"
            "mechanism_only"
        ),
        "performance_reference_authorized": False,
        "optimization_claim_authorized": False,
    }
    runtime = workload["runtime_fixed"]
    assert runtime["kv_connector"] == "SimpleCPUOffloadConnector"
    assert runtime["cpu_bytes_to_use"] == 274877906944
    assert runtime["cpu_bytes_to_use_per_rank"] == 34359738368
    assert runtime["lazy_offload"] is False
    assert runtime["enable_prefix_caching"] is True
    assert runtime["num_speculative_tokens"] == 1

    plan = workload["request_plan"]
    assert plan["lifecycle_count"] == 1
    assert plan["request_count"] == 6
    assert [row["role"] for row in plan["sequence"]] == [
        "warmup",
        "prime",
        "pressure",
        "restore_follower",
        "repeat_follower",
        "isolated_control",
    ]
    assert [row["context_tokens"] for row in plan["sequence"]] == [
        4096,
        32768,
        131072,
        32768,
        32768,
        32768,
    ]
    assert plan["request_retries"] == 0
    assert workload["host_memory_gate"]["mem_available_bytes_min"] == 412316860416
    assert workload["evidence_contract"]["world_size_exact"] == 8
    assert workload["evidence_contract"]["d2h_positive_bytes_all_workers"] is True
    assert workload["evidence_contract"]["h2d_positive_bytes_all_workers"] is True
    assert workload["execution_state"]["npu_execution_authorized"] is True
    assert workload["execution_state"]["next_task_authorized"] is False
    assert RUNNER.is_file()
    assert MODE_RUNNER.is_file()


def test_k1a_grading_separates_store_only_yellow_from_store_restore_green():
    sys.path.insert(0, str(REPO_ROOT))
    from tools.inference_contracts.run_deepseek_p8_2_k1a_simple_cpu_offload import (
        grade_k1a_evidence,
    )

    roles = (
        ("warmup", 4096),
        ("prime", 32768),
        ("pressure", 131072),
        ("restore_follower", 32768),
        ("repeat_follower", 32768),
        ("isolated_control", 32768),
    )
    rows = [
        {
            "request_id": f"lifecycle_01_{role}",
            "k1a_role": role,
            "status": "success",
            "http_status": 200,
            "prompt_tokens": context_tokens,
            "context_tokens": context_tokens,
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
            "request_body_sha256": str(index).zfill(64),
            "ttft_ms": 1.0,
            "e2el_ms": 2.0,
        }
        for index, (role, context_tokens) in enumerate(roles, start=1)
    ]
    restore = rows[3]
    restore["status"] = "failed"
    restore["prefix_evidence_ok"] = False
    restore["checks"] = {
        "server_alive": True,
        "health_after_200": True,
        "queue_idle_after": True,
        "prefix_evidence_ok": False,
    }
    common = {
        "request_rows": rows,
        "cleanup": "clean",
        "connector_resolution_ok": True,
        "repair_diagnostic_ok": True,
        "host_memory_gate_ok": True,
    }
    store_only = grade_k1a_evidence(
        **common,
        trace_summary={
                "d2h_store_complete": True,
                "d2h_async_copy_pipeline_exact": True,
                "h2d_restore_complete": False,
            "runtime_evidence_exact": False,
        },
    )
    assert store_only["server_grade"] == "yellow_p8_2_k1a_store_only_no_restore"
    assert store_only["successful_request_count"] == 6
    assert store_only["request_evidence_exact"] is True
    assert store_only["request_status_mechanism_coupling_detected"] is True
    assert store_only["failed_mechanism_predicates"] == ["prefix_evidence_ok"]
    assert store_only["offload_store_evidence_candidate"] is True
    assert store_only["offload_restore_evidence_candidate"] is False

    green = grade_k1a_evidence(
        **common,
        trace_summary={
            "d2h_store_complete": True,
            "h2d_restore_complete": True,
            "runtime_evidence_exact": True,
        },
    )
    assert green["server_grade"] == (
        "candidate_green_p8_2_k1a_simple_cpu_offload_store_restore"
    )
    assert green["successful_request_count"] == 6
    assert green["request_evidence_exact"] is True
    assert green["offload_store_evidence_candidate"] is True
    assert green["offload_restore_evidence_candidate"] is True
    assert green["performance_reference_accepted"] is False


def test_k1a_mode_runner_freezes_the_explicit_connector_server_argv(tmp_path: Path):
    env = os.environ.copy()
    env["P8_2_K1A_MODE_AUDIT_ONLY"] = "1"
    completed = subprocess.run(
        ["bash", str(MODE_RUNNER), str(tmp_path / "result")],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    audit = dict(
        line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line
    )
    assert audit["task_id"] == (
        "p8_2_k1a_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0717"
    )
    argv = shlex.split(audit["server_command"])
    assert audit["server_command_identity_schema"] == (
        "ak_infer_lab_server_argv_v1"
    )
    assert audit["server_command_sha256"] == (
        "d769e0b0fb9c49759b62167ea3bc07996baa7ade0d8d86633d626ea1f07da134"
    )
    assert argv.count("--kv-transfer-config") == 1
    config = json.loads(argv[argv.index("--kv-transfer-config") + 1])
    assert config == {
        "kv_connector": "SimpleCPUOffloadConnector",
        "kv_role": "kv_both",
        "kv_connector_extra_config": {
            "cpu_bytes_to_use": 274877906944,
            "cpu_bytes_to_use_per_rank": 34359738368,
            "lazy_offload": False,
        },
    }
    for flag in (
        "--enable-prefix-caching",
        "--enable-chunked-prefill",
        "--enable-expert-parallel",
        "--speculative-config",
        "--compilation-config",
    ):
        assert argv.count(flag) == 1
    assert "--disable-hybrid-kv-cache-manager" not in argv
    assert "--no-enable-prefix-caching" not in argv
    assert audit["request_count"] == "6"
    assert audit["lifecycle_count"] == "1"
    assert audit["observer_mode"] == "observe_only_no_decision_or_copy_mutation"

    source = MODE_RUNNER.read_text(encoding="utf-8")
    assert source.index('runtime_patch_self_test.txt') < source.index(
        'export P8_2_K1A_TRANSFER_TRACE_DIR="${TRACE_DIR}"'
    )


def test_k1a_preparer_freezes_six_unique_content_free_request_bodies(tmp_path: Path):
    source = tmp_path / "source_payload.json"
    source.write_text(
        json.dumps({"prompt": list(range(4096))}, separators=(",", ":")),
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "artifact"
    subprocess.run(
        [
            "python3",
            str(REQUEST_RUNNER),
            "prepare",
            "--source-payload",
            str(source),
            "--artifact-dir",
            str(artifact_dir),
            "--model-name",
            "deepseek-v4-flash-w8a8-mtp",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    manifest = json.loads(
        (artifact_dir / "request_body_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["request_count"] == 6
    assert manifest["role_order"] == [
        "warmup",
        "prime",
        "pressure",
        "restore_follower",
        "repeat_follower",
        "isolated_control",
    ]
    assert manifest["expected_restore_prefix_hit_tokens"] == 16384
    assert manifest["cross_group_lcp_less_than_block_size"] is True
    assert manifest["body_hashes_unique"] is True
    assert manifest["generated_text_retained"] is False
    assert manifest["token_ids_retained"] is False
    for record in manifest["records"]:
        body_path = artifact_dir / record["body_relative_path"]
        body = json.loads(body_path.read_text(encoding="utf-8"))
        assert len(body["prompt"]) == record["context_tokens"]
        assert hashlib.sha256(body_path.read_bytes()).hexdigest() == record[
            "request_body_sha256"
        ]


def test_k1a_r5_f0_feasibility_is_the_only_current_server_handoff():
    handoff = HANDOFF.read_text(encoding="utf-8")
    task_id = (
        "p8_2_k1a_r5_f1_pressure_window_conditional_l2_2026_0721"
    )
    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert f"task_id: {task_id}" in handoff
    assert (
        "execution_mode: authorized_offline_raw_pressure_window_then_"
        "conditional_one_fixed_lifecycle"
        in handoff
    )
    for field in (
        "server_sync_review_authorized: true",
        "npu_execution_authorized: conditional",
        "vllm_server_start_authorized: conditional",
        "model_requests_authorized: conditional",
        "keep_alive_stop_and_restore_authorized: conditional",
        "profiler_authorized: false",
        "result_transfer_authorized: true",
        "next_task_authorized: false",
        "formal_model_lifecycle_count_max: 1",
        "model_request_count_max: 4",
        "capacity_search_authorized: false",
    ):
        assert field in handoff
    for marker in (
        "parent_server_grade=red_p8_2_k1a_r5_l1_r1_cpu_target_lost",
        "parent_successful_request_count=3",
        "run_deepseek_p8_2_k1a_r5_f1_pressure_window.sh",
        "candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout",
        "pressure_request_count_exact: 1",
        "K2",
        "P8.3-I1",
    ):
        assert marker in handoff

    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    artifacts = readiness["artifacts"]
    assert artifacts["current_server_handoff_task"] == task_id
    assert artifacts["next_workload"] == (
        "workloads/p8_2_k1a_r5_f1_pressure_window_conditional_lifecycle.yaml"
    )
    acceptance = readiness["acceptance"]
    assert acceptance["p8_2_k1_feasibility_grade"] == (
        "blocked_p8_2_k1_frozen_stack_import_incompatible"
    )
    assert acceptance["p8_2_k1a_feasibility_grade"] == (
        "conditional_p8_2_k1a_simple_cpu_offload_source_candidate"
    )
    assert acceptance["p8_2_k1a_runtime_grade"] == (
        "red_p8_2_k1a_simple_cpu_offload_no_success"
    )
    assert acceptance["p8_2_k1a_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r1_allocator_probe_authorized"] is False
    assert acceptance["p8_2_k1a_r2_grade"] == (
        "ready_p8_2_k1a_r2_allocator_capacity"
    )
    assert acceptance["p8_2_k1a_r2_allocator_probe_authorized"] is False
    assert acceptance["p8_2_k1a_r3_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_r1_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r4_offline_closeout_authorized"] is True
    assert acceptance["p8_2_k1a_r4_npu_execution_authorized"] is False
    assert acceptance["p8_2_execution_authorized"] is False
    assert acceptance["p8_2_parent_auto_advance_authorized"] is False
    assert acceptance["current_task_scoped_authorization"] == (
        "P8.2-K1A-R5-F1_offline_first_then_at_most_one_fixed_non_search_lifecycle"
    )
    assert acceptance["p8_3_technical_dependency_on_k1a"] is False
    assert acceptance["p8_3_i0_local_planning_ready"] is True
    assert acceptance["p8_3_i0_local_implementation_status"] == (
        "completed_green_inventory_taxonomy_followup_prepared"
    )
    assert acceptance["p8_3_i0_server_checkpoint_inventory_authorized"] is False
    assert acceptance["p8_3_i0_r1_grade"] == (
        "green_p8_3_i0_r1_unclassified_taxonomy"
    )
    assert acceptance["p8_3_i0_r1_existing_inventory_taxonomy_authorized"] is False
    assert acceptance["p8_3_i1_server_execution_authorized"] is False
    assert acceptance["next_task_authorized"] is False
