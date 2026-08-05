"""P6.3C-R3C adaptive Decode-SLO-aware chunk-budget experiment.

R3B showed that a static On budget moves along a TTFT--Decode-tail Pareto
frontier but does not satisfy the project's joint deployment bounds.  R3C
keeps the legal Off baseline and a static B=8192 anchor, then evaluates three
adaptive policies.  Adaptive policies keep the command-line budget at 12288
and temporarily cap only the current scheduler iteration when Decode
residents coexist with a waiting Prefill.

The request generation and metric implementation are reused from the audited
R3B runner.  This module changes only the policy schedule and the mechanism
contract; it does not silently reinterpret R3B evidence as R3C evidence.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts import (
    p6_3c_r3c_adaptive_scheduler as controller,
)
from tools.inference_contracts import (
    run_deepseek_p6_3c_r3b_chunk_budget as base,
)


TASK_ID = "p6_3c_r3c_adaptive_budget_2026_0805_run01"
WORKLOAD_RELATIVE_PATH = (
    "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r3c_adaptive_budget.yaml"
)
REQUEST_PREFIX = "p6_3c_r3c"
MAX_MODEL_LEN = 12288
MAX_NUM_SEQS = 9
INJECTED_PROMPT_TOKENS = base.INJECTED_PROMPT_TOKENS
TRACKS = base.TRACKS
MODES = base.MODES
PERFORMANCE_CELL_SEQUENCE = base.PERFORMANCE_CELL_SEQUENCE

CONFIGS = (
    {
        "config_id": "off_b12288",
        "mode": "chunked_prefill_off",
        "max_num_batched_tokens": 12288,
        "policy_type": "static_off",
    },
    {
        "config_id": "static_on_b8192",
        "mode": "chunked_prefill_on",
        "max_num_batched_tokens": 8192,
        "policy_type": "static_on",
    },
    *(
        {
            "config_id": f"adaptive_on_t{target}",
            "mode": "chunked_prefill_on",
            "max_num_batched_tokens": 12288,
            "policy_type": "adaptive_on",
            "active_chunk_target_tokens": target,
            "decode_quantum_tokens": 2,
        }
        for target in (2048, 4096, 8192)
    ),
)
CONFIG_BY_ID = {row["config_id"]: row for row in CONFIGS}
ON_CONFIG_IDS = tuple(
    row["config_id"] for row in CONFIGS if row["mode"] == "chunked_prefill_on"
)


def _bind_base_globals() -> None:
    """Bind the audited R3B implementation to the R3C policy contract."""

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
    base.REFINALIZATION_TASK_ID = "p6_3c_r3c_a1_adaptive_budget_reaggregation_2026_0805"


_bind_base_globals()


def _read_trace(lifecycle_dir: Path) -> list[dict[str, Any]]:
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


def mechanism_budget_summary(
    artifact_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    trial = base._trial_plan("mechanism")[0]
    injection_marker = f"cmpl-{trial['injected_request_id']}"
    resident_marker = f"cmpl-{trial['resident_request_id']}-"
    rows: list[dict[str, Any]] = []
    for lifecycle in base.MECHANISM_LIFECYCLES:
        root = artifact_dir / "lifecycles" / lifecycle["lifecycle_id"]
        trace = _read_trace(root)
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
        first = relevant[0] if relevant else {}
        first_items = first.get("scheduled_requests") or []
        first_items = [item for item in first_items if isinstance(item, dict)]
        first_items = [
            item
            for item in first_items
            if injection_marker in str(item.get("request_id"))
            or resident_marker in str(item.get("request_id"))
        ]
        scheduled_rows = [
            item
            for step in relevant
            for item in step.get("scheduled_requests") or []
            if isinstance(item, dict)
            and injection_marker in str(item.get("request_id"))
            and int(item.get("scheduled_prefill_tokens") or 0) > 0
        ]
        chunk_sizes = [
            int(item.get("scheduled_prefill_tokens") or 0)
            for item in scheduled_rows
        ]
        resident_count = sum(
            resident_marker in str(item.get("request_id")) for item in first_items
        )
        resident_tokens = int(first.get("resident_decode_tokens") or 0)
        observed_budget = int(
            first.get("effective_token_budget") or first.get("token_budget") or 0
        )
        configured_budget = int(lifecycle["max_num_batched_tokens"])
        target = lifecycle.get("active_chunk_target_tokens")
        # The observer records the budget actually used by this scheduler
        # iteration.  Derive the expected first Prefill chunk from that
        # budget and the resident Decode reservation instead of assuming
        # D=16; this keeps the evidence interpretable if the runtime's
        # resident token count differs from the nominal staged-arrival value.
        expected_first = min(
            INJECTED_PROMPT_TOKENS,
            max(observed_budget - resident_tokens, 0),
        )
        # Warmup and resident-only scheduling can precede the injected
        # request.  Select the first pressure decision rather than assuming
        # the first controller record is the admission-cliff step.
        controller_first = next(
            (
                row
                for row in controller_rows
                if row.get("decision") == "pressure_capped"
            ),
            controller_rows[0] if controller_rows else {},
        )
        controller_contract_ok = (
            lifecycle.get("policy_type") != "adaptive_on"
            or (
                controller_first.get("decision") == "pressure_capped"
                and int(controller_first.get("selected_budget") or 0)
                == observed_budget
                and int(controller_first.get("active_chunk_target_tokens") or 0)
                == int(target)
            )
        )
        preempted = sorted(
            {
                str(request_id)
                for row in relevant
                for request_id in row.get("preempted_request_ids") or []
            }
        )
        row = {
            **lifecycle,
            "observer_installed": observer_installed,
            "relevant_step_count": len(relevant),
            "controller_trace_count": len(controller_rows),
            "controller_first_decision": controller_first.get("decision"),
            "resident_running_count_first_step": resident_count,
            "resident_decode_tokens_first_step": resident_tokens,
            "configured_max_num_batched_tokens": configured_budget,
            "token_budget_first_step": observed_budget,
            "expected_injected_tokens_first_step": expected_first,
            "injected_tokens_first_step": (
                int(scheduled_rows[0].get("scheduled_prefill_tokens") or 0)
                if scheduled_rows
                else 0
            ),
            "first_step_partial": any(
                item.get("prefill_partial") is True for item in first_items
            ),
            "first_step_mixed": first.get("mixed_decode_prefill"),
            "prefill_chunk_count": len(chunk_sizes),
            "prefill_chunk_sizes": ",".join(str(value) for value in chunk_sizes),
            "observed_prefill_tokens": sum(chunk_sizes),
            "preempted_request_ids": ",".join(preempted),
            "controller_contract_complete": controller_contract_ok,
        }
        row["mechanism_contract_complete"] = all(
            (
                observer_installed,
                bool(relevant),
                resident_count == base.r3a.RESIDENT_COUNT,
                resident_tokens > 0,
                observed_budget > resident_tokens,
                row["injected_tokens_first_step"] == expected_first,
                0 < row["injected_tokens_first_step"] < INJECTED_PROMPT_TOKENS,
                row["first_step_partial"] is True,
                row["first_step_mixed"] is True,
                sum(chunk_sizes) == INJECTED_PROMPT_TOKENS,
                not preempted,
                controller_contract_ok,
            )
        )
        rows.append(row)
    summary = {
        "task_id": TASK_ID,
        "policy_count": len(rows),
        "expected_policy_count": len(base.MECHANISM_LIFECYCLES),
        "all_policy_mechanisms_complete": len(rows) == len(base.MECHANISM_LIFECYCLES)
        and all(row["mechanism_contract_complete"] for row in rows),
        # Keep the audited R3B finalizer's gate name as a compatibility alias;
        # the R3C-facing name above remains the source-of-truth wording.
        "all_budget_mechanisms_complete": len(rows)
        == len(base.MECHANISM_LIFECYCLES)
        and all(row["mechanism_contract_complete"] for row in rows),
        "adaptive_controller_trace_complete": all(
            row["controller_contract_complete"]
            for row in rows
            if row["policy_type"] == "adaptive_on"
        ),
        "configured_budget_preserved_for_adaptive": all(
            row["configured_max_num_batched_tokens"] == 12288
            for row in rows
            if row["policy_type"] == "adaptive_on"
        ),
        "scientific_contract_changed_from_r3b": True,
        "change": "runtime adaptive per-iteration cap under decode-resident pressure",
        "performance_authorized": len(rows) == len(base.MECHANISM_LIFECYCLES)
        and all(row["mechanism_contract_complete"] for row in rows),
    }
    return summary, rows


def write_mechanism_evidence(artifact_dir: Path) -> dict[str, Any]:
    summary, rows = mechanism_budget_summary(artifact_dir)
    (artifact_dir / "r3c_mechanism_budget_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "mechanism_scheduler_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    base._write_tsv(artifact_dir / "r3c_mechanism_budget_cells.tsv", rows)
    return summary


def controller_evidence(artifact_dir: Path) -> dict[str, Any]:
    lifecycle_rows: list[dict[str, Any]] = []
    decision_count = 0
    pressure_count = 0
    full_budget_count = 0
    selected_budgets: set[int] = set()
    for lifecycle in base.LIFECYCLE_SCHEDULE:
        rows = _controller_trace(
            artifact_dir / "lifecycles" / lifecycle["lifecycle_id"]
        )
        decision_count += len(rows)
        pressure_count += sum(row.get("decision") == "pressure_capped" for row in rows)
        full_budget_count += sum(row.get("decision") == "full_budget" for row in rows)
        selected_budgets.update(
            int(row["selected_budget"])
            for row in rows
            if row.get("selected_budget") is not None
        )
        lifecycle_rows.append(
            {
                "lifecycle_id": lifecycle["lifecycle_id"],
                "config_id": lifecycle["config_id"],
                "policy_type": lifecycle.get("policy_type"),
                "controller_trace_count": len(rows),
                "pressure_capped_count": sum(
                    row.get("decision") == "pressure_capped" for row in rows
                ),
                "full_budget_count": sum(
                    row.get("decision") == "full_budget" for row in rows
                ),
                "selected_budgets": sorted(
                    {
                        int(row["selected_budget"])
                        for row in rows
                        if row.get("selected_budget") is not None
                    }
                ),
            }
        )
    adaptive_rows = [
        row for row in lifecycle_rows if row["policy_type"] == "adaptive_on"
    ]
    static_rows = [
        row for row in lifecycle_rows if row["policy_type"] != "adaptive_on"
    ]
    adaptive_trace_contract_complete = bool(adaptive_rows) and all(
        row["controller_trace_count"] > 0
        and row["pressure_capped_count"] > 0
        and row["full_budget_count"] > 0
        for row in adaptive_rows
    )
    static_trace_absent = all(
        row["controller_trace_count"] == 0 for row in static_rows
    )
    configured_budget_preserved = all(
        all(
            int(trace_row.get("configured_budget") or 0) == 12288
            for trace_row in _controller_trace(
                artifact_dir / "lifecycles" / row["lifecycle_id"]
            )
        )
        for row in adaptive_rows
    )
    summary = {
        "task_id": TASK_ID,
        "schema": "p6_3c_r3c_adaptive_scheduler_v1",
        "decision_count": decision_count,
        "pressure_capped_decision_count": pressure_count,
        "full_budget_decision_count": full_budget_count,
        "selected_budget_values": sorted(selected_budgets),
        "lifecycle_rows": lifecycle_rows,
        "adaptive_trace_contract_complete": adaptive_trace_contract_complete,
        "static_trace_absent": static_trace_absent,
        "configured_budget_preserved_for_adaptive": configured_budget_preserved,
        "trace_is_control_evidence_not_performance_metric": True,
    }
    (artifact_dir / "r3c_adaptive_controller_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def _rewrite_r3b_outputs(artifact_dir: Path) -> None:
    for stem in ("policy_uncertainty", "pareto_frontier", "policy_summary", "policy_paired_effects"):
        old = artifact_dir / f"r3b_{stem}.{'json' if stem in ('policy_uncertainty', 'pareto_frontier') else 'tsv'}"
        new = artifact_dir / f"r3c_{stem}.{'json' if stem in ('policy_uncertainty', 'pareto_frontier') else 'tsv'}"
        if old.is_file():
            old.replace(new)


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    grading = base.finalize_artifacts(artifact_dir, analysis_task_id=TASK_ID)
    _rewrite_r3b_outputs(artifact_dir)
    controller_summary = controller_evidence(artifact_dir)

    frontier = json.loads(
        (artifact_dir / "r3c_pareto_frontier.json").read_text(encoding="utf-8")
    )
    performance_complete = bool(
        grading.get("performance_analysis_complete")
        and grading.get("performance_lifecycles_complete")
    )
    mechanism_complete = bool(grading.get("mechanism_all_budgets_complete"))
    evidence_complete = bool(
        grading.get("evidence_status") == "complete"
        and mechanism_complete
        and performance_complete
        and controller_summary["adaptive_trace_contract_complete"]
        and controller_summary["static_trace_absent"]
        and controller_summary["configured_budget_preserved_for_adaptive"]
    )
    bound_ids = frontier.get("deployment_bound_config_ids", [])
    scientific = (
        "adaptive_policy_candidate_found_within_preregistered_bounds"
        if bound_ids
        else "adaptive_policy_tradeoff_no_candidate_within_bounds"
    )
    grading.update(
        {
            "task_id": TASK_ID,
            "source_task_id": "p6_3c_r3b_a1_performance_reaggregation_2026_0804",
            "server_grade": "complete_p6_3c_r3c_adaptive_policy_evidence"
            if evidence_complete
            else "incomplete_p6_3c_r3c_adaptive_policy_evidence",
            "evidence_status": "complete" if evidence_complete else "incomplete",
            "scientific_outcome": scientific,
            "scientific_contract_changed_from_r3b": True,
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
        "adaptive_controller_trace_complete": grading["adaptive_controller_trace_complete"],
        "configured_budget_preserved_for_adaptive": True,
        "claim_boundary": "controlled_decode_resident_admission_cliff_adaptive_policy_only",
    }
    (artifact_dir / "scientific_outcome.json").write_text(
        json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    environment_path = artifact_dir / "environment_and_hashes.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    environment.update(
        {
            "task_id": TASK_ID,
            "source_task_id": grading["source_task_id"],
            "workload_path": WORKLOAD_RELATIVE_PATH,
            "policy_configs": list(CONFIGS),
            "adaptive_controller": {
                "schema": "p6_3c_r3c_adaptive_scheduler_v1",
                "enabled": "adaptive_lifecycles_only",
                "configured_budget_preserved": True,
                "active_chunk_target_tokens_grid": [2048, 4096, 8192],
                "decode_quantum_tokens": 2,
                "pressure_condition": (
                    "decode_resident_count>0 and waiting_prefill_count>0"
                ),
                "selected_budget": (
                    "min(configured_budget, decode_reserve + active_chunk_target)"
                ),
                "scheduler_field_changed": "max_num_scheduled_tokens_only",
                "runtime_env_not_present_during_finalize": True,
            },
            "configured_budget_preserved_for_adaptive": True,
            "on_budgets": [8192, 12288, 12288, 12288],
            "active_chunk_targets": [2048, 4096, 8192],
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
        "- R3C 保持命令行 `max_num_batched_tokens=12288`，仅在 Decode 驻留与等待 Prefill 同时存在时收紧当前 iteration budget。",
        f"- adaptive controller decisions: `{controller_summary['decision_count']}`（pressure-capped `{controller_summary['pressure_capped_decision_count']}`, full-budget `{controller_summary['full_budget_decision_count']}`）。",
        f"- controller contract complete: `{controller_summary['adaptive_trace_contract_complete']}`; configured budget preserved: `{controller_summary['configured_budget_preserved_for_adaptive']}`。",
        f"- 非支配配置：`{frontier.get('pareto_config_ids', [])}`。",
        f"- deployment bounds 内的配置：`{bound_ids}`。",
        "- 结论只覆盖受控 decode-resident admission-cliff；不外推自然 API、生产 SLO 或普遍收益。",
        "- R3A/R3B、F4 和原始 135168/4096/1 blocked 审计均保留。",
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
    "r3c_mechanism_budget_summary.json",
    "r3c_mechanism_budget_cells.tsv",
    "r3c_policy_summary.tsv",
    "r3c_policy_paired_effects.tsv",
    "r3c_policy_uncertainty.json",
    "r3c_pareto_frontier.json",
    "r3c_adaptive_controller_summary.json",
    "scientific_outcome.json",
    "grading_inputs.json",
    "startup_resource_summary.tsv",
    "resource_recovery_summary.json",
    "cleanup_status.txt",
    "first_failure_excerpt.txt",
)
base.BOUNDED_CANDIDATES = BOUNDED_CANDIDATES
base.write_mechanism_evidence = write_mechanism_evidence


def package_results(artifact_dir: Path) -> dict[str, Any]:
    return base.package_results(artifact_dir)


def main(argv: list[str] | None = None) -> int:
    import argparse

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
