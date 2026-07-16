import hashlib
import os
from pathlib import Path
import subprocess

import pytest
import yaml

from tools.inference_contracts.prepare_deepseek_p8_1_r1_observe_matrix import (
    FROZEN_BODY_SHA256,
    build_body_relationship_summary,
)
from tools.inference_contracts.finalize_deepseek_p8_1_r1_observe_only_matrix import (
    CANDIDATE_GREEN,
    grade_r1_replay,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PARENT_WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_1_vllm_ascend_official_mtp_observe_only_matrix.yaml"
)
R1_WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_1_r1_vllm_ascend_official_mtp_observe_only_matrix.yaml"
)
PARENT_RUNNER = (
    REPO_ROOT / "tools/inference_contracts/run_deepseek_p8_1_observe_only_matrix.sh"
)
R1_RUNNER = (
    REPO_ROOT / "tools/inference_contracts/run_deepseek_p8_1_r1_observe_only_matrix.sh"
)


def test_parent_matrix_is_closed_as_developer_reviewed_yellow() -> None:
    workload = yaml.safe_load(PARENT_WORKLOAD.read_text(encoding="utf-8"))

    result = workload["execution_result"]
    assert result["server_grade"] == "yellow_p8_1_matrix_trace_invalid"
    assert result["developer_grade"] == "yellow_p8_1_matrix_trace_invalid"
    assert result["successful_requests"] == "6_of_6"
    assert result["shared_prefix_slot"] == "medium_shared_follower"
    assert result["shared_prefix_token_lcp"] == 58880
    assert result["shared_prefix_expected_hit_tokens"] == 49152
    assert result["shared_prefix_actual_hit_tokens"] == 0
    assert result["other_five_actual_hit_tokens"] == [0, 0, 0, 0, 0]
    assert result["mtp_health_queue_trace_replay_join_ok"] is True
    assert result["cleanup"] == "clean"
    assert result["result_package"] == {"files": 13, "bytes": 17195}
    assert result["developer_received_path"].endswith(
        "p8_1_official_mtp_observe_only_matrix_20260716_yellow"
    )
    assert result["generated_text_or_token_ids_received"] is False
    assert result["cause_proven"] is False

    assert workload["execution_state"] == {
        "status": "completed_developer_reviewed_yellow",
        "server_handoff": "historical",
        "server_result": "received_and_reviewed",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
        "result_transfer_authorized": False,
        "standing_npu_and_vllm_consumption_authorization": True,
    }


def test_r1_workload_replays_the_same_matrix_with_the_full_r2_repair() -> None:
    workload = yaml.safe_load(R1_WORKLOAD.read_text(encoding="utf-8"))

    assert workload["task_id"] == (
        "p8_1_r1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0717"
    )
    assert workload["stage_contract"] == {
        "stage": "P8.1-R1",
        "mode": "vllm_ascend_observe_only_bounded_matrix_r2_repair_replay",
        "claim_boundary": (
            "official_mtp_shared_prefix_observe_only_trace_repair_replay_not_performance"
        ),
        "performance_comparison_authorized": False,
        "p8_2_execution_authorized": False,
    }
    assert workload["parent_lineage"]["task_id"] == (
        "p8_1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0716"
    )
    assert workload["parent_lineage"]["developer_grade"] == (
        "yellow_p8_1_matrix_trace_invalid"
    )
    assert workload["parent_lineage"]["only_failed_gate"] == (
        "medium_shared_follower_prefix_hit_0_expected_49152"
    )
    assert workload["repair_hypothesis"]["cause_proven_before_replay"] is False

    assert workload["runtime_fixed"] == {
        "model_path": "/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp",
        "max_model_len": 135168,
        "max_num_batched_tokens": 4096,
        "max_num_seqs": 1,
        "block_size": 128,
        "tensor_parallel_size": 8,
        "enable_expert_parallel": True,
        "quantization": "ascend",
        "enable_chunked_prefill": True,
        "enable_prefix_caching": True,
        "speculative_method": "mtp",
        "num_speculative_tokens": 1,
        "cudagraph_mode": "FULL_DECODE_ONLY",
    }

    repair = workload["source_and_repair_gate"]
    assert repair["full_p6_3b_r2_task_local_repair_required"] is True
    assert repair["runtime_implementation_sha256"] == (
        "6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c"
    )
    assert repair["deferred_loader_sha256"] == (
        "9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631"
    )
    assert repair["mtp_overlay_patch_sha256"] == (
        "75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1"
    )
    assert repair["hybrid_manager_overlay_patch_sha256"] == (
        "cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e"
    )
    assert repair["deferred_install_overlay_patch_sha256"] == (
        "ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b"
    )
    assert repair["runtime_diagnostic_hard_gate"] is True
    assert repair["base_environment_or_site_packages_mutation"] is False

    frozen_hashes = workload["request_plan"]["frozen_request_body_sha256"]
    assert frozen_hashes == {
        "short_isolated_a": "7d59f274cf53019b221e5d4add7628551bed5a910255e267f52719dac41f2b21",
        "medium_shared_prime": "1ff2523c2cb5172f5ce0ba9ce5bde2a66c9ed3d20e73cb8715fbd36841f39496",
        "medium_shared_follower": "46363c923be52449e803488bec3f7691a620cd31248ac3b62304407d35485169",
        "long_isolated_a": "e5d848816122c3d9f1dba0e7149294017471fc4ebfabfe6a69402666b92f2857",
        "short_isolated_b": "c36dc099ab384fb8da5bff881473af45a75f918bf59104db5828a8302d2aecd5",
        "long_isolated_b": "820a663bf3335849673f508fde484a0a84c17ebc16b513b2be4be1e6508eeb88",
    }
    assert workload["request_plan"]["request_count"] == 6
    assert workload["request_plan"]["lifecycle_count"] == 1
    assert workload["request_plan"]["order_and_bodies_identical_to_parent"] is True

    controls = workload["protocol_and_environment_controls"]
    assert controls["localhost_no_proxy_explicit"] is True
    assert controls["lowercase_no_proxy_required"] is True
    assert controls["uppercase_no_proxy_required"] is True
    assert controls["prefix_cache_retention_interval"] == "explicitly_unset"
    assert workload["runner"]["expected_server_command_sha256"] == (
        "370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19"
    )
    for path_key, hash_key in (
        ("path", "sha256"),
        ("preparer", "preparer_sha256"),
        ("finalizer", "finalizer_sha256"),
    ):
        artifact = REPO_ROOT / workload["runner"][path_key]
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == (
            workload["runner"][hash_key]
        )

    assert workload["acceptance"]["server_candidate_green_grade"] == (
        "candidate_green_p8_1_r1_official_mtp_observe_only_matrix"
    )
    assert workload["stop_policy"]["stop_on_first_request_failure"] is True
    assert workload["stop_policy"]["no_retry"] is True
    assert workload["stop_policy"]["no_profiler_or_offload"] is True
    assert workload["stop_policy"]["no_p8_2_p7_or_p9"] is True
    assert workload["execution_state"]["npu_execution_authorized"] is True
    assert workload["execution_state"]["next_task_authorized"] is True
    assert workload["execution_state"]["result_transfer_authorized"] is False


def test_r1_body_gate_freezes_hashes_and_emits_only_sanitized_relationships() -> None:
    records = [
        {
            "order": index,
            "slot_id": slot_id,
            "input_tokens": 65536 if "medium" in slot_id else 4096,
            "body_bytes": 1234 + index,
            "body_relative_path": f"bodies/{slot_id}.json",
            "request_body_sha256": digest,
        }
        for index, (slot_id, digest) in enumerate(FROZEN_BODY_SHA256.items(), 1)
    ]
    manifest = {
        "records": records,
        "shared_prefix": {
            "prime_slot": "medium_shared_prime",
            "follower_slot": "medium_shared_follower",
            "token_lcp": 58880,
            "expected_prefix_hit_tokens": 49152,
        },
        "all_other_pairwise_prefixes_less_than_tokens": 128,
        "all_other_pairwise_prefixes_valid": True,
    }

    summary = build_body_relationship_summary(manifest)

    assert summary["frozen_body_hashes_exact"] is True
    assert summary["request_count"] == 6
    assert summary["shared_prefix"] == manifest["shared_prefix"]
    assert summary["request_bodies_remain_server_local"] is True
    assert summary["generated_text_or_token_ids_present"] is False
    assert [row["slot_id"] for row in summary["records"]] == list(
        FROZEN_BODY_SHA256
    )
    assert all("body_relative_path" not in row for row in summary["records"])
    assert "prompt" not in repr(summary)

    manifest["records"][0]["request_body_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="frozen request body hash mismatch"):
        build_body_relationship_summary(manifest)


def test_r1_grading_requires_parent_trace_green_and_complete_repair_evidence() -> None:
    parent = {
        "grade": "candidate_green_p8_1_official_mtp_observe_only_matrix",
        "successful_request_count": 6,
        "shared_prefix_exact": True,
        "isolated_zero_hit": True,
        "per_request_mtp_ok": True,
        "health_queue_ok": True,
        "replay_deterministic": True,
        "join_coverage_complete": True,
        "trace_validation_errors": 0,
        "cleanup": "clean",
    }
    body = {"frozen_body_hashes_exact": True, "request_count": 6}
    repair = {
        "repair_identity_exact": True,
        "hybrid_diagnostic_ok": True,
        "deferred_import_order_verified": True,
        "retention_interval_explicitly_unset": True,
        "source_hashes_ok": True,
    }
    resolved = {
        "resolved_enable_prefix_caching": True,
        "server_command_has_expected_flag": True,
        "process_cmdline_has_expected_flag": True,
        "opposite_flag_absent": True,
    }

    grading = grade_r1_replay(parent, body, repair, resolved)

    assert grading["grade"] == CANDIDATE_GREEN
    assert grading["parent_trace_gate_ok"] is True
    assert grading["frozen_body_gate_ok"] is True
    assert grading["repair_gate_ok"] is True
    assert grading["resolved_prefix_cache_gate_ok"] is True
    assert grading["cause_supported_by_replay"] is True
    assert grading["performance_effect_accepted"] is False

    repair["hybrid_diagnostic_ok"] = False
    failed = grade_r1_replay(parent, body, repair, resolved)
    assert failed["grade"] == "yellow_p8_1_r1_matrix_trace_invalid"
    assert failed["repair_gate_ok"] is False
    assert failed["cause_supported_by_replay"] is False

    parent["shared_prefix_exact"] = False
    parent["grade"] = "yellow_p8_1_matrix_trace_invalid"
    repair["hybrid_diagnostic_ok"] = True
    persistent_zero_hit = grade_r1_replay(parent, body, repair, resolved)
    assert persistent_zero_hit["grade"] == "yellow_p8_1_r1_matrix_trace_invalid"
    assert persistent_zero_hit["persistent_shared_prefix_failure"] is True
    assert persistent_zero_hit["next_action"] == (
        "read_only_frozen_source_and_server_local_log_diagnosis"
    )


def test_r1_runner_preserves_argv_and_closes_repair_protocol_gates() -> None:
    parent_audit = subprocess.run(
        ["bash", str(PARENT_RUNNER), "/tmp/not-created"],
        cwd=REPO_ROOT,
        env={"PATH": os.environ["PATH"], "P8_1_AUDIT_ONLY": "1"},
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    r1_audit = subprocess.run(
        ["bash", str(R1_RUNNER), "/tmp/not-created"],
        cwd=REPO_ROOT,
        env={"PATH": os.environ["PATH"], "P8_1_R1_AUDIT_ONLY": "1"},
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert r1_audit == parent_audit
    assert hashlib.sha256(r1_audit.encode()).hexdigest() == (
        "370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19"
    )

    runner = R1_RUNNER.read_text(encoding="utf-8")
    assert "cp -a --no-preserve=ownership" in runner
    assert "p6_3b_r1_hybrid_kv_runtime_patch.py" in runner
    assert "p6_3b_r2_hybrid_kv_runtime_patch.py" in runner
    assert "vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch" in runner
    assert "vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch" in runner
    assert "6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c" in runner
    assert "9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631" in runner
    assert "cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e" in runner
    assert "ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b" in runner
    assert "P6_3B_R2_ENABLE_HYBRID_KV_PATCH=1" in runner
    assert "require_ascend_manager_resolution" in runner
    assert "unset VLLM_PREFIX_CACHE_RETENTION_INTERVAL" in runner
    assert "export no_proxy=" in runner
    assert "export NO_PROXY=" in runner
    assert "resolved_prefix_cache_config.json" in runner
    assert runner.index("resolved_prefix_cache_config.json") < runner.index(
        "while IFS=$'\\t' read -r slot_id"
    )
    assert "repair_identity.json" in runner
    assert "body_relationship_summary.json" in runner
    assert "repair_diagnostic_summary.json" in runner
    assert "prepare_deepseek_p8_1_r1_observe_matrix.py" in runner
    assert "finalize_deepseek_p8_1_r1_observe_only_matrix.py" in runner
    assert "msprof" not in runner
    assert "kv-offloading" not in runner

    subprocess.run(["bash", "-n", str(R1_RUNNER)], cwd=REPO_ROOT, check=True)


def test_r1_is_the_only_authorized_handoff_and_current_truth() -> None:
    task_id = (
        "p8_1_r1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0717"
    )
    handoff = (REPO_ROOT / "通信模块/docs/developer-to-server.md").read_text(
        encoding="utf-8"
    )
    assert handoff.count("当前唯一服务器动作") == 1
    assert f"task_id: {task_id}" in handoff
    assert (
        "execution_mode: authorized_p8_1_r1_full_r2_repair_observe_only_six_request_replay"
        in handoff
    )
    assert "npu_execution_authorized: true" in handoff
    assert "next_task_authorized: true" in handoff
    assert "result_transfer_authorized: false" in handoff
    assert "request_count_exact: 6" in handoff
    assert "lifecycle_count_max: 1" in handoff
    assert "no_p8_2_p7_or_p9: true" in handoff
    assert "yellow_p8_1_matrix_trace_invalid" in handoff
    assert "cause_proven_before_replay: false" in handoff
    assert "p8_1_vllm_ascend_official_mtp_observe_only_matrix.yaml" in handoff
    assert "p8_1_r1_vllm_ascend_official_mtp_observe_only_matrix.yaml" in handoff
    assert handoff.count("bash \"${RUNNER}\" \"${RESULT_DIR}\"") == 1

    readiness = yaml.safe_load(
        (REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml").read_text(
            encoding="utf-8"
        )
    )
    artifacts = readiness["artifacts"]
    assert artifacts["completed_p8_1_workload"].endswith(
        "p8_1_vllm_ascend_official_mtp_observe_only_matrix.yaml"
    )
    assert artifacts["next_workload"].endswith(
        "p8_1_r1_vllm_ascend_official_mtp_observe_only_matrix.yaml"
    )
    assert artifacts["current_server_handoff_task"] == task_id
    acceptance = readiness["acceptance"]
    assert acceptance["p8_1_grade"] == "yellow_p8_1_matrix_trace_invalid"
    assert acceptance["p8_1_execution_authorized"] is False
    assert acceptance["p8_1_r1_execution_authorized"] is True
    assert acceptance["p8_2_execution_authorized"] is False
    assert acceptance["next_task_authorized"] is True

    for relative_path in (
        "docs/EXPERIMENT_PLAN.md",
        "docs/DEEPSEEK_V4_FLASH_ASCEND_PLAN.md",
        "docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md",
        "工作记录与进度笔记本/02_阶段计划.md",
        "工作记录与进度笔记本/05_下一步行动指导.md",
    ):
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "yellow_p8_1_matrix_trace_invalid" in text, relative_path
        assert "P8.1-R1" in text, relative_path
        assert task_id in text, relative_path
        assert "P8.2" in text, relative_path
