"""P6.3C-R3D persistent Prefill-pressure policy experiment.

R3C proved that a task-local per-iteration budget can run in the real
EngineCore, but its waiting-only condition capped only the first admitted
chunk.  R3D retains that admission-only T4096 policy as a contemporaneous
anchor and compares it with four policies that keep the cap active while the
long Prefill remains unfinished in the running queue.

Request generation, staged arrival, performance metrics, pairing, bootstrap
and Pareto aggregation are inherited from the audited R3B/R3C lineage.  This
module changes the policy state machine and strengthens the mechanism gate to
cover the complete Prefill chunk sequence.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts import (  # noqa: E402
    run_deepseek_p6_3c_r3c_adaptive_budget as parent,
)


base = parent.base
TASK_ID = "p6_3c_r3d_persistent_prefill_pressure_2026_0807_run01"
WORKLOAD_RELATIVE_PATH = (
    "benchmarks/deepseek_v4_flash/workloads/p6_3c_r3d_persistent_prefill_pressure.yaml"
)
REQUEST_PREFIX = "p6_3c_r3d"
MAX_MODEL_LEN = 12288
MAX_NUM_SEQS = 9
INJECTED_PROMPT_TOKENS = base.INJECTED_PROMPT_TOKENS
TRACKS = base.TRACKS
MODES = base.MODES
PERFORMANCE_CELL_SEQUENCE = base.PERFORMANCE_CELL_SEQUENCE
PERSISTENT_TARGETS = (128, 256, 512, 1024)

CONFIGS = (
    {
        "config_id": "off_b12288",
        "mode": "chunked_prefill_off",
        "max_num_batched_tokens": 12288,
        "policy_type": "static_off",
        "pressure_scope": "none",
    },
    {
        "config_id": "admission_on_t4096",
        "mode": "chunked_prefill_on",
        "max_num_batched_tokens": 12288,
        "policy_type": "adaptive_on",
        "pressure_scope": "admission_only",
        "active_chunk_target_tokens": 4096,
        "decode_quantum_tokens": 2,
    },
    *(
        {
            "config_id": f"persistent_on_t{target}",
            "mode": "chunked_prefill_on",
            "max_num_batched_tokens": 12288,
            "policy_type": "adaptive_on",
            "pressure_scope": "persistent_prefill",
            "active_chunk_target_tokens": target,
            "decode_quantum_tokens": 2,
        }
        for target in PERSISTENT_TARGETS
    ),
)
CONFIG_BY_ID = {row["config_id"]: row for row in CONFIGS}
ON_CONFIG_IDS = tuple(
    row["config_id"] for row in CONFIGS if row["mode"] == "chunked_prefill_on"
)


def _bind_base_globals() -> None:
    """Bind the audited staged-arrival implementation to the R3D contract."""

    base.TASK_ID = TASK_ID
    base.WORKLOAD_RELATIVE_PATH = WORKLOAD_RELATIVE_PATH
    base.REQUEST_PREFIX = REQUEST_PREFIX
    base.MAX_MODEL_LEN = MAX_MODEL_LEN
    base.MAX_NUM_SEQS = MAX_NUM_SEQS
    base.INJECTED_PROMPT_TOKENS = INJECTED_PROMPT_TOKENS
    base.CONFIGS = CONFIGS
    base.CONFIG_BY_ID = CONFIG_BY_ID
    base.ON_CONFIG_IDS = ON_CONFIG_IDS
    base.TRACKS = TRACKS
    base.MODES = MODES
    base.PERFORMANCE_CELL_SEQUENCE = PERFORMANCE_CELL_SEQUENCE
    base.LIFECYCLE_SCHEDULE = base._build_lifecycle_schedule()
    base.MECHANISM_LIFECYCLES = tuple(
        row for row in base.LIFECYCLE_SCHEDULE if row["track"] == "mechanism"
    )
    base.PERFORMANCE_LIFECYCLES = tuple(
        row for row in base.LIFECYCLE_SCHEDULE if row["track"] == "performance"
    )
    base.EXPECTED_MODEL_LIFECYCLES = len(base.LIFECYCLE_SCHEDULE)
    base.EXPECTED_ENGINE_REQUESTS = 10 * len(base.MECHANISM_LIFECYCLES) + 103 * len(
        base.PERFORMANCE_LIFECYCLES
    )
    base.EXPECTED_HTTP_REQUESTS = 3 * len(base.MECHANISM_LIFECYCLES) + 19 * len(
        base.PERFORMANCE_LIFECYCLES
    )
    base.EXPECTED_PERFORMANCE_TRIALS = len(base.PERFORMANCE_LIFECYCLES) * len(
        PERFORMANCE_CELL_SEQUENCE
    )
    base.EXPECTED_POLICY_SUMMARY_ROWS = len(CONFIGS) * 2
    base.EXPECTED_VALID_TRIALS_PER_SUMMARY = 12
    base.EXPECTED_POLICY_PAIRS = len(ON_CONFIG_IDS) * 2 * 6
    base.REFINALIZATION_TASK_ID = (
        "p6_3c_r3d_a1_persistent_prefill_reaggregation_2026_0807"
    )


def _read_observer_trace(lifecycle_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(
        (lifecycle_dir / "runtime/scheduler_trace").glob("trace.*.jsonl")
    ):
        rows.extend(base.r3a._read_jsonl(path))  # noqa: SLF001
    return rows


def _controller_trace(lifecycle_dir: Path) -> list[dict[str, Any]]:
    path = lifecycle_dir / "runtime/adaptive_scheduler_trace/schedule_decisions.jsonl"
    if not path.is_file():
        return []
    return base.r3a._read_jsonl(path)  # noqa: SLF001


def _injected_item(step: dict[str, Any], marker: str) -> dict[str, Any] | None:
    for item in step.get("scheduled_requests") or []:
        if (
            isinstance(item, dict)
            and marker in str(item.get("request_id"))
            and int(item.get("scheduled_prefill_tokens") or 0) > 0
        ):
            return item
    return None


def mechanism_budget_summary(
    artifact_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    trial = base._trial_plan("mechanism")[0]
    injection_marker = f"cmpl-{trial['injected_request_id']}"
    resident_marker = f"cmpl-{trial['resident_request_id']}-"
    rows: list[dict[str, Any]] = []

    for lifecycle in base.MECHANISM_LIFECYCLES:
        root = artifact_dir / "lifecycles" / lifecycle["lifecycle_id"]
        trace = _read_observer_trace(root)
        controller_rows = _controller_trace(root)
        observer_installed = any(
            row.get("event") == "observer_installed"
            and row.get("schema") == "p6_3c_r3_decode_resident_v1"
            for row in trace
        )
        relevant = [
            row
            for row in trace
            if row.get("event") == "scheduler_step"
            and injection_marker in json.dumps(row, separators=(",", ":"))
        ]
        relevant.sort(key=lambda row: int(row.get("step_index") or 0))
        chunk_steps = [
            (step, item)
            for step in relevant
            if (item := _injected_item(step, injection_marker)) is not None
        ]
        first_step, first_item = chunk_steps[0] if chunk_steps else ({}, {})
        first_items = [
            item
            for item in first_step.get("scheduled_requests") or []
            if isinstance(item, dict)
            and (
                injection_marker in str(item.get("request_id"))
                or resident_marker in str(item.get("request_id"))
            )
        ]
        resident_count = sum(
            resident_marker in str(item.get("request_id")) for item in first_items
        )
        chunk_sizes = [
            int(item.get("scheduled_prefill_tokens") or 0) for _, item in chunk_steps
        ]
        target = int(lifecycle["active_chunk_target_tokens"])
        scope = str(lifecycle["pressure_scope"])
        per_chunk_contracts: list[bool] = []
        running_prefill_pressure_steps = 0
        admission_reversion_steps = 0
        pressure_chunk_count = 0
        full_budget_chunk_count = 0
        preempted = sorted(
            {
                str(request_id)
                for step in relevant
                for request_id in step.get("preempted_request_ids") or []
            }
        )

        for index, (step, item) in enumerate(chunk_steps):
            decision = step.get("controller_decision") or {}
            chunk = int(item.get("scheduled_prefill_tokens") or 0)
            remaining = int(item.get("remaining_prompt_tokens") or 0)
            decode_count = int(decision.get("decode_resident_count") or 0)
            waiting_count = int(decision.get("waiting_prefill_count") or 0)
            running_unfinished = int(
                decision.get("running_unfinished_prefill_count") or 0
            )
            selected_budget = int(decision.get("selected_budget") or 0)
            configured_budget = int(decision.get("configured_budget") or 0)
            scheduled_resident_tokens = int(step.get("resident_decode_tokens") or 0)
            decision_name = decision.get("decision")
            pressure_active = decision.get("pressure_active") is True
            if decision_name == "pressure_capped":
                pressure_chunk_count += 1
            elif decision_name == "full_budget":
                full_budget_chunk_count += 1

            if index > 0 and waiting_count == 0 and running_unfinished > 0:
                if decision_name == "pressure_capped":
                    running_prefill_pressure_steps += 1
                elif decision_name == "full_budget" and decode_count > 0:
                    admission_reversion_steps += 1

            if pressure_active:
                expected_budget = min(12288, decode_count * 2 + target)
                contract = all(
                    (
                        decode_count > 0,
                        decision_name == "pressure_capped",
                        selected_budget == expected_budget,
                        configured_budget == 12288,
                        chunk
                        == min(
                            max(selected_budget - scheduled_resident_tokens, 0),
                            remaining,
                        ),
                    )
                )
            else:
                contract = all(
                    (
                        decision_name == "full_budget",
                        selected_budget == configured_budget == 12288,
                        0 < chunk <= remaining,
                    )
                )
            per_chunk_contracts.append(contract)

        first_decision = first_step.get("controller_decision") or {}
        first_chunk = int(first_item.get("scheduled_prefill_tokens") or 0)
        scope_specific_complete = (
            running_prefill_pressure_steps > 0 and admission_reversion_steps == 0
            if scope == "persistent_prefill"
            else admission_reversion_steps > 0 and running_prefill_pressure_steps == 0
        )
        row = {
            **lifecycle,
            "observer_installed": observer_installed,
            "relevant_step_count": len(relevant),
            "controller_trace_count": len(controller_rows),
            "resident_running_count_first_step": resident_count,
            "resident_decode_tokens_first_step": int(
                first_step.get("resident_decode_tokens") or 0
            ),
            "controller_first_decision": first_decision.get("decision"),
            "controller_first_pressure_scope": first_decision.get("pressure_scope"),
            "configured_max_num_batched_tokens": int(
                lifecycle["max_num_batched_tokens"]
            ),
            "token_budget_first_step": int(
                first_step.get("effective_token_budget") or 0
            ),
            "injected_tokens_first_step": first_chunk,
            "first_step_partial": first_item.get("prefill_partial"),
            "first_step_mixed": first_step.get("mixed_decode_prefill"),
            "prefill_chunk_count": len(chunk_sizes),
            "prefill_chunk_sizes": ",".join(str(value) for value in chunk_sizes),
            "observed_prefill_tokens": sum(chunk_sizes),
            "pressure_chunk_count": pressure_chunk_count,
            "full_budget_chunk_count": full_budget_chunk_count,
            "running_prefill_pressure_step_count": running_prefill_pressure_steps,
            "admission_reversion_step_count": admission_reversion_steps,
            "per_chunk_budget_contract_complete": bool(per_chunk_contracts)
            and all(per_chunk_contracts),
            "scope_specific_sequence_complete": scope_specific_complete,
            "preempted_request_ids": ",".join(preempted),
        }
        row["mechanism_contract_complete"] = all(
            (
                observer_installed,
                bool(controller_rows),
                bool(chunk_steps),
                resident_count == base.r3a.RESIDENT_COUNT,
                row["resident_decode_tokens_first_step"] > 0,
                first_decision.get("decision") == "pressure_capped",
                first_decision.get("pressure_scope") == scope,
                first_chunk == target,
                row["first_step_partial"] is True,
                row["first_step_mixed"] is True,
                sum(chunk_sizes) == INJECTED_PROMPT_TOKENS,
                row["per_chunk_budget_contract_complete"],
                scope_specific_complete,
                not preempted,
            )
        )
        rows.append(row)

    complete = len(rows) == len(base.MECHANISM_LIFECYCLES) and all(
        row["mechanism_contract_complete"] for row in rows
    )
    summary = {
        "task_id": TASK_ID,
        "policy_count": len(rows),
        "expected_policy_count": len(base.MECHANISM_LIFECYCLES),
        "all_policy_mechanisms_complete": complete,
        "all_budget_mechanisms_complete": complete,
        "full_prefill_sequence_gate_complete": complete,
        "persistent_running_prefill_pressure_observed": all(
            row["running_prefill_pressure_step_count"] > 0
            for row in rows
            if row["pressure_scope"] == "persistent_prefill"
        ),
        "admission_only_reversion_observed": all(
            row["admission_reversion_step_count"] > 0
            for row in rows
            if row["pressure_scope"] == "admission_only"
        ),
        "configured_budget_preserved_for_all_on": all(
            row["configured_max_num_batched_tokens"] == 12288 for row in rows
        ),
        "scientific_contract_changed_from_r3c": True,
        "change": (
            "waiting-only admission cap versus cap sustained through running "
            "unfinished Prefill"
        ),
        "performance_authorized": complete,
    }
    return summary, rows


def write_mechanism_evidence(artifact_dir: Path) -> dict[str, Any]:
    summary, rows = mechanism_budget_summary(artifact_dir)
    (artifact_dir / "r3d_mechanism_sequence_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "mechanism_scheduler_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    base._write_tsv(artifact_dir / "r3d_mechanism_sequence_cells.tsv", rows)
    return summary


def controller_evidence(artifact_dir: Path) -> dict[str, Any]:
    lifecycle_rows: list[dict[str, Any]] = []
    for lifecycle in base.LIFECYCLE_SCHEDULE:
        traces = _controller_trace(
            artifact_dir / "lifecycles" / lifecycle["lifecycle_id"]
        )
        running_pressure = sum(
            row.get("decision") == "pressure_capped"
            and int(row.get("waiting_prefill_count") or 0) == 0
            and int(row.get("running_unfinished_prefill_count") or 0) > 0
            for row in traces
        )
        running_reversion = sum(
            row.get("decision") == "full_budget"
            and int(row.get("waiting_prefill_count") or 0) == 0
            and int(row.get("running_unfinished_prefill_count") or 0) > 0
            and int(row.get("decode_resident_count") or 0) > 0
            for row in traces
        )
        lifecycle_rows.append(
            {
                "lifecycle_id": lifecycle["lifecycle_id"],
                "config_id": lifecycle["config_id"],
                "policy_type": lifecycle["policy_type"],
                "pressure_scope": lifecycle["pressure_scope"],
                "controller_trace_count": len(traces),
                "pressure_capped_count": sum(
                    row.get("decision") == "pressure_capped" for row in traces
                ),
                "full_budget_count": sum(
                    row.get("decision") == "full_budget" for row in traces
                ),
                "running_prefill_pressure_count": running_pressure,
                "running_prefill_reversion_count": running_reversion,
                "configured_budget_preserved": all(
                    int(row.get("configured_budget") or 0) == 12288 for row in traces
                ),
            }
        )

    adaptive_rows = [
        row for row in lifecycle_rows if row["policy_type"] == "adaptive_on"
    ]
    static_rows = [row for row in lifecycle_rows if row["policy_type"] == "static_off"]
    trace_complete = bool(adaptive_rows) and all(
        row["controller_trace_count"] > 0
        and row["pressure_capped_count"] > 0
        and row["full_budget_count"] > 0
        and row["configured_budget_preserved"]
        and (
            row["running_prefill_pressure_count"] > 0
            if row["pressure_scope"] == "persistent_prefill"
            else row["running_prefill_reversion_count"] > 0
        )
        for row in adaptive_rows
    )
    summary = {
        "task_id": TASK_ID,
        "schema": "p6_3c_r3d_persistent_scheduler_v1",
        "lifecycle_rows": lifecycle_rows,
        "adaptive_trace_contract_complete": trace_complete,
        "static_trace_absent": all(
            row["controller_trace_count"] == 0 for row in static_rows
        ),
        "configured_budget_preserved_for_adaptive": all(
            row["configured_budget_preserved"] for row in adaptive_rows
        ),
        "persistent_running_prefill_pressure_decision_count": sum(
            row["running_prefill_pressure_count"] for row in adaptive_rows
        ),
        "admission_only_running_prefill_reversion_decision_count": sum(
            row["running_prefill_reversion_count"] for row in adaptive_rows
        ),
        "trace_is_control_evidence_not_performance_metric": True,
    }
    (artifact_dir / "r3d_controller_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def _rewrite_outputs(artifact_dir: Path) -> None:
    for stem in (
        "policy_uncertainty",
        "pareto_frontier",
        "policy_summary",
        "policy_paired_effects",
    ):
        suffix = "json" if stem in ("policy_uncertainty", "pareto_frontier") else "tsv"
        old = artifact_dir / f"r3b_{stem}.{suffix}"
        new = artifact_dir / f"r3d_{stem}.{suffix}"
        if old.is_file():
            old.replace(new)


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    grading = base.finalize_artifacts(artifact_dir, analysis_task_id=TASK_ID)
    _rewrite_outputs(artifact_dir)
    controller_summary = controller_evidence(artifact_dir)
    mechanism = json.loads(
        (artifact_dir / "r3d_mechanism_sequence_summary.json").read_text(
            encoding="utf-8"
        )
    )
    frontier = json.loads(
        (artifact_dir / "r3d_pareto_frontier.json").read_text(encoding="utf-8")
    )
    performance_complete = bool(
        grading.get("performance_analysis_complete")
        and grading.get("performance_lifecycles_complete")
    )
    evidence_complete = all(
        (
            grading.get("evidence_status") == "complete",
            mechanism["full_prefill_sequence_gate_complete"],
            controller_summary["adaptive_trace_contract_complete"],
            controller_summary["static_trace_absent"],
            controller_summary["configured_budget_preserved_for_adaptive"],
            performance_complete,
        )
    )
    bound_ids = frontier.get("deployment_bound_config_ids", [])
    if not mechanism["full_prefill_sequence_gate_complete"]:
        scientific = "persistent_prefill_mechanism_incomplete"
    elif not performance_complete:
        scientific = "persistent_prefill_performance_incomplete"
    elif bound_ids:
        scientific = "persistent_prefill_policy_candidate_found_within_bounds"
    else:
        scientific = "persistent_prefill_tradeoff_no_candidate_within_bounds"

    grading.update(
        {
            "task_id": TASK_ID,
            "source_task_id": "p6_3c_r3c_adaptive_budget_2026_0805_run01",
            "server_grade": "complete_p6_3c_r3d_persistent_prefill_evidence"
            if evidence_complete
            else "incomplete_p6_3c_r3d_persistent_prefill_evidence",
            "evidence_status": "complete" if evidence_complete else "incomplete",
            "scientific_outcome": scientific,
            "scientific_contract_changed_from_r3c": True,
            "full_prefill_sequence_gate_complete": mechanism[
                "full_prefill_sequence_gate_complete"
            ],
            "persistent_running_prefill_pressure_observed": mechanism[
                "persistent_running_prefill_pressure_observed"
            ],
            "admission_only_reversion_observed": mechanism[
                "admission_only_reversion_observed"
            ],
            "adaptive_controller_trace_complete": controller_summary[
                "adaptive_trace_contract_complete"
            ],
            "configured_budget_preserved_for_adaptive": True,
            "automatic_next_stage_selection": False,
            "universal_benefit_claimed": False,
        }
    )
    (artifact_dir / "grading_inputs.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    outcome = {
        "task_id": TASK_ID,
        "source_task_id": grading["source_task_id"],
        "scientific_outcome": scientific,
        "evidence_complete": evidence_complete,
        "pareto_config_ids": frontier.get("pareto_config_ids", []),
        "deployment_bound_config_ids": bound_ids,
        "full_prefill_sequence_gate_complete": grading[
            "full_prefill_sequence_gate_complete"
        ],
        "claim_boundary": (
            "controlled_decode_resident_admission_cliff_persistent_prefill_policy_only"
        ),
    }
    (artifact_dir / "scientific_outcome.json").write_text(
        json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    environment_path = artifact_dir / "environment_and_hashes.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    overlay_smoke_path = artifact_dir / "runtime_overlay_preflight_smoke.json"
    overlay_smoke = (
        json.loads(overlay_smoke_path.read_text(encoding="utf-8"))
        if overlay_smoke_path.is_file()
        else None
    )
    environment.update(
        {
            "task_id": TASK_ID,
            "source_task_id": grading["source_task_id"],
            "workload_path": WORKLOAD_RELATIVE_PATH,
            "policy_configs": list(CONFIGS),
            "adaptive_controller": {
                "schema": "p6_3c_r3d_persistent_scheduler_v1",
                "configured_budget_preserved": True,
                "admission_only_anchor_target": 4096,
                "persistent_target_grid": list(PERSISTENT_TARGETS),
                "persistent_pressure_condition": (
                    "decode_resident_count>0 and "
                    "(waiting_prefill_count+running_unfinished_prefill_count)>0"
                ),
                "scheduler_field_changed": "max_num_scheduled_tokens_only",
            },
            "max_num_batched_tokens": 12288,
            "active_chunk_targets": [4096, *PERSISTENT_TARGETS],
            "runtime_overlay_import_smoke": overlay_smoke,
        }
    )
    environment_path.write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    summary_lines = [
        f"# {TASK_ID} 结果摘要",
        "",
        f"- evidence status: `{grading['evidence_status']}`",
        f"- scientific outcome: `{scientific}`",
        "- R3D 比较 contemporaneous Off、R3C waiting-only T4096 anchor 与四档 persistent Prefill-pressure policy。",
        f"- 完整 Prefill chunk-sequence gate: `{grading['full_prefill_sequence_gate_complete']}`。",
        f"- running unfinished Prefill 持续限额证据: `{grading['persistent_running_prefill_pressure_observed']}`；waiting-only 回退 full budget 证据: `{grading['admission_only_reversion_observed']}`。",
        f"- 非支配配置：`{frontier.get('pareto_config_ids', [])}`。",
        f"- deployment bounds 内的配置：`{bound_ids}`。",
        "- 结论只覆盖受控 decode-resident admission cliff，不外推自然 API、生产 SLO 或普遍收益。",
        "- R3C、R3B、R3A、F4 与原始 blocked 审计均保留。",
        "",
    ]
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(summary_lines), encoding="utf-8"
    )
    return grading


BOUNDED_CANDIDATES = (
    "result_summary.md",
    "environment_and_hashes.json",
    "payload_identity_summary.json",
    "lifecycle_summary.tsv",
    "r3d_mechanism_sequence_summary.json",
    "r3d_mechanism_sequence_cells.tsv",
    "r3d_policy_summary.tsv",
    "r3d_policy_paired_effects.tsv",
    "r3d_policy_uncertainty.json",
    "r3d_pareto_frontier.json",
    "r3d_controller_summary.json",
    "scientific_outcome.json",
    "grading_inputs.json",
    "startup_resource_summary.tsv",
    "runtime_overlay_preflight_smoke.json",
    "resource_recovery_summary.json",
    "cleanup_status.txt",
    "first_failure_excerpt.txt",
)


def _activate_contract() -> None:
    """Activate R3D bindings only for an R3D command invocation.

    Keeping this out of module import avoids changing the shared R3B analysis
    module underneath R3C unit tests that happen to be collected in the same
    Python process.
    """

    _bind_base_globals()
    base.BOUNDED_CANDIDATES = BOUNDED_CANDIDATES
    base.write_mechanism_evidence = write_mechanism_evidence


def package_results(artifact_dir: Path) -> dict[str, Any]:
    _activate_contract()
    return base.package_results(artifact_dir)


def main(argv: list[str] | None = None) -> int:
    import argparse

    _activate_contract()
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    run_mode = sub.add_parser("run-mode")
    run_mode.add_argument("--artifact-dir", type=Path, required=True)
    run_mode.add_argument("--lifecycle-dir", type=Path, required=True)
    run_mode.add_argument("--base-url", required=True)
    run_mode.add_argument("--server-pid", type=int, required=True)
    run_mode.add_argument("--track", choices=TRACKS, required=True)
    run_mode.add_argument("--mode", choices=MODES, required=True)
    gate = sub.add_parser("mechanism-gate")
    gate.add_argument("--artifact-dir", type=Path, required=True)
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    package = sub.add_parser("package")
    package.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "prepare":
        base.prepare_artifacts(args.source_payload, args.artifact_dir, args.model_name)
        return 0
    if args.command == "run-mode":
        return base.execute_mode(
            args.artifact_dir,
            args.lifecycle_dir,
            args.base_url,
            args.server_pid,
            args.track,
            args.mode,
        )
    if args.command == "mechanism-gate":
        summary = write_mechanism_evidence(args.artifact_dir)
        return 0 if summary["performance_authorized"] else 3
    if args.command == "finalize":
        grading = finalize_artifacts(args.artifact_dir)
        return 0 if grading["evidence_status"] == "complete" else 2
    if args.command == "package":
        package_results(args.artifact_dir)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
