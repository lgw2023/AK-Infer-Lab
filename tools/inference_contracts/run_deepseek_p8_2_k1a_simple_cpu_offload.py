from __future__ import annotations

import argparse
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

from tools.inference_contracts.p8_2_k1a_simple_cpu_offload_observer import (
    summarize_trace_rows,
)
from tools.inference_contracts.p8_2_k1a_failure_forensics import (
    build_failure_diagnostic,
    first_failed_predicate,
)
from tools.inference_contracts.run_deepseek_p6_3b_prefix_cache_ab import (
    _common_prefix_length,
    _read_jsonl,
    execute_mode,
    prepare_artifacts,
)


TASK_ID = os.environ.get(
    "P8_2_K1A_TASK_ID",
    "p8_2_k1a_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0717",
)
CPU_BYTES_TO_USE = int(os.environ.get("P8_2_K1A_CPU_BYTES_TO_USE", "274877906944"))
CPU_BYTES_TO_USE_PER_RANK = int(
    os.environ.get("P8_2_K1A_CPU_BYTES_TO_USE_PER_RANK", "34359738368")
)
OUTPUT_TOKENS = 64
BLOCK_SIZE = 128
HYBRID_LCM_TOKENS = 16384
PRIMARY_GROUP = "k1a_primary_32768_prefix90"
ROLE_CONTEXT = {
    "warmup": 4096,
    "prime": 32768,
    "pressure": 131072,
    "restore_follower": 32768,
    "repeat_follower": 32768,
    "isolated_control": 32768,
}
ROLE_ORDER = tuple(ROLE_CONTEXT)
REQUEST_ROLE = {
    "lifecycle_01_warmup": "warmup",
    "lifecycle_01_prime": "prime",
    "lifecycle_01_pressure": "pressure",
    "lifecycle_01_restore_follower": "restore_follower",
    "lifecycle_01_repeat_follower": "repeat_follower",
    "lifecycle_01_isolated_control": "isolated_control",
}
CANDIDATE_GREEN = os.environ.get(
    "P8_2_K1A_CANDIDATE_GREEN",
    "candidate_green_p8_2_k1a_simple_cpu_offload_store_restore",
)
NO_SUCCESS_GRADE = os.environ.get(
    "P8_2_K1A_NO_SUCCESS_GRADE",
    "red_p8_2_k1a_simple_cpu_offload_no_success",
)
PARTIAL_GRADE = os.environ.get(
    "P8_2_K1A_PARTIAL_GRADE",
    "yellow_p8_2_k1a_simple_cpu_offload_partial",
)
STORE_ONLY_GRADE = os.environ.get(
    "P8_2_K1A_STORE_ONLY_GRADE",
    "yellow_p8_2_k1a_store_only_no_restore",
)
EVIDENCE_INCOMPLETE_GRADE = os.environ.get(
    "P8_2_K1A_EVIDENCE_INCOMPLETE_GRADE",
    "red_p8_2_k1a_transfer_evidence_incomplete",
)
RESULT_TRANSFER_AUTHORIZED = (
    os.environ.get("P8_2_K1A_RESULT_TRANSFER_AUTHORIZED", "true").lower()
    == "true"
)
CANDIDATE_NAMES = (
    "result_summary.md",
    "environment_and_hashes.json",
    "request_body_manifest.json",
    "request_summary.tsv",
    "transfer_trace_summary.json",
    "connector_resolution_summary.json",
    "mtp_queue_health_summary.json",
    "host_memory_summary.json",
    "repair_diagnostic_summary.json",
    "grading_inputs.json",
    "cleanup_status.txt",
    "first_failure_excerpt.txt",
    "failure_diagnostic_summary.json",
)


def _plan_row(
    request_id: str,
    group_id: str,
    request_role: str,
    repeat_index: int,
    context_tokens: int,
    shared_tokens: int,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "group_id": group_id,
        "request_role": request_role,
        "repeat_index": repeat_index,
        "context_tokens": context_tokens,
        "output_tokens": OUTPUT_TOKENS,
        "target_shared_prefix_ratio_pct": 90 if shared_tokens else 0,
        "target_shared_prefix_tokens": shared_tokens,
    }


def build_run_plan() -> list[dict[str, Any]]:
    shared = 32768 * 90 // 100 // BLOCK_SIZE * BLOCK_SIZE
    return [
        _plan_row(
            "lifecycle_01_warmup", "k1a_warmup_4096", "prime", 0, 4096, 0
        ),
        _plan_row(
            "lifecycle_01_prime", PRIMARY_GROUP, "prime", 0, 32768, shared
        ),
        _plan_row(
            "lifecycle_01_pressure",
            "k1a_pressure_131072",
            "prime",
            0,
            131072,
            0,
        ),
        _plan_row(
            "lifecycle_01_restore_follower",
            PRIMARY_GROUP,
            "measured",
            1,
            32768,
            shared,
        ),
        _plan_row(
            "lifecycle_01_repeat_follower",
            PRIMARY_GROUP,
            "measured",
            2,
            32768,
            shared,
        ),
        _plan_row(
            "lifecycle_01_isolated_control",
            "k1a_isolated_control_32768",
            "prime",
            0,
            32768,
            0,
        ),
    ]


def prepare_k1a_artifacts(
    source_payload: Path,
    artifact_dir: Path,
    model_name: str,
) -> dict[str, Any]:
    plan = build_run_plan()
    prepared = prepare_artifacts(
        source_payload,
        artifact_dir,
        model_name,
        plan=plan,
    )
    by_request = {
        str(row["request_id"]): row for row in prepared["records"]
    }
    prompts: dict[str, list[int]] = {}
    records: list[dict[str, Any]] = []
    for row in plan:
        request_id = str(row["request_id"])
        record = by_request[request_id]
        body_path = artifact_dir / str(record["body_relative_path"])
        body = json.loads(body_path.read_text(encoding="utf-8"))
        prompts[request_id] = body["prompt"]
        k1a_role = REQUEST_ROLE[request_id]
        row["k1a_role"] = k1a_role
        row["expected_prefix_hit_tokens"] = (
            HYBRID_LCM_TOKENS
            if k1a_role in {"restore_follower", "repeat_follower"}
            else 0
        )
        records.append({**record, **row})

    primary = prompts["lifecycle_01_prime"]
    restore_lcp = _common_prefix_length(
        primary, prompts["lifecycle_01_restore_follower"]
    )
    repeat_lcp = _common_prefix_length(
        primary, prompts["lifecycle_01_repeat_follower"]
    )
    isolated_ids = (
        "lifecycle_01_warmup",
        "lifecycle_01_pressure",
        "lifecycle_01_isolated_control",
    )
    cross_group_lcp_max = max(
        _common_prefix_length(primary, prompts[request_id])
        for request_id in isolated_ids
    )
    if restore_lcp // HYBRID_LCM_TOKENS * HYBRID_LCM_TOKENS != HYBRID_LCM_TOKENS:
        raise ValueError("restore follower hybrid-LCM expectation drift")
    if repeat_lcp // HYBRID_LCM_TOKENS * HYBRID_LCM_TOKENS != HYBRID_LCM_TOKENS:
        raise ValueError("repeat follower hybrid-LCM expectation drift")
    if cross_group_lcp_max >= BLOCK_SIZE:
        raise ValueError("isolated K1A body shares a cacheable primary block")
    if len({row["request_body_sha256"] for row in records}) != 6:
        raise ValueError("K1A request bodies are not unique")

    (artifact_dir / "run_plan.json").write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "task_id": TASK_ID,
        "source_payload_sha256": hashlib.sha256(source_payload.read_bytes()).hexdigest(),
        "lifecycle_count": 1,
        "request_count": 6,
        "role_order": list(ROLE_ORDER),
        "restore_token_lcp": restore_lcp,
        "repeat_token_lcp": repeat_lcp,
        "expected_restore_prefix_hit_tokens": HYBRID_LCM_TOKENS,
        "cross_group_lcp_max": cross_group_lcp_max,
        "cross_group_lcp_less_than_block_size": cross_group_lcp_max < BLOCK_SIZE,
        "body_hashes_unique": True,
        "records": records,
        "generated_text_retained": False,
        "token_ids_retained": False,
    }
    (artifact_dir / "request_body_manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _request_evidence_exact(row: dict[str, Any]) -> bool:
    role = str(row.get("k1a_role") or REQUEST_ROLE.get(str(row.get("request_id"))))
    expected_context = ROLE_CONTEXT.get(role)
    return all(
        (
            row.get("status") == "success",
            row.get("http_status") == 200,
            int(row.get("prompt_tokens") or 0) == expected_context,
            int(row.get("context_tokens") or 0) == expected_context,
            int(row.get("output_tokens") or 0) == OUTPUT_TOKENS,
            int(row.get("generated_token_count") or 0) == OUTPUT_TOKENS,
            int(row.get("streamed_token_count") or 0) == OUTPUT_TOKENS,
            row.get("finish_reason") == "length",
            row.get("saw_done") is True,
            0 < int(row.get("max_token_chunk_width") or 0) <= 2,
            row.get("queue_metrics_ok") is True,
            row.get("counter_continuity_ok") is True,
            row.get("spec_activity_ok") is True,
            float(row.get("accepted_token_delta") or 0) > 0,
            len(str(row.get("request_body_sha256") or "")) == 64,
        )
    )


def grade_k1a_evidence(
    *,
    request_rows: list[dict[str, Any]],
    trace_summary: dict[str, Any],
    cleanup: str,
    connector_resolution_ok: bool,
    repair_diagnostic_ok: bool,
    host_memory_gate_ok: bool,
    accepted_capacity_exact: bool = True,
) -> dict[str, Any]:
    roles = [
        str(row.get("k1a_role") or REQUEST_ROLE.get(str(row.get("request_id"))))
        for row in request_rows
    ]
    successful = [row for row in request_rows if row.get("status") == "success"]
    structural_complete = len(request_rows) == 6 and roles == list(ROLE_ORDER)
    request_evidence_exact = structural_complete and all(
        _request_evidence_exact(row) for row in request_rows
    )
    base_evidence = all(
        (
            request_evidence_exact,
            connector_resolution_ok,
            repair_diagnostic_ok,
            host_memory_gate_ok,
            accepted_capacity_exact,
            cleanup == "clean",
        )
    )
    store_ok = trace_summary.get("d2h_store_complete") is True
    restore_ok = trace_summary.get("h2d_restore_complete") is True
    store_pipeline_exact = (
        trace_summary.get("d2h_async_copy_pipeline_exact") is True
    )
    runtime_evidence_exact = trace_summary.get("runtime_evidence_exact") is True
    if not successful:
        grade = NO_SUCCESS_GRADE
    elif not structural_complete:
        grade = PARTIAL_GRADE
    elif base_evidence and store_ok and store_pipeline_exact and not restore_ok:
        grade = STORE_ONLY_GRADE
    elif not (
        base_evidence and store_ok and restore_ok and runtime_evidence_exact
    ):
        grade = EVIDENCE_INCOMPLETE_GRADE
    else:
        grade = CANDIDATE_GREEN
    return {
        "server_grade": grade,
        "successful_request_count": len(successful),
        "request_count": len(request_rows),
        "request_order_exact": structural_complete,
        "request_evidence_exact": request_evidence_exact,
        "connector_resolution_ok": connector_resolution_ok,
        "repair_diagnostic_ok": repair_diagnostic_ok,
        "host_memory_gate_ok": host_memory_gate_ok,
        "accepted_capacity_exact": accepted_capacity_exact,
        "cpu_bytes_to_use": CPU_BYTES_TO_USE,
        "cpu_bytes_to_use_per_rank": CPU_BYTES_TO_USE_PER_RANK,
        "cleanup": cleanup,
        "offload_store_evidence_candidate": store_ok,
        "offload_restore_evidence_candidate": restore_ok,
        "runtime_evidence_exact": trace_summary.get("runtime_evidence_exact") is True,
        "performance_reference_accepted": False,
        "optimization_claim_accepted": False,
        "developer_review_required": True,
        "claim_boundary": (
            "deepseek_tp8_ep_mtp_single_lifecycle_d2h_store_h2d_restore_"
            "mechanism_only"
        ),
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_trace_rows(trace_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not trace_root.is_dir():
        return rows
    for path in sorted(trace_root.glob("trace.*.jsonl")):
        rows.extend(_read_jsonl(path))
    return rows


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_request_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = (
        "request_id",
        "k1a_role",
        "status",
        "http_status",
        "context_tokens",
        "output_tokens",
        "prompt_tokens",
        "generated_token_count",
        "streamed_token_count",
        "finish_reason",
        "saw_done",
        "max_token_chunk_width",
        "prefix_hits_delta",
        "accepted_token_delta",
        "queue_metrics_ok",
        "counter_continuity_ok",
        "spec_activity_ok",
        "first_failed_predicate",
        "ttft_ms",
        "e2el_ms",
        "request_body_sha256",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(
            {**row, "first_failed_predicate": first_failed_predicate(row)}
            for row in rows
        )


def write_candidate_manifest(artifact_dir: Path) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for name in CANDIDATE_NAMES:
        path = artifact_dir / name
        if not path.is_file():
            missing.append(name)
            continue
        files[name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "sensitivity": "bounded_operational_metadata_no_content_or_token_ids",
        }
    total = sum(row["bytes"] for row in files.values())
    if total > 71680:
        raise ValueError(f"candidate package exceeds 70KB: {total}")
    manifest = {
        "schema_version": "p8_2_k1a_candidate_manifest_v1",
        "result_root": str(artifact_dir),
        "files": files,
        "missing_candidate_files": missing,
        "candidate_file_count": len(files),
        "candidate_total_bytes": total,
        "max_total_bytes": 71680,
        "result_transfer_authorized": RESULT_TRANSFER_AUTHORIZED,
    }
    _write_json(artifact_dir / "candidate_manifest.server_local.json", manifest)
    return manifest


def finalize_k1a(artifact_dir: Path) -> dict[str, Any]:
    request_path = artifact_dir / "modes/prefix_cache_on/raw_request_results.jsonl"
    rows = _read_jsonl(request_path)
    for row in rows:
        row["k1a_role"] = REQUEST_ROLE.get(str(row.get("request_id")), "unknown")
    trace_summary = summarize_trace_rows(
        _read_trace_rows(artifact_dir / "runtime/offload_trace"),
        expected_world_size=8,
        restore_request_suffix="restore_follower",
    )
    _write_json(artifact_dir / "transfer_trace_summary.json", trace_summary)
    connector = _read_json(artifact_dir / "connector_resolution_summary.json")
    repair = _read_json(artifact_dir / "repair_diagnostic_summary.json")
    host = _read_json(artifact_dir / "host_memory_summary.json")
    accepted_capacity_exact = all(
        (
            connector.get("resolved_cpu_capacity_exact") is True,
            connector.get("cpu_bytes_to_use") == CPU_BYTES_TO_USE,
            connector.get("cpu_bytes_to_use_per_rank") == CPU_BYTES_TO_USE_PER_RANK,
            host.get("configured_cpu_tier_bytes_total") == CPU_BYTES_TO_USE,
            host.get("configured_cpu_tier_bytes_per_rank") == CPU_BYTES_TO_USE_PER_RANK,
        )
    )
    cleanup_path = artifact_dir / "cleanup_status.txt"
    cleanup = cleanup_path.read_text(encoding="utf-8").strip() if cleanup_path.is_file() else "missing"
    grading = grade_k1a_evidence(
        request_rows=rows,
        trace_summary=trace_summary,
        cleanup=cleanup,
        connector_resolution_ok=connector.get("resolved_connector_exact") is True,
        repair_diagnostic_ok=repair.get("hybrid_diagnostic_ok") is True,
        host_memory_gate_ok=host.get("preflight_gate_ok") is True,
        accepted_capacity_exact=accepted_capacity_exact,
    )
    grading["task_id"] = TASK_ID
    grading["trace_summary"] = trace_summary
    failure_diagnostic, failure_excerpt = build_failure_diagnostic(
        artifact_dir, rows, trace_summary
    )
    _write_json(
        artifact_dir / "failure_diagnostic_summary.json", failure_diagnostic
    )
    _write_json(artifact_dir / "grading_inputs.json", grading)
    _write_request_summary(artifact_dir / "request_summary.tsv", rows)
    mtp = {
        "request_count": len(rows),
        "spec_activity_ok_count": sum(row.get("spec_activity_ok") is True for row in rows),
        "queue_metrics_ok_count": sum(row.get("queue_metrics_ok") is True for row in rows),
        "counter_continuity_ok_count": sum(
            row.get("counter_continuity_ok") is True for row in rows
        ),
        "accepted_token_delta_total": sum(
            float(row.get("accepted_token_delta") or 0) for row in rows
        ),
    }
    _write_json(artifact_dir / "mtp_queue_health_summary.json", mtp)
    failure_path = artifact_dir / "first_failure_excerpt.txt"
    existing_failure = (
        failure_path.read_text(encoding="utf-8") if failure_path.is_file() else ""
    )
    if grading["server_grade"] == CANDIDATE_GREEN:
        failure_path.write_text("none\n", encoding="utf-8")
    elif not existing_failure.strip() or existing_failure.strip() == grading["server_grade"]:
        failure_path.write_text(failure_excerpt, encoding="utf-8")
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(
            (
                "# P8.2-K1A SimpleCPUOffload result",
                "",
                f"- task_id: `{TASK_ID}`",
                f"- server_grade: `{grading['server_grade']}`",
                f"- successful_request_count: `{grading['successful_request_count']}/6`",
                f"- accepted_capacity_exact: `{grading['accepted_capacity_exact']}`",
                f"- cpu_bytes_to_use_per_rank: `{CPU_BYTES_TO_USE_PER_RANK}`",
                f"- d2h_store_complete: `{trace_summary['d2h_store_complete']}`",
                f"- h2d_restore_complete: `{trace_summary['h2d_restore_complete']}`",
                f"- d2h_bytes_total: `{trace_summary['d2h_bytes_total']}`",
                f"- h2d_bytes_total: `{trace_summary['h2d_bytes_total']}`",
                "- boundary: one DeepSeek TP8+EP+MTP mechanism lifecycle; not a performance reference or optimization claim.",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    grading["candidate_files_present"] = [
        name for name in CANDIDATE_NAMES if (artifact_dir / name).is_file()
    ]
    write_candidate_manifest(artifact_dir)
    return grading


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    execute = subparsers.add_parser("execute")
    execute.add_argument("--artifact-dir", type=Path, required=True)
    execute.add_argument("--base-url", required=True)
    execute.add_argument("--server-pid", type=int, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        result = prepare_k1a_artifacts(
            args.source_payload, args.artifact_dir, args.model_name
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "execute":
        return execute_mode(
            args.artifact_dir,
            args.base_url,
            args.server_pid,
            "prefix_cache_on",
            positive_hit_required_group_ids={PRIMARY_GROUP},
        )
    result = finalize_k1a(args.artifact_dir)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["server_grade"] == CANDIDATE_GREEN else 2


if __name__ == "__main__":
    raise SystemExit(main())
