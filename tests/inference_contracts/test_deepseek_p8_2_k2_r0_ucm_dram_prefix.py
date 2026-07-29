from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.inference_contracts.run_deepseek_p8_2_k2_r0_ucm_dram_prefix import (
    TASK_ID,
    finalize,
    package,
)


ROOT = Path(__file__).resolve().parents[2]
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    / "p8_2_k2_r0_ucm_dram_external_prefix_path.yaml"
)
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    / "p8_2_k2_r0_ucm_dram_external_prefix_path_audit.yaml"
)
SERVER_DRIVER = (
    ROOT
    / "tools/inference_contracts/"
    / "run_deepseek_p8_2_k2_r0_server_task.sh"
)
CMAKE_WRAPPER = (
    ROOT
    / "tools/inference_contracts/"
    / "run_ucm_cmake_python_wrapper.sh"
)
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"
READINESS = (
    ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
)


def _request(role: str, delta: dict[str, float]) -> dict:
    return {
        "request_role": role,
        "status": "success",
        "context_tokens": 4096 if role == "warmup" else 32768,
        "output_tokens": 64,
        "http_status": 200,
        "prompt_tokens": 4096 if role == "warmup" else 32768,
        "generated_token_count": 64,
        "ttft_ms": 100.0,
        "tpot_ms": 10.0,
        "itl_p95_ms": 12.0,
        "e2el_ms": 730.0,
        "counter_delta": delta,
    }


def _write_no_touch_recovery(artifact: Path) -> None:
    (artifact / "resource_recovery_summary.json").write_text(
        json.dumps(
            {
                "stopped_card_ids": [],
                "restored_card_ids": [],
                "keep_alive_restored_exact": True,
                "port_7000_listener_count": 0,
                "vllm_residual_process_count": 0,
                "tracked_worktree_clean": True,
                "npu_stop_attempted": False,
                "formal_model_lifecycle_started": False,
                "preflight_failed_before_npu_touch": True,
                "dependency_exit_code": 1,
                "startup_capacity_exit_code": 1,
            }
        ),
        encoding="utf-8",
    )


def test_contract_targets_real_ucm_path_without_performance_precondition() -> None:
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    assert workload["task_id"] == TASK_ID
    assert workload["ucm_store"]["pipeline"] == "Cache|Posix"
    assert workload["ucm_store"]["dram_cache_buffer_capacity_gb"] == 16
    assert workload["ucm_store"]["startup_geometry"][
        "run03_16gib_buffer_number"
    ] == 2592
    assert workload["ucm_store"]["startup_geometry"][
        "required_buffer_number"
    ] == 2048
    assert workload["ucm_store"]["use_layerwise"] is True
    assert workload["implementation_acceptance"][
        "latency_sign_is_not_a_path_gate"
    ] is True
    assert audit["developer_decision"][
        "performance_benefit_is_not_an_implementation_prerequisite"
    ] is True
    assert audit["pinned_ucm_source"]["commit"] == (
        "01cbf9b71892c88319862fa57f195b0bef93fa6f"
    )
    assert readiness["artifacts"]["current_server_handoff_task"] == (
        "p8_2_k2_r0_run03_fawa_startup_attribution_2026_0729_run01"
    )
    assert readiness["artifacts"]["next_workload"].endswith(
        "p8_2_k2_r0_run03_fawa_startup_attribution.yaml"
    )
    assert readiness["acceptance"]["p8_2_k1a_r5_f1_r17_grade"] == (
        "green_p8_2_k1a_r5_f1_r17_restore_h2d_mechanism_closed"
    )
    assert readiness["acceptance"]["p8_2_k2_r0_execution_authorized"] is True


def test_finalize_accepts_dram_hit_and_h2d_load_independent_of_latency(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "result"
    runtime = artifact / "runtime"
    runtime.mkdir(parents=True)
    rows = [
        _request("warmup", {}),
        _request(
            "prime",
            {
                "ucm:save_bytes_total": 4096,
                "ucm:cache_dump_bytes_total": 4096,
            },
        ),
        _request(
            "follower",
            {
                "ucm:ucm_hit_tokens_total": 32768,
                "ucm:gpu_hbm_hit_tokens_total": 0,
                "ucm:cache_lookup_hit_blocks_total": 256,
                "ucm:load_bytes_total": 4096,
                "ucm:cache_load_bytes_total": 4096,
                "ucm:posix_s2h_bytes_total": 0,
            },
        ),
    ]
    (runtime / "request_results.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    (runtime / "vllm_server.log").write_text(
        "request_id: bounded, hit hbm: 0, hit external: 256\n",
        encoding="utf-8",
    )
    (artifact / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
    (artifact / "dependency_and_environment_summary.json").write_text(
        '{"dependency_status":"ready"}\n', encoding="utf-8"
    )
    (artifact / "startup_capacity_summary.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "pre_npu_capacity_gate_passed": True,
                "configured_cache_buffer_gib_per_rank": 16,
                "configured_buffer_number": 2592,
                "required_buffer_number": 2048,
            }
        ),
        encoding="utf-8",
    )
    (runtime / "server_pid.txt").write_text("123\n", encoding="utf-8")
    (runtime / "server_ready_exit_code.txt").write_text("0\n", encoding="utf-8")
    (artifact / "resource_recovery_summary.json").write_text(
        json.dumps(
            {
                "stopped_card_ids": list(range(8)),
                "restored_card_ids": list(range(8)),
                "keep_alive_restored_exact": True,
                "port_7000_listener_count": 0,
                "vllm_residual_process_count": 0,
                "tracked_worktree_clean": True,
            }
        ),
        encoding="utf-8",
    )
    grade = finalize(artifact)
    assert grade == "implemented_p8_2_k2_r0_ucm_dram_external_prefix_path"
    summary = json.loads(
        (artifact / "ucm_path_summary.json").read_text(encoding="utf-8")
    )
    assert summary["mechanism_implemented"] is True
    assert summary["posix_read_absent_on_follower"] is True
    assert summary["performance_benefit_required_for_mechanism_acceptance"] is False
    package(artifact)
    manifest = json.loads(
        (artifact / "candidate_manifest.server_local.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["payload_file_count"] == 11
    assert manifest["transfer_file_count"] == 12
    assert manifest["manifest_bytes"] == (
        artifact / "candidate_manifest.server_local.json"
    ).stat().st_size
    assert manifest["transfer_total_bytes"] <= 71680


def test_finalize_records_exact_preflight_failure_before_npu_touch(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "result"
    artifact.mkdir()
    (artifact / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
    (artifact / "dependency_and_environment_summary.json").write_text(
        '{"dependency_status":"dependency_failed"}\n',
        encoding="utf-8",
    )
    _write_no_touch_recovery(artifact)
    grade = finalize(artifact)
    assert grade == "blocked_p8_2_k2_r0_dependency_preflight"
    grading = json.loads(
        (artifact / "grading_summary.json").read_text(encoding="utf-8")
    )
    assert grading["resource_recovery_exact"] is True
    assert grading["resource_state"] == (
        "dependency_preflight_failed_before_npu_touch"
    )


def test_server_driver_repairs_poisoned_dependency_state_atomically() -> None:
    text = SERVER_DRIVER.read_text(encoding="utf-8")
    assert "EXPECTED_RUN_LABEL=${TASK_ID}_run03" in text
    assert "quarantine_path" in text
    assert "validate_nfs_creation_identity" in text
    assert "tree_owned_by_current_user_and_group" in text
    assert "global_git_safe_directory_mutated" in text
    assert "dependency_log_truncated_before_attempt" in text
    assert "install_marker_written_after_import_probe_only" in text
    assert "git config --global" not in text
    marker_write = text.index('mv -- "${marker_tmp}"')
    import_probe = text.index('ucm_import_probe "${env_stage}/bin/python"')
    assert import_probe < marker_write
    assert "UCM_CACHE_BUFFER_GIB=16" in text
    assert "UCM_OBSERVED_SHARD_SIZE_BYTES=6627328" in text
    assert "UCM_LOAD_EXCLUSIVE_BUFFER_NUMBER=1024" in text
    assert "write_startup_capacity_summary" in text
    wrapper = CMAKE_WRAPPER.read_text(encoding="utf-8")
    assert "-DPYTHON_EXECUTABLE=*" in wrapper
    assert "-DPython_EXECUTABLE=${UCM_BUILD_PYTHON}" in wrapper


def test_finalize_separates_capacity_preflight_from_dependency_failure(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "result"
    artifact.mkdir()
    (artifact / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
    (artifact / "dependency_and_environment_summary.json").write_text(
        '{"dependency_status":"ready"}\n',
        encoding="utf-8",
    )
    (artifact / "startup_capacity_summary.json").write_text(
        '{"status":"insufficient","pre_npu_capacity_gate_passed":false}\n',
        encoding="utf-8",
    )
    _write_no_touch_recovery(artifact)
    recovery = json.loads(
        (artifact / "resource_recovery_summary.json").read_text(encoding="utf-8")
    )
    recovery["dependency_exit_code"] = 0
    recovery["startup_capacity_exit_code"] = 1
    (artifact / "resource_recovery_summary.json").write_text(
        json.dumps(recovery), encoding="utf-8"
    )
    grade = finalize(artifact)
    assert grade == "blocked_p8_2_k2_r0_startup_capacity_preflight"
    grading = json.loads(
        (artifact / "grading_summary.json").read_text(encoding="utf-8")
    )
    assert grading["resource_state"] == (
        "startup_capacity_preflight_failed_before_npu_touch"
    )


def test_finalize_classifies_lifecycle_startup_buffer_failure(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "result"
    runtime = artifact / "runtime"
    runtime.mkdir(parents=True)
    (artifact / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
    (artifact / "dependency_and_environment_summary.json").write_text(
        '{"dependency_status":"ready"}\n',
        encoding="utf-8",
    )
    (artifact / "startup_capacity_summary.json").write_text(
        '{"status":"ready","pre_npu_capacity_gate_passed":true}\n',
        encoding="utf-8",
    )
    (runtime / "server_pid.txt").write_text("123\n", encoding="utf-8")
    (runtime / "server_ready_exit_code.txt").write_text("1\n", encoding="utf-8")
    (runtime / "vllm_server.log").write_text(
        "Worker failed: too small buffer(8589934592) on shard(6627328)\n",
        encoding="utf-8",
    )
    (artifact / "resource_recovery_summary.json").write_text(
        json.dumps(
            {
                "stopped_card_ids": list(range(8)),
                "restored_card_ids": list(range(8)),
                "keep_alive_restored_exact": True,
                "port_7000_listener_count": 0,
                "vllm_residual_process_count": 0,
                "tracked_worktree_clean": True,
            }
        ),
        encoding="utf-8",
    )
    grade = finalize(artifact)
    assert grade == "blocked_p8_2_k2_r0_lifecycle_startup"
    startup = json.loads(
        (artifact / "startup_failure_summary.json").read_text(encoding="utf-8")
    )
    assert startup["startup_class"] == "ucm_cache_buffer_too_small"
    assert startup["reported_buffer_number"] == 1296


def test_handoff_is_current_only_and_operationally_complete() -> None:
    text = HANDOFF.read_text(encoding="utf-8")
    assert text.count("## 当前唯一服务器动作：") == 1
    assert TASK_ID in text
    assert "01cbf9b71892c88319862fa57f195b0bef93fa6f" in text
    assert (
        "run_deepseek_p8_2_k2_r0_run03_fawa_"
        "startup_attribution_server_task.sh"
    ) in text
    assert "本轮**禁止执行**" in text
    assert "npu_stop.sh 0 1 2 3 4 5 6 7" in text
    assert "npu_keep_alive.sh 0 1 2 3 4 5 6 7" in text
    assert "不评价 external KV 方案性能" in text
    assert "npu_execution_authorized: false" in text
    assert "run04_authorized: false" in text
    assert "parent_and_source_mutation_authorized: false" in text
    assert "transfer_method_selected: false" in text
