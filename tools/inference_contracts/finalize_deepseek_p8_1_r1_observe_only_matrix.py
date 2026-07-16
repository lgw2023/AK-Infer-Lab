from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools.inference_contracts.finalize_deepseek_p8_1_observe_only_matrix import (
    finalize_matrix_artifacts,
)
from tools.inference_contracts.run_deepseek_p6_3b_r1_hybrid_kv_repair import (
    summarize_hybrid_diagnostics,
)


PARENT_CANDIDATE_GREEN = "candidate_green_p8_1_official_mtp_observe_only_matrix"
CANDIDATE_GREEN = "candidate_green_p8_1_r1_official_mtp_observe_only_matrix"
EXPECTED_REPAIR_IDENTITY = {
    "runtime_impl": "6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c",
    "deferred_loader": "9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631",
    "mtp_patch": "75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1",
    "hybrid_patch": "cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e",
    "deferred_patch": "ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b",
    "overlay_proposer": "7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02",
    "overlay_ascend_coordinator": "a1ed9c82e308608cd20965a49baa29a3e95d723248fff699fd83dfb3caf10250",
    "overlay_ascend_interface": "524c933ef17806ecba0634804bc562de1f69dc095fe1346e2edd0103845bfa75",
}


def _all_true(record: Mapping[str, Any], names: tuple[str, ...]) -> bool:
    return all(record.get(name) is True for name in names)


def grade_r1_replay(
    parent: Mapping[str, Any],
    body: Mapping[str, Any],
    repair: Mapping[str, Any],
    resolved: Mapping[str, Any],
) -> dict[str, Any]:
    successful_requests = int(parent.get("successful_request_count", 0))
    parent_trace_gate_ok = (
        parent.get("grade") == PARENT_CANDIDATE_GREEN
        and successful_requests == 6
        and _all_true(
            parent,
            (
                "shared_prefix_exact",
                "isolated_zero_hit",
                "per_request_mtp_ok",
                "health_queue_ok",
                "replay_deterministic",
                "join_coverage_complete",
            ),
        )
        and int(parent.get("trace_validation_errors", -1)) == 0
        and parent.get("cleanup") == "clean"
    )
    frozen_body_gate_ok = (
        body.get("frozen_body_hashes_exact") is True
        and int(body.get("request_count", 0)) == 6
    )
    repair_gate_ok = _all_true(
        repair,
        (
            "repair_identity_exact",
            "hybrid_diagnostic_ok",
            "deferred_import_order_verified",
            "retention_interval_explicitly_unset",
            "source_hashes_ok",
        ),
    )
    resolved_prefix_cache_gate_ok = _all_true(
        resolved,
        (
            "resolved_enable_prefix_caching",
            "server_command_has_expected_flag",
            "process_cmdline_has_expected_flag",
            "opposite_flag_absent",
        ),
    )
    all_green = all(
        (
            parent_trace_gate_ok,
            frozen_body_gate_ok,
            repair_gate_ok,
            resolved_prefix_cache_gate_ok,
        )
    )
    if successful_requests == 0:
        grade = "red_p8_1_r1_request_no_success"
    elif successful_requests < 6:
        grade = "yellow_p8_1_r1_matrix_partial"
    elif all_green:
        grade = CANDIDATE_GREEN
    elif parent.get("cleanup") != "clean":
        grade = "red_p8_1_r1_cleanup_incomplete"
    else:
        grade = "yellow_p8_1_r1_matrix_trace_invalid"

    persistent_shared_prefix_failure = (
        successful_requests == 6 and parent.get("shared_prefix_exact") is False
    )
    return {
        **dict(parent),
        "grade": grade,
        "parent_trace_grade": parent.get("grade"),
        "parent_trace_gate_ok": parent_trace_gate_ok,
        "frozen_body_gate_ok": frozen_body_gate_ok,
        "repair_gate_ok": repair_gate_ok,
        "resolved_prefix_cache_gate_ok": resolved_prefix_cache_gate_ok,
        "persistent_shared_prefix_failure": persistent_shared_prefix_failure,
        "cause_supported_by_replay": all_green,
        "cause_proven_as_unique": False,
        "performance_effect_accepted": False,
        "next_action": (
            "read_only_frozen_source_and_server_local_log_diagnosis"
            if persistent_shared_prefix_failure
            else "wait_for_external_developer_review"
        ),
        "claim_boundary": (
            "official_mtp_shared_prefix_observe_only_trace_repair_replay_not_performance"
        ),
    }


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        return fallback
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object row: {path}")
            rows.append(value)
    return rows


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def finalize_r1_artifacts(artifact_dir: Path) -> dict[str, Any]:
    parent = finalize_matrix_artifacts(artifact_dir)
    body_source = artifact_dir / "prepared_requests/body_relationship_summary.json"
    body = _read_json(
        body_source,
        {"frozen_body_hashes_exact": False, "request_count": 0},
    )
    _write_json(artifact_dir / "body_relationship_summary.json", body)

    runtime_dir = artifact_dir / "runtime"
    identity = _read_json(runtime_dir / "repair_identity.json", {})
    diagnostics = _read_jsonl(runtime_dir / "hybrid_kv_runtime_diagnostic.jsonl")
    diagnostic_summary = summarize_hybrid_diagnostics(
        diagnostics,
        require_deferred_install=True,
    )
    repair = {
        **diagnostic_summary,
        "repair_identity": identity,
        "expected_repair_identity": EXPECTED_REPAIR_IDENTITY,
        "repair_identity_exact": identity == EXPECTED_REPAIR_IDENTITY,
        "base_environment_or_site_packages_mutated": False,
    }
    _write_json(artifact_dir / "repair_diagnostic_summary.json", repair)

    resolved = _read_json(
        runtime_dir / "resolved_prefix_cache_config.json",
        {
            "resolved_enable_prefix_caching": False,
            "server_command_has_expected_flag": False,
            "process_cmdline_has_expected_flag": False,
            "opposite_flag_absent": False,
        },
    )
    grading = grade_r1_replay(parent, body, repair, resolved)
    _write_json(artifact_dir / "grading_inputs.json", grading)

    environment_path = artifact_dir / "environment_and_hashes.json"
    environment = _read_json(environment_path, {})
    environment.update(
        {
            "task_id": (
                "p8_1_r1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0717"
            ),
            "parent_task_id": (
                "p8_1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0716"
            ),
            "full_r2_repair_identity": identity,
            "full_r2_repair_identity_exact": repair["repair_identity_exact"],
            "prefix_cache_retention_interval": "explicitly_unset",
            "localhost_no_proxy_explicit": True,
            "generated_content_retained": False,
            "generated_token_ids_retained": False,
        }
    )
    _write_json(environment_path, environment)

    if grading["grade"] == CANDIDATE_GREEN:
        failure = "none"
    elif grading["persistent_shared_prefix_failure"]:
        failure = "medium_shared_follower_prefix_hit_mismatch_after_complete_r2_repair"
    else:
        failure = grading["grade"]
    (artifact_dir / "first_failure_excerpt.txt").write_text(
        failure + "\n", encoding="utf-8"
    )
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(
            [
                "# P8.1-R1 official MTP observe-only repair replay result",
                "",
                f"- grade: `{grading['grade']}`",
                f"- successful_requests: `{grading.get('successful_request_count', 0)}/6`",
                f"- shared_prefix_exact: `{str(grading.get('shared_prefix_exact', False)).lower()}`",
                f"- frozen_body_gate_ok: `{str(grading['frozen_body_gate_ok']).lower()}`",
                f"- repair_gate_ok: `{str(grading['repair_gate_ok']).lower()}`",
                "- resolved_prefix_cache_gate_ok: "
                f"`{str(grading['resolved_prefix_cache_gate_ok']).lower()}`",
                "- causal interpretation: replay may support the missing-repair diagnosis, but does not prove it is the unique cause.",
                "- boundary: observe-only repair replay; not a performance comparison or P8.2 authorization.",
                "- content retention: generated text and token IDs are not retained.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return grading


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finalize the bounded P8.1-R1 matrix")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    grading = finalize_r1_artifacts(args.artifact_dir)
    print(json.dumps(grading, sort_keys=True))
    return 0 if grading["grade"] == CANDIDATE_GREEN else 1


if __name__ == "__main__":
    raise SystemExit(main())
