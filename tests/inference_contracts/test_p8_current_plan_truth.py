from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
P8_PLAN = REPO_ROOT / "docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md"
P5_P9_PLAN = REPO_ROOT / "工作记录与进度笔记本/12_P5_P9_后续阶段重排计划.md"


def test_current_plans_route_only_r3_r2_r2_r1_and_keep_the_expert_budget_open() -> None:
    p8_plan = P8_PLAN.read_text(encoding="utf-8")
    p5_p9_plan = P5_P9_PLAN.read_text(encoding="utf-8")
    task_id = (
        "p8_2_k1a_r3_r2_r2_r1_deepseek_v4_flash_observer_contract_replay_"
        "2026_0720"
    )

    assert task_id in p8_plan
    assert task_id in p5_p9_plan
    assert "当前 handoff 只授权 P8.3-I0-R1" not in p8_plan
    assert "当前只读服务器 section 物化真实 checkpoint inventory" not in p8_plan
    assert "K1A-R3 formal lifecycle current" not in p5_p9_plan
    assert "K1A-R3-R2 source-contract blocked" in p5_p9_plan
    assert "K1A-R3-R2-R1 runtime partial yellow" in p5_p9_plan
    assert "K1A-R3-R2-R2-R1 observer-contract replay authorized" in p5_p9_plan
    assert "P8.3-I0/I0-R1 已在窄边界 green且 budget incomplete" in p5_p9_plan
    assert "P8.3-I1 Level-A hotness trace 必须另行授权" in p5_p9_plan
    for artifact in (
        "p8_2_k1a_r3_r2_portable_argv_audit.yaml",
        "p8_2_k1a_r3_r2_r1_installed_source_gate_audit.yaml",
        "p8_2_k1a_r3_r2_r2_forensic_replay_audit.yaml",
        "p8_2_k1a_r3_r2_r2_r1_observer_contract_audit.yaml",
        "p8_3_i0_r1_inventory_taxonomy_audit.yaml",
        "canonicalize_server_argv.py",
    ):
        assert artifact in p8_plan
