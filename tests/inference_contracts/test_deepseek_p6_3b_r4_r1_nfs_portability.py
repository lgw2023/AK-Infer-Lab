import hashlib
import importlib
from pathlib import Path
import subprocess
import sys

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
MODE_RUNNER_PATH = (
    REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3b_r4_r1_mode.sh"
)
R4_MODE_RUNNER_PATH = (
    REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3b_r4_mode.sh"
)
WORKLOAD_PATH = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3b_r4_r1_explicit_prefix_cache_matched_ab.yaml"
)
R4_WORKLOAD_PATH = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3b_r4_explicit_prefix_cache_matched_ab.yaml"
)
RUNNER_PATH = (
    REPO_ROOT
    / "tools/inference_contracts/run_deepseek_p6_3b_r4_r1_explicit_matched_ab.py"
)


def test_r4_r1_overlay_copy_is_safe_on_root_squashed_nfs():
    runner = MODE_RUNNER_PATH.read_text(encoding="utf-8")
    historical_r4 = R4_MODE_RUNNER_PATH.read_text(encoding="utf-8")

    assert 'command cp -a --no-preserve=ownership "$2" "$3"' in runner
    assert "export -f cp" in runner
    assert "run_deepseek_p6_3b_r4_mode.sh" in runner
    assert 'cp -a "${BASE_PLUGIN_ROOT}"' in historical_r4
    assert "--no-preserve=ownership" not in historical_r4


def test_r4_r1_runner_reports_the_independent_task_identity(tmp_path):
    result = subprocess.run(
        [sys.executable, str(RUNNER_PATH), "--help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "P6.3B-R4-R1" in result.stdout
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    module = importlib.import_module(
        "tools.inference_contracts."
        "run_deepseek_p6_3b_r4_r1_explicit_matched_ab"
    )
    assert module.TASK_ID == (
        "p6_3b_r4_r1_deepseek_v4_flash_w8a8_mtp_explicit_"
        "prefix_cache_matched_ab_2026_0716"
    )
    assert "candidate_green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab" in runner


def test_r4_r1_finalizer_relabels_and_rehashes_parent_r4_evidence(
    tmp_path, monkeypatch
):
    module = importlib.import_module(
        "tools.inference_contracts."
        "run_deepseek_p6_3b_r4_r1_explicit_matched_ab"
    )
    parent_grade = "candidate_green_p6_3b_r4_explicit_prefix_cache_matched_ab"

    def fake_parent_finalize(artifact_dir):
        for name in module.CANDIDATE_NAMES:
            if name == "grading_inputs.json":
                continue
            (artifact_dir / name).write_text("placeholder\n", encoding="utf-8")
        (artifact_dir / "result_summary.md").write_text(
            "# P6.3B-R4 explicit result\n"
            "- task_id: p6_3b_r4_deepseek_v4_flash_w8a8_mtp_explicit_"
            "prefix_cache_matched_ab_2026_0716\n"
            f"- server_grade: {parent_grade}\n",
            encoding="utf-8",
        )
        (artifact_dir / "environment_and_hashes.json").write_text(
            "{}\n", encoding="utf-8"
        )
        (artifact_dir / "first_failure_excerpt.txt").write_text(
            parent_grade + "\n", encoding="utf-8"
        )
        return {"server_grade": parent_grade}

    monkeypatch.setattr(module.r4, "finalize_artifacts", fake_parent_finalize)
    grading = module.finalize_artifacts(tmp_path)

    assert grading["server_grade"] == module.CANDIDATE_GREEN
    assert grading["task_id"] == module.TASK_ID
    assert grading["candidate_size_gate_pass"] is True
    summary = (tmp_path / "result_summary.md").read_text(encoding="utf-8")
    assert "P6.3B-R4-R1" in summary
    assert module.TASK_ID in summary
    assert module.CANDIDATE_GREEN in summary
    assert (tmp_path / "server_grade.txt").read_text(encoding="utf-8").strip() == (
        module.CANDIDATE_GREEN
    )
    manifest = (tmp_path / "delivery_candidates.tsv").read_text(encoding="utf-8")
    assert manifest.count("\n") == len(module.CANDIDATE_NAMES) + 1


def test_r4_r1_is_completed_without_erasing_the_blocked_r4_lineage():
    workload = yaml.safe_load(WORKLOAD_PATH.read_text(encoding="utf-8"))
    historical_r4 = yaml.safe_load(R4_WORKLOAD_PATH.read_text(encoding="utf-8"))

    assert workload["stage_contract"]["stage"] == "P6.3B-R4-R1"
    assert workload["task_id"].startswith("p6_3b_r4_r1_")
    assert workload["accepted_prerequisites"]["r4_grade"] == (
        "blocked_p6_3b_r4_source_or_resource_gate"
    )
    assert workload["accepted_prerequisites"]["r4_actual_server_lifecycles"] == 0
    assert workload["accepted_prerequisites"]["r4_requests_sent"] == 0
    assert workload["root_squash_portability_repair"] == {
        "filesystem": "nfs4_sec_sys_root_squash",
        "failing_copy": "cp_-a_preserve_ownership",
        "replacement_copy": "cp_-a_--no-preserve=ownership",
        "content_hash_semantics_unchanged": True,
        "runtime_or_request_semantics_unchanged": True,
    }
    assert workload["lifecycle_plan"]["total_requests"] == 64
    assert workload["acceptance"]["server_candidate_green_grade"] == (
        "candidate_green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab"
    )
    assert workload["execution_state"] == {
        "status": "completed_developer_accepted_green",
        "server_handoff": "historical",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
    }
    assert workload["execution_result"]["developer_grade"] == (
        "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab"
    )
    for artifact in workload["runner_artifacts"].values():
        path = REPO_ROOT / artifact["path"]
        assert path.stat().st_size == artifact["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]

    assert historical_r4["execution_result"]["server_grade"] == (
        "blocked_p6_3b_r4_source_or_resource_gate"
    )
    assert historical_r4["execution_result"]["actual_server_lifecycles"] == 0
    assert historical_r4["execution_result"]["request_count"] == 0
    assert historical_r4["execution_result"]["cleanup"] == "clean"
    assert historical_r4["execution_result"]["superseded_by"] == WORKLOAD_PATH.name
    assert historical_r4["execution_state"]["npu_execution_authorized"] is False
    assert historical_r4["execution_state"]["next_task_authorized"] is False


def test_r4_r1_closeout_is_preserved_in_the_unique_r5_f0_task():
    handoff = (REPO_ROOT / "通信模块/docs/developer-to-server.md").read_text(
        encoding="utf-8"
    )
    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert "P8.2-K1A-R5-F1-R4 完整恢复资格对齐" in handoff
    assert "task_id: p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_2026_0722" in handoff
    assert "npu_execution_authorized: true" in handoff
    assert "next_task_authorized: false" in handoff
    assert "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab" in handoff
    assert "blocked_p6_3c_not_strict_single_variable" in handoff

    readiness = yaml.safe_load(
        (
            REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
        ).read_text(encoding="utf-8")
    )
    assert readiness["artifacts"]["completed_p6_3b_r4_workload"].endswith(
        "p6_3b_r4_explicit_prefix_cache_matched_ab.yaml"
    )
    assert readiness["artifacts"]["completed_p6_3b_r4_r1_workload"].endswith(
        "p6_3b_r4_r1_explicit_prefix_cache_matched_ab.yaml"
    )
    assert readiness["artifacts"]["completed_p8_2_k0_workload"].endswith(
        "p8_2_k0_order_balanced_prefix_cache_baseline.yaml"
    )
    assert readiness["artifacts"]["next_workload"].endswith(
        "p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.yaml"
    )
    assert readiness["acceptance"]["p6_3b_r4_grade"] == (
        "blocked_p6_3b_r4_source_or_resource_gate"
    )
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

    truth_paths = (
        REPO_ROOT / "docs/EXPERIMENT_PLAN.md",
        REPO_ROOT / "工作记录与进度笔记本/02_阶段计划.md",
        REPO_ROOT / "工作记录与进度笔记本/05_下一步行动指导.md",
        REPO_ROOT / "工作记录与进度笔记本/09_DeepSeek_V4_Flash_专项计划.md",
        REPO_ROOT / "工作记录与进度笔记本/12_P5_P9_后续阶段重排计划.md",
    )
    for path in truth_paths:
        text = path.read_text(encoding="utf-8")
        assert "P6.3B-R4-R1" in text, path
        assert "root-squash" in text, path
