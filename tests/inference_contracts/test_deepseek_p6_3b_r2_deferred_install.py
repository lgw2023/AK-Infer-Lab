import hashlib
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_r2_runtime_patch_import_is_inert_until_deferred_bootstrap():
    patch = importlib.import_module(
        "tools.inference_contracts.p6_3b_r2_hybrid_kv_runtime_patch"
    )

    assert patch.PATCH_INSTALLED is False
    assert patch.ENABLE_ENV == "P6_3B_R2_ENABLE_HYBRID_KV_PATCH"
    assert callable(patch.install_runtime_patch)


def test_r2_manager_resolution_requires_both_ascend_mla_spec_keys():
    patch = importlib.import_module(
        "tools.inference_contracts.p6_3b_r2_hybrid_kv_runtime_patch"
    )

    class AscendMLAAttentionSpec:
        pass

    class AscendSlidingWindowMLASpec:
        pass

    interface = SimpleNamespace(
        AscendMLAAttentionSpec=AscendMLAAttentionSpec,
        AscendSlidingWindowMLASpec=AscendSlidingWindowMLASpec,
    )
    manager = SimpleNamespace(
        MLAAttentionSpec=AscendMLAAttentionSpec,
        SlidingWindowMLASpec=AscendSlidingWindowMLASpec,
        spec_manager_map={
            AscendMLAAttentionSpec: object,
            AscendSlidingWindowMLASpec: object,
        },
    )

    snapshot = patch.require_ascend_manager_resolution(
        manager_module=manager,
        interface_module=interface,
    )
    assert snapshot == {
        "ascend_mla_exact_key_registered": True,
        "ascend_sliding_window_mla_exact_key_registered": True,
        "manager_mla_alias_is_ascend": True,
        "manager_sliding_window_mla_alias_is_ascend": True,
    }

    manager.spec_manager_map.pop(AscendSlidingWindowMLASpec)
    with pytest.raises(RuntimeError, match="Ascend KV spec manager resolution"):
        patch.require_ascend_manager_resolution(
            manager_module=manager,
            interface_module=interface,
        )


def test_r2_ascend_bootstrap_defers_install_until_after_spec_replacement():
    patch_path = (
        REPO_ROOT
        / "benchmarks/deepseek_v4_flash/patches/"
        "vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch"
    )
    content = patch_path.read_text(encoding="utf-8")

    mla_assignment = (
        "vllm.v1.kv_cache_interface.MLAAttentionSpec = AscendMLAAttentionSpec"
    )
    sliding_assignment = (
        "vllm.v1.kv_cache_interface.SlidingWindowMLASpec = "
        "AscendSlidingWindowMLASpec"
    )
    deferred_import = (
        "from p6_3b_r2_hybrid_kv_runtime_patch import install_runtime_patch"
    )
    assert mla_assignment in content
    assert sliding_assignment in content
    assert deferred_import in content
    assert content.index(mla_assignment) < content.index(deferred_import)
    assert content.index(sliding_assignment) < content.index(deferred_import)
    assert "P6_3B_R2_ENABLE_HYBRID_KV_PATCH" in content
    assert "sitecustomize" not in content


def test_r2_mode_runner_uses_real_import_order_self_test_before_vllm():
    mode_runner = (
        REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3b_r2_mode.sh"
    ).read_text(encoding="utf-8")

    assert "sitecustomize" not in mode_runner
    assert "p6_3b_hybrid_kv_runtime_impl.py" in mode_runner
    assert "p6_3b_r2_hybrid_kv_runtime_patch.py" in mode_runner
    assert "hybrid_kv_deferred_install_overlay.patch" in mode_runner
    assert "patch -l -p1" in mode_runner
    assert (
        "import vllm_ascend.patch.platform.patch_kv_cache_interface" in mode_runner
    )
    assert "require_ascend_manager_resolution" in mode_runner
    assert "P6_3B_R2_ENABLE_HYBRID_KV_PATCH=1" in mode_runner
    assert mode_runner.index("runtime_patch_self_test.txt") < mode_runner.index(
        "setsid \"${cmd[@]}\""
    )
    assert "--enable-prefix-caching" in mode_runner
    assert "--speculative-config" in mode_runner
    assert "--enable-chunked-prefill" in mode_runner
    assert "--max-num-seqs 1" in mode_runner
    assert "--enforce-eager" not in mode_runner
    assert "msprof" not in mode_runner
    assert "npu-smi" not in mode_runner


def test_r2_finalizer_preserves_real_startup_failure_excerpt(tmp_path):
    runner = importlib.import_module(
        "tools.inference_contracts.run_deepseek_p6_3b_r2_hybrid_kv_repair"
    )
    mode_dir = tmp_path / "modes/prefix_cache_on"
    runtime_dir = mode_dir / "runtime"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "source_gate_status.txt").write_text("pass\n", encoding="utf-8")
    (mode_dir / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
    (mode_dir / "first_failure_excerpt.txt").write_text(
        "KeyError: AscendMLAAttentionSpec\n", encoding="utf-8"
    )

    grading = runner.finalize_artifacts(tmp_path)

    assert grading["server_grade"] == (
        "red_p6_3b_r2_hybrid_kv_repair_no_success"
    )
    assert "KeyError: AscendMLAAttentionSpec" in (
        tmp_path / "first_failure_excerpt.txt"
    ).read_text(encoding="utf-8")
    assert "# P6.3B-R2 hybrid-KV repair result" in (
        tmp_path / "result_summary.md"
    ).read_text(encoding="utf-8")


def test_r2_workload_closes_r1_and_freezes_only_the_deferred_install_delta():
    r1 = yaml.safe_load(
        (
            REPO_ROOT
            / "benchmarks/deepseek_v4_flash/workloads/"
            "p6_3b_r1_hybrid_kv_repair.yaml"
        ).read_text(encoding="utf-8")
    )
    r2 = yaml.safe_load(
        (
            REPO_ROOT
            / "benchmarks/deepseek_v4_flash/workloads/"
            "p6_3b_r2_hybrid_kv_deferred_install_repair.yaml"
        ).read_text(encoding="utf-8")
    )

    assert r1["execution_result"]["task_status"] == (
        "red_p6_3b_r1_hybrid_kv_repair_no_success"
    )
    assert r1["execution_result"]["server_ready"] is False
    assert r1["execution_result"]["requests_dispatched"] == 0
    assert r1["execution_result"]["cleanup"] == "clean"
    assert r1["execution_result"]["superseded_by"] == (
        "p6_3b_r2_hybrid_kv_deferred_install_repair.yaml"
    )
    assert r1["execution_state"]["npu_execution_authorized"] is False
    assert r1["execution_state"]["next_task_authorized"] is False

    assert r2["workload_id"] == (
        "p6_3b_r2_deepseek_v4_flash_mtp_prefix_cache_hybrid_kv_"
        "deferred_install_repair"
    )
    assert r2["task_id"] == (
        "p6_3b_r2_deepseek_v4_flash_w8a8_mtp_prefix_cache_hybrid_kv_"
        "deferred_install_repair_2026_0715"
    )
    assert r2["stage_contract"]["stage"] == "P6.3B-R2"
    assert r2["stage_contract"]["prior_r1_grade"] == (
        "red_p6_3b_r1_hybrid_kv_repair_no_success"
    )
    repair = r2["hybrid_kv_repair"]
    assert repair["eager_sitecustomize_allowed"] is False
    assert repair["install_trigger"] == (
        "after_ascend_mla_and_sliding_window_mla_spec_replacement"
    )
    assert repair["manager_resolution_preflight"] == [
        "AscendMLAAttentionSpec",
        "AscendSlidingWindowMLASpec",
    ]
    assert repair["runtime_upgrade"] is False
    assert repair["base_environment_mutation"] is False
    assert repair["site_packages_mutation"] is False
    frozen_files = {
        repair["runtime_implementation_path"]: repair[
            "runtime_implementation_sha256"
        ],
        repair["deferred_loader_path"]: repair["deferred_loader_sha256"],
        repair["deferred_bootstrap_patch_path"]: repair[
            "deferred_bootstrap_patch_sha256"
        ],
        repair["vllm_ascend_manager_overlay_patch_path"]: repair[
            "vllm_ascend_manager_overlay_patch_sha256"
        ],
        r2["runner_artifacts"]["runner_path"]: r2["runner_artifacts"][
            "runner_sha256"
        ],
        r2["runner_artifacts"]["mode_runner_path"]: r2[
            "runner_artifacts"
        ]["mode_runner_sha256"],
    }
    for relative_path, expected_sha256 in frozen_files.items():
        assert hashlib.sha256(
            (REPO_ROOT / relative_path).read_bytes()
        ).hexdigest() == expected_sha256
    assert r2["lifecycle_plan"] == r1["lifecycle_plan"]
    assert r2["prefix_groups"] == r1["prefix_groups"]
    assert r2["execution_state"] == {
        "status": "authorized_for_execution",
        "server_handoff": "current",
        "npu_execution_authorized": True,
        "next_task_authorized": True,
    }


def test_r2_grading_requires_deferred_import_order_runtime_evidence():
    runner = importlib.import_module(
        "tools.inference_contracts.run_deepseek_p6_3b_r2_hybrid_kv_repair"
    )
    rows = []
    for item in runner.build_r1_plan():
        measured = item["request_role"] == "measured"
        rows.append(
            {
                **item,
                "status": "success",
                "prefix_queries_delta": 4096.0,
                "prefix_hits_delta": 2048.0 if measured else 0.0,
                "accepted_token_delta": 32.0,
                "queue_metrics_ok": True,
                "counter_continuity_ok": True,
                "spec_activity_ok": True,
            }
        )
    diagnostics = [
        {
            "event": "runtime_patch_installed",
            "retention_interval": None,
            "source_evidence": {
                name: {"match": True}
                for name in runner.EXPECTED_SOURCE_SHA256
            },
        },
        {
            "event": "coordinator_snapshot",
            "lcm_block_size": 16384,
            "eagle_group_ids": [1],
            "attention_groups": [{"group_ids": [0, 1]}],
            "managers": [
                {"group_id": 0, "manager_type": "SlidingWindow", "use_eagle": True},
                {"group_id": 1, "manager_type": "Compress", "use_eagle": True},
            ],
            "prefix_cache_retention_interval": None,
        },
        {"event": "eagle_lookahead_cache_target"},
        {"event": "eagle_reachable_mask"},
    ]

    missing = runner.grade_r2_evidence(
        rows, diagnostics=diagnostics, cleanup="clean"
    )
    assert missing["server_grade"] == (
        "red_p6_3b_r2_hybrid_kv_evidence_incomplete"
    )
    assert missing["deferred_import_order_verified"] is False

    diagnostics.append({"event": "deferred_import_order_verified"})
    green = runner.grade_r2_evidence(
        rows, diagnostics=diagnostics, cleanup="clean"
    )
    assert green["server_grade"] == (
        "candidate_green_p6_3b_r2_hybrid_kv_repair"
    )
    assert green["deferred_import_order_verified"] is True
