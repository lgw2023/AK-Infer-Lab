from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable


TASK_ID = "p8_2_k2_r0_run03_fawa_startup_attribution_2026_0729"
RUN_ID = f"{TASK_ID}_run01"
PARENT_TASK_ID = "p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728"
PARENT_RUN_BASENAME = f"{PARENT_TASK_ID}_run03"
UCM_COMMIT = "01cbf9b71892c88319862fa57f195b0bef93fa6f"
PARENT_MANIFEST_SHA256 = (
    "a278c44dbf879c42fe2119ca8a7708b7bc0aea8103e4387af1ff3c73b974cbe4"
)
PARENT_MANIFEST_BYTES = 3434
MAX_TRANSFER_BYTES = 71680
MAX_EXCERPT_BYTES = 18000
SENSITIVITY = "bounded_operational_metadata_no_content_or_token_ids"
PAYLOAD_NAMES = (
    "fawa_store_geometry.json",
    "grading_summary.json",
    "parent_provenance.json",
    "resource_observation_summary.json",
    "result_summary.md",
    "source_constructor_lineage.json",
    "startup_exception_summary.json",
    "startup_traceback_excerpt.txt",
    "task_grade.txt",
)

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
FRAME_RE = re.compile(r'File "([^"]+)", line ([0-9]+), in ([A-Za-z_][A-Za-z0-9_<>.]*)')
EXCEPTION_RE = re.compile(
    r"(?P<type>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Failure))"
    r":\s*(?P<message>.+)$"
)
STORE_CONFIG_RE = re.compile(r"create FAWA\s+(FA|WA)\s+(\S+)\s+with config:\s*(\{.*\})")
SAFE_STORE_KEYS = (
    "block_size",
    "cache_buffer_capacity_gb",
    "cache_load_exclusive_buffer_number",
    "device_id",
    "enable_metrics",
    "io_direct",
    "local_rank_size",
    "posix_capacity_gb",
    "posix_gc_enable",
    "share_buffer_enable",
    "shard_size",
    "store_pipeline",
    "tensor_bytes",
    "tensor_count",
    "unique_id",
    "use_gdr",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _run_output(command: list[str]) -> str:
    return subprocess.check_output(
        command,
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def _bounded_text(value: object, limit: int = 1200) -> str:
    text = str(value).replace("\x00", "")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _sanitize_line(line: str) -> str:
    line = ANSI_RE.sub("", line).replace("\x00", "")
    line = re.sub(
        r"(?i)(request[_ -]?id\s*[:=]\s*)[^\s,;]+",
        r"\1<redacted>",
        line,
    )
    line = re.sub(
        r"(?i)(token[_ -]?ids?\s*[:=]\s*)\[[^\]]*\]",
        r"\1<redacted>",
        line,
    )
    line = re.sub(
        r"(?i)((?:prompt|generated_text|output_text)\s*[:=]\s*)"
        r"(['\"]).*?\2",
        r"\1<redacted>",
        line,
    )
    return _bounded_text(line, 1600)


def _display_path(raw: str, source_root: Path) -> str:
    path = Path(raw)
    try:
        return f"<ucm-source>/{path.relative_to(source_root)}"
    except ValueError:
        pass
    marker = "/site-packages/"
    if marker in raw:
        return f"<site-packages>/{raw.split(marker, 1)[1]}"
    return f"<runtime>/{path.name}"


def validate_parent(
    parent_result_dir: Path,
    *,
    expected_manifest_sha256: str = PARENT_MANIFEST_SHA256,
    expected_manifest_bytes: int = PARENT_MANIFEST_BYTES,
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    if parent_result_dir.name != PARENT_RUN_BASENAME:
        raise ValueError(f"parent basename mismatch: {parent_result_dir.name}")
    manifest_path = parent_result_dir / "candidate_manifest.server_local.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    if manifest_path.stat().st_size != expected_manifest_bytes:
        raise ValueError("parent manifest byte count mismatch")
    if _sha256(manifest_path) != expected_manifest_sha256:
        raise ValueError("parent manifest SHA-256 mismatch")
    manifest = _json(manifest_path)
    if manifest.get("task_id") != PARENT_TASK_ID:
        raise ValueError("parent task id mismatch")
    if manifest.get("payload_file_count") != len(manifest.get("files", [])):
        raise ValueError("parent manifest file count mismatch")

    verified_files: list[dict[str, Any]] = []
    for entry in manifest.get("files", []):
        relative = str(entry["relative_path"])
        if "/" in relative or relative.startswith("."):
            raise ValueError(f"unsafe parent payload path: {relative}")
        path = parent_result_dir / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        actual_bytes = path.stat().st_size
        actual_sha256 = _sha256(path)
        if actual_bytes != int(entry["bytes"]):
            raise ValueError(f"parent payload bytes mismatch: {relative}")
        if actual_sha256 != str(entry["sha256"]):
            raise ValueError(f"parent payload SHA-256 mismatch: {relative}")
        verified_files.append(
            {
                "relative_path": relative,
                "bytes": actual_bytes,
                "sha256": actual_sha256,
                "matches_parent_manifest": True,
            }
        )

    grading = _json(parent_result_dir / "grading_summary.json")
    startup = _json(parent_result_dir / "startup_failure_summary.json")
    capacity = _json(parent_result_dir / "startup_capacity_summary.json")
    expected_parent = {
        "grade": "blocked_p8_2_k2_r0_lifecycle_startup",
        "path_class": "lifecycle_startup_failed_before_requests",
        "startup_class": "lifecycle_startup_failed_other",
        "formal_model_lifecycle_count": 1,
        "request_count": 0,
    }
    for key, expected in expected_parent.items():
        if grading.get(key) != expected:
            raise ValueError(f"parent grading mismatch for {key}")
    if startup.get("ucm_too_small_buffer_observed") is not False:
        raise ValueError("run03 unexpectedly repeated run02 buffer failure")
    if capacity.get("status") != "ready":
        raise ValueError("parent startup capacity was not ready")

    raw_log = parent_result_dir / "runtime" / "vllm_server.log"
    if not raw_log.is_file() or raw_log.stat().st_size <= 0:
        raise FileNotFoundError(raw_log)
    raw_stat = raw_log.stat()
    provenance = {
        "parent_task_id": PARENT_TASK_ID,
        "parent_run_basename": PARENT_RUN_BASENAME,
        "parent_result_dir": str(parent_result_dir),
        "parent_manifest_bytes": manifest_path.stat().st_size,
        "parent_manifest_sha256": _sha256(manifest_path),
        "parent_manifest_matches_frozen_input": True,
        "parent_payload_file_count": len(verified_files),
        "parent_payload_total_bytes": sum(item["bytes"] for item in verified_files),
        "parent_payloads_all_match_manifest": True,
        "parent_payloads": verified_files,
        "parent_grade": grading["grade"],
        "parent_path_class": grading["path_class"],
        "parent_startup_class": grading["startup_class"],
        "parent_dependency_status": grading["dependency_status"],
        "parent_startup_capacity_status": grading["startup_capacity_status"],
        "parent_formal_model_lifecycle_count": 1,
        "parent_request_count": 0,
        "parent_raw_log_path": str(raw_log),
        "parent_raw_log_bytes": raw_stat.st_size,
        "parent_raw_log_mtime_ns_before": raw_stat.st_mtime_ns,
        "parent_raw_log_hash_retained": False,
        "parent_raw_log_read_only": True,
    }
    return provenance, raw_log, capacity


def collect_source_lineage(source_root: Path) -> dict[str, Any]:
    source_head = _run_output(["git", "-C", str(source_root), "rev-parse", "HEAD"])
    source_status = _run_output(
        [
            "git",
            "-C",
            str(source_root),
            "status",
            "--porcelain",
            "--untracked-files=no",
        ]
    )
    if source_head != UCM_COMMIT:
        raise ValueError(f"pinned UCM HEAD mismatch: {source_head}")
    if source_status:
        raise ValueError("pinned UCM tracked worktree is dirty")

    ucm_connector = source_root / "ucm/integration/vllm/ucm_connector.py"
    hma_connector = source_root / "ucm/integration/vllm/hma_connector.py"
    cache_store = source_root / "ucm/store/cache/cc/cache_store.cc"
    for path in (ucm_connector, hma_connector, cache_store):
        if not path.is_file():
            raise FileNotFoundError(path)

    source = hma_connector.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions: dict[str, dict[str, int]] = {}
    constructor_calls: list[dict[str, Any]] = []
    fawa_class = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "UCMFAWAConnector"
        ),
        None,
    )
    if fawa_class is None:
        raise ValueError("UCMFAWAConnector class not found in pinned source")
    for node in fawa_class.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in {
                "__init__",
                "_init_group_metas",
                "_create_fa_store",
                "_create_wa_store",
                "_base_store_config",
                "_set_default_shm_buffer_capacity",
                "_create_store",
                "register_kv_caches",
            }:
                functions[node.name] = {
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                }
            if node.name == "__init__":
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Attribute)
                        and child.func.attr
                        in {
                            "_init_group_metas",
                            "_create_fa_store",
                            "_create_wa_store",
                        }
                    ):
                        constructor_calls.append(
                            {"call": child.func.attr, "line": child.lineno}
                        )
    constructor_calls.sort(key=lambda item: item["line"])

    semantics = {
        "outer_dispatch_instantiates_fawa_at_ucm_connector_line_2669": (
            "self.connector = UCMFAWAConnector(vllm_config, role, kv_cache_config)"
            in ucm_connector.read_text(encoding="utf-8")
        ),
        "scheduler_constructs_fa_then_wa": (
            "self.store = self._create_fa_store(None)" in source
            and "self.wa_store = self._create_wa_store(None)" in source
            and source.index("self.store = self._create_fa_store(None)")
            < source.index("self.wa_store = self._create_wa_store(None)")
        ),
        "base_config_deep_copied_per_store": (
            'copy.deepcopy(self.connector_configs[0]["ucm_connector_config"])' in source
        ),
        "explicit_cache_capacity_bypasses_default_split": (
            'if config.get("cache_buffer_capacity_gb") is not None:' in source
            and 'config["cache_buffer_capacity_gb"] = 128 // 2' in source
        ),
        "store_config_logged_before_factory_create": (
            source.index("create FAWA {label}")
            < source.index("UcmConnectorFactoryV1.create_connector")
        ),
        "worker_geometry_sets_shard_and_block_to_padded_tensor_sum": (
            'config["shard_size"] = padded_size' in source
            and 'config["block_size"] = padded_size' in source
        ),
        "cache_size_gate_skips_scheduler_device_minus_one": (
            "if (config.deviceId == -1) { return Status::OK(); }"
            in cache_store.read_text(encoding="utf-8")
        ),
    }
    if not all(semantics.values()):
        raise ValueError("pinned FAWA constructor semantics drifted")

    return {
        "ucm_source_root": str(source_root),
        "ucm_source_head": source_head,
        "ucm_source_tracked_clean": source_status == "",
        "ucm_expected_commit": UCM_COMMIT,
        "source_files": {
            str(path.relative_to(source_root)): {
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in (ucm_connector, hma_connector, cache_store)
        },
        "hma_constructor_function_lines": functions,
        "hma_constructor_calls": constructor_calls,
        "constructor_semantics": semantics,
        "constructor_order": [
            "UCMFAWAConnector.__init__",
            "_init_group_metas",
            "scheduler:_create_fa_store",
            "scheduler:_create_wa_store",
            "worker:register_kv_caches_then_create_fa_and_wa_stores",
        ],
        "capacity_semantics": (
            "the explicit YAML cache_buffer_capacity_gb value is deep-copied "
            "into both FA and WA store configs; the pinned 64-GiB-per-store "
            "default split runs only when the explicit value is absent"
        ),
        "claim_boundary": (
            "pinned_source_constructor_semantics_not_runtime_failure_cause"
        ),
    }


def _exception_entries(
    lines: list[str],
    source_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    frames: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    for index, raw_line in enumerate(lines):
        line = ANSI_RE.sub("", raw_line)
        frame_match = FRAME_RE.search(line)
        if frame_match:
            raw_path, raw_number, function = frame_match.groups()
            frames.append(
                {
                    "log_line": index + 1,
                    "source_path": _display_path(raw_path, source_root),
                    "source_line": int(raw_number),
                    "function": function,
                    "is_ucm_frame": (
                        "/ucm/" in raw_path
                        or raw_path.endswith(
                            (
                                "ucm_connector.py",
                                "hma_connector.py",
                                "cache_store.cc",
                            )
                        )
                    ),
                }
            )
        exception_match = EXCEPTION_RE.search(line)
        if exception_match:
            message = _bounded_text(exception_match.group("message"))
            exception_type = exception_match.group("type")
            exceptions.append(
                {
                    "log_line": index + 1,
                    "exception_type": exception_type,
                    "exception_message": message,
                    "generic_worker_wrapper": (
                        exception_type.endswith(
                            (
                                "EngineDeadError",
                                "ChildProcessError",
                            )
                        )
                        or any(
                            marker in message.lower()
                            for marker in (
                                "worker failed with error",
                                "engine core initialization failed",
                                "worker died",
                                "engine core died",
                                "engine dead",
                                "failed to start engine",
                                "died unexpectedly",
                            )
                        )
                    ),
                }
            )
    return frames, exceptions


def _select_primary_exception(
    exceptions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    non_wrapper = [item for item in exceptions if not item["generic_worker_wrapper"]]
    if non_wrapper:
        return non_wrapper[-1]
    return exceptions[-1] if exceptions else None


def _failure_stage(
    frames: list[dict[str, Any]],
    primary: dict[str, Any] | None,
    stores: list[dict[str, Any]],
) -> dict[str, Any]:
    if primary is None:
        return {
            "stage": "exception_not_recovered",
            "basis": "no bounded exception signature parsed",
            "inference_only": False,
        }
    preceding = [
        frame
        for frame in frames
        if frame["log_line"] <= primary["log_line"]
        and primary["log_line"] - frame["log_line"] <= 180
    ]
    hma = [
        frame
        for frame in preceding
        if frame["source_path"].endswith("hma_connector.py")
    ]
    function = hma[-1]["function"] if hma else ""
    direct = {
        "_init_group_metas": "fawa_group_meta_initialization",
        "_base_store_config": "fawa_base_store_config",
        "_set_default_shm_buffer_capacity": "fawa_capacity_assignment",
        "_create_fa_store": "fawa_fa_store_creation",
        "_create_wa_store": "fawa_wa_store_creation",
        "register_kv_caches": "fawa_worker_cache_registration",
    }
    if function in direct:
        return {
            "stage": direct[function],
            "basis": f"innermost hma_connector frame function={function}",
            "inference_only": False,
        }
    if function == "_create_store":
        parsed = [item for item in stores if item["parsed"]]
        last_label = parsed[-1]["label"] if parsed else None
        return {
            "stage": (
                f"fawa_{str(last_label).lower()}_store_factory_creation"
                if last_label
                else "fawa_store_factory_creation_label_unresolved"
            ),
            "basis": (
                "innermost frame is _create_store; label uses last "
                "successfully logged pre-factory store config when available"
            ),
            "inference_only": True,
        }
    if hma:
        return {
            "stage": "fawa_constructor_other",
            "basis": f"innermost hma_connector frame function={function}",
            "inference_only": False,
        }
    return {
        "stage": "outer_ucm_fawa_dispatch_only",
        "basis": "no inner hma_connector frame recovered",
        "inference_only": False,
    }


def _excerpt(
    lines: list[str],
    anchor_indices: Iterable[int],
) -> tuple[str, dict[str, Any]]:
    selected: set[int] = set()
    for index in anchor_indices:
        selected.update(range(max(0, index - 8), min(len(lines), index + 9)))
    ordered = sorted(selected)
    output: list[str] = []
    previous: int | None = None
    for index in ordered:
        if previous is not None and index > previous + 1:
            output.append("... bounded gap ...")
        output.append(f"{index + 1}: {_sanitize_line(lines[index])}")
        previous = index
    encoded = ("\n".join(output) + "\n").encode("utf-8")
    truncated = len(encoded) > MAX_EXCERPT_BYTES
    if truncated:
        encoded = encoded[:MAX_EXCERPT_BYTES]
        encoded = encoded.rsplit(b"\n", 1)[0] + b"\n... excerpt byte cap ...\n"
    return encoded.decode("utf-8", errors="replace"), {
        "selected_source_line_count": len(ordered),
        "excerpt_bytes": len(encoded),
        "excerpt_truncated_at_byte_cap": truncated,
        "excerpt_byte_cap": MAX_EXCERPT_BYTES,
    }


def parse_store_geometry(
    lines: list[str],
    configured_capacity_gib: int | None,
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for index, raw_line in enumerate(lines):
        line = ANSI_RE.sub("", raw_line)
        match = STORE_CONFIG_RE.search(line)
        if not match:
            continue
        label, connector_name, raw_config = match.groups()
        entry: dict[str, Any] = {
            "log_line": index + 1,
            "label": label,
            "connector_name": connector_name,
            "parsed": False,
        }
        try:
            value = ast.literal_eval(raw_config)
            if not isinstance(value, dict):
                raise ValueError("store config is not a dict")
            safe = {
                key: value[key]
                for key in SAFE_STORE_KEYS
                if key in value
                and isinstance(value[key], (bool, float, int, str, type(None)))
            }
            entry["config"] = safe
            entry["parsed"] = True
            device_id = safe.get("device_id", -1)
            entry["role"] = "scheduler" if device_id in (-1, None) else "worker"
            buffer_gib = safe.get("cache_buffer_capacity_gb")
            shard_size = safe.get("shard_size")
            load_exclusive = int(safe.get("cache_load_exclusive_buffer_number") or 1024)
            required = max(1024, load_exclusive * 2)
            if (
                isinstance(buffer_gib, (int, float))
                and isinstance(shard_size, int)
                and shard_size > 0
            ):
                buffer_number = int(float(buffer_gib) * (1 << 30)) // shard_size
                entry["geometry"] = {
                    "buffer_number": buffer_number,
                    "required_buffer_number": required,
                    "capacity_gate_predicted": buffer_number >= required,
                }
            else:
                entry["geometry"] = {
                    "buffer_number": None,
                    "required_buffer_number": required,
                    "capacity_gate_predicted": (
                        "bypassed_for_scheduler_device_minus_one"
                        if entry["role"] == "scheduler"
                        else None
                    ),
                }
        except (SyntaxError, ValueError) as error:
            entry["parse_error"] = f"{type(error).__name__}: {error}"
        observations.append(entry)

    role_label_counts: dict[str, int] = {}
    for entry in observations:
        key = f"{entry.get('role', 'unparsed')}:{entry['label']}"
        role_label_counts[key] = role_label_counts.get(key, 0) + 1
    explicit_applies_twice = configured_capacity_gib is not None
    return {
        "store_config_observation_count": len(observations),
        "parsed_store_config_count": sum(entry["parsed"] for entry in observations),
        "role_label_counts": role_label_counts,
        "observations": observations,
        "configured_explicit_cache_buffer_capacity_gib": (configured_capacity_gib),
        "pinned_source_applies_explicit_capacity_to_each_fa_wa_store": (
            explicit_applies_twice
        ),
        "predicted_combined_fa_wa_capacity_gib_per_connector_instance": (
            configured_capacity_gib * 2 if configured_capacity_gib is not None else None
        ),
        "combined_capacity_is_host_allocation_proof": False,
        "claim_boundary": (
            "runtime_logged_store_configs_plus_pinned_constructor_semantics;"
            "predicted_combined_capacity_is_not_observed_host_allocation"
        ),
    }


def parse_exception(
    raw_log: Path,
    source_root: Path,
    stores: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    text = raw_log.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    frames, exceptions = _exception_entries(lines, source_root)
    primary = _select_primary_exception(exceptions)
    relevant_frames = [
        frame
        for frame in frames
        if frame["is_ucm_frame"]
        or frame["source_path"].endswith(
            ("worker_base.py", "core.py", "proc_executor.py")
        )
    ]
    anchors = {item["log_line"] - 1 for item in exceptions} | {
        item["log_line"] - 1 for item in relevant_frames
    }
    anchors.update(
        index
        for index, line in enumerate(lines)
        if any(
            marker in line
            for marker in (
                "Traceback (most recent call last)",
                "UCMFAWAConnector",
                "create FAWA",
                "Worker failed with error",
                "worker died",
            )
        )
    )
    excerpt, excerpt_summary = _excerpt(lines, anchors)
    stage = _failure_stage(frames, primary, stores)
    exception_summary = {
        "raw_log_path": str(raw_log),
        "raw_log_bytes": raw_log.stat().st_size,
        "raw_log_line_count": len(lines),
        "exception_entry_count": len(exceptions),
        "frame_entry_count": len(frames),
        "ucm_frame_count": sum(frame["is_ucm_frame"] for frame in frames),
        "outer_fawa_dispatch_line_2669_observed": any(
            frame["source_path"].endswith("ucm_connector.py")
            and frame["source_line"] == 2669
            for frame in frames
        ),
        "hma_inner_frame_observed": any(
            frame["source_path"].endswith("hma_connector.py") for frame in frames
        ),
        "primary_exception": primary,
        "failure_stage": stage,
        "bounded_frames": relevant_frames[-80:],
        "bounded_exceptions": exceptions[-40:],
        "traceback_excerpt_path": "startup_traceback_excerpt.txt",
        **excerpt_summary,
        "generated_content_retained": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
        "raw_log_hash_retained": False,
        "claim_boundary": (
            "run03_server_local_startup_log_exception_and_constructor_"
            "lineage_only_no_request_or_performance_claim"
        ),
    }
    return exception_summary, excerpt


def _read_configured_capacity(parent_result_dir: Path) -> int | None:
    path = parent_result_dir / "runtime" / "ucm_dram_first_config.yaml"
    if not path.is_file():
        return None
    match = re.search(
        r"^\s*cache_buffer_capacity_gb:\s*([0-9]+)\s*$",
        path.read_text(encoding="utf-8", errors="replace"),
        flags=re.MULTILINE,
    )
    return int(match.group(1)) if match else None


def _next_action(
    primary: dict[str, Any] | None,
    geometry: dict[str, Any],
) -> dict[str, Any]:
    if primary is None:
        action = "add_targeted_constructor_exception_capture_before_new_lifecycle"
    else:
        message = str(primary.get("exception_message", "")).lower()
        if "too small buffer" in message:
            action = "recompute_fa_and_wa_capacity_from_each_observed_shard"
        elif any(
            marker in message
            for marker in ("cannot allocate", "out of memory", "no space")
        ):
            action = "separate_and_bound_fa_wa_host_buffer_allocation"
        elif any(
            marker in message
            for marker in (
                "invalid shard",
                "invalid block size",
                "invalid tensor size",
            )
        ):
            action = "repair_fawa_store_geometry_at_the_exact_failed_role"
        elif any(
            marker in message
            for marker in ("permission denied", "no such file", "posix")
        ):
            action = "repair_fawa_namespaced_storage_backend_preflight"
        else:
            action = "implement_targeted_fix_at_recovered_primary_frame"
    return {
        "recommended_developer_action": action,
        "another_lifecycle_authorized_by_this_task": False,
        "run04_authorized": False,
        "parameter_sweep_authorized": False,
        "server_side_code_edit_authorized": False,
        "geometry_observations_available": geometry["parsed_store_config_count"] > 0,
    }


def analyze(
    parent_result_dir: Path,
    result_dir: Path,
    source_root: Path,
    resource_observation: Path,
) -> str:
    if result_dir.name != RUN_ID:
        raise ValueError(f"result basename must be {RUN_ID}")
    if result_dir.exists():
        raise FileExistsError(result_dir)
    result_dir.mkdir(parents=True)

    provenance, raw_log, parent_capacity = validate_parent(parent_result_dir)
    source_lineage = collect_source_lineage(source_root)
    configured_capacity = _read_configured_capacity(parent_result_dir)
    log_lines = raw_log.read_text(encoding="utf-8", errors="replace").splitlines()
    geometry = parse_store_geometry(log_lines, configured_capacity)
    exception, excerpt = parse_exception(
        raw_log,
        source_root,
        geometry["observations"],
    )
    raw_stat_after = raw_log.stat()
    provenance["parent_raw_log_mtime_ns_after"] = raw_stat_after.st_mtime_ns
    provenance["parent_raw_log_bytes_after"] = raw_stat_after.st_size
    provenance["parent_raw_log_unchanged_during_analysis"] = (
        provenance["parent_raw_log_mtime_ns_before"] == raw_stat_after.st_mtime_ns
        and provenance["parent_raw_log_bytes"] == raw_stat_after.st_size
    )
    if not provenance["parent_raw_log_unchanged_during_analysis"]:
        raise RuntimeError("parent raw startup log changed during analysis")

    resource = _json(resource_observation)
    required_resource = all(
        (
            resource.get("npu_started") is False,
            resource.get("vllm_started") is False,
            resource.get("model_requests_sent") == 0,
            resource.get("keep_alive_action") == "left_running",
            resource.get("port_7000_listener_count_before") == 0,
            resource.get("port_7000_listener_count_after") == 0,
            resource.get("vllm_residual_process_count_before") == 0,
            resource.get("vllm_residual_process_count_after") == 0,
            resource.get("tracked_worktree_clean") is True,
        )
    )
    primary = exception["primary_exception"]
    attributed = all(
        (
            provenance["parent_payloads_all_match_manifest"] is True,
            provenance["parent_raw_log_unchanged_during_analysis"] is True,
            source_lineage["ucm_source_head"] == UCM_COMMIT,
            primary is not None,
            bool(primary and primary.get("exception_type")),
            bool(primary and primary.get("exception_message")),
            exception["ucm_frame_count"] > 0,
            required_resource,
        )
    )
    if attributed:
        grade = "attributed_p8_2_k2_r0_run03_fawa_startup_failure"
    elif primary is not None and required_resource:
        grade = "partial_p8_2_k2_r0_run03_startup_failure_attribution"
    else:
        grade = "blocked_p8_2_k2_r0_run03_startup_evidence_incomplete"
    action = _next_action(primary, geometry)
    grading = {
        "task_id": TASK_ID,
        "run_id": RUN_ID,
        "grade": grade,
        "parent_grade": provenance["parent_grade"],
        "parent_manifest_valid": True,
        "parent_raw_log_read_only": True,
        "parent_raw_log_unchanged_during_analysis": provenance[
            "parent_raw_log_unchanged_during_analysis"
        ],
        "pinned_ucm_source_valid": True,
        "exact_exception_type_recovered": bool(
            primary and primary.get("exception_type")
        ),
        "exact_exception_message_recovered": bool(
            primary and primary.get("exception_message")
        ),
        "ucm_inner_frame_recovered": exception["ucm_frame_count"] > 0,
        "fawa_store_config_observation_count": geometry[
            "store_config_observation_count"
        ],
        "fawa_store_config_parsed_count": geometry["parsed_store_config_count"],
        "failure_stage": exception["failure_stage"],
        "npu_started": False,
        "vllm_started": False,
        "model_requests_sent": 0,
        "keep_alive_action": "left_running",
        "resource_observation_exact": required_resource,
        "performance_benefit_claimed": False,
        "mechanism_implemented_claimed": False,
        "run04_authorized": False,
        "next_task_authorized": False,
        **action,
        "claim_boundary": (
            "zero_npu_read_only_parent_startup_failure_attribution_only;"
            "no_external_prefix_mechanism_or_performance_claim"
        ),
    }

    (result_dir / "parent_provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (result_dir / "source_constructor_lineage.json").write_text(
        json.dumps(source_lineage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (result_dir / "fawa_store_geometry.json").write_text(
        json.dumps(geometry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (result_dir / "startup_exception_summary.json").write_text(
        json.dumps(exception, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (result_dir / "startup_traceback_excerpt.txt").write_text(
        excerpt,
        encoding="utf-8",
    )
    (result_dir / "resource_observation_summary.json").write_text(
        json.dumps(resource, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (result_dir / "grading_summary.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (result_dir / "task_grade.txt").write_text(grade + "\n", encoding="utf-8")
    result_summary = (
        "# P8.2-K2-R0 run03 FAWA startup attribution\n\n"
        f"- grade: `{grade}`\n"
        f"- parent: `{PARENT_RUN_BASENAME}`; manifest and all payloads verified\n"
        f"- exact exception: `{primary}`\n"
        f"- failure stage: `{exception['failure_stage']['stage']}`\n"
        f"- logged FA/WA store configs: "
        f"`{geometry['store_config_observation_count']}` "
        f"(parsed `{geometry['parsed_store_config_count']}`)\n"
        f"- recommended developer action: "
        f"`{action['recommended_developer_action']}`\n"
        "- execution: zero NPU, zero vLLM, zero model requests; keep-alive left running\n"
        "- boundary: exact startup attribution only; no mechanism or performance claim\n"
    )
    (result_dir / "result_summary.md").write_text(
        result_summary,
        encoding="utf-8",
    )
    return grade


def package(result_dir: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for name in PAYLOAD_NAMES:
        path = result_dir / name
        if not path.is_file():
            raise FileNotFoundError(path)
        files.append(
            {
                "relative_path": name,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "sensitivity": SENSITIVITY,
            }
        )
    payload_bytes = sum(item["bytes"] for item in files)
    manifest = {
        "task_id": TASK_ID,
        "run_id": RUN_ID,
        "files": files,
        "payload_file_count": len(files),
        "payload_total_bytes": payload_bytes,
        "manifest_bytes": 0,
        "transfer_file_count": len(files) + 1,
        "transfer_total_bytes": 0,
        "bounded_transfer_max_bytes": MAX_TRANSFER_BYTES,
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "automatic_transfer_allowed": False,
        "available_methods": ["email", "upload-api", "server-local"],
        "recommended_method": "server-local",
        "recommended_method_reason": (
            "the bounded diagnostic package is already server-local and the "
            "raw startup log remains in place"
        ),
        "raw_startup_log_retained_server_local": True,
        "generated_content_retained": False,
        "request_ids_retained": False,
        "token_ids_retained": False,
        "raw_log_hash_retained": False,
    }
    path = result_dir / "candidate_manifest.server_local.json"
    for _ in range(12):
        path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest_bytes = path.stat().st_size
        transfer_bytes = payload_bytes + manifest_bytes
        if (
            manifest["manifest_bytes"] == manifest_bytes
            and manifest["transfer_total_bytes"] == transfer_bytes
        ):
            break
        manifest["manifest_bytes"] = manifest_bytes
        manifest["transfer_total_bytes"] = transfer_bytes
    else:
        raise RuntimeError("manifest size did not converge")
    if manifest["transfer_total_bytes"] > MAX_TRANSFER_BYTES:
        raise ValueError("bounded package exceeds 70 KiB")
    persisted = _json(path)
    if persisted != manifest:
        raise RuntimeError("persisted manifest drift")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--parent-result-dir", type=Path, required=True)
    analyze_parser.add_argument("--result-dir", type=Path, required=True)
    analyze_parser.add_argument("--ucm-source-root", type=Path, required=True)
    analyze_parser.add_argument(
        "--resource-observation",
        type=Path,
        required=True,
    )
    package_parser = subparsers.add_parser("package")
    package_parser.add_argument("--result-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "analyze":
        analyze(
            args.parent_result_dir,
            args.result_dir,
            args.ucm_source_root,
            args.resource_observation,
        )
        return 0
    package(args.result_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
