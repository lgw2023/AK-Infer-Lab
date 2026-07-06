from __future__ import annotations

import argparse
import importlib
import importlib.metadata as metadata
import importlib.util
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.validation import validate_trace_fixture


DEFAULT_RUN_ID = "runtime_vllm_engine_single_request_smoke_2026_0706_p1_016"
DEFAULT_CONTRACT_DIR = REPO_ROOT / "工作记录与进度笔记本" / "p1_inference_contracts"
DEFAULT_LONG_MANIFEST = DEFAULT_CONTRACT_DIR / "workload_long_manifest.yaml"
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "工作记录与进度笔记本" / "runtime_trace_smokes"

VLLM_SMOKE_CASES = [
    {"case_id": "P002_cap4096_gen32", "prompt_id": "P002", "cap_tokens": 4096, "max_new_tokens": 32},
    {"case_id": "P003_cap8192_gen32", "prompt_id": "P003", "cap_tokens": 8192, "max_new_tokens": 32},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded vLLM/vLLM-Ascend single-request smoke on the Ascend server."
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
    parser.add_argument("--device-label", default=os.environ.get("AK_VLLM_DEVICE_LABEL", "npu:6"))
    parser.add_argument("--contract-dir", type=Path, default=DEFAULT_CONTRACT_DIR)
    parser.add_argument("--long-manifest", type=Path, default=DEFAULT_LONG_MANIFEST)
    parser.add_argument("--max-model-len", type=int, default=int(os.environ.get("AK_VLLM_MAX_MODEL_LEN", "9216")))
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
    return parser.parse_args()


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


def write_run_context(path: Path, args: argparse.Namespace, selected_cases: list[dict[str, Any]]) -> None:
    lines = [
        f"run_id={args.run_id}",
        f"commit={_git_commit()}",
        f"timestamp={_timestamp()}",
        f"hostname={os.uname().nodename}",
        f"python={_which_python()}",
        f"cwd={Path.cwd()}",
        f"MODEL_PATH={args.model_path}",
        f"DEVICE_LABEL={args.device_label}",
        f"CONTRACT_DIR={args.contract_dir}",
        f"LONG_MANIFEST={args.long_manifest}",
        f"ASCEND_RT_VISIBLE_DEVICES={os.environ.get('ASCEND_RT_VISIBLE_DEVICES', '')}",
        f"VLLM_USE_V1={os.environ.get('VLLM_USE_V1', '')}",
        f"VLLM_PLUGINS={os.environ.get('VLLM_PLUGINS', '')}",
        f"VLLM_WORKER_MULTIPROC_METHOD={os.environ.get('VLLM_WORKER_MULTIPROC_METHOD', '')}",
        "task_policy=vllm_engine_single_request_smoke_no_package_install",
        "matrix_policy=vllm_public_llm_generate_4k_8k_single_request",
        "profiler_policy=disabled_not_part_of_this_task",
        "performance_policy=smoke_only_no_benchmark_or_bottleneck_conclusion",
        "selected_cases="
        + ",".join(
            f"{case['prompt_id']}@{case['cap_tokens']}+{case['max_new_tokens']}"
            for case in selected_cases
        ),
        f"max_model_len={args.max_model_len}",
        f"gpu_memory_utilization={args.gpu_memory_utilization}",
        f"tensor_parallel_size={args.tensor_parallel_size}",
        f"dtype={args.dtype}",
        f"enforce_eager={int(args.enforce_eager)}",
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


def run_vllm_smoke(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir or (DEFAULT_ARTIFACT_ROOT / args.run_id)
    generated_dir = artifact_dir / "generated_texts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)

    write_run_context(artifact_dir / "run_context.txt", args, VLLM_SMOKE_CASES)
    write_package_inventory(artifact_dir / "package_inventory.tsv")
    write_model_path_precheck(artifact_dir / "model_path_precheck.txt", args.model_path)
    import_probe = write_import_probe(artifact_dir / "vllm_import_probe.tsv")

    trace_path = artifact_dir / "vllm_engine_single_request_trace.jsonl"
    summary_path = artifact_dir / "vllm_engine_single_request_summary.tsv"
    result_path = artifact_dir / "vllm_engine_single_request_result.json"
    conclusion_path = artifact_dir / "vllm_engine_single_request_conclusion.txt"
    validation_path = artifact_dir / "vllm_engine_single_request_validation.txt"

    rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    fatal_error = ""
    tokenizer_class = ""
    llm_class = ""

    try:
        from transformers import AutoTokenizer
        from vllm import LLM, SamplingParams

        prompt_index = load_prompt_index(args.contract_dir, args.long_manifest)
        tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
        tokenizer_class = tokenizer.__class__.__name__

        llm_kwargs = {
            "model": args.model_path,
            "trust_remote_code": True,
            "max_model_len": args.max_model_len,
            "tensor_parallel_size": args.tensor_parallel_size,
            "gpu_memory_utilization": args.gpu_memory_utilization,
            "enforce_eager": args.enforce_eager,
        }
        if args.dtype != "auto":
            llm_kwargs["dtype"] = args.dtype

        engine_start_ns = time.monotonic_ns()
        llm = LLM(**llm_kwargs)
        engine_end_ns = time.monotonic_ns()
        llm_class = llm.__class__.__name__

        (artifact_dir / "vllm_engine_init.json").write_text(
            json.dumps(
                {
                    "llm_class": llm_class,
                    "llm_kwargs": llm_kwargs,
                    "latency_us": max(0, (engine_end_ns - engine_start_ns) // 1000),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        for request_index, case in enumerate(VLLM_SMOKE_CASES, start=1):
            rows.append(
                run_case(
                    llm=llm,
                    sampling_params_cls=SamplingParams,
                    tokenizer=tokenizer,
                    prompt_index=prompt_index,
                    case=case,
                    request_index=request_index,
                    device_label=args.device_label,
                    generated_dir=generated_dir,
                    events=events,
                )
            )
    except Exception:
        fatal_error = traceback.format_exc()

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
    status = "success" if not fatal_error and failed_count == 0 and not validation_errors else "failed"

    _write_summary(summary_path, rows)
    result = {
        "run_id": args.run_id,
        "status": status,
        "matrix_status": status,
        "phase": "complete" if not fatal_error else "fatal",
        "model_path": args.model_path,
        "device_label": args.device_label,
        "tokenizer_class": tokenizer_class,
        "llm_class": llm_class,
        "attempted_case_count": len(rows),
        "success_case_count": success_count,
        "failed_case_count": failed_count,
        "input_count_mismatch_count": input_count_mismatch_count,
        "submitted_count_mismatch_count": submitted_count_mismatch_count,
        "trace_event_count": len(events),
        "trace_validation_errors": len(validation_errors),
        "trace_validation_error_messages": validation_errors,
        "fatal_error": fatal_error,
        "import_probe": import_probe,
        "policy": "vllm_engine_single_request_smoke_no_package_install",
        "matrix_policy": "vllm_public_llm_generate_4k_8k_single_request",
        "profiler_policy": "disabled_not_part_of_this_task",
        "performance_policy": "smoke_only_no_benchmark_or_bottleneck_conclusion",
        "rows": rows,
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_conclusion(conclusion_path, result)
    return 0 if status == "success" else 1


def run_case(
    *,
    llm: Any,
    sampling_params_cls: Any,
    tokenizer: Any,
    prompt_index: dict[str, dict[str, Any]],
    case: dict[str, Any],
    request_index: int,
    device_label: str,
    generated_dir: Path,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt_id = str(case["prompt_id"])
    cap_tokens = int(case["cap_tokens"])
    max_new_tokens = int(case["max_new_tokens"])
    case_id = str(case["case_id"])
    row = {
        "case_id": case_id,
        "prompt_id": prompt_id,
        "cap_tokens": cap_tokens,
        "max_new_tokens": max_new_tokens,
        "full_token_count": 0,
        "expected_input_token_count": 0,
        "input_token_count": 0,
        "submitted_input_token_count": 0,
        "generated_token_count": 0,
        "generated_text_nonempty": 0,
        "finish_reason": "",
        "prompt_input_mode": "decoded_text_after_transformers_token_cap",
        "status": "failed",
        "error_type": "",
        "error": "",
    }

    try:
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

        row["full_token_count"] = len(token_ids)
        row["expected_input_token_count"] = min(len(token_ids), cap_tokens)
        row["input_token_count"] = len(selected_token_ids)
        row["submitted_input_token_count"] = len(submitted_ids)

        request_id = f"req_p1_vllm_engine_smoke_{request_index:04d}_{case_id}"
        stream_id = f"vllm:{device_label}:default_stream"
        enqueue_ts = time.monotonic_ns()
        events.append(_event(case_id, request_id, request_index, "enqueue", "point", "request_runtime_profile", enqueue_ts))
        events.append(
            _event(
                case_id,
                request_id,
                request_index,
                "tokenize",
                "metric_sample",
                "request_runtime_profile",
                time.monotonic_ns(),
                bytes_read=len(prompt_text.encode("utf-8")),
                bytes_write=len(selected_token_ids) * 8,
                policy_decision="transformers_token_cap_then_decoded_text",
            )
        )

        sampling_params = sampling_params_cls(max_tokens=max_new_tokens, temperature=0.0)
        generate_start = time.monotonic_ns()
        outputs = llm.generate([selected_text], sampling_params)
        end_ts = time.monotonic_ns()

        request_output = outputs[0] if outputs else None
        generated_text = ""
        generated_token_ids: list[int] = []
        finish_reason = ""
        if request_output is not None and getattr(request_output, "outputs", None):
            first_output = request_output.outputs[0]
            generated_text = getattr(first_output, "text", "") or ""
            generated_token_ids = list(getattr(first_output, "token_ids", []) or [])
            finish_reason = str(getattr(first_output, "finish_reason", "") or "")

        (generated_dir / f"{case_id}.txt").write_text(generated_text, encoding="utf-8")
        (generated_dir / f"{case_id}_token_ids.json").write_text(
            json.dumps(generated_token_ids, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        row["generated_token_count"] = len(generated_token_ids)
        row["generated_text_nonempty"] = int(bool(generated_text))
        row["finish_reason"] = finish_reason
        row["status"] = "success" if generated_token_ids or generated_text else "failed"
        if not generated_token_ids and not generated_text:
            row["error_type"] = "empty_generation"
            row["error"] = "vLLM generate returned no text or token ids"
        if row["submitted_input_token_count"] != row["input_token_count"]:
            row["status"] = "failed"
            row["error_type"] = row["error_type"] or "submitted_input_count_mismatch"
            row["error"] = row["error"] or "decoded capped text did not re-tokenize to the selected token count"

        kv_object_id = f"kv:{request_id}:L00"
        events.extend(
            [
                _event(
                    case_id,
                    request_id,
                    request_index,
                    "prefill",
                    "span_start",
                    "operator_timeline_profile",
                    generate_start,
                    layer_id=0,
                    op_name="vllm.LLM.generate_prefill_decode_candidate",
                    stream_id=stream_id,
                    device_id=device_label,
                ),
                _event(
                    case_id,
                    request_id,
                    request_index,
                    "prefill",
                    "lifecycle",
                    "state_object_profile",
                    generate_start,
                    layer_id=0,
                    stream_id=stream_id,
                    device_id=device_label,
                    object_type="kv",
                    object_id=kv_object_id,
                    target_tier="npu_hbm",
                    bytes_write=len(selected_token_ids) * 2,
                    policy_decision="vllm_engine_single_request",
                ),
                _event(
                    case_id,
                    request_id,
                    request_index,
                    "prefill",
                    "metric_sample",
                    "transfer_overlap_profile",
                    generate_start,
                    layer_id=0,
                    stream_id=stream_id,
                    device_id=device_label,
                    object_type="kv",
                    object_id=kv_object_id,
                    bytes_read=len(selected_token_ids) * 2,
                    overlap_ratio=0.0,
                ),
                _event(
                    case_id,
                    request_id,
                    request_index,
                    "prefill",
                    "span_end",
                    "operator_timeline_profile",
                    end_ts,
                    layer_id=0,
                    op_name="vllm.LLM.generate_prefill_decode_candidate",
                    stream_id=stream_id,
                    device_id=device_label,
                    latency_us=max(0, (end_ts - generate_start) // 1000),
                ),
                _event(
                    case_id,
                    request_id,
                    request_index,
                    "decode",
                    "metric_sample",
                    "request_runtime_profile",
                    end_ts,
                    latency_us=max(0, (end_ts - generate_start) // 1000),
                    policy_decision=f"max_new_tokens_{max_new_tokens}",
                ),
            ]
        )
    except Exception as exc:
        row["error_type"] = exc.__class__.__name__
        row["error"] = traceback.format_exc()
    return row


def _event(
    case_id: str,
    request_id: str,
    request_index: int,
    phase: str,
    event_type: str,
    resource_scope: str,
    timestamp_ns: int,
    *,
    layer_id: int | None = None,
    op_name: str | None = None,
    kernel_name: str | None = None,
    stream_id: str | None = None,
    device_id: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    source_tier: str = "host_dram",
    target_tier: str = "npu_hbm",
    bytes_read: int = 0,
    bytes_write: int = 0,
    latency_us: int = 0,
    queue_wait_us: int = 0,
    overlap_ratio: float | None = None,
    policy_decision: str = "none",
    hit_or_miss: str = "not_applicable",
    stall_reason: str = "unknown",
) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "event_id": f"evt_{case_id}_{resource_scope}_{phase}_{event_type}_{request_index:04d}",
        "timestamp_ns": timestamp_ns,
        "time_base": "host_monotonic_ns",
        "trace_id": "trace_p1_vllm_engine_single_request_smoke_0001",
        "request_id": request_id,
        "session_id": "session_p1_vllm_engine_single_request_smoke",
        "phase": phase,
        "event_type": event_type,
        "resource_scope": resource_scope,
        "layer_id": layer_id,
        "op_name": op_name,
        "kernel_name": kernel_name,
        "stream_id": stream_id,
        "device_id": device_id,
        "object_type": object_type,
        "object_id": object_id,
        "source_tier": source_tier,
        "target_tier": target_tier,
        "bytes_read": bytes_read,
        "bytes_write": bytes_write,
        "latency_us": latency_us,
        "queue_wait_us": queue_wait_us,
        "overlap_ratio": overlap_ratio,
        "policy_decision": policy_decision,
        "hit_or_miss": hit_or_miss,
        "stall_reason": stall_reason,
        "evidence_source": "vllm_engine_public_generate_smoke",
        "artifact_path": "vllm_engine_single_request_trace.jsonl",
    }


def _write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "case_id",
        "prompt_id",
        "cap_tokens",
        "max_new_tokens",
        "full_token_count",
        "expected_input_token_count",
        "input_token_count",
        "submitted_input_token_count",
        "generated_token_count",
        "generated_text_nonempty",
        "finish_reason",
        "prompt_input_mode",
        "status",
        "error_type",
        "error",
    ]
    lines = ["\t".join(columns)]
    for row in rows:
        lines.append("\t".join(str(row.get(column, "")).replace("\n", "\\n") for column in columns))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_conclusion(path: Path, result: dict[str, Any]) -> None:
    keys = [
        "status",
        "matrix_status",
        "phase",
        "model_path",
        "device_label",
        "tokenizer_class",
        "llm_class",
        "attempted_case_count",
        "success_case_count",
        "failed_case_count",
        "input_count_mismatch_count",
        "submitted_count_mismatch_count",
        "trace_event_count",
        "trace_validation_errors",
        "policy",
        "matrix_policy",
        "profiler_policy",
        "performance_policy",
    ]
    path.write_text("\n".join(f"{key}={result.get(key, '')}" for key in keys) + "\n", encoding="utf-8")


def _git_commit() -> str:
    git_head = REPO_ROOT / ".git" / "HEAD"
    try:
        head = git_head.read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref_path = REPO_ROOT / ".git" / head.removeprefix("ref: ")
            return ref_path.read_text(encoding="utf-8").strip()
        return head
    except OSError:
        return ""


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _which_python() -> str:
    return os.environ.get("PYTHON", "") or sys.executable


def main() -> int:
    return run_vllm_smoke(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
