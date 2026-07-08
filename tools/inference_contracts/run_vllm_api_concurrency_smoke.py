from __future__ import annotations

import argparse
import importlib
import importlib.metadata as metadata
import importlib.util
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.validation import validate_trace_fixture


DEFAULT_RUN_ID = "runtime_vllm_api_concurrency_smoke_2026_0706_p1_018"
DEFAULT_CONTRACT_DIR = REPO_ROOT / "工作记录与进度笔记本" / "p1_inference_contracts"
DEFAULT_LONG_MANIFEST = DEFAULT_CONTRACT_DIR / "workload_long_manifest.yaml"
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "工作记录与进度笔记本" / "runtime_trace_smokes"

VLLM_API_CONCURRENCY_CASES = [
    {
        "case_id": "P007_api_prefix_first_cap4096_gen32",
        "prompt_id": "P007",
        "cap_tokens": 4096,
        "max_new_tokens": 32,
        "arrival_delay_ms": 0,
        "concurrency_group": "api_concurrency_smoke_0001",
        "prefix_reuse_group": "prefix_group_a",
    },
    {
        "case_id": "P008_api_prefix_second_cap4096_gen32",
        "prompt_id": "P008",
        "cap_tokens": 4096,
        "max_new_tokens": 32,
        "arrival_delay_ms": 100,
        "concurrency_group": "api_concurrency_smoke_0001",
        "prefix_reuse_group": "prefix_group_a",
    },
    {
        "case_id": "P012_api_continuous_candidate_cap4096_gen32",
        "prompt_id": "P012",
        "cap_tokens": 4096,
        "max_new_tokens": 32,
        "arrival_delay_ms": 200,
        "concurrency_group": "api_concurrency_smoke_0001",
        "prefix_reuse_group": "continuous_prefix_a",
    },
]

VLLM_API_BURST_QUEUE_CASES = [
    {
        "case_id": "P007_api_burst_prefix_first_cap4096_gen32",
        "prompt_id": "P007",
        "cap_tokens": 4096,
        "max_new_tokens": 32,
        "arrival_delay_ms": 0,
        "concurrency_group": "api_burst_queue_smoke_0001",
        "prefix_reuse_group": "prefix_group_a",
    },
    {
        "case_id": "P008_api_burst_prefix_second_cap4096_gen32",
        "prompt_id": "P008",
        "cap_tokens": 4096,
        "max_new_tokens": 32,
        "arrival_delay_ms": 100,
        "concurrency_group": "api_burst_queue_smoke_0001",
        "prefix_reuse_group": "prefix_group_a",
    },
    {
        "case_id": "P011_api_burst_001_cap4096_gen32",
        "prompt_id": "P011",
        "cap_tokens": 4096,
        "max_new_tokens": 32,
        "arrival_delay_ms": 200,
        "concurrency_group": "api_burst_queue_smoke_0001",
        "prefix_reuse_group": "burst_prefix_a",
    },
    {
        "case_id": "P011_api_burst_002_cap4096_gen32",
        "prompt_id": "P011",
        "cap_tokens": 4096,
        "max_new_tokens": 32,
        "arrival_delay_ms": 300,
        "concurrency_group": "api_burst_queue_smoke_0001",
        "prefix_reuse_group": "burst_prefix_a",
    },
    {
        "case_id": "P011_api_burst_003_cap4096_gen32",
        "prompt_id": "P011",
        "cap_tokens": 4096,
        "max_new_tokens": 32,
        "arrival_delay_ms": 400,
        "concurrency_group": "api_burst_queue_smoke_0001",
        "prefix_reuse_group": "burst_prefix_a",
    },
    {
        "case_id": "P012_api_continuous_001_cap4096_gen32",
        "prompt_id": "P012",
        "cap_tokens": 4096,
        "max_new_tokens": 32,
        "arrival_delay_ms": 500,
        "concurrency_group": "api_burst_queue_smoke_0001",
        "prefix_reuse_group": "continuous_prefix_a",
    },
    {
        "case_id": "P012_api_continuous_002_cap4096_gen32",
        "prompt_id": "P012",
        "cap_tokens": 4096,
        "max_new_tokens": 32,
        "arrival_delay_ms": 600,
        "concurrency_group": "api_burst_queue_smoke_0001",
        "prefix_reuse_group": "continuous_prefix_a",
    },
    {
        "case_id": "P012_api_continuous_003_cap4096_gen32",
        "prompt_id": "P012",
        "cap_tokens": 4096,
        "max_new_tokens": 32,
        "arrival_delay_ms": 700,
        "concurrency_group": "api_burst_queue_smoke_0001",
        "prefix_reuse_group": "continuous_prefix_a",
    },
]

VLLM_API_CONTINUOUS16_MIXED_CASES = [
    {
        "case_id": "P007_api_continuous16_prefix_first_cap8192_gen64",
        "prompt_id": "P007",
        "cap_tokens": 8192,
        "max_new_tokens": 64,
        "arrival_delay_ms": 0,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "prefix_group_a",
    },
    {
        "case_id": "P008_api_continuous16_prefix_second_cap8192_gen64",
        "prompt_id": "P008",
        "cap_tokens": 8192,
        "max_new_tokens": 64,
        "arrival_delay_ms": 100,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "prefix_group_a",
    },
    {
        "case_id": "P011_api_continuous16_burst_001_cap4096_gen64",
        "prompt_id": "P011",
        "cap_tokens": 4096,
        "max_new_tokens": 64,
        "arrival_delay_ms": 200,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "burst_prefix_a",
    },
    {
        "case_id": "P011_api_continuous16_burst_002_cap4096_gen64",
        "prompt_id": "P011",
        "cap_tokens": 4096,
        "max_new_tokens": 64,
        "arrival_delay_ms": 300,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "burst_prefix_a",
    },
    {
        "case_id": "P011_api_continuous16_burst_003_cap4096_gen64",
        "prompt_id": "P011",
        "cap_tokens": 4096,
        "max_new_tokens": 64,
        "arrival_delay_ms": 400,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "burst_prefix_a",
    },
    {
        "case_id": "P011_api_continuous16_burst_004_cap4096_gen64",
        "prompt_id": "P011",
        "cap_tokens": 4096,
        "max_new_tokens": 64,
        "arrival_delay_ms": 500,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "burst_prefix_a",
    },
    {
        "case_id": "P012_api_continuous16_001_cap8192_gen64",
        "prompt_id": "P012",
        "cap_tokens": 8192,
        "max_new_tokens": 64,
        "arrival_delay_ms": 600,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "continuous_prefix_a",
    },
    {
        "case_id": "P012_api_continuous16_002_cap8192_gen64",
        "prompt_id": "P012",
        "cap_tokens": 8192,
        "max_new_tokens": 64,
        "arrival_delay_ms": 800,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "continuous_prefix_a",
    },
    {
        "case_id": "P012_api_continuous16_003_cap8192_gen64",
        "prompt_id": "P012",
        "cap_tokens": 8192,
        "max_new_tokens": 64,
        "arrival_delay_ms": 1000,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "continuous_prefix_a",
    },
    {
        "case_id": "P012_api_continuous16_004_cap8192_gen64",
        "prompt_id": "P012",
        "cap_tokens": 8192,
        "max_new_tokens": 64,
        "arrival_delay_ms": 1200,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "continuous_prefix_a",
    },
    {
        "case_id": "P012_api_continuous16_005_cap8192_gen64",
        "prompt_id": "P012",
        "cap_tokens": 8192,
        "max_new_tokens": 64,
        "arrival_delay_ms": 1400,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "continuous_prefix_a",
    },
    {
        "case_id": "P012_api_continuous16_006_cap8192_gen64",
        "prompt_id": "P012",
        "cap_tokens": 8192,
        "max_new_tokens": 64,
        "arrival_delay_ms": 1600,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "continuous_prefix_a",
    },
    {
        "case_id": "P003_api_continuous16_system_001_cap8192_gen64",
        "prompt_id": "P003",
        "cap_tokens": 8192,
        "max_new_tokens": 64,
        "arrival_delay_ms": 1800,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "system_long_a",
    },
    {
        "case_id": "P003_api_continuous16_system_002_cap8192_gen64",
        "prompt_id": "P003",
        "cap_tokens": 8192,
        "max_new_tokens": 64,
        "arrival_delay_ms": 2000,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "system_long_a",
    },
    {
        "case_id": "P009_api_continuous16_moe_001_cap8192_gen64",
        "prompt_id": "P009",
        "cap_tokens": 8192,
        "max_new_tokens": 64,
        "arrival_delay_ms": 2200,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "none",
    },
    {
        "case_id": "P009_api_continuous16_moe_002_cap8192_gen64",
        "prompt_id": "P009",
        "cap_tokens": 8192,
        "max_new_tokens": 64,
        "arrival_delay_ms": 2400,
        "concurrency_group": "api_continuous16_mixed_0001",
        "prefix_reuse_group": "none",
    },
]


def _make_continuous32_mixed_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for wave_index, delay_offset_ms in enumerate((0, 2600), start=1):
        for case in VLLM_API_CONTINUOUS16_MIXED_CASES:
            expanded = dict(case)
            expanded["case_id"] = str(case["case_id"]).replace(
                "_api_continuous16_",
                f"_api_continuous32_w{wave_index}_",
            )
            expanded["arrival_delay_ms"] = int(case["arrival_delay_ms"]) + delay_offset_ms
            expanded["concurrency_group"] = "api_continuous32_mixed_0001"
            cases.append(expanded)
    return cases


VLLM_API_CONTINUOUS32_MIXED_CASES = _make_continuous32_mixed_cases()

SERVER_STATS_PATTERN = re.compile(
    r"Avg prompt throughput:\s*(?P<prompt_throughput>[0-9.]+)\s*tokens/s,\s*"
    r"Avg generation throughput:\s*(?P<generation_throughput>[0-9.]+)\s*tokens/s,\s*"
    r"Running:\s*(?P<running>[0-9]+)\s*reqs,\s*"
    r"Waiting:\s*(?P<waiting>[0-9]+)\s*reqs,\s*"
    r"GPU KV cache usage:\s*(?P<kv_cache_usage>[0-9.]+)%,\s*"
    r"Prefix cache hit rate:\s*(?P<prefix_cache_hit_rate>[0-9.]+)%"
)


def default_max_model_len_for(case_plan: str) -> int:
    if case_plan in {"continuous16_mixed", "continuous32_mixed"}:
        return 9216
    return 6144


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded vLLM OpenAI API server concurrency smoke on the Ascend server."
    )
    parser.add_argument("--run-id", default=os.environ.get("RUN_ID", DEFAULT_RUN_ID))
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to 工作记录与进度笔记本/runtime_trace_smokes/<run-id>.",
    )
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
        default=os.environ.get("AK_VLLM_API_CASE_PLAN", "three_request_smoke"),
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
        help="Optional vLLM SamplingParams min_tokens value for each completion request.",
    )
    parser.add_argument(
        "--ignore-eos",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("AK_VLLM_API_IGNORE_EOS", "0") == "1",
        help="Optional vLLM SamplingParams ignore_eos value for each completion request.",
    )
    args = parser.parse_args()
    if args.max_model_len is None:
        env_max_model_len = os.environ.get("AK_VLLM_MAX_MODEL_LEN")
        args.max_model_len = int(env_max_model_len) if env_max_model_len else default_max_model_len_for(args.case_plan)
    return args


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_prompt_index(contract_dir: Path, long_manifest: Path) -> dict[str, dict[str, Any]]:
    manifest = load_yaml(long_manifest)
    prompts = manifest.get("prompts", [])
    if not isinstance(prompts, list):
        raise ValueError("long manifest prompts must be a list")

    prompt_index: dict[str, dict[str, Any]] = {}
    for prompt in prompts:
        if not isinstance(prompt, dict):
            raise ValueError("long manifest prompt entries must be mappings")
        prompt_id = str(prompt["prompt_id"])
        prompt_path = contract_dir / str(prompt["prompt_path"])
        prompt_index[prompt_id] = {
            "metadata": prompt,
            "text": prompt_path.read_text(encoding="utf-8"),
        }
    return prompt_index


def select_cases(case_plan: str) -> list[dict[str, Any]]:
    if case_plan == "three_request_smoke":
        return VLLM_API_CONCURRENCY_CASES
    if case_plan == "burst8":
        return VLLM_API_BURST_QUEUE_CASES
    if case_plan == "continuous16_mixed":
        return VLLM_API_CONTINUOUS16_MIXED_CASES
    if case_plan == "continuous32_mixed":
        return VLLM_API_CONTINUOUS32_MIXED_CASES
    raise ValueError(f"unknown case plan: {case_plan}")


def matrix_policy_for(case_plan: str) -> str:
    if case_plan == "continuous32_mixed":
        return "vllm_openai_api_server_thirty_two_request_mixed_4k_8k_continuous_workload_candidate"
    if case_plan == "continuous16_mixed":
        return "vllm_openai_api_server_sixteen_request_mixed_4k_8k_continuous_workload_candidate"
    if case_plan == "burst8":
        return "vllm_openai_api_server_eight_staggered_burst_queue_requests_candidate"
    return "vllm_openai_api_server_three_overlapping_completion_requests_candidate"


def continuous_policy_for(case_plan: str) -> str:
    if case_plan == "continuous32_mixed":
        return "candidate_only_thirty_two_staggered_clients_mixed_4k_8k_no_throughput_or_scheduler_claim"
    if case_plan == "continuous16_mixed":
        return "candidate_only_sixteen_staggered_clients_mixed_4k_8k_no_throughput_or_scheduler_claim"
    if case_plan == "burst8":
        return "candidate_only_eight_staggered_clients_no_throughput_or_scheduler_claim"
    return "candidate_only_three_overlapping_clients_no_scheduler_claim"


def run_vllm_api_concurrency_smoke(args: argparse.Namespace) -> int:
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

    trace_path = artifact_dir / "vllm_api_concurrency_trace.jsonl"
    summary_path = artifact_dir / "vllm_api_concurrency_summary.tsv"
    result_path = artifact_dir / "vllm_api_concurrency_result.json"
    conclusion_path = artifact_dir / "vllm_api_concurrency_conclusion.txt"
    validation_path = artifact_dir / "vllm_api_concurrency_validation.txt"
    server_cmd_path = artifact_dir / "vllm_api_server_command.json"
    server_log_path = artifact_dir / "vllm_api_server.log"
    server_stats_path = artifact_dir / "vllm_api_server_stats_summary.tsv"

    rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    fatal_error = ""
    server_ready = False
    server_return_code: int | None = None
    server_process: subprocess.Popen[str] | None = None

    try:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
        prompt_index = load_prompt_index(args.contract_dir, args.long_manifest)
        prepared = [
            prepare_case(
                tokenizer=tokenizer,
                prompt_index=prompt_index,
                case=case,
                request_index=index,
            )
            for index, case in enumerate(selected_cases, start=1)
        ]
        rows = [item["row"] for item in prepared]
        events.extend(make_pre_request_events(prepared, args.device_label, args.enable_prefix_caching))

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

            client_results = run_overlapping_completion_requests(
                prepared=prepared,
                args=args,
            )

        apply_client_results(
            rows=rows,
            prepared=prepared,
            client_results=client_results,
            tokenizer=tokenizer,
            generated_dir=generated_dir,
        )
        events.extend(make_post_request_events(prepared, rows, args.device_label, args.enable_prefix_caching))
    except Exception:
        fatal_error = traceback.format_exc()
    finally:
        if server_process is not None:
            server_return_code = stop_process_group(server_process)

    server_stats_summary = write_server_stats_summary(server_log_path, server_stats_path)
    _write_jsonl(trace_path, events)
    validation_report = validate_trace_fixture(trace_path) if events else None
    validation_errors = validation_report.errors if validation_report else ["no trace events emitted"]
    validation_path.write_text(
        "\n".join(validation_errors) + "\n" if validation_errors else "errors=0\n",
        encoding="utf-8",
    )

    success_count = sum(1 for row in rows if row["status"] == "success")
    failed_count = len(rows) - success_count
    input_count_mismatch_count = sum(
        1 for row in rows if row["input_token_count"] != row["expected_input_token_count"]
    )
    submitted_count_mismatch_count = sum(
        1 for row in rows if row["submitted_input_token_count"] != row["input_token_count"]
    )
    overlap_candidate_count = count_client_overlap_candidates(rows)
    status = (
        "success"
        if not fatal_error
        and server_ready
        and len(rows) == len(selected_cases)
        and failed_count == 0
        and overlap_candidate_count > 0
        and not validation_errors
        else "failed"
    )

    _write_summary(summary_path, rows)
    result = {
        "run_id": args.run_id,
        "status": status,
        "matrix_status": status,
        "phase": "complete" if not fatal_error else "fatal",
        "model_path": args.model_path,
        "served_model_name": args.served_model_name,
        "device_label": args.device_label,
        "host": args.host,
        "port": args.port,
        "case_plan": args.case_plan,
        "server_ready": int(server_ready),
        "server_return_code_after_shutdown": server_return_code,
        "request_count": len(selected_cases),
        "success_case_count": success_count,
        "failed_case_count": failed_count,
        "client_overlap_candidate_count": overlap_candidate_count,
        "prefix_cache_requested": int(args.enable_prefix_caching),
        "request_min_tokens": args.min_tokens,
        "request_ignore_eos": int(args.ignore_eos),
        "input_count_mismatch_count": input_count_mismatch_count,
        "submitted_count_mismatch_count": submitted_count_mismatch_count,
        "trace_event_count": len(events),
        "trace_validation_errors": len(validation_errors),
        "trace_validation_error_messages": validation_errors,
        "server_stats_sample_count": server_stats_summary["sample_count"],
        "server_stats_max_running_reqs": server_stats_summary["max_running_reqs"],
        "server_stats_max_waiting_reqs": server_stats_summary["max_waiting_reqs"],
        "server_stats_max_kv_cache_usage_pct": server_stats_summary["max_kv_cache_usage_pct"],
        "server_stats_max_prefix_cache_hit_rate_pct": server_stats_summary["max_prefix_cache_hit_rate_pct"],
        "fatal_error": fatal_error,
        "import_probe": import_probe,
        "policy": "vllm_api_concurrency_smoke_no_package_install",
        "matrix_policy": matrix_policy_for(args.case_plan),
        "profiler_policy": "disabled_not_part_of_this_task",
        "performance_policy": "smoke_only_no_benchmark_or_bottleneck_conclusion",
        "prefix_cache_policy": "requested_if_supported_no_hit_rate_claim",
        "continuous_batching_policy": continuous_policy_for(args.case_plan),
        "rows": rows,
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_conclusion(conclusion_path, result)
    return 0 if status == "success" else 1


def prepare_case(
    *,
    tokenizer: Any,
    prompt_index: dict[str, dict[str, Any]],
    case: dict[str, Any],
    request_index: int,
) -> dict[str, Any]:
    prompt_id = str(case["prompt_id"])
    cap_tokens = int(case["cap_tokens"])
    case_id = str(case["case_id"])
    prompt_text = prompt_index[prompt_id]["text"]
    token_ids = tokenizer(prompt_text, add_special_tokens=False).input_ids
    if token_ids and isinstance(token_ids[0], list):
        token_ids = token_ids[0]
    token_ids = list(token_ids)
    selected_token_ids = token_ids[:cap_tokens]
    selected_text = tokenizer.decode(selected_token_ids, skip_special_tokens=False)
    submitted_ids = tokenizer(selected_text, add_special_tokens=False).input_ids
    if submitted_ids and isinstance(submitted_ids[0], list):
        submitted_ids = submitted_ids[0]

    row = {
        "case_id": case_id,
        "prompt_id": prompt_id,
        "endpoint": "/v1/completions",
        "concurrency_group": str(case["concurrency_group"]),
        "prefix_reuse_group": str(case["prefix_reuse_group"]),
        "arrival_delay_ms": int(case["arrival_delay_ms"]),
        "cap_tokens": cap_tokens,
        "max_new_tokens": int(case["max_new_tokens"]),
        "full_token_count": len(token_ids),
        "expected_input_token_count": min(len(token_ids), cap_tokens),
        "input_token_count": len(selected_token_ids),
        "submitted_input_token_count": len(submitted_ids),
        "http_status": 0,
        "request_start_ns": 0,
        "response_end_ns": 0,
        "client_wall_us": 0,
        "generated_token_count": 0,
        "generated_text_nonempty": 0,
        "finish_reason": "",
        "prompt_input_mode": "decoded_text_after_transformers_token_cap",
        "status": "failed",
        "error_type": "",
        "error": "",
    }
    return {
        "case": case,
        "row": row,
        "request_index": request_index,
        "request_id": f"req_p1_vllm_api_concurrency_{request_index:04d}_{case_id}",
        "selected_text": selected_text,
        "selected_token_ids": selected_token_ids,
        "prompt_bytes": len(selected_text.encode("utf-8")),
    }


def build_server_command(args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        os.environ.get("AK_VLLM_API_SERVER_MODULE", "vllm.entrypoints.openai.api_server"),
        "--model",
        args.model_path,
        "--served-model-name",
        args.served_model_name,
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--trust-remote-code",
        "--max-model-len",
        str(args.max_model_len),
        "--tensor-parallel-size",
        str(args.tensor_parallel_size),
        "--gpu-memory-utilization",
        str(args.gpu_memory_utilization),
        "--dtype",
        args.dtype,
    ]
    if args.enforce_eager:
        cmd.append("--enforce-eager")
    if args.enable_prefix_caching:
        cmd.append("--enable-prefix-caching")
    return cmd


def wait_for_server_ready(host: str, port: int, process: subprocess.Popen[str], timeout_sec: float) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        if probe_http(f"http://{host}:{port}/health", timeout=5):
            return True
        time.sleep(2)
    return False


def probe_http(url: str, timeout: float) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= int(response.status) < 400
    except Exception:
        return False


def run_overlapping_completion_requests(
    *,
    prepared: list[dict[str, Any]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = [{} for _ in prepared]
    threads = []
    base_url = f"http://{args.host}:{args.port}/v1/completions"
    for index, item in enumerate(prepared):
        thread = threading.Thread(
            target=_request_worker,
            args=(index, item, args, base_url, results),
            daemon=True,
        )
        threads.append(thread)
        thread.start()
    for thread in threads:
        thread.join(timeout=args.request_timeout_sec + 30)
    return results


def _request_worker(
    index: int,
    item: dict[str, Any],
    args: argparse.Namespace,
    url: str,
    results: list[dict[str, Any]],
) -> None:
    time.sleep(int(item["case"]["arrival_delay_ms"]) / 1000)
    row = item["row"]
    payload = build_completion_payload(args, item)
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start_ns = time.monotonic_ns()
    try:
        with urllib.request.urlopen(request, timeout=args.request_timeout_sec) as response:
            body = response.read().decode("utf-8", errors="replace")
            end_ns = time.monotonic_ns()
            parsed = json.loads(body)
            results[index] = {
                "ok": True,
                "http_status": int(response.status),
                "body": parsed,
                "body_raw": body,
                "request_start_ns": start_ns,
                "response_end_ns": end_ns,
            }
    except urllib.error.HTTPError as error:
        end_ns = time.monotonic_ns()
        body = error.read().decode("utf-8", errors="replace")
        results[index] = {
            "ok": False,
            "http_status": int(error.code),
            "body_raw": body,
            "request_start_ns": start_ns,
            "response_end_ns": end_ns,
            "error": body,
        }

    except Exception:
        end_ns = time.monotonic_ns()
        results[index] = {
            "ok": False,
            "http_status": 0,
            "body_raw": "",
            "request_start_ns": start_ns,
            "response_end_ns": end_ns,
            "error": traceback.format_exc(),
        }


def build_completion_payload(args: argparse.Namespace, item: dict[str, Any]) -> dict[str, Any]:
    row = item["row"]
    payload = {
        "model": args.served_model_name,
        "prompt": item["selected_text"],
        "max_tokens": int(row["max_new_tokens"]),
        "temperature": 0,
    }
    if args.min_tokens is not None:
        payload["min_tokens"] = int(args.min_tokens)
    if args.ignore_eos:
        payload["ignore_eos"] = True
    return payload


def apply_client_results(
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
        row["request_start_ns"] = int(result.get("request_start_ns") or 0)
        row["response_end_ns"] = int(result.get("response_end_ns") or 0)
        row["http_status"] = int(result.get("http_status") or 0)
        if row["request_start_ns"] and row["response_end_ns"]:
            row["client_wall_us"] = max(0, (row["response_end_ns"] - row["request_start_ns"]) // 1000)

        generated_text = ""
        generated_token_count = 0
        finish_reason = ""
        if result.get("ok"):
            body = result.get("body") or {}
            choices = body.get("choices") or []
            if choices:
                choice = choices[0]
                generated_text = str(choice.get("text") or "")
                finish_reason = str(choice.get("finish_reason") or "")
            usage = body.get("usage") or {}
            generated_token_count = int(usage.get("completion_tokens") or 0)
            if generated_token_count <= 0 and generated_text:
                token_ids = tokenizer(generated_text, add_special_tokens=False).input_ids
                if token_ids and isinstance(token_ids[0], list):
                    token_ids = token_ids[0]
                generated_token_count = len(token_ids)
        else:
            row["error"] = str(result.get("error") or "missing client result")

        (generated_dir / f"{case_id}.txt").write_text(generated_text, encoding="utf-8")
        (generated_dir / f"{case_id}_response.json").write_text(
            json.dumps(result.get("body") or {"raw": result.get("body_raw", "")}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        row["generated_token_count"] = generated_token_count
        row["generated_text_nonempty"] = int(bool(generated_text))
        row["finish_reason"] = finish_reason
        row["status"] = "success" if 200 <= row["http_status"] < 300 and (generated_text or generated_token_count) else "failed"
        if row["status"] != "success":
            row["error_type"] = row["error_type"] or "api_request_failed_or_empty_generation"
            row["error"] = row["error"] or "OpenAI completions response was not successful or empty"
        if row["submitted_input_token_count"] != row["input_token_count"]:
            row["status"] = "failed"
            row["error_type"] = row["error_type"] or "submitted_input_count_mismatch"
            row["error"] = row["error"] or "decoded capped text did not re-tokenize to the selected token count"


def make_pre_request_events(
    prepared: list[dict[str, Any]],
    device_label: str,
    enable_prefix_caching: bool,
) -> list[dict[str, Any]]:
    timestamp_ns = time.monotonic_ns()
    group_id = str(prepared[0]["case"]["concurrency_group"])
    events = [
        _event(
            group_id,
            "scheduler",
            0,
            "enqueue",
            "decision",
            "scheduler_policy_profile",
            timestamp_ns,
            policy_decision=(
                f"openai_api_server_{len(prepared)}_staggered_clients_"
                f"prefix_cache_requested_{int(enable_prefix_caching)}"
            ),
            device_id=device_label,
        )
    ]
    for item in prepared:
        row = item["row"]
        case_id = row["case_id"]
        request_id = item["request_id"]
        events.append(
            _event(
                case_id,
                request_id,
                item["request_index"],
                "enqueue",
                "point",
                "request_runtime_profile",
                timestamp_ns + int(row["arrival_delay_ms"]) * 1_000_000,
                queue_wait_us=0,
                policy_decision=f"concurrency_group={group_id}",
                device_id=device_label,
            )
        )
        events.append(
            _event(
                case_id,
                request_id,
                item["request_index"],
                "tokenize",
                "metric_sample",
                "request_runtime_profile",
                time.monotonic_ns(),
                bytes_read=item["prompt_bytes"],
                bytes_write=len(item["selected_token_ids"]) * 8,
                policy_decision="transformers_token_cap_then_decoded_text",
                device_id=device_label,
            )
        )
        events.append(
            _event(
                case_id,
                request_id,
                item["request_index"],
                "prefill",
                "metric_sample",
                "kv_prefix_profile",
                time.monotonic_ns(),
                object_type="prefix",
                object_id=f"prefix:{row['prefix_reuse_group']}",
                bytes_read=len(item["selected_token_ids"]) * 2,
                policy_decision="candidate_only_no_runtime_hit_signal",
                hit_or_miss="unknown",
                device_id=device_label,
            )
        )
    return events


def make_post_request_events(
    prepared: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    device_label: str,
    enable_prefix_caching: bool,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item, row in zip(prepared, rows):
        case_id = row["case_id"]
        request_id = item["request_id"]
        request_index = item["request_index"]
        stream_id = f"vllm_api:{device_label}:candidate_stream"
        kv_object_id = f"kv:{request_id}:L00"
        start_ns = int(row["request_start_ns"]) or time.monotonic_ns()
        end_ns = int(row["response_end_ns"]) or start_ns
        events.extend(
            [
                _event(
                    case_id,
                    request_id,
                    request_index,
                    "prefill",
                    "span_start",
                    "operator_timeline_profile",
                    start_ns,
                    layer_id=0,
                    op_name="vllm.openai_api_server.completions_prefill_decode_candidate",
                    stream_id=stream_id,
                    device_id=device_label,
                    policy_decision=f"enable_prefix_caching={int(enable_prefix_caching)}",
                ),
                _event(
                    case_id,
                    request_id,
                    request_index,
                    "prefill",
                    "lifecycle",
                    "state_object_profile",
                    start_ns,
                    layer_id=0,
                    stream_id=stream_id,
                    device_id=device_label,
                    object_type="kv",
                    object_id=kv_object_id,
                    target_tier="npu_hbm",
                    bytes_write=int(row["input_token_count"]) * 2,
                    policy_decision="vllm_openai_api_server_candidate",
                ),
                _event(
                    case_id,
                    request_id,
                    request_index,
                    "prefill",
                    "metric_sample",
                    "transfer_overlap_profile",
                    start_ns,
                    layer_id=0,
                    stream_id=stream_id,
                    device_id=device_label,
                    object_type="kv",
                    object_id=kv_object_id,
                    bytes_read=int(row["input_token_count"]) * 2,
                    overlap_ratio=0.0,
                ),
                _event(
                    case_id,
                    request_id,
                    request_index,
                    "decode",
                    "span_end",
                    "operator_timeline_profile",
                    end_ns,
                    layer_id=0,
                    op_name="vllm.openai_api_server.completions_prefill_decode_candidate",
                    stream_id=stream_id,
                    device_id=device_label,
                    latency_us=int(row["client_wall_us"]),
                    policy_decision=f"max_new_tokens={row['max_new_tokens']}",
                ),
            ]
        )
    return events


def count_client_overlap_candidates(rows: list[dict[str, Any]]) -> int:
    intervals = [
        (int(row["request_start_ns"]), int(row["response_end_ns"]))
        for row in rows
        if int(row["request_start_ns"]) > 0 and int(row["response_end_ns"]) > int(row["request_start_ns"])
    ]
    overlaps = 0
    for index, (start, end) in enumerate(intervals):
        for other_start, other_end in intervals[index + 1 :]:
            if start < other_end and other_start < end:
                overlaps += 1
    return overlaps


def write_server_stats_summary(log_path: Path, output_path: Path) -> dict[str, Any]:
    fields = [
        "line_number",
        "avg_prompt_throughput_tokens_s",
        "avg_generation_throughput_tokens_s",
        "running_reqs",
        "waiting_reqs",
        "gpu_kv_cache_usage_pct",
        "prefix_cache_hit_rate_pct",
    ]
    rows: list[dict[str, Any]] = []
    if log_path.is_file():
        for line_number, line in enumerate(log_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            match = SERVER_STATS_PATTERN.search(line)
            if match:
                rows.append(
                    {
                        "line_number": line_number,
                        "avg_prompt_throughput_tokens_s": float(match.group("prompt_throughput")),
                        "avg_generation_throughput_tokens_s": float(match.group("generation_throughput")),
                        "running_reqs": int(match.group("running")),
                        "waiting_reqs": int(match.group("waiting")),
                        "gpu_kv_cache_usage_pct": float(match.group("kv_cache_usage")),
                        "prefix_cache_hit_rate_pct": float(match.group("prefix_cache_hit_rate")),
                    }
                )

    output_lines = ["\t".join(fields)]
    for row in rows:
        output_lines.append("\t".join(str(row[field]) for field in fields))
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")

    return {
        "sample_count": len(rows),
        "max_running_reqs": max((row["running_reqs"] for row in rows), default=0),
        "max_waiting_reqs": max((row["waiting_reqs"] for row in rows), default=0),
        "max_kv_cache_usage_pct": max((row["gpu_kv_cache_usage_pct"] for row in rows), default=0.0),
        "max_prefix_cache_hit_rate_pct": max((row["prefix_cache_hit_rate_pct"] for row in rows), default=0.0),
    }


def pick_free_port(host: str) -> int:
    for port in range(18080, 18121):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError("no free localhost port found in 18080-18120")


def stop_process_group(process: subprocess.Popen[str]) -> int | None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=30)
    return process.returncode


def write_run_context(path: Path, args: argparse.Namespace, selected_cases: list[dict[str, Any]]) -> None:
    lines = [
        f"run_id={args.run_id}",
        f"commit={_git_commit()}",
        f"timestamp={_timestamp()}",
        f"hostname={os.uname().nodename}",
        f"python={_which_python()}",
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
        f"ATB_HOME_PATH={os.environ.get('ATB_HOME_PATH', '')}",
        "task_policy=vllm_api_concurrency_smoke_no_package_install",
        f"matrix_policy={matrix_policy_for(args.case_plan)}",
        "profiler_policy=disabled_not_part_of_this_task",
        "performance_policy=smoke_only_no_benchmark_or_bottleneck_conclusion",
        "prefix_cache_policy=requested_if_supported_no_hit_rate_claim",
        f"continuous_batching_policy={continuous_policy_for(args.case_plan)}",
        "selected_cases="
        + ",".join(
            f"{case['prompt_id']}@{case['cap_tokens']}+{case['max_new_tokens']}+delay{case['arrival_delay_ms']}ms"
            for case in selected_cases
        ),
        f"request_count={len(selected_cases)}",
        f"max_model_len={args.max_model_len}",
        f"gpu_memory_utilization={args.gpu_memory_utilization}",
        f"tensor_parallel_size={args.tensor_parallel_size}",
        f"dtype={args.dtype}",
        f"enforce_eager={int(args.enforce_eager)}",
        f"enable_prefix_caching={int(args.enable_prefix_caching)}",
        f"server_ready_timeout_sec={args.server_ready_timeout_sec}",
        f"request_timeout_sec={args.request_timeout_sec}",
        f"request_min_tokens={args.min_tokens}",
        f"request_ignore_eos={int(args.ignore_eos)}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_package_inventory(path: Path) -> None:
    packages = [
        ("torch", "torch"),
        ("torch_npu", "torch_npu"),
        ("transformers", "transformers"),
        ("tokenizers", "tokenizers"),
        ("sentencepiece", "sentencepiece"),
        ("accelerate", "accelerate"),
        ("safetensors", "safetensors"),
        ("vllm", "vllm"),
        ("vllm_ascend", "vllm_ascend"),
    ]
    lines = ["package\tmodule\tdistribution_version\tspec_found\torigin"]
    for dist_name, module_name in packages:
        try:
            version = metadata.version(dist_name)
        except metadata.PackageNotFoundError:
            version = ""
        spec = importlib.util.find_spec(module_name)
        lines.append(
            "\t".join(
                [
                    dist_name,
                    module_name,
                    version,
                    "1" if spec else "0",
                    getattr(spec, "origin", "") or "",
                ]
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_model_path_precheck(path: Path, model_path: str) -> None:
    root = Path(model_path)
    lines = [
        f"model_path={root}",
        f"exists={int(root.exists())}",
        f"is_dir={int(root.is_dir())}",
    ]
    for name in ["config.json", "tokenizer_config.json", "tokenizer.json", "generation_config.json"]:
        item = root / name
        lines.append(f"{name}\texists={int(item.is_file())}\tbytes={item.stat().st_size if item.is_file() else ''}")
        if item.is_file() and name in {"config.json", "tokenizer_config.json"}:
            data = json.loads(item.read_text(encoding="utf-8"))
            if name == "config.json":
                lines.append(f"config_model_type={data.get('model_type', '')}")
                lines.append(f"config_architectures={data.get('architectures', '')}")
            if name == "tokenizer_config.json":
                lines.append(f"tokenizer_class={data.get('tokenizer_class', '')}")
                lines.append(f"model_max_length={data.get('model_max_length', '')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_import_probe(path: Path) -> dict[str, str]:
    modules = ["torch", "torch_npu", "transformers", "vllm", "vllm_ascend"]
    results: dict[str, str] = {}
    lines = ["module\tstatus\terror"]
    for module_name in modules:
        try:
            importlib.import_module(module_name)
            results[module_name] = "ok"
            lines.append(f"{module_name}\tok\t")
        except Exception:
            error = traceback.format_exc().replace("\n", "\\n")
            results[module_name] = "failed"
            lines.append(f"{module_name}\tfailed\t{error}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


def _event(
    case_id: str,
    request_id: str,
    request_index: int,
    phase: str,
    event_type: str,
    resource_scope: str,
    timestamp_ns: int,
    **overrides: Any,
) -> dict[str, Any]:
    event = {
        "schema_version": "p1.1",
        "event_id": f"evt_p1_vllm_api_{request_index:04d}_{phase}_{event_type}_{resource_scope}",
        "timestamp_ns": int(timestamp_ns),
        "time_base": "host_monotonic_ns",
        "trace_id": "trace_vllm_api_concurrency_smoke",
        "request_id": request_id,
        "session_id": "session_vllm_api_concurrency_smoke",
        "phase": phase,
        "event_type": event_type,
        "resource_scope": resource_scope,
        "layer_id": overrides.get("layer_id", 0),
        "op_name": overrides.get("op_name", ""),
        "kernel_name": overrides.get("kernel_name", ""),
        "stream_id": overrides.get("stream_id", f"host:vllm_api:{request_index}"),
        "device_id": overrides.get("device_id", ""),
        "object_type": overrides.get("object_type", "kv"),
        "object_id": overrides.get("object_id", f"kv:{request_id}:L00"),
        "source_tier": overrides.get("source_tier", "host_dram"),
        "target_tier": overrides.get("target_tier", "npu_hbm"),
        "bytes_read": overrides.get("bytes_read", 0),
        "bytes_write": overrides.get("bytes_write", 0),
        "latency_us": overrides.get("latency_us", 0),
        "queue_wait_us": overrides.get("queue_wait_us", 0),
        "overlap_ratio": overrides.get("overlap_ratio", 0.0),
        "policy_decision": overrides.get("policy_decision", "none"),
        "hit_or_miss": overrides.get("hit_or_miss", "unknown"),
        "stall_reason": overrides.get("stall_reason", "unknown"),
        "evidence_source": "vllm_openai_api_concurrency_smoke",
        "artifact_path": (
            "runtime_trace_smokes/"
            f"{os.environ.get('RUN_ID', DEFAULT_RUN_ID)}/vllm_api_concurrency_trace.jsonl"
        ),
    }
    event["case_id"] = case_id
    return event


def _write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )


def _write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
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
        "client_wall_us",
        "generated_token_count",
        "generated_text_nonempty",
        "finish_reason",
        "status",
        "error_type",
        "error",
    ]
    lines = ["\t".join(fields)]
    for row in rows:
        lines.append("\t".join(str(row.get(field, "")) for field in fields))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_conclusion(path: Path, result: dict[str, Any]) -> None:
    keys = [
        "status",
        "matrix_status",
        "phase",
        "model_path",
        "served_model_name",
        "device_label",
        "host",
        "port",
        "case_plan",
        "server_ready",
        "request_count",
        "success_case_count",
        "failed_case_count",
        "client_overlap_candidate_count",
        "prefix_cache_requested",
        "input_count_mismatch_count",
        "submitted_count_mismatch_count",
        "trace_event_count",
        "trace_validation_errors",
        "server_stats_sample_count",
        "server_stats_max_running_reqs",
        "server_stats_max_waiting_reqs",
        "server_stats_max_kv_cache_usage_pct",
        "server_stats_max_prefix_cache_hit_rate_pct",
        "policy",
        "matrix_policy",
        "profiler_policy",
        "performance_policy",
        "prefix_cache_policy",
        "continuous_batching_policy",
    ]
    path.write_text("\n".join(f"{key}={result.get(key, '')}" for key in keys) + "\n", encoding="utf-8")


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return ""


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _which_python() -> str:
    return sys.executable


def main() -> int:
    return run_vllm_api_concurrency_smoke(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
