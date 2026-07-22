from pathlib import Path
import hashlib
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p6_3c_chunked_prefill_feasibility_audit.yaml"
)


def bash_server_command_sha256(argv):
    command = subprocess.run(
        [
            "bash",
            "-c",
            'printf "%q " "$@"; printf "\\n"',
            "p6_3c_argv_audit",
            *argv,
        ],
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(command).hexdigest()


def test_frozen_p6_3c_is_blocked_before_runtime_by_vllm_validation():
    audit = yaml.safe_load(AUDIT_PATH.read_text(encoding="utf-8"))

    assert audit["stage"] == "P6.3C"
    assert audit["audit_status"] == "completed_local_frozen_source_audit"
    assert audit["grade"] == "blocked_p6_3c_not_strict_single_variable"
    assert audit["frozen_config"]["max_model_len"] == 135168
    assert audit["frozen_config"]["max_num_batched_tokens"] == 4096
    assert audit["validation_evaluation"] == {
        "chunked_prefill_off": True,
        "max_num_batched_tokens_less_than_max_model_len": True,
        "raises_value_error_before_resolved_runtime_config": True,
    }
    assert audit["formal_matched_ab_allowed"] is False


def test_audit_proves_explicit_cli_boolean_but_off_cannot_resolve():
    audit = yaml.safe_load(AUDIT_PATH.read_text(encoding="utf-8"))

    assert audit["runtime_pin"] == {
        "vllm_version": "0.22.1+empty",
        "vllm_commit": "0decac0d96c42b49572498019f0a0e3600f50398",
        "vllm_ascend_version": "0.22.1rc1",
        "vllm_ascend_commit": "5f6faa0cb8830f667266f3b8121cd1383606f2a1",
    }
    cli = audit["explicit_cli_control"]
    assert cli["on_flag"] == "--enable-chunked-prefill"
    assert cli["off_flag"] == "--no-enable-chunked-prefill"
    assert cli["argparse_action"] == "BooleanOptionalAction"
    assert cli["normalized_argv_delta_count"] == 1
    assert cli["normalized_argv_delta"] == {
        "chunked_prefill_off": "--no-enable-chunked-prefill",
        "chunked_prefill_on": "--enable-chunked-prefill",
    }

    sources = audit["frozen_source_evidence"]
    assert sources["vllm_arg_utils"]["sha256"] == (
        "ee107df77e59d1ca860d826feda540158bdefbdcaa3a2b786967396d83315d16"
    )
    assert sources["vllm_scheduler_config"]["sha256"] == (
        "c7d4cdd00bcf82be156d2affd170a2bb17ff0dce96af21c79734f01bcd11b049"
    )
    assert sources["vllm_ascend_scheduler_patch"]["sha256"] == (
        "3c7a4cae783f6a083fd0a3715c3c70ba9243ae2f3ae8668962378edee6d6ed3e"
    )
    assert sources["vllm_ascend_scheduler_patch"]["changes_scheduler_config_validation"] is False

    assert audit["resolved_config_gate"] == {
        "chunked_prefill_on": True,
        "chunked_prefill_off": "unavailable_validation_rejects_engine_config",
        "both_modes_resolved_before_requests": False,
    }
    assert audit["required_second_variable_escape"] == {
        "increase_max_num_batched_tokens_to_at_least": 135168,
        "or_decrease_max_model_len_to_at_most": 4096,
        "allowed_by_p6_3c_contract": False,
    }


def test_blocked_audit_freezes_reference_parity_without_creating_a_workload():
    audit = yaml.safe_load(AUDIT_PATH.read_text(encoding="utf-8"))

    frozen = audit["frozen_config"]
    assert frozen["model_object_id"] == "deepseek_v4_flash_w8a8_mtp_modelscope"
    assert frozen["quantization"] == "ascend"
    assert frozen["tensor_parallel_size"] == 8
    assert frozen["enable_expert_parallel"] is True
    assert frozen["speculative_config"] == {
        "method": "mtp",
        "num_speculative_tokens": 1,
    }
    assert frozen["cudagraph_mode"] == "FULL_DECODE_ONLY"
    assert frozen["max_num_seqs"] == 1
    assert frozen["block_size"] == 128
    assert frozen["prefix_cache_flag_both_modes"] == "--enable-prefix-caching"
    assert frozen["primary_cell"] == {
        "context_tokens": 131072,
        "output_tokens": 64,
        "concurrency": 1,
    }

    normalized = audit["candidate_normalized_server_argv"]
    before = normalized["before_chunked_prefill_flag"]
    after = normalized["after_chunked_prefill_flag"]
    off_argv = before + [normalized["chunked_prefill_off_flag"]] + after
    on_argv = before + [normalized["chunked_prefill_on_flag"]] + after
    delta_indices = [
        index
        for index, (off_arg, on_arg) in enumerate(zip(off_argv, on_argv))
        if off_arg != on_arg
    ]
    assert len(off_argv) == len(on_argv)
    assert delta_indices == [len(before)]
    assert off_argv[delta_indices[0]] == "--no-enable-chunked-prefill"
    assert on_argv[delta_indices[0]] == "--enable-chunked-prefill"
    assert "--enable-prefix-caching" in off_argv
    assert "--enable-prefix-caching" in on_argv
    assert normalized["serialization"] == "bash_printf_percent_q_space_plus_newline"

    assert audit["candidate_server_command_sha256"] == {
        "chunked_prefill_off": "46728ac6b0be753670c96021a9292469df0c78437d4e60d1e0458cbdf9b63507",
        "chunked_prefill_on": "370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19",
        "chunked_prefill_on_matches_current_reference": True,
        "hashes_are_a_local_normalization_audit_not_execution_evidence": True,
    }
    assert bash_server_command_sha256(off_argv) == audit[
        "candidate_server_command_sha256"
    ]["chunked_prefill_off"]
    assert bash_server_command_sha256(on_argv) == audit[
        "candidate_server_command_sha256"
    ]["chunked_prefill_on"]

    for artifact in audit["reference_artifacts"].values():
        path = REPO_ROOT / artifact["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]

    assert audit["execution_boundary"] == {
        "executable_workload_created": False,
        "mode_runner_created": False,
        "request_bodies_created": False,
        "server_task_created": False,
        "npu_execution_authorized": False,
        "next_task_authorized": False,
        "npu_or_vllm_started": False,
        "requests_sent": 0,
    }
    assert not list(
        (REPO_ROOT / "benchmarks/deepseek_v4_flash/workloads").glob("p6_3c*.yaml")
    )


def test_current_truth_surfaces_keep_p6_3c_blocked_during_k1a_review():
    readiness = yaml.safe_load(
        (
            REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
        ).read_text(encoding="utf-8")
    )
    assert readiness["artifacts"]["p6_3c_feasibility_audit"].endswith(
        "p6_3c_chunked_prefill_feasibility_audit.yaml"
    )
    assert readiness["artifacts"]["completed_p8_2_k0_workload"].endswith(
        "p8_2_k0_order_balanced_prefix_cache_baseline.yaml"
    )
    assert readiness["artifacts"]["next_workload"].endswith(
        "p8_2_k1a_r5_f1_r1_request_local_pressure_conditional_lifecycle.yaml"
    )
    assert readiness["artifacts"]["next_stage_candidate"] == (
        "P8.2-K1A-R5-F1-R1_request_local_progress_then_conditional_fixed_L2"
    )
    assert readiness["acceptance"]["p6_3c_feasibility_grade"] == (
        "blocked_p6_3c_not_strict_single_variable"
    )
    assert readiness["acceptance"]["p6_3c_execution_authorized"] is False
    assert readiness["acceptance"]["p8_1_execution_authorized"] is False
    assert readiness["acceptance"]["p8_1_r1_execution_authorized"] is False
    assert readiness["acceptance"]["p8_2_k0_execution_authorized"] is False
    assert readiness["acceptance"]["p8_2_k0_refinalization_authorized"] is False
    assert readiness["acceptance"]["p8_2_k1_feasibility_grade"] == (
        "blocked_p8_2_k1_frozen_stack_import_incompatible"
    )
    assert readiness["acceptance"]["p8_2_k1_execution_authorized"] is False
    assert readiness["acceptance"]["p8_2_k1a_execution_authorized"] is False
    assert readiness["acceptance"]["p8_2_k1a_r1_allocator_probe_authorized"] is False
    assert readiness["acceptance"]["p8_2_k1a_r2_allocator_probe_authorized"] is False
    assert readiness["acceptance"]["p8_2_k1a_r3_execution_authorized"] is False
    assert readiness["acceptance"]["p8_2_k1a_r3_r2_execution_authorized"] is False
    assert readiness["acceptance"]["p8_2_k1a_r3_r2_r1_execution_authorized"] is False
    assert readiness["acceptance"]["p8_2_k1a_r3_r2_r2_execution_authorized"] is False
    assert readiness["acceptance"]["p8_2_k1a_r3_r2_r2_r1_execution_authorized"] is False
    assert readiness["acceptance"]["p8_2_k1a_r3_r2_r2_r1_r1_execution_authorized"] is False
    assert readiness["acceptance"]["p8_2_k1a_r3_r2_r2_r1_r1_r1_execution_authorized"] is False
    assert readiness["acceptance"]["p8_2_k1a_r4_offline_closeout_authorized"] is True
    assert readiness["acceptance"]["p8_2_k1a_r4_npu_execution_authorized"] is False
    assert readiness["acceptance"]["next_task_authorized"] is False

    handoff = (REPO_ROOT / "通信模块/docs/developer-to-server.md").read_text(
        encoding="utf-8"
    )
    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert "task_id: p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722" in handoff
    assert "execution_mode: authorized_parent_legacy_then_one_calibration_then_conditional_fixed_l2" in handoff
    assert "npu_execution_authorized: conditional" in handoff
    assert "next_task_authorized: false" in handoff
    assert "runtime_or_dependency_mutation_authorized: false" in handoff
    assert "green_p8_1_r1_official_mtp_observe_only_matrix" in handoff
    assert "model_request_count_max: 4" in handoff

    truth_paths = (
        REPO_ROOT / "docs/EXPERIMENT_PLAN.md",
        REPO_ROOT / "docs/DEEPSEEK_V4_FLASH_ASCEND_PLAN.md",
        REPO_ROOT / "工作记录与进度笔记本/02_阶段计划.md",
        REPO_ROOT / "工作记录与进度笔记本/05_下一步行动指导.md",
        REPO_ROOT / "工作记录与进度笔记本/16_P6_阶段复盘与P6_3进入评估.md",
    )
    for path in truth_paths:
        text = path.read_text(encoding="utf-8")
        assert "blocked_p6_3c_not_strict_single_variable" in text, path

    assert "4096 < 135168" in (
        REPO_ROOT / "docs/DEEPSEEK_V4_FLASH_ASCEND_PLAN.md"
    ).read_text(encoding="utf-8")
