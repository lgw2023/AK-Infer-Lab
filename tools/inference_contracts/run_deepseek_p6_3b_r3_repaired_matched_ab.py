from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from tools.inference_contracts.run_deepseek_p6_3b_prefix_cache_ab import (
    MODES,
    _read_jsonl,
    _write_comparison_tables,
    build_run_plan,
    execute_mode,
    grade_evidence,
    prepare_artifacts,
)
from tools.inference_contracts.run_deepseek_p6_3b_r1_hybrid_kv_repair import (
    summarize_hybrid_diagnostics,
)
from tools.inference_contracts.p6_3b_r1_hybrid_kv_runtime_patch import (
    EXPECTED_SOURCE_SHA256,
)


def _map_base_grade(grade: str) -> str:
    return {
        "red_cleanup_incomplete": "red_cleanup_incomplete",
        "red_p6_3b_prefix_cache_matched_ab_no_success": (
            "red_p6_3b_r3_repaired_prefix_cache_matched_ab_no_success"
        ),
        "yellow_p6_3b_prefix_cache_matched_ab_partial": (
            "yellow_p6_3b_r3_repaired_prefix_cache_matched_ab_partial"
        ),
        "red_p6_3b_prefix_cache_evidence_incomplete": (
            "red_p6_3b_r3_repaired_prefix_cache_evidence_incomplete"
        ),
        "candidate_green_p6_3b_prefix_cache_matched_ab": (
            "candidate_green_p6_3b_r3_repaired_prefix_cache_matched_ab"
        ),
    }[grade]


def grade_r3_evidence(
    request_rows: list[dict[str, Any]],
    *,
    cleanup_by_mode: dict[str, str],
    diagnostic_ok_by_mode: dict[str, bool],
    repair_identity_by_mode: dict[str, dict[str, str]],
) -> dict[str, Any]:
    grading = grade_evidence(request_rows, cleanup_by_mode=cleanup_by_mode)
    same_repair = (
        set(repair_identity_by_mode) == set(MODES)
        and all(repair_identity_by_mode[mode] for mode in MODES)
        and repair_identity_by_mode["prefix_cache_off"]
        == repair_identity_by_mode["prefix_cache_on"]
    )
    diagnostics_ok = (
        set(diagnostic_ok_by_mode) == set(MODES)
        and all(diagnostic_ok_by_mode.values())
    )
    grade = _map_base_grade(grading["server_grade"])
    if grade.startswith("candidate_green") and not (same_repair and diagnostics_ok):
        grade = "red_p6_3b_r3_repaired_prefix_cache_evidence_incomplete"
    grading.update(
        {
            "server_grade": grade,
            "same_r2_repair_in_both_modes": same_repair,
            "required_diagnostic_ok_by_mode": diagnostic_ok_by_mode,
            "repair_identity_by_mode": repair_identity_by_mode,
            "mechanism_effect_accepted": False,
            "developer_review_required": True,
            "claim_boundary": (
                "repaired_hybrid_kv_prefix_cache_matched_ab_"
                "mechanism_effect_only"
            ),
        }
    )
    return grading


def _read_repair_identity(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            result[parts[0]] = parts[1]
    return result


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(Path(__file__).resolve().parents[2]), *args],
            text=True,
        ).strip()
    except Exception:
        return ""


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    request_rows = [
        row
        for mode in MODES
        for row in _read_jsonl(
            artifact_dir / "modes" / mode / "raw_request_results.jsonl"
        )
    ]
    cleanup_by_mode = {
        mode: (
            (artifact_dir / "modes" / mode / "cleanup_status.txt")
            .read_text(encoding="utf-8")
            .strip()
            if (artifact_dir / "modes" / mode / "cleanup_status.txt").exists()
            else "incomplete"
        )
        for mode in MODES
    }
    cleanup = (
        "clean"
        if all(cleanup_by_mode[mode] == "clean" for mode in MODES)
        else "incomplete"
    )
    (artifact_dir / "cleanup_status.txt").write_text(
        cleanup + "\n", encoding="utf-8"
    )

    diagnostics_by_mode = {
        mode: _read_jsonl(
            artifact_dir
            / "modes"
            / mode
            / "runtime"
            / "hybrid_kv_runtime_diagnostic.jsonl"
        )
        for mode in MODES
    }
    diagnostic_summary_by_mode = {
        mode: summarize_hybrid_diagnostics(
            diagnostics_by_mode[mode], require_deferred_install=True
        )
        for mode in MODES
    }
    diagnostic_ok_by_mode = {
        "prefix_cache_off": all(
            (
                diagnostic_summary_by_mode["prefix_cache_off"][
                    "install_event_count"
                ]
                > 0,
                diagnostic_summary_by_mode["prefix_cache_off"][
                    "deferred_import_order_verified"
                ],
                diagnostic_summary_by_mode["prefix_cache_off"]["source_hashes_ok"],
                diagnostic_summary_by_mode["prefix_cache_off"][
                    "retention_interval_explicitly_unset"
                ],
            )
        ),
        "prefix_cache_on": diagnostic_summary_by_mode["prefix_cache_on"][
            "hybrid_diagnostic_ok"
        ],
    }
    repair_identity_by_mode = {
        mode: _read_repair_identity(
            artifact_dir / "modes" / mode / "repair_identity.tsv"
        )
        for mode in MODES
    }
    source_gate_ok_by_mode = {
        mode: (
            artifact_dir
            / "modes"
            / mode
            / "runtime"
            / "source_gate_status.txt"
        ).exists()
        and (
            artifact_dir
            / "modes"
            / mode
            / "runtime"
            / "source_gate_status.txt"
        ).read_text(encoding="utf-8").strip()
        == "pass"
        for mode in MODES
    }
    diagnostic_ok_by_mode = {
        mode: diagnostic_ok_by_mode[mode] and source_gate_ok_by_mode[mode]
        for mode in MODES
    }
    grading = grade_r3_evidence(
        request_rows,
        cleanup_by_mode=cleanup_by_mode,
        diagnostic_ok_by_mode=diagnostic_ok_by_mode,
        repair_identity_by_mode=repair_identity_by_mode,
    )
    if not request_rows and not all(source_gate_ok_by_mode.values()):
        grading["server_grade"] = "blocked_p6_3b_r3_source_or_resource_gate"
    grading["source_gate_ok_by_mode"] = source_gate_ok_by_mode

    _write_comparison_tables(artifact_dir, request_rows)
    (artifact_dir / "hybrid_kv_diagnostic_summary.json").write_text(
        json.dumps(
            {
                "by_mode": diagnostic_summary_by_mode,
                "required_diagnostic_ok_by_mode": diagnostic_ok_by_mode,
                "all_required_diagnostics_green": all(
                    diagnostic_ok_by_mode.values()
                ),
                "prefix_cache_on_full_hybrid_diagnostic_ok": (
                    diagnostic_summary_by_mode["prefix_cache_on"][
                        "hybrid_diagnostic_ok"
                    ]
                ),
                "same_r2_repair_in_both_modes": grading[
                    "same_r2_repair_in_both_modes"
                ],
                "repair_identity_by_mode": repair_identity_by_mode,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    environment = {
        "git_head": _git_value("rev-parse", "HEAD"),
        "origin_main": _git_value("rev-parse", "origin/main"),
        "tracked_status": _git_value(
            "status", "--porcelain", "--untracked-files=no"
        ),
        "source_payload_sha256": (
            (artifact_dir / "source_payload_sha256.txt")
            .read_text(encoding="utf-8")
            .split()[0]
            if (artifact_dir / "source_payload_sha256.txt").exists()
            else None
        ),
        "server_command_sha256_by_mode": {
            mode: (
                (artifact_dir / "modes" / mode / "server_command_sha256.txt")
                .read_text(encoding="utf-8")
                .split()[0]
                if (
                    artifact_dir / "modes" / mode / "server_command_sha256.txt"
                ).exists()
                else None
            )
            for mode in MODES
        },
        "server_lifecycle_count": 2,
        "profiler_run": False,
        "hbm_sampler_run": False,
        "mode_order": list(MODES),
        "fixed_mode_order_is_a_reported_limitation": True,
        "same_r2_repair_in_both_modes": grading[
            "same_r2_repair_in_both_modes"
        ],
    }
    (artifact_dir / "environment_and_hashes.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    candidate_green = (
        "candidate_green_p6_3b_r3_repaired_prefix_cache_matched_ab"
    )
    failure = "none"
    if grading["server_grade"] != candidate_green:
        first_failed = next(
            (row for row in request_rows if row.get("status") != "success"),
            None,
        )
        if first_failed is not None:
            failure = json.dumps(
                {
                    key: value
                    for key, value in first_failed.items()
                    if key not in {"token_arrival_ns"}
                },
                indent=2,
                sort_keys=True,
            )[:8192]
        else:
            for mode in MODES:
                mode_failure = (
                    artifact_dir / "modes" / mode / "first_failure_excerpt.txt"
                )
                if mode_failure.exists():
                    failure = mode_failure.read_text(encoding="utf-8")[:8192].rstrip()
                    break
            else:
                failure = grading["server_grade"]
    (artifact_dir / "first_failure_excerpt.txt").write_text(
        failure + "\n", encoding="utf-8"
    )

    lines = [
        "# P6.3B-R3 repaired Prefix Cache matched A/B server result",
        "",
        "- task_id: p6_3b_r3_deepseek_v4_flash_w8a8_mtp_repaired_prefix_cache_matched_ab_2026_0715",
        f"- server_grade: {grading['server_grade']}",
        f"- requests: {grading['successful_request_count']}/64 successful",
        f"- prime_requests: {grading['prime_request_count']}/16",
        f"- measured_requests: {grading['measured_request_count']}/48",
        f"- all_eight_groups_matched: {str(grading['all_eight_groups_matched']).lower()}",
        f"- body_pairing_ok: {str(grading['body_pairing_ok']).lower()}",
        "- prefix_cache_on_positive_hit_measured_count: "
        f"{grading['prefix_cache_on_positive_hit_measured_count']}/24",
        f"- prefix_cache_on_hit_delta_total: {grading['prefix_cache_on_hit_delta_total']}",
        f"- prefix_cache_off_hit_delta_total: {grading['prefix_cache_off_hit_delta_total']}",
        "- same_r2_repair_in_both_modes: "
        f"{str(grading['same_r2_repair_in_both_modes']).lower()}",
        f"- required_diagnostic_ok_by_mode: {json.dumps(diagnostic_ok_by_mode, sort_keys=True)}",
        "- mechanism_effect_accepted: false (developer review required)",
        "- green_means_evidence_complete_not_prefix_cache_faster: true",
        "- fixed_mode_order_limitation: prefix_cache_off_then_prefix_cache_on",
        "- claim_boundary: repaired_hybrid_kv_prefix_cache_matched_ab_mechanism_effect_only",
        f"- raw_result_root_server_local: {artifact_dir}",
        "- generated content and returned token ID payloads are not retained or packaged",
    ]
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    candidate_names = (
        "result_summary.md",
        "environment_and_hashes.json",
        "request_body_manifest.json",
        "mode_group_summary.tsv",
        "paired_request_summary.tsv",
        "grading_inputs.json",
        "hybrid_kv_diagnostic_summary.json",
        "cleanup_status.txt",
        "first_failure_excerpt.txt",
    )
    candidate_rows = []
    total = 0
    for name in candidate_names:
        path = artifact_dir / name
        if not path.exists() or name == "grading_inputs.json":
            continue
        size = path.stat().st_size
        total += size
        candidate_rows.append(
            (
                str(path),
                size,
                hashlib.sha256(path.read_bytes()).hexdigest(),
                "bounded_structured_repaired_prefix_cache_ab_evidence_no_content_payload",
            )
        )
    grading_path = artifact_dir / "grading_inputs.json"
    grading["candidate_total_bytes"] = total
    grading["candidate_size_gate_pass"] = total <= 71680
    for _ in range(10):
        grading_path.write_text(
            json.dumps(grading, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        candidate_total = total + grading_path.stat().st_size
        candidate_gate = candidate_total <= 71680
        if (
            grading["candidate_total_bytes"] == candidate_total
            and grading["candidate_size_gate_pass"] == candidate_gate
        ):
            break
        grading["candidate_total_bytes"] = candidate_total
        grading["candidate_size_gate_pass"] = candidate_gate
    else:
        raise RuntimeError("grading candidate size did not converge")
    total = grading["candidate_total_bytes"]
    candidate_rows.append(
        (
            str(grading_path),
            grading_path.stat().st_size,
            hashlib.sha256(grading_path.read_bytes()).hexdigest(),
            "bounded_structured_repaired_prefix_cache_ab_evidence_no_content_payload",
        )
    )
    with (artifact_dir / "delivery_candidates.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["path", "bytes", "sha256", "sensitivity"])
        writer.writerows(candidate_rows)
    (artifact_dir / "delivery_candidates_total_bytes.txt").write_text(
        f"{total}\n", encoding="utf-8"
    )
    (artifact_dir / "server_grade.txt").write_text(
        grading["server_grade"] + "\n", encoding="utf-8"
    )
    return grading


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the DeepSeek P6.3B-R3 repaired Prefix Cache matched A/B."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    run_mode = subparsers.add_parser("run-mode")
    run_mode.add_argument("--artifact-dir", type=Path, required=True)
    run_mode.add_argument("--base-url", required=True)
    run_mode.add_argument("--server-pid", type=int, required=True)
    run_mode.add_argument("--mode", choices=MODES, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        prepare_artifacts(args.source_payload, args.artifact_dir, args.model_name)
        return 0
    if args.command == "run-mode":
        return execute_mode(
            args.artifact_dir, args.base_url, args.server_pid, args.mode
        )
    grading = finalize_artifacts(args.artifact_dir)
    return (
        0
        if grading["server_grade"]
        == "candidate_green_p6_3b_r3_repaired_prefix_cache_matched_ab"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
