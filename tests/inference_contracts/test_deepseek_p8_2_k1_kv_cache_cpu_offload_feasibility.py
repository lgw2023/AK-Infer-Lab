from pathlib import Path
import json
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
K0_WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k0_order_balanced_prefix_cache_baseline.yaml"
)
K1_AUDIT = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1_kv_cache_cpu_offload_feasibility_audit.yaml"
)
K1_AUDITOR = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "audit_deepseek_p8_2_k1_kv_cache_cpu_offload.py"
)
READINESS = REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
HANDOFF = REPO_ROOT / "通信模块/docs/developer-to-server.md"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_k0_r1_candidate_is_closed_as_developer_accepted_green():
    workload = _load_yaml(K0_WORKLOAD)

    assert workload["execution_state"] == {
        "status": "completed_developer_accepted_green",
        "server_handoff": "consumed_historical",
        "server_result": "developer_reviewed",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
        "result_transfer_authorized": False,
        "standing_npu_and_vllm_consumption_authorization": True,
    }
    result = workload["execution_result"]
    assert result["original_server_grade"] == (
        "red_p8_2_k0_order_balanced_prefix_baseline_evidence_incomplete"
    )
    assert result["refinalized_server_grade"] == (
        "candidate_green_p8_2_k0_order_balanced_prefix_cache_baseline"
    )
    assert result["developer_grade"] == (
        "green_p8_2_k0_order_balanced_prefix_cache_baseline"
    )
    assert result["successful_request_count"] == "20_of_20"
    assert result["request_evidence_predicate_count"] == 15
    assert result["request_evidence_predicates_all_20_of_20"] is True
    assert result["source_evidence_file_count"] == 29
    assert result["source_evidence_unchanged"] is True
    assert result["candidate_file_count"] == 14
    assert result["candidate_total_bytes"] == 35241
    assert result["package_sha256_verified_by_developer"] is True
    assert result["performance_reference_accepted"] is False
    assert result["offload_evidence_accepted"] is False


def test_k1_frozen_stack_audit_blocks_an_executable_offload_workload():
    audit = _load_yaml(K1_AUDIT)

    assert audit["audit_grade"] == (
        "blocked_p8_2_k1_frozen_stack_import_incompatible"
    )
    assert audit["claim_boundary"] == (
        "frozen_source_import_config_and_hybrid_group_compatibility_only"
    )
    assert audit["frozen_runtime"] == {
        "vllm_version": "0.22.1+empty",
        "vllm_commit": "0decac0d96c42b49572498019f0a0e3600f50398",
        "vllm_ascend_version": "0.22.1rc1",
        "vllm_ascend_commit": "5f6faa0cb8830f667266f3b8121cd1383606f2a1",
    }
    compatibility = audit["compatibility_findings"]
    assert compatibility["ascend_npu_spec_imports"] == [
        "vllm.v1.kv_offload.abstract",
        "vllm.v1.kv_offload.mediums",
        "vllm.v1.kv_offload.spec",
    ]
    assert compatibility["missing_in_frozen_vllm_tree"] == [
        "vllm/v1/kv_offload/abstract.py",
        "vllm/v1/kv_offload/mediums.py",
        "vllm/v1/kv_offload/spec.py",
    ]
    assert compatibility["npu_spec_single_group_assertion_count"] == 2
    assert compatibility["deepseek_r2_hybrid_group_count_min"] == 2
    assert compatibility["direct_import_expected_to_fail_before_npu"] is True
    assert compatibility["documented_block_size_128_valid_for_hybrid"] is False

    decision = audit["decision"]
    assert decision["formal_k1_matched_ab_allowed"] is False
    assert decision["k1_workload"] == "none"
    assert decision["k1_runner"] == "none"
    assert decision["task_local_compatibility_patch_authorized"] is False
    assert decision["npu_execution_authorized"] is False
    assert decision["next_stage_authorized"] is False

    assert not list(
        (REPO_ROOT / "benchmarks/deepseek_v4_flash/workloads").glob("p8_2_k1_*.yaml")
    )
    assert not list(
        (REPO_ROOT / "tools/inference_contracts").glob("run_deepseek_p8_2_k1_*")
    )


def test_k1_auditor_reproduces_the_frozen_source_incompatibility():
    completed = subprocess.run(
        [
            "python3",
            str(K1_AUDITOR),
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
        "blocked_p8_2_k1_frozen_stack_import_incompatible"
    )
    assert result["vllm_commit"] == (
        "0decac0d96c42b49572498019f0a0e3600f50398"
    )
    assert result["vllm_ascend_commit"] == (
        "5f6faa0cb8830f667266f3b8121cd1383606f2a1"
    )
    assert result["source_hash_gate"] is True
    assert result["missing_legacy_modules"] == [
        "vllm/v1/kv_offload/abstract.py",
        "vllm/v1/kv_offload/mediums.py",
        "vllm/v1/kv_offload/spec.py",
    ]
    assert result["npu_spec_single_group_assertion_count"] == 2
    assert result["formal_k1_workload_allowed"] is False
    assert result["npu_started"] is False
    assert result["vllm_server_started"] is False
    assert result["model_request_sent"] is False


def test_k1_auditor_accepts_hash_verified_installed_source_trees(tmp_path: Path):
    vllm_root = tmp_path / "vllm"
    ascend_root = tmp_path / "vllm_ascend_root"
    source_specs = (
        (
            REPO_ROOT / "reference_repos/vllm",
            "0decac0d96c42b49572498019f0a0e3600f50398",
            vllm_root,
            (
                "vllm/config/kv_transfer.py",
                "vllm/engine/arg_utils.py",
                "vllm/v1/kv_offload/base.py",
                "vllm/v1/kv_offload/factory.py",
                "vllm/distributed/kv_transfer/kv_connector/v1/offloading_connector.py",
                "vllm/distributed/kv_transfer/kv_connector/v1/offloading/metrics.py",
            ),
        ),
        (
            REPO_ROOT / "reference_repos/vllm-ascend",
            "5f6faa0cb8830f667266f3b8121cd1383606f2a1",
            ascend_root,
            (
                "vllm_ascend/kv_offload/npu.py",
                "vllm_ascend/kv_offload/cpu_npu.py",
                "docs/source/user_guide/feature_guide/kv_cache_cpu_offload.md",
            ),
        ),
    )
    for repo, commit, destination, relative_paths in source_specs:
        for relative_path in relative_paths:
            target = destination / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(
                subprocess.run(
                    ["git", "-C", str(repo), "show", f"{commit}:{relative_path}"],
                    capture_output=True,
                    check=True,
                ).stdout
            )

    completed = subprocess.run(
        [
            "python3",
            str(K1_AUDITOR),
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
        "blocked_p8_2_k1_frozen_stack_import_incompatible"
    )
    assert result["source_hash_gate"] is True
    assert result["missing_legacy_modules"] == [
        "vllm/v1/kv_offload/abstract.py",
        "vllm/v1/kv_offload/mediums.py",
        "vllm/v1/kv_offload/spec.py",
    ]
    assert result["npu_spec_single_group_assertion_count"] == 2
    assert result["formal_k1_workload_allowed"] is False


def test_k1_block_is_preserved_in_the_k1a_causal_replay_server_handoff():
    task_id = "p8_2_k1a_r3_r2_r2_r1_r1_r1_deepseek_v4_flash_causal_exception_replay_2026_0720"
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert handoff.count("当前唯一服务器动作") == 1
    assert f"task_id: {task_id}" in handoff
    assert (
        "execution_mode: authorized_offline_causal_exception_refinalization_then_one_same_capacity_lifecycle"
        in handoff
    )
    for field in (
        "server_sync_review_authorized: true",
        "npu_execution_authorized: true",
        "vllm_server_start_authorized: true",
        "model_requests_authorized: true",
        "keep_alive_stop_and_restore_authorized: true",
        "result_directory_creation_authorized: true",
        "result_transfer_authorized: true",
        "next_task_authorized: false",
        "formal_model_lifecycle_count_max: 1",
        "model_request_count_max: 6",
    ):
        assert field in handoff
    assert "blocked_p8_2_k1_frozen_stack_import_incompatible" in handoff
    assert "SimpleCPUOffloadConnector" in handoff
    assert "K2" in handoff and "不得进入" in handoff

    readiness = _load_yaml(READINESS)
    artifacts = readiness["artifacts"]
    assert artifacts["p8_2_k1_feasibility_audit"].endswith(
        "p8_2_k1_kv_cache_cpu_offload_feasibility_audit.yaml"
    )
    assert artifacts["current_p8_2_k1_auditor"].endswith(
        "audit_deepseek_p8_2_k1_kv_cache_cpu_offload.py"
    )
    assert artifacts["next_workload"].endswith(
        "p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_replay.yaml"
    )
    assert artifacts["current_server_handoff_task"] == task_id
    assert artifacts["current_server_handoff_execution_mode"] == (
        "authorized_offline_causal_exception_refinalization_then_one_same_capacity_lifecycle"
    )
    acceptance = readiness["acceptance"]
    assert acceptance["p8_2_k0_grade"] == (
        "green_p8_2_k0_order_balanced_prefix_cache_baseline"
    )
    assert acceptance["p8_2_k0_refinalization_authorized"] is False
    assert acceptance["p8_2_k1_feasibility_grade"] == (
        "blocked_p8_2_k1_frozen_stack_import_incompatible"
    )
    assert acceptance["p8_2_k1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r1_allocator_probe_authorized"] is False
    assert acceptance["p8_2_k1a_r2_allocator_probe_authorized"] is False
    assert acceptance["p8_2_k1a_r3_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_r1_execution_authorized"] is False
    assert acceptance["p8_2_k1a_r3_r2_r2_r1_r1_r1_execution_authorized"] is True
    assert acceptance["server_sync_review_authorized"] is True
    assert acceptance["next_task_authorized"] is False
