import importlib
import json
import hashlib
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
MODE_RUNNER_PATH = (
    REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3b_r4_mode.sh"
)
WORKLOAD_PATH = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3b_r4_explicit_prefix_cache_matched_ab.yaml"
)


def test_r4_mode_runner_uses_explicit_opposite_prefix_cache_flags_and_gates_them():
    runner = MODE_RUNNER_PATH.read_text(encoding="utf-8")
    shared_runner = (
        REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3b_r3_mode.sh"
    ).read_text(encoding="utf-8")
    contract = runner + shared_runner

    assert "P6_3B_PREFIX_CACHE_CONTROL=explicit_opposite_flags" in contract
    assert "--no-enable-prefix-caching" in contract
    assert "--enable-prefix-caching" in contract
    assert "resolved_prefix_cache_config.json" in contract
    assert "process_cmdline_has_expected_flag" in contract
    assert "process_cmdline_has_opposite_flag" in contract
    assert "REQUEST_RUNNER=" in runner
    assert "run_deepseek_p6_3b_r4_explicit_matched_ab.py" in runner


def test_r4_grading_requires_true_off_and_known_positive_on_groups_only():
    runner = importlib.import_module(
        "tools.inference_contracts.run_deepseek_p6_3b_r4_explicit_matched_ab"
    )
    rows = []
    for mode in runner.MODES:
        for item in runner.build_run_plan():
            measured = item["request_role"] == "measured"
            known_positive = item["group_id"] in runner.POSITIVE_HIT_GROUPS
            expected_hits = (
                item["target_shared_prefix_tokens"]
                // runner.HYBRID_LCM_TOKENS
                * runner.HYBRID_LCM_TOKENS
            )
            hits = (
                float(expected_hits)
                if mode == "prefix_cache_on" and measured and known_positive
                else 0.0
            )
            rows.append(
                {
                    **item,
                    "mode": mode,
                    "status": "success",
                    "queue_metrics_ok": True,
                    "counter_continuity_ok": True,
                    "spec_activity_ok": True,
                    "prefix_evidence_ok": True,
                    "prefix_queries_delta": 32768.0 if mode == "prefix_cache_on" else 0.0,
                    "prefix_hits_delta": hits,
                    "expected_prefix_hit_tokens": expected_hits,
                    "accepted_token_delta": 32.0,
                }
            )

    repair_identity = {
        mode: {"runtime_impl": "same", "deferred_loader": "same"}
        for mode in runner.MODES
    }
    resolved = {
        mode: {
            "resolved_enable_prefix_caching": mode == "prefix_cache_on",
            "server_command_has_expected_flag": True,
            "server_command_has_opposite_flag": False,
            "process_cmdline_has_expected_flag": True,
            "process_cmdline_has_opposite_flag": False,
        }
        for mode in runner.MODES
    }
    green = runner.grade_r4_evidence(
        rows,
        cleanup_by_mode={mode: "clean" for mode in runner.MODES},
        diagnostic_ok_by_mode={mode: True for mode in runner.MODES},
        repair_identity_by_mode=repair_identity,
        resolved_prefix_config_by_mode=resolved,
        token_lcp_evidence_ok=True,
    )
    assert green["server_grade"] == (
        "candidate_green_p6_3b_r4_explicit_prefix_cache_matched_ab"
    )
    assert green["prefix_cache_on_required_positive_hit_count"] == 9
    assert green["prefix_cache_on_boundary_positive_hit_count"] == 0
    assert green["prefix_cache_off_hit_delta_total"] == 0
    assert green["resolved_prefix_control_ok"] is True

    known_positive_row = next(
        row
        for row in rows
        if row["mode"] == "prefix_cache_on"
        and row["request_role"] == "measured"
        and row["group_id"] in runner.POSITIVE_HIT_GROUPS
    )
    known_positive_row["prefix_hits_delta"] = 0.0
    red = runner.grade_r4_evidence(
        rows,
        cleanup_by_mode={mode: "clean" for mode in runner.MODES},
        diagnostic_ok_by_mode={mode: True for mode in runner.MODES},
        repair_identity_by_mode=repair_identity,
        resolved_prefix_config_by_mode=resolved,
        token_lcp_evidence_ok=True,
    )
    assert red["server_grade"] == (
        "red_p6_3b_r4_explicit_prefix_cache_evidence_incomplete"
    )


def test_r4_prepare_records_actual_token_lcp_without_retaining_token_ids(tmp_path):
    runner = importlib.import_module(
        "tools.inference_contracts.run_deepseek_p6_3b_r4_explicit_matched_ab"
    )
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps({"prompt": list(range(4096))}), encoding="utf-8"
    )

    manifest = runner.prepare_r4_artifacts(
        source, tmp_path / "run", "deepseek-test"
    )
    measured = [
        row for row in manifest["records"] if row["request_role"] == "measured"
    ]

    assert len(measured) == 24
    assert all(row["actual_token_lcp"] >= row["planned_shared_tokens"] for row in measured)
    assert all(len(row["actual_lcp_sha256"]) == 64 for row in measured)
    assert all(
        row["expected_prefix_hit_tokens"]
        == row["actual_token_lcp"] // runner.HYBRID_LCM_TOKENS * runner.HYBRID_LCM_TOKENS
        for row in measured
    )
    assert manifest["token_lcp_evidence_ok"] is True
    assert manifest["generated_text_retained"] is False
    assert manifest["token_ids_retained"] is False
    manifest_text = (tmp_path / "run/request_body_manifest.json").read_text(
        encoding="utf-8"
    )
    assert '"prompt"' not in manifest_text


def test_r4_finalizer_writes_bounded_explicit_control_evidence(tmp_path):
    runner = importlib.import_module(
        "tools.inference_contracts.run_deepseek_p6_3b_r4_explicit_matched_ab"
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
            "lcm_block_size": runner.HYBRID_LCM_TOKENS,
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
            known_positive = item["group_id"] in runner.POSITIVE_HIT_GROUPS
            expected_hits = (
                item["target_shared_prefix_tokens"]
                // runner.HYBRID_LCM_TOKENS
                * runner.HYBRID_LCM_TOKENS
            )
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
                    "prefix_queries_delta": 32768.0 if mode == "prefix_cache_on" else 0.0,
                    "prefix_hits_delta": (
                        float(expected_hits)
                        if mode == "prefix_cache_on" and measured and known_positive
                        else 0.0
                    ),
                    "expected_prefix_hit_tokens": expected_hits,
                    "accepted_token_delta": 32.0,
                }
            )
        (mode_dir / "raw_request_results.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        mode_diagnostics = diagnostics[:2] if mode == "prefix_cache_off" else diagnostics
        (runtime_dir / "hybrid_kv_runtime_diagnostic.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in mode_diagnostics),
            encoding="utf-8",
        )
        (runtime_dir / "source_gate_status.txt").write_text("pass\n", encoding="utf-8")
        (runtime_dir / "resolved_prefix_cache_config.json").write_text(
            json.dumps(
                {
                    "resolved_enable_prefix_caching": mode == "prefix_cache_on",
                    "server_command_has_expected_flag": True,
                    "server_command_has_opposite_flag": False,
                    "process_cmdline_has_expected_flag": True,
                    "process_cmdline_has_opposite_flag": False,
                }
            ),
            encoding="utf-8",
        )
        (mode_dir / "repair_identity.tsv").write_text(
            repair_identity, encoding="utf-8"
        )
        (mode_dir / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")

    lcp_records = []
    for item in runner.build_run_plan():
        if item["request_role"] == "measured":
            lcp_records.append(
                {
                    **item,
                    "planned_shared_tokens": item["target_shared_prefix_tokens"],
                    "actual_token_lcp": item["target_shared_prefix_tokens"],
                    "actual_lcp_sha256": "a" * 64,
                    "expected_prefix_hit_tokens": (
                        item["target_shared_prefix_tokens"]
                        // runner.HYBRID_LCM_TOKENS
                        * runner.HYBRID_LCM_TOKENS
                    ),
                }
            )
    (tmp_path / "request_body_manifest.json").write_text(
        json.dumps(
            {
                "token_lcp_evidence_ok": True,
                "generated_text_retained": False,
                "token_ids_retained": False,
                "records": lcp_records,
            }
        ),
        encoding="utf-8",
    )

    grading = runner.finalize_artifacts(tmp_path)

    assert grading["server_grade"] == (
        "candidate_green_p6_3b_r4_explicit_prefix_cache_matched_ab"
    )
    assert grading["candidate_size_gate_pass"] is True
    assert grading["resolved_prefix_control_ok"] is True
    assert (tmp_path / "resolved_prefix_cache_config_summary.json").exists()
    assert "P6.3B-R4" in (tmp_path / "result_summary.md").read_text(
        encoding="utf-8"
    )
    candidates = (tmp_path / "delivery_candidates.tsv").read_text(
        encoding="utf-8"
    )
    assert "resolved_prefix_cache_config_summary.json" in candidates
    assert "generated_text" not in candidates
    assert "token_ids" not in candidates


def test_r4_workload_is_preserved_as_blocked_explicit_control_evidence():
    workload = yaml.safe_load(WORKLOAD_PATH.read_text(encoding="utf-8"))

    assert workload["stage_contract"]["stage"] == "P6.3B-R4"
    assert workload["mode_order"] == ["prefix_cache_off", "prefix_cache_on"]
    assert workload["single_variable"] == {
        "name": "enable_prefix_caching",
        "prefix_cache_off_flag": "--no-enable-prefix-caching",
        "prefix_cache_on_flag": "--enable-prefix-caching",
        "resolved_runtime_config_hard_gate": {"off": False, "on": True},
        "same_r2_repair_in_both_modes": True,
        "all_other_server_arguments_identical": True,
        "same_canonical_body_bytes_across_modes": True,
    }
    assert workload["lifecycle_plan"]["total_requests"] == 64
    assert workload["positive_hit_policy"]["hard_gate_groups"] == [
        "ctx32768_prefix90",
        "ctx65536_prefix90",
        "ctx131072_prefix90",
    ]
    assert workload["positive_hit_policy"]["hard_gate_measured_requests"] == 9
    assert workload["positive_hit_policy"]["boundary_measured_requests"] == 15
    assert workload["token_lcp_evidence"]["required"] is True
    assert workload["execution_state"] == {
        "status": "completed_blocked_source_or_resource_gate",
        "server_handoff": "historical",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
    }
    assert workload["execution_result"]["actual_server_lifecycles"] == 0
    assert workload["execution_result"]["request_count"] == 0
    assert workload["execution_result"]["cleanup"] == "clean"
    assert workload["stage_contract"]["p6_3c_execution_authorized"] is False


def test_r4_r1_closeout_is_preserved_during_r5_f0_feasibility():
    handoff = (REPO_ROOT / "通信模块/docs/developer-to-server.md").read_text(
        encoding="utf-8"
    )
    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert "P8.2-K1A-R5-F1-R9 runtime effective-group geometry" in handoff
    assert "npu_execution_authorized: true" in handoff
    assert "next_task_authorized: false" in handoff
    assert "model_request_count_max: 4" in handoff
    assert "runtime_or_dependency_mutation_authorized: false" in handoff
    assert "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab" in handoff
    assert "blocked_p6_3c_not_strict_single_variable" in handoff

    r3 = yaml.safe_load(
        (
            REPO_ROOT
            / "benchmarks/deepseek_v4_flash/workloads/"
            "p6_3b_r3_repaired_prefix_cache_matched_ab.yaml"
        ).read_text(encoding="utf-8")
    )
    assert r3["execution_result"]["server_grade"] == (
        "yellow_p6_3b_r3_repaired_prefix_cache_matched_ab_partial"
    )
    assert r3["execution_result"]["effective_comparison"] == (
        "repaired_prefix_cache_on_vs_on"
    )
    assert r3["execution_result"]["superseded_by"] == (
        "p6_3b_r4_explicit_prefix_cache_matched_ab.yaml"
    )
    assert r3["execution_state"]["npu_execution_authorized"] is False

    readiness = yaml.safe_load(
        (
            REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
        ).read_text(encoding="utf-8")
    )
    assert readiness["artifacts"]["completed_p6_3b_r3_workload"].endswith(
        "p6_3b_r3_repaired_prefix_cache_matched_ab.yaml"
    )
    assert readiness["artifacts"]["completed_p6_3b_r4_r1_workload"].endswith(
        "p6_3b_r4_r1_explicit_prefix_cache_matched_ab.yaml"
    )
    assert readiness["artifacts"]["completed_p8_2_k0_workload"].endswith(
        "p8_2_k0_order_balanced_prefix_cache_baseline.yaml"
    )
    assert readiness["artifacts"]["next_workload"].endswith(
            "p8_2_k1a_r5_f1_r9_effective_group_geometry.yaml"
    )
    assert readiness["acceptance"]["p6_3b_r3_grade"].startswith("yellow_")
    assert readiness["acceptance"]["p6_3b_r4_execution_authorized"] is False
    assert readiness["acceptance"]["p6_3b_r4_r1_grade"] == (
        "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab"
    )
    assert readiness["acceptance"]["p6_3b_r4_r1_execution_authorized"] is False
    assert readiness["acceptance"]["p6_3c_execution_authorized"] is False
    assert readiness["acceptance"]["p8_2_k0_execution_authorized"] is False
    assert readiness["acceptance"]["p8_2_k0_refinalization_authorized"] is False
    assert readiness["acceptance"]["p8_2_k1_feasibility_grade"] == (
        "blocked_p8_2_k1_frozen_stack_import_incompatible"
    )
    assert readiness["acceptance"]["p8_2_k1_execution_authorized"] is False


def test_r4_workload_freezes_the_published_runner_files():
    workload = yaml.safe_load(WORKLOAD_PATH.read_text(encoding="utf-8"))
    for key in ("runner", "mode_runner"):
        artifact = workload["runner_artifacts"][key]
        path = REPO_ROOT / artifact["path"]
        assert path.stat().st_size == artifact["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_r4_runner_supports_direct_file_execution_outside_the_repo(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(
                REPO_ROOT
                / "tools/inference_contracts/"
                "run_deepseek_p6_3b_r4_explicit_matched_ab.py"
            ),
            "--help",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "P6.3B-R4" in result.stdout
