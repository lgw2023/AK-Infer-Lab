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
    LIFECYCLE_SCHEDULE,
    MECHANISM_LIFECYCLES,
    PERFORMANCE_CELL_SEQUENCE,
    PERFORMANCE_LIFECYCLES,
    build_run_plan,
    mechanism_budget_summary,
    prepare_artifacts,
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
