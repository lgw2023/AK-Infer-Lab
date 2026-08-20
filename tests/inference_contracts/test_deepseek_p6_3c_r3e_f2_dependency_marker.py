from __future__ import annotations

import csv
import json
from pathlib import Path
import pickle
from types import SimpleNamespace

import pytest

from tools.inference_contracts import (
    analyze_p6_3c_r3e_f2_dependency_markers as analysis,
)
from tools.inference_contracts import (
    p6_3c_r3e_f2_dependency_marker as marker,
)
from tools.inference_contracts import (
    run_deepseek_p6_3c_r3e_f2_dependency_marker_canary as runner,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _context(
    lifecycle_id: str, policy_id: str, timing_context_id: str, step_index: int
) -> dict[str, object]:
    return marker.marker_context(
        lifecycle_id=lifecycle_id,
        policy_id=policy_id,
        timing_context_id=timing_context_id,
        step_index=step_index,
    )


def _events(
    lifecycle_id: str,
    policy_id: str,
    timing_context_id: str,
    step_index: int,
    rank: int,
    *,
    base_ts: float,
    include_runtime_device_link: bool = True,
) -> list[dict[str, object]]:
    context = _context(lifecycle_id, policy_id, timing_context_id, step_index)
    marker_name = marker.build_marker_name(context, rank)
    runtime_args: dict[str, object] = {"correlation_id": 42 + step_index}
    device_args: dict[str, object] = {}
    if include_runtime_device_link:
        runtime_args["connection_id"] = 9000 + step_index
        device_args["connection_id"] = 9000 + step_index
    return [
        {
            "name": marker_name,
            "cat": "cpu_op",
            "ph": "X",
            "pid": 99,
            "ts": base_ts,
            "dur": 100.0,
            "args": {},
        },
        {
            "name": "aten::matmul",
            "cat": "cpu_op",
            "ph": "X",
            "pid": 99,
            "ts": base_ts + 10,
            "dur": 10.0,
            "args": {"correlation_id": 42 + step_index},
        },
        {
            "name": "Dequeue@HcclAllReduce",
            "ph": "X",
            "pid": 99,
            "ts": base_ts + 30,
            "dur": 10.0,
            "args": runtime_args,
        },
        {
            "name": "HcomAllReduce",
            "cat": "kernel",
            "ph": "X",
            "pid": 7,
            "ts": base_ts + 50,
            "dur": 20.0,
            "args": device_args,
        },
        {
            "name": "Communication(Not Overlapped)",
            "ph": "X",
            "pid": 7,
            "ts": base_ts + 72,
            "dur": 10.0,
            "args": {"connection_id": 9000 + step_index},
        },
    ]


def _write_lifecycle(
    artifact_dir: Path,
    lifecycle_id: str,
    policy_id: str,
    steps: list[tuple[str, int]],
    *,
    include_runtime_device_link: bool = True,
) -> None:
    scheduler_dir = (
        artifact_dir
        / "lifecycles"
        / lifecycle_id
        / "runtime"
        / "scheduler_trace"
    )
    scheduler_dir.mkdir(parents=True, exist_ok=True)
    scheduler_rows = [
        {
            "event": "dependency_marker_scheduled",
            "schema": marker.MARKER_SCHEMA,
            "lifecycle_id": lifecycle_id,
            "policy_id": policy_id,
            "timing_context_id": timing_context_id,
            "step_index": step_index,
        }
        for timing_context_id, step_index in steps
    ]
    (scheduler_dir / "trace.100.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in scheduler_rows),
        encoding="utf-8",
    )
    for rank in range(8):
        trace_dir = (
            artifact_dir
            / "lifecycles"
            / lifecycle_id
            / "runtime"
            / "torch_profiler"
            / f"dp0_rank{rank}_1_ascend_pt"
            / "ASCEND_PROFILER_OUTPUT"
        )
        trace_dir.mkdir(parents=True, exist_ok=True)
        events: list[dict[str, object]] = [
            {
                "name": "process_labels",
                "ph": "M",
                "pid": 7,
                "args": {"labels": "NPU 0"},
            }
        ]
        for index, (timing_context_id, step_index) in enumerate(steps):
            events.extend(
                _events(
                    lifecycle_id,
                    policy_id,
                    timing_context_id,
                    step_index,
                    rank,
                    base_ts=100.0 + index * 200.0,
                    include_runtime_device_link=include_runtime_device_link,
                )
            )
        (trace_dir / "trace_view.json").write_text(
            json.dumps(events), encoding="utf-8"
        )


def test_marker_payload_roundtrips_without_request_content() -> None:
    output = SimpleNamespace()
    context = _context("f2_s1_01", "admission_on_t4096", "100:7:200", 7)
    marker.attach_marker_context(output, context)
    restored = pickle.loads(pickle.dumps(output))
    restored_context = getattr(restored, marker.MARKER_ATTRIBUTE)
    name = marker.build_marker_name(restored_context, 3)

    assert marker.parse_marker_name(name) == {**context, "worker_rank": 3}
    assert not any(
        token in name.lower()
        for token in ("prompt", "generated", "token_id", "request_id")
    )
    with pytest.raises(ValueError):
        marker.marker_context(
            lifecycle_id="bad|payload",
            policy_id="p",
            timing_context_id="c",
            step_index=0,
        )


def test_s1_requires_8_rank_marker_and_full_actual_kernel_chain(
    tmp_path: Path,
) -> None:
    _write_lifecycle(
        tmp_path,
        "f2_s1_01",
        "admission_on_t4096",
        [("100:1:200", 1)],
    )
    output = tmp_path / "analysis"
    summary = analysis.analyze_artifact(
        tmp_path, ("f2_s1_01",), output, stage="S1"
    )

    assert summary["trace_parse_complete"] is True
    assert summary["trace_rank_coverage_complete"] is True
    assert summary["marker_presence_complete"] is True
    assert summary["full_dependency_chain_complete"] is True
    assert summary["s2_authorized"] is True
    assert summary["causal_bottleneck_resolved"] is False
    rows = list(
        csv.DictReader(
            (output / "dependency_edge_summary.tsv").open(encoding="utf-8"),
            delimiter="\t",
        )
    )
    assert {
        row["edge_segment"]
        for row in rows
        if row["edge_complete_for_all_expected_rows"] == "True"
    } == {
        "marker_to_host_op",
        "host_op_to_runtime_launch",
        "runtime_launch_to_actual_device_kernel",
    }
    assert all(row["rank_row_coverage_rate"] == "1.0" for row in rows)
    assert all(
        row["repeated_pressure_step_coverage_rate"] == "1.0" for row in rows
    )
    chains = list(
        csv.DictReader(
            (output / "cross_domain_link_chains.tsv").open(encoding="utf-8"),
            delimiter="\t",
        )
    )
    assert len(chains) == 8
    assert all(row["actual_device_kernel_name"] == "HcomAllReduce" for row in chains)
    assert all("Communication" not in row["actual_device_kernel_name"] for row in chains)


def test_missing_runtime_to_actual_kernel_identifier_stops_s2(
    tmp_path: Path,
) -> None:
    _write_lifecycle(
        tmp_path,
        "f2_s1_01",
        "admission_on_t4096",
        [("100:1:200", 1)],
        include_runtime_device_link=False,
    )
    summary = analysis.analyze_artifact(
        tmp_path, ("f2_s1_01",), tmp_path / "analysis", stage="S1"
    )

    assert summary["marker_presence_complete"] is True
    assert summary["full_dependency_chain_complete"] is False
    assert summary["s2_authorized"] is False
    assert summary["dependency_linkage_gap"] == (
        "runtime_launch_to_actual_device_kernel"
    )
    assert summary["optimization_target_selected"] is False


def test_duplicate_worker_marker_fails_the_exactly_once_s1_gate(
    tmp_path: Path,
) -> None:
    _write_lifecycle(
        tmp_path,
        "f2_s1_01",
        "admission_on_t4096",
        [("100:1:200", 1)],
    )
    for trace_path in tmp_path.rglob("trace_view.json"):
        events = json.loads(trace_path.read_text(encoding="utf-8"))
        duplicate = dict(events[1])
        duplicate["ts"] = float(duplicate["ts"]) + 0.1
        duplicate["dur"] = float(duplicate["dur"]) - 0.2
        events.append(duplicate)
        trace_path.write_text(json.dumps(events), encoding="utf-8")

    summary = analysis.analyze_artifact(
        tmp_path, ("f2_s1_01",), tmp_path / "analysis", stage="S1"
    )

    assert summary["marker_presence_complete"] is False
    assert summary["s2_authorized"] is False
    assert summary["dependency_linkage_gap"].startswith(
        "worker_marker_missing_or_rank_incomplete"
    )


def test_final_gate_requires_same_final_edge_on_two_steps_in_both_policies(
    tmp_path: Path,
) -> None:
    _write_lifecycle(
        tmp_path,
        "f2_s2_01",
        "admission_on_t4096",
        [("101:1:201", 1), ("101:2:202", 2)],
    )
    _write_lifecycle(
        tmp_path,
        "f2_s2_02",
        "persistent_on_t128",
        [("102:1:201", 1), ("102:2:202", 2)],
    )
    summary = analysis.analyze_artifact(
        tmp_path,
        ("f2_s2_01", "f2_s2_02"),
        tmp_path / "analysis",
        stage="FINAL",
    )

    assert summary["causal_bottleneck_resolved"] is True
    assert summary["stable_final_edge_signature"]
    assert summary["optimization_target_selected"] is False


def test_contract_is_conditional_and_does_not_repeat_budget_sweep() -> None:
    workload = (
        REPO_ROOT
        / "benchmarks/deepseek_v4_flash/workloads/"
        "p6_3c_r3e_f2_request_scoped_dependency_marker_canary.yaml"
    ).read_text(encoding="utf-8")
    experiment = (
        REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3c_r3e_f2_experiment.sh"
    ).read_text(encoding="utf-8")

    assert runner.S1_LIFECYCLE_IDS == ("f2_s1_01",)
    assert runner.S2_LIFECYCLE_IDS == ("f2_s2_01", "f2_s2_02")
    assert "conditional_on: S1 gate only" in workload
    assert "17-lifecycle repetition" in workload
    assert "five-level budget sweep" in workload
    assert 'if test "${s2_authorized}" != true' in experiment
    assert "optimization_target_selected_by_default: false" in workload
