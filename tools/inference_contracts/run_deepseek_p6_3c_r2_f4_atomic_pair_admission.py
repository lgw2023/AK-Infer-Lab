from __future__ import annotations

from contextlib import contextmanager
import csv
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
    run_deepseek_p6_3c_r2_f3_atomic_pair_admission as f3,
)
from tools.inference_contracts import (
    run_deepseek_p6_3c_r2_scheduler_pressure as r2,
)
from tools.inference_contracts.p6_3c_r2_f4_atomic_pair_admission import (
    normalize_atomic_pair_request_id,
)


TASK_ID = os.environ.get(
    "P6_3C_TASK_ID",
    (
        "p6_3c_r2_f4_request_id_normalized_atomic_coarrival_"
        "2026_0731_run01"
    ),
)
REQUEST_ID_PREFIX = "p6_3c_r2_f4"
WORKLOAD_RELATIVE_PATH = (
    "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r2_f4_request_id_normalized_atomic_coarrival_matched_ab.yaml"
)
ATOMIC_SUMMARY = "atomic_pair_admission_summary.json"
ATOMIC_RELEASE_TSV = "atomic_pair_release_summary.tsv"
ATOMIC_FIRST_STEP_TSV = "mechanism_atomic_pair_first_step.tsv"
F4_BOUNDED_CANDIDATES = f3.F3_BOUNDED_CANDIDATES
FAILURE_EVENTS = set(f3.FAILURE_EVENTS)


@contextmanager
def _configured_f3():
    replacements = {
        "TASK_ID": TASK_ID,
        "REQUEST_ID_PREFIX": REQUEST_ID_PREFIX,
        "WORKLOAD_RELATIVE_PATH": WORKLOAD_RELATIVE_PATH,
        "F3_BOUNDED_CANDIDATES": F4_BOUNDED_CANDIDATES,
    }
    originals = {name: getattr(f3, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(f3, name, value)
        yield
    finally:
        for name, value in originals.items():
            setattr(f3, name, value)


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
            canonical_ids = [
                f"cmpl-{batch['request_id']}-0",
                f"cmpl-{batch['request_id']}-1",
            ]
            pairs.append(
                {
                    "lifecycle_id": lifecycle["lifecycle_id"],
                    "track": lifecycle["track"],
                    "mode": lifecycle["mode"],
                    "batch_id": batch["batch_id"],
                    "cell_id": batch["cell_id"],
                    "pressure": bool(batch["pressure"]),
                    "prompt_tokens": list(batch["prompt_tokens"]),
                    "canonical_request_ids": canonical_ids,
                    "pair_key": canonical_ids[0].rsplit("-", 1)[0],
                }
            )
    return pairs


def _normalize_actual_ids(
    actual_ids: list[Any],
) -> tuple[list[str], bool]:
    normalized = [
        normalize_atomic_pair_request_id(str(request_id))
        for request_id in actual_ids
    ]
    valid = bool(actual_ids) and all(item is not None for item in normalized)
    canonical_ids = [
        item.canonical_request_id
        for item in normalized
        if item is not None
    ]
    return canonical_ids, valid and len(canonical_ids) == len(actual_ids)


def _terminal_state(
    trace_rows: list[dict[str, Any]],
    expected_pair_count: int,
) -> dict[str, Any]:
    shutdown_rows = [
        row
        for row in trace_rows
        if row.get("event") == "atomic_pair_admission_shutdown_state"
    ]
    checkpoint_rows = [
        row
        for row in trace_rows
        if row.get("event") == "atomic_pair_admission_state_checkpoint"
    ]
    source = "missing"
    selected: dict[str, Any] = {}
    if shutdown_rows:
        source = "shutdown"
        selected = shutdown_rows[-1]
    elif checkpoint_rows:
        source = "post_release_checkpoint"
        selected = checkpoint_rows[-1]
    clean = (
        selected.get("pending_pair_count") == 0
        and selected.get("failed_pair_count") == 0
        and selected.get("completed_pair_count") == expected_pair_count
        and (
            source == "shutdown"
            or selected.get("reason") == "pair_complete_released"
        )
    )
    return {
        "shutdown_state_observed": bool(shutdown_rows),
        "state_checkpoint_observed": bool(checkpoint_rows),
        "terminal_state_source": source,
        "pending_pair_count": selected.get("pending_pair_count"),
        "failed_pair_count": selected.get("failed_pair_count"),
        "completed_pair_count": selected.get("completed_pair_count"),
        "terminal_state_clean": clean,
    }


def _release_table_and_gate(
    artifact_dir: Path,
    plan: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    expected = _expected_pairs(plan)
    release_rows = []
    lifecycle_states = []
    failure_rows = []
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
        expected_count = 3 if lifecycle["track"] == "mechanism" else 9
        lifecycle_states.append(
            {
                "lifecycle_id": lifecycle_id,
                **_terminal_state(trace_rows, expected_count),
            }
        )

    exact_release_count = 0
    for pair in expected:
        candidates = [
            row
            for row in all_trace_by_lifecycle[pair["lifecycle_id"]]
            if row.get("event") == "pair_complete_released"
        ]
        matches = []
        for row in candidates:
            actual_ids = list(row.get("actual_request_ids") or [])
            normalized_ids, actual_id_contract_exact = _normalize_actual_ids(
                actual_ids
            )
            trace_canonical_ids = list(
                row.get("canonical_request_ids") or []
            )
            if (
                actual_id_contract_exact
                and normalized_ids == pair["canonical_request_ids"]
                and trace_canonical_ids == normalized_ids
                and row.get("pair_key") == pair["pair_key"]
            ):
                matches.append(row)
        actual_ids = list(matches[0].get("actual_request_ids") or []) if matches else []
        normalized_ids, actual_id_contract_exact = _normalize_actual_ids(
            actual_ids
        )
        exact = (
            len(matches) == 1
            and actual_id_contract_exact
            and normalized_ids == pair["canonical_request_ids"]
            and matches[0].get("pair_indices") == [0, 1]
            and matches[0].get("prompt_tokens") == pair["prompt_tokens"]
            and matches[0].get("release_order")
            == "pair_index_ascending_before_next_scheduler_step"
        )
        exact_release_count += int(exact)
        waits = matches[0].get("member_buffer_wait_ns") if matches else []
        release_rows.append(
            {
                **{
                    key: pair[key]
                    for key in (
                        "lifecycle_id",
                        "track",
                        "mode",
                        "batch_id",
                        "cell_id",
                    )
                },
                "canonical_request_id_0": pair["canonical_request_ids"][0],
                "canonical_request_id_1": pair["canonical_request_ids"][1],
                "actual_request_id_0": (
                    actual_ids[0] if len(actual_ids) == 2 else None
                ),
                "actual_request_id_1": (
                    actual_ids[1] if len(actual_ids) == 2 else None
                ),
                "actual_id_contract_exact": actual_id_contract_exact,
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
                    round(
                        max(float(value) for value in waits) / 1_000_000,
                        6,
                    )
                    if len(waits) == 2
                    else None
                ),
            }
        )

    terminal_states_clean = all(
        row["terminal_state_clean"] for row in lifecycle_states
    )
    release_gate = (
        len(installed_lifecycles) == len(r2.base.LIFECYCLE_SCHEDULE)
        and exact_release_count == len(expected)
        and not failure_rows
        and terminal_states_clean
    )
    return (
        {
            "installed_lifecycle_count": len(installed_lifecycles),
            "installed_lifecycles": installed_lifecycles,
            "expected_pair_release_count": len(expected),
            "exact_pair_release_count": exact_release_count,
            "failure_event_count": len(failure_rows),
            "failure_events": failure_rows,
            "lifecycle_terminal_states": lifecycle_states,
            "shutdown_state_observed_count": sum(
                row["shutdown_state_observed"] for row in lifecycle_states
            ),
            "checkpoint_terminal_state_used_count": sum(
                row["terminal_state_source"] == "post_release_checkpoint"
                for row in lifecycle_states
            ),
            "all_lifecycle_terminal_states_clean": terminal_states_clean,
            "atomic_pair_release_gate_complete": release_gate,
        },
        release_rows,
    )


def _normalized_scheduler_step(
    row: dict[str, Any],
) -> tuple[list[str], dict[str, int], bool]:
    actual_waiting = list(row.get("waiting_order_before") or [])
    canonical_waiting, waiting_valid = _normalize_actual_ids(actual_waiting)
    scheduled_items = list(row.get("scheduled_requests") or [])
    actual_scheduled = [
        str(item.get("request_id")) for item in scheduled_items
    ]
    canonical_scheduled_ids, scheduled_valid = _normalize_actual_ids(
        actual_scheduled
    )
    scheduled = {
        canonical_id: int(item.get("scheduled_tokens") or 0)
        for canonical_id, item in zip(
            canonical_scheduled_ids,
            scheduled_items,
            strict=True,
        )
    }
    no_duplicate_canonical_ids = (
        len(scheduled) == len(canonical_scheduled_ids)
    )
    return (
        canonical_waiting,
        scheduled,
        waiting_valid and scheduled_valid and no_duplicate_canonical_ids,
    )


def _first_step_table_and_gate(
    artifact_dir: Path,
    plan: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = []
    for pair in [
        item for item in _expected_pairs(plan) if item["track"] == "mechanism"
    ]:
        lifecycle_dir = artifact_dir / "lifecycles" / pair["lifecycle_id"]
        relevant_steps = []
        for row in r2.base._read_trace_rows(lifecycle_dir):
            if row.get("event") != "scheduler_step":
                continue
            canonical_waiting, scheduled, ids_valid = (
                _normalized_scheduler_step(row)
            )
            if any(
                request_id in {*canonical_waiting, *scheduled}
                for request_id in pair["canonical_request_ids"]
            ):
                relevant_steps.append(
                    (
                        int(row.get("step_index") or 0),
                        row,
                        canonical_waiting,
                        scheduled,
                        ids_valid,
                    )
                )
        relevant_steps.sort(key=lambda item: item[0])
        if relevant_steps:
            _, first, canonical_waiting, scheduled, ids_valid = relevant_steps[0]
        else:
            first, canonical_waiting, scheduled, ids_valid = {}, [], {}, False
        prompt_0, prompt_1 = [
            int(value) for value in pair["prompt_tokens"]
        ]
        if not pair["pressure"]:
            expected_scheduled = {
                pair["canonical_request_ids"][0]: prompt_0,
                pair["canonical_request_ids"][1]: prompt_1,
            }
        elif pair["mode"] == "chunked_prefill_off":
            expected_scheduled = {
                pair["canonical_request_ids"][0]: prompt_0
            }
        else:
            expected_scheduled = {
                pair["canonical_request_ids"][0]: prompt_0,
                pair["canonical_request_ids"][1]: (
                    r2.MAX_NUM_BATCHED_TOKENS - prompt_0
                ),
            }
        waiting_pair_exact = (
            canonical_waiting == pair["canonical_request_ids"]
        )
        scheduled_exact = scheduled == expected_scheduled
        total_exact = int(
            first.get("total_num_scheduled_tokens") or 0
        ) == sum(expected_scheduled.values())
        rows.append(
            {
                "lifecycle_id": pair["lifecycle_id"],
                "mode": pair["mode"],
                "cell_id": pair["cell_id"],
                "first_step_index": first.get("step_index"),
                "actual_id_contract_exact": ids_valid,
                "actual_waiting_order_before": json.dumps(
                    first.get("waiting_order_before") or [],
                    separators=(",", ":"),
                ),
                "canonical_waiting_order_before": json.dumps(
                    canonical_waiting,
                    separators=(",", ":"),
                ),
                "waiting_pair_exact": waiting_pair_exact,
                "canonical_scheduled_tokens": json.dumps(
                    scheduled,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "expected_scheduled_tokens": json.dumps(
                    expected_scheduled,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "scheduled_exact": scheduled_exact,
                "total_scheduled_exact": total_exact,
                "first_step_contract_exact": (
                    ids_valid
                    and waiting_pair_exact
                    and scheduled_exact
                    and total_exact
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


def prepare_artifacts(
    source_payload: Path,
    artifact_dir: Path,
    model_name: str,
) -> dict[str, Any]:
    with _configured_f3():
        return f3.prepare_artifacts(source_payload, artifact_dir, model_name)


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
        "max_member_wait_ms_max": (
            round(max(values), 6) if values else None
        ),
        "interpretation": (
            "common_request_id_normalized_atomic_coarrival_overhead_"
            "audited_both_modes_performance_effects_remain_descriptive"
        ),
    }


def _mapped_f4_grade(grade: str) -> str:
    return {
        (
            "candidate_green_p6_3c_r2_chunked_prefill_"
            "capacity_calibrated_matched_ab"
        ): (
            "candidate_green_p6_3c_r2_f4_chunked_prefill_"
            "request_id_normalized_atomic_coarrival_matched_ab"
        ),
        (
            "red_p6_3c_r2_f3_atomic_pair_admission_"
            "evidence_incomplete"
        ): (
            "red_p6_3c_r2_f4_atomic_pair_admission_"
            "evidence_incomplete"
        ),
        (
            "red_p6_3c_r2_f3_chunked_prefill_mechanism_"
            "evidence_incomplete"
        ): (
            "red_p6_3c_r2_f4_chunked_prefill_mechanism_"
            "evidence_incomplete"
        ),
        "red_p6_3c_r2_scheduler_pressure_no_success": (
            "red_p6_3c_r2_f4_scheduler_pressure_no_success"
        ),
        "yellow_p6_3c_r2_scheduler_pressure_partial": (
            "yellow_p6_3c_r2_f4_scheduler_pressure_partial"
        ),
        "red_p6_3c_r2_scheduler_pressure_evidence_incomplete": (
            "red_p6_3c_r2_f4_scheduler_pressure_evidence_incomplete"
        ),
        "red_p6_3c_r2_startup_kv_capacity_no_success": (
            "red_p6_3c_r2_f4_startup_kv_capacity_no_success"
        ),
    }.get(grade, grade)


def _f4_overlay_module_summary(artifact_dir: Path) -> dict[str, Any]:
    paths = [artifact_dir / "runtime_overlay_preflight_manifest.json"]
    paths.extend(
        artifact_dir
        / "lifecycles"
        / lifecycle["lifecycle_id"]
        / "runtime"
        / "runtime_overlay_manifest.json"
        for lifecycle in r2.base.LIFECYCLE_SCHEDULE
    )
    modules = []
    for path in paths:
        if not path.is_file():
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        modules.append(manifest.get("atomic_pair_admission_module"))
    expected = "p6_3c_r2_f4_atomic_pair_admission"
    return {
        "f4_overlay_module_manifest_count": len(modules),
        "f4_overlay_module_names": modules,
        "f4_overlay_module_gate_complete": (
            len(modules) == 7 and modules == [expected] * 7
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
            "- 原 P6.3C blocked、R1/R2/F1/F2 与 F3 "
            "`red_p6_3c_r2_f3_atomic_pair_admission_evidence_incomplete` "
            "全部作为独立审计保留；本任务不是 F3 run02。"
        ),
        (
            "- 共同冻结环境：`12288/12288/2`、Prefix Cache off、同一 "
            "hybrid-KV repair、同一 request-ID-normalized atomic pair "
            "admission；唯一 A/B 差异仍是 Chunked Prefill 显式 Off/On。"
        ),
        (
            f"- 请求 `{grading.get('successful_request_count')}/90`；"
            f"规范化成对释放 `{atomic['exact_pair_release_count']}/"
            f"{atomic['expected_pair_release_count']}`；"
            f"机制首轮合同 "
            f"`{atomic['first_scheduler_step_contract_exact_count']}/6`。"
        ),
        "",
        "## 请求 ID 与原子准入证据",
        "",
        (
            "- vLLM actual ID 必须严格符合 "
            "`cmpl-<canonical pair>-<0|1>-<8 hex>`；release 与 "
            "scheduler observer 共用同一 canonical 映射："
            f"`{atomic['request_id_normalization_gate_complete']}`。"
        ),
        (
            "- 两个 tagged measured request 在进入 Scheduler 前成对释放："
            f"`{atomic['atomic_pair_release_gate_complete']}`。"
        ),
        (
            "- 生命周期 terminal state 全部 clean："
            f"`{atomic['all_lifecycle_terminal_states_clean']}`；"
            "shutdown trace lifecycle="
            f"`{atomic['shutdown_state_observed_count']}/6`，"
            "post-release checkpoint fallback="
            f"`{atomic['checkpoint_terminal_state_used_count']}/6`。"
        ),
        (
            "- 每个机制 cell 首个 scheduler step 的 waiting 次序和 "
            "scheduled token 精确符合冻结预期："
            f"`{atomic['mechanism_atomic_coarrival_gate_complete']}`。"
        ),
        "",
        "## Chunked Prefill 机制证据",
        "",
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
        "## 性能与结论边界",
        "",
        "- 性能轨道仍为 Off→On→On→Off，scheduler observer/profiler 关闭。",
        (
            "- admission barrier 是两侧共同的受控实验环境；其等待开销单独"
            "记录，TTFT/E2EL/TPOT/ITL/吞吐只作该环境内描述。"
        ),
        "- candidate 结果仍须开发机逐文件复核后才能进入项目结论。",
        "- 不声明自然 API 到达行为、普遍性能收益或统计显著性。",
        "- 未获用户明确传输渠道选择前，不外发任何候选文件。",
        "",
    ]
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


@contextmanager
def _configured_f3_finalizer():
    replacements = {
        "_release_table_and_gate": _release_table_and_gate,
        "_first_step_table_and_gate": _first_step_table_and_gate,
        "_performance_barrier_summary": _performance_barrier_summary,
    }
    originals = {name: getattr(f3, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(f3, name, value)
        with _configured_f3():
            yield
    finally:
        for name, value in originals.items():
            setattr(f3, name, value)


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    with _configured_f3_finalizer():
        grading = f3.finalize_artifacts(artifact_dir)

    atomic_path = artifact_dir / ATOMIC_SUMMARY
    atomic = json.loads(atomic_path.read_text(encoding="utf-8"))
    release_rows = []
    with (artifact_dir / ATOMIC_RELEASE_TSV).open(
        encoding="utf-8",
        newline="",
    ) as handle:
        release_rows = list(csv.DictReader(handle, delimiter="\t"))
    first_step_rows = []
    with (artifact_dir / ATOMIC_FIRST_STEP_TSV).open(
        encoding="utf-8",
        newline="",
    ) as handle:
        first_step_rows = list(csv.DictReader(handle, delimiter="\t"))
    request_id_normalization_gate = (
        len(release_rows) == 42
        and all(row["actual_id_contract_exact"] == "True" for row in release_rows)
        and len(first_step_rows) == 6
        and all(
            row["actual_id_contract_exact"] == "True"
            for row in first_step_rows
        )
    )
    atomic.update(
        {
            "task_id": TASK_ID,
            "request_id_contract": (
                "cmpl-canonical-pair-index-8hex-runtime-suffix"
            ),
            "request_id_normalization_gate_complete": (
                request_id_normalization_gate
            ),
            "controller_scope": (
                "tagged_runtime_suffixed_f4_measured_request_pairs_only_"
                "all_other_requests_unchanged"
            ),
            "coarrival_gate_complete": (
                atomic["atomic_pair_release_gate_complete"]
                and atomic["mechanism_atomic_coarrival_gate_complete"]
                and request_id_normalization_gate
            ),
        }
    )
    atomic_path.write_text(
        json.dumps(atomic, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    mechanism_path = artifact_dir / "mechanism_scheduler_summary.json"
    mechanism = json.loads(mechanism_path.read_text(encoding="utf-8"))
    mechanism["atomic_pair_admission"].update(
        {
            "request_id_normalization_gate_complete": (
                request_id_normalization_gate
            ),
            "coarrival_gate_complete": atomic["coarrival_gate_complete"],
        }
    )
    mechanism["mechanism_gate_complete"] = (
        mechanism.get("mechanism_gate_complete") is True
        and atomic["coarrival_gate_complete"]
    )
    mechanism_path.write_text(
        json.dumps(mechanism, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    grade = _mapped_f4_grade(str(grading["server_grade"]))
    overlay_module = _f4_overlay_module_summary(artifact_dir)
    full_execution = (
        grading.get("all_lifecycles_success") is True
        and grading.get("successful_request_count") == 90
        and grading.get("successful_batch_count") == 48
    )
    runtime_and_transport_gates = (
        grading.get("startup_resource_gate_complete") is True
        and grading.get("shared_hybrid_kv_repair_exact_all_lifecycles")
        is True
        and grading.get("runtime_layout_gate_complete") is True
        and grading.get("loopback_transport_gate_complete") is True
        and grading.get("atomic_pair_admission_resolved_all_lifecycles")
        is True
        and overlay_module["f4_overlay_module_gate_complete"] is True
    )
    if (
        grade.startswith("candidate_green")
        and not (
            atomic["coarrival_gate_complete"]
            and runtime_and_transport_gates
        )
    ):
        grade = (
            "red_p6_3c_r2_f4_atomic_pair_admission_"
            "evidence_incomplete"
        )
    elif (
        full_execution
        and atomic["coarrival_gate_complete"]
        and mechanism.get("mechanism_gate_complete") is not True
    ):
        grade = (
            "red_p6_3c_r2_f4_chunked_prefill_mechanism_"
            "evidence_incomplete"
        )
    grading.update(
        {
            "task_id": TASK_ID,
            "server_grade": grade,
            "parent_p6_3c_r2_f3_grade_preserved": (
                "red_p6_3c_r2_f3_atomic_pair_admission_"
                "evidence_incomplete"
            ),
            "parent_p6_3c_r2_f3_overwritten": False,
            "request_id_normalization_gate_complete": (
                request_id_normalization_gate
            ),
            "f4_runtime_and_transport_gates_complete": (
                runtime_and_transport_gates
            ),
            **overlay_module,
            "atomic_pair_release_gate_complete": atomic[
                "atomic_pair_release_gate_complete"
            ],
            "mechanism_atomic_coarrival_gate_complete": atomic[
                "mechanism_atomic_coarrival_gate_complete"
            ],
            "coarrival_gate_complete": atomic["coarrival_gate_complete"],
            "mechanism_gate_complete": mechanism["mechanism_gate_complete"],
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
    environment.pop("f3_runner_sha256", None)
    environment.update(
        {
            "task_id": TASK_ID,
            "workload_path": WORKLOAD_RELATIVE_PATH,
            "workload_sha256": r2.base._optional_repo_sha256(
                WORKLOAD_RELATIVE_PATH
            ),
            "f4_runner_sha256": r2.base._sha256_path(Path(__file__)),
            "f4_atomic_pair_admission_sha256": (
                r2.base._optional_repo_sha256(
                    "tools/inference_contracts/"
                    "p6_3c_r2_f4_atomic_pair_admission.py"
                )
            ),
            "atomic_pair_request_prefix": REQUEST_ID_PREFIX,
            "atomic_pair_request_id_contract": (
                "canonical-member-id-plus-8hex-runtime-suffix"
            ),
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
    if grade.startswith("candidate_green"):
        first_failure_path.write_text("none\n", encoding="utf-8")
    elif full_execution:
        first_failure_path.write_text(
            f"server_grade={grade}\n"
            f"successful_request_count="
            f"{grading.get('successful_request_count')}/90\n"
            "request_id_normalization_gate_complete="
            f"{request_id_normalization_gate}\n"
            f"coarrival_gate_complete={atomic['coarrival_gate_complete']}\n"
            "mechanism_gate_complete="
            f"{mechanism['mechanism_gate_complete']}\n"
            "keep_alive_restore_exact="
            f"{grading.get('keep_alive_restore_exact')}\n",
            encoding="utf-8",
        )
    return grading


def execute_mode(
    artifact_dir: Path,
    lifecycle_dir: Path,
    base_url: str,
    server_pid: int,
    track: str,
    mode: str,
) -> int:
    with _configured_f3():
        return f3.execute_mode(
            artifact_dir,
            lifecycle_dir,
            base_url,
            server_pid,
            track,
            mode,
        )


def package_results(artifact_dir: Path) -> dict[str, Any]:
    with _configured_f3():
        return f3.package_results(artifact_dir)


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
