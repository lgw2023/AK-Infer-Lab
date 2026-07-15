from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from tools.inference_contracts.run_deepseek_p6_3b_prefix_cache_ab import (
    _read_jsonl,
    _summary,
    build_run_plan,
    prepare_artifacts,
)


R1_CONTEXTS = (32768, 65536, 131072)
R1_PREFIX_RATIO = 90
EXPECTED_PRIMES = 3
EXPECTED_MEASURED = 9
EXPECTED_REQUESTS = 12


def build_r1_plan() -> list[dict[str, Any]]:
    return [
        row
        for row in build_run_plan()
        if int(row["context_tokens"]) in R1_CONTEXTS
        and int(row["target_shared_prefix_ratio_pct"]) == R1_PREFIX_RATIO
    ]


def summarize_hybrid_diagnostics(
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    install_events = [
        row for row in diagnostics if row.get("event") == "runtime_patch_installed"
    ]
    snapshots = [
        row for row in diagnostics if row.get("event") == "coordinator_snapshot"
    ]
    source_hashes_ok = any(
        evidence
        and all(item.get("match") is True for item in evidence.values())
        for event in install_events
        if isinstance((evidence := event.get("source_evidence")), dict)
    )
    retention_unset = bool(install_events) and all(
        event.get("retention_interval") is None for event in install_events
    ) and all(
        snapshot.get("prefix_cache_retention_interval") is None
        for snapshot in snapshots
    )

    propagation_ok = False
    eagle_manager_count = 0
    lcm_block_sizes: set[int] = set()
    manager_types: set[str] = set()
    eagle_swa_present = False
    for snapshot in snapshots:
        managers = {
            int(manager["group_id"]): manager
            for manager in snapshot.get("managers", [])
            if "group_id" in manager
        }
        eagle_group_ids = {
            int(group_id) for group_id in snapshot.get("eagle_group_ids", [])
        }
        groups_ok = True
        saw_eagle_group = False
        for group in snapshot.get("attention_groups", []):
            group_ids = {int(group_id) for group_id in group.get("group_ids", [])}
            if group_ids & eagle_group_ids:
                saw_eagle_group = True
                groups_ok = groups_ok and bool(group_ids) and all(
                    managers.get(group_id, {}).get("use_eagle") is True
                    for group_id in group_ids
                )
        propagation_ok = propagation_ok or (saw_eagle_group and groups_ok)
        eagle_manager_count = max(
            eagle_manager_count,
            sum(manager.get("use_eagle") is True for manager in managers.values()),
        )
        if snapshot.get("lcm_block_size") is not None:
            lcm_block_sizes.add(int(snapshot["lcm_block_size"]))
        for manager in managers.values():
            manager_type = str(manager.get("manager_type") or "")
            manager_types.add(manager_type)
            if manager.get("use_eagle") is True and "SlidingWindow" in manager_type:
                eagle_swa_present = True

    lookahead_observed = any(
        row.get("event") == "eagle_lookahead_cache_target" for row in diagnostics
    )
    reachable_mask_observed = any(
        row.get("event") == "eagle_reachable_mask" for row in diagnostics
    )
    reachable_mask_ok = not eagle_swa_present or reachable_mask_observed
    diagnostic_ok = all(
        (
            bool(install_events),
            source_hashes_ok,
            retention_unset,
            bool(snapshots),
            propagation_ok,
            eagle_manager_count > 0,
            lookahead_observed,
            reachable_mask_ok,
        )
    )
    return {
        "event_count": len(diagnostics),
        "install_event_count": len(install_events),
        "coordinator_snapshot_count": len(snapshots),
        "source_hashes_ok": source_hashes_ok,
        "retention_interval_explicitly_unset": retention_unset,
        "manager_eagle_propagation_ok": propagation_ok,
        "eagle_manager_count_max": eagle_manager_count,
        "lookahead_cache_target_observed": lookahead_observed,
        "eagle_swa_present": eagle_swa_present,
        "reachable_mask_observed": reachable_mask_observed,
        "reachable_mask_ok": reachable_mask_ok,
        "lcm_block_sizes": sorted(lcm_block_sizes),
        "manager_types": sorted(manager_types),
        "hybrid_diagnostic_ok": diagnostic_ok,
    }


def grade_r1_evidence(
    request_rows: list[dict[str, Any]],
    *,
    diagnostics: list[dict[str, Any]],
    cleanup: str,
) -> dict[str, Any]:
    primes = [row for row in request_rows if row.get("request_role") == "prime"]
    measured = [
        row for row in request_rows if row.get("request_role") == "measured"
    ]
    prime_success = sum(row.get("status") == "success" for row in primes)
    measured_success = sum(row.get("status") == "success" for row in measured)
    positive_hits = sum(
        float(row.get("prefix_hits_delta") or 0.0) > 0 for row in measured
    )
    hit_delta_total = sum(
        float(row.get("prefix_hits_delta") or 0.0) for row in request_rows
    )
    query_delta_total = sum(
        float(row.get("prefix_queries_delta") or 0.0) for row in request_rows
    )
    accepted_delta_total = sum(
        float(row.get("accepted_token_delta") or 0.0) for row in request_rows
    )
    expected_groups = {row["group_id"] for row in build_r1_plan()}
    represented_groups = {str(row.get("group_id")) for row in request_rows}
    queue_ok = all(row.get("queue_metrics_ok") is True for row in request_rows)
    continuity_ok = all(
        row.get("counter_continuity_ok") is True for row in request_rows
    )
    spec_activity_ok = all(
        row.get("spec_activity_ok") is True for row in request_rows
    )
    diagnostic = summarize_hybrid_diagnostics(diagnostics)
    structural_complete = (
        len(request_rows) == EXPECTED_REQUESTS
        and len(primes) == EXPECTED_PRIMES
        and len(measured) == EXPECTED_MEASURED
        and represented_groups == expected_groups
    )
    evidence_complete = (
        structural_complete
        and prime_success == EXPECTED_PRIMES
        and measured_success == EXPECTED_MEASURED
        and positive_hits == EXPECTED_MEASURED
        and hit_delta_total > 0
        and query_delta_total > 0
        and accepted_delta_total > 0
        and queue_ok
        and continuity_ok
        and spec_activity_ok
        and diagnostic["hybrid_diagnostic_ok"] is True
    )

    if cleanup != "clean":
        grade = "red_cleanup_incomplete"
    elif not request_rows or prime_success + measured_success == 0:
        grade = "red_p6_3b_r1_hybrid_kv_repair_no_success"
    elif len(measured) == EXPECTED_MEASURED and positive_hits == 0:
        grade = "red_p6_3b_r1_hybrid_kv_zero_hit_persists"
    elif not structural_complete or positive_hits < EXPECTED_MEASURED:
        grade = "yellow_p6_3b_r1_hybrid_kv_repair_partial"
    elif not evidence_complete:
        grade = "red_p6_3b_r1_hybrid_kv_evidence_incomplete"
    else:
        grade = "candidate_green_p6_3b_r1_hybrid_kv_repair"

    return {
        "server_grade": grade,
        "request_row_count": len(request_rows),
        "prime_success_count": prime_success,
        "measured_success_count": measured_success,
        "positive_hit_measured_count": positive_hits,
        "prefix_queries_delta_total": query_delta_total,
        "prefix_hits_delta_total": hit_delta_total,
        "accepted_token_delta_total": accepted_delta_total,
        "represented_groups": sorted(represented_groups),
        "queue_metrics_ok": queue_ok,
        "counter_continuity_ok": continuity_ok,
        "spec_activity_ok": spec_activity_ok,
        "structural_complete": structural_complete,
        "hybrid_diagnostic_ok": diagnostic["hybrid_diagnostic_ok"],
        "cleanup": cleanup,
        "performance_effect_accepted": False,
        "developer_review_required": True,
        "prior_p6_3b_yellow_preserved": True,
        "existing_p6_references_remain_true": True,
        "claim_boundary": (
            "hybrid_kv_mtp_prefix_cache_compatibility_repair_and_positive_hit_only"
        ),
    }


def _write_group_summary(
    artifact_dir: Path,
    request_rows: list[dict[str, Any]],
) -> None:
    output_rows = []
    for group in build_r1_plan()[::4]:
        rows = [
            row
            for row in request_rows
            if row.get("group_id") == group["group_id"]
        ]
        measured = [row for row in rows if row.get("request_role") == "measured"]
        output_rows.append(
            {
                "group_id": group["group_id"],
                "context_tokens": group["context_tokens"],
                "target_shared_prefix_tokens": group["target_shared_prefix_tokens"],
                "request_count": len(rows),
                "request_success_count": sum(
                    row.get("status") == "success" for row in rows
                ),
                "measured_positive_hit_count": sum(
                    float(row.get("prefix_hits_delta") or 0.0) > 0
                    for row in measured
                ),
                "prefix_queries_delta_total": round(
                    sum(float(row.get("prefix_queries_delta") or 0.0) for row in rows),
                    6,
                ),
                "prefix_hits_delta_total": round(
                    sum(float(row.get("prefix_hits_delta") or 0.0) for row in rows),
                    6,
                ),
                "observed_hit_ratio": (
                    round(
                        sum(
                            float(row.get("prefix_hits_delta") or 0.0)
                            for row in rows
                        )
                        / sum(
                            float(row.get("prefix_queries_delta") or 0.0)
                            for row in rows
                        ),
                        6,
                    )
                    if sum(
                        float(row.get("prefix_queries_delta") or 0.0)
                        for row in rows
                    )
                    > 0
                    else None
                ),
                "ttft_ms_measured": json.dumps(
                    _summary([float(row.get("ttft_ms") or 0.0) for row in measured]),
                    separators=(",", ":"),
                ),
            }
        )
    with (artifact_dir / "group_summary.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(output_rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(output_rows)


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    mode_dir = artifact_dir / "modes" / "prefix_cache_on"
    request_rows = _read_jsonl(mode_dir / "raw_request_results.jsonl")
    diagnostic_path = mode_dir / "runtime" / "hybrid_kv_runtime_diagnostic.jsonl"
    diagnostics = _read_jsonl(diagnostic_path)
    cleanup_path = mode_dir / "cleanup_status.txt"
    cleanup = (
        cleanup_path.read_text(encoding="utf-8").strip()
        if cleanup_path.exists()
        else "incomplete"
    )
    (artifact_dir / "cleanup_status.txt").write_text(
        cleanup + "\n", encoding="utf-8"
    )
    diagnostic_summary = summarize_hybrid_diagnostics(diagnostics)
    grading = grade_r1_evidence(
        request_rows,
        diagnostics=diagnostics,
        cleanup=cleanup,
    )
    source_gate_path = mode_dir / "runtime" / "source_gate_status.txt"
    if not request_rows and (
        not source_gate_path.exists()
        or source_gate_path.read_text(encoding="utf-8").strip() != "pass"
    ):
        grading["server_grade"] = "blocked_p6_3b_r1_source_or_resource_gate"
    _write_group_summary(artifact_dir, request_rows)
    (artifact_dir / "hybrid_kv_diagnostic_summary.json").write_text(
        json.dumps(diagnostic_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "grading_inputs.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    failure = "none"
    if grading["server_grade"] != "candidate_green_p6_3b_r1_hybrid_kv_repair":
        failed = next(
            (row for row in request_rows if row.get("status") != "success"),
            None,
        )
        failure = (
            json.dumps(
                {
                    "request_id": failed.get("request_id"),
                    "status": failed.get("status"),
                    "prefix_queries_delta": failed.get("prefix_queries_delta"),
                    "prefix_hits_delta": failed.get("prefix_hits_delta"),
                },
                sort_keys=True,
            )
            if failed
            else grading["server_grade"]
        )
    (artifact_dir / "first_failure_excerpt.txt").write_text(
        failure + "\n", encoding="utf-8"
    )
    summary = "\n".join(
        [
            "# P6.3B-R1 hybrid-KV repair result",
            "",
            f"- server_grade: `{grading['server_grade']}`",
            "- claim_boundary: `hybrid_kv_mtp_prefix_cache_compatibility_repair_and_positive_hit_only`",
            f"- requests: `{grading['request_row_count']}/12` rows, "
            f"prime success `{grading['prime_success_count']}/3`, measured success "
            f"`{grading['measured_success_count']}/9`",
            f"- positive-hit measured followers: `{grading['positive_hit_measured_count']}/9`",
            f"- prefix queries/hits delta: `{grading['prefix_queries_delta_total']}` / "
            f"`{grading['prefix_hits_delta_total']}`",
            f"- MTP accepted-token delta: `{grading['accepted_token_delta_total']}`",
            f"- hybrid diagnostic: `{grading['hybrid_diagnostic_ok']}`; cleanup: `{cleanup}`",
            "- performance_effect_accepted: `false`; this is not a matched performance A/B.",
            "- prior P6.3B yellow and existing P6 green references remain unchanged.",
            "",
        ]
    )
    (artifact_dir / "result_summary.md").write_text(summary, encoding="utf-8")
    return grading


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == "prepare":
        prepare_artifacts(
            args.source_payload,
            args.artifact_dir,
            args.model_name,
            plan=build_r1_plan(),
        )
        return 0
    grading = finalize_artifacts(args.artifact_dir)
    return (
        0
        if grading["server_grade"]
        == "candidate_green_p6_3b_r1_hybrid_kv_repair"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
