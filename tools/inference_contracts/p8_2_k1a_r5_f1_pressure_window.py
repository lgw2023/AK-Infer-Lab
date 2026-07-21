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


PARENT_GRADE = "red_p8_2_k1a_r5_l1_r1_cpu_target_lost"
BLOCKED_GRADE = "blocked_p8_2_k1a_r5_f1_no_exact_pressure_window"
READY_GRADE = "candidate_ready_p8_2_k1a_r5_f1_exact_pressure_window"
SENSITIVITY = "bounded_operational_metadata_no_content_or_token_ids"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_parent_package(root: Path) -> dict[str, Any]:
    manifest_path = root / "candidate_manifest.server_local.json"
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != (
        "p8_2_k1a_r5_l1_bounded_candidate_manifest_v1"
    ):
        raise ValueError("unexpected R5-L1-R1 manifest schema")
    if manifest.get("generated_content_retained") is not False:
        raise ValueError("parent retained generated content")
    if manifest.get("token_ids_retained") is not False:
        raise ValueError("parent retained token ids")
    if manifest.get("result_transfer_authorized") is not True:
        raise ValueError("parent result eligibility drift")
    if manifest.get("transfer_method_selected") is not False:
        raise ValueError("parent transfer method must remain unselected")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("parent manifest files missing")
    checked = []
    for relative, expected in sorted(files.items()):
        path = root / relative
        if not path.is_file():
            raise ValueError(f"parent payload missing: {relative}")
        actual = {
            "relative_path": relative,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "sensitivity": expected.get("sensitivity"),
        }
        if actual["bytes"] != expected.get("bytes"):
            raise ValueError(f"parent payload size drift: {relative}")
        if actual["sha256"] != expected.get("sha256"):
            raise ValueError(f"parent payload hash drift: {relative}")
        if actual["sensitivity"] != SENSITIVITY:
            raise ValueError(f"parent payload sensitivity drift: {relative}")
        checked.append(actual)

    grading = _read_json(root / "grading_summary.json")
    timeline = _read_json(root / "residency_gate_timeline.json")
    transfer = _read_json(root / "transfer_trace_summary.json")
    required = {
        "server_grade": PARENT_GRADE,
        "successful_request_count": 3,
        "request_evidence_exact": True,
        "cleanup": "clean",
        "actual_cpu_eviction_proven": False,
        "h2d_restore_mechanism_candidate": False,
        "performance_reference_accepted": False,
        "k2_authorized": False,
        "p8_3_i1_authorized": False,
        "next_task_authorized": False,
    }
    for field, expected in required.items():
        if grading.get(field) != expected:
            raise ValueError(f"parent grading drift: {field}")
    if timeline.get("pressure_request_count_executed") != 1:
        raise ValueError("parent pressure count drift")
    if timeline.get("restore_sent") is not False:
        raise ValueError("parent unexpectedly sent restore")
    if timeline.get("terminal_decision") != "cpu_target_lost":
        raise ValueError("parent terminal decision drift")
    if transfer.get("d2h_store_complete") is not True:
        raise ValueError("parent D2H store gate drift")
    if transfer.get("d2h_completed_worker_count") != 8:
        raise ValueError("parent D2H worker count drift")
    if transfer.get("h2d_restore_complete") is not False:
        raise ValueError("parent H2D boundary drift")
    return {
        "schema_version": "p8_2_k1a_r5_f1_parent_replay_v1",
        "manifest_sha256": _sha256(manifest_path),
        "payload_file_count": len(checked),
        "payload_total_bytes": sum(int(row["bytes"]) for row in checked),
        "payloads_verified": True,
        "parent_grade": PARENT_GRADE,
        "request_count": 3,
        "pressure_request_count": 1,
        "d2h_store_complete": True,
        "h2d_restore_complete": False,
    }


def _request_windows(root: Path) -> list[dict[str, Any]]:
    control = root / "runtime/request_control"
    rows = _read_jsonl(control / "raw_request_results.jsonl")
    metrics = control / "raw_metrics"
    windows = []
    for row in rows:
        request_id = str(row.get("request_id") or "")
        role = str(row.get("k1a_role") or "")
        before = metrics / f"{request_id}_before.prom"
        after = metrics / f"{request_id}_after.prom"
        if not before.is_file() or not after.is_file():
            raise ValueError(f"raw request boundary missing: {request_id}")
        start = before.stat().st_mtime_ns
        end = after.stat().st_mtime_ns
        if start >= end:
            raise ValueError(f"invalid raw request boundary: {request_id}")
        windows.append(
            {
                "request_id": request_id,
                "role": role,
                "start_timestamp_ns": start,
                "end_timestamp_ns": end,
            }
        )
    if [row["role"] for row in windows] != [
        "warmup",
        "target_prime",
        "pressure_01",
    ]:
        raise ValueError("parent raw request role order drift")
    return windows


def _phase(timestamp_ns: int, windows: list[dict[str, Any]]) -> str:
    for index, window in enumerate(windows):
        if window["start_timestamp_ns"] <= timestamp_ns <= window["end_timestamp_ns"]:
            return str(window["role"])
        if index + 1 < len(windows):
            next_window = windows[index + 1]
            if window["end_timestamp_ns"] < timestamp_ns < next_window["start_timestamp_ns"]:
                return f"post_{window['role']}"
    return "outside_request_windows"


def build_pressure_window_attribution(root: Path) -> dict[str, Any]:
    windows = _request_windows(root)
    rows: list[dict[str, Any]] = []
    for path in sorted((root / "runtime/offload_trace").glob("h2d-residency.*.jsonl")):
        rows.extend(_read_jsonl(path))
    rows.sort(key=lambda row: int(row.get("timestamp_ns") or 0))
    if not rows:
        raise ValueError("R5-L1-R1 residency trace missing")
    forbidden_keys = {"block_hash", "block_hashes", "raw_hash_values"}
    if any(forbidden_keys.intersection(row) for row in rows):
        raise ValueError("raw target hash values were retained")
    for row in rows:
        row["phase"] = _phase(int(row.get("timestamp_ns") or 0), windows)
    captures = [
        row
        for row in rows
        if row.get("event") == "target_hashes_captured"
        and int(row.get("target_block_count") or 0) == 64
    ]
    snapshots = [
        row
        for row in rows
        if row.get("event") == "target_residency_snapshot"
        and int(row.get("target_block_count") or 0) == 64
    ]
    if not captures or not snapshots:
        raise ValueError("target capture or residency snapshots missing")
    target_rows = [
        row for row in snapshots if row["phase"] in {"target_prime", "post_target_prime"}
    ]
    pressure_rows = [row for row in snapshots if row["phase"] == "pressure_01"]
    if not target_rows or not pressure_rows:
        raise ValueError("target or pressure residency snapshots missing")
    target_terminal = target_rows[-1]
    target_terminal_cpu = int(target_terminal.get("cpu_target_block_count") or 0)
    target_terminal_gpu = int(target_terminal.get("gpu_target_block_count") or 0)
    if (target_terminal_cpu, target_terminal_gpu) != (0, 64):
        raise ValueError("target-prime residency drift: expected CPU=0 GPU=64")
    cpu_only = [
        row
        for row in pressure_rows
        if int(row.get("cpu_target_block_count") or 0) == 64
        and int(row.get("gpu_target_block_count") or 0) == 0
    ]
    cpu_evictions = [
        row
        for row in rows
        if row.get("event") == "target_cache_evicted"
        and row.get("tier") == "cpu"
    ]
    gpu_before = int(target_terminal.get("gpu_free_block_count") or 0)
    first_cpu_eviction_ns = min(
        (int(row.get("timestamp_ns") or 0) for row in cpu_evictions),
        default=None,
    )
    exact_before_cpu_eviction = [
        row
        for row in cpu_only
        if first_cpu_eviction_ns is None
        or int(row.get("timestamp_ns") or 0) < first_cpu_eviction_ns
    ]
    candidate_deltas = sorted(
        {
            gpu_before - int(row.get("gpu_free_block_count") or 0)
            for row in exact_before_cpu_eviction
        }
    )
    safe_window = len(candidate_deltas) == 1 and candidate_deltas[0] > 0
    first_exact = exact_before_cpu_eviction[0] if exact_before_cpu_eviction else {}
    return {
        "schema_version": "p8_2_k1a_r5_f1_pressure_window_attribution_v1",
        "request_windows": windows,
        "target_capture_count": len(captures),
        "target_prime_terminal_cpu_blocks": target_terminal_cpu,
        "target_prime_terminal_gpu_blocks": target_terminal_gpu,
        "pressure_snapshot_count": len(pressure_rows),
        "pressure_cpu_target_peak_blocks": max(
            int(row.get("cpu_target_block_count") or 0) for row in pressure_rows
        ),
        "pressure_gpu_target_min_blocks": min(
            int(row.get("gpu_target_block_count") or 0) for row in pressure_rows
        ),
        "pressure_cpu_only_exact_snapshot_count": len(cpu_only),
        "gpu_free_blocks_before_pressure": gpu_before,
        "gpu_free_blocks_at_first_exact_window": (
            int(first_exact.get("gpu_free_block_count") or 0)
            if first_exact
            else None
        ),
        "pressure_allocated_blocks_at_first_exact_window": (
            candidate_deltas[0] if safe_window else None
        ),
        "first_cpu_target_eviction_timestamp_ns": first_cpu_eviction_ns,
        "cpu_target_eviction_event_count": sum(
            int(row.get("target_evicted_count") or 0) for row in cpu_evictions
        ),
        "safe_pressure_window_proven": safe_window,
        "raw_hash_values_retained": False,
        "actual_cpu_eviction_proven": False,
    }


def inspect_source(manager_path: Path, block_pool_path: Path) -> dict[str, Any]:
    manager = manager_path.read_text(encoding="utf-8")
    block_pool = block_pool_path.read_text(encoding="utf-8")
    required = (
        "_prepare_lazy_store_specs",
        "find_longest_cache_hit",
        "popleft_n",
        "_maybe_evict_cached_block",
        "cached_block_hash_to_block.pop",
    )
    joined = manager + "\n" + block_pool
    missing = [value for value in required if value not in joined]
    if missing:
        raise ValueError("frozen source semantics missing: " + ", ".join(missing))
    return {
        "schema_version": "p8_2_k1a_r5_f1_frozen_source_semantics_v1",
        "manager_sha256": _sha256(manager_path),
        "block_pool_sha256": _sha256(block_pool_path),
        "lazy_store_path_present": True,
        "cpu_lookup_path_present": True,
        "free_block_queue_dequeue_method": "popleft_n",
        "cached_hash_eviction_path_present": True,
        "source_semantics_gate": "pass",
    }


def _write_manifest(output: Path, payloads: list[str]) -> None:
    files = {}
    for relative in payloads:
        path = output / relative
        files[relative] = {
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "sensitivity": SENSITIVITY,
        }
    _write_json(
        output / "candidate_manifest.server_local.json",
        {
            "schema_version": "p8_2_k1a_r5_f1_candidate_manifest_v1",
            "files": files,
            "payload_file_count": len(files),
            "payload_total_bytes": sum(row["bytes"] for row in files.values()),
            "max_total_bytes": 71680,
            "generated_content_retained": False,
            "token_ids_retained": False,
            "raw_hash_values_retained": False,
            "result_transfer_authorized": True,
            "transfer_method_selected": False,
            "automatic_transfer_allowed": False,
        },
    )


def analyze(args: argparse.Namespace) -> int:
    output = args.output_dir
    raw = args.raw_result_root.resolve()
    if output.exists():
        raise FileExistsError(f"output directory exists: {output}")
    if output.resolve() == raw or raw in output.resolve().parents:
        raise ValueError("output must be outside immutable raw result root")
    parent = verify_parent_package(args.parent_package)
    before = inventory_tree(args.raw_result_root)
    attribution = build_pressure_window_attribution(args.raw_result_root)
    source = inspect_source(args.manager_source, args.block_pool_source)
    after = inventory_tree(args.raw_result_root)
    if before != after:
        raise ValueError("raw source evidence changed during analysis")

    output.mkdir(parents=True)
    provenance = {
        "schema_version": "p8_2_k1a_r5_f1_raw_source_provenance_v1",
        "before": before,
        "after": after,
        "source_evidence_unchanged": True,
    }
    safe_window = attribution["safe_pressure_window_proven"] is True
    candidate_blocks = attribution[
        "pressure_allocated_blocks_at_first_exact_window"
    ]
    output_tokens = 64
    candidate_context = (
        int(candidate_blocks) * 128 - output_tokens if safe_window else None
    )
    candidate = {
        "schema_version": "p8_2_k1a_r5_f1_pressure_candidate_v1",
        "candidate_pressure_context_tokens": candidate_context,
        "candidate_pressure_total_blocks": candidate_blocks,
        "candidate_output_tokens": output_tokens,
        "candidate_is_fixed_not_search": safe_window,
        "formal_conditional_lifecycle_allowed": safe_window,
        "reason": (
            "one exact pre-eviction CPU=64 GPU=0 window and one free-block "
            "delta determine the fixed candidate"
            if safe_window
            else "no exact CPU=64 GPU=0 pressure snapshot was proven"
        ),
    }
    grade = READY_GRADE if safe_window else BLOCKED_GRADE
    grading = {
        "schema_version": "p8_2_k1a_r5_f1_grading_v1",
        "server_grade": grade,
        "claim_boundary": (
            "offline_parent_raw_trace_and_frozen_source_pressure_window_"
            "provenance_only_no_runtime_or_performance_claim"
        ),
        "parent_package_replay": "pass",
        "raw_source_evidence_unchanged": True,
        "frozen_source_semantics_gate": "pass",
        "safe_pressure_window_proven": safe_window,
        "formal_conditional_lifecycle_allowed": safe_window,
        "npu_started": False,
        "vllm_started": False,
        "model_request_sent": False,
        "keep_alive_disrupted": False,
        "actual_cpu_eviction_proven": False,
        "h2d_restore_mechanism_accepted": False,
        "cause_proven_as_unique": False,
        "performance_reference_accepted": False,
        "k2_authorized": False,
        "p8_3_i1_authorized": False,
        "next_task_authorized": False,
    }
    outputs = {
        "parent_package_replay.json": parent,
        "raw_source_provenance.json": provenance,
        "pressure_window_attribution.json": attribution,
        "frozen_source_semantics.json": source,
        "pressure_candidate.json": candidate,
        "grading_summary.json": grading,
    }
    for relative, value in outputs.items():
        _write_json(output / relative, value)
    (output / "task_grade.txt").write_text(grade + "\n", encoding="utf-8")
    (output / "result_summary.md").write_text(
        "\n".join(
            (
                "# P8.2-K1A-R5-F1 pressure-window provenance",
                "",
                f"- grade: `{grade}`",
                (
                    "- one fixed pressure candidate was derived without a search."
                    if safe_window
                    else "- existing raw trace has no exact CPU=64/GPU=0 pressure window."
                ),
                "- no NPU lifecycle, request, H2D acceptance or performance claim.",
                "",
            )
        ),
        encoding="utf-8",
    )
    payloads = [*outputs, "task_grade.txt", "result_summary.md"]
    _write_manifest(output, payloads)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    command = subparsers.add_parser("analyze")
    command.add_argument("--parent-package", type=Path, required=True)
    command.add_argument("--raw-result-root", type=Path, required=True)
    command.add_argument("--manager-source", type=Path, required=True)
    command.add_argument("--block-pool-source", type=Path, required=True)
    command.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "analyze":
        return analyze(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
