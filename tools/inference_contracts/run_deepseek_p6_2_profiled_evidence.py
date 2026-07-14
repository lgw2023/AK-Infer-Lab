from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.run_deepseek_p6_1_unprofiled_baseline import (  # noqa: E402
    _get,
    _metrics_snapshot,
    _process_alive,
    _stream_request,
    _wait_for_idle,
)


PROFILED_CELLS = (
    ("short_prefill", 4096, 64),
    ("long_prefill", 131072, 64),
    ("decode_heavy", 4096, 256),
)


def parse_npu_smi_hbm_table(text: str) -> list[dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    current: int | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = re.match(r"^\|\s*([0-7])\s+910B1\s+\|", line)
        if match:
            current = int(match.group(1))
            continue
        if current is None:
            continue
        if not re.match(r"^\|\s*\d+\s*\|\s*[0-9A-Fa-f:.]+\s*\|", line):
            continue
        ratios = re.findall(r"([0-9]+)\s*/\s*([0-9]+)", line)
        if not ratios:
            continue
        used_mb, capacity_mb = map(float, ratios[-1])
        records[current] = {
            "device_id": current,
            "hbm_capacity_mb": capacity_mb,
            "hbm_used_mb": used_mb,
            "hbm_free_mb": capacity_mb - used_mb,
            "hbm_usage_pct": used_mb * 100.0 / capacity_mb,
            "parser_ok": capacity_mb > 0,
        }
        current = None
    return [
        records.get(device_id, {"device_id": device_id, "parser_ok": False})
        for device_id in range(8)
    ]


def summarize_phase_memory(
    *,
    cell_id: str,
    samples: list[dict[str, Any]],
    request_start_ns: int,
    first_token_ns: int,
    response_end_ns: int,
) -> list[dict[str, Any]]:
    phase_windows = (
        ("prefill", request_start_ns, first_token_ns),
        ("decode", first_token_ns, response_end_ns),
    )
    rows: list[dict[str, Any]] = []
    for phase, phase_start, phase_end in phase_windows:
        overlapping = [
            sample
            for sample in samples
            if int(sample["sweep_start_monotonic_ns"]) < phase_end
            and int(sample["sweep_end_monotonic_ns"]) > phase_start
        ]
        rss = [float(sample.get("host_process_rss_mb") or 0.0) for sample in overlapping]
        pss = [
            float(sample["host_process_pss_mb"])
            for sample in overlapping
            if sample.get("host_process_pss_mb") is not None
        ]
        coverage = [
            sum(bool(device.get("parser_ok")) for device in sample.get("devices", []))
            for sample in overlapping
        ]
        used_totals = [
            sum(float(device.get("hbm_used_mb") or 0.0) for device in sample.get("devices", []))
            for sample in overlapping
        ]
        free_totals = [
            sum(float(device.get("hbm_free_mb") or 0.0) for device in sample.get("devices", []))
            for sample in overlapping
        ]
        usage_values = [
            float(device.get("hbm_usage_pct") or 0.0)
            for sample in overlapping
            for device in sample.get("devices", [])
            if device.get("parser_ok")
        ]
        rows.append(
            {
                "cell_id": cell_id,
                "phase": phase,
                "sample_count": len(overlapping),
                "device_coverage_min": min(coverage, default=0),
                "parse_failure_count": sum(max(0, 8 - item) for item in coverage),
                "host_process_rss_mb_avg": round(statistics.fmean(rss), 3) if rss else None,
                "host_process_rss_mb_max": round(max(rss), 3) if rss else None,
                "host_process_pss_mb_avg": round(statistics.fmean(pss), 3) if pss else None,
                "host_process_pss_mb_max": round(max(pss), 3) if pss else None,
                "npu_hbm_used_mb_total_avg": round(statistics.fmean(used_totals), 3)
                if used_totals
                else None,
                "npu_hbm_used_mb_total_max": round(max(used_totals), 3)
                if used_totals
                else None,
                "npu_hbm_free_mb_total_min": round(min(free_totals), 3)
                if free_totals
                else None,
                "npu_hbm_usage_pct_device_max": round(max(usage_values), 6)
                if usage_values
                else None,
                "policy": "sweep_interval_overlap_boundary_sample_counted_in_both_phases",
            }
        )
    return rows


def _common_prefix_length(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    for index, (left_token, right_token) in enumerate(zip(left, right, strict=True)):
        if left_token != right_token:
            return index
    return len(left)


def _select_offsets(source_tokens: list[int], count: int) -> list[tuple[int, int]]:
    prefixes: list[tuple[int, ...]] = []
    selected: list[tuple[int, int]] = []
    for offset in range(len(source_tokens)):
        prefix = tuple(
            source_tokens[(offset + index) % len(source_tokens)] for index in range(128)
        )
        if prefix in prefixes:
            continue
        max_common = max(
            (_common_prefix_length(prefix, prior) for prior in prefixes),
            default=0,
        )
        if max_common >= 128:
            continue
        prefixes.append(prefix)
        selected.append((offset, max_common))
        if len(selected) == count:
            return selected
    raise ValueError("source payload does not provide enough distinct prefix rotations")


def _repeat_and_truncate(tokens: list[int], size: int, offset: int) -> list[int]:
    rotated = tokens[offset:] + tokens[:offset]
    return (rotated * math.ceil(size / len(rotated)))[:size]


def build_profiled_plan() -> list[dict[str, Any]]:
    return [
        {
            "cell_id": cell_id,
            "warmup": {"context_tokens": 4096, "output_tokens": 64},
            "measured": {
                "context_tokens": context_tokens,
                "output_tokens": output_tokens,
            },
        }
        for cell_id, context_tokens, output_tokens in PROFILED_CELLS
    ]


def prepare_artifacts(
    source_payload: Path,
    artifact_dir: Path,
    model_name: str,
) -> dict[str, Any]:
    source = json.loads(source_payload.read_text(encoding="utf-8"))
    source_tokens = source.get("prompt")
    if not isinstance(source_tokens, list) or len(source_tokens) != 4096:
        raise ValueError("source payload must contain exactly 4096 prompt token IDs")
    if not all(isinstance(token, int) and not isinstance(token, bool) for token in source_tokens):
        raise ValueError("source prompt must contain integer token IDs")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    body_dir = artifact_dir / "bodies"
    body_dir.mkdir(parents=True, exist_ok=True)
    plan = build_profiled_plan()
    offsets = iter(_select_offsets(source_tokens, len(plan) * 2))
    records: list[dict[str, Any]] = []

    for cell in plan:
        for role in ("warmup", "measured"):
            request = cell[role]
            offset, max_common = next(offsets)
            prompt = _repeat_and_truncate(
                source_tokens,
                int(request["context_tokens"]),
                offset,
            )
            body = {
                "ignore_eos": True,
                "max_tokens": int(request["output_tokens"]),
                "min_tokens": int(request["output_tokens"]),
                "model": model_name,
                "prompt": prompt,
                "return_token_ids": True,
                "stream": True,
                "stream_options": {"include_usage": True},
                "temperature": 0.0,
            }
            raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            request_id = f"{cell['cell_id']}_{role}"
            relative_path = Path("bodies") / f"{request_id}.json"
            (artifact_dir / relative_path).write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            request.update(
                {
                    "request_id": request_id,
                    "body_relative_path": str(relative_path),
                    "request_body_sha256": digest,
                    "cyclic_offset": offset,
                }
            )
            records.append(
                {
                    "cell_id": cell["cell_id"],
                    "role": role,
                    "request_id": request_id,
                    "context_tokens": request["context_tokens"],
                    "output_tokens": request["output_tokens"],
                    "body_bytes": len(raw),
                    "request_body_sha256": digest,
                    "common_prefix_upper_bound_tokens": max_common,
                }
            )

    manifest = {
        "source_prompt_tokens": len(source_tokens),
        "request_count": len(records),
        "pairwise_common_prefix_tokens_less_than": 128,
        "all_request_body_sha256_unique": len(
            {row["request_body_sha256"] for row in records}
        )
        == len(records),
        "generated_text_retained": False,
        "token_ids_retained": False,
        "records": records,
    }
    if not manifest["all_request_body_sha256_unique"]:
        raise ValueError("request body hashes are not unique")
    (artifact_dir / "profiled_plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "request_body_manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _descendant_pids(root_pid: int) -> list[int]:
    parents: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            text = (entry / "stat").read_text(encoding="utf-8", errors="replace")
            right = text.rfind(")")
            fields = text[right + 2 :].split()
            parents[int(entry.name)] = int(fields[1])
        except (OSError, ValueError, IndexError):
            continue
    selected = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, parent in parents.items():
            if parent in selected and pid not in selected:
                selected.add(pid)
                changed = True
    return sorted(selected)


def _read_kb_field(path: Path, field: str) -> float | None:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(field + ":"):
                return float(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def collect_process_memory(root_pid: int) -> dict[str, Any]:
    rss_kb = 0.0
    pss_kb = 0.0
    pss_count = 0
    pids = _descendant_pids(root_pid)
    for pid in pids:
        rss = _read_kb_field(Path(f"/proc/{pid}/status"), "VmRSS")
        if rss is not None:
            rss_kb += rss
        pss = _read_kb_field(Path(f"/proc/{pid}/smaps_rollup"), "Pss")
        if pss is not None:
            pss_kb += pss
            pss_count += 1
    return {
        "process_count": len(pids),
        "host_process_rss_mb": rss_kb / 1024.0,
        "host_process_pss_mb": pss_kb / 1024.0 if pss_count else None,
    }


def collect_memory_sample(server_pid: int, raw_dir: Path, sequence: int) -> dict[str, Any]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    start_ns = time.monotonic_ns()
    completed = subprocess.run(
        ["npu-smi", "info"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        text=True,
    )
    process_memory = collect_process_memory(server_pid)
    end_ns = time.monotonic_ns()
    raw_path = raw_dir / f"npu_smi_{sequence:06d}.txt"
    raw_path.write_text(completed.stdout, encoding="utf-8")
    devices = parse_npu_smi_hbm_table(completed.stdout)
    return {
        "sequence": sequence,
        "command": ["npu-smi", "info"],
        "return_code": completed.returncode,
        "sweep_start_monotonic_ns": start_ns,
        "sweep_end_monotonic_ns": end_ns,
        "sweep_wall_seconds": (end_ns - start_ns) / 1e9,
        "device_coverage": sum(bool(device.get("parser_ok")) for device in devices),
        "parse_failure_count": sum(not bool(device.get("parser_ok")) for device in devices),
        "devices": devices,
        "raw_server_path": str(raw_path),
        **process_memory,
    }


def _write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _request_item(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": request["request_id"],
        "request_index": 1,
        "body_relative_path": request["body_relative_path"],
        "request_body_sha256": request["request_body_sha256"],
    }


def _run_single_request(
    *,
    artifact_dir: Path,
    base_url: str,
    server_pid: int,
    cell_id: str,
    role: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    batch = {
        "batch_id": f"{cell_id}_{role}",
        "phase": role,
        "context_tokens": request["context_tokens"],
        "output_tokens": request["output_tokens"],
        "concurrency": 1,
        "repeat_index": 1,
    }
    return _stream_request(
        artifact_dir=artifact_dir,
        base_url=base_url,
        server_pid=server_pid,
        batch=batch,
        request_item=_request_item(request),
        start_barrier=threading.Barrier(1),
    )


def run_cell(
    *,
    artifact_dir: Path,
    cell_id: str,
    base_url: str,
    server_pid: int,
    sample_once: Callable[[int, Path, int], dict[str, Any]] = collect_memory_sample,
    sample_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    plan = json.loads((artifact_dir / "profiled_plan.json").read_text(encoding="utf-8"))
    cell = next((row for row in plan if row["cell_id"] == cell_id), None)
    if cell is None:
        raise ValueError(f"unknown profiled cell: {cell_id}")
    cell_dir = artifact_dir / "source" / cell_id
    vllm_dir = cell_dir / "vllm"
    raw_metrics = cell_dir / "raw_metrics"
    raw_memory = cell_dir / "raw_memory"
    vllm_dir.mkdir(parents=True, exist_ok=True)

    health_before_warmup, _ = _get(base_url, "/health", timeout=5)
    idle_before_warmup, _ = _wait_for_idle(
        base_url,
        raw_metrics / "before_warmup.prom",
    )
    warmup = _run_single_request(
        artifact_dir=artifact_dir,
        base_url=base_url,
        server_pid=server_pid,
        cell_id=cell_id,
        role="warmup",
        request=cell["warmup"],
    )
    idle_after_warmup, _ = _wait_for_idle(
        base_url,
        raw_metrics / "after_warmup.prom",
    )

    health_before, _ = _get(base_url, "/health", timeout=5)
    idle_before, metrics_before = _wait_for_idle(
        base_url,
        raw_metrics / "before_measured.prom",
    )

    samples: list[dict[str, Any]] = []
    stop_sampler = threading.Event()
    sampler_started = threading.Event()

    def sampler() -> None:
        sequence = 0
        while not stop_sampler.is_set():
            sampler_started.set()
            started = time.monotonic()
            try:
                samples.append(sample_once(server_pid, raw_memory / "npu_smi", sequence))
            except Exception as error:
                samples.append(
                    {
                        "sequence": sequence,
                        "sweep_start_monotonic_ns": time.monotonic_ns(),
                        "sweep_end_monotonic_ns": time.monotonic_ns(),
                        "device_coverage": 0,
                        "parse_failure_count": 8,
                        "devices": [],
                        "sampler_error": f"{type(error).__name__}: {str(error)[:1024]}",
                    }
                )
            sequence += 1
            remaining = sample_interval_seconds - (time.monotonic() - started)
            if stop_sampler.wait(max(0.0, remaining)):
                break

    sampler_thread = threading.Thread(target=sampler, daemon=True)
    sampler_thread.start()
    sampler_started.wait(timeout=5)
    measured = _run_single_request(
        artifact_dir=artifact_dir,
        base_url=base_url,
        server_pid=server_pid,
        cell_id=cell_id,
        role="measured",
        request=cell["measured"],
    )
    stop_sampler.set()
    sampler_thread.join(timeout=120)

    health_after, _ = _get(base_url, "/health", timeout=5)
    idle_after, metrics_after = _wait_for_idle(
        base_url,
        raw_metrics / "after_measured.prom",
    )
    counter_delta = {
        name: float(metrics_after.get(name) or 0.0) - float(metrics_before.get(name) or 0.0)
        for name in ("num_drafts", "num_draft_tokens", "num_accepted_tokens")
    }
    phase_rows = summarize_phase_memory(
        cell_id=cell_id,
        samples=samples,
        request_start_ns=int(measured.get("request_start_ns") or 0),
        first_token_ns=int((measured.get("token_arrival_ns") or [0])[0]),
        response_end_ns=int(measured.get("request_end_ns") or 0),
    )
    _write_tsv(cell_dir / "phase_memory_summary.tsv", phase_rows)
    (cell_dir / "raw_memory_samples.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in samples),
        encoding="utf-8",
    )
    (cell_dir / "request_timing_and_token_arrival.json").write_text(
        json.dumps({"warmup": warmup, "measured": measured}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    phase_memory_ok = len(phase_rows) == 2 and all(
        row["sample_count"] > 0
        and row["device_coverage_min"] == 8
        and row["parse_failure_count"] == 0
        for row in phase_rows
    )
    counter_evidence_ok = (
        metrics_before.get("all_required_metrics_present") is True
        and metrics_after.get("all_required_metrics_present") is True
        and counter_delta["num_drafts"] > 0
        and counter_delta["num_draft_tokens"] > 0
        and counter_delta["num_accepted_tokens"] >= 0
    )
    checks = {
        "server_alive": _process_alive(server_pid),
        "health_before_warmup_200": health_before_warmup == 200,
        "idle_before_warmup": idle_before_warmup,
        "warmup_success": warmup.get("status") == "success",
        "idle_after_warmup": idle_after_warmup,
        "health_before_measured_200": health_before == 200,
        "idle_before_measured": idle_before,
        "measured_success": measured.get("status") == "success",
        "health_after_measured_200": health_after == 200,
        "idle_after_measured": idle_after,
        "counter_evidence_ok": counter_evidence_ok,
        "phase_memory_ok": phase_memory_ok,
    }
    status = "success" if all(checks.values()) else "failed"
    result = {
        "cell_id": cell_id,
        "status": status,
        "warmup_status": warmup.get("status"),
        "measured_status": measured.get("status"),
        "context_tokens": cell["measured"]["context_tokens"],
        "output_tokens": cell["measured"]["output_tokens"],
        "request_body_sha256": measured.get("request_body_sha256"),
        "prompt_tokens": measured.get("prompt_tokens"),
        "generated_token_count": measured.get("generated_token_count"),
        "streamed_token_count": measured.get("streamed_token_count"),
        "max_token_chunk_width": measured.get("max_token_chunk_width"),
        "finish_reason": measured.get("finish_reason"),
        "saw_done": measured.get("saw_done"),
        "request_start_ns": measured.get("request_start_ns"),
        "first_token_ns": (measured.get("token_arrival_ns") or [None])[0],
        "response_end_ns": measured.get("request_end_ns"),
        "diagnostic_ttft_ms": measured.get("ttft_ms"),
        "diagnostic_tpot_ms": measured.get("tpot_ms"),
        "diagnostic_e2el_ms": measured.get("e2el_ms"),
        "counter_delta": counter_delta,
        "accepted_token_delta": counter_delta["num_accepted_tokens"],
        "counter_evidence_ok": counter_evidence_ok,
        "memory_sample_count": len(samples),
        "phase_memory_ok": phase_memory_ok,
        "checks": checks,
        "generated_text_retained": False,
        "token_ids_retained": False,
    }
    (cell_dir / "profiled_cell_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    aggregate_row = {
        "case_id": cell_id,
        "prompt_id": cell_id,
        "prefix_reuse_group": "none",
        "arrival_delay_ms": 0,
        "cap_tokens": cell["measured"]["context_tokens"],
        "max_new_tokens": cell["measured"]["output_tokens"],
        "input_token_count": measured.get("prompt_tokens"),
        "generated_token_count": measured.get("generated_token_count"),
        "request_start_ns": measured.get("request_start_ns"),
        "response_end_ns": measured.get("request_end_ns"),
        "client_wall_us": round(
            (int(measured.get("request_end_ns") or 0) - int(measured.get("request_start_ns") or 0))
            / 1000.0,
            3,
        ),
        "status": status,
    }
    (vllm_dir / "vllm_api_concurrency_result.json").write_text(
        json.dumps(
            {
                "run_id": f"p6_2_{cell_id}",
                "status": status,
                "request_count": 1,
                "success_case_count": int(status == "success"),
                "failed_case_count": int(status != "success"),
                "rows": [aggregate_row],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return result


def _read_tsv(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or not path.read_text(encoding="utf-8").strip():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), *args], text=True
        ).strip()
    except Exception:
        return ""


def finalize_artifacts(
    *,
    artifact_dir: Path,
    cleanup_status: str,
    aggregate_exit: int,
) -> dict[str, Any]:
    cell_results: list[dict[str, Any]] = []
    phase_rows: list[dict[str, Any]] = []
    inventory_rows: list[dict[str, Any]] = []
    for cell_id, _, _ in PROFILED_CELLS:
        cell_dir = artifact_dir / "source" / cell_id
        result_path = cell_dir / "profiled_cell_result.json"
        result = (
            json.loads(result_path.read_text(encoding="utf-8"))
            if result_path.is_file()
            else {"cell_id": cell_id, "status": "missing"}
        )
        cell_results.append(result)
        phase_rows.extend(_read_tsv(cell_dir / "phase_memory_summary.tsv"))
        profiler_exit_path = cell_dir / "profiler_exit_code.txt"
        profiler_exit = (
            int(profiler_exit_path.read_text(encoding="utf-8").strip())
            if profiler_exit_path.is_file()
            else 99
        )
        output_files = (
            [
                line
                for line in (cell_dir / "msprof_output_files.txt")
                .read_text(encoding="utf-8", errors="replace")
                .splitlines()
                if line
            ]
            if (cell_dir / "msprof_output_files.txt").is_file()
            else []
        )
        inventory_rows.append(
            {
                "cell_id": cell_id,
                "profiler_exit_code": profiler_exit,
                "msprof_file_count": len(output_files),
                "sqlite_file_count": sum(path.endswith(".db") for path in output_files),
                "raw_profiler_server_root": next(
                    (path.split("/PROF_", 1)[0] for path in output_files if "/PROF_" in path),
                    "",
                ),
            }
        )

    analysis_dir = artifact_dir / "analysis"
    aggregate_result_path = analysis_dir / "msprof_request_device_aggregate_result.json"
    aggregate_result = (
        json.loads(aggregate_result_path.read_text(encoding="utf-8"))
        if aggregate_result_path.is_file()
        else {"overall_status": "missing", "mode_summaries": []}
    )
    aggregate_modes = {
        row.get("mode"): row for row in aggregate_result.get("mode_summaries", [])
    }
    cell_ids = {cell_id for cell_id, _, _ in PROFILED_CELLS}
    successful_cells = [row for row in cell_results if row.get("status") == "success"]
    accepted_total = sum(float(row.get("accepted_token_delta") or 0.0) for row in cell_results)
    phase_by_cell = {
        cell_id: [row for row in phase_rows if row.get("cell_id") == cell_id]
        for cell_id in cell_ids
    }
    phase_ok = all(
        {row.get("phase") for row in phase_by_cell[cell_id]} == {"prefill", "decode"}
        and all(
            int(row.get("sample_count") or 0) > 0
            and int(row.get("device_coverage_min") or 0) == 8
            and int(row.get("parse_failure_count") or 0) == 0
            for row in phase_by_cell[cell_id]
        )
        for cell_id in cell_ids
    )
    profiler_ok = all(
        row["profiler_exit_code"] == 0 and row["sqlite_file_count"] > 0
        for row in inventory_rows
    )
    aggregate_ok = aggregate_exit == 0 and all(
        aggregate_modes.get(cell_id, {}).get("aggregate_status")
        == "request_device_aggregate_available"
        and int(aggregate_modes[cell_id].get("msprof_root_exists") or 0) == 1
        and int(aggregate_modes[cell_id].get("request_device_summary_rows") or 0) > 0
        and int(aggregate_modes[cell_id].get("top_op_summary_rows") or 0) > 0
        and int(aggregate_modes[cell_id].get("metric_summary_rows") or 0) > 0
        for cell_id in cell_ids
    )
    heavy_joins_skipped = bool(aggregate_result.get("heavy_joins_skipped"))

    if cleanup_status != "clean":
        grade = "red_cleanup_incomplete"
    elif not successful_cells:
        grade = "red_mtp_profiled_evidence_no_success"
    elif heavy_joins_skipped:
        grade = "yellow_mtp_profiled_evidence_skip_heavy_joins"
    elif (
        len(successful_cells) == 3
        and accepted_total > 0
        and phase_ok
        and profiler_ok
        and aggregate_ok
    ):
        grade = "candidate_green_mtp_profiled_evidence"
    else:
        grade = "yellow_mtp_profiled_evidence_partial"

    grading = {
        "server_grade": grade,
        "profiled_cell_count": len(cell_results),
        "successful_profiled_cell_count": len(successful_cells),
        "accepted_token_delta_total": accepted_total,
        "phase_memory_ok": phase_ok,
        "profiler_ok": profiler_ok,
        "request_device_aggregate_ok": aggregate_ok,
        "aggregate_exit": aggregate_exit,
        "heavy_joins_skipped": heavy_joins_skipped,
        "cleanup_status": cleanup_status,
        "performance_reference_baseline_remains_true": True,
        "developer_review_required": True,
        "claim_boundary": (
            "mtp_profiled_operator_memory_transfer_and_request_device_evidence_only"
        ),
    }
    (artifact_dir / "grading_inputs.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "cleanup_status.txt").write_text(cleanup_status + "\n", encoding="utf-8")

    compact_cell_fields = (
        "cell_id",
        "status",
        "context_tokens",
        "output_tokens",
        "prompt_tokens",
        "generated_token_count",
        "streamed_token_count",
        "finish_reason",
        "saw_done",
        "accepted_token_delta",
        "counter_evidence_ok",
        "phase_memory_ok",
        "diagnostic_ttft_ms",
        "diagnostic_tpot_ms",
        "diagnostic_e2el_ms",
    )
    _write_tsv(
        artifact_dir / "profiled_cell_summary.tsv",
        [{field: row.get(field, "") for field in compact_cell_fields} for row in cell_results],
    )
    _write_tsv(artifact_dir / "phase_memory_summary.tsv", phase_rows)
    _write_tsv(
        artifact_dir / "request_device_aggregate_summary.tsv",
        [aggregate_modes[cell_id] for cell_id, _, _ in PROFILED_CELLS if cell_id in aggregate_modes],
    )
    _write_tsv(artifact_dir / "profiler_inventory.tsv", inventory_rows)

    for source_name, target_name in (
        ("request_top_op_type_duration.tsv", "request_top_op_summary.tsv"),
        ("request_ai_core_metric_summary.tsv", "ai_core_metric_summary.tsv"),
    ):
        source = analysis_dir / source_name
        target = artifact_dir / target_name
        target.write_bytes(source.read_bytes() if source.is_file() else b"")

    environment = {
        "git_head": _git_value("rev-parse", "HEAD"),
        "origin_main": _git_value("rev-parse", "origin/main"),
        "tracked_status": _git_value("status", "--porcelain", "--untracked-files=no"),
        "source_payload_sha256": (
            (artifact_dir / "source_payload_sha256.txt").read_text().split()[0]
            if (artifact_dir / "source_payload_sha256.txt").is_file()
            else None
        ),
        "server_command_sha256": (
            (artifact_dir / "server_command_sha256.txt").read_text().split()[0]
            if (artifact_dir / "server_command_sha256.txt").is_file()
            else None
        ),
        "server_lifecycle_count": len(
            [row for row in inventory_rows if row["profiler_exit_code"] != 99]
        ),
        "profiler_run": True,
        "hbm_sampler_run": True,
    }
    (artifact_dir / "environment_and_hashes.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = [
        "# P6.2 MTP profiled evidence server result",
        "",
        "- task_id: p6_2_deepseek_v4_flash_w8a8_mtp_profiled_evidence_2026_0714",
        f"- server_grade: {grade}",
        f"- profiled_cells: {len(successful_cells)}/3 successful",
        f"- accepted_token_delta_total: {accepted_total}",
        f"- phase_memory_ok: {str(phase_ok).lower()}",
        f"- request_device_aggregate_ok: {str(aggregate_ok).lower()}",
        f"- cleanup: {cleanup_status}",
        "- profiled_latency_is_performance_baseline: false",
        "- performance_reference_baseline_remains_true: true",
        "- claim_boundary: mtp_profiled_operator_memory_transfer_and_request_device_evidence_only",
        f"- raw_result_root_server_local: {artifact_dir}",
        "- generated_text_retained: false",
        "- token_ids_retained: false",
    ]
    (artifact_dir / "result_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    if grade != "candidate_green_mtp_profiled_evidence":
        first_failure = next(
            (row for row in cell_results if row.get("status") != "success"),
            {"aggregate_result": aggregate_result},
        )
        (artifact_dir / "first_failure_excerpt.txt").write_text(
            json.dumps(first_failure, indent=2, sort_keys=True)[:8192] + "\n",
            encoding="utf-8",
        )

    candidate_names = (
        "result_summary.md",
        "environment_and_hashes.json",
        "request_body_manifest.json",
        "profiled_cell_summary.tsv",
        "phase_memory_summary.tsv",
        "request_device_aggregate_summary.tsv",
        "request_top_op_summary.tsv",
        "ai_core_metric_summary.tsv",
        "profiler_inventory.tsv",
        "grading_inputs.json",
        "cleanup_status.txt",
        "first_failure_excerpt.txt",
    )
    candidate_rows = []
    total_bytes = 0
    for name in candidate_names:
        path = artifact_dir / name
        if not path.is_file():
            continue
        size = path.stat().st_size
        total_bytes += size
        candidate_rows.append(
            {
                "path": str(path),
                "bytes": size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "sensitivity": (
                    "bounded_structured_profiled_evidence_no_generated_content_or_token_ids"
                ),
            }
        )
    _write_tsv(artifact_dir / "delivery_candidates.tsv", candidate_rows)
    (artifact_dir / "delivery_candidates_total_bytes.txt").write_text(
        f"{total_bytes}\n", encoding="utf-8"
    )
    if total_bytes > 71680:
        grading["candidate_size_gate_pass"] = False
        grading["candidate_total_bytes"] = total_bytes
        (artifact_dir / "grading_inputs.json").write_text(
            json.dumps(grading, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return grading


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the DeepSeek P6.2 MTP profiled evidence client."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    run = subparsers.add_parser("run-cell")
    run.add_argument("--artifact-dir", type=Path, required=True)
    run.add_argument("--cell-id", choices=[row[0] for row in PROFILED_CELLS], required=True)
    run.add_argument("--base-url", required=True)
    run.add_argument("--server-pid", type=int, required=True)
    run.add_argument("--sample-interval-seconds", type=float, default=1.0)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    finalize.add_argument("--cleanup-status", required=True)
    finalize.add_argument("--aggregate-exit", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        prepare_artifacts(args.source_payload, args.artifact_dir, args.model_name)
        return 0
    if args.command == "run-cell":
        result = run_cell(
            artifact_dir=args.artifact_dir,
            cell_id=args.cell_id,
            base_url=args.base_url,
            server_pid=args.server_pid,
            sample_interval_seconds=args.sample_interval_seconds,
        )
        return 0 if result["status"] == "success" else 2
    if args.command == "finalize":
        finalize_artifacts(
            artifact_dir=args.artifact_dir,
            cleanup_status=args.cleanup_status,
            aggregate_exit=args.aggregate_exit,
        )
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
