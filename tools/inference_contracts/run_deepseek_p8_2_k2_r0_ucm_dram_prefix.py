from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.run_deepseek_p6_1_unprofiled_baseline import (
    _process_alive,
    _stream_request,
)
from tools.inference_contracts.run_deepseek_p6_3b_prefix_cache_ab import (
    prepare_artifacts,
)


TASK_ID = "p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728"
CONTEXT_TOKENS = 32768
OUTPUT_TOKENS = 64
SENSITIVITY = "bounded_operational_metadata_no_content_or_token_ids"
UCM_COUNTERS = (
    "cache_lookup_hit_blocks_total",
    "cache_lookup_miss_blocks_total",
    "cache_load_blocks_total",
    "cache_dump_blocks_total",
    "cache_load_bytes_total",
    "cache_dump_bytes_total",
    "posix_s2h_bytes_total",
    "posix_h2s_bytes_total",
    "load_bytes_total",
    "save_bytes_total",
    "total_prefix_query_tokens_total",
    "gpu_hbm_hit_tokens_total",
    "ucm_hit_tokens_total",
    "total_prefix_query_blocks_total",
    "gpu_hbm_hit_blocks_total",
    "connector_lookup_errors_total",
    "connector_load_submit_errors_total",
    "connector_load_wait_errors_total",
    "connector_load_invalid_requests_total",
    "connector_load_invalid_blocks_total",
    "connector_dump_submit_errors_total",
    "connector_dump_wait_errors_total",
    "cache_h2d_errors_total",
    "cache_d2h_errors_total",
    "posix_open_errors_total",
    "posix_io_errors_total",
)
VLLM_COUNTERS = (
    "vllm:num_requests_running",
    "vllm:num_requests_waiting",
    "vllm:spec_decode_num_drafts_total",
    "vllm:spec_decode_num_draft_tokens_total",
    "vllm:spec_decode_num_accepted_tokens_total",
)
ERROR_COUNTERS = tuple(
    name
    for name in UCM_COUNTERS
    if "error" in name or "invalid" in name
)
PAYLOAD_NAMES = (
    "cleanup_status.txt",
    "dependency_and_environment_summary.json",
    "grading_summary.json",
    "request_summary.tsv",
    "resource_recovery_summary.json",
    "result_summary.md",
    "task_grade.txt",
    "ucm_metric_deltas.tsv",
    "ucm_path_summary.json",
)


def _plan() -> list[dict[str, Any]]:
    return [
        {
            "request_id": "k2_warmup",
            "group_id": "warmup_unrelated_4k",
            "request_role": "warmup",
            "repeat_index": 0,
            "context_tokens": 4096,
            "output_tokens": OUTPUT_TOKENS,
            "target_shared_prefix_ratio_pct": 0,
            "target_shared_prefix_tokens": 0,
        },
        {
            "request_id": "k2_prime",
            "group_id": "exact_reuse_32k",
            "request_role": "prime",
            "repeat_index": 0,
            "context_tokens": CONTEXT_TOKENS,
            "output_tokens": OUTPUT_TOKENS,
            "target_shared_prefix_ratio_pct": 100,
            "target_shared_prefix_tokens": CONTEXT_TOKENS,
        },
        {
            "request_id": "k2_follower",
            "group_id": "exact_reuse_32k",
            "request_role": "follower",
            "repeat_index": 1,
            "context_tokens": CONTEXT_TOKENS,
            "output_tokens": OUTPUT_TOKENS,
            "target_shared_prefix_ratio_pct": 100,
            "target_shared_prefix_tokens": CONTEXT_TOKENS,
        },
    ]


def prepare(source_payload: Path, artifact_dir: Path, model_name: str) -> None:
    manifest = prepare_artifacts(
        source_payload,
        artifact_dir,
        model_name,
        plan=_plan(),
        authorized_identical_body_request_ids=frozenset(
            {"k2_prime", "k2_follower"}
        ),
    )
    records = {
        str(row["request_id"]): row for row in manifest["records"]
    }
    prime = records["k2_prime"]
    follower = records["k2_follower"]
    if prime["request_body_sha256"] != follower["request_body_sha256"]:
        raise ValueError("K2 prime/follower body identity drift")
    if int(follower["actual_shared_prefix_tokens"]) != CONTEXT_TOKENS:
        raise ValueError("K2 follower does not exactly reuse the 32K prefix")
    manifest["task_id"] = TASK_ID
    manifest["internal_prefix_cache_enabled"] = False
    manifest["ucm_connector_enabled"] = True
    manifest["expected_external_reuse_tokens"] = CONTEXT_TOKENS
    manifest["claim_boundary"] = (
        "single_lifecycle_ucm_external_prefix_store_lookup_load_"
        "and_dram_first_path_observation"
    )
    (artifact_dir / "request_body_manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _get(base_url: str, route: str, timeout: float = 10.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(
            base_url.rstrip("/") + route, timeout=timeout
        ) as response:
            return int(response.status), response.read()
    except Exception:
        return 0, b""


def _parse_prometheus(raw: bytes) -> dict[str, float | bool]:
    values: dict[str, float | bool] = {
        **{f"ucm:{name}": 0.0 for name in UCM_COUNTERS},
        **{name: 0.0 for name in VLLM_COUNTERS},
    }
    found = {name: False for name in values}
    for raw_line in raw.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        name = parts[0].split("{", 1)[0]
        if name not in values:
            continue
        try:
            values[name] = float(values[name]) + float(parts[1])
            found[name] = True
        except ValueError:
            continue
    values["queue_metrics_present"] = all(
        found[name]
        for name in (
            "vllm:num_requests_running",
            "vllm:num_requests_waiting",
        )
    )
    values["spec_metrics_present"] = all(
        found[name]
        for name in VLLM_COUNTERS
        if "spec_decode" in name
    )
    values["ucm_metrics_present"] = any(
        found[f"ucm:{name}"] for name in UCM_COUNTERS
    )
    return values


def _snapshot(base_url: str, raw_path: Path) -> dict[str, Any]:
    status, raw = _get(base_url, "/metrics")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)
    return {
        **_parse_prometheus(raw),
        "http_status": status,
        "raw_server_path": str(raw_path),
    }


def _idle(snapshot: dict[str, Any]) -> bool:
    return (
        snapshot.get("http_status") == 200
        and snapshot.get("queue_metrics_present") is True
        and float(snapshot.get("vllm:num_requests_running") or 0) == 0
        and float(snapshot.get("vllm:num_requests_waiting") or 0) == 0
    )


def _wait_for_idle(
    base_url: str, raw_path: Path, timeout_seconds: float = 90.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _snapshot(base_url, raw_path)
        if _idle(last):
            return last
        time.sleep(0.5)
    return last


def _delta(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, float]:
    names = [f"ucm:{name}" for name in UCM_COUNTERS] + list(VLLM_COUNTERS)
    return {
        name: float(after.get(name) or 0) - float(before.get(name) or 0)
        for name in names
    }


def _metric_progress(
    role: str, delta: dict[str, float]
) -> bool:
    if role == "prime":
        return (
            delta["ucm:save_bytes_total"] > 0
            and delta["ucm:cache_dump_bytes_total"] > 0
        )
    if role == "follower":
        return (
            delta["ucm:ucm_hit_tokens_total"] > 0
            and delta["ucm:load_bytes_total"] > 0
            and delta["ucm:cache_load_bytes_total"] > 0
        )
    return True


def run(
    artifact_dir: Path,
    base_url: str,
    server_pid: int,
    server_log: Path,
) -> int:
    plan = json.loads(
        (artifact_dir / "run_plan.json").read_text(encoding="utf-8")
    )
    rows: list[dict[str, Any]] = []
    metrics_dir = artifact_dir / "runtime" / "raw_metrics"
    for item in plan:
        request_id = str(item["request_id"])
        before = _wait_for_idle(
            base_url, metrics_dir / f"{request_id}_before.prom"
        )
        log_start = server_log.stat().st_size if server_log.exists() else 0
        batch = {
            "batch_id": request_id,
            "phase": item["request_role"],
            "cell_id": item["group_id"],
            "context_tokens": item["context_tokens"],
            "output_tokens": item["output_tokens"],
            "concurrency": 1,
            "repeat_index": item["repeat_index"],
            "requests": [{**item, "request_index": 1}],
        }
        import threading

        request_row = _stream_request(
            artifact_dir=artifact_dir,
            base_url=base_url,
            server_pid=server_pid,
            batch=batch,
            request_item=batch["requests"][0],
            start_barrier=threading.Barrier(1),
        )
        after = _wait_for_idle(
            base_url, metrics_dir / f"{request_id}_after.prom"
        )
        delta = _delta(before, after)
        deadline = time.monotonic() + 60
        while (
            request_row.get("status") == "success"
            and not _metric_progress(str(item["request_role"]), delta)
            and time.monotonic() < deadline
        ):
            time.sleep(1)
            after = _snapshot(
                base_url, metrics_dir / f"{request_id}_after.prom"
            )
            delta = _delta(before, after)
        log_end = server_log.stat().st_size if server_log.exists() else log_start
        checks = {
            "server_alive_after": _process_alive(server_pid),
            "queue_idle_before": _idle(before),
            "queue_idle_after": _idle(after),
            "ucm_metrics_present": (
                before.get("ucm_metrics_present") is True
                or after.get("ucm_metrics_present") is True
            ),
            "role_metric_progress": _metric_progress(
                str(item["request_role"]), delta
            ),
        }
        if str(item["request_role"]) == "warmup":
            checks["role_metric_progress"] = True
        row = {
            **request_row,
            "request_role": item["request_role"],
            "metrics_before": before,
            "metrics_after": after,
            "counter_delta": delta,
            "server_log_start_byte": log_start,
            "server_log_end_byte": log_end,
            "checks": {**request_row.get("checks", {}), **checks},
            "generated_text_retained": False,
            "token_ids_retained": False,
        }
        if request_row.get("status") != "success" or not all(checks.values()):
            row["status"] = "failed"
        rows.append(row)
        raw_path = artifact_dir / "runtime" / "request_results.jsonl"
        raw_path.write_text(
            "".join(
                json.dumps(value, separators=(",", ":"), sort_keys=True)
                + "\n"
                for value in rows
            ),
            encoding="utf-8",
        )
        if row["status"] != "success":
            break
    return 0 if len(rows) == 3 and all(
        row["status"] == "success" for row in rows
    ) else 2


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _safe_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _role_row(rows: list[dict[str, Any]], role: str) -> dict[str, Any]:
    return next(
        (row for row in rows if row.get("request_role") == role), {}
    )


def _log_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "lookup_line_count": 0,
            "positive_external_lookup_line_count": 0,
            "max_logged_hbm_hit_blocks": 0,
            "max_logged_external_hit_blocks": 0,
        }
    pattern = re.compile(
        r"hit hbm:\s*(\d+).*?hit external:\s*(\d+)"
    )
    pairs = [
        (int(left), int(right))
        for left, right in pattern.findall(
            path.read_text(encoding="utf-8", errors="replace")
        )
    ]
    return {
        "lookup_line_count": len(pairs),
        "positive_external_lookup_line_count": sum(
            external > 0 for _, external in pairs
        ),
        "max_logged_hbm_hit_blocks": max(
            (hbm for hbm, _ in pairs), default=0
        ),
        "max_logged_external_hit_blocks": max(
            (external for _, external in pairs), default=0
        ),
    }


def _write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def finalize(artifact_dir: Path) -> str:
    rows = _read_rows(artifact_dir / "runtime" / "request_results.jsonl")
    prime = _role_row(rows, "prime")
    follower = _role_row(rows, "follower")
    prime_delta = prime.get("counter_delta") or {}
    follower_delta = follower.get("counter_delta") or {}
    recovery = _safe_json(artifact_dir / "resource_recovery_summary.json")
    cleanup = (
        (artifact_dir / "cleanup_status.txt")
        .read_text(encoding="utf-8")
        .strip()
        if (artifact_dir / "cleanup_status.txt").exists()
        else "unknown"
    )
    error_delta_total = sum(
        max(0.0, float(follower_delta.get(f"ucm:{name}") or 0.0))
        + max(0.0, float(prime_delta.get(f"ucm:{name}") or 0.0))
        for name in ERROR_COUNTERS
    )
    request_success_exact = (
        len(rows) == 3 and all(row.get("status") == "success" for row in rows)
    )
    prime_store_observed = (
        float(prime_delta.get("ucm:save_bytes_total") or 0) > 0
        and float(prime_delta.get("ucm:cache_dump_bytes_total") or 0) > 0
    )
    external_hit_observed = (
        float(follower_delta.get("ucm:ucm_hit_tokens_total") or 0) > 0
    )
    hbm_hit_absent_on_follower = (
        float(follower_delta.get("ucm:gpu_hbm_hit_tokens_total") or 0) == 0
    )
    cache_stage_hit_observed = (
        float(
            follower_delta.get("ucm:cache_lookup_hit_blocks_total") or 0
        )
        > 0
    )
    h2d_load_observed = (
        float(follower_delta.get("ucm:load_bytes_total") or 0) > 0
        and float(follower_delta.get("ucm:cache_load_bytes_total") or 0) > 0
    )
    posix_read_absent_on_follower = (
        float(follower_delta.get("ucm:posix_s2h_bytes_total") or 0) == 0
    )
    log_summary = _log_summary(
        artifact_dir / "runtime" / "vllm_server.log"
    )
    external_log_corroborated = (
        log_summary["positive_external_lookup_line_count"] > 0
    )
    recovery_exact = all(
        (
            recovery.get("stopped_card_ids") == list(range(8)),
            recovery.get("restored_card_ids") == list(range(8)),
            recovery.get("keep_alive_restored_exact") is True,
            recovery.get("port_7000_listener_count") == 0,
            recovery.get("vllm_residual_process_count") == 0,
            recovery.get("tracked_worktree_clean") is True,
        )
    )
    mechanism_implemented = all(
        (
            request_success_exact,
            prime_store_observed,
            external_hit_observed,
            hbm_hit_absent_on_follower,
            cache_stage_hit_observed,
            h2d_load_observed,
            posix_read_absent_on_follower,
            error_delta_total == 0,
            external_log_corroborated,
            cleanup == "clean",
            recovery_exact,
        )
    )
    if mechanism_implemented:
        grade = "implemented_p8_2_k2_r0_ucm_dram_external_prefix_path"
        path_class = "ucm_cache_store_dram_hit_then_h2d_load"
    elif external_hit_observed and h2d_load_observed:
        grade = "partial_p8_2_k2_r0_ucm_external_hit_non_dram_or_incomplete_recovery"
        path_class = "ucm_external_hit_with_non_dram_or_incomplete_evidence"
    elif not rows:
        grade = "blocked_p8_2_k2_r0_dependency_or_startup_preflight"
        path_class = "not_executed"
    else:
        grade = "incomplete_p8_2_k2_r0_ucm_external_prefix_path"
        path_class = "request_or_mechanism_incomplete"

    path_summary = {
        "task_id": TASK_ID,
        "path_class": path_class,
        "internal_prefix_cache_enabled": False,
        "ucm_connector_enabled": True,
        "request_success_exact": request_success_exact,
        "prime_store_observed": prime_store_observed,
        "external_hit_observed": external_hit_observed,
        "hbm_hit_absent_on_follower": hbm_hit_absent_on_follower,
        "cache_stage_hit_observed": cache_stage_hit_observed,
        "h2d_load_observed": h2d_load_observed,
        "posix_read_absent_on_follower": posix_read_absent_on_follower,
        "error_counter_delta_total": error_delta_total,
        "prime_save_bytes_delta": prime_delta.get("ucm:save_bytes_total", 0),
        "prime_cache_dump_bytes_delta": prime_delta.get(
            "ucm:cache_dump_bytes_total", 0
        ),
        "follower_ucm_hit_tokens_delta": follower_delta.get(
            "ucm:ucm_hit_tokens_total", 0
        ),
        "follower_gpu_hbm_hit_tokens_delta": follower_delta.get(
            "ucm:gpu_hbm_hit_tokens_total", 0
        ),
        "follower_cache_lookup_hit_blocks_delta": follower_delta.get(
            "ucm:cache_lookup_hit_blocks_total", 0
        ),
        "follower_load_bytes_delta": follower_delta.get(
            "ucm:load_bytes_total", 0
        ),
        "follower_cache_load_bytes_delta": follower_delta.get(
            "ucm:cache_load_bytes_total", 0
        ),
        "follower_posix_s2h_bytes_delta": follower_delta.get(
            "ucm:posix_s2h_bytes_total", 0
        ),
        "log_summary": log_summary,
        "mechanism_implemented": mechanism_implemented,
        "performance_benefit_required_for_mechanism_acceptance": False,
        "performance_result_interpretation": (
            "record_observed_latency_without_using_its_sign_as_a_path_gate"
        ),
        "claim_boundary": (
            "single_lifecycle_ucm_external_prefix_store_lookup_load_"
            "and_dram_first_path_observation"
        ),
    }
    (artifact_dir / "ucm_path_summary.json").write_text(
        json.dumps(path_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    request_summary_rows = [
        {
            "request_role": row.get("request_role"),
            "status": row.get("status"),
            "context_tokens": row.get("context_tokens"),
            "output_tokens": row.get("output_tokens"),
            "http_status": row.get("http_status"),
            "prompt_tokens": row.get("prompt_tokens"),
            "generated_token_count": row.get("generated_token_count"),
            "ttft_ms": row.get("ttft_ms"),
            "tpot_ms": row.get("tpot_ms"),
            "e2el_ms": row.get("e2el_ms"),
        }
        for row in rows
    ]
    _write_tsv(artifact_dir / "request_summary.tsv", request_summary_rows)
    metric_rows = []
    for role, row in (("prime", prime), ("follower", follower)):
        delta = row.get("counter_delta") or {}
        metric_rows.extend(
            {
                "request_role": role,
                "metric": name,
                "delta": delta.get(f"ucm:{name}", 0),
            }
            for name in UCM_COUNTERS
        )
    _write_tsv(artifact_dir / "ucm_metric_deltas.tsv", metric_rows)
    latencies = {
        role: {
            key: row.get(key)
            for key in ("ttft_ms", "tpot_ms", "itl_p95_ms", "e2el_ms")
        }
        for role, row in (("prime", prime), ("follower", follower))
        if row
    }
    grading = {
        "task_id": TASK_ID,
        "grade": grade,
        "mechanism_implemented": mechanism_implemented,
        "path_class": path_class,
        "request_count": len(rows),
        "successful_request_count": sum(
            row.get("status") == "success" for row in rows
        ),
        "request_retry_count": 0,
        "formal_model_lifecycle_count": (
            1
            if (artifact_dir / "runtime" / "server_pid.txt").is_file()
            else 0
        ),
        "latencies_descriptive_only": latencies,
        "performance_benefit_required": False,
        "performance_benefit_claimed": False,
        "unique_root_cause_required": False,
        "unique_root_cause_claimed": False,
        "cleanup_status": cleanup,
        "resource_recovery_exact": recovery_exact,
        "next_task_authorized": False,
        "k3_authorized": False,
        "p8_3_i1_authorized": False,
    }
    (artifact_dir / "grading_summary.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "task_grade.txt").write_text(
        grade + "\n", encoding="utf-8"
    )
    follower_ttft = follower.get("ttft_ms") if follower else None
    prime_ttft = prime.get("ttft_ms") if prime else None
    summary = (
        "# P8.2-K2-R0 UCM DRAM-first external prefix path\n\n"
        f"- grade: `{grade}`\n"
        f"- path: `{path_class}`\n"
        f"- requests: `{len(rows)}`; successful: "
        f"`{sum(row.get('status') == 'success' for row in rows)}`\n"
        f"- external hit tokens on follower: "
        f"`{path_summary['follower_ucm_hit_tokens_delta']}`\n"
        f"- follower cache-stage hit blocks: "
        f"`{path_summary['follower_cache_lookup_hit_blocks_delta']}`\n"
        f"- follower H2D load bytes: "
        f"`{path_summary['follower_load_bytes_delta']}`\n"
        f"- follower Posix S2H bytes: "
        f"`{path_summary['follower_posix_s2h_bytes_delta']}`\n"
        f"- observed TTFT prime/follower (descriptive): "
        f"`{prime_ttft}` / `{follower_ttft}` ms\n"
        "- acceptance is based on the implemented store→external lookup/hit"
        "→DRAM cache load path, not on the sign of a latency delta.\n"
        "- raw logs, metrics, request bodies, request IDs, token IDs and"
        " generated content remain server-local.\n"
    )
    (artifact_dir / "result_summary.md").write_text(
        summary, encoding="utf-8"
    )
    return grade


def package(artifact_dir: Path) -> None:
    entries = []
    for name in PAYLOAD_NAMES:
        path = artifact_dir / name
        if not path.is_file():
            raise FileNotFoundError(path)
        entries.append(
            {
                "relative_path": name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "sensitivity": SENSITIVITY,
            }
        )
    payload_total = sum(int(entry["bytes"]) for entry in entries)
    manifest = {
        "task_id": TASK_ID,
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "automatic_transfer_allowed": False,
        "available_methods": ["email", "upload-api", "server-local"],
        "recommended_method": "server-local",
        "recommended_method_reason": (
            "the bounded package is already on the server and contains only "
            "operational metadata; inspect the complete inventory before choice"
        ),
        "bounded_transfer_max_bytes": 71680,
        "payload_file_count": len(entries),
        "payload_total_bytes": payload_total,
        "transfer_file_count": len(entries) + 1,
        "manifest_bytes": 0,
        "transfer_total_bytes": 0,
        "files": entries,
        "raw_logs_metrics_request_bodies_and_generated_output_retained_server_local": True,
    }
    manifest_path = artifact_dir / "candidate_manifest.server_local.json"
    for _ in range(10):
        data = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        manifest_bytes = len(data.encode("utf-8"))
        transfer_total = payload_total + manifest_bytes
        if (
            manifest["manifest_bytes"] == manifest_bytes
            and manifest["transfer_total_bytes"] == transfer_total
        ):
            break
        manifest["manifest_bytes"] = manifest_bytes
        manifest["transfer_total_bytes"] = transfer_total
    else:
        raise RuntimeError("candidate manifest size did not converge")
    manifest_path.write_text(data, encoding="utf-8")
    total = payload_total + manifest_path.stat().st_size
    if total != manifest["transfer_total_bytes"]:
        raise ValueError("candidate manifest transfer size drift")
    if total > 71680:
        raise ValueError(f"bounded package exceeds 71680 bytes: {total}")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--source-payload", type=Path, required=True)
    prepare_parser.add_argument("--artifact-dir", type=Path, required=True)
    prepare_parser.add_argument("--model-name", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--artifact-dir", type=Path, required=True)
    run_parser.add_argument("--base-url", required=True)
    run_parser.add_argument("--server-pid", type=int, required=True)
    run_parser.add_argument("--server-log", type=Path, required=True)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--artifact-dir", type=Path, required=True)
    package_parser = subparsers.add_parser("package")
    package_parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.source_payload, args.artifact_dir, args.model_name)
        return 0
    if args.command == "run":
        return run(
            args.artifact_dir,
            args.base_url,
            args.server_pid,
            args.server_log,
        )
    if args.command == "finalize":
        finalize(args.artifact_dir)
        return 0
    if args.command == "package":
        package(args.artifact_dir)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
