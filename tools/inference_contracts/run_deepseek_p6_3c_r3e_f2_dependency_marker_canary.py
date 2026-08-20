"""Driver/finalizer for the staged R3E-F2 dependency-marker canary."""

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

from tools.inference_contracts import (  # noqa: E402
    analyze_p6_3c_r3e_f2_dependency_markers as marker_analysis,
)
from tools.inference_contracts import (  # noqa: E402
    run_deepseek_p6_3c_r3e_latency_floor as r3e,
)


base = r3e.base
TASK_ID = "p6_3c_r3e_f2_request_scoped_dependency_marker_canary_2026_0820"
WORKLOAD_RELATIVE_PATH = (
    "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r3e_f2_request_scoped_dependency_marker_canary.yaml"
)
REQUEST_PREFIX = "p6_3c_r3e_f2"
TRACKS = ("mechanism",)
MODES = ("chunked_prefill_on",)
MAX_MODEL_LEN = 12288
MAX_NUM_SEQS = 9
S1_LIFECYCLE_IDS = ("f2_s1_01",)
S2_LIFECYCLE_IDS = ("f2_s2_01", "f2_s2_02")
ALL_LIFECYCLE_IDS = S1_LIFECYCLE_IDS + S2_LIFECYCLE_IDS

CONFIGS = (
    {
        "config_id": "admission_on_t4096",
        "mode": "chunked_prefill_on",
        "max_num_batched_tokens": 12288,
        "policy_type": "adaptive_on",
        "pressure_scope": "admission_only",
        "active_chunk_target_tokens": 4096,
        "decode_quantum_tokens": 2,
    },
    {
        "config_id": "persistent_on_t128",
        "mode": "chunked_prefill_on",
        "max_num_batched_tokens": 12288,
        "policy_type": "adaptive_on",
        "pressure_scope": "persistent_prefill",
        "active_chunk_target_tokens": 128,
        "decode_quantum_tokens": 2,
    },
)
CONFIG_BY_ID = {row["config_id"]: row for row in CONFIGS}
LIFECYCLE_SCHEDULE = (
    {
        "track": "mechanism",
        "lifecycle_id": "f2_s1_01",
        "mirror_round": "s1_single_pressure_window",
        "evidence_track": "dependency_marker_canary",
        "marker_pressure_step_limit": 1,
        **CONFIG_BY_ID["admission_on_t4096"],
    },
    {
        "track": "mechanism",
        "lifecycle_id": "f2_s2_01",
        "mirror_round": "s2_repeated_pressure_steps",
        "evidence_track": "dependency_marker_repetition",
        "marker_pressure_step_limit": 2,
        **CONFIG_BY_ID["admission_on_t4096"],
    },
    {
        "track": "mechanism",
        "lifecycle_id": "f2_s2_02",
        "mirror_round": "s2_repeated_pressure_steps",
        "evidence_track": "dependency_marker_repetition",
        "marker_pressure_step_limit": 2,
        **CONFIG_BY_ID["persistent_on_t128"],
    },
)
LIFECYCLE_BY_ID = {row["lifecycle_id"]: row for row in LIFECYCLE_SCHEDULE}

BOUNDED_CANDIDATES = (
    "result_summary.md",
    "environment_and_hashes.json",
    "marker_propagation_summary.json",
    "step_rank_marker_coverage.tsv",
    "dependency_edge_summary.tsv",
    "cross_domain_link_chains.tsv",
    "bottleneck_hypothesis_review.json",
    "adaptive_execution_review.json",
    "resource_recovery_summary.json",
    "grading_inputs.json",
    "scientific_outcome.json",
)


def _activate_contract() -> None:
    r3e.TASK_ID = TASK_ID
    r3e.WORKLOAD_RELATIVE_PATH = WORKLOAD_RELATIVE_PATH
    r3e.REQUEST_PREFIX = REQUEST_PREFIX
    r3e.TRACKS = TRACKS
    r3e.MODES = MODES
    r3e.MAX_MODEL_LEN = MAX_MODEL_LEN
    r3e.MAX_NUM_SEQS = MAX_NUM_SEQS
    r3e.CONFIGS = CONFIGS
    r3e.CONFIG_BY_ID = CONFIG_BY_ID
    r3e.LIFECYCLE_SCHEDULE = LIFECYCLE_SCHEDULE
    r3e.LIFECYCLE_BY_ID = LIFECYCLE_BY_ID
    r3e.HOST_LIFECYCLE_IDS = ()
    r3e.PROFILE_LIFECYCLE_IDS = ALL_LIFECYCLE_IDS
    r3e.EXPECTED_MODEL_LIFECYCLES = len(ALL_LIFECYCLE_IDS)
    r3e.EXPECTED_ENGINE_REQUESTS = len(ALL_LIFECYCLE_IDS) * 10
    r3e.EXPECTED_HTTP_REQUESTS = len(ALL_LIFECYCLE_IDS) * 3
    r3e._bind_base_globals()  # noqa: SLF001
    base.BOUNDED_CANDIDATES = BOUNDED_CANDIDATES


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    base._write_tsv(path, rows)  # noqa: SLF001


def _executed_lifecycles(artifact_dir: Path) -> tuple[str, ...]:
    return tuple(
        lifecycle_id
        for lifecycle_id in ALL_LIFECYCLE_IDS
        if (artifact_dir / "lifecycles" / lifecycle_id).is_dir()
    )


def _profile_control_rows(
    artifact_dir: Path, lifecycle_ids: tuple[str, ...]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lifecycle_id in lifecycle_ids:
        payload = _read_json(
            artifact_dir
            / "lifecycles"
            / lifecycle_id
            / "runtime"
            / "profile_api_control.json"
        )
        events = payload.get("events") or []
        rows.append(
            {
                "lifecycle_id": lifecycle_id,
                "profile_api_enabled": payload.get("profile_api_enabled"),
                "actions": ",".join(str(row.get("action")) for row in events),
                "http_statuses": ",".join(
                    str(row.get("http_status")) for row in events
                ),
                "profile_start_stop_complete": (
                    payload.get("profile_api_enabled") is True
                    and [row.get("action") for row in events] == ["start", "stop"]
                    and all(row.get("success") is True for row in events)
                ),
            }
        )
    return rows


def _lifecycle_rows(
    artifact_dir: Path, lifecycle_ids: tuple[str, ...]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lifecycle_id in lifecycle_ids:
        lifecycle_dir = artifact_dir / "lifecycles" / lifecycle_id
        requests = _read_jsonl(lifecycle_dir / "raw_request_results.jsonl")
        trials = _read_jsonl(lifecycle_dir / "raw_trial_results.jsonl")
        cleanup = (
            (lifecycle_dir / "cleanup_status.txt").read_text(encoding="utf-8").strip()
            if (lifecycle_dir / "cleanup_status.txt").is_file()
            else "missing"
        )
        exit_code = (
            (lifecycle_dir / "lifecycle_exit_code.txt")
            .read_text(encoding="utf-8")
            .strip()
            if (lifecycle_dir / "lifecycle_exit_code.txt").is_file()
            else "missing"
        )
        rows.append(
            {
                "lifecycle_id": lifecycle_id,
                "config_id": LIFECYCLE_BY_ID[lifecycle_id]["config_id"],
                "stage": "S1" if lifecycle_id in S1_LIFECYCLE_IDS else "S2",
                "lifecycle_exit_code": exit_code,
                "cleanup_status": cleanup,
                "request_count": len(requests),
                "successful_request_count": sum(
                    row.get("status") == "success" for row in requests
                ),
                "http_request_count": sum(
                    int(row.get("http_request_count") or 0) for row in trials
                ),
                "trial_count": len(trials),
            }
        )
    return rows


def _candidate_manifest(artifact_dir: Path) -> dict[str, Any]:
    files = []
    for name in BOUNDED_CANDIDATES:
        path = artifact_dir / name
        if path.is_file():
            files.append(
                {
                    "path": name,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "sensitivity": (
                        "internal_project_evidence_no_prompt_generated_text_or_token_ids"
                    ),
                }
            )
    total_bytes = sum(int(row["bytes"]) for row in files)
    if total_bytes > 70 * 1024:
        raise ValueError(f"F2 bounded package exceeds 70KB: {total_bytes}")
    return {
        "schema": "p6_3c_r3e_f2_candidate_manifest_v1",
        "task_id": TASK_ID,
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "available_methods": ["email", "upload-api", "server-local"],
        "recommended_method": "upload-api",
        "recommended_reason": "one_named_multi_file_session_with_sha_validation",
        "candidate_file_count": len(files),
        "candidate_total_bytes": total_bytes,
        "files": files,
    }


def package(artifact_dir: Path) -> dict[str, Any]:
    manifest_path = artifact_dir / "candidate_manifest.server_local.json"
    manifest_path.unlink(missing_ok=True)
    manifest = _candidate_manifest(artifact_dir)
    _write_json(manifest_path, manifest)
    return manifest


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    _activate_contract()
    executed = _executed_lifecycles(artifact_dir)
    final_analysis = marker_analysis.analyze_artifact(
        artifact_dir,
        executed,
        artifact_dir,
        stage="FINAL",
    )
    s1_gate = _read_json(
        artifact_dir / "stage_analysis" / "s1" / "marker_propagation_summary.json"
    )
    s1_complete = bool(s1_gate) and s1_gate.get("trace_parse_complete") is True
    s2_authorized = s1_gate.get("s2_authorized") is True
    s2_executed_exact = set(S2_LIFECYCLE_IDS).issubset(executed)
    staged_stop_valid = (not s2_authorized and executed == S1_LIFECYCLE_IDS) or (
        s2_authorized and s2_executed_exact
    )
    lifecycle_rows = _lifecycle_rows(artifact_dir, executed)
    _write_tsv(artifact_dir / "lifecycle_summary.tsv", lifecycle_rows)
    lifecycle_execution_complete = bool(lifecycle_rows) and all(
        row["lifecycle_exit_code"] == "0"
        and row["cleanup_status"] == "clean"
        and int(row["request_count"]) == 10
        and int(row["successful_request_count"]) == 10
        and int(row["http_request_count"]) == 3
        and int(row["trial_count"]) == 2
        for row in lifecycle_rows
    )
    profile_rows = _profile_control_rows(artifact_dir, executed)
    _write_tsv(artifact_dir / "f2_profile_control_summary.tsv", profile_rows)
    profile_control_complete = bool(profile_rows) and all(
        row["profile_start_stop_complete"] is True for row in profile_rows
    )
    s0 = _read_json(artifact_dir / "s0_source_import_smoke.json")
    recovery = _read_json(artifact_dir / "resource_recovery_summary.json")
    cleanup_status = (
        (artifact_dir / "cleanup_status.txt").read_text(encoding="utf-8").strip()
        if (artifact_dir / "cleanup_status.txt").is_file()
        else "missing"
    )
    cleanup_complete = (
        recovery.get("keep_alive_restored_exact") is True
        and cleanup_status == "clean"
    )
    evidence_complete = all(
        (
            s0.get("source_import_smoke_complete") is True,
            s0.get("npu_operation_requested") is False,
            s1_complete,
            staged_stop_valid,
            lifecycle_execution_complete,
            profile_control_complete,
            final_analysis.get("trace_parse_complete") is True,
            final_analysis.get("trace_rank_coverage_complete") is True,
            final_analysis.get("marker_presence_complete") is True,
            cleanup_complete,
        )
    )
    causal_resolved = final_analysis.get("causal_bottleneck_resolved") is True
    full_chain = final_analysis.get("full_dependency_chain_complete") is True
    if not evidence_complete:
        scientific_outcome = "dependency_marker_canary_evidence_incomplete"
    elif causal_resolved:
        scientific_outcome = (
            "repeated_dependency_linked_final_edge_resolved_"
            "optimization_target_unselected"
        )
    elif full_chain:
        scientific_outcome = (
            "explicit_marker_dependency_chain_observed_repeated_final_edge_unresolved"
        )
    else:
        scientific_outcome = (
            "explicit_marker_present_dependency_linkage_gap_precisely_bounded"
        )
    grading = {
        "task_id": TASK_ID,
        "server_grade": (
            "complete_p6_3c_r3e_f2_dependency_marker_canary_evidence"
            if evidence_complete
            else "incomplete_p6_3c_r3e_f2_dependency_marker_canary_evidence"
        ),
        "evidence_status": "complete" if evidence_complete else "incomplete",
        "scientific_outcome": scientific_outcome,
        "s0_source_import_smoke_complete": s0.get("source_import_smoke_complete"),
        "s1_complete": s1_complete,
        "s2_authorized": s2_authorized,
        "s2_executed": s2_executed_exact,
        "staged_stop_valid": staged_stop_valid,
        "executed_lifecycle_ids": list(executed),
        "trace_parse_complete": final_analysis.get("trace_parse_complete"),
        "rank_coverage_complete": final_analysis.get(
            "trace_rank_coverage_complete"
        ),
        "marker_presence_complete": final_analysis.get(
            "marker_presence_complete"
        ),
        "dependency_linkage_gap": final_analysis.get("dependency_linkage_gap"),
        "causal_bottleneck_resolved": causal_resolved,
        "optimization_target_selected": False,
        "performance_gain_claimed": False,
        "cleanup_complete": cleanup_complete,
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "next_task_authorized": False,
    }
    _write_json(artifact_dir / "grading_inputs.json", grading)
    outcome = {
        "task_id": TASK_ID,
        "source_a2_task_id": "p6_3c_r3e_f1_a2_step_flow_causal_linkage_2026_0809",
        "source_a2_outcome_preserved": (
            "temporal_step_attribution_complete_dependency_linkage_unavailable"
        ),
        "parent_r3d_outcome_preserved": (
            "persistent_prefill_tradeoff_no_candidate_within_bounds"
        ),
        "scientific_outcome": scientific_outcome,
        "causal_bottleneck_resolved": causal_resolved,
        "optimization_target_selected": False,
        "claim_boundary": (
            "request_scoped_dependency_marker_canary_not_performance_or_"
            "deployable_optimization_evidence"
        ),
    }
    _write_json(artifact_dir / "scientific_outcome.json", outcome)
    stage_execution = {
        "task_id": TASK_ID,
        "s0_completed_without_npu": s0.get("source_import_smoke_complete") is True,
        "s1_lifecycle_ids": list(S1_LIFECYCLE_IDS),
        "s1_completed": s1_complete,
        "s1_s2_authorized": s2_authorized,
        "s2_lifecycle_ids": list(S2_LIFECYCLE_IDS),
        "s2_executed": s2_executed_exact,
        "executed_lifecycle_ids": list(executed),
        "automatic_larger_experiment_authorized": False,
    }
    _write_json(artifact_dir / "stage_execution_summary.json", stage_execution)
    environment = {
        "task_id": TASK_ID,
        "repo_head": base._git_output("rev-parse", "HEAD"),  # noqa: SLF001
        "repo_origin_main": base._git_output(  # noqa: SLF001
            "rev-parse", "origin/main"
        ),
        "workload_path": WORKLOAD_RELATIVE_PATH,
        "workload_sha256": _sha256(REPO_ROOT / WORKLOAD_RELATIVE_PATH),
        "runner_sha256": _sha256(Path(__file__)),
        "analyzer_sha256": _sha256(Path(marker_analysis.__file__)),
        "marker_patch_sha256": _sha256(
            REPO_ROOT
            / "tools/inference_contracts/p6_3c_r3e_f2_dependency_marker.py"
        ),
        "s0_source_import_smoke": s0,
        "capacity_contract": {
            "max_model_len": MAX_MODEL_LEN,
            "max_num_batched_tokens": 12288,
            "max_num_seqs": MAX_NUM_SEQS,
            "enable_chunked_prefill": True,
            "enable_prefix_caching": False,
            "tensor_parallel_size": 8,
        },
        "generated_text_retained": False,
        "generated_token_ids_retained": False,
    }
    _write_json(artifact_dir / "environment_and_hashes.json", environment)
    adaptive_path = artifact_dir / "adaptive_execution_review.json"
    if not adaptive_path.is_file():
        _write_json(
            adaptive_path,
            {
                "task_id": TASK_ID,
                "adaptive_attempt_count": 0,
                "adaptive_patch_paths": [],
                "scientific_contract_changed": False,
                "shared_checkout_mutated": False,
                "final_package_must_be_regenerated_after_any_adaptation": True,
            },
        )
    _write_json(
        artifact_dir / "mechanism_scheduler_summary.json",
        {
            "task_id": TASK_ID,
            "marker_presence_complete": final_analysis.get(
                "marker_presence_complete"
            ),
            "dependency_linkage_gap": final_analysis.get("dependency_linkage_gap"),
            "performance_comparison_allowed": False,
        },
    )
    _write_tsv(
        artifact_dir / "performance_mode_cell_summary.tsv",
        [
            {
                "diagnostic_track": "not_applicable",
                "reason": "dependency_marker_canary_not_performance_comparison",
            }
        ],
    )
    _write_tsv(
        artifact_dir / "performance_order_balanced_pairs.tsv",
        [
            {
                "diagnostic_track": "not_applicable",
                "reason": "source_R3D_performance_outcome_preserved",
            }
        ],
    )
    lines = [
        f"# {TASK_ID} 结果摘要",
        "",
        f"- evidence status: `{grading['evidence_status']}`",
        f"- scientific outcome: `{scientific_outcome}`",
        f"- S0/S1 complete: `{s0.get('source_import_smoke_complete')}/{s1_complete}`；S2 authorized/executed: `{s2_authorized}/{s2_executed_exact}`。",
        f"- trace/rank/marker complete: `{final_analysis.get('trace_parse_complete')}/{final_analysis.get('trace_rank_coverage_complete')}/{final_analysis.get('marker_presence_complete')}`。",
        f"- dependency linkage gap: `{final_analysis.get('dependency_linkage_gap')}`。",
        f"- causal bottleneck resolved: `{causal_resolved}`；optimization target selected: `False`。",
        "- Marker containment is an instrumented worker execution scope. Host→runtime and runtime→actual-kernel edges still require profiler flow/correlation identifiers.",
        "- Free/Computing/Communication/Communication(Not Overlapped)/Notify_Wait remain derived analysis timelines and never satisfy the actual-kernel edge.",
        "- This canary does not repeat a budget sweep, produce a performance benefit claim, or authorize a larger experiment.",
        "",
    ]
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    package(artifact_dir)
    return grading


def main(argv: list[str] | None = None) -> int:
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
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    package_parser = sub.add_parser("package")
    package_parser.add_argument("--artifact-dir", type=Path, required=True)
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
    if args.command == "finalize":
        grading = finalize_artifacts(args.artifact_dir)
        return 0 if grading["evidence_status"] == "complete" else 2
    if args.command == "package":
        print(json.dumps(package(args.artifact_dir), indent=2, sort_keys=True))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
