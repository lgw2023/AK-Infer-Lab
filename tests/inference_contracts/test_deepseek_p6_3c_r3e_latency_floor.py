from __future__ import annotations

from pathlib import Path

from tools.inference_contracts import (
    run_deepseek_p6_3c_r3e_latency_floor as runner,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _mixed_row(
    lifecycle_id: str,
    config_id: str,
    executor_ms: float,
    total_ms: float,
) -> dict[str, object]:
    return {
        "lifecycle_id": lifecycle_id,
        "config_id": config_id,
        "step_class": "mixed_prefill_decode",
        "timing_complete": True,
        "scheduler_cpu_ms": 1.0,
        "executor_submit_cpu_ms": 0.2,
        "execute_model_future_ms": executor_ms * 0.8,
        "engine_pipeline_ms": executor_ms,
        "scheduler_update_cpu_ms": 1.0,
        "schedule_to_update_complete_ms": total_ms,
        "engine_pipeline_fraction_of_step": executor_ms / total_ms,
    }


def test_r3e_reuses_scientific_request_contract_but_changes_measurement_object() -> None:
    assert len(runner.LIFECYCLE_SCHEDULE) == 5
    assert runner.HOST_LIFECYCLE_IDS == ("host_01", "host_02", "host_03")
    assert runner.PROFILE_LIFECYCLE_IDS == ("profile_01", "profile_02")
    assert {row["mode"] for row in runner.LIFECYCLE_SCHEDULE} == {
        "chunked_prefill_on"
    }
    assert {row["max_num_batched_tokens"] for row in runner.LIFECYCLE_SCHEDULE} == {
        12288
    }
    assert runner.EXPECTED_ENGINE_REQUESTS == 50
    assert runner.EXPECTED_HTTP_REQUESTS == 15


def test_host_summary_identifies_executor_dominated_target_insensitive_floor() -> None:
    rows = [
        _mixed_row("host_01", "admission_on_t4096", 400.0, 405.0),
        _mixed_row("host_02", "persistent_on_t1024", 410.0, 415.0),
        _mixed_row("host_03", "persistent_on_t128", 420.0, 425.0),
    ]

    summary, groups = runner.summarize_host_timing_rows(rows)

    assert len(groups) == 3
    assert summary["host_timing_complete"] is True
    assert summary["mixed_engine_pipeline_fraction_at_least_0_80"] is True
    assert summary["persistent_mixed_pipeline_target_insensitive"] is True
    assert summary["persistent_t128_to_t1024_pipeline_median_ratio"] == 1.02439
    assert summary["host_scheduler_and_update_dominant"] is False


def test_host_summary_fails_closed_when_one_policy_has_no_correlated_step() -> None:
    rows = [
        _mixed_row("host_01", "admission_on_t4096", 400.0, 405.0),
        _mixed_row("host_02", "persistent_on_t1024", 410.0, 415.0),
    ]

    summary, _ = runner.summarize_host_timing_rows(rows)

    assert summary["host_timing_complete"] is False
    assert summary["mixed_engine_pipeline_fraction_at_least_0_80"] is False


def test_profiler_categories_preserve_collective_and_compute_attribution() -> None:
    assert runner._op_category("HcomAllReduce") == "collective_communication"  # noqa: SLF001
    assert runner._op_category("GroupedMatmul") == "matmul_or_moe"  # noqa: SLF001
    assert runner._op_category("FlashAttentionScore") == "attention"  # noqa: SLF001
    assert runner._op_category("MemcpyAsync") == "memory_transfer_or_sync"  # noqa: SLF001


def test_r3e_profiler_is_diagnostic_and_audit_contract_is_zero_npu() -> None:
    base_mode = (
        REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh"
    ).read_text(encoding="utf-8")
    experiment = (
        REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3c_r3e_experiment.sh"
    ).read_text(encoding="utf-8")
    workload = (
        REPO_ROOT
        / "benchmarks/deepseek_v4_flash/workloads/"
        "p6_3c_r3e_mixed_step_latency_floor_attribution.yaml"
    ).read_text(encoding="utf-8")
    smoke = (
        REPO_ROOT / "tools/inference_contracts/smoke_p6_3c_runtime_overlay.py"
    ).read_text(encoding="utf-8")

    assert "--msproftx=on" in base_mode
    assert "P6_3C_DIAGNOSTIC_MSPROF" in base_mode
    assert "P6_3C_AUDIT_ONLY" in experiment
    assert experiment.index("host-gate") < experiment.index("diagnostic_msprof || continue")
    assert "performance_comparison_allowed: false" in workload
    assert 'guard_callable_name = "update_full_graph_params"' in smoke
