from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.run_deepseek_p6_3b_prefix_cache_ab import (
    MODES,
    _common_prefix_length,
    _read_jsonl,
    _write_comparison_tables,
    build_run_plan,
    execute_mode,
    prepare_artifacts,
)
from tools.inference_contracts.run_deepseek_p6_3b_r1_hybrid_kv_repair import (
    summarize_hybrid_diagnostics,
)
from tools.inference_contracts.run_deepseek_p6_3b_r3_repaired_matched_ab import (
    _git_value,
    _read_repair_identity,
)
from tools.inference_contracts.p6_3b_r1_hybrid_kv_runtime_patch import (
    EXPECTED_SOURCE_SHA256,
)


HYBRID_LCM_TOKENS = 16384
POSITIVE_HIT_GROUPS = {
    "ctx32768_prefix90",
    "ctx65536_prefix90",
    "ctx131072_prefix90",
}


def prepare_r4_artifacts(
    source_payload: Path,
    artifact_dir: Path,
    model_name: str,
) -> dict[str, Any]:
    manifest = prepare_artifacts(source_payload, artifact_dir, model_name)
    records = manifest["records"]
    records_by_group: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        records_by_group.setdefault(str(record["group_id"]), []).append(record)

    for group_records in records_by_group.values():
        prime_record = next(
            record for record in group_records if record["request_role"] == "prime"
        )
        prime_body = json.loads(
            (artifact_dir / prime_record["body_relative_path"]).read_text(
                encoding="utf-8"
            )
        )
        prime_prompt = prime_body["prompt"]
        for record in group_records:
            body = json.loads(
                (artifact_dir / record["body_relative_path"]).read_text(
                    encoding="utf-8"
                )
            )
            prompt = body["prompt"]
            actual_lcp = (
                0
                if record["request_role"] == "prime"
                else _common_prefix_length(prime_prompt, prompt)
            )
            canonical_lcp = json.dumps(
                prompt[:actual_lcp], separators=(",", ":")
            ).encode("utf-8")
            record.update(
                {
                    "planned_shared_tokens": record[
                        "target_shared_prefix_tokens"
                    ],
                    "actual_token_lcp": actual_lcp,
                    "actual_lcp_sha256": hashlib.sha256(
                        canonical_lcp
                    ).hexdigest(),
                    "actual_lcp_mod_128": actual_lcp % 128,
                    "actual_lcp_mod_16384": actual_lcp % HYBRID_LCM_TOKENS,
                    "expected_prefix_hit_tokens": (
                        actual_lcp
                        // HYBRID_LCM_TOKENS
                        * HYBRID_LCM_TOKENS
                    ),
                }
            )

    measured = [
        record for record in records if record["request_role"] == "measured"
    ]
    token_lcp_evidence_ok = len(measured) == 24 and all(
        record["planned_shared_tokens"]
        <= record["actual_token_lcp"]
        < record["planned_shared_tokens"] + 128
        for record in measured
    )
    manifest.update(
        {
            "hybrid_lcm_tokens": HYBRID_LCM_TOKENS,
            "actual_lcp_hash_encoding": "compact_json_integer_array_utf8",
            "token_lcp_evidence_ok": token_lcp_evidence_ok,
            "records": records,
        }
    )
    run_plan = json.loads(
        (artifact_dir / "run_plan.json").read_text(encoding="utf-8")
    )
    records_by_request = {
        record["request_id"]: record for record in records
    }
    for item in run_plan:
        record = records_by_request[item["request_id"]]
        for key in (
            "planned_shared_tokens",
            "actual_token_lcp",
            "actual_lcp_sha256",
            "actual_lcp_mod_128",
            "actual_lcp_mod_16384",
            "expected_prefix_hit_tokens",
        ):
            item[key] = record[key]
    (artifact_dir / "run_plan.json").write_text(
        json.dumps(run_plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "request_body_manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def grade_r4_evidence(
    request_rows: list[dict[str, Any]],
    *,
    cleanup_by_mode: dict[str, str],
    diagnostic_ok_by_mode: dict[str, bool],
    repair_identity_by_mode: dict[str, dict[str, str]],
    resolved_prefix_config_by_mode: dict[str, dict[str, Any]],
    token_lcp_evidence_ok: bool,
) -> dict[str, Any]:
    prime_rows = [row for row in request_rows if row.get("request_role") == "prime"]
    measured_rows = [
        row for row in request_rows if row.get("request_role") == "measured"
    ]
    successful = [row for row in request_rows if row.get("status") == "success"]
    expected_groups = {item["group_id"] for item in build_run_plan()}
    represented_by_mode = {
        mode: {
            str(row.get("group_id"))
            for row in successful
            if row.get("mode") == mode
        }
        for mode in MODES
    }
    all_groups_matched = all(
        represented_by_mode[mode] == expected_groups for mode in MODES
    )
    bodies_by_mode = {
        mode: {
            str(row.get("request_id")): str(row.get("request_body_sha256"))
            for row in request_rows
            if row.get("mode") == mode
        }
        for mode in MODES
    }
    body_pairing_ok = (
        len(bodies_by_mode["prefix_cache_off"]) == 32
        and bodies_by_mode["prefix_cache_off"]
        == bodies_by_mode["prefix_cache_on"]
    )
    on_measured = [
        row
        for row in measured_rows
        if row.get("mode") == "prefix_cache_on"
    ]
    required_on = [
        row for row in on_measured if row.get("group_id") in POSITIVE_HIT_GROUPS
    ]
    boundary_on = [
        row for row in on_measured if row.get("group_id") not in POSITIVE_HIT_GROUPS
    ]
    required_positive = sum(
        float(row.get("prefix_hits_delta") or 0.0) > 0 for row in required_on
    )
    boundary_positive = sum(
        float(row.get("prefix_hits_delta") or 0.0) > 0 for row in boundary_on
    )
    required_hits_aligned = len(required_on) == 9 and all(
        float(row.get("prefix_hits_delta") or 0.0) > 0
        and float(row.get("prefix_hits_delta") or 0.0) % HYBRID_LCM_TOKENS == 0
        and float(row.get("prefix_hits_delta") or 0.0)
        == float(row.get("expected_prefix_hit_tokens") or 0.0)
        for row in required_on
    )
    on_hits_total = sum(
        float(row.get("prefix_hits_delta") or 0.0)
        for row in request_rows
        if row.get("mode") == "prefix_cache_on"
    )
    off_hits_total = sum(
        float(row.get("prefix_hits_delta") or 0.0)
        for row in request_rows
        if row.get("mode") == "prefix_cache_off"
    )
    accepted_by_mode = {
        mode: sum(
            float(row.get("accepted_token_delta") or 0.0)
            for row in request_rows
            if row.get("mode") == mode
        )
        for mode in MODES
    }
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
    resolved_prefix_control_ok = all(
        resolved_prefix_config_by_mode.get(mode, {}).get(
            "resolved_enable_prefix_caching"
        )
        is (mode == "prefix_cache_on")
        and resolved_prefix_config_by_mode.get(mode, {}).get(
            "server_command_has_expected_flag"
        )
        is True
        and resolved_prefix_config_by_mode.get(mode, {}).get(
            "server_command_has_opposite_flag"
        )
        is False
        and resolved_prefix_config_by_mode.get(mode, {}).get(
            "process_cmdline_has_expected_flag"
        )
        is True
        and resolved_prefix_config_by_mode.get(mode, {}).get(
            "process_cmdline_has_opposite_flag"
        )
        is False
        for mode in MODES
    )
    structural_complete = (
        len(request_rows) == 64
        and len(successful) == 64
        and len(prime_rows) == 16
        and len(measured_rows) == 48
        and all_groups_matched
        and body_pairing_ok
    )
    evidence_complete = (
        all(row.get("queue_metrics_ok") is True for row in request_rows)
        and all(row.get("counter_continuity_ok") is True for row in request_rows)
        and all(row.get("spec_activity_ok") is True for row in request_rows)
        and all(row.get("prefix_evidence_ok") is True for row in request_rows)
        and required_positive == 9
        and required_hits_aligned
        and on_hits_total > 0
        and off_hits_total == 0
        and all(value > 0 for value in accepted_by_mode.values())
        and same_repair
        and diagnostics_ok
        and resolved_prefix_control_ok
        and token_lcp_evidence_ok
    )
    any_measured_success = any(row in successful for row in measured_rows)

    if any(cleanup_by_mode.get(mode) != "clean" for mode in MODES):
        grade = "red_cleanup_incomplete"
    elif not any_measured_success:
        grade = "red_p6_3b_r4_explicit_prefix_cache_matched_ab_no_success"
    elif not structural_complete:
        grade = "yellow_p6_3b_r4_explicit_prefix_cache_matched_ab_partial"
    elif not evidence_complete:
        grade = "red_p6_3b_r4_explicit_prefix_cache_evidence_incomplete"
    else:
        grade = "candidate_green_p6_3b_r4_explicit_prefix_cache_matched_ab"

    return {
        "server_grade": grade,
        "prime_request_count": len(prime_rows),
        "measured_request_count": len(measured_rows),
        "successful_request_count": len(successful),
        "all_eight_groups_matched": all_groups_matched,
        "body_pairing_ok": body_pairing_ok,
        "prefix_cache_on_required_positive_hit_count": required_positive,
        "prefix_cache_on_boundary_positive_hit_count": boundary_positive,
        "prefix_cache_on_hit_delta_total": on_hits_total,
        "prefix_cache_off_hit_delta_total": off_hits_total,
        "required_positive_hits_hybrid_lcm_aligned": required_hits_aligned,
        "mtp_accepted_token_delta_by_mode": accepted_by_mode,
        "same_r2_repair_in_both_modes": same_repair,
        "required_diagnostic_ok_by_mode": diagnostic_ok_by_mode,
        "resolved_prefix_control_ok": resolved_prefix_control_ok,
        "resolved_prefix_config_by_mode": resolved_prefix_config_by_mode,
        "token_lcp_evidence_ok": token_lcp_evidence_ok,
        "queue_metrics_ok": all(
            row.get("queue_metrics_ok") is True for row in request_rows
        ),
        "counter_continuity_ok": all(
            row.get("counter_continuity_ok") is True for row in request_rows
        ),
        "prefix_evidence_ok": evidence_complete,
        "cleanup_by_mode": cleanup_by_mode,
        "mechanism_effect_accepted": False,
        "developer_review_required": True,
        "existing_p6_references_remain_true": True,
        "claim_boundary": (
            "explicit_prefix_cache_control_repaired_hybrid_kv_matched_ab_"
            "mechanism_effect_only"
        ),
    }


def _token_lcp_evidence_ok(manifest: dict[str, Any]) -> bool:
    measured = [
        record
        for record in manifest.get("records", [])
        if record.get("request_role") == "measured"
    ]
    required = [
        record
        for record in measured
        if record.get("group_id") in POSITIVE_HIT_GROUPS
    ]
    return (
        manifest.get("token_lcp_evidence_ok") is True
        and manifest.get("generated_text_retained") is False
        and manifest.get("token_ids_retained") is False
        and len(measured) == 24
        and len(required) == 9
        and all(
            isinstance(record.get("actual_lcp_sha256"), str)
            and len(record["actual_lcp_sha256"]) == 64
            and int(record.get("actual_token_lcp") or 0)
            >= int(record.get("planned_shared_tokens") or 0)
            and int(record.get("expected_prefix_hit_tokens") or 0)
            == int(record.get("actual_token_lcp") or 0)
            // HYBRID_LCM_TOKENS
            * HYBRID_LCM_TOKENS
            for record in measured
        )
        and all(
            int(record.get("expected_prefix_hit_tokens") or 0) > 0
            for record in required
        )
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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

    diagnostic_summary_by_mode = {
        mode: summarize_hybrid_diagnostics(
            _read_jsonl(
                artifact_dir
                / "modes"
                / mode
                / "runtime"
                / "hybrid_kv_runtime_diagnostic.jsonl"
            ),
            require_deferred_install=True,
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
        "prefix_cache_off": all(
            (
                diagnostic_summary_by_mode["prefix_cache_off"][
                    "install_event_count"
                ]
                > 0,
                diagnostic_summary_by_mode["prefix_cache_off"][
                    "deferred_import_order_verified"
                ],
                diagnostic_summary_by_mode["prefix_cache_off"][
                    "source_hashes_ok"
                ],
                diagnostic_summary_by_mode["prefix_cache_off"][
                    "retention_interval_explicitly_unset"
                ],
                source_gate_ok_by_mode["prefix_cache_off"],
            )
        ),
        "prefix_cache_on": (
            diagnostic_summary_by_mode["prefix_cache_on"][
                "hybrid_diagnostic_ok"
            ]
            and source_gate_ok_by_mode["prefix_cache_on"]
        ),
    }
    repair_identity_by_mode = {
        mode: _read_repair_identity(
            artifact_dir / "modes" / mode / "repair_identity.tsv"
        )
        for mode in MODES
    }
    resolved_prefix_config_by_mode = {
        mode: _read_json(
            artifact_dir
            / "modes"
            / mode
            / "runtime"
            / "resolved_prefix_cache_config.json"
        )
        for mode in MODES
    }
    manifest = _read_json(artifact_dir / "request_body_manifest.json")
    token_lcp_ok = _token_lcp_evidence_ok(manifest)
    grading = grade_r4_evidence(
        request_rows,
        cleanup_by_mode=cleanup_by_mode,
        diagnostic_ok_by_mode=diagnostic_ok_by_mode,
        repair_identity_by_mode=repair_identity_by_mode,
        resolved_prefix_config_by_mode=resolved_prefix_config_by_mode,
        token_lcp_evidence_ok=token_lcp_ok,
    )
    if not request_rows and (
        not all(source_gate_ok_by_mode.values())
        or not grading["resolved_prefix_control_ok"]
    ):
        grading["server_grade"] = "blocked_p6_3b_r4_source_or_resource_gate"
    grading["source_gate_ok_by_mode"] = source_gate_ok_by_mode

    _write_comparison_tables(artifact_dir, request_rows)
    (artifact_dir / "hybrid_kv_diagnostic_summary.json").write_text(
        json.dumps(
            {
                "by_mode": diagnostic_summary_by_mode,
                "required_diagnostic_ok_by_mode": diagnostic_ok_by_mode,
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
    (artifact_dir / "resolved_prefix_cache_config_summary.json").write_text(
        json.dumps(
            {
                "by_mode": resolved_prefix_config_by_mode,
                "resolved_prefix_control_ok": grading[
                    "resolved_prefix_control_ok"
                ],
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
        "resolved_prefix_control_ok": grading["resolved_prefix_control_ok"],
    }
    (artifact_dir / "environment_and_hashes.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    candidate_green = (
        "candidate_green_p6_3b_r4_explicit_prefix_cache_matched_ab"
    )
    failure = "none"
    if grading["server_grade"] != candidate_green:
        first_failed = next(
            (row for row in request_rows if row.get("status") != "success"),
            None,
        )
        if first_failed is not None:
            failure = json.dumps(first_failed, indent=2, sort_keys=True)[:8192]
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
        "# P6.3B-R4 explicit Prefix Cache control matched A/B server result",
        "",
        "- task_id: p6_3b_r4_deepseek_v4_flash_w8a8_mtp_explicit_prefix_cache_matched_ab_2026_0716",
        f"- server_grade: {grading['server_grade']}",
        f"- requests: {grading['successful_request_count']}/64 successful",
        f"- prime_requests: {grading['prime_request_count']}/16",
        f"- measured_requests: {grading['measured_request_count']}/48",
        f"- body_pairing_ok: {str(grading['body_pairing_ok']).lower()}",
        "- resolved_prefix_control_ok: "
        f"{str(grading['resolved_prefix_control_ok']).lower()}",
        "- prefix_cache_on_required_positive_hit_count: "
        f"{grading['prefix_cache_on_required_positive_hit_count']}/9",
        "- prefix_cache_on_boundary_positive_hit_count: "
        f"{grading['prefix_cache_on_boundary_positive_hit_count']}/15",
        "- prefix_cache_off_hit_delta_total: "
        f"{grading['prefix_cache_off_hit_delta_total']}",
        "- token_lcp_evidence_ok: "
        f"{str(grading['token_lcp_evidence_ok']).lower()}",
        "- same_r2_repair_in_both_modes: "
        f"{str(grading['same_r2_repair_in_both_modes']).lower()}",
        "- mechanism_effect_accepted: false (developer review required)",
        "- green_means_evidence_complete_not_prefix_cache_faster: true",
        "- fixed_mode_order_limitation: prefix_cache_off_then_prefix_cache_on",
        "- claim_boundary: explicit_prefix_cache_control_repaired_hybrid_kv_matched_ab_mechanism_effect_only",
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
        "resolved_prefix_cache_config_summary.json",
        "cleanup_status.txt",
        "first_failure_excerpt.txt",
    )
    candidate_rows = []
    total_without_grading = 0
    for name in candidate_names:
        path = artifact_dir / name
        if not path.exists() or name == "grading_inputs.json":
            continue
        size = path.stat().st_size
        total_without_grading += size
        candidate_rows.append(
            (
                str(path),
                size,
                hashlib.sha256(path.read_bytes()).hexdigest(),
                "bounded_structured_explicit_prefix_cache_ab_evidence_no_content_payload",
            )
        )
    grading_path = artifact_dir / "grading_inputs.json"
    grading["candidate_total_bytes"] = total_without_grading
    grading["candidate_size_gate_pass"] = True
    for _ in range(10):
        grading_path.write_text(
            json.dumps(grading, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        candidate_total = total_without_grading + grading_path.stat().st_size
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
    candidate_rows.append(
        (
            str(grading_path),
            grading_path.stat().st_size,
            hashlib.sha256(grading_path.read_bytes()).hexdigest(),
            "bounded_structured_explicit_prefix_cache_ab_evidence_no_content_payload",
        )
    )
    with (artifact_dir / "delivery_candidates.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["path", "bytes", "sha256", "sensitivity"])
        writer.writerows(candidate_rows)
    (artifact_dir / "delivery_candidates_total_bytes.txt").write_text(
        f"{grading['candidate_total_bytes']}\n", encoding="utf-8"
    )
    (artifact_dir / "server_grade.txt").write_text(
        grading["server_grade"] + "\n", encoding="utf-8"
    )
    return grading


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the DeepSeek P6.3B-R4 explicit Prefix Cache control matched A/B."
        )
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
        prepare_r4_artifacts(
            args.source_payload, args.artifact_dir, args.model_name
        )
        return 0
    if args.command == "run-mode":
        return execute_mode(
            args.artifact_dir,
            args.base_url,
            args.server_pid,
            args.mode,
            positive_hit_required_group_ids=POSITIVE_HIT_GROUPS,
        )
    grading = finalize_artifacts(args.artifact_dir)
    return (
        0
        if grading["server_grade"]
        == "candidate_green_p6_3b_r4_explicit_prefix_cache_matched_ab"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
