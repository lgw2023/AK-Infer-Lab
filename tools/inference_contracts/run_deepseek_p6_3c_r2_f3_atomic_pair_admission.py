from __future__ import annotations

import csv
from contextlib import contextmanager
import json
import os
from pathlib import Path
import statistics
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts import (
    run_deepseek_p6_3c_r2_scheduler_pressure as r2,
)


TASK_ID = os.environ.get(
    "P6_3C_TASK_ID",
    "p6_3c_r2_f3_chunked_prefill_atomic_pair_admission_2026_0730_run01",
)
REQUEST_ID_PREFIX = "p6_3c_r2_f3"
WORKLOAD_RELATIVE_PATH = (
    "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r2_f3_atomic_pair_admission_matched_ab.yaml"
)
ATOMIC_SUMMARY = "atomic_pair_admission_summary.json"
ATOMIC_RELEASE_TSV = "atomic_pair_release_summary.tsv"
ATOMIC_FIRST_STEP_TSV = "mechanism_atomic_pair_first_step.tsv"
F3_BOUNDED_CANDIDATES = (
    *r2.R2_BOUNDED_CANDIDATES[:-2],
    ATOMIC_SUMMARY,
    ATOMIC_RELEASE_TSV,
    ATOMIC_FIRST_STEP_TSV,
    *r2.R2_BOUNDED_CANDIDATES[-2:],
)
FAILURE_EVENTS = {
    "pair_duplicate_member",
    "pair_release_failed",
    "pair_timeout_aborted",
    "pair_timeout_wakeup_unavailable",
    "pair_aborted_before_release",
    "pair_member_rejected_after_pair_failure",
}


@contextmanager
def _configured_r2():
    replacements = {
        "TASK_ID": TASK_ID,
        "REQUEST_ID_PREFIX": REQUEST_ID_PREFIX,
        "WORKLOAD_RELATIVE_PATH": WORKLOAD_RELATIVE_PATH,
        "R2_BOUNDED_CANDIDATES": F3_BOUNDED_CANDIDATES,
    }
    originals = {name: getattr(r2, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(r2, name, value)
        yield
    finally:
        for name, value in originals.items():
            setattr(r2, name, value)


def _read_atomic_rows(lifecycle_dir: Path) -> list[dict[str, Any]]:
    rows = []
    trace_root = lifecycle_dir / "runtime" / "atomic_pair_trace"
    for path in sorted(trace_root.glob("trace.*.jsonl")):
        rows.extend(r2.base._read_jsonl(path))
    return rows


def _expected_pairs(
    plan: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    pairs = []
    for lifecycle in r2.base.LIFECYCLE_SCHEDULE:
        for batch in plan[lifecycle["track"]]:
            if batch["phase"] != "measured":
                continue
            pairs.append(
                {
                    "lifecycle_id": lifecycle["lifecycle_id"],
                    "track": lifecycle["track"],
                    "mode": lifecycle["mode"],
                    "batch_id": batch["batch_id"],
                    "cell_id": batch["cell_id"],
                    "pressure": bool(batch["pressure"]),
                    "prompt_tokens": list(batch["prompt_tokens"]),
                    "request_ids": [
                        f"cmpl-{batch['request_id']}-0",
                        f"cmpl-{batch['request_id']}-1",
                    ],
                }
            )
    return pairs


def _release_table_and_gate(
    artifact_dir: Path,
    plan: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    expected = _expected_pairs(plan)
    release_rows: list[dict[str, Any]] = []
    lifecycle_states: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    installed_lifecycles = []
    all_trace_by_lifecycle: dict[str, list[dict[str, Any]]] = {}
    for lifecycle in r2.base.LIFECYCLE_SCHEDULE:
        lifecycle_id = lifecycle["lifecycle_id"]
        lifecycle_dir = artifact_dir / "lifecycles" / lifecycle_id
        trace_rows = _read_atomic_rows(lifecycle_dir)
        all_trace_by_lifecycle[lifecycle_id] = trace_rows
        if any(
            row.get("event") == "atomic_pair_admission_installed"
            for row in trace_rows
        ):
            installed_lifecycles.append(lifecycle_id)
        failure_rows.extend(
            {"lifecycle_id": lifecycle_id, **row}
            for row in trace_rows
            if row.get("event") in FAILURE_EVENTS
        )
        shutdown_rows = [
            row
            for row in trace_rows
            if row.get("event") == "atomic_pair_admission_shutdown_state"
        ]
        lifecycle_states.append(
            {
                "lifecycle_id": lifecycle_id,
                "shutdown_state_observed": bool(shutdown_rows),
                "pending_pair_count": (
                    shutdown_rows[-1].get("pending_pair_count")
                    if shutdown_rows
                    else None
                ),
                "failed_pair_count": (
                    shutdown_rows[-1].get("failed_pair_count")
                    if shutdown_rows
                    else None
                ),
                "completed_pair_count": (
                    shutdown_rows[-1].get("completed_pair_count")
                    if shutdown_rows
                    else None
                ),
            }
        )

    exact_release_count = 0
    for pair in expected:
        matches = [
            row
            for row in all_trace_by_lifecycle[pair["lifecycle_id"]]
            if row.get("event") == "pair_complete_released"
            and row.get("request_ids") == pair["request_ids"]
        ]
        exact = (
            len(matches) == 1
            and matches[0].get("pair_indices") == [0, 1]
            and matches[0].get("prompt_tokens") == pair["prompt_tokens"]
            and matches[0].get("release_order")
            == "pair_index_ascending_before_next_scheduler_step"
        )
        exact_release_count += int(exact)
        waits = matches[0].get("member_buffer_wait_ns") if matches else []
        release_rows.append(
            {
                **{key: pair[key] for key in (
                    "lifecycle_id",
                    "track",
                    "mode",
                    "batch_id",
                    "cell_id",
                )},
                "request_id_0": pair["request_ids"][0],
                "request_id_1": pair["request_ids"][1],
                "prompt_tokens_0": pair["prompt_tokens"][0],
                "prompt_tokens_1": pair["prompt_tokens"][1],
                "release_event_count": len(matches),
                "release_exact": exact,
                "member_0_wait_ms": (
                    round(float(waits[0]) / 1_000_000, 6)
                    if len(waits) == 2
                    else None
                ),
                "member_1_wait_ms": (
                    round(float(waits[1]) / 1_000_000, 6)
                    if len(waits) == 2
                    else None
                ),
                "max_member_wait_ms": (
                    round(max(float(value) for value in waits) / 1_000_000, 6)
                    if len(waits) == 2
                    else None
                ),
            }
        )

    expected_by_lifecycle = {
        lifecycle["lifecycle_id"]: (
            3 if lifecycle["track"] == "mechanism" else 9
        )
        for lifecycle in r2.base.LIFECYCLE_SCHEDULE
    }
    shutdown_clean = all(
        row["shutdown_state_observed"]
        and row["pending_pair_count"] == 0
        and row["failed_pair_count"] == 0
        and row["completed_pair_count"]
        == expected_by_lifecycle[row["lifecycle_id"]]
        for row in lifecycle_states
    )
    release_gate = (
        len(installed_lifecycles) == len(r2.base.LIFECYCLE_SCHEDULE)
        and exact_release_count == len(expected)
        and not failure_rows
        and shutdown_clean
    )
    return (
        {
            "installed_lifecycle_count": len(installed_lifecycles),
            "installed_lifecycles": installed_lifecycles,
            "expected_pair_release_count": len(expected),
            "exact_pair_release_count": exact_release_count,
            "failure_event_count": len(failure_rows),
            "failure_events": failure_rows,
            "lifecycle_shutdown_states": lifecycle_states,
            "all_lifecycle_shutdown_states_clean": shutdown_clean,
            "atomic_pair_release_gate_complete": release_gate,
        },
        release_rows,
    )


def _first_step_table_and_gate(
    artifact_dir: Path,
    plan: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = []
    for pair in [
        item for item in _expected_pairs(plan) if item["track"] == "mechanism"
    ]:
        lifecycle_dir = (
            artifact_dir / "lifecycles" / pair["lifecycle_id"]
        )
        trace_rows = r2.base._read_trace_rows(lifecycle_dir)
        relevant_steps = sorted(
            (
                row
                for row in trace_rows
                if row.get("event") == "scheduler_step"
                and any(
                    request_id in json.dumps(row, separators=(",", ":"))
                    for request_id in pair["request_ids"]
                )
            ),
            key=lambda row: int(row.get("step_index") or 0),
        )
        first = relevant_steps[0] if relevant_steps else {}
        waiting_before = first.get("waiting_order_before") or []
        scheduled = {
            str(item.get("request_id")): int(
                item.get("scheduled_tokens") or 0
            )
            for item in first.get("scheduled_requests") or []
        }
        prompt_0, prompt_1 = [int(value) for value in pair["prompt_tokens"]]
        if not pair["pressure"]:
            expected_scheduled = {
                pair["request_ids"][0]: prompt_0,
                pair["request_ids"][1]: prompt_1,
            }
        elif pair["mode"] == "chunked_prefill_off":
            expected_scheduled = {pair["request_ids"][0]: prompt_0}
        else:
            expected_scheduled = {
                pair["request_ids"][0]: prompt_0,
                pair["request_ids"][1]: r2.MAX_NUM_BATCHED_TOKENS - prompt_0,
            }
        waiting_pair_exact = waiting_before == pair["request_ids"]
        scheduled_exact = scheduled == expected_scheduled
        total_exact = int(first.get("total_num_scheduled_tokens") or 0) == sum(
            expected_scheduled.values()
        )
        rows.append(
            {
                "lifecycle_id": pair["lifecycle_id"],
                "mode": pair["mode"],
                "cell_id": pair["cell_id"],
                "first_step_index": first.get("step_index"),
                "waiting_pair_exact": waiting_pair_exact,
                "waiting_order_before": json.dumps(
                    waiting_before, separators=(",", ":")
                ),
                "scheduled_exact": scheduled_exact,
                "scheduled_tokens": json.dumps(
                    scheduled, separators=(",", ":"), sort_keys=True
                ),
                "expected_scheduled_tokens": json.dumps(
                    expected_scheduled,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "total_scheduled_exact": total_exact,
                "first_step_contract_exact": (
                    waiting_pair_exact and scheduled_exact and total_exact
                ),
            }
        )
    gate = len(rows) == 6 and all(
        row["first_step_contract_exact"] for row in rows
    )
    return (
        {
            "mechanism_cell_count": len(rows),
            "first_scheduler_step_contract_exact_count": sum(
                row["first_step_contract_exact"] for row in rows
            ),
            "mechanism_atomic_coarrival_gate_complete": gate,
        },
        rows,
    )


def _performance_barrier_summary(
    release_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    values = [
        float(row["max_member_wait_ms"])
        for row in release_rows
        if row["track"] == "performance"
        and row["max_member_wait_ms"] is not None
    ]
    return {
        "performance_pair_count": len(values),
        "max_member_wait_ms_median": (
            round(statistics.median(values), 6) if values else None
        ),
        "max_member_wait_ms_max": round(max(values), 6) if values else None,
        "interpretation": (
            "common_controlled_coarrival_overhead_audited_both_modes_"
            "performance_effects_remain_descriptive"
        ),
    }


def _write_result_summary(
    artifact_dir: Path,
    grading: dict[str, Any],
    mechanism: dict[str, Any],
    atomic: dict[str, Any],
) -> None:
    lines = [
        f"# {TASK_ID} 结果摘要",
        "",
        f"- server grade: `{grading['server_grade']}`",
        (
            "- 原 P6.3C blocked、R1/R2/F1 启动链与 F2 "
            "`red_p6_3c_r2_f2_scheduler_pressure_evidence_incomplete` "
            "均作为独立审计保留。"
        ),
        (
            "- 共同冻结环境：`12288/12288/2`、Prefix Cache off、同一 "
            "hybrid-KV repair、同一 task-local atomic pair admission；"
            "唯一 A/B 差异仍是 Chunked Prefill 显式 Off/On。"
        ),
        (
            f"- 请求 `{grading.get('successful_request_count')}/90`；"
            f"原子成对释放 `{atomic['exact_pair_release_count']}/"
            f"{atomic['expected_pair_release_count']}`；"
            f"六个机制首轮合同 `{atomic['first_scheduler_step_contract_exact_count']}/6`。"
        ),
        "",
        "## 机制证据",
        "",
        (
            "- 两个 tagged measured request 在进入 Scheduler 前成对释放："
            f"`{atomic['atomic_pair_release_gate_complete']}`。"
        ),
        (
            "- 每个机制 cell 首个 scheduler step 的 waiting 次序和 scheduled token "
            f"精确符合冻结预期：`{atomic['mechanism_atomic_coarrival_gate_complete']}`。"
        ),
        (
            "- Off 三组无 partial prefill："
            f"`{mechanism.get('off_prefill_partial_absent_all_cells')}`；"
            "On 两个压力组存在 partial prefill："
            f"`{mechanism.get('on_prefill_partial_present_both_pressure_cells')}`。"
        ),
        (
            "- 4K+4K 两侧均无 partial prefill："
            f"`{mechanism.get('low_pressure_partial_absent_both_modes')}`。"
        ),
        "",
        "## 性能边界",
        "",
        "- 性能轨道仍为 Off→On→On→Off，scheduler observer/profiler 关闭。",
        (
            "- admission barrier 是两侧共同的受控实验环境；其等待开销单独记录，"
            "TTFT/E2EL/TPOT/ITL/吞吐只作该环境内描述，不能外推为生产 API 收益。"
        ),
        "",
        "## 结论边界",
        "",
        "- candidate 结果仍须开发机逐文件复核后才能进入项目结论。",
        "- 不声明普遍性能收益、统计显著性或自然到达流量下的调度效果。",
        "- 未获用户明确传输渠道选择前，不外发任何候选文件。",
        "",
    ]
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    with _configured_r2():
        grading = r2.finalize_artifacts(artifact_dir)
        plan = json.loads(
            (artifact_dir / "run_plan.json").read_text(encoding="utf-8")
        )
        release_gate, release_rows = _release_table_and_gate(
            artifact_dir, plan
        )
        first_step_gate, first_step_rows = _first_step_table_and_gate(
            artifact_dir, plan
        )
        performance_barrier = _performance_barrier_summary(release_rows)
        atomic = {
            "task_id": TASK_ID,
            "controller_scope": (
                "tagged_measured_request_pairs_only_all_other_requests_unchanged"
            ),
            "both_modes_share_identical_controller": True,
            **release_gate,
            **first_step_gate,
            "coarrival_gate_complete": (
                release_gate["atomic_pair_release_gate_complete"]
                and first_step_gate[
                    "mechanism_atomic_coarrival_gate_complete"
                ]
            ),
            "performance_barrier_wait": performance_barrier,
            "claim_boundary": (
                "controlled_atomic_scheduler_visibility_not_natural_"
                "openai_api_arrival_behavior"
            ),
        }
        (artifact_dir / ATOMIC_SUMMARY).write_text(
            json.dumps(atomic, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        r2.base._write_tsv(
            artifact_dir / ATOMIC_RELEASE_TSV,
            release_rows,
            list(release_rows[0]) if release_rows else ["lifecycle_id"],
        )
        r2.base._write_tsv(
            artifact_dir / ATOMIC_FIRST_STEP_TSV,
            first_step_rows,
            list(first_step_rows[0]) if first_step_rows else ["lifecycle_id"],
        )

        mechanism_path = artifact_dir / "mechanism_scheduler_summary.json"
        mechanism = json.loads(mechanism_path.read_text(encoding="utf-8"))
        mechanism["atomic_pair_admission"] = {
            key: atomic[key]
            for key in (
                "atomic_pair_release_gate_complete",
                "mechanism_atomic_coarrival_gate_complete",
                "coarrival_gate_complete",
                "claim_boundary",
            )
        }
        mechanism["mechanism_gate_complete"] = (
            mechanism.get("mechanism_gate_complete") is True
            and atomic["coarrival_gate_complete"]
        )
        mechanism_path.write_text(
            json.dumps(mechanism, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        original_grade = str(grading["server_grade"])
        full_execution = (
            grading.get("all_lifecycles_success") is True
            and grading.get("successful_request_count") == 90
            and grading.get("successful_batch_count") == 48
        )
        if original_grade == "red_cleanup_incomplete":
            grade = original_grade
        elif full_execution and not atomic["coarrival_gate_complete"]:
            grade = (
                "red_p6_3c_r2_f3_atomic_pair_admission_evidence_incomplete"
            )
        elif original_grade.startswith("candidate_green") and atomic[
            "coarrival_gate_complete"
        ]:
            grade = original_grade
        elif full_execution:
            grade = (
                "red_p6_3c_r2_f3_chunked_prefill_mechanism_"
                "evidence_incomplete"
            )
        else:
            grade = original_grade

        resolved_atomic = []
        for lifecycle in r2.base.LIFECYCLE_SCHEDULE:
            path = (
                artifact_dir
                / "lifecycles"
                / lifecycle["lifecycle_id"]
                / "runtime"
                / "resolved_scheduler_config.json"
            )
            if path.is_file():
                resolved_atomic.append(
                    json.loads(path.read_text(encoding="utf-8")).get(
                        "atomic_pair_admission_enabled"
                    )
                )
        grading.update(
            {
                "task_id": TASK_ID,
                "server_grade": grade,
                "parent_p6_3c_r2_f2_grade_preserved": (
                    "red_p6_3c_r2_f2_scheduler_pressure_evidence_incomplete"
                ),
                "parent_p6_3c_r2_f2_overwritten": False,
                "atomic_pair_admission_resolved_all_lifecycles": (
                    resolved_atomic
                    == [True] * len(r2.base.LIFECYCLE_SCHEDULE)
                ),
                "atomic_pair_release_gate_complete": atomic[
                    "atomic_pair_release_gate_complete"
                ],
                "mechanism_atomic_coarrival_gate_complete": atomic[
                    "mechanism_atomic_coarrival_gate_complete"
                ],
                "coarrival_gate_complete": atomic[
                    "coarrival_gate_complete"
                ],
                "mechanism_gate_complete": mechanism[
                    "mechanism_gate_complete"
                ],
                "performance_is_descriptive_only": True,
                "natural_api_arrival_benefit_claimed": False,
            }
        )
        (artifact_dir / "grading_inputs.json").write_text(
            json.dumps(grading, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        environment_path = artifact_dir / "environment_and_hashes.json"
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        environment.update(
            {
                "task_id": TASK_ID,
                "workload_path": WORKLOAD_RELATIVE_PATH,
                "workload_sha256": r2.base._optional_repo_sha256(
                    WORKLOAD_RELATIVE_PATH
                ),
                "f3_runner_sha256": r2.base._sha256_path(Path(__file__)),
                "atomic_pair_admission_sha256": r2.base._optional_repo_sha256(
                    "tools/inference_contracts/"
                    "p6_3c_r2_f3_atomic_pair_admission.py"
                ),
                "atomic_pair_request_prefix": REQUEST_ID_PREFIX,
                "atomic_pair_timeout_seconds": 30,
                "atomic_pair_admission_both_modes": True,
            }
        )
        environment_path.write_text(
            json.dumps(environment, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_result_summary(artifact_dir, grading, mechanism, atomic)

        first_failure_path = artifact_dir / "first_failure_excerpt.txt"
        current_excerpt = (
            first_failure_path.read_text(encoding="utf-8", errors="replace")
            if first_failure_path.is_file()
            else ""
        )
        if grade.startswith("candidate_green"):
            first_failure_path.write_text("none\n", encoding="utf-8")
        elif full_execution or current_excerpt.startswith("server_grade="):
            first_failure_path.write_text(
                f"server_grade={grade}\n"
                f"successful_request_count="
                f"{grading.get('successful_request_count')}/90\n"
                f"coarrival_gate_complete="
                f"{atomic['coarrival_gate_complete']}\n"
                f"mechanism_gate_complete="
                f"{mechanism['mechanism_gate_complete']}\n"
                f"keep_alive_restore_exact="
                f"{grading.get('keep_alive_restore_exact')}\n",
                encoding="utf-8",
            )
        return grading


def prepare_artifacts(
    source_payload: Path,
    artifact_dir: Path,
    model_name: str,
) -> dict[str, Any]:
    with _configured_r2():
        return r2.prepare_artifacts(source_payload, artifact_dir, model_name)


def execute_mode(
    artifact_dir: Path,
    lifecycle_dir: Path,
    base_url: str,
    server_pid: int,
    track: str,
    mode: str,
) -> int:
    with _configured_r2():
        return r2.execute_mode(
            artifact_dir,
            lifecycle_dir,
            base_url,
            server_pid,
            track,
            mode,
        )


def package_results(artifact_dir: Path) -> dict[str, Any]:
    with _configured_r2():
        return r2.package_results(artifact_dir)


def main(argv: list[str] | None = None) -> int:
    args = r2.base.parse_args(argv)
    if args.command == "prepare":
        prepare_artifacts(args.source_payload, args.artifact_dir, args.model_name)
        return 0
    if args.command == "run-mode":
        return execute_mode(
            args.artifact_dir,
            args.lifecycle_dir,
            args.base_url,
            args.server_pid,
            args.track,
            args.mode,
        )
    if args.command == "finalize":
        grading = finalize_artifacts(args.artifact_dir)
        return (
            0
            if str(grading["server_grade"]).startswith("candidate_green")
            else 2
        )
    if args.command == "package":
        package_results(args.artifact_dir)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
