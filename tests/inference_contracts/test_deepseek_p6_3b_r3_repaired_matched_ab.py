import hashlib
import importlib
import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKLOAD_PATH = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3b_r3_repaired_prefix_cache_matched_ab.yaml"
)


def test_r3_workload_repeats_the_full_matched_ab_with_one_repaired_runtime():
    workload = yaml.safe_load(WORKLOAD_PATH.read_text(encoding="utf-8"))

    assert workload["stage_contract"]["stage"] == "P6.3B-R3"
    assert workload["stage_contract"]["claim_boundary"] == (
        "repaired_hybrid_kv_prefix_cache_matched_ab_mechanism_effect_only"
    )
    assert workload["accepted_prerequisites"]["r2_grade"] == (
        "green_p6_3b_r2_hybrid_kv_repair"
    )
    assert workload["mode_order"] == ["prefix_cache_off", "prefix_cache_on"]
    assert workload["single_variable"]["name"] == "enable_prefix_caching"
    assert workload["single_variable"]["same_r2_repair_in_both_modes"] is True
    assert len(workload["prefix_groups"]) == 8
    assert workload["lifecycle_plan"]["server_lifecycles"] == 2
    assert workload["lifecycle_plan"]["total_requests"] == 64
    assert workload["execution_state"] == {
        "status": "completed_server_yellow_invalid_control",
        "server_handoff": "historical",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
    }
    assert workload["execution_result"]["effective_comparison"] == (
        "repaired_prefix_cache_on_vs_on"
    )
    assert workload["stage_contract"]["p6_3c_execution_authorized"] is False


def test_r3_mode_runner_loads_the_same_r2_repair_and_only_toggles_prefix_cache():
    runner = (
        REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3b_r3_mode.sh"
    ).read_text(encoding="utf-8")

    assert "prefix_cache_off|prefix_cache_on" in runner
    assert "p6_3b_hybrid_kv_runtime_impl.py" in runner
    assert "p6_3b_r2_hybrid_kv_runtime_patch.py" in runner
    assert "hybrid_kv_deferred_install_overlay.patch" in runner
    assert "git apply --check --ignore-whitespace" in runner
    assert "git apply --ignore-whitespace" in runner
    assert "P6_3B_R2_ENABLE_HYBRID_KV_PATCH=1" in runner
    assert "require_ascend_manager_resolution" in runner
    assert 'if test "${MODE}" = prefix_cache_on; then' in runner
    assert runner.count("cmd+=(--enable-prefix-caching)") == 1
    assert runner.count("--speculative-config") == 1
    assert "--enable-chunked-prefill" in runner
    assert "unset VLLM_PREFIX_CACHE_RETENTION_INTERVAL" in runner
    assert "sitecustomize.py" not in runner
    assert "msprof" not in runner
    assert "hbm" not in runner.lower()


def test_r3_grading_requires_matched_requests_and_green_repair_in_both_modes():
    runner = importlib.import_module(
        "tools.inference_contracts.run_deepseek_p6_3b_r3_repaired_matched_ab"
    )
    rows = []
    for mode in runner.MODES:
        for item in runner.build_run_plan():
            measured = item["request_role"] == "measured"
            rows.append(
                {
                    **item,
                    "mode": mode,
                    "status": "success",
                    "queue_metrics_ok": True,
                    "counter_continuity_ok": True,
                    "spec_activity_ok": True,
                    "prefix_evidence_ok": True,
                    "prefix_queries_delta": 100.0 if mode == "prefix_cache_on" else 0.0,
                    "prefix_hits_delta": (
                        50.0
                        if mode == "prefix_cache_on" and measured
                        else 0.0
                    ),
                    "accepted_token_delta": 32.0,
                }
            )

    repair_identity = {
        mode: {"runtime_impl": "same", "deferred_loader": "same"}
        for mode in runner.MODES
    }
    green = runner.grade_r3_evidence(
        rows,
        cleanup_by_mode={mode: "clean" for mode in runner.MODES},
        diagnostic_ok_by_mode={mode: True for mode in runner.MODES},
        repair_identity_by_mode=repair_identity,
    )
    assert green["server_grade"] == (
        "candidate_green_p6_3b_r3_repaired_prefix_cache_matched_ab"
    )
    assert green["same_r2_repair_in_both_modes"] is True
    assert green["required_diagnostic_ok_by_mode"] == {
        "prefix_cache_off": True,
        "prefix_cache_on": True,
    }

    repair_identity["prefix_cache_on"]["runtime_impl"] = "different"
    mismatch = runner.grade_r3_evidence(
        rows,
        cleanup_by_mode={mode: "clean" for mode in runner.MODES},
        diagnostic_ok_by_mode={mode: True for mode in runner.MODES},
        repair_identity_by_mode=repair_identity,
    )
    assert mismatch["server_grade"] == (
        "red_p6_3b_r3_repaired_prefix_cache_evidence_incomplete"
    )

    missing_identity = runner.grade_r3_evidence(
        rows,
        cleanup_by_mode={mode: "clean" for mode in runner.MODES},
        diagnostic_ok_by_mode={mode: True for mode in runner.MODES},
        repair_identity_by_mode={mode: {} for mode in runner.MODES},
    )
    assert missing_identity["same_r2_repair_in_both_modes"] is False
    assert missing_identity["server_grade"] == (
        "red_p6_3b_r3_repaired_prefix_cache_evidence_incomplete"
    )


def test_r3_finalizer_writes_bounded_repaired_matched_ab_evidence(tmp_path):
    runner = importlib.import_module(
        "tools.inference_contracts.run_deepseek_p6_3b_r3_repaired_matched_ab"
    )
    diagnostics = [
        {
            "event": "runtime_patch_installed",
            "retention_interval": None,
            "source_evidence": {
                name: {"match": True} for name in runner.EXPECTED_SOURCE_SHA256
            },
        },
        {"event": "deferred_import_order_verified"},
        {
            "event": "coordinator_snapshot",
            "lcm_block_size": 16384,
            "eagle_group_ids": [1],
            "attention_groups": [{"group_ids": [0, 1]}],
            "managers": [
                {
                    "group_id": 0,
                    "manager_type": "SlidingWindowManager",
                    "use_eagle": True,
                },
                {
                    "group_id": 1,
                    "manager_type": "CompressAttentionManager",
                    "use_eagle": True,
                },
            ],
            "prefix_cache_retention_interval": None,
        },
        {"event": "eagle_lookahead_cache_target"},
        {"event": "eagle_reachable_mask"},
    ]
    repair_identity = "runtime_impl\tsame\ndeferred_loader\tsame\n"
    for mode in runner.MODES:
        mode_dir = tmp_path / "modes" / mode
        runtime_dir = mode_dir / "runtime"
        runtime_dir.mkdir(parents=True)
        rows = []
        for item in runner.build_run_plan():
            measured = item["request_role"] == "measured"
            rows.append(
                {
                    **item,
                    "mode": mode,
                    "status": "success",
                    "ttft_ms": 10.0 if mode == "prefix_cache_on" else 20.0,
                    "tpot_ms": 30.0,
                    "e2el_ms": 100.0,
                    "output_tokens_per_second": 2.0,
                    "queue_metrics_ok": True,
                    "counter_continuity_ok": True,
                    "spec_activity_ok": True,
                    "prefix_evidence_ok": True,
                    "prefix_queries_delta": 100.0 if mode == "prefix_cache_on" else 0.0,
                    "prefix_hits_delta": (
                        50.0
                        if mode == "prefix_cache_on" and measured
                        else 0.0
                    ),
                    "accepted_token_delta": 32.0,
                }
            )
        (mode_dir / "raw_request_results.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        mode_diagnostics = diagnostics[:2] if mode == "prefix_cache_off" else diagnostics
        (runtime_dir / "hybrid_kv_runtime_diagnostic.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in mode_diagnostics),
            encoding="utf-8",
        )
        (runtime_dir / "source_gate_status.txt").write_text(
            "pass\n", encoding="utf-8"
        )
        (mode_dir / "repair_identity.tsv").write_text(
            repair_identity, encoding="utf-8"
        )
        (mode_dir / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")

    (tmp_path / "request_body_manifest.json").write_text(
        json.dumps({"generated_text_retained": False, "token_ids_retained": False}),
        encoding="utf-8",
    )
    grading = runner.finalize_artifacts(tmp_path)

    assert grading["server_grade"] == (
        "candidate_green_p6_3b_r3_repaired_prefix_cache_matched_ab"
    )
    assert grading["candidate_size_gate_pass"] is True
    assert grading["same_r2_repair_in_both_modes"] is True
    assert (tmp_path / "hybrid_kv_diagnostic_summary.json").exists()
    assert "P6.3B-R3" in (tmp_path / "result_summary.md").read_text(
        encoding="utf-8"
    )
    candidates = (tmp_path / "delivery_candidates.tsv").read_text(
        encoding="utf-8"
    )
    assert "hybrid_kv_diagnostic_summary.json" in candidates
    assert "generated_text" not in candidates
    assert "token_ids" not in candidates
    candidate_rows = [line.split("\t") for line in candidates.splitlines()[1:]]
    candidate_bytes = sum(int(row[1]) for row in candidate_rows)
    assert candidate_bytes == int(
        (tmp_path / "delivery_candidates_total_bytes.txt")
        .read_text(encoding="utf-8")
        .strip()
    )
    assert candidate_bytes == json.loads(
        (tmp_path / "grading_inputs.json").read_text(encoding="utf-8")
    )["candidate_total_bytes"]

    (
        tmp_path
        / "modes"
        / "prefix_cache_off"
        / "runtime"
        / "source_gate_status.txt"
    ).unlink()
    missing_source_gate = runner.finalize_artifacts(tmp_path)
    assert missing_source_gate["server_grade"] == (
        "red_p6_3b_r3_repaired_prefix_cache_evidence_incomplete"
    )


def test_r2_is_closed_green_and_superseded_by_the_authorized_r3():
    r2_path = (
        REPO_ROOT
        / "benchmarks/deepseek_v4_flash/workloads/"
        "p6_3b_r2_hybrid_kv_deferred_install_repair.yaml"
    )
    r2 = yaml.safe_load(r2_path.read_text(encoding="utf-8"))

    assert r2["execution_result"]["developer_accepted_grade"] == (
        "green_p6_3b_r2_hybrid_kv_repair"
    )
    assert r2["execution_result"]["prime_success"] == 3
    assert r2["execution_result"]["measured_success"] == 9
    assert r2["execution_result"]["positive_hit_measured_count"] == 9
    assert r2["execution_result"]["cleanup"] == "clean"
    assert r2["execution_result"]["superseded_by"] == (
        "p6_3b_r3_repaired_prefix_cache_matched_ab.yaml"
    )
    assert r2["execution_state"] == {
        "status": "completed_server_candidate_developer_accepted_green",
        "server_handoff": "historical",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
    }


def test_handoff_preserves_r4_r1_closeout_during_r5_f0_feasibility():
    handoff = (
        REPO_ROOT / "通信模块/docs/developer-to-server.md"
    ).read_text(encoding="utf-8")

    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert "P8.2-K1A-R5-F1-R3 运行中窗口中止与单次恢复" in handoff
    assert "task_id: p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722" in handoff
    assert "execution_mode: authorized_single_lifecycle_inflight_trigger_abort_idle_restore" in handoff
    assert "npu_execution_authorized: true" in handoff
    assert "next_task_authorized: false" in handoff
    assert "R5-L1-R1 的有界包" in handoff
    assert "精确重放 R2 geometry/rendezvous/allocator" in handoff
    assert "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab" in handoff
    assert "green_p8_1_r1_official_mtp_observe_only_matrix" in handoff


def test_current_truth_surfaces_preserve_r3_and_blocked_r4_then_close_r4_r1():
    readiness = yaml.safe_load(
        (
            REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
        ).read_text(encoding="utf-8")
    )
    artifacts = readiness["artifacts"]
    acceptance = readiness["acceptance"]

    assert artifacts["completed_p6_3b_r2_workload"] == (
        "workloads/p6_3b_r2_hybrid_kv_deferred_install_repair.yaml"
    )
    assert artifacts["completed_p6_3b_r3_workload"].endswith(
        "p6_3b_r3_repaired_prefix_cache_matched_ab.yaml"
    )
    assert artifacts["completed_p6_3b_r4_r1_workload"] == (
        "workloads/p6_3b_r4_r1_explicit_prefix_cache_matched_ab.yaml"
    )
    assert artifacts["completed_p8_2_k0_workload"].endswith(
        "p8_2_k0_order_balanced_prefix_cache_baseline.yaml"
    )
    assert artifacts["next_workload"].endswith(
        "p8_2_k1a_r5_f1_r3_inflight_abort_restore.yaml"
    )
    assert acceptance["p6_3b_r2_grade"] == (
        "green_p6_3b_r2_hybrid_kv_repair"
    )
    assert acceptance["p6_3b_r2_execution_authorized"] is False
    assert acceptance["p6_3b_r3_execution_authorized"] is False
    assert acceptance["p6_3b_r4_grade"] == (
        "blocked_p6_3b_r4_source_or_resource_gate"
    )
    assert acceptance["p6_3b_r4_execution_authorized"] is False
    assert acceptance["p6_3b_r4_r1_grade"] == (
        "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab"
    )
    assert acceptance["p6_3b_r4_r1_execution_authorized"] is False
    assert acceptance["p6_3c_execution_authorized"] is False
    assert readiness["target_runtime"]["runtime_status"] == (
        "p8_2_k0_green_k1_blocked_k1a_red_k1a_r2_ready_full_r3_lineage_preserved_k1a_r3_r2_r2_r1_r1_r1_store_only_yellow_h2d_absent_k1a_r4_blocked_k1a_r4_r1_offline_store_only_green_k1a_r5_f0_ready_k1a_r5_l1_d2h_green_controller_red_k1a_r5_l1_r1_target_lost_red_k1a_r5_f1_offline_current_l2_conditional_i0_r1_green"
    )

    surfaces = [
        REPO_ROOT / "工作记录与进度笔记本/02_阶段计划.md",
        REPO_ROOT / "工作记录与进度笔记本/05_下一步行动指导.md",
        REPO_ROOT / "工作记录与进度笔记本/09_DeepSeek_V4_Flash_专项计划.md",
        REPO_ROOT / "工作记录与进度笔记本/12_P5_P9_后续阶段重排计划.md",
        REPO_ROOT / "工作记录与进度笔记本/16_P6_阶段复盘与P6_3进入评估.md",
        REPO_ROOT / "docs/EXPERIMENT_PLAN.md",
    ]
    for path in surfaces:
        text = path.read_text(encoding="utf-8")
        assert "green_p6_3b_r2_hybrid_kv_repair" in text, path.name
        assert "P6.3B-R3" in text, path.name
        assert "P6.3B-R4" in text, path.name
        assert "same R2 repair" in text, path.name
        assert "P6.3C" in text, path.name


def test_r3_workload_freezes_the_published_runner_files():
    workload = yaml.safe_load(WORKLOAD_PATH.read_text(encoding="utf-8"))

    for key in ("runner", "mode_runner"):
        artifact = workload["runner_artifacts"][key]
        path = REPO_ROOT / artifact["path"]
        assert path.stat().st_size == artifact["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
