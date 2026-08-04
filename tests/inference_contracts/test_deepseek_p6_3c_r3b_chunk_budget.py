from __future__ import annotations

import json
import math
from pathlib import Path

from tools.inference_contracts.run_deepseek_p6_3c_r3a_decode_resident import (
    _max_token_stall_ms,
)
from tools.inference_contracts.run_deepseek_p6_3c_r3b_chunk_budget import (
    CONFIGS,
    EXPECTED_ENGINE_REQUESTS,
    EXPECTED_HTTP_REQUESTS,
    EXPECTED_PERFORMANCE_TRIALS,
    EXPECTED_POLICY_PAIRS,
    LIFECYCLE_SCHEDULE,
    MECHANISM_LIFECYCLES,
    ON_CONFIG_IDS,
    PERFORMANCE_CELL_SEQUENCE,
    PERFORMANCE_LIFECYCLES,
    PERFORMANCE_METRIC_FIELDS,
    _performance_analysis_completeness,
    _performance_rows,
    build_run_plan,
    mechanism_budget_summary,
    performance_evidence,
    prepare_artifacts,
    refinalize_artifacts,
)


def test_r3b_schedule_is_mirrored_and_counts_are_exact() -> None:
    assert len(MECHANISM_LIFECYCLES) == 5
    assert len(PERFORMANCE_LIFECYCLES) == 12
    assert len(LIFECYCLE_SCHEDULE) == 17
    first = [row["config_id"] for row in PERFORMANCE_LIFECYCLES[:6]]
    second = [row["config_id"] for row in PERFORMANCE_LIFECYCLES[6:]]
    assert second == list(reversed(first))
    assert first == [row["config_id"] for row in CONFIGS]
    assert len(PERFORMANCE_CELL_SEQUENCE) == 12
    assert PERFORMANCE_CELL_SEQUENCE.count("resident_only") == 6
    assert PERFORMANCE_CELL_SEQUENCE.count("admission_cliff_12281") == 6

    mechanism_requests = 1 + 8 + 1
    mechanism_http = 1 + 1 + 1
    performance_requests = 1 + 6 * 8 + 6 * 9
    performance_http = 1 + 6 + 6 * 2
    assert (
        5 * mechanism_requests + 12 * performance_requests == EXPECTED_ENGINE_REQUESTS
    )
    assert 5 * mechanism_http + 12 * performance_http == EXPECTED_HTTP_REQUESTS


def test_prepare_materializes_one_byte_identical_policy_payload_matrix(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    artifact = tmp_path / "artifact"

    manifest = prepare_artifacts(source, artifact, "test-model")
    plan = build_run_plan()

    assert manifest["body_record_count"] == 22
    assert len(list((artifact / "bodies").glob("*.json"))) == 22
    assert len(plan["trials"]["mechanism"]) == 1
    assert len(plan["trials"]["performance"]) == 12
    injected = [row for row in manifest["records"] if row["request_role"] == "injected"]
    assert len(injected) == 7
    assert all(row["prompt_token_lengths"] == [12281] for row in injected)


def _write_budget_trace(root: Path, lifecycle: dict[str, object]) -> None:
    trace_dir = (
        root / "lifecycles" / str(lifecycle["lifecycle_id"]) / "runtime/scheduler_trace"
    )
    trace_dir.mkdir(parents=True)
    trial_id = "p6_3c_r3b_mechanism_admission_cliff_12281_r01"
    injected_id = f"cmpl-{trial_id}_injected-a1b2c3d4"
    resident_ids = [f"cmpl-{trial_id}_resident-{index}-a1b2c3d4" for index in range(8)]
    budget = int(lifecycle["max_num_batched_tokens"])
    first_chunk = budget - 16
    remaining = 12281
    chunks = []
    while remaining:
        chunk = min(first_chunk if not chunks else budget, remaining)
        chunks.append(chunk)
        remaining -= chunk
    rows: list[dict[str, object]] = [
        {"event": "observer_installed", "schema": "p6_3c_r3_decode_resident_v1"}
    ]
    remaining = 12281
    for index, chunk in enumerate(chunks):
        rows.append(
            {
                "event": "scheduler_step",
                "step_index": 100 + index,
                "token_budget": budget,
                "running_order_before": resident_ids + ([injected_id] if index else []),
                "waiting_order_before": [injected_id] if index == 0 else [],
                "resident_decode_tokens": 16 if index == 0 else 0,
                "mixed_decode_prefill": index == 0,
                "preempted_request_ids": [],
                "scheduled_requests": [
                    {
                        "request_id": injected_id,
                        "phase": "injected_prefill",
                        "scheduled_prefill_tokens": chunk,
                        "prefill_partial": chunk < remaining,
                    }
                ],
            }
        )
        remaining -= chunk
    (trace_dir / "trace.1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def test_mechanism_gate_calibrates_every_on_budget(tmp_path: Path) -> None:
    for lifecycle in MECHANISM_LIFECYCLES:
        _write_budget_trace(tmp_path, lifecycle)

    summary, rows = mechanism_budget_summary(tmp_path)

    assert len(rows) == 5
    assert summary["all_budget_mechanisms_complete"] is True
    assert summary["all_first_chunks_equal_remaining_budget"] is True
    assert [row["prefill_chunk_count"] for row in rows] == [
        math.ceil((12281 - (2048 - 16)) / 2048) + 1,
        math.ceil((12281 - (4096 - 16)) / 4096) + 1,
        math.ceil((12281 - (6144 - 16)) / 6144) + 1,
        math.ceil((12281 - (8192 - 16)) / 8192) + 1,
        2,
    ]


def test_resident_max_stall_is_true_adjacent_gap_not_itl_p99() -> None:
    rows = [
        {"token_arrival_ns": [0, 1_000_000, 101_000_000], "itl_p99_ms": 3.0},
        {"token_arrival_ns": [0, 2_000_000], "itl_p99_ms": 50.0},
    ]
    assert _max_token_stall_ms(rows) == 100.0


def test_performance_rows_reconstruct_missing_measured_phase_from_plan(
    tmp_path: Path,
) -> None:
    lifecycle = PERFORMANCE_LIFECYCLES[0]
    root = tmp_path / "lifecycles" / lifecycle["lifecycle_id"]
    root.mkdir(parents=True)
    measured = {
        "track": "performance",
        "trial_id": "p6_3c_r3b_performance_resident_only_r01",
        "cell_id": "resident_only",
        "repeat_index": 1,
        "order_index": 1,
        "status": "success",
        "arrival_contract": {},
        "config_id": lifecycle["config_id"],
        "mirror_round": lifecycle["mirror_round"],
        "lifecycle_id": lifecycle["lifecycle_id"],
        "aggregate_output_tokens_per_second": 100.0,
    }
    warmup = {
        "phase": "warmup",
        "trial_id": "p6_3c_r3b_performance_warmup",
        "cell_id": "warmup",
        "status": "success",
    }
    unknown = {
        **measured,
        "trial_id": "not_preregistered",
    }
    (root / "raw_trial_results.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in (warmup, measured, unknown)),
        encoding="utf-8",
    )
    (root / "raw_request_results.jsonl").write_text("", encoding="utf-8")

    rows = _performance_rows(tmp_path)

    assert len(rows) == 1
    assert rows[0]["phase"] == "measured"
    assert rows[0]["phase_source"] == "reconstructed_from_preregistered_trial_id"


def test_empty_performance_aggregation_fails_closed(tmp_path: Path) -> None:
    _, paired, uncertainty, frontier = performance_evidence(tmp_path)

    completeness = uncertainty["analysis_completeness"]
    assert completeness["complete"] is False
    assert completeness["measured_trial_count"] == 0
    assert completeness["valid_pair_count"] == 0
    assert len(paired) == EXPECTED_POLICY_PAIRS
    assert frontier["pareto_config_ids"] == [row["config_id"] for row in CONFIGS]


def test_performance_completeness_requires_all_trials_pairs_and_objectives() -> None:
    summaries = [{"valid_trial_count": 12} for _ in range(len(CONFIGS) * 2)]
    paired = [{"valid_pair": True} for _ in range(EXPECTED_POLICY_PAIRS)]
    uncertainty = {
        "configs": {
            config_id: {
                metric: {
                    "n": 12,
                    "mirror_round_medians": {"round_1": 1.0, "round_2": 1.0},
                }
                for metric in PERFORMANCE_METRIC_FIELDS
            }
            for config_id in ON_CONFIG_IDS
        }
    }
    objective_fields = {
        "injected_ttft_ms_median": "minimize",
        "resident_interference_tbt_p99_ms_median": "minimize",
        "resident_interference_max_stall_ms_median": "minimize",
        "aggregate_output_tps_median": "maximize",
        "resident_tbt_slo_attainment_median": "maximize",
    }
    frontier = {
        "objective_directions": objective_fields,
        "pareto_config_ids": ["off_b12288"],
        "rows": [
            {
                **{field: 1.0 for field in objective_fields},
                "pareto_nondominated": True,
            }
            for _ in CONFIGS
        ],
    }

    completeness = _performance_analysis_completeness(
        summaries, paired, uncertainty, frontier
    )

    assert completeness["complete"] is True
    assert completeness["measured_trial_count"] == EXPECTED_PERFORMANCE_TRIALS
    assert completeness["valid_pair_count"] == EXPECTED_POLICY_PAIRS

    paired[-1]["valid_pair"] = False
    assert (
        _performance_analysis_completeness(summaries, paired, uncertainty, frontier)[
            "complete"
        ]
        is False
    )


def test_refinalize_creates_separate_zero_npu_provenance_without_source_writes(
    tmp_path: Path,
) -> None:
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    source = tmp_path / "source"
    prepare_artifacts(payload, source, "test-model")
    (source / "lifecycles").mkdir()
    (source / "resource_recovery_summary.json").write_text(
        json.dumps({"keep_alive_restored_exact": True}), encoding="utf-8"
    )
    (source / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
    source_files_before = sorted(
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_file()
    )
    output = tmp_path / "derived"

    grading = refinalize_artifacts(source, output)

    source_files_after = sorted(
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_file()
    )
    provenance = json.loads(
        (output / "analysis_provenance.json").read_text(encoding="utf-8")
    )
    assert grading["evidence_status"] == "incomplete"
    assert source_files_after == source_files_before
    assert provenance["source_evidence_unchanged"] is True
    assert provenance["source_result_overwritten"] is False
    assert provenance["npu_used"] is False
    assert (output / "lifecycles").is_symlink()
    assert (output / "candidate_manifest.server_local.json").is_file()
