from __future__ import annotations

import argparse
import csv
import json
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
from statistics import median
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.run_vllm_api_concurrency_smoke import (
    DEFAULT_ARTIFACT_ROOT,
    DEFAULT_CONTRACT_DIR,
    DEFAULT_LONG_MANIFEST,
    build_server_command,
    default_max_model_len_for,
    load_prompt_index,
    pick_free_port,
    prepare_case,
    select_cases,
    stop_process_group,
    wait_for_server_ready,
    write_import_probe,
    write_model_path_precheck,
    write_package_inventory,
    write_server_stats_summary,
)

DEFAULT_RUN_ID = "runtime_vllm_api_streaming_perf_2026_0708_p1_029"
PERFORMANCE_POLICY = "streaming_client_latency_metrics_no_bottleneck_claim"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded vLLM OpenAI API streaming completion performance probe."
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
    parser.add_argument("--contract-dir", type=Path, default=DEFAULT_CONTRACT_DIR)
    parser.add_argument("--long-manifest", type=Path, default=DEFAULT_LONG_MANIFEST)
    parser.add_argument(
        "--case-plan",
        choices=["three_request_smoke", "burst8", "continuous16_mixed", "continuous32_mixed"],
        default=os.environ.get("AK_VLLM_API_CASE_PLAN", "continuous16_mixed"),
    )
    parser.add_argument("--max-model-len", type=int, default=None)
    parser.add_argument(
        "--gpu-memory-utilization",
        type=float,
        default=float(os.environ.get("AK_VLLM_GPU_MEMORY_UTILIZATION", "0.85")),
    )
    parser.add_argument("--tensor-parallel-size", type=int, default=int(os.environ.get("AK_VLLM_TP_SIZE", "1")))
    parser.add_argument("--dtype", default=os.environ.get("AK_VLLM_DTYPE", "auto"))
    parser.add_argument(
        "--enforce-eager",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("AK_VLLM_ENFORCE_EAGER", "1") != "0",
    )
    parser.add_argument(
        "--enable-prefix-caching",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("AK_VLLM_ENABLE_PREFIX_CACHING", "1") != "0",
    )
    parser.add_argument(
        "--server-ready-timeout-sec",
        type=float,
        default=float(os.environ.get("AK_VLLM_API_READY_TIMEOUT_SEC", "600")),
    )
    parser.add_argument(
        "--request-timeout-sec",
        type=float,
        default=float(os.environ.get("AK_VLLM_API_REQUEST_TIMEOUT_SEC", "600")),
    )
    parser.add_argument(
        "--min-tokens",
        type=int,
        default=int(os.environ["AK_VLLM_API_MIN_TOKENS"])
        if os.environ.get("AK_VLLM_API_MIN_TOKENS")
        else None,
    )
    parser.add_argument(
        "--ignore-eos",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("AK_VLLM_API_IGNORE_EOS", "0") == "1",
    )
    parser.add_argument(
        "--stream-include-usage",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("AK_VLLM_API_STREAM_INCLUDE_USAGE", "0") == "1",
        help="Request stream_options.include_usage when the server supports it.",
    )
    args = parser.parse_args()
    if args.max_model_len is None:
        env_max_model_len = os.environ.get("AK_VLLM_MAX_MODEL_LEN")
        args.max_model_len = int(env_max_model_len) if env_max_model_len else default_max_model_len_for(args.case_plan)
    return args


def run_streaming_perf(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir or (DEFAULT_ARTIFACT_ROOT / args.run_id)
    generated_dir = artifact_dir / "generated_texts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)

    selected_cases = select_cases(args.case_plan)
    args.port = args.port or pick_free_port(args.host)
    write_run_context(artifact_dir / "run_context.txt", args, selected_cases)
    write_package_inventory(artifact_dir / "package_inventory.tsv")
    write_model_path_precheck(artifact_dir / "model_path_precheck.txt", args.model_path)
    import_probe = write_import_probe(artifact_dir / "vllm_import_probe.tsv")

    summary_path = artifact_dir / "vllm_api_streaming_perf_summary.tsv"
    result_path = artifact_dir / "vllm_api_streaming_perf_result.json"
    server_cmd_path = artifact_dir / "vllm_api_server_command.json"
    server_log_path = artifact_dir / "vllm_api_server.log"
    server_stats_path = artifact_dir / "vllm_api_server_stats_summary.tsv"
    event_path = artifact_dir / "vllm_api_streaming_events.jsonl"

    rows: list[dict[str, Any]] = []
    stream_events: list[dict[str, Any]] = []
    fatal_error = ""
    server_ready = False
    server_return_code: int | None = None
    server_process: subprocess.Popen[str] | None = None

    try:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
        prompt_index = load_prompt_index(args.contract_dir, args.long_manifest)
        prepared = [
            prepare_case(tokenizer=tokenizer, prompt_index=prompt_index, case=case, request_index=index)
            for index, case in enumerate(selected_cases, start=1)
        ]
        rows = [item["row"] for item in prepared]

        server_cmd = build_server_command(args)
        server_cmd_path.write_text(json.dumps(server_cmd, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
                port=args.port,
                process=server_process,
                timeout_sec=args.server_ready_timeout_sec,
            )
            if not server_ready:
                raise RuntimeError("vLLM OpenAI API server did not become ready")

            client_results = run_overlapping_streaming_requests(prepared=prepared, args=args)

        apply_streaming_results(
            rows=rows,
            prepared=prepared,
            client_results=client_results,
            tokenizer=tokenizer,
            generated_dir=generated_dir,
        )
        stream_events = build_stream_events(args.run_id, rows, client_results)
    except Exception:
        fatal_error = traceback.format_exc()
    finally:
        if server_process is not None:
            server_return_code = stop_process_group(server_process)

    server_stats_summary = write_server_stats_summary(server_log_path, server_stats_path)
    write_tsv(summary_path, rows, STREAMING_SUMMARY_FIELDS)
    write_jsonl(event_path, stream_events)

    success_count = sum(1 for row in rows if row.get("status") == "success")
    failed_count = len(rows) - success_count
    generated_mismatch_count = sum(
        1
        for row in rows
        if int(row.get("generated_token_count") or 0) != int(row.get("max_new_tokens") or 0)
    )
    latency = summarize_latency(rows)
    status = (
        "success"
        if not fatal_error
        and server_ready
        and len(rows) == len(selected_cases)
        and failed_count == 0
        and generated_mismatch_count == 0
        else "failed"
    )
    result = {
        "run_id": args.run_id,
        "status": status,
        "model_path": args.model_path,
        "served_model_name": args.served_model_name,
        "device_label": args.device_label,
        "host": args.host,
        "port": args.port,
        "case_plan": args.case_plan,
        "request_count": len(selected_cases),
        "success_case_count": success_count,
        "failed_case_count": failed_count,
        "generated_token_count_mismatch_count": generated_mismatch_count,
        "prefix_cache_requested": int(args.enable_prefix_caching),
        "request_min_tokens": args.min_tokens,
        "request_ignore_eos": int(args.ignore_eos),
        "stream_include_usage": int(args.stream_include_usage),
        "server_ready": int(server_ready),
        "server_return_code_after_shutdown": server_return_code,
        "server_stats_sample_count": server_stats_summary["sample_count"],
        "server_stats_max_running_reqs": server_stats_summary["max_running_reqs"],
        "server_stats_max_waiting_reqs": server_stats_summary["max_waiting_reqs"],
        "server_stats_max_kv_cache_usage_pct": server_stats_summary["max_kv_cache_usage_pct"],
        "server_stats_max_prefix_cache_hit_rate_pct": server_stats_summary["max_prefix_cache_hit_rate_pct"],
        "latency_summary": latency,
        "fatal_error": fatal_error,
        "import_probe": import_probe,
        "policy": PERFORMANCE_POLICY,
        "ttft_policy": "host_client_stream_first_nonempty_text_chunk",
        "tpot_policy": "host_client_response_end_minus_first_token_div_generated_tokens_minus_one",
        "throughput_policy": "client_wall_generated_tokens_per_second",
        "bottleneck_policy": "no_bottleneck_claim",
        "rows": rows,
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_brief_summary(artifact_dir / "summary.txt", result)
    write_mail_attachment_candidates(artifact_dir)
    return 0 if status == "success" else 1


def run_overlapping_streaming_requests(
    *,
    prepared: list[dict[str, Any]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = [{} for _ in prepared]
    threads = []
    base_url = f"http://{args.host}:{args.port}/v1/completions"
    for index, item in enumerate(prepared):
        thread = threading.Thread(
            target=streaming_request_worker,
            args=(index, item, args, base_url, results),
            daemon=True,
        )
        threads.append(thread)
        thread.start()
    for thread in threads:
        thread.join(timeout=args.request_timeout_sec + 30)
    return results


def streaming_request_worker(
    index: int,
    item: dict[str, Any],
    args: argparse.Namespace,
    url: str,
    results: list[dict[str, Any]],
) -> None:
    time.sleep(int(item["case"]["arrival_delay_ms"]) / 1000)
    payload = build_streaming_payload(args, item)
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    start_ns = time.monotonic_ns()
    chunks: list[dict[str, Any]] = []
    generated_parts: list[str] = []
    finish_reason = ""
    usage: dict[str, Any] = {}
    first_token_ns = 0
    try:
        with urllib.request.urlopen(request, timeout=args.request_timeout_sec) as response:
            http_status = int(response.status)
            for raw_line in response:
                now_ns = time.monotonic_ns()
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                data_text = line[5:].strip()
                if data_text == "[DONE]":
                    chunks.append({"event": "done", "timestamp_ns": now_ns})
                    continue
                try:
                    event = json.loads(data_text)
                except json.JSONDecodeError:
                    chunks.append({"event": "decode_error", "timestamp_ns": now_ns, "raw": data_text[:500]})
                    continue
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
            end_ns = time.monotonic_ns()
            results[index] = {
                "ok": True,
                "http_status": http_status,
                "request_start_ns": start_ns,
                "first_token_ns": first_token_ns,
                "response_end_ns": end_ns,
                "generated_text": "".join(generated_parts),
                "finish_reason": finish_reason,
                "usage": usage,
                "chunks": chunks,
            }
    except urllib.error.HTTPError as error:
        end_ns = time.monotonic_ns()
        body = error.read().decode("utf-8", errors="replace")
        results[index] = {
            "ok": False,
            "http_status": int(error.code),
            "request_start_ns": start_ns,
            "first_token_ns": first_token_ns,
            "response_end_ns": end_ns,
            "generated_text": "".join(generated_parts),
            "finish_reason": finish_reason,
            "usage": usage,
            "chunks": chunks,
            "error": body,
        }
    except Exception:
        end_ns = time.monotonic_ns()
        results[index] = {
            "ok": False,
            "http_status": 0,
            "request_start_ns": start_ns,
            "first_token_ns": first_token_ns,
            "response_end_ns": end_ns,
            "generated_text": "".join(generated_parts),
            "finish_reason": finish_reason,
            "usage": usage,
            "chunks": chunks,
            "error": traceback.format_exc(),
        }


def build_streaming_payload(args: argparse.Namespace, item: dict[str, Any]) -> dict[str, Any]:
    row = item["row"]
    payload = {
        "model": args.served_model_name,
        "prompt": item["selected_text"],
        "max_tokens": int(row["max_new_tokens"]),
        "temperature": 0,
        "stream": True,
    }
    if args.stream_include_usage:
        payload["stream_options"] = {"include_usage": True}
    if args.min_tokens is not None:
        payload["min_tokens"] = int(args.min_tokens)
    if args.ignore_eos:
        payload["ignore_eos"] = True
    return payload


def extract_completion_delta(event: dict[str, Any]) -> tuple[str, str]:
    choices = event.get("choices") or []
    if not choices:
        return "", ""
    choice = choices[0] or {}
    text = choice.get("text")
    if text is None and isinstance(choice.get("delta"), dict):
        text = choice["delta"].get("content")
    finish_reason = choice.get("finish_reason")
    return str(text or ""), str(finish_reason or "")


def apply_streaming_results(
    *,
    rows: list[dict[str, Any]],
    prepared: list[dict[str, Any]],
    client_results: list[dict[str, Any]],
    tokenizer: Any,
    generated_dir: Path,
) -> None:
    for index, row in enumerate(rows):
        case_id = row["case_id"]
        result = client_results[index] if index < len(client_results) else {}
        generated_text = str(result.get("generated_text") or "")
        usage = result.get("usage") or {}
        generated_token_count = int(usage.get("completion_tokens") or 0)
        if generated_token_count <= 0 and generated_text:
            token_ids = tokenizer(generated_text, add_special_tokens=False).input_ids
            if token_ids and isinstance(token_ids[0], list):
                token_ids = token_ids[0]
            generated_token_count = len(token_ids)

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
        row["generated_token_count"] = generated_token_count
        row["stream_text_chunk_count"] = len(chunk_times)
        row["stream_inter_chunk_count"] = len(inter_chunk_us)
        row["stream_inter_chunk_mean_us"] = round_number(mean(inter_chunk_us)) if inter_chunk_us else 0
        row["stream_inter_chunk_median_us"] = round_number(median(inter_chunk_us)) if inter_chunk_us else 0
        row["stream_inter_chunk_p95_us"] = percentile(inter_chunk_us, 95) if inter_chunk_us else 0
        row["tpot_us"] = compute_tpot_us(first_ns, end_ns, generated_token_count)
        row["output_tokens_per_s"] = compute_tokens_per_s(generated_token_count, row["client_wall_us"])
        row["finish_reason"] = str(result.get("finish_reason") or "")
        row["generated_text_nonempty"] = int(bool(generated_text))
        row["stream_usage_completion_tokens"] = int(usage.get("completion_tokens") or 0)
        row["status"] = (
            "success"
            if result.get("ok") and 200 <= row["http_status"] < 300 and generated_token_count > 0 and first_ns > 0
            else "failed"
        )
        if row["status"] != "success":
            row["error_type"] = row.get("error_type") or "streaming_api_request_failed"
            row["error"] = str(result.get("error") or "missing first token or generated tokens")
        else:
            row["error_type"] = ""
            row["error"] = ""

        (generated_dir / f"{case_id}.txt").write_text(generated_text, encoding="utf-8")
        response_record = {
            key: value
            for key, value in result.items()
            if key not in {"generated_text", "chunks"}
        }
        response_record["chunk_count"] = len(result.get("chunks", []))
        (generated_dir / f"{case_id}_stream_response.json").write_text(
            json.dumps(response_record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def compute_tpot_us(first_token_ns: int, response_end_ns: int, generated_token_count: int) -> int:
    if not first_token_ns or response_end_ns <= first_token_ns or generated_token_count <= 1:
        return 0
    return max(0, (response_end_ns - first_token_ns) // max(1, generated_token_count - 1) // 1000)


def compute_tokens_per_s(generated_token_count: int, client_wall_us: int) -> float:
    if generated_token_count <= 0 or client_wall_us <= 0:
        return 0.0
    return round_number(generated_token_count / (client_wall_us / 1_000_000))


def summarize_latency(rows: list[dict[str, Any]]) -> dict[str, Any]:
    success_rows = [row for row in rows if row.get("status") == "success"]
    fields = ("ttft_us", "tpot_us", "client_wall_us", "output_tokens_per_s")
    summary: dict[str, Any] = {"success_request_count": len(success_rows)}
    for field in fields:
        values = [float(row.get(field) or 0) for row in success_rows if float(row.get(field) or 0) > 0]
        summary[f"{field}_min"] = round_number(min(values)) if values else 0
        summary[f"{field}_median"] = round_number(median(values)) if values else 0
        summary[f"{field}_p95"] = percentile(values, 95) if values else 0
        summary[f"{field}_max"] = round_number(max(values)) if values else 0
    total_generated = sum(int(row.get("generated_token_count") or 0) for row in success_rows)
    total_wall_us = sum(int(row.get("client_wall_us") or 0) for row in success_rows)
    summary["total_generated_token_count"] = total_generated
    summary["aggregate_client_generated_tokens_per_s"] = compute_tokens_per_s(total_generated, total_wall_us)
    return summary


def build_stream_events(run_id: str, rows: list[dict[str, Any]], client_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row, result in zip(rows, client_results):
        for index, chunk in enumerate(result.get("chunks", []), start=1):
            if chunk.get("event") != "data":
                continue
            events.append(
                {
                    "run_id": run_id,
                    "case_id": row.get("case_id", ""),
                    "prompt_id": row.get("prompt_id", ""),
                    "prefix_reuse_group": row.get("prefix_reuse_group", ""),
                    "chunk_index": index,
                    "timestamp_ns": chunk.get("timestamp_ns", 0),
                    "text_len": chunk.get("text_len", 0),
                    "finish_reason": chunk.get("finish_reason", ""),
                    "policy": PERFORMANCE_POLICY,
                }
            )
    return events


STREAMING_SUMMARY_FIELDS = [
    "case_id",
    "prompt_id",
    "endpoint",
    "concurrency_group",
    "prefix_reuse_group",
    "arrival_delay_ms",
    "cap_tokens",
    "max_new_tokens",
    "input_token_count",
    "submitted_input_token_count",
    "http_status",
    "ttft_us",
    "tpot_us",
    "decode_wall_us_after_first",
    "client_wall_us",
    "output_tokens_per_s",
    "generated_token_count",
    "stream_text_chunk_count",
    "stream_inter_chunk_count",
    "stream_inter_chunk_mean_us",
    "stream_inter_chunk_median_us",
    "stream_inter_chunk_p95_us",
    "finish_reason",
    "status",
    "error_type",
    "error",
]


def write_run_context(path: Path, args: argparse.Namespace, selected_cases: list[dict[str, Any]]) -> None:
    lines = [
        f"run_id={args.run_id}",
        f"commit={git_commit()}",
        f"timestamp={time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        f"hostname={socket.gethostname()}",
        f"python={sys.executable}",
        f"cwd={Path.cwd()}",
        f"MODEL_PATH={args.model_path}",
        f"SERVED_MODEL_NAME={args.served_model_name}",
        f"API_HOST={args.host}",
        f"API_PORT={args.port}",
        f"CASE_PLAN={args.case_plan}",
        f"DEVICE_LABEL={args.device_label}",
        f"CONTRACT_DIR={args.contract_dir}",
        f"LONG_MANIFEST={args.long_manifest}",
        f"ASCEND_RT_VISIBLE_DEVICES={os.environ.get('ASCEND_RT_VISIBLE_DEVICES', '')}",
        f"VLLM_USE_V1={os.environ.get('VLLM_USE_V1', '')}",
        f"VLLM_PLUGINS={os.environ.get('VLLM_PLUGINS', '')}",
        f"VLLM_WORKER_MULTIPROC_METHOD={os.environ.get('VLLM_WORKER_MULTIPROC_METHOD', '')}",
        f"max_model_len={args.max_model_len}",
        f"gpu_memory_utilization={args.gpu_memory_utilization}",
        f"tensor_parallel_size={args.tensor_parallel_size}",
        f"dtype={args.dtype}",
        f"enforce_eager={int(args.enforce_eager)}",
        f"enable_prefix_caching={int(args.enable_prefix_caching)}",
        f"request_min_tokens={args.min_tokens}",
        f"request_ignore_eos={int(args.ignore_eos)}",
        f"stream_include_usage={int(args.stream_include_usage)}",
        f"request_count={len(selected_cases)}",
        "selected_cases="
        + ",".join(
            f"{case['prompt_id']}@{case['cap_tokens']}+{case['max_new_tokens']}+delay{case['arrival_delay_ms']}ms"
            for case in selected_cases
        ),
        f"performance_policy={PERFORMANCE_POLICY}",
        "ttft_policy=host_client_stream_first_nonempty_text_chunk",
        "tpot_policy=host_client_response_end_minus_first_token_div_generated_tokens_minus_one",
        "bottleneck_policy=no_bottleneck_claim",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_brief_summary(path: Path, result: dict[str, Any]) -> None:
    latency = result["latency_summary"]
    keys = [
        "run_id",
        "status",
        "model_path",
        "case_plan",
        "request_count",
        "success_case_count",
        "failed_case_count",
        "generated_token_count_mismatch_count",
        "prefix_cache_requested",
        "request_min_tokens",
        "request_ignore_eos",
        "server_stats_max_running_reqs",
        "server_stats_max_waiting_reqs",
        "server_stats_max_kv_cache_usage_pct",
        "server_stats_max_prefix_cache_hit_rate_pct",
        "policy",
        "ttft_policy",
        "tpot_policy",
        "bottleneck_policy",
    ]
    lines = [f"{key}={result.get(key, '')}" for key in keys]
    lines.append("## latency_summary")
    for key in sorted(latency):
        lines.append(f"{key}={latency[key]}")
    if result.get("fatal_error"):
        lines.append("## fatal_error")
        lines.append(str(result["fatal_error"]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mail_attachment_candidates(artifact_dir: Path) -> None:
    relpaths = [
        "summary.txt",
        "run_context.txt",
        "vllm_api_streaming_perf_summary.tsv",
        "vllm_api_streaming_perf_result.json",
        "vllm_api_server_stats_summary.tsv",
    ]
    lines = ["path\tsize_bytes\tmail_ok"]
    for relpath in relpaths:
        path = artifact_dir / relpath
        if not path.exists():
            continue
        size = path.stat().st_size
        lines.append(f"{path}\t{size}\t{str(size <= 70 * 1024).lower()}")
    (artifact_dir / "mail_attachment_candidates.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def percentile(values: list[float] | list[int], pct: int) -> float:
    if not values:
        return 0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return round_number(ordered[0])
    rank = (pct / 100) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return round_number(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def mean(values: list[int]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def round_number(value: float) -> float:
    return round(float(value), 6)


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return ""


def main() -> int:
    return run_streaming_perf(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
