from html.parser import HTMLParser
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = (
    REPO_ROOT
    / "工作记录与进度笔记本/"
    "DeepSeek_V4_Flash_W8A8_8NPU_性能总览_修订版.html"
)
WORKLOAD_PATH = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3b_r4_r1_explicit_prefix_cache_matched_ab.yaml"
)


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _visible_text(path: Path) -> str:
    parser = _VisibleText()
    parser.feed(path.read_text(encoding="utf-8"))
    return " ".join(" ".join(parser.parts).split())


def test_dashboard_exposes_the_accepted_r4_r1_prefix_cache_evidence():
    html = DASHBOARD_PATH.read_text(encoding="utf-8")
    text = _visible_text(DASHBOARD_PATH)

    assert "P6.3B-R4-R1" in text
    assert "64 / 64" in text
    assert "9 / 9" in text
    assert "Off hit=0" in text
    assert html.count("data-prefix-row=") == 8
    assert "29,440 / 16,384" in text
    assert "58,880 / 49,152" in text
    assert "117,889 / 114,688" in text
    assert "3,199.4 → 1,645.7" in text
    assert "6,399.3 → 1,734.6" in text
    assert "12,826.0 → 1,873.7" in text
    assert "−48.6%" in text
    assert "−72.9%" in text
    assert "−85.4%" in text
    assert "其余 15 条 boundary 仍为零命中" in text
    assert "不是普遍 Prefix Cache 性能收益" in text
    assert html.count('class="summary-item"') == 4
    assert "显式 Prefix Cache 开关产生了可观测机制效应" in text


def test_r4_r1_workload_is_closed_as_developer_accepted_green():
    workload = yaml.safe_load(WORKLOAD_PATH.read_text(encoding="utf-8"))
    result = workload["execution_result"]

    assert result["server_grade"] == (
        "candidate_green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab"
    )
    assert result["developer_grade"] == (
        "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab"
    )
    assert result["requests"] == "64_of_64"
    assert result["prefix_cache_off_hit_delta_total"] == 0
    assert result["prefix_cache_on_primary_positive_hit_count"] == "9_of_9"
    assert result["prefix_cache_on_boundary_positive_hit_count"] == "0_of_15"
    assert result["mechanism_effect_accepted"] is True
    assert result["performance_effect_accepted"] is False
    assert result["aborted_pre_request_invocations"] == 1
    assert result["aborted_pre_request_request_count"] == 0
    assert result["final_measured_server_lifecycles"] == 2
    assert result["cleanup"] == "clean"
    assert result["result_package"] == {"files": 10, "bytes": 44550}

    assert workload["execution_state"] == {
        "status": "completed_developer_accepted_green",
        "server_handoff": "historical",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
    }


def test_current_handoff_and_truth_surfaces_wait_after_r4_r1_closeout():
    handoff = (REPO_ROOT / "通信模块/docs/developer-to-server.md").read_text(
        encoding="utf-8"
    )
    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert "只读同步复核并等待，不执行 NPU" in handoff
    assert "task_id: p6_3c_strict_single_variable_blocked_closeout_sync_review_2026_0716" in handoff
    assert "server_sync_review_authorized: true" in handoff
    assert "execution_mode: authorized_read_only_sync_review_and_wait_no_npu" in handoff
    assert "npu_execution_authorized: false" in handoff
    assert "next_task_authorized: false" in handoff
    assert "standing_npu_and_vllm_consumption_authorization: true" in handoff
    assert "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab" in handoff
    assert "blocked_p6_3c_not_strict_single_variable" in handoff
    assert "vllm serve" not in handoff
    assert "upload-api" not in handoff

    readiness = yaml.safe_load(
        (
            REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
        ).read_text(encoding="utf-8")
    )
    assert readiness["artifacts"]["completed_p6_3b_r4_r1_workload"].endswith(
        "p6_3b_r4_r1_explicit_prefix_cache_matched_ab.yaml"
    )
    assert readiness["artifacts"]["next_workload"] is None
    assert readiness["acceptance"]["p6_3b_r4_r1_grade"] == (
        "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab"
    )
    assert readiness["acceptance"]["p6_3b_r4_r1_execution_authorized"] is False
    assert readiness["acceptance"]["p6_3b_mechanism_baseline"] is True
    assert readiness["acceptance"]["p6_3c_execution_authorized"] is False
    assert readiness["acceptance"]["next_task_authorized"] is False
    assert (
        readiness["acceptance"]["standing_npu_and_vllm_consumption_authorization"]
        is True
    )

    truth_paths = (
        REPO_ROOT / "docs/EXPERIMENT_PLAN.md",
        REPO_ROOT / "工作记录与进度笔记本/02_阶段计划.md",
        REPO_ROOT / "工作记录与进度笔记本/05_下一步行动指导.md",
        REPO_ROOT / "工作记录与进度笔记本/09_DeepSeek_V4_Flash_专项计划.md",
        REPO_ROOT / "工作记录与进度笔记本/12_P5_P9_后续阶段重排计划.md",
        REPO_ROOT / "工作记录与进度笔记本/16_P6_阶段复盘与P6_3进入评估.md",
    )
    for path in truth_paths:
        text = path.read_text(encoding="utf-8")
        assert "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab" in text, path
        assert "P6.3C" in text, path
        assert "blocked_p6_3c_not_strict_single_variable" in text, path
