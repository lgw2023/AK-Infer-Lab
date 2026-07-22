from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
P8_PLAN = REPO_ROOT / "docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md"
P5_P9_PLAN = REPO_ROOT / "工作记录与进度笔记本/12_P5_P9_后续阶段重排计划.md"


def test_current_plans_route_only_f1_r5_and_keep_later_stages_closed() -> None:
    p8_plan = P8_PLAN.read_text(encoding="utf-8")
    p5_p9_plan = P5_P9_PLAN.read_text(encoding="utf-8")
    task_id = "p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723"

    assert task_id in p8_plan
    assert task_id in p5_p9_plan
    assert "当前 handoff 只授权 P8.3-I0-R1" not in p8_plan
    assert "当前只读服务器 section 物化真实 checkpoint inventory" not in p8_plan
    assert "K1A-R3 formal lifecycle current" not in p5_p9_plan
    assert "K1A-R3-R2 source-contract blocked" in p5_p9_plan
    assert "K1A-R3-R2-R1 runtime partial yellow" in p5_p9_plan
    assert "K1A-R3-R2-R2-R1 source/observer gate blocked" in p5_p9_plan
    assert "K1A-R3-R2-R2-R1-R1-R1 store-only yellow" in p5_p9_plan
    assert "K1A-R4 source-matcher blocked" in p5_p9_plan
    assert "K1A-R4-R1 offline store-only closeout green" in p5_p9_plan
    assert "K1A-R5-F0 feasibility ready" in p5_p9_plan
    assert "K1A-R5-F1-R4 effective-target-overridden invalid -> K1A-R5-F1-R5 runtime-keyspace-probe invalid -> K1A-R5-F1-R6 logical-keyspace restore current" in p5_p9_plan
    assert "P8.3-I0/I0-R1 已在窄边界 green且 budget incomplete" in p5_p9_plan
    assert "P8.3-I1 Level-A hotness trace 必须另行授权" in p5_p9_plan
    for artifact in (
        "p8_2_k1a_r3_r2_portable_argv_audit.yaml",
        "p8_2_k1a_r3_r2_r1_installed_source_gate_audit.yaml",
        "p8_2_k1a_r3_r2_r2_forensic_replay_audit.yaml",
        "p8_2_k1a_r3_r2_r2_r1_observer_contract_audit.yaml",
        "p8_2_k1a_r3_r2_r2_r1_r1_source_binding_provenance_audit.yaml",
        "p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_replay_audit.yaml",
        "p8_2_k1a_r4_store_only_refinalization_audit.yaml",
        "p8_2_k1a_r4_r1_source_semantics_replay_audit.yaml",
        "p8_2_k1a_r5_f0_h2d_trigger_feasibility_audit.yaml",
        "p8_2_k1a_r5_l1_lazy_h2d_lifecycle_audit.yaml",
        "p8_2_k1a_r5_l1_r1_lazy_h2d_lifecycle_audit.yaml",
        "p8_2_k1a_r5_f1_pressure_window_audit.yaml",
        "p8_2_k1a_r5_f1_r1_request_local_pressure_audit.yaml",
        "p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_audit.yaml",
        "p8_2_k1a_r5_f1_r5_effective_restore_contract_audit.yaml",
        "p8_2_k1a_r5_f1_r6_logical_keyspace_restore_audit.yaml",
        "p8_3_i0_r1_inventory_taxonomy_audit.yaml",
        "canonicalize_server_argv.py",
        "p8_2_k1a_trace_attribution.py",
        "p8_2_k1a_h2d_trigger_feasibility.py",
        "p8_2_k1a_h2d_residency_observer.py",
        "p8_2_k1a_r5_f1_pressure_window.py",
        "run_deepseek_p8_2_k1a_r5_f1_pressure_window.sh",
        "run_deepseek_p8_2_k1a_r5_l2_fixed_pressure.sh",
        "p8_2_k1a_r5_f1_r1_request_local_pressure.py",
        "run_deepseek_p8_2_k1a_r5_f1_r1_request_local_pressure.sh",
        "run_deepseek_p8_2_k1a_r5_f1_r1_request_local_calibration.sh",
        "run_deepseek_p8_2_k1a_r5_f1_r1_fixed_pressure_l2.sh",
        "run_deepseek_p8_2_k1a_r5_f0_h2d_trigger_feasibility.sh",
        "run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh",
        "run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh",
        "run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.sh",
        "run_deepseek_p8_2_k1a_r5_f1_r5_server_task.sh",
        "run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh",
        "run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh",
    ):
        assert artifact in p8_plan
