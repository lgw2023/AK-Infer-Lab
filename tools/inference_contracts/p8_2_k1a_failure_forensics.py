from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.p8_2_k1a_simple_cpu_offload_observer import (
    summarize_trace_rows,
)


FORBIDDEN_CONTENT_KEYS = {
    "completion",
    "generated_text",
    "generated_output",
    "output_text",
    "prompt",
    "prompt_text",
    "prompt_token_ids",
    "text",
    "response_text",
    "token_arrival_ns",
    "token_ids",
}
TRACE_FIELDS = (
    "event",
    "component",
    "direction",
    "pid",
    "rank",
    "local_rank",
    "timestamp_ns",
    "event_idx",
    "event_hwm",
    "block_count",
    "byte_count",
    "sub_tensor_count",
    "request_id",
    "num_new_tokens",
    "is_async",
    "pending_event_count",
    "copy_thread_alive",
    "error_type",
    "error_message",
)
CANDIDATE_NAMES = (
    "result_summary.md",
    "failure_diagnostic_summary.json",
    "failed_request_sanitized.json",
    "transfer_trace_timeline.json",
    "vllm_first_failure_excerpt.txt",
    "source_evidence_provenance.json",
)
SENSITIVE_LINE_MARKERS = (
    "generated_text",
    "output_text",
    "prompt_token_ids",
    "token_arrival_ns",
    "token_ids",
)


def first_failed_predicate(row: dict[str, Any]) -> str | None:
    if row.get("status") != "success" and not row.get("checks"):
        return "status_success"
    for name, passed in (row.get("checks") or {}).items():
        if passed is not True:
            return str(name)
    return None if row.get("status") == "success" else "status_success"


def _sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_json(item)
            for key, item in value.items()
            if str(key).lower() not in FORBIDDEN_CONTENT_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_json(item) for item in value[:32]]
    if isinstance(value, str):
        return value[:2048]
    return value


def _resolve_error_path(artifact_dir: Path, row: dict[str, Any]) -> Path | None:
    candidates: list[Path] = []
    declared = row.get("bounded_error_server_path")
    if declared:
        candidates.append(Path(str(declared)))
    request_id = str(row.get("request_id") or "unknown")
    candidates.extend(
        artifact_dir / "request_errors" / f"{request_id}.{suffix}"
        for suffix in ("body", "txt")
    )
    root = artifact_dir.resolve()
    for path in candidates:
        try:
            resolved = path.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def _read_error_excerpt(path: Path | None) -> str:
    if path is None:
        return ""
    raw = path.read_bytes()[:8192]
    text = raw.decode("utf-8", errors="replace")
    try:
        sanitized = _sanitize_json(json.loads(text))
        return json.dumps(sanitized, ensure_ascii=False, sort_keys=True)[:4096]
    except json.JSONDecodeError:
        lines = [
            line
            for line in text.splitlines()
            if not any(marker in line.lower() for marker in SENSITIVE_LINE_MARKERS)
        ]
        return "\n".join(lines)[:4096]


def _classify_failure(
    row: dict[str, Any],
    trace_summary: dict[str, Any],
    error_excerpt: str,
) -> str:
    checks = row.get("checks") or {}
    http_status = row.get("http_status")
    if checks.get("server_alive") is False:
        return "server_process_exit"
    if int(trace_summary.get("transfer_failure_event_count") or 0) > 0:
        return "offload_runtime_exception"
    if (http_status is not None and http_status != 200) or error_excerpt:
        return "http_or_client_error"
    if checks.get("health_after_200") is False:
        return "request_health_loss_without_direct_exception"
    if (
        int(trace_summary.get("d2h_worker_count") or 0) > 0
        and int(trace_summary.get("d2h_completed_worker_count") or 0) == 0
    ):
        return "transfer_completion_absent_without_direct_exception"
    return "insufficient_parent_evidence"


def build_failure_diagnostic(
    artifact_dir: Path,
    rows: list[dict[str, Any]],
    trace_summary: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    failed = next((row for row in rows if row.get("status") != "success"), None)
    if failed is None:
        value = {
            "failed_request_id": None,
            "first_failed_predicate": None,
            "failure_classification": "none",
            "cause_proven_as_unique": False,
            "error_excerpt": "",
            "generated_content_retained": False,
            "token_ids_retained": False,
        }
        return value, "none\n"

    predicate = first_failed_predicate(failed)
    error_path = _resolve_error_path(artifact_dir, failed)
    error_excerpt = _read_error_excerpt(error_path)
    value = {
        "failed_request_id": failed.get("request_id"),
        "failed_request_role": failed.get("k1a_role"),
        "status": failed.get("status"),
        "http_status": failed.get("http_status"),
        "first_failed_predicate": predicate,
        "failed_predicates": [
            str(name)
            for name, passed in (failed.get("checks") or {}).items()
            if passed is not True
        ],
        "server_alive": (failed.get("checks") or {}).get("server_alive"),
        "health_after_200": (failed.get("checks") or {}).get("health_after_200"),
        "queue_idle_after": (failed.get("checks") or {}).get("queue_idle_after"),
        "d2h_worker_count": trace_summary.get("d2h_worker_count", 0),
        "d2h_completed_worker_count": trace_summary.get(
            "d2h_completed_worker_count", 0
        ),
        "transfer_failure_event_count": trace_summary.get(
            "transfer_failure_event_count", 0
        ),
        "failure_classification": _classify_failure(
            failed, trace_summary, error_excerpt
        ),
        "cause_proven_as_unique": False,
        "error_artifact_name": error_path.name if error_path else None,
        "error_excerpt": error_excerpt,
        "generated_content_retained": False,
        "token_ids_retained": False,
    }
    excerpt_lines = [
        f"failed_request_id={value['failed_request_id']}",
        f"first_failed_predicate={predicate}",
        f"failure_classification={value['failure_classification']}",
    ]
    if error_excerpt:
        excerpt_lines.append(f"error_excerpt={error_excerpt}")
    return value, "\n".join(excerpt_lines)[:8192] + "\n"


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_tree(root: Path) -> dict[str, Any]:
    records: list[str] = []
    total_bytes = 0
    symlink_count = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            symlink_count += 1
            records.append(f"L\t{relative}\t{path.readlink()}")
        elif path.is_file():
            size = path.stat().st_size
            total_bytes += size
            records.append(f"F\t{relative}\t{size}\t{_hash_file(path)}")
    aggregate = hashlib.sha256(("\n".join(records) + "\n").encode()).hexdigest()
    return {
        "file_count": sum(record.startswith("F\t") for record in records),
        "symlink_count": symlink_count,
        "total_bytes": total_bytes,
        "aggregate_sha256": aggregate,
    }


def _read_jsonl_files(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _sanitize_request_row(row: dict[str, Any]) -> dict[str, Any]:
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
        "request_body_sha256",
        "request_start_ns",
        "request_end_ns",
        "ttft_ms",
        "tpot_ms",
        "e2el_ms",
        "prefix_hits_delta",
        "accepted_token_delta",
        "queue_metrics_ok",
        "counter_continuity_ok",
        "spec_activity_ok",
        "checks",
    )
    sanitized = {name: _sanitize_json(row.get(name)) for name in fields if name in row}
    sanitized["first_failed_predicate"] = first_failed_predicate(row)
    sanitized["metrics_before"] = {
        name: row.get("metrics_before", {}).get(name)
        for name in (
            "num_requests_running",
            "num_requests_waiting",
            "num_drafts",
            "num_draft_tokens",
            "num_accepted_tokens",
            "prefix_queries",
            "prefix_hits",
        )
    }
    sanitized["metrics_after"] = {
        name: row.get("metrics_after", {}).get(name)
        for name in sanitized["metrics_before"]
    }
    sanitized["generated_content_retained"] = False
    sanitized["token_ids_retained"] = False
    return sanitized


def _trace_timeline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    events = [
        {name: _sanitize_json(row[name]) for name in TRACE_FIELDS if name in row}
        for row in rows
    ]
    events.sort(
        key=lambda row: (
            int(row.get("timestamp_ns") or 0),
            int(row.get("pid") or 0),
        )
    )
    return {
        "event_count": len(events),
        "events": events,
        "generated_content_retained": False,
        "token_ids_retained": False,
    }


def _bounded_log_excerpt(path: Path) -> str:
    if not path.is_file():
        return "no_vllm_log\n"
    pattern = re.compile(
        r"error|exception|traceback|failed|timeout|offload|d2h|h2d|copy|acl",
        re.IGNORECASE,
    )
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    selected: set[int] = set()
    for index, line in enumerate(lines):
        if pattern.search(line):
            selected.update(range(max(0, index - 2), min(len(lines), index + 3)))
    output: list[str] = []
    for index in sorted(selected):
        line = lines[index]
        if any(marker in line.lower() for marker in SENSITIVE_LINE_MARKERS):
            continue
        output.append(f"{index + 1}: {line[:2048]}")
    text = "\n".join(output)
    return (text[:16383] + "\n") if text else "no_matching_failure_lines\n"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _function_parameters(
    tree: ast.AST,
    function_name: str,
    *,
    class_name: str | None = None,
) -> list[str]:
    nodes: list[ast.AST] = list(ast.walk(tree))
    if class_name is not None:
        classes = [
            node
            for node in nodes
            if isinstance(node, ast.ClassDef) and node.name == class_name
        ]
        nodes = list(ast.walk(classes[0])) if classes else []
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return [
                argument.arg
                for argument in (
                    list(node.args.posonlyargs)
                    + list(node.args.args)
                    + list(node.args.kwonlyargs)
                )
            ]
    return []


def extract_existing_evidence(source_result_dir: Path, output_dir: Path) -> dict[str, Any]:
    if not source_result_dir.is_dir():
        raise ValueError(f"source result directory does not exist: {source_result_dir}")
    if output_dir.exists():
        raise ValueError(f"output directory already exists: {output_dir}")
    before = inventory_tree(source_result_dir)
    request_path = (
        source_result_dir / "modes/prefix_cache_on/raw_request_results.jsonl"
    )
    if not request_path.is_file():
        raise ValueError(f"raw request evidence missing: {request_path}")
    rows = _read_jsonl_files([request_path])
    failed = next((row for row in rows if row.get("status") != "success"), None)
    if failed is None:
        raise ValueError("parent evidence has no failed request")
    trace_paths = sorted(
        (source_result_dir / "runtime/offload_trace").glob("trace.*.jsonl")
    )
    trace_rows = _read_jsonl_files(trace_paths)
    trace_summary = summarize_trace_rows(
        trace_rows, expected_world_size=8, restore_request_suffix="restore_follower"
    )
    diagnostic, _ = build_failure_diagnostic(
        source_result_dir, rows, trace_summary
    )
    allowed_classes = {
        "request_health_loss_without_direct_exception",
        "transfer_completion_absent_without_direct_exception",
        "insufficient_parent_evidence",
    }
    diagnostic["formal_replay_allowed"] = (
        diagnostic["failure_classification"] in allowed_classes
    )
    diagnostic["formal_replay_requires_new_task_authorization"] = True
    diagnostic["parent_trace_summary"] = trace_summary

    output_dir.mkdir(parents=True)
    _write_json(output_dir / "failure_diagnostic_summary.json", diagnostic)
    _write_json(
        output_dir / "failed_request_sanitized.json",
        _sanitize_request_row(failed),
    )
    _write_json(
        output_dir / "transfer_trace_timeline.json", _trace_timeline(trace_rows)
    )
    (output_dir / "vllm_first_failure_excerpt.txt").write_text(
        _bounded_log_excerpt(source_result_dir / "runtime/vllm_server.log"),
        encoding="utf-8",
    )
    after = inventory_tree(source_result_dir)
    provenance = {
        "source_result_dir": str(source_result_dir),
        "before": before,
        "after": after,
        "source_evidence_unchanged": before == after,
        "generated_content_retained": False,
        "token_ids_retained": False,
    }
    _write_json(output_dir / "source_evidence_provenance.json", provenance)
    (output_dir / "result_summary.md").write_text(
        "\n".join(
            (
                "# P8.2-K1A parent failure forensics",
                "",
                f"- failed_request_id: `{diagnostic['failed_request_id']}`",
                f"- first_failed_predicate: `{diagnostic['first_failed_predicate']}`",
                f"- failure_classification: `{diagnostic['failure_classification']}`",
                f"- formal_replay_allowed: `{str(diagnostic['formal_replay_allowed']).lower()}`",
                f"- source_evidence_unchanged: `{str(before == after).lower()}`",
                "- claim_boundary: offline existing raw evidence forensics only; no runtime or performance claim.",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    files = {
        name: {
            "bytes": (output_dir / name).stat().st_size,
            "sha256": _hash_file(output_dir / name),
            "sensitivity": "bounded_operational_metadata_no_content_or_token_ids",
        }
        for name in CANDIDATE_NAMES
        if (output_dir / name).is_file()
    }
    missing = [name for name in CANDIDATE_NAMES if name not in files]
    total = sum(value["bytes"] for value in files.values())
    if missing:
        raise ValueError(f"missing candidate files: {missing}")
    if total > 71680 or any(value["bytes"] > 71680 for value in files.values()):
        raise ValueError(f"candidate package exceeds 70KB: {total}")
    manifest = {
        "schema_version": "p8_2_k1a_failure_forensics_manifest_v1",
        "files": files,
        "missing_candidate_files": missing,
        "candidate_file_count": len(files),
        "candidate_total_bytes": total,
        "max_total_bytes": 71680,
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "automatic_transfer_allowed": False,
    }
    _write_json(output_dir / "candidate_manifest.server_local.json", manifest)
    return {
        "failure_classification": diagnostic["failure_classification"],
        "formal_replay_allowed": diagnostic["formal_replay_allowed"],
        "source_evidence_unchanged": before == after,
        "candidate_total_bytes": total,
    }


def audit_source_semantics(
    vllm_root: Path,
    vllm_ascend_root: Path,
    output: Path,
) -> dict[str, Any]:
    definitions = {
        "vllm_scheduler": (
            vllm_root / "v1/simple_kv_offload/manager.py",
            {
                "SimpleCPUOffloadScheduler",
                "SimpleCPUOffloadScheduler.get_num_new_matched_tokens",
                "SimpleCPUOffloadScheduler.build_connector_meta",
                "SimpleCPUOffloadScheduler.update_connector_output",
            },
        ),
        "vllm_worker": (
            vllm_root / "v1/simple_kv_offload/worker.py",
            {
                "SimpleCPUOffloadWorker",
                "SimpleCPUOffloadWorker._poll_stream_events",
            },
        ),
        "ascend_worker": (
            vllm_ascend_root / "simple_kv_offload/worker.py",
            {"SimpleCPUOffloadNPUWorker"},
        ),
        "ascend_copy_backend": (
            vllm_ascend_root / "simple_kv_offload/copy_backend.py",
            {
                "NPUDmaCopyBackend",
                "NPUDmaCopyBackend._copy_loop",
                "NPUDmaCopyBackend.launch_copy",
            },
        ),
        "ascend_npu_mem_ops": (
            vllm_ascend_root / "simple_kv_offload/npu_mem_ops.py",
            {"copy_blocks"},
        ),
        "ascend_connector": (
            vllm_ascend_root
            / "distributed/kv_transfer/kv_pool/simple_cpu_offload/"
            "simple_cpu_offload_connector.py",
            {"AscendSimpleCPUOffloadConnector"},
        ),
    }
    files: dict[str, Any] = {}
    parsed_trees: dict[str, ast.Module] = {}
    all_required_present = True
    for label, (path, required) in definitions.items():
        if not path.is_file():
            files[label] = {"path": str(path), "exists": False, "missing": sorted(required)}
            all_required_present = False
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parsed_trees[label] = tree
        symbols: set[str] = set()
        for node in tree.body:
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            symbols.add(node.name)
            if isinstance(node, ast.ClassDef):
                symbols.update(
                    f"{node.name}.{child.name}"
                    for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                )
        missing = sorted(required - symbols)
        all_required_present &= not missing
        files[label] = {
            "path": str(path),
            "exists": True,
            "bytes": path.stat().st_size,
            "sha256": _hash_file(path),
            "required_symbols": sorted(required),
            "missing_symbols": missing,
        }

    ascend_worker_tree = parsed_trees.get("ascend_worker")
    derived_bases: set[str] = set()
    if ascend_worker_tree is not None:
        for node in ascend_worker_tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "SimpleCPUOffloadNPUWorker":
                derived_bases.update(
                    base.id
                    for base in node.bases
                    if isinstance(base, ast.Name)
                )
    inheritance_resolved = all(
        (
            "SimpleCPUOffloadWorker" in derived_bases,
            not files.get("vllm_worker", {}).get("missing_symbols"),
        )
    )
    all_required_present &= inheritance_resolved
    inheritance_resolution = {
        "base_class": "SimpleCPUOffloadWorker",
        "base_method": "SimpleCPUOffloadWorker._poll_stream_events",
        "derived_class": "SimpleCPUOffloadNPUWorker",
        "derived_class_inherits_base": "SimpleCPUOffloadWorker" in derived_bases,
        "method_resolution": (
            "inherited_from_frozen_vllm" if inheritance_resolved else "unresolved"
        ),
        "resolved": inheritance_resolved,
    }
    copy_binding = {
        "binding_imported_name": None,
        "binding_kind": None,
        "binding_local_name": None,
        "binding_module": None,
        "definition_label": "ascend_npu_mem_ops",
        "definition_present": not files.get("ascend_npu_mem_ops", {}).get(
            "missing_symbols", ["copy_blocks"]
        ),
        "resolved": False,
        "symbol": "copy_blocks",
    }
    copy_backend_tree = parsed_trees.get("ascend_copy_backend")
    if copy_backend_tree is not None:
        for node in copy_backend_tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            for alias in node.names:
                local_name = alias.asname or alias.name
                if local_name != "copy_blocks":
                    continue
                copy_binding.update(
                    {
                        "binding_imported_name": alias.name,
                        "binding_kind": "import_from",
                        "binding_local_name": local_name,
                        "binding_module": node.module,
                    }
                )
    copy_binding["resolved"] = all(
        (
            copy_binding["binding_imported_name"] == "copy_blocks",
            copy_binding["binding_kind"] == "import_from",
            copy_binding["binding_local_name"] == "copy_blocks",
            copy_binding["binding_module"]
            == "vllm_ascend.simple_kv_offload.npu_mem_ops",
            copy_binding["definition_present"],
        )
    )
    all_required_present &= copy_binding["resolved"]
    frozen_launch_parameters = _function_parameters(
        parsed_trees.get("ascend_copy_backend", ast.Module(body=[], type_ignores=[])),
        "launch_copy",
        class_name="NPUDmaCopyBackend",
    )
    observer_tree = ast.parse(
        (
            REPO_ROOT
            / "tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py"
        ).read_text(encoding="utf-8")
    )
    observer_launch_parameters = _function_parameters(
        observer_tree, "observed_launch"
    )
    observer_extra_parameters = sorted(
        set(observer_launch_parameters) - set(frozen_launch_parameters)
    )
    observer_signature_compatible = (
        observer_launch_parameters == frozen_launch_parameters
    )
    all_required_present &= observer_signature_compatible
    frozen_launch_signature = {
        "parameters": frozen_launch_parameters,
        "observer_extra_parameters": observer_extra_parameters,
        "observer_signature_compatible": observer_signature_compatible,
    }
    value = {
        "schema_version": "p8_2_k1a_source_semantics_audit_v3",
        "source_semantics_gate": "pass" if all_required_present else "fail",
        "source_file_count": sum(row.get("exists") is True for row in files.values()),
        "required_symbols_present": all_required_present,
        "inheritance_resolution": inheritance_resolution,
        "copy_primitive_resolution": copy_binding,
        "frozen_launch_signature": frozen_launch_signature,
        "observer_surface": {
            "scheduler_match": (
                "SimpleCPUOffloadScheduler.get_num_new_matched_tokens"
            ),
            "scheduler_schedule": "SimpleCPUOffloadScheduler.build_connector_meta",
            "scheduler_completion": (
                "SimpleCPUOffloadScheduler.update_connector_output"
            ),
            "copy_backend_enqueue": "NPUDmaCopyBackend.launch_copy",
            "copy_backend_worker_loop": "NPUDmaCopyBackend._copy_loop",
            "copy_primitive": "copy_blocks",
            "worker_completion": "SimpleCPUOffloadNPUWorker._poll_stream_events",
        },
        "files": files,
        "audit_only_no_source_mutation": True,
        "npu_started": False,
        "vllm_server_started": False,
        "model_request_sent": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, value)
    return value


def audit_runtime_log(log_path: Path, output: Path) -> dict[str, Any]:
    if not log_path.is_file():
        raise ValueError(f"runtime log does not exist: {log_path}")
    before = {"bytes": log_path.stat().st_size, "sha256": _hash_file(log_path)}
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    exception_pattern = re.compile(
        r"(?P<type>[A-Za-z_][\w.]*(?:Error|Exception)):\s*(?P<message>.*)$"
    )
    frame_pattern = re.compile(
        r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<function>[^\s]+)'
    )
    exceptions: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        match = exception_pattern.search(line)
        if match is None:
            continue
        exception_type = match.group("type").rsplit(".", 1)[-1]
        message = " ".join(match.group("message").split())
        lower_message = message.lower()
        known_wait_event_defect = exception_type == "TypeError" and (
            (
                "launch_copy" in lower_message
                and "takes 6 positional arguments but 7 were given" in lower_message
            )
            or (
                "launch_copy" in lower_message
                and "unexpected keyword argument" in lower_message
                and "wait_event" in lower_message
            )
        )
        frame_matches = []
        for frame_line in lines[max(0, index - 32) : index]:
            frame = frame_pattern.search(frame_line)
            if frame is None:
                continue
            frame_matches.append(
                {
                    "file": Path(frame.group("file")).name,
                    "function": frame.group("function"),
                    "line": int(frame.group("line")),
                }
            )
        exceptions.append(
            {
                "callsite_frames": frame_matches[-6:],
                "exception_type": exception_type,
                "known_retired_observer_defect_match": known_wait_event_defect,
                "line_number": index + 1,
                "message_pattern": (
                    "launch_copy_extra_positional_wait_event"
                    if known_wait_event_defect
                    else "unrecognized_runtime_exception"
                ),
                "normalized_message_sha256": hashlib.sha256(
                    message.encode("utf-8")
                ).hexdigest(),
            }
        )
    known_count = sum(
        row["known_retired_observer_defect_match"] for row in exceptions
    )
    unknown_count = len(exceptions) - known_count
    if not exceptions:
        gate = "pass_no_direct_runtime_exception"
    elif unknown_count == 0:
        gate = "pass_known_retired_observer_defect"
    else:
        gate = "fail_unknown_runtime_exception"
    after = {"bytes": log_path.stat().st_size, "sha256": _hash_file(log_path)}
    value = {
        "schema_version": "p8_2_k1a_runtime_exception_provenance_v1",
        "runtime_log_gate": gate,
        "formal_lifecycle_runtime_log_condition": gate.startswith("pass_"),
        "direct_runtime_exception_present": bool(exceptions),
        "exception_count": len(exceptions),
        "known_retired_observer_wait_event_defect_count": known_count,
        "unknown_runtime_exception_count": unknown_count,
        "traceback_marker_count": sum(
            "Traceback (most recent call last)" in line for line in lines
        ),
        "exceptions": exceptions[:32],
        "exception_records_truncated": len(exceptions) > 32,
        "source_log_before": before,
        "source_log_after": after,
        "source_log_unchanged": before == after,
        "generated_content_retained": False,
        "token_ids_retained": False,
        "npu_started": False,
        "vllm_server_started": False,
        "model_request_sent": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, value)
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    extract = subparsers.add_parser("extract")
    extract.add_argument("--source-result-dir", type=Path, required=True)
    extract.add_argument("--output-dir", type=Path, required=True)
    source_audit = subparsers.add_parser("source-audit")
    source_audit.add_argument("--vllm-root", type=Path, required=True)
    source_audit.add_argument("--vllm-ascend-root", type=Path, required=True)
    source_audit.add_argument("--output", type=Path, required=True)
    runtime_log_audit = subparsers.add_parser("runtime-log-audit")
    runtime_log_audit.add_argument("--log", type=Path, required=True)
    runtime_log_audit.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "source-audit":
        result = audit_source_semantics(
            args.vllm_root, args.vllm_ascend_root, args.output
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["source_semantics_gate"] == "pass" else 2
    if args.command == "runtime-log-audit":
        result = audit_runtime_log(args.log, args.output)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["runtime_log_gate"].startswith("pass_") else 2
    result = extract_existing_evidence(args.source_result_dir, args.output_dir)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
