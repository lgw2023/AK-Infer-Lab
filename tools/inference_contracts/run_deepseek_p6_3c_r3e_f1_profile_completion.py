"""P6.3C-R3E-F1 request-scoped profiler completion.

R3E attempt03 already completed the three unprofiled host-timing lifecycles.
F1 preserves that evidence and runs only the two missing diagnostic endpoints.
It replaces process-wide ``msprof`` wrapping with vLLM's request-scoped torch
profiler API, so model loading is outside the captured interval.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts import (  # noqa: E402
    analyze_torch_profiler_traces as trace_analysis,
)
from tools.inference_contracts import (  # noqa: E402
    run_deepseek_p6_3c_r3e_latency_floor as r3e,
)


base = r3e.base
SOURCE_TASK_ID = r3e.TASK_ID
TASK_ID = "p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01"
WORKLOAD_RELATIVE_PATH = (
    "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r3e_f1_request_scoped_profile_completion.yaml"
)
REQUEST_PREFIX = "p6_3c_r3e_f1"
TRACKS = ("mechanism",)
MODES = ("chunked_prefill_on",)
MAX_MODEL_LEN = 12288
MAX_NUM_SEQS = 9
EXPECTED_MODEL_LIFECYCLES = 2
EXPECTED_ENGINE_REQUESTS = 20
EXPECTED_HTTP_REQUESTS = 6
PROFILE_LIFECYCLE_IDS = ("profile_f1_01", "profile_f1_02")

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
        "lifecycle_id": "profile_f1_01",
        "mirror_round": "request_scoped_profile",
        "evidence_track": "vllm_torch_profile_api",
        **CONFIG_BY_ID["admission_on_t4096"],
    },
    {
        "track": "mechanism",
        "lifecycle_id": "profile_f1_02",
        "mirror_round": "request_scoped_profile",
        "evidence_track": "vllm_torch_profile_api",
        **CONFIG_BY_ID["persistent_on_t128"],
    },
)
LIFECYCLE_BY_ID = {row["lifecycle_id"]: row for row in LIFECYCLE_SCHEDULE}


def _activate_contract() -> None:
    """Bind the shared staged-arrival driver to the two F1 lifecycles."""

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
    r3e.PROFILE_LIFECYCLE_IDS = PROFILE_LIFECYCLE_IDS
    r3e.EXPECTED_MODEL_LIFECYCLES = EXPECTED_MODEL_LIFECYCLES
    r3e.EXPECTED_ENGINE_REQUESTS = EXPECTED_ENGINE_REQUESTS
    r3e.EXPECTED_HTTP_REQUESTS = EXPECTED_HTTP_REQUESTS
    r3e._bind_base_globals()  # noqa: SLF001
    base.BOUNDED_CANDIDATES = BOUNDED_CANDIDATES


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def validate_source_host_evidence(source_result: Path) -> dict[str, Any]:
    required = (
        "r3e_host_attribution.json",
        "r3e_host_phase_summary.tsv",
        "r3e_mechanism_cells.tsv",
        "lifecycle_summary.tsv",
        "environment_and_hashes.json",
    )
    missing = [name for name in required if not (source_result / name).is_file()]
    if missing:
        raise ValueError(f"source R3E host evidence missing: {missing}")

    host = _read_json(source_result / "r3e_host_attribution.json")
    environment = _read_json(source_result / "environment_and_hashes.json")
    lifecycle_rows = _read_tsv(source_result / "lifecycle_summary.tsv")
    mechanism_rows = _read_tsv(source_result / "r3e_mechanism_cells.tsv")
    source_host_ids = {"host_01", "host_02", "host_03"}
    successful_host_ids = {
        row.get("lifecycle_id")
        for row in lifecycle_rows
        if row.get("lifecycle_id") in source_host_ids
        and row.get("lifecycle_exit_code") == "0"
        and row.get("cleanup_status") == "clean"
    }
    mechanism_host_ids = {
        row.get("lifecycle_id")
        for row in mechanism_rows
        if row.get("lifecycle_id") in source_host_ids
        and str(row.get("mechanism_contract_complete")).lower() == "true"
    }
    checks = {
        "source_task_id_exact": environment.get("task_id") == SOURCE_TASK_ID,
        "host_timing_complete": host.get("host_timing_complete") is True,
        "three_host_lifecycles_successful": successful_host_ids == source_host_ids,
        "three_host_mechanism_cells_complete": mechanism_host_ids == source_host_ids,
        "engine_pipeline_fraction_gate": (
            host.get("mixed_engine_pipeline_fraction_at_least_0_80") is True
        ),
        "target_insensitive_gate": (
            host.get("persistent_mixed_pipeline_target_insensitive") is True
        ),
    }
    return {
        "source_task_id": SOURCE_TASK_ID,
        "source_result": str(source_result),
        "source_host_evidence_complete": all(checks.values()),
        "checks": checks,
        "host_attribution": host,
        "files": {
            name: {
                "bytes": (source_result / name).stat().st_size,
                "sha256": _sha256(source_result / name),
            }
            for name in required
        },
        "source_result_overwritten": False,
    }


def _profile_control_complete(artifact_dir: Path) -> tuple[bool, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for lifecycle_id in PROFILE_LIFECYCLE_IDS:
        evidence = _read_json(
            artifact_dir
            / "lifecycles"
            / lifecycle_id
            / "runtime/profile_api_control.json"
        )
        events = evidence.get("events") or []
        rows.append(
            {
                "lifecycle_id": lifecycle_id,
                "profile_api_enabled": evidence.get("profile_api_enabled"),
                "actions": [row.get("action") for row in events],
                "http_statuses": [row.get("http_status") for row in events],
                "profile_start_stop_complete": (
                    evidence.get("profile_api_enabled") is True
                    and [row.get("action") for row in events] == ["start", "stop"]
                    and all(row.get("success") is True for row in events)
                ),
            }
        )
    return all(row["profile_start_stop_complete"] for row in rows), rows


def finalize_artifacts(artifact_dir: Path, source_result: Path) -> dict[str, Any]:
    _activate_contract()
    source = validate_source_host_evidence(source_result)
    mechanism = r3e.write_mechanism_evidence(artifact_dir, PROFILE_LIFECYCLE_IDS)
    roots = {
        lifecycle_id: artifact_dir
        / "lifecycles"
        / lifecycle_id
        / "runtime/torch_profiler"
        for lifecycle_id in PROFILE_LIFECYCLE_IDS
    }
    profiler = trace_analysis.analyze_trace_roots(roots)
    trace_analysis.write_tsv(
        artifact_dir / "r3e_f1_trace_inventory.tsv", profiler["trace_inventory"]
    )
    trace_analysis.write_tsv(
        artifact_dir / "r3e_f1_device_category_summary.tsv",
        profiler["category_rows"],
    )
    trace_analysis.write_tsv(
        artifact_dir / "r3e_f1_top_device_operators.tsv",
        profiler["top_operator_rows"],
    )
    (artifact_dir / "r3e_f1_profiler_summary.json").write_text(
        json.dumps(
            {
                key: value
                for key, value in profiler.items()
                if key not in {"trace_inventory", "category_rows", "top_operator_rows"}
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "source_r3e_host_evidence.json").write_text(
        json.dumps(source, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    profile_control_complete, profile_control_rows = _profile_control_complete(
        artifact_dir
    )
    base._write_tsv(  # noqa: SLF001
        artifact_dir / "r3e_f1_profile_control_summary.tsv", profile_control_rows
    )
    lifecycle_rows = base._lifecycle_rows(artifact_dir)  # noqa: SLF001
    startup_rows = base._startup_rows(artifact_dir)  # noqa: SLF001
    payload = base._payload_summary(artifact_dir)  # noqa: SLF001
    base._write_tsv(artifact_dir / "lifecycle_summary.tsv", lifecycle_rows)  # noqa: SLF001
    base._write_tsv(  # noqa: SLF001
        artifact_dir / "startup_resource_summary.tsv", startup_rows
    )
    (artifact_dir / "payload_identity_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    base._write_tsv(  # noqa: SLF001
        artifact_dir / "performance_mode_cell_summary.tsv",
        [
            {
                "diagnostic_track": "not_applicable",
                "reason": "request_scoped_profiler_not_performance_comparison",
            }
        ],
    )
    base._write_tsv(  # noqa: SLF001
        artifact_dir / "performance_order_balanced_pairs.tsv",
        [
            {
                "diagnostic_track": "not_applicable",
                "reason": "source_R3D_performance_outcome_preserved",
            }
        ],
    )

    request_count = sum(int(row.get("request_count") or 0) for row in lifecycle_rows)
    success_count = sum(
        int(row.get("successful_request_count") or 0) for row in lifecycle_rows
    )
    http_count = sum(int(row.get("http_request_count") or 0) for row in lifecycle_rows)
    lifecycle_complete = len(lifecycle_rows) == EXPECTED_MODEL_LIFECYCLES and all(
        row.get("lifecycle_exit_code") == "0"
        and row.get("cleanup_status") == "clean"
        and int(row.get("request_count") or 0) == 10
        and int(row.get("successful_request_count") or 0) == 10
        and int(row.get("http_request_count") or 0) == 3
        for row in lifecycle_rows
    )
    resolved_complete = all(
        row.get("resolved_enable_chunked_prefill") is True
        and row.get("resolved_enable_prefix_caching") is False
        and row.get("resolved_max_model_len") == MAX_MODEL_LEN
        and row.get("resolved_max_num_batched_tokens") == 12288
        and row.get("resolved_max_num_seqs") == MAX_NUM_SEQS
        and row.get("profiler_enabled") is True
        and row.get("profiler_backend") == "vllm_torch_profile_api"
        for row in lifecycle_rows
    )
    startup_complete = len(startup_rows) == EXPECTED_MODEL_LIFECYCLES and all(
        row.get("server_ready") is True for row in startup_rows
    )
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
            source["source_host_evidence_complete"],
            lifecycle_complete,
            resolved_complete,
            startup_complete,
            profile_control_complete,
            mechanism.get("full_prefill_sequence_gate_complete"),
            profiler["profiler_complete"],
            request_count == success_count == EXPECTED_ENGINE_REQUESTS,
            http_count == EXPECTED_HTTP_REQUESTS,
            payload.get("all_body_files_sha256_exact"),
            cleanup_complete,
        )
    )
    if not source["source_host_evidence_complete"]:
        scientific = "source_r3e_host_evidence_incomplete"
    elif not mechanism.get("full_prefill_sequence_gate_complete"):
        scientific = "request_scoped_profile_mechanism_incomplete"
    elif not profiler["profiler_complete"]:
        scientific = "latency_floor_device_category_attribution_incomplete"
    else:
        scientific = "executor_path_supported_with_request_scoped_device_categories"

    grading = {
        "task_id": TASK_ID,
        "source_task_id": SOURCE_TASK_ID,
        "server_grade": (
            "complete_p6_3c_r3e_f1_request_scoped_profile_evidence"
            if evidence_complete
            else "incomplete_p6_3c_r3e_f1_request_scoped_profile_evidence"
        ),
        "evidence_status": "complete" if evidence_complete else "incomplete",
        "scientific_outcome": scientific,
        "source_host_evidence_complete": source["source_host_evidence_complete"],
        "lifecycles_complete": lifecycle_complete,
        "resolved_config_exact": resolved_complete,
        "profile_api_control_complete": profile_control_complete,
        "profiler_complete": profiler["profiler_complete"],
        "mechanism_complete": mechanism.get("full_prefill_sequence_gate_complete"),
        "request_count": request_count,
        "successful_request_count": success_count,
        "http_request_count": http_count,
        "cleanup_complete": cleanup_complete,
        "keep_alive_restore_exact": recovery.get("keep_alive_restored_exact"),
        "profiler_data_excluded_from_performance_claim": True,
        "parent_r3d_outcome_preserved": (
            "persistent_prefill_tradeoff_no_candidate_within_bounds"
        ),
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "next_task_authorized": False,
        "universal_benefit_claimed": False,
    }
    (artifact_dir / "grading_inputs.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    outcome = {
        "task_id": TASK_ID,
        "source_task_id": SOURCE_TASK_ID,
        "scientific_outcome": scientific,
        "evidence_complete": evidence_complete,
        "source_host_attribution": source["host_attribution"],
        "profiler_lifecycle_summaries": profiler["lifecycle_summaries"],
        "claim_boundary": (
            "controlled_decode_resident_request_scoped_operator_category_evidence_only"
        ),
    }
    (artifact_dir / "scientific_outcome.json").write_text(
        json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    environment = {
        "task_id": TASK_ID,
        "source_task_id": SOURCE_TASK_ID,
        "repo_head": base._git_output("rev-parse", "HEAD"),  # noqa: SLF001
        "repo_origin_main": base._git_output(  # noqa: SLF001
            "rev-parse", "origin/main"
        ),
        "workload_path": WORKLOAD_RELATIVE_PATH,
        "workload_sha256": _sha256(REPO_ROOT / WORKLOAD_RELATIVE_PATH),
        "runner_sha256": _sha256(Path(__file__)),
        "profiler_backend": "vllm_torch_profile_api",
        "profile_window": "after_warmup_before_measured_trial_to_after_measured_trial",
        "capacity_contract": {
            "max_model_len": MAX_MODEL_LEN,
            "max_num_batched_tokens": 12288,
            "max_num_seqs": MAX_NUM_SEQS,
            "prefix_cache_enabled": False,
        },
        "generated_text_retained": False,
        "generated_token_ids_retained": False,
        "runtime_overlay_import_smoke": _read_json(
            artifact_dir / "runtime_overlay_preflight_smoke.json"
        ),
    }
    (artifact_dir / "environment_and_hashes.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    host = source["host_attribution"]
    lines = [
        f"# {TASK_ID} 结果摘要",
        "",
        f"- evidence status: `{grading['evidence_status']}`",
        f"- scientific outcome: `{scientific}`",
        f"- source R3E host evidence complete: `{source['source_host_evidence_complete']}`；new profiler lifecycles: `{sum(row.get('lifecycle_exit_code') == '0' for row in lifecycle_rows)}/{EXPECTED_MODEL_LIFECYCLES}`。",
        f"- request-scoped profiler control complete: `{profile_control_complete}`；trace/device evidence complete: `{profiler['profiler_complete']}`。",
        f"- source host pipeline fraction gate: `{host.get('mixed_engine_pipeline_fraction_at_least_0_80')}`；T128/T1024 pipeline median ratio: `{host.get('persistent_t128_to_t1024_pipeline_median_ratio')}`。",
        "- Profiling starts only after model readiness and lifecycle warmup, and stops after the single measured staged-arrival trial; model loading is outside the captured interval.",
        "- Device duration sums are diagnostic counters because streams overlap. They are not a wall-clock decomposition or a profiler-on performance comparison.",
        "- R3D persistent-policy performance result and the original P6.3C blocked audit remain unchanged.",
        "",
    ]
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    failure = artifact_dir / "first_failure_excerpt.txt"
    if evidence_complete:
        failure.write_text("none\n", encoding="utf-8")
    elif not failure.is_file():
        failure.write_text(
            f"scientific_outcome={scientific}\n"
            f"source_host_evidence_complete={source['source_host_evidence_complete']}\n"
            f"profile_api_control_complete={profile_control_complete}\n"
            f"profiler_complete={profiler['profiler_complete']}\n",
            encoding="utf-8",
        )
    return grading


BOUNDED_CANDIDATES = (
    "result_summary.md",
    "environment_and_hashes.json",
    "source_r3e_host_evidence.json",
    "payload_identity_summary.json",
    "lifecycle_summary.tsv",
    "r3e_mechanism_summary.json",
    "r3e_mechanism_cells.tsv",
    "r3e_f1_profile_control_summary.tsv",
    "r3e_f1_profiler_summary.json",
    "r3e_f1_trace_inventory.tsv",
    "r3e_f1_device_category_summary.tsv",
    "r3e_f1_top_device_operators.tsv",
    "scientific_outcome.json",
    "grading_inputs.json",
    "startup_resource_summary.tsv",
    "runtime_overlay_preflight_smoke.json",
    "resource_recovery_summary.json",
    "cleanup_status.txt",
    "first_failure_excerpt.txt",
)


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
    validate_source = sub.add_parser("validate-source")
    validate_source.add_argument("--source-r3e-result", type=Path, required=True)
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    finalize.add_argument(
        "--source-r3e-result",
        type=Path,
        default=Path(os.environ["P6_3C_R3E_SOURCE_RESULT"])
        if os.environ.get("P6_3C_R3E_SOURCE_RESULT")
        else None,
    )
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
    if args.command == "validate-source":
        evidence = validate_source_host_evidence(args.source_r3e_result)
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0 if evidence["source_host_evidence_complete"] else 2
    if args.command == "finalize":
        if args.source_r3e_result is None:
            raise ValueError(
                "--source-r3e-result or P6_3C_R3E_SOURCE_RESULT is required"
            )
        grading = finalize_artifacts(args.artifact_dir, args.source_r3e_result)
        return 0 if grading["evidence_status"] == "complete" else 2
    if args.command == "package":
        base.package_results(args.artifact_dir)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
