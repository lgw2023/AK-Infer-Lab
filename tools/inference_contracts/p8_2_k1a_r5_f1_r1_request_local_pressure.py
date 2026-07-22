from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.p8_2_k1a_failure_forensics import inventory_tree


BLOCK_SIZE_TOKENS = 128
OUTPUT_TOKENS = 64
REQUIRED_COMPLETION_MARGIN_TOKENS = 4096
TARGET_BLOCK_COUNT = 64
SENSITIVITY = "bounded_operational_metadata_no_content_or_token_ids"
READY_GRADE = "candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure"
CALIBRATION_REQUIRED_GRADE = (
    "candidate_requires_p8_2_k1a_r5_f1_r1_instrumented_calibration"
)
BLOCKED_GRADE = "blocked_p8_2_k1a_r5_f1_r1_request_local_pressure_gate"


def derive_request_local_pressure_candidate(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    progress = sorted(
        (
            row
            for row in rows
            if row.get("event") == "request_local_pressure_progress"
            and row.get("contract_role") == "pressure_01"
        ),
        key=lambda row: int(row.get("timestamp_ns") or 0),
    )
    exact_progress = [
        row
        for row in progress
        if row.get("request_local_progress_exact") is True
        and int(row.get("scheduled_request_count") or 0) == 1
        and int(row.get("target_block_count") or 0) == TARGET_BLOCK_COUNT
    ]
    sequence_exact = bool(progress) and len(exact_progress) == len(progress)
    previous_after: int | None = None
    for index, row in enumerate(exact_progress):
        before = int(row.get("num_computed_tokens_before_schedule") or 0)
        scheduled = int(row.get("num_scheduled_tokens") or 0)
        after = int(row.get("num_computed_tokens_after_schedule") or 0)
        if scheduled <= 0 or after != before + scheduled:
            sequence_exact = False
        if index == 0 and before != 0:
            sequence_exact = False
        if previous_after is not None and before != previous_after:
            sequence_exact = False
        previous_after = after

    cpu_evictions = [
        row
        for row in rows
        if row.get("event") == "target_cache_evicted"
        and row.get("tier") == "cpu"
        and int(row.get("target_evicted_count") or 0) > 0
    ]
    first_eviction_ns = min(
        (int(row.get("timestamp_ns") or 0) for row in cpu_evictions),
        default=None,
    )
    exact_cpu_only = [
        row
        for row in exact_progress
        if int(row.get("cpu_target_block_count") or 0) == TARGET_BLOCK_COUNT
        and int(row.get("gpu_target_block_count") or 0) == 0
        and (
            first_eviction_ns is None
            or int(row.get("timestamp_ns") or 0) < first_eviction_ns
        )
    ]
    first_exact = exact_cpu_only[0] if exact_cpu_only else None
    first_total = (
        int(first_exact.get("num_computed_tokens_after_schedule") or 0)
        if first_exact
        else None
    )
    last_total = (
        max(
            int(row.get("num_computed_tokens_after_schedule") or 0)
            for row in exact_cpu_only
        )
        if exact_cpu_only
        else None
    )
    margin = (
        last_total - first_total
        if first_total is not None and last_total is not None
        else None
    )
    candidate_context = (
        first_total - OUTPUT_TOKENS if first_total is not None else None
    )
    candidate_allowed = all(
        (
            sequence_exact,
            first_total is not None,
            first_total is not None and first_total > OUTPUT_TOKENS,
            first_total is not None and first_total % BLOCK_SIZE_TOKENS == 0,
            margin is not None
            and margin >= REQUIRED_COMPLETION_MARGIN_TOKENS,
        )
    )
    if not progress:
        next_required_action = (
            "one_observe_only_request_local_progress_calibration_lifecycle"
        )
    elif candidate_allowed:
        next_required_action = "one_fixed_non_search_l2_lifecycle"
    else:
        next_required_action = "stop_request_local_candidate_gate_blocked"
    return {
        "schema_version": "p8_2_k1a_r5_f1_r1_request_local_attribution_v1",
        "progress_event_count": len(progress),
        "exact_progress_event_count": len(exact_progress),
        "exact_cpu_only_progress_event_count": len(exact_cpu_only),
        "request_local_progress_source_exact": sequence_exact,
        "first_cpu_target_eviction_timestamp_ns": first_eviction_ns,
        "target_cpu_cache_eviction_observed": bool(cpu_evictions),
        "first_exact_window_timestamp_ns": (
            int(first_exact.get("timestamp_ns") or 0) if first_exact else None
        ),
        "candidate_pressure_total_tokens": first_total,
        "candidate_pressure_context_tokens": (
            candidate_context if candidate_allowed else None
        ),
        "candidate_output_tokens": OUTPUT_TOKENS,
        "observed_exact_window_margin_tokens": margin,
        "required_completion_margin_tokens": (
            REQUIRED_COMPLETION_MARGIN_TOKENS
        ),
        "candidate_total_tokens_block_aligned": (
            first_total is not None and first_total % BLOCK_SIZE_TOKENS == 0
        ),
        "net_gpu_free_delta_used": False,
        "legacy_gpu_free_pool_delta_is_not_request_local": True,
        "formal_fixed_l2_candidate_allowed": candidate_allowed,
        "next_required_action": next_required_action,
        "pressure_caused_target_eviction_proven": False,
        "cause_proven_as_unique": False,
        "request_id_retained": False,
        "token_ids_retained": False,
        "generated_content_retained": False,
    }


def _read_trace_dir(trace_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(trace_dir.glob("h2d-residency.*.jsonl")):
        rows.extend(
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return rows


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(output: Path, payloads: list[str]) -> None:
    files = {
        relative: {
            "bytes": (output / relative).stat().st_size,
            "sha256": _sha256(output / relative),
            "sensitivity": SENSITIVITY,
        }
        for relative in payloads
    }
    _write_json(
        output / "candidate_manifest.server_local.json",
        {
            "schema_version": "p8_2_k1a_r5_f1_r1_candidate_manifest_v1",
            "files": files,
            "payload_file_count": len(files),
            "payload_total_bytes": sum(row["bytes"] for row in files.values()),
            "max_total_bytes": 71680,
            "generated_content_retained": False,
            "token_ids_retained": False,
            "request_ids_retained": False,
            "raw_hash_values_retained": False,
            "result_transfer_authorized": True,
            "transfer_method_selected": False,
            "automatic_transfer_allowed": False,
        },
    )


def analyze_trace(args: argparse.Namespace) -> int:
    output = args.output_dir.resolve()
    source = args.source_result_root.resolve()
    if output.exists():
        raise FileExistsError(f"output directory exists: {output}")
    if output == source or source in output.parents:
        raise ValueError("output must be outside immutable source result root")
    before = inventory_tree(source)
    rows = _read_trace_dir(args.trace_dir)
    if not rows:
        raise ValueError("request-local pressure trace is missing")
    attribution = derive_request_local_pressure_candidate(rows)
    after = inventory_tree(source)
    if before != after:
        raise ValueError("source evidence changed during request-local analysis")

    allowed = attribution["formal_fixed_l2_candidate_allowed"] is True
    if allowed:
        grade = READY_GRADE
    elif args.analysis_mode == "parent_legacy" and not attribution[
        "progress_event_count"
    ]:
        grade = CALIBRATION_REQUIRED_GRADE
    else:
        grade = BLOCKED_GRADE
    candidate = {
        "schema_version": "p8_2_k1a_r5_f1_r1_pressure_candidate_v1",
        "candidate_pressure_context_tokens": attribution[
            "candidate_pressure_context_tokens"
        ],
        "candidate_pressure_total_tokens": attribution[
            "candidate_pressure_total_tokens"
        ],
        "candidate_output_tokens": OUTPUT_TOKENS,
        "observed_exact_window_margin_tokens": attribution[
            "observed_exact_window_margin_tokens"
        ],
        "required_completion_margin_tokens": REQUIRED_COMPLETION_MARGIN_TOKENS,
        "candidate_is_fixed_not_search": allowed,
        "candidate_uses_request_local_progress": allowed,
        "candidate_uses_gpu_free_pool_delta": False,
        "formal_fixed_l2_candidate_allowed": allowed,
    }
    provenance = {
        "schema_version": "p8_2_k1a_r5_f1_r1_source_provenance_v1",
        "before": before,
        "after": after,
        "source_evidence_unchanged": True,
    }
    grading = {
        "schema_version": "p8_2_k1a_r5_f1_r1_grading_v1",
        "server_grade": grade,
        "analysis_mode": args.analysis_mode,
        "source_evidence_unchanged": True,
        "request_local_progress_source_exact": attribution[
            "request_local_progress_source_exact"
        ],
        "formal_fixed_l2_candidate_allowed": allowed,
        "target_cpu_cache_eviction_observed": attribution[
            "target_cpu_cache_eviction_observed"
        ],
        "pressure_caused_target_eviction_proven": False,
        "cause_proven_as_unique": False,
        "npu_started_by_analysis": False,
        "vllm_started_by_analysis": False,
        "model_request_sent_by_analysis": False,
        "performance_reference_accepted": False,
        "k2_authorized": False,
        "p8_3_i1_authorized": False,
        "next_task_authorized": False,
        "claim_boundary": (
            "request_local_pressure_progress_provenance_and_fixed_candidate_"
            "derivation_only_no_h2d_or_performance_claim"
        ),
    }
    output.mkdir(parents=True)
    values = {
        "request_local_pressure_attribution.json": attribution,
        "pressure_candidate.json": candidate,
        "source_evidence_provenance.json": provenance,
        "grading_summary.json": grading,
    }
    for relative, value in values.items():
        _write_json(output / relative, value)
    (output / "task_grade.txt").write_text(grade + "\n", encoding="utf-8")
    (output / "result_summary.md").write_text(
        "\n".join(
            (
                "# P8.2-K1A-R5-F1-R1 request-local pressure provenance",
                "",
                f"- grade: `{grade}`",
                f"- analysis mode: `{args.analysis_mode}`",
                (
                    "- one fixed candidate is derived from direct request-local "
                    "scheduler progress with a full-chunk safety margin."
                    if allowed
                    else "- no fixed L2 candidate is authorized by this analysis."
                ),
                "- no H2D, performance, K2, P8.3-I1 or unique-cause claim.",
                "",
            )
        ),
        encoding="utf-8",
    )
    payloads = [*values, "task_grade.txt", "result_summary.md"]
    _write_manifest(output, payloads)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    derive = subparsers.add_parser("derive")
    derive_source = derive.add_mutually_exclusive_group(required=True)
    derive_source.add_argument("--rows", type=Path)
    derive_source.add_argument("--trace-dir", type=Path)
    derive.add_argument("--output", type=Path, required=True)
    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--source-result-root", type=Path, required=True)
    analyze.add_argument("--trace-dir", type=Path, required=True)
    analyze.add_argument(
        "--analysis-mode",
        choices=("parent_legacy", "calibration"),
        required=True,
    )
    analyze.add_argument("--output-dir", type=Path, required=True)
    return parser


def _load_derive_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.trace_dir is not None:
        return _read_trace_dir(args.trace_dir)
    rows = json.loads(args.rows.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not all(
        isinstance(row, dict) for row in rows
    ):
        raise ValueError("rows must be a JSON list of objects")
    return rows


def main() -> int:
    args = _parser().parse_args()
    if args.command == "analyze":
        return analyze_trace(args)
    if args.command == "derive":
        value = derive_request_local_pressure_candidate(_load_derive_rows(args))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
