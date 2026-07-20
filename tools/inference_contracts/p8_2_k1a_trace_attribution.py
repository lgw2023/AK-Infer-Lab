from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.p8_2_k1a_failure_forensics import inventory_tree


ROLE_ORDER = (
    "warmup",
    "prime",
    "pressure",
    "restore_follower",
    "repeat_follower",
    "isolated_control",
)
EVENT_NAMES = (
    "transfer_scheduled",
    "device_copy_submitted",
    "device_copy_enqueued",
    "device_copy_launch_returned",
    "copy_blocks_entered",
    "copy_blocks_returned",
    "transfer_poll_entered",
    "transfer_poll_returned",
    "transfer_completed",
    "store_event_completed",
    "cpu_hit_matched",
    "load_scheduled",
    "load_request_completed",
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method_source(text: str, class_name: str, method_name: str) -> str:
    tree = ast.parse(text)
    lines = text.splitlines()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    child.name == method_name
                ):
                    return "\n".join(lines[child.lineno - 1 : child.end_lineno])
    return ""


def audit_cpu_tier_source_semantics(
    vllm_root: Path,
    output_path: Path,
    *,
    expected_manager_sha256: str | None = None,
    expected_block_pool_sha256: str | None = None,
) -> dict[str, Any]:
    manager_path = vllm_root / "v1/simple_kv_offload/manager.py"
    block_pool_path = vllm_root / "v1/core/block_pool.py"
    manager_text = manager_path.read_text(encoding="utf-8")
    block_pool_text = block_pool_path.read_text(encoding="utf-8")
    match_source = _method_source(
        manager_text, "SimpleCPUOffloadScheduler", "get_num_new_matched_tokens"
    )
    eager_store_source = _method_source(
        manager_text, "SimpleCPUOffloadScheduler", "_prepare_eager_store_specs"
    )
    allocation_source = _method_source(block_pool_text, "BlockPool", "get_new_blocks")
    eviction_source = _method_source(
        block_pool_text, "BlockPool", "_maybe_evict_cached_block"
    )
    manager_sha256 = _hash_file(manager_path)
    block_pool_sha256 = _hash_file(block_pool_path)
    cpu_match = ".find_longest_cache_hit(" in match_source
    eager_allocation = all(
        marker in eager_store_source
        for marker in (".get_num_free_blocks(", ".get_new_blocks(")
    )
    cached_eviction = all(
        (
            ".popleft(" in allocation_source,
            "._maybe_evict_cached_block(" in allocation_source,
            ".cached_block_hash_to_block.pop(" in eviction_source,
        )
    )
    manager_hash_exact = (
        expected_manager_sha256 is None or manager_sha256 == expected_manager_sha256
    )
    block_pool_hash_exact = (
        expected_block_pool_sha256 is None
        or block_pool_sha256 == expected_block_pool_sha256
    )
    gate = all(
        (
            cpu_match,
            eager_allocation,
            cached_eviction,
            manager_hash_exact,
            block_pool_hash_exact,
        )
    )
    result = {
        "schema_version": "p8_2_k1a_r4_cpu_tier_source_semantics_v1",
        "source_semantics_gate": "pass" if gate else "fail",
        "manager_sha256": manager_sha256,
        "manager_hash_exact": manager_hash_exact,
        "block_pool_sha256": block_pool_sha256,
        "block_pool_hash_exact": block_pool_hash_exact,
        "cpu_match_uses_find_longest_cache_hit": cpu_match,
        "eager_store_allocates_from_cpu_block_pool": eager_allocation,
        "cpu_pool_allocation_may_evict_cached_hash_entry": cached_eviction,
        "capacity_churn_hypothesis_supported": (
            eager_allocation and cached_eviction
        ),
        "pressure_evicted_prime_from_cpu_tier_proven": False,
        "h2d_absence_cause_proven_as_unique": False,
        "claim_boundary": (
            "frozen_source_capacity_churn_semantics_only_no_actual_runtime_"
            "eviction_or_unique_cause_claim"
        ),
    }
    _write_json(output_path, result)
    return result


def _request_windows(source_result_dir: Path) -> list[dict[str, Any]]:
    mode_root = source_result_dir / "modes/prefix_cache_on"
    rows = _read_jsonl(mode_root / "raw_request_results.jsonl")
    metrics = mode_root / "raw_metrics"
    windows = []
    for row in rows:
        request_id = str(row.get("request_id") or "")
        role = str(row.get("k1a_role") or request_id.removeprefix("lifecycle_01_"))
        before = metrics / f"{request_id}_before.prom"
        after = metrics / f"{request_id}_after.prom"
        if not before.is_file() or not after.is_file():
            raise ValueError(f"request metric boundary missing: {request_id}")
        windows.append(
            {
                "request_id": request_id,
                "role": role,
                "start_timestamp_ns": before.stat().st_mtime_ns,
                "end_timestamp_ns": after.stat().st_mtime_ns,
                "prefix_hits_delta": float(row.get("prefix_hits_delta") or 0),
            }
        )
    if [window["role"] for window in windows] != list(ROLE_ORDER):
        raise ValueError("K1A request role order drift")
    for index, window in enumerate(windows):
        if window["start_timestamp_ns"] >= window["end_timestamp_ns"]:
            raise ValueError(f"invalid request metric window: {window['request_id']}")
        if index and windows[index - 1]["end_timestamp_ns"] > window["start_timestamp_ns"]:
            raise ValueError("K1A request metric windows overlap")
    return windows


def _phase_for_timestamp(
    timestamp_ns: int, windows: list[dict[str, Any]]
) -> tuple[str, str | None]:
    for index, window in enumerate(windows):
        if window["start_timestamp_ns"] <= timestamp_ns <= window["end_timestamp_ns"]:
            return str(window["role"]), str(window["role"])
        if index + 1 < len(windows):
            next_window = windows[index + 1]
            if window["end_timestamp_ns"] < timestamp_ns < next_window["start_timestamp_ns"]:
                return f"post_{window['role']}", None
    return "outside_request_windows", None


def _empty_summary() -> dict[str, Any]:
    return {
        "trace_event_count": 0,
        "d2h_submitted_copy_bytes": 0,
        "h2d_submitted_copy_bytes": 0,
        "d2h_event_indices": [],
        "h2d_event_indices": [],
        "store_event_completed_count": 0,
        "cpu_hit_matched_count": 0,
        "cpu_hit_matched_tokens": 0,
        "load_scheduled_count": 0,
        "load_request_completed_count": 0,
        "event_counts": {name: 0 for name in EVENT_NAMES},
    }


def _add_event(summary: dict[str, Any], row: dict[str, Any]) -> None:
    summary["trace_event_count"] += 1
    event = str(row.get("event") or "")
    if event in summary["event_counts"]:
        summary["event_counts"][event] += 1
    direction = str(row.get("direction") or "")
    if event == "device_copy_submitted" and direction in {"d2h", "h2d"}:
        summary[f"{direction}_submitted_copy_bytes"] += int(
            row.get("byte_count") or 0
        )
    event_idx = row.get("event_idx")
    if event_idx is not None and direction in {"d2h", "h2d"}:
        summary[f"{direction}_event_indices"].append(int(event_idx))
    if event == "store_event_completed":
        summary["store_event_completed_count"] += 1
    if event == "cpu_hit_matched":
        summary["cpu_hit_matched_count"] += 1
        summary["cpu_hit_matched_tokens"] += int(row.get("num_new_tokens") or 0)
    if event == "load_scheduled":
        summary["load_scheduled_count"] += 1
    if event == "load_request_completed":
        summary["load_request_completed_count"] += 1


def build_trace_attribution(
    source_result_dir: Path, output_dir: Path
) -> dict[str, Any]:
    source_resolved = source_result_dir.resolve()
    output_resolved = output_dir.resolve()
    if source_resolved == output_resolved or source_resolved in output_resolved.parents:
        raise ValueError("trace attribution output must be outside source evidence")
    if output_dir.exists():
        raise FileExistsError(f"trace attribution output exists: {output_dir}")
    before = inventory_tree(source_result_dir)
    windows = _request_windows(source_result_dir)
    trace_rows: list[dict[str, Any]] = []
    for path in sorted((source_result_dir / "runtime/offload_trace").glob("trace.*.jsonl")):
        trace_rows.extend(_read_jsonl(path))
    trace_rows.sort(key=lambda row: int(row.get("timestamp_ns") or 0))
    by_role = {role: _empty_summary() for role in ROLE_ORDER}
    by_phase: dict[str, dict[str, Any]] = {}
    unattributed_request_id_events = 0
    for row in trace_rows:
        phase, role = _phase_for_timestamp(int(row.get("timestamp_ns") or 0), windows)
        phase_summary = by_phase.setdefault(phase, _empty_summary())
        _add_event(phase_summary, row)
        if role is not None:
            _add_event(by_role[role], row)
        request_id = row.get("request_id")
        if request_id and role is None:
            request_role = str(request_id).removeprefix("lifecycle_01_")
            if request_role in by_role:
                _add_event(by_role[request_role], row)
            else:
                unattributed_request_id_events += 1
    for summary in [*by_role.values(), *by_phase.values()]:
        summary["d2h_event_indices"] = sorted(set(summary["d2h_event_indices"]))
        summary["h2d_event_indices"] = sorted(set(summary["h2d_event_indices"]))
    prefix_hits = {window["role"]: window["prefix_hits_delta"] for window in windows}
    restore = by_role["restore_follower"]
    result = {
        "schema_version": "p8_2_k1a_r4_trace_attribution_v1",
        "request_window_gate": "pass",
        "request_windows_exact": True,
        "request_windows": windows,
        "trace_event_count": len(trace_rows),
        "by_role": by_role,
        "by_phase": by_phase,
        "unattributed_request_id_event_count": unattributed_request_id_events,
        "restore_miss_then_repeat_gpu_hit_pattern": (
            prefix_hits["restore_follower"] == 0
            and prefix_hits["repeat_follower"] > 0
            and restore["cpu_hit_matched_count"] == 0
            and restore["load_scheduled_count"] == 0
        ),
        "d2h_bytes_semantics": "cumulative_submitted_copy_volume",
        "unique_cpu_residency_bytes_observed": False,
        "cpu_tier_eviction_events_instrumented": False,
        "prime_blocks_resident_at_restore_proven": False,
        "pressure_evicted_prime_from_cpu_tier_proven": False,
        "restore_recomputed_then_repeat_gpu_hit_supported": (
            prefix_hits["restore_follower"] == 0
            and prefix_hits["repeat_follower"] > 0
        ),
        "h2d_absence_cause_proven_as_unique": False,
        "generated_content_retained": False,
        "token_ids_retained": False,
    }
    output_dir.mkdir(parents=True)
    after = inventory_tree(source_result_dir)
    result["source_evidence_unchanged"] = before == after
    _write_json(output_dir / "trace_attribution_summary.json", result)
    _write_json(
        output_dir / "trace_source_provenance.json",
        {
            "source_evidence_before": before,
            "source_evidence_after": after,
            "source_evidence_unchanged": before == after,
        },
    )
    (output_dir / "trace_attribution_summary.md").write_text(
        "\n".join(
            (
                "# P8.2-K1A-R4 raw trace attribution",
                "",
                "- D2H/H2D events are grouped by request metric-file wall-clock windows and inter-request gaps.",
                "- Submitted byte totals are cumulative copy volume, not unique CPU-tier residency.",
                "- The current trace does not instrument CPU-tier eviction or prove why H2D was absent.",
                f"- restore miss then repeat GPU-hit pattern: `{str(result['restore_miss_then_repeat_gpu_hit_pattern']).lower()}`",
                "- boundary: read-only attribution; no runtime, performance or unique-cause claim.",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    files = []
    for name in (
        "trace_attribution_summary.json",
        "trace_source_provenance.json",
        "trace_attribution_summary.md",
    ):
        path = output_dir / name
        files.append(
            {
                "absolute_path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": _hash_file(path),
                "sensitivity": (
                    "bounded_operational_metadata_no_content_or_token_ids"
                ),
            }
        )
    total = sum(row["bytes"] for row in files)
    if total > 71680:
        raise ValueError(f"trace attribution candidate exceeds 70KB: {total}")
    _write_json(
        output_dir / "candidate_manifest.server_local.json",
        {
            "schema_version": "p8_2_k1a_r4_trace_candidate_manifest_v1",
            "files": files,
            "payload_file_count": len(files),
            "payload_total_bytes": total,
            "result_transfer_authorized": True,
            "transfer_method_selected": False,
        },
    )
    return result


def finalize_r4_offline_closeout(result_root: Path) -> dict[str, Any]:
    refinalization = json.loads(
        (result_root / "refinalization/offline_refinalization.json").read_text(
            encoding="utf-8"
        )
    )
    trace = json.loads(
        (result_root / "trace_attribution/trace_attribution_summary.json").read_text(
            encoding="utf-8"
        )
    )
    source = json.loads(
        (result_root / "source_semantics/cpu_tier_source_semantics.json").read_text(
            encoding="utf-8"
        )
    )
    store_only_accepted = all(
        (
            str(refinalization.get("refinalized_grade", "")).endswith(
                "store_only_no_restore"
            ),
            refinalization.get("request_transport_evidence_exact") is True,
            refinalization.get("successful_request_count") == 6,
            refinalization.get("offload_store_evidence_candidate") is True,
            refinalization.get("offload_restore_evidence_candidate") is False,
            refinalization.get("source_evidence_unchanged") is True,
        )
    )
    trace_gate = all(
        (
            trace.get("request_window_gate") == "pass",
            trace.get("request_windows_exact") is True,
            trace.get("source_evidence_unchanged") is True,
            trace.get("unique_cpu_residency_bytes_observed") is False,
            trace.get("pressure_evicted_prime_from_cpu_tier_proven") is False,
            trace.get("h2d_absence_cause_proven_as_unique") is False,
        )
    )
    source_gate = all(
        (
            source.get("source_semantics_gate") == "pass",
            source.get("pressure_evicted_prime_from_cpu_tier_proven") is False,
            source.get("h2d_absence_cause_proven_as_unique") is False,
        )
    )
    task_green = store_only_accepted and trace_gate and source_gate
    result = {
        "schema_version": "p8_2_k1a_r4_offline_closeout_v1",
        "task_grade": (
            "candidate_green_p8_2_k1a_r4_offline_store_only_closeout"
            if task_green
            else "blocked_p8_2_k1a_r4_offline_closeout_gate"
        ),
        "parent_runtime_grade": refinalization.get("source_server_grade"),
        "parent_runtime_grade_preserved": (
            refinalization.get("source_server_grade_preserved") is True
        ),
        "refinalized_runtime_grade": refinalization.get("refinalized_grade"),
        "store_only_refinalization_accepted": store_only_accepted,
        "trace_attribution_gate": "pass" if trace_gate else "fail",
        "source_semantics_gate": "pass" if source_gate else "fail",
        "capacity_churn_hypothesis_supported_by_source": source.get(
            "capacity_churn_hypothesis_supported"
        ),
        "capacity_churn_proven_for_parent_lifecycle": False,
        "h2d_absence_cause_proven_as_unique": False,
        "formal_h2d_trigger_lifecycle_allowed": False,
        "formal_h2d_trigger_lifecycle_requires_new_handoff": True,
        "npu_started": False,
        "vllm_started": False,
        "model_request_sent": False,
        "performance_reference_accepted": False,
        "k2_authorized": False,
        "p8_3_i1_authorized": False,
        "next_task_authorized": False,
        "claim_boundary": (
            "offline_store_only_refinalization_raw_trace_attribution_and_frozen_"
            "source_semantics_only_no_runtime_replay_or_unique_cause_claim"
        ),
    }
    _write_json(result_root / "grading_summary.json", result)
    (result_root / "task_grade.txt").write_text(
        result["task_grade"] + "\n", encoding="utf-8"
    )
    (result_root / "result_summary.md").write_text(
        "\n".join(
            (
                "# P8.2-K1A-R4 offline closeout",
                "",
                f"- task_grade: `{result['task_grade']}`",
                f"- parent_runtime_grade: `{result['parent_runtime_grade']}` (preserved)",
                f"- refinalized_runtime_grade: `{result['refinalized_runtime_grade']}`",
                f"- trace_attribution_gate: `{result['trace_attribution_gate']}`",
                f"- source_semantics_gate: `{result['source_semantics_gate']}`",
                "- D2H store-only evidence is accepted; H2D restore remains open.",
                "- Source semantics support capacity churn as a hypothesis, but the parent lifecycle does not prove actual prime eviction or a unique cause.",
                "- no NPU/vLLM/model request; K2, P8.3-I1 and a new H2D-trigger lifecycle remain unauthorized.",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    relative_candidates = (
        "result_summary.md",
        "grading_summary.json",
        "task_grade.txt",
        "refinalization/offline_refinalization.json",
        "refinalization/corrected_request_summary.tsv",
        "refinalization/source_evidence_provenance.json",
        "trace_attribution/trace_attribution_summary.json",
        "trace_attribution/trace_source_provenance.json",
        "source_semantics/cpu_tier_source_semantics.json",
    )
    files = []
    for relative in relative_candidates:
        path = result_root / relative
        files.append(
            {
                "relative_path": relative,
                "absolute_path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": _hash_file(path),
                "sensitivity": (
                    "bounded_operational_metadata_no_content_or_token_ids"
                ),
            }
        )
    total = sum(row["bytes"] for row in files)
    if total > 71680:
        raise ValueError(f"R4 offline closeout candidate exceeds 70KB: {total}")
    _write_json(
        result_root / "candidate_manifest.server_local.json",
        {
            "schema_version": "p8_2_k1a_r4_offline_closeout_manifest_v1",
            "files": files,
            "payload_file_count": len(files),
            "payload_total_bytes": total,
            "max_total_bytes": 71680,
            "result_transfer_authorized": True,
            "transfer_method_selected": False,
            "generated_content_retained": False,
            "token_ids_retained": False,
        },
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    trace = commands.add_parser("trace-attribution")
    trace.add_argument("--source-result-dir", type=Path, required=True)
    trace.add_argument("--output-dir", type=Path, required=True)
    source = commands.add_parser("source-audit")
    source.add_argument("--vllm-root", type=Path, required=True)
    source.add_argument("--output", type=Path, required=True)
    source.add_argument("--expected-manager-sha256")
    source.add_argument("--expected-block-pool-sha256")
    finalize = commands.add_parser("finalize-closeout")
    finalize.add_argument("--result-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "trace-attribution":
        result = build_trace_attribution(args.source_result_dir, args.output_dir)
    elif args.command == "source-audit":
        result = audit_cpu_tier_source_semantics(
            args.vllm_root,
            args.output,
            expected_manager_sha256=args.expected_manager_sha256,
            expected_block_pool_sha256=args.expected_block_pool_sha256,
        )
    else:
        result = finalize_r4_offline_closeout(args.result_root)
    print(json.dumps(result, sort_keys=True))
    if args.command == "finalize-closeout":
        return 0 if result.get("task_grade") == (
            "candidate_green_p8_2_k1a_r4_offline_store_only_closeout"
        ) else 2
    return 0 if result.get("source_semantics_gate") != "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())
