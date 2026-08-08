"""Zero-NPU cross-rank reaggregation of the completed R3E-F1 traces.

R3E-F1 already paid the cost of two request-scoped profiler lifecycles.  This
task reads those retained traces in place and derives a reproducible evidence
package.  It never starts vLLM, touches keep-alive, or changes the measured
request set.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.inference_contracts import analyze_torch_profiler_traces as trace_analysis


TASK_ID = "p6_3c_r3e_f1_a1_cross_rank_trace_reaggregation_2026_0808"
SOURCE_TASK_ID = "p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01"
LIFECYCLE_IDS = ("profile_f1_01", "profile_f1_02")
EXPECTED_CONFIGS = {
    "profile_f1_01": "admission_on_t4096",
    "profile_f1_02": "persistent_on_t128",
}
SMALL_SOURCE_FILES = (
    "grading_inputs.json",
    "environment_and_hashes.json",
    "lifecycle_summary.tsv",
    "r3e_mechanism_cells.tsv",
    "r3e_f1_profile_control_summary.tsv",
    "resource_recovery_summary.json",
    "cleanup_status.txt",
)
BOUNDED_CANDIDATES = (
    "result_summary.md",
    "grading_inputs.json",
    "scientific_outcome.json",
    "source_evidence_manifest.json",
    "trace_completeness.json",
    "trace_inventory.tsv",
    "execution_domain_category_by_rank.tsv",
    "rank_execution_summary.tsv",
    "cross_rank_execution_summary.tsv",
    "top_execution_operators.tsv",
    "scheduler_normalization.tsv",
    "hypothesis_review.json",
    "adaptive_execution_review.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    trace_analysis.write_tsv(path, rows)


def _trace_roots(source: Path, trace_workspace: Path | None) -> dict[str, Path]:
    if trace_workspace is not None:
        return {
            lifecycle_id: trace_workspace / lifecycle_id
            for lifecycle_id in LIFECYCLE_IDS
        }
    return {
        lifecycle_id: source
        / "lifecycles"
        / lifecycle_id
        / "runtime"
        / "torch_profiler"
        for lifecycle_id in LIFECYCLE_IDS
    }


def _mechanism_normalizers(source: Path) -> dict[str, dict[str, int]]:
    rows = _read_tsv(source / "r3e_mechanism_cells.tsv")
    output: dict[str, dict[str, int]] = {}
    for row in rows:
        lifecycle_id = row.get("lifecycle_id", "")
        if lifecycle_id not in LIFECYCLE_IDS:
            continue
        output[lifecycle_id] = {
            "relevant_step_count": int(row.get("relevant_step_count") or 0),
            "prefill_chunk_count": int(row.get("prefill_chunk_count") or 0),
            "pressure_chunk_count": int(row.get("pressure_chunk_count") or 0),
        }
    return output


def source_evidence_manifest(
    source: Path, trace_workspace: Path | None = None
) -> dict[str, Any]:
    roots = _trace_roots(source, trace_workspace)
    files: dict[str, Any] = {}
    for name in SMALL_SOURCE_FILES:
        path = source / name
        files[name] = {
            "exists": path.is_file(),
            "bytes": path.stat().st_size if path.is_file() else None,
            "sha256": _sha256(path) if path.is_file() else None,
        }
    traces: list[dict[str, Any]] = []
    for lifecycle_id, root in roots.items():
        for path in trace_analysis.discover_trace_files(root):
            stat = path.stat()
            traces.append(
                {
                    "lifecycle_id": lifecycle_id,
                    "rank_id": trace_analysis.trace_rank(path),
                    "path": str(path),
                    "bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
    return {
        "schema": "p6_3c_r3e_f1_a1_source_evidence_manifest_v1",
        "source_task_id": SOURCE_TASK_ID,
        "source_result": str(source),
        "trace_workspace": str(trace_workspace) if trace_workspace else None,
        "small_files": files,
        "trace_files": traces,
        "source_result_overwritten": False,
    }


def validate_source(
    source: Path,
    *,
    expected_ranks: int,
    trace_workspace: Path | None = None,
) -> dict[str, Any]:
    missing = [name for name in SMALL_SOURCE_FILES if not (source / name).is_file()]
    if missing:
        raise ValueError(f"source R3E-F1 evidence missing: {missing}")
    grading = _read_json(source / "grading_inputs.json")
    lifecycle_rows = _read_tsv(source / "lifecycle_summary.tsv")
    mechanism_rows = _read_tsv(source / "r3e_mechanism_cells.tsv")
    profile_rows = _read_tsv(source / "r3e_f1_profile_control_summary.tsv")
    roots = _trace_roots(source, trace_workspace)
    trace_files = {
        lifecycle_id: trace_analysis.discover_trace_files(root)
        for lifecycle_id, root in roots.items()
    }
    ranks = {
        lifecycle_id: sorted(
            {trace_analysis.trace_rank(path) for path in paths},
            key=lambda value: int(value) if value.isdigit() else 10**9,
        )
        for lifecycle_id, paths in trace_files.items()
    }
    lifecycle_ids = {
        row.get("lifecycle_id")
        for row in lifecycle_rows
        if row.get("lifecycle_exit_code") == "0"
        and row.get("cleanup_status") == "clean"
    }
    mechanism_configs = {
        row.get("lifecycle_id"): row.get("config_id") for row in mechanism_rows
    }
    checks = {
        "source_task_id_exact": grading.get("task_id") == SOURCE_TASK_ID,
        "source_evidence_complete": grading.get("evidence_status") == "complete",
        "source_profiler_complete": grading.get("profiler_complete") is True,
        "source_lifecycles_complete": set(LIFECYCLE_IDS).issubset(lifecycle_ids),
        "source_configs_exact": all(
            mechanism_configs.get(lifecycle_id) == config_id
            for lifecycle_id, config_id in EXPECTED_CONFIGS.items()
        ),
        "profile_control_complete": all(
            str(row.get("profile_start_stop_complete")).lower() == "true"
            for row in profile_rows
        )
        and len(profile_rows) == 2,
        "trace_files_present": all(trace_files.values()),
        "rank_views_ready": all(
            len(rank_ids) == expected_ranks
            and len(trace_files[lifecycle_id]) == expected_ranks
            for lifecycle_id, rank_ids in ranks.items()
        ),
        "source_cleanup_complete": (
            _read_json(source / "resource_recovery_summary.json").get(
                "keep_alive_restored_exact"
            )
            is True
            and (source / "cleanup_status.txt").read_text(encoding="utf-8").strip()
            == "clean"
        ),
    }
    return {
        "source_validation_complete": all(checks.values()),
        "checks": checks,
        "trace_rank_ids": ranks,
        "trace_file_counts": {
            lifecycle_id: len(paths) for lifecycle_id, paths in trace_files.items()
        },
        "expected_ranks_per_lifecycle": expected_ranks,
    }


def _scheduler_rows(
    source: Path, normalizers: dict[str, dict[str, int]]
) -> list[dict[str, Any]]:
    mechanism = {
        row["lifecycle_id"]: row
        for row in _read_tsv(source / "r3e_mechanism_cells.tsv")
        if row.get("lifecycle_id") in LIFECYCLE_IDS
    }
    rows: list[dict[str, Any]] = []
    for lifecycle_id in LIFECYCLE_IDS:
        row = mechanism[lifecycle_id]
        rows.append(
            {
                "lifecycle_id": lifecycle_id,
                "config_id": row["config_id"],
                **normalizers[lifecycle_id],
                "running_prefill_pressure_step_count": int(
                    row.get("running_prefill_pressure_step_count") or 0
                ),
                "prefill_chunk_sizes": row.get("prefill_chunk_sizes"),
                "mechanism_contract_complete": row.get(
                    "mechanism_contract_complete"
                ),
                "normalization_scope": (
                    "whole_request_scoped_profile_window_not_timestamp_joined_steps"
                ),
            }
        )
    return rows


def _hypothesis_review(
    profiler: dict[str, Any], normalizers: dict[str, dict[str, int]]
) -> dict[str, Any]:
    compiler_rows = [
        row
        for row in profiler["top_operator_rows"]
        if "fx_compiler" in str(row["op_name"]).lower()
    ]
    hccl_queue_rows = [
        row
        for row in profiler["category_rows"]
        if row["evidence_domain"] == "runtime_or_queue_wait"
        and row["op_category"] == "collective_communication"
    ]
    attention_rows = [
        row
        for row in profiler["category_rows"]
        if row["op_category"] == "attention"
    ]
    return {
        "compiler_repetition": {
            "rows": compiler_rows,
            "interpretation": (
                "event counts are normalized by rank and Prefill chunk, but nested "
                "host ranges can repeat without graph recompilation; inspect trace "
                "arguments or cache diagnostics before claiming compile-per-chunk"
            ),
            "prefill_chunk_counts": {
                lifecycle_id: row["prefill_chunk_count"]
                for lifecycle_id, row in normalizers.items()
            },
        },
        "collective_queue_wait": {
            "rows": hccl_queue_rows,
            "critical_path_identifiable": False,
            "reason": (
                "queue ranges and summed durations lack dependency-flow proof; "
                "their presence does not establish exposed HCCL critical-path time"
            ),
        },
        "attention_visibility": {
            "rows": attention_rows,
            "classifier_includes_ascend_sparse_attention": True,
            "absence_means_not_observed_under_current_schema_not_negligible_cost": True,
        },
        "next_optimization_decision_ready": False,
        "decision_blocker": (
            "requires cross-rank complete evidence plus timestamp/dependency linkage "
            "before choosing compiler, collective, MoE, or attention optimization"
        ),
    }


def _candidate_manifest(output: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for name in BOUNDED_CANDIDATES:
        path = output / name
        if not path.is_file():
            continue
        files.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "sensitivity": "internal_project_evidence_no_generated_content",
            }
        )
    total = sum(row["bytes"] for row in files)
    if total > 70 * 1024:
        raise ValueError(f"bounded candidate package exceeds 70KB: {total}")
    return {
        "schema": "p6_3c_r3e_f1_a1_candidate_manifest_v1",
        "task_id": TASK_ID,
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "available_methods": ["email", "upload-api", "server-local"],
        "recommended_method": "upload-api",
        "recommended_reason": "one_named_multi_file_session_with_sha_validation",
        "candidate_file_count": len(files),
        "candidate_total_bytes": total,
        "files": files,
    }


def reaggregate(
    source: Path,
    output: Path,
    *,
    expected_ranks: int,
    top_n_ops: int,
    max_events_per_trace: int | None,
    trace_workspace: Path | None,
) -> dict[str, Any]:
    if source.resolve() == output.resolve():
        raise ValueError("derived output must not overwrite the source result")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"derived output must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    validation = validate_source(
        source, expected_ranks=expected_ranks, trace_workspace=trace_workspace
    )
    source_before = source_evidence_manifest(source, trace_workspace)
    normalizers = _mechanism_normalizers(source)
    profiler = trace_analysis.analyze_trace_roots(
        _trace_roots(source, trace_workspace),
        top_n_ops=top_n_ops,
        expected_ranks_per_lifecycle=expected_ranks,
        max_events_per_trace=max_events_per_trace,
        normalizers=normalizers,
    )
    source_after = source_evidence_manifest(source, trace_workspace)
    source_unchanged = source_before == source_after

    _write_tsv(output / "trace_inventory.tsv", profiler["trace_inventory"])
    _write_tsv(
        output / "execution_domain_category_by_rank.tsv", profiler["category_rows"]
    )
    _write_tsv(output / "rank_execution_summary.tsv", profiler["rank_rows"])
    _write_tsv(
        output / "cross_rank_execution_summary.tsv", profiler["cross_rank_rows"]
    )
    _write_tsv(
        output / "top_execution_operators.tsv", profiler["top_operator_rows"]
    )
    _write_tsv(
        output / "scheduler_normalization.tsv",
        _scheduler_rows(source, normalizers),
    )
    completeness = {
        key: value
        for key, value in profiler.items()
        if key
        not in {
            "trace_inventory",
            "category_rows",
            "rank_rows",
            "cross_rank_rows",
            "top_operator_rows",
        }
    }
    _write_json(output / "trace_completeness.json", completeness)
    _write_json(output / "hypothesis_review.json", _hypothesis_review(profiler, normalizers))
    _write_json(output / "source_evidence_manifest.json", source_after)

    complete = (
        validation["source_validation_complete"]
        and profiler["profiler_complete"]
        and source_unchanged
        and max_events_per_trace is None
    )
    scientific_outcome = (
        "descriptive_cross_rank_execution_path_complete_causal_bottleneck_unresolved"
        if complete
        else "cross_rank_trace_reaggregation_incomplete"
    )
    outcome = {
        "task_id": TASK_ID,
        "source_task_id": SOURCE_TASK_ID,
        "scientific_outcome": scientific_outcome,
        "source_scientific_outcome_preserved": (
            "executor_path_supported_with_request_scoped_device_categories"
        ),
        "parent_r3d_outcome_preserved": (
            "persistent_prefill_tradeoff_no_candidate_within_bounds"
        ),
        "cross_rank_trace_complete": profiler["profiler_complete"],
        "source_evidence_unchanged": source_unchanged,
        "claim_boundary": (
            "request_scoped_descriptive_execution_path_not_causal_bottleneck_or_performance"
        ),
        "optimization_target_selected": False,
    }
    _write_json(output / "scientific_outcome.json", outcome)
    grading = {
        "task_id": TASK_ID,
        "source_task_id": SOURCE_TASK_ID,
        "server_grade": (
            "complete_p6_3c_r3e_f1_a1_cross_rank_trace_evidence"
            if complete
            else "incomplete_p6_3c_r3e_f1_a1_cross_rank_trace_evidence"
        ),
        "evidence_status": "complete" if complete else "incomplete",
        "scientific_outcome": scientific_outcome,
        "source_validation": validation,
        "source_evidence_unchanged": source_unchanged,
        "all_trace_arrays_parsed_to_end": all(
            row["parse_complete"] is True for row in profiler["trace_inventory"]
        ),
        "event_limit_used": max_events_per_trace is not None,
        "expected_ranks_per_lifecycle": expected_ranks,
        "profiler_complete": profiler["profiler_complete"],
        "npu_used": False,
        "keep_alive_action": "left_running",
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "next_task_authorized": False,
        "universal_bottleneck_claimed": False,
    }
    _write_json(output / "grading_inputs.json", grading)
    adaptive = {
        "task_id": TASK_ID,
        "operation": "zero_npu_read_only_cross_rank_trace_reaggregation",
        "published_analyzer_used": True,
        "adaptive_attempt_count": 0,
        "adaptive_patch_paths": [],
        "scientific_contract_changed": False,
        "source_result_overwritten": False,
        "source_evidence_unchanged": source_unchanged,
    }
    _write_json(output / "adaptive_execution_review.json", adaptive)
    lifecycle_bits = "; ".join(
        f"{row['lifecycle_id']}={row['rank_count']}/{expected_ranks} ranks, "
        f"events={row['event_count']}, parse_complete={row['parse_complete']}"
        for row in profiler["lifecycle_summaries"]
    )
    (output / "result_summary.md").write_text(
        "\n".join(
            [
                f"# {TASK_ID} 结果摘要",
                "",
                f"- evidence status: `{grading['evidence_status']}`",
                f"- scientific outcome: `{scientific_outcome}`",
                f"- trace coverage: {lifecycle_bits}",
                f"- source evidence unchanged: `{source_unchanged}`；NPU used: `false`；keep-alive: `left_running`。",
                "- 事件按 device kernel、runtime/queue wait、host framework range、name-inferred device candidate 与 unclassified timed range 分域；名称推断不再等同于设备 kernel。",
                "- Ascend sparse-attention / lightning-indexer 名称已进入 attention 语义类别，避免把未分类误写成 attention 不重要。",
                "- duration sum 与 timestamp interval union 都是描述性活动量，不是 dependency-aware critical path；本任务不据此选择 collective、compiler、MoE 或 attention 优化方向。",
                "- R3E-F1 的 request-scoped 执行路径证据与 R3D 阴性性能结论均保留；本轮没有性能重跑或新收益声明。",
                "",
            ]
        ),
        encoding="utf-8",
    )

    manifest = _candidate_manifest(output)
    _write_json(output / "candidate_manifest.server_local.json", manifest)
    return grading


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-only")
    validate.add_argument("--source-artifact-dir", type=Path, required=True)
    validate.add_argument("--trace-workspace", type=Path)
    validate.add_argument("--expected-ranks", type=int, default=8)
    derive = sub.add_parser("reaggregate")
    derive.add_argument("--source-artifact-dir", type=Path, required=True)
    derive.add_argument("--output-dir", type=Path, required=True)
    derive.add_argument("--trace-workspace", type=Path)
    derive.add_argument("--expected-ranks", type=int, default=8)
    derive.add_argument("--top-n-ops", type=int, default=30)
    derive.add_argument("--max-events-per-trace", type=int)
    args = parser.parse_args(argv)

    if args.command == "validate-only":
        result = validate_source(
            args.source_artifact_dir,
            expected_ranks=args.expected_ranks,
            trace_workspace=args.trace_workspace,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["source_validation_complete"] else 2
    grading = reaggregate(
        args.source_artifact_dir,
        args.output_dir,
        expected_ranks=args.expected_ranks,
        top_n_ops=args.top_n_ops,
        max_events_per_trace=args.max_events_per_trace,
        trace_workspace=args.trace_workspace,
    )
    print(json.dumps(grading, indent=2, sort_keys=True))
    return 0 if grading["evidence_status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
