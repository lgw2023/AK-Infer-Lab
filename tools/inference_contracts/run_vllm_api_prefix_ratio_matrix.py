from __future__ import annotations

import argparse
import csv
import json
import math
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.run_vllm_api_concurrency_smoke import (
    DEFAULT_ARTIFACT_ROOT,
    build_server_command,
    pick_free_port,
    stop_process_group,
    wait_for_server_ready,
    write_import_probe,
    write_model_path_precheck,
    write_package_inventory,
    write_server_stats_summary,
)
from tools.inference_contracts.run_vllm_api_streaming_perf import (
    compute_tokens_per_s,
    compute_tpot_us,
    extract_completion_delta,
)

DEFAULT_RUN_ID = "runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031"
DEFAULT_INPUT_CAPS = (8192, 16384, 32768, 65536, 131072)
DEFAULT_PREFIX_RATIOS = (0.30, 0.60, 0.90)
DEFAULT_OUTPUT_TOKENS = 1024
DEFAULT_WARMUP_REQUESTS_PER_CELL = 1
DEFAULT_MEASURED_REQUESTS_PER_CELL = 3
MEMORY_SAMPLE_INTERVAL_SEC = 0.4
POLICY = "long_context_prefix_ratio_matrix_no_bottleneck_claim"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Qwen/vLLM long-context prefix-cache ratio matrix cells via OpenAI streaming API."
    )
    parser.add_argument("--run-id", default=os.environ.get("RUN_ID", DEFAULT_RUN_ID))
    parser.add_argument("--artifact-dir", type=Path, default=None)
    parser.add_argument(
        "--model-path",
        default=os.environ.get("AK_SMALL_MODEL_PATH", "/data/node0_disk1/Public/Qwen3.5-4B"),
    )
    parser.add_argument("--served-model-name", default=os.environ.get("AK_VLLM_SERVED_MODEL_NAME", "Qwen3.5-4B"))
    parser.add_argument("--host", default=os.environ.get("AK_VLLM_API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("AK_VLLM_API_PORT", "0")))
    parser.add_argument("--device-label", default=os.environ.get("AK_VLLM_DEVICE_LABEL", "npu:6"))
    parser.add_argument("--input-caps", default=",".join(str(value) for value in DEFAULT_INPUT_CAPS))
    parser.add_argument("--prefix-ratios", default=",".join(f"{value:.2f}" for value in DEFAULT_PREFIX_RATIOS))
    parser.add_argument("--output-tokens", type=int, default=DEFAULT_OUTPUT_TOKENS)
    parser.add_argument("--warmup-requests-per-cell", type=int, default=DEFAULT_WARMUP_REQUESTS_PER_CELL)
    parser.add_argument("--measured-requests-per-cell", type=int, default=DEFAULT_MEASURED_REQUESTS_PER_CELL)
    parser.add_argument("--mode", choices=["prefix_cache_on", "prefix_cache_off"], required=True)
    parser.add_argument(
        "--gpu-memory-utilization",
        type=float,
        default=float(os.environ.get("AK_VLLM_GPU_MEMORY_UTILIZATION", "0.90")),
    )
    parser.add_argument("--tensor-parallel-size", type=int, default=int(os.environ.get("AK_VLLM_TP_SIZE", "1")))
    parser.add_argument("--dtype", default=os.environ.get("AK_VLLM_DTYPE", "auto"))
    parser.add_argument(
        "--enforce-eager",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("AK_VLLM_ENFORCE_EAGER", "1") != "0",
    )
    parser.add_argument(
        "--server-ready-timeout-sec",
        type=float,
        default=float(os.environ.get("AK_VLLM_API_READY_TIMEOUT_SEC", "1200")),
    )
    parser.add_argument(
        "--request-timeout-sec",
        type=float,
        default=float(os.environ.get("AK_VLLM_API_REQUEST_TIMEOUT_SEC", "7200")),
    )
    parser.add_argument("--sample-memory", action="store_true")
    return parser.parse_args()


def parse_int_csv(text: str) -> tuple[int, ...]:
    values = tuple(int(item.strip()) for item in text.split(",") if item.strip())
    if not values or any(value <= 0 for value in values):
        raise ValueError(f"invalid positive integer CSV: {text!r}")
    return values


def parse_ratio_csv(text: str) -> tuple[float, ...]:
    values = tuple(float(item.strip()) for item in text.split(",") if item.strip())
    if not values or any(value <= 0 or value >= 1 for value in values):
        raise ValueError(f"invalid ratio CSV, values must be between 0 and 1: {text!r}")
    return values


def build_matrix_cells(
    input_caps: tuple[int, ...] = DEFAULT_INPUT_CAPS,
    prefix_ratios: tuple[float, ...] = DEFAULT_PREFIX_RATIOS,
    output_tokens: int = DEFAULT_OUTPUT_TOKENS,
) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for input_cap in input_caps:
        for ratio in prefix_ratios:
            shared_tokens = math.floor(input_cap * ratio)
            ratio_pct = int(round(ratio * 100))
            cells.append(
                {
                    "cell_id": f"cap{input_cap}_prefix{ratio_pct}",
                    "input_cap_tokens": input_cap,
                    "target_prefix_ratio": ratio,
                    "target_prefix_ratio_pct": ratio_pct,
                    "target_shared_prefix_tokens": shared_tokens,
                    "target_unique_suffix_tokens": input_cap - shared_tokens,
                    "output_tokens": output_tokens,
                    "max_model_len": input_cap + output_tokens + 1024,
                }
            )
    return cells


def build_cell_request_specs(
    cell: dict[str, Any],
    warmup_requests_per_cell: int = DEFAULT_WARMUP_REQUESTS_PER_CELL,
    measured_requests_per_cell: int = DEFAULT_MEASURED_REQUESTS_PER_CELL,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for index in range(1, warmup_requests_per_cell + 1):
        specs.append(
            {
                "case_id": f"{cell['cell_id']}_warmup_{index:02d}",
                "request_role": "warmup",
                "request_role_index": index,
                "arrival_delay_ms": 0,
            }
        )
    for index in range(1, measured_requests_per_cell + 1):
        specs.append(
            {
                "case_id": f"{cell['cell_id']}_measured_{index:02d}",
                "request_role": "measured",
                "request_role_index": index,
                "arrival_delay_ms": (index - 1) * 100,
            }
        )
    return specs


def prepare_cell_prompts(tokenizer: Any, cell: dict[str, Any], request_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shared_ids = build_source_token_ids(
        tokenizer,
        label=f"{cell['cell_id']}_shared_prefix",
        min_tokens=int(cell["target_shared_prefix_tokens"]) + 128,
    )[: int(cell["target_shared_prefix_tokens"])]
    prepared: list[dict[str, Any]] = []
    for request_index, spec in enumerate(request_specs, start=1):
        unique_ids = build_source_token_ids(
            tokenizer,
            label=f"{cell['cell_id']}_{spec['request_role']}_{spec['request_role_index']}_unique_suffix",
            min_tokens=int(cell["target_unique_suffix_tokens"]) + 128,
        )[: int(cell["target_unique_suffix_tokens"])]
        combined_ids = shared_ids + unique_ids
        prompt_text = tokenizer.decode(combined_ids, skip_special_tokens=False)
        submitted_ids = tokenize_text(tokenizer, prompt_text)
        actual_shared_ratio = len(shared_ids) / len(submitted_ids) if submitted_ids else 0.0
        prepared.append(
            {
                "spec": spec,
                "prompt": prompt_text,
                "row": {
                    "case_id": spec["case_id"],
                    "mode": "",
                    "cell_id": cell["cell_id"],
                    "request_role": spec["request_role"],
                    "request_role_index": spec["request_role_index"],
                    "input_cap_tokens": cell["input_cap_tokens"],
                    "target_prefix_ratio_pct": cell["target_prefix_ratio_pct"],
                    "target_prefix_ratio": cell["target_prefix_ratio"],
                    "target_shared_prefix_tokens": cell["target_shared_prefix_tokens"],
                    "actual_shared_prefix_token_count": len(shared_ids),
                    "actual_input_token_count": len(submitted_ids),
                    "actual_shared_prefix_ratio_pct": round_number(actual_shared_ratio * 100),
                    "max_model_len": cell["max_model_len"],
                    "max_new_tokens": cell["output_tokens"],
                    "arrival_delay_ms": spec["arrival_delay_ms"],
                    "http_status": 0,
                    "request_start_ns": 0,
                    "first_token_ns": 0,
                    "response_end_ns": 0,
                    "ttft_us": 0,
                    "tpot_us": 0,
                    "decode_wall_us_after_first": 0,
                    "client_wall_us": 0,
                    "output_tokens_per_s": 0.0,
                    "generated_token_count": 0,
                    "stream_text_chunk_count": 0,
                    "stream_inter_chunk_median_us": 0,
                    "finish_reason": "",
                    "status": "pending",
                    "error_type": "",
                    "error": "",
                    "policy": POLICY,
                },
            }
        )
    return prepared


def build_source_token_ids(tokenizer: Any, *, label: str, min_tokens: int) -> list[int]:
    block_index = 0
    token_ids: list[int] = []
    while len(token_ids) < min_tokens:
        block_index += 1
        block_text = "\n".join(
            [
                f"### P1.31 deterministic context block {label} {block_index:05d}",
                "This static fixture simulates coding-agent long-context evidence.",
                f"run_id=synthetic_prefix_ratio_matrix_{label}_{block_index:05d}",
                "Policy: target shared-prefix ratio is controlled by text construction.",
                "Observed prefix cache hit rate must come only from vLLM server stats.",
                "Do not infer bottlenecks, HBM traffic, or cache benefit from this text.",
                "Fields: request_id phase timestamp_ns input_tokens output_tokens rss pss hbm.",
                "The repeated wording is intentional for stable tokenizer pressure.",
            ]
        )
        block_ids = tokenize_text(tokenizer, block_text)
        if not block_ids:
            raise ValueError(
                f"tokenizer produced no tokens for deterministic context block {label!r}"
            )
        token_ids.extend(block_ids)
    return token_ids


def tokenize_text(tokenizer: Any, text: str) -> list[int]:
    token_ids = tokenizer(text, add_special_tokens=False).input_ids
    if token_ids and isinstance(token_ids[0], list):
        token_ids = token_ids[0]
    return list(token_ids)


def run_prefix_ratio_matrix(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir or (DEFAULT_ARTIFACT_ROOT / args.run_id / args.mode)
    cells_dir = artifact_dir / "cells"
    generated_dir = artifact_dir / "generated_texts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    cells_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)

    input_caps = parse_int_csv(args.input_caps)
    prefix_ratios = parse_ratio_csv(args.prefix_ratios)
    cells = build_matrix_cells(input_caps=input_caps, prefix_ratios=prefix_ratios, output_tokens=args.output_tokens)

    write_run_context(artifact_dir / "run_context.txt", args, cells)
    write_package_inventory(artifact_dir / "package_inventory.tsv")
    write_model_path_precheck(artifact_dir / "model_path_precheck.txt", args.model_path)
    import_probe = write_import_probe(artifact_dir / "vllm_import_probe.tsv")

    request_rows: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []
    phase_rows: list[dict[str, Any]] = []
    server_stats_rows: list[dict[str, Any]] = []
    fatal_error = ""

    try:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
        for cell in cells:
            cell_result = run_cell(
                args=args,
                tokenizer=tokenizer,
                cell=cell,
                cell_dir=cells_dir / cell["cell_id"],
                generated_dir=generated_dir,
            )
            request_rows.extend(cell_result["request_rows"])
            cell_rows.append(cell_result["cell_row"])
            phase_rows.extend(cell_result["phase_rows"])
            server_stats_rows.extend(cell_result["server_stats_rows"])
    except Exception:
        fatal_error = traceback.format_exc()

    write_tsv(artifact_dir / "request_summary.tsv", request_rows, REQUEST_FIELDS)
    write_tsv(artifact_dir / "cell_summary.tsv", cell_rows, CELL_FIELDS)
    write_tsv(artifact_dir / "phase_memory_summary.tsv", phase_rows, PHASE_FIELDS)
    write_tsv(artifact_dir / "server_stats_summary.tsv", server_stats_rows, SERVER_STATS_FIELDS)

    expected_cell_count = len(input_caps) * len(prefix_ratios)
    success_cell_count = sum(1 for row in cell_rows if row.get("cell_status") == "success")
    status = (
        "success"
        if not fatal_error and len(cell_rows) == expected_cell_count and success_cell_count == expected_cell_count
        else "failed"
    )
    result = {
        "run_id": args.run_id,
        "mode": args.mode,
        "status": status,
        "model_path": args.model_path,
        "served_model_name": args.served_model_name,
        "request_count": len(request_rows),
        "cell_count": len(cell_rows),
        "expected_cell_count": expected_cell_count,
        "success_cell_count": success_cell_count,
        "failed_cell_count": len(cell_rows) - success_cell_count,
        "output_tokens": args.output_tokens,
        "warmup_requests_per_cell": args.warmup_requests_per_cell,
        "measured_requests_per_cell": args.measured_requests_per_cell,
        "input_caps": list(input_caps),
        "prefix_ratios": list(prefix_ratios),
        "sample_memory": int(args.sample_memory),
        "import_probe": import_probe,
        "policy": POLICY,
        "length_policy": "input_cap_tokens_are_8k_16k_32k_64k_128k_output_tokens_fixed_1024",
        "prefix_ratio_policy": "target_ratio_is_shared_prefix_tokens_div_input_cap_observed_hit_rate_from_vllm_stats_only",
        "memory_policy": "process_group_rss_pss_and_whole_device_hbm_occupancy_not_kv_object_bytes",
        "bottleneck_policy": "no_bottleneck_claim",
        "fatal_error": fatal_error,
        "cell_rows": cell_rows,
    }
    (artifact_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_summary(artifact_dir / "summary.txt", result)
    write_mail_attachment_candidates(artifact_dir)
    return 0 if status == "success" else 1


def run_cell(
    *,
    args: argparse.Namespace,
    tokenizer: Any,
    cell: dict[str, Any],
    cell_dir: Path,
    generated_dir: Path,
) -> dict[str, Any]:
    cell_dir.mkdir(parents=True, exist_ok=True)
    prepared = prepare_cell_prompts(
        tokenizer,
        cell,
        build_cell_request_specs(cell, args.warmup_requests_per_cell, args.measured_requests_per_cell),
    )
    for item in prepared:
        item["row"]["mode"] = args.mode

    cell_args = argparse.Namespace(**vars(args))
    cell_args.max_model_len = int(cell["max_model_len"])
    cell_args.enable_prefix_caching = args.mode == "prefix_cache_on"
    cell_args.port = pick_free_port(args.host) if args.port == 0 else args.port

    server_cmd = build_server_command(cell_args)
    (cell_dir / "vllm_api_server_command.json").write_text(
        json.dumps(server_cmd, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (cell_dir / "cell_context.json").write_text(json.dumps(cell, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    server_log_path = cell_dir / "vllm_api_server.log"
    server_stats_path = cell_dir / "vllm_api_server_stats_summary.tsv"
    server_ready = False
    server_return_code: int | None = None
    server_process: subprocess.Popen[str] | None = None
    cell_error = ""
    memory_samples: list[dict[str, Any]] = []

    try:
        with server_log_path.open("w", encoding="utf-8") as log_handle:
            server_process = subprocess.Popen(
                server_cmd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            server_ready = wait_for_server_ready(
                host=args.host,
                port=cell_args.port,
                process=server_process,
                timeout_sec=args.server_ready_timeout_sec,
            )
            if not server_ready:
                raise RuntimeError("vLLM OpenAI API server did not become ready")

            warmup_items = [item for item in prepared if item["row"]["request_role"] == "warmup"]
            measured_items = [item for item in prepared if item["row"]["request_role"] == "measured"]
            for item in warmup_items:
                result = streaming_request(item=item, args=cell_args)
                apply_streaming_result(item, result, tokenizer, generated_dir)

            sampler = None
            if args.sample_memory and server_process is not None:
                sampler = MemorySampler(
                    root_pid=server_process.pid,
                    device_id=device_id_from_label(args.device_label),
                    samples=memory_samples,
                    interval_sec=MEMORY_SAMPLE_INTERVAL_SEC,
                )
                sampler.start()
            measured_results = run_overlapping_requests(measured_items, cell_args)
            if sampler is not None:
                sampler.stop()
            for item, result in zip(measured_items, measured_results):
                apply_streaming_result(item, result, tokenizer, generated_dir)
    except Exception:
        cell_error = traceback.format_exc()
    finally:
        if server_process is not None:
            server_return_code = stop_process_group(server_process)

    server_stats_summary = write_server_stats_summary(server_log_path, server_stats_path)
    server_stats_rows = read_server_stats_rows(server_stats_path, args.mode, cell)
    request_rows = [item["row"] for item in prepared]
    measured_rows = [row for row in request_rows if row["request_role"] == "measured"]
    warmup_rows = [row for row in request_rows if row["request_role"] == "warmup"]
    measured_success_count = sum(1 for row in measured_rows if row["status"] == "success")
    warmup_success_count = sum(1 for row in warmup_rows if row["status"] == "success")
    generated_mismatch_count = sum(
        1
        for row in measured_rows
        if int(row.get("generated_token_count") or 0) != int(cell["output_tokens"])
    )
    cell_status = (
        "success"
        if not cell_error
        and server_ready
        and warmup_success_count == len(warmup_rows)
        and measured_success_count == len(measured_rows)
        and generated_mismatch_count == 0
        else "failed"
    )
    phase_rows = summarize_phase_memory(
        mode=args.mode,
        cell=cell,
        request_rows=measured_rows,
        samples=memory_samples,
        kv_cache_usage_pct=float(server_stats_summary["max_kv_cache_usage_pct"]),
    )
    write_tsv(cell_dir / "request_summary.tsv", request_rows, REQUEST_FIELDS)
    write_tsv(cell_dir / "phase_memory_summary.tsv", phase_rows, PHASE_FIELDS)
    write_jsonl(cell_dir / "memory_samples.jsonl", memory_samples)

    cell_row = {
        "mode": args.mode,
        "cell_id": cell["cell_id"],
        "input_cap_tokens": cell["input_cap_tokens"],
        "target_prefix_ratio_pct": cell["target_prefix_ratio_pct"],
        "target_shared_prefix_tokens": cell["target_shared_prefix_tokens"],
        "output_tokens": cell["output_tokens"],
        "max_model_len": cell["max_model_len"],
        "server_ready": int(server_ready),
        "server_return_code_after_shutdown": server_return_code if server_return_code is not None else "",
        "warmup_request_count": len(warmup_rows),
        "warmup_success_count": warmup_success_count,
        "measured_request_count": len(measured_rows),
        "measured_success_count": measured_success_count,
        "failed_request_count": len(measured_rows) - measured_success_count,
        "generated_token_count_mismatch_count": generated_mismatch_count,
        "ttft_us_median": stat(measured_rows, "ttft_us", "median"),
        "tpot_us_median": stat(measured_rows, "tpot_us", "median"),
        "client_wall_us_median": stat(measured_rows, "client_wall_us", "median"),
        "output_tokens_per_s_median": stat(measured_rows, "output_tokens_per_s", "median"),
        "server_stats_sample_count": server_stats_summary["sample_count"],
        "server_stats_max_running_reqs": server_stats_summary["max_running_reqs"],
        "server_stats_max_waiting_reqs": server_stats_summary["max_waiting_reqs"],
        "server_stats_max_kv_cache_usage_pct": server_stats_summary["max_kv_cache_usage_pct"],
        "server_stats_max_prefix_cache_hit_rate_pct": server_stats_summary["max_prefix_cache_hit_rate_pct"],
        "target_vs_observed_prefix_hit_rate_delta_pct": round_number(
            float(server_stats_summary["max_prefix_cache_hit_rate_pct"]) - float(cell["target_prefix_ratio_pct"])
        ),
        "memory_sample_count": len(memory_samples),
        "cell_status": cell_status,
        "error": compact_error(cell_error),
        "policy": POLICY,
    }
    (cell_dir / "cell_result.json").write_text(
        json.dumps({"cell_row": cell_row, "request_rows": request_rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "cell_row": cell_row,
        "request_rows": request_rows,
        "phase_rows": phase_rows,
        "server_stats_rows": server_stats_rows,
    }


def run_overlapping_requests(prepared: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = [{} for _ in prepared]
    threads = []
    for index, item in enumerate(prepared):
        thread = threading.Thread(target=request_worker, args=(index, item, args, results), daemon=True)
        threads.append(thread)
        thread.start()
    for thread in threads:
        thread.join(timeout=args.request_timeout_sec + 30)
    return results


def request_worker(index: int, item: dict[str, Any], args: argparse.Namespace, results: list[dict[str, Any]]) -> None:
    time.sleep(int(item["row"]["arrival_delay_ms"]) / 1000)
    results[index] = streaming_request(item=item, args=args)


def streaming_request(*, item: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "model": args.served_model_name,
        "prompt": item["prompt"],
        "max_tokens": int(item["row"]["max_new_tokens"]),
        "temperature": 0,
        "stream": True,
        "min_tokens": int(item["row"]["max_new_tokens"]),
        "ignore_eos": True,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://{args.host}:{args.port}/v1/completions",
        data=data,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    start_ns = time.monotonic_ns()
    generated_parts: list[str] = []
    chunks: list[dict[str, Any]] = []
    first_token_ns = 0
    finish_reason = ""
    usage: dict[str, Any] = {}
    try:
        with urllib.request.urlopen(request, timeout=args.request_timeout_sec) as response:
            http_status = int(response.status)
            for raw_line in response:
                now_ns = time.monotonic_ns()
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data_text = line[5:].strip()
                if data_text == "[DONE]":
                    chunks.append({"event": "done", "timestamp_ns": now_ns})
                    continue
                event = json.loads(data_text)
                choice_text, choice_finish = extract_completion_delta(event)
                if choice_text:
                    if not first_token_ns:
                        first_token_ns = now_ns
                    generated_parts.append(choice_text)
                if choice_finish:
                    finish_reason = choice_finish
                if isinstance(event.get("usage"), dict):
                    usage = event["usage"]
                chunks.append(
                    {
                        "event": "data",
                        "timestamp_ns": now_ns,
                        "text_len": len(choice_text),
                        "finish_reason": choice_finish,
                    }
                )
            return {
                "ok": True,
                "http_status": http_status,
                "request_start_ns": start_ns,
                "first_token_ns": first_token_ns,
                "response_end_ns": time.monotonic_ns(),
                "generated_text": "".join(generated_parts),
                "finish_reason": finish_reason,
                "usage": usage,
                "chunks": chunks,
            }
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "http_status": int(error.code),
            "request_start_ns": start_ns,
            "first_token_ns": first_token_ns,
            "response_end_ns": time.monotonic_ns(),
            "generated_text": "".join(generated_parts),
            "finish_reason": finish_reason,
            "usage": usage,
            "chunks": chunks,
            "error": body,
        }
    except Exception:
        return {
            "ok": False,
            "http_status": 0,
            "request_start_ns": start_ns,
            "first_token_ns": first_token_ns,
            "response_end_ns": time.monotonic_ns(),
            "generated_text": "".join(generated_parts),
            "finish_reason": finish_reason,
            "usage": usage,
            "chunks": chunks,
            "error": traceback.format_exc(),
        }


def apply_streaming_result(item: dict[str, Any], result: dict[str, Any], tokenizer: Any, generated_dir: Path) -> None:
    row = item["row"]
    generated_text = str(result.get("generated_text") or "")
    usage = result.get("usage") or {}
    generated_token_count = int(usage.get("completion_tokens") or 0)
    if generated_token_count <= 0 and generated_text:
        generated_token_count = len(tokenize_text(tokenizer, generated_text))

    start_ns = int(result.get("request_start_ns") or 0)
    first_ns = int(result.get("first_token_ns") or 0)
    end_ns = int(result.get("response_end_ns") or 0)
    chunk_times = [
        int(chunk["timestamp_ns"])
        for chunk in result.get("chunks", [])
        if chunk.get("event") == "data" and int(chunk.get("text_len") or 0) > 0
    ]
    inter_chunk_us = [
        max(0, (chunk_times[pos] - chunk_times[pos - 1]) // 1000)
        for pos in range(1, len(chunk_times))
    ]
    row["http_status"] = int(result.get("http_status") or 0)
    row["request_start_ns"] = start_ns
    row["first_token_ns"] = first_ns
    row["response_end_ns"] = end_ns
    row["ttft_us"] = max(0, (first_ns - start_ns) // 1000) if first_ns and start_ns else 0
    row["client_wall_us"] = max(0, (end_ns - start_ns) // 1000) if end_ns and start_ns else 0
    row["decode_wall_us_after_first"] = max(0, (end_ns - first_ns) // 1000) if end_ns and first_ns else 0
    row["tpot_us"] = compute_tpot_us(first_ns, end_ns, generated_token_count)
    row["output_tokens_per_s"] = compute_tokens_per_s(generated_token_count, int(row["client_wall_us"]))
    row["generated_token_count"] = generated_token_count
    row["stream_text_chunk_count"] = len(chunk_times)
    row["stream_inter_chunk_median_us"] = median_int(inter_chunk_us)
    row["finish_reason"] = str(result.get("finish_reason") or "")
    row["status"] = (
        "success"
        if result.get("ok") and 200 <= row["http_status"] < 300 and generated_token_count > 0 and first_ns > 0
        else "failed"
    )
    row["error_type"] = "" if row["status"] == "success" else "streaming_api_request_failed"
    row["error"] = "" if row["status"] == "success" else compact_error(str(result.get("error") or "missing generation"))

    (generated_dir / f"{row['case_id']}.txt").write_text(generated_text, encoding="utf-8")


class MemorySampler:
    def __init__(self, *, root_pid: int, device_id: str, samples: list[dict[str, Any]], interval_sec: float) -> None:
        self.root_pid = root_pid
        self.device_id = device_id
        self.samples = samples
        self.interval_sec = interval_sec
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            sample = sample_process_group_memory(self.root_pid)
            sample.update(sample_npu_hbm(self.device_id))
            sample["timestamp_ns"] = time.monotonic_ns()
            self.samples.append(sample)
            self._stop.wait(self.interval_sec)


def sample_process_group_memory(root_pid: int) -> dict[str, Any]:
    pids = process_group_pids(root_pid)
    rss_kb = 0
    pss_kb = 0
    for pid in pids:
        rss_kb += read_status_kb(pid, "VmRSS:")
        pss_kb += read_smaps_rollup_kb(pid, "Pss:")
    return {
        "pid_count": len(pids),
        "rss_mb": round_number(rss_kb / 1024),
        "pss_mb": round_number(pss_kb / 1024),
    }


def process_group_pids(root_pid: int) -> list[int]:
    parent_by_pid: dict[int, int] = {}
    for path in Path("/proc").glob("[0-9]*"):
        try:
            text = (path / "stat").read_text(encoding="utf-8", errors="replace")
            after_comm = text.rsplit(")", 1)[1].strip().split()
            parent_by_pid[int(path.name)] = int(after_comm[1])
        except Exception:
            continue
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, parent in parent_by_pid.items():
            if parent in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    return sorted(descendants)


def read_status_kb(pid: int, field: str) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(field):
                return int(line.split()[1])
    except Exception:
        return 0
    return 0


def read_smaps_rollup_kb(pid: int, field: str) -> int:
    try:
        for line in Path(f"/proc/{pid}/smaps_rollup").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(field):
                return int(line.split()[1])
    except Exception:
        return 0
    return 0


def sample_npu_hbm(device_id: str) -> dict[str, Any]:
    try:
        output = subprocess.check_output(
            ["npu-smi", "info", "-t", "usages", "-i", str(device_id)],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
    except Exception:
        return {"hbm_used_mb": 0.0, "hbm_free_mb": 0.0, "hbm_usage_pct": 0.0}
    capacity = first_float_after(output, "HBM Capacity(MB)")
    usage_pct = first_float_after(output, "HBM Usage Rate(%)")
    used = capacity * usage_pct / 100 if capacity and usage_pct else 0.0
    return {
        "hbm_used_mb": round_number(used),
        "hbm_free_mb": round_number(capacity - used) if capacity else 0.0,
        "hbm_usage_pct": round_number(usage_pct),
    }


def first_float_after(text: str, label: str) -> float:
    for line in text.splitlines():
        if label in line:
            numbers = [part for part in line.replace("|", " ").split() if part.replace(".", "", 1).isdigit()]
            if numbers:
                return float(numbers[-1])
    return 0.0


def summarize_phase_memory(
    *,
    mode: str,
    cell: dict[str, Any],
    request_rows: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    kv_cache_usage_pct: float,
) -> list[dict[str, Any]]:
    rows = []
    for phase in ("prefill", "decode"):
        phase_samples = [
            sample
            for sample in samples
            if any(sample_overlaps_phase(int(sample["timestamp_ns"]), row, phase) for row in request_rows)
        ]
        rows.append(
            {
                "mode": mode,
                "cell_id": cell["cell_id"],
                "input_cap_tokens": cell["input_cap_tokens"],
                "target_prefix_ratio_pct": cell["target_prefix_ratio_pct"],
                "phase": phase,
                "sample_count": len(phase_samples),
                "overlapped_request_count": count_overlapped_requests(phase_samples, request_rows, phase),
                "rss_avg_mb": avg_field(phase_samples, "rss_mb"),
                "rss_max_mb": max_field(phase_samples, "rss_mb"),
                "pss_avg_mb": avg_field(phase_samples, "pss_mb"),
                "pss_max_mb": max_field(phase_samples, "pss_mb"),
                "hbm_used_avg_mb": avg_field(phase_samples, "hbm_used_mb"),
                "hbm_used_max_mb": max_field(phase_samples, "hbm_used_mb"),
                "hbm_free_min_mb": min_field(phase_samples, "hbm_free_mb"),
                "hbm_usage_pct_max": max_field(phase_samples, "hbm_usage_pct"),
                "kv_cache_usage_pct_max": round_number(kv_cache_usage_pct),
                "policy": "process_group_rss_pss_and_whole_device_hbm_occupancy_not_kv_object_bytes",
            }
        )
    return rows


def sample_overlaps_phase(timestamp_ns: int, row: dict[str, Any], phase: str) -> bool:
    start = int(row.get("request_start_ns") or 0)
    first = int(row.get("first_token_ns") or 0)
    end = int(row.get("response_end_ns") or 0)
    if phase == "prefill":
        return start > 0 and first > start and start <= timestamp_ns <= first
    return first > 0 and end > first and first <= timestamp_ns <= end


def count_overlapped_requests(samples: list[dict[str, Any]], request_rows: list[dict[str, Any]], phase: str) -> int:
    return sum(
        1
        for row in request_rows
        if any(sample_overlaps_phase(int(sample["timestamp_ns"]), row, phase) for sample in samples)
    )


def read_server_stats_rows(path: Path, mode: str, cell: dict[str, Any]) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    result = []
    for row in rows:
        item = {
            "mode": mode,
            "cell_id": cell["cell_id"],
            "input_cap_tokens": cell["input_cap_tokens"],
            "target_prefix_ratio_pct": cell["target_prefix_ratio_pct"],
        }
        item.update(row)
        result.append(item)
    return result


def write_run_context(path: Path, args: argparse.Namespace, cells: list[dict[str, Any]]) -> None:
    lines = [
        f"run_id={args.run_id}",
        f"commit={git_commit()}",
        f"timestamp={time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        f"hostname={socket.gethostname()}",
        f"python={sys.executable}",
        f"cwd={Path.cwd()}",
        f"MODEL_PATH={args.model_path}",
        f"SERVED_MODEL_NAME={args.served_model_name}",
        f"mode={args.mode}",
        f"input_caps={args.input_caps}",
        f"prefix_ratios={args.prefix_ratios}",
        f"output_tokens={args.output_tokens}",
        f"warmup_requests_per_cell={args.warmup_requests_per_cell}",
        f"measured_requests_per_cell={args.measured_requests_per_cell}",
        f"cell_count={len(cells)}",
        f"gpu_memory_utilization={args.gpu_memory_utilization}",
        f"tensor_parallel_size={args.tensor_parallel_size}",
        f"dtype={args.dtype}",
        f"sample_memory={int(args.sample_memory)}",
        f"ASCEND_RT_VISIBLE_DEVICES={os.environ.get('ASCEND_RT_VISIBLE_DEVICES', '')}",
        f"VLLM_USE_V1={os.environ.get('VLLM_USE_V1', '')}",
        f"VLLM_PLUGINS={os.environ.get('VLLM_PLUGINS', '')}",
        f"VLLM_WORKER_MULTIPROC_METHOD={os.environ.get('VLLM_WORKER_MULTIPROC_METHOD', '')}",
        f"policy={POLICY}",
        "length_policy=input caps are fixed at 8K/16K/32K/64K/128K; output tokens fixed at 1024",
        "prefix_ratio_policy=target shared-prefix ratio is not observed hit rate",
        "bottleneck_policy=no_bottleneck_claim",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(path: Path, result: dict[str, Any]) -> None:
    lines = [
        f"run_id={result['run_id']}",
        f"mode={result['mode']}",
        f"status={result['status']}",
        f"cell_count={result['cell_count']}",
        f"expected_cell_count={result['expected_cell_count']}",
        f"success_cell_count={result['success_cell_count']}",
        f"failed_cell_count={result['failed_cell_count']}",
        f"output_tokens={result['output_tokens']}",
        f"warmup_requests_per_cell={result['warmup_requests_per_cell']}",
        f"measured_requests_per_cell={result['measured_requests_per_cell']}",
        f"policy={result['policy']}",
        f"length_policy={result['length_policy']}",
        f"prefix_ratio_policy={result['prefix_ratio_policy']}",
        f"memory_policy={result['memory_policy']}",
        f"bottleneck_policy={result['bottleneck_policy']}",
        "",
        "## cell_rows",
    ]
    for row in result["cell_rows"]:
        lines.append(
            "\t".join(
                [
                    row["mode"],
                    row["cell_id"],
                    f"cap={row['input_cap_tokens']}",
                    f"target_prefix_pct={row['target_prefix_ratio_pct']}",
                    f"success={row['measured_success_count']}/{row['measured_request_count']}",
                    f"generated_mismatch={row['generated_token_count_mismatch_count']}",
                    f"ttft_median_us={row['ttft_us_median']}",
                    f"tpot_median_us={row['tpot_us_median']}",
                    f"observed_prefix_hit_pct={row['server_stats_max_prefix_cache_hit_rate_pct']}",
                    f"status={row['cell_status']}",
                ]
            )
        )
    if result.get("fatal_error"):
        lines.extend(["", "## fatal_error", compact_error(str(result["fatal_error"]))])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mail_attachment_candidates(artifact_dir: Path) -> None:
    relpaths = [
        "summary.txt",
        "result.json",
        "request_summary.tsv",
        "cell_summary.tsv",
        "phase_memory_summary.tsv",
        "server_stats_summary.tsv",
    ]
    lines = ["path\tsize_bytes\tmail_ok"]
    for relpath in relpaths:
        path = artifact_dir / relpath
        if path.exists():
            size = path.stat().st_size
            lines.append(f"{path}\t{size}\t{str(size <= 70 * 1024).lower()}")
    (artifact_dir / "mail_attachment_candidates.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def stat(rows: list[dict[str, Any]], field: str, kind: str) -> float:
    values = [float(row.get(field) or 0) for row in rows if float(row.get(field) or 0) > 0]
    if not values:
        return 0.0
    values = sorted(values)
    if kind == "median":
        middle = len(values) // 2
        return round_number(values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2)
    raise ValueError(kind)


def median_int(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    middle = len(ordered) // 2
    return int(ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2)


def avg_field(rows: list[dict[str, Any]], field: str) -> float:
    values = [float(row.get(field) or 0) for row in rows if float(row.get(field) or 0) > 0]
    return round_number(mean(values)) if values else 0.0


def max_field(rows: list[dict[str, Any]], field: str) -> float:
    values = [float(row.get(field) or 0) for row in rows if float(row.get(field) or 0) > 0]
    return round_number(max(values)) if values else 0.0


def min_field(rows: list[dict[str, Any]], field: str) -> float:
    values = [float(row.get(field) or 0) for row in rows if float(row.get(field) or 0) > 0]
    return round_number(min(values)) if values else 0.0


def compact_error(text: str) -> str:
    return text.replace("\n", "\\n")[:2000]


def round_number(value: float) -> float:
    return round(float(value), 6)


def device_id_from_label(label: str) -> str:
    if ":" in label:
        return label.rsplit(":", 1)[1]
    return label


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return ""


REQUEST_FIELDS = [
    "case_id",
    "mode",
    "cell_id",
    "request_role",
    "request_role_index",
    "input_cap_tokens",
    "target_prefix_ratio_pct",
    "target_prefix_ratio",
    "target_shared_prefix_tokens",
    "actual_shared_prefix_token_count",
    "actual_input_token_count",
    "actual_shared_prefix_ratio_pct",
    "max_model_len",
    "max_new_tokens",
    "arrival_delay_ms",
    "http_status",
    "request_start_ns",
    "first_token_ns",
    "response_end_ns",
    "ttft_us",
    "tpot_us",
    "decode_wall_us_after_first",
    "client_wall_us",
    "output_tokens_per_s",
    "generated_token_count",
    "stream_text_chunk_count",
    "stream_inter_chunk_median_us",
    "finish_reason",
    "status",
    "error_type",
    "error",
    "policy",
]

CELL_FIELDS = [
    "mode",
    "cell_id",
    "input_cap_tokens",
    "target_prefix_ratio_pct",
    "target_shared_prefix_tokens",
    "output_tokens",
    "max_model_len",
    "server_ready",
    "server_return_code_after_shutdown",
    "warmup_request_count",
    "warmup_success_count",
    "measured_request_count",
    "measured_success_count",
    "failed_request_count",
    "generated_token_count_mismatch_count",
    "ttft_us_median",
    "tpot_us_median",
    "client_wall_us_median",
    "output_tokens_per_s_median",
    "server_stats_sample_count",
    "server_stats_max_running_reqs",
    "server_stats_max_waiting_reqs",
    "server_stats_max_kv_cache_usage_pct",
    "server_stats_max_prefix_cache_hit_rate_pct",
    "target_vs_observed_prefix_hit_rate_delta_pct",
    "memory_sample_count",
    "cell_status",
    "error",
    "policy",
]

PHASE_FIELDS = [
    "mode",
    "cell_id",
    "input_cap_tokens",
    "target_prefix_ratio_pct",
    "phase",
    "sample_count",
    "overlapped_request_count",
    "rss_avg_mb",
    "rss_max_mb",
    "pss_avg_mb",
    "pss_max_mb",
    "hbm_used_avg_mb",
    "hbm_used_max_mb",
    "hbm_free_min_mb",
    "hbm_usage_pct_max",
    "kv_cache_usage_pct_max",
    "policy",
]

SERVER_STATS_FIELDS = [
    "mode",
    "cell_id",
    "input_cap_tokens",
    "target_prefix_ratio_pct",
    "line_number",
    "avg_prompt_throughput_tokens_s",
    "avg_generation_throughput_tokens_s",
    "running_reqs",
    "waiting_reqs",
    "gpu_kv_cache_usage_pct",
    "prefix_cache_hit_rate_pct",
]


def main() -> int:
    return run_prefix_ratio_matrix(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
