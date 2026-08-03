from __future__ import annotations

import json
from pathlib import Path

from tools.inference_contracts.p6_3c_r3_decode_resident_observer import (
    request_phase,
    summarize_r3_scheduler_rows,
)
from tools.inference_contracts.run_deepseek_p6_3c_r3a_decode_resident import (
    EXPECTED_ENGINE_REQUESTS,
    EXPECTED_HTTP_REQUESTS,
    PERFORMANCE_CELL_SEQUENCE,
    RESIDENT_COUNT,
    TASK_ID,
    _scientific_outcome,
    build_run_plan,
    mechanism_scout_summary,
    paired_bootstrap_median_ci,
    prepare_artifacts,
)


def test_run_plan_encodes_the_scientific_sample_matrix() -> None:
    plan = build_run_plan()
    mechanism = plan["trials"]["mechanism"]
    performance = plan["trials"]["performance"]

    assert [row["cell_id"] for row in mechanism] == [
        "resident_only",
        "fit_control_12000",
        "admission_cliff_12281",
    ]
    assert [row["cell_id"] for row in performance] == list(PERFORMANCE_CELL_SEQUENCE)
    assert len(performance) == 18
    assert all(
        sum(row["cell_id"] == cell_id for row in performance) == 6
        for cell_id in (
            "resident_only",
            "fit_control_12000",
            "admission_cliff_12281",
        )
    )
    mechanism_engine_requests = 1 + 3 * RESIDENT_COUNT + 2
    performance_engine_requests = 1 + 18 * RESIDENT_COUNT + 12
    mechanism_http_requests = 1 + 3 + 2
    performance_http_requests = 1 + 18 + 12
    assert 2 * mechanism_engine_requests + 4 * performance_engine_requests == (
        EXPECTED_ENGINE_REQUESTS
    )
    assert 2 * mechanism_http_requests + 4 * performance_http_requests == (
        EXPECTED_HTTP_REQUESTS
    )


def test_prepare_materializes_exact_payload_lengths(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    artifact_dir = tmp_path / "artifact"

    manifest = prepare_artifacts(source, artifact_dir, "test-model")

    assert manifest["body_record_count"] == 37
    assert len(list((artifact_dir / "bodies").glob("*.json"))) == 37
    cliff_records = [
        row
        for row in manifest["records"]
        if row.get("cell_id") == "admission_cliff_12281"
        and row["request_role"] == "injected"
    ]
    assert len(cliff_records) == 7
    assert all(row["prompt_token_lengths"] == [12281] for row in cliff_records)


def _scheduler_row(
    *,
    trial_id: str,
    injected_tokens: int | None,
    partial: bool,
    mixed: bool,
) -> dict[str, object]:
    resident_ids = [
        f"cmpl-{trial_id}_resident-{index}-a1b2c3d4" for index in range(RESIDENT_COUNT)
    ]
    injected_id = f"cmpl-{trial_id}_injected-a1b2c3d4"
    scheduled = [
        {
            "request_id": request_id,
            "phase": "resident_decode",
            "scheduled_tokens": 2,
            "scheduled_prefill_tokens": 0,
            "scheduled_decode_tokens": 2,
            "prefill_partial": False,
        }
        for request_id in resident_ids
    ]
    if injected_tokens:
        scheduled.append(
            {
                "request_id": injected_id,
                "phase": "injected_prefill",
                "scheduled_tokens": injected_tokens,
                "scheduled_prefill_tokens": injected_tokens,
                "scheduled_decode_tokens": 0,
                "prefill_partial": partial,
            }
        )
    return {
        "event": "scheduler_step",
        "step_index": 10,
        "running_order_before": resident_ids,
        "waiting_order_before": [injected_id]
        if "resident_only" not in trial_id
        else [],
        "resident_decode_tokens": 16,
        "injected_prefill_tokens": injected_tokens or 0,
        "mixed_decode_prefill": mixed,
        "preempted_request_ids": [],
        "scheduled_requests": scheduled,
    }


def _write_mechanism_trace(root: Path, lifecycle_id: str, mode: str) -> None:
    trace_dir = root / "lifecycles" / lifecycle_id / "runtime/scheduler_trace"
    trace_dir.mkdir(parents=True)
    rows: list[dict[str, object]] = [
        {
            "event": "observer_installed",
            "schema": "p6_3c_r3_decode_resident_v1",
        }
    ]
    resident_trial = "p6_3c_r3a_mechanism_resident_only_r01"
    rows.append(
        _scheduler_row(
            trial_id=resident_trial,
            injected_tokens=None,
            partial=False,
            mixed=False,
        )
    )
    fit_trial = "p6_3c_r3a_mechanism_fit_control_12000_r01"
    rows.append(
        _scheduler_row(
            trial_id=fit_trial,
            injected_tokens=12000,
            partial=False,
            mixed=True,
        )
    )
    cliff_trial = "p6_3c_r3a_mechanism_admission_cliff_12281_r01"
    rows.append(
        _scheduler_row(
            trial_id=cliff_trial,
            injected_tokens=(12272 if mode == "chunked_prefill_on" else None),
            partial=mode == "chunked_prefill_on",
            mixed=mode == "chunked_prefill_on",
        )
    )
    (trace_dir / "trace.1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def test_scout_gate_distinguishes_fit_from_the_admission_cliff(
    tmp_path: Path,
) -> None:
    _write_mechanism_trace(tmp_path, "mechanism_01", "chunked_prefill_off")
    _write_mechanism_trace(tmp_path, "mechanism_02", "chunked_prefill_on")

    summary, rows = mechanism_scout_summary(tmp_path)

    assert len(rows) == 6
    assert summary["fit_control_whole_admission_both_modes"] is True
    assert summary["off_cliff_waits_with_zero_prefill_tokens"] is True
    assert summary["on_cliff_partial_mixed_admission"] is True
    assert summary["r3_s0_gate_complete"] is True


def test_observer_summary_reports_mixed_partial_prefill_and_preemption() -> None:
    rows = [
        {
            "event": "scheduler_step",
            "running_count_before": 8,
            "waiting_count_before": 1,
            "resident_decode_tokens": 16,
            "injected_prefill_tokens": 12272,
            "preempted_request_ids": [],
            "scheduled_requests": [
                {"phase": "injected_prefill", "prefill_partial": True}
            ],
        }
    ]
    summary = summarize_r3_scheduler_rows(rows)

    assert summary == {
        "scheduler_step_count": 1,
        "mixed_decode_prefill_step_count": 1,
        "injected_partial_prefill_step_count": 1,
        "preempted_request_count": 0,
        "max_running_count_before": 8,
        "max_waiting_count_before": 1,
    }
    assert request_phase("cmpl-x_resident-0-a1b2c3d4", 0) == "resident_decode"
    assert request_phase("cmpl-x_injected-a1b2c3d4", 100) == "injected_prefill"


def test_paired_bootstrap_and_outcome_keep_benefit_and_cost_separate() -> None:
    ci = paired_bootstrap_median_ci([-100.0, -90.0, -80.0], samples=1000)
    assert ci["n"] == 3
    assert ci["median"] == -90.0
    assert ci["ci95_high"] < 0

    outcome = _scientific_outcome(
        {"r3_s0_gate_complete": True},
        {
            "admission_cliff_12281": {
                "injected_ttft_relative_change_on_vs_off": -0.25,
                "resident_interference_p99_relative_change_on_vs_off": 0.18,
                "aggregate_output_tps_relative_change_on_vs_off": -0.02,
                "paired_bootstrap_on_minus_off_ttft_ms": ci,
            }
        },
        performance_complete=True,
    )

    assert outcome["task_id"] == TASK_ID
    assert outcome["practical_benefit_threshold_met"] is True
    assert outcome["deployment_cost_bound_resident_p99_tbt_met"] is False
    assert outcome["scientific_outcome"] == "mechanism_confirmed_tradeoff_only"
