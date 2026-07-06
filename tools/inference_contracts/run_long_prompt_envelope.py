from __future__ import annotations

import argparse
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


DEFAULT_RUN_ID = "runtime_long_prompt_envelope_decode_2026_0706_p1_015"
DEFAULT_CONTRACT_DIR = REPO_ROOT / "工作记录与进度笔记本" / "p1_inference_contracts"
DEFAULT_LONG_MANIFEST = DEFAULT_CONTRACT_DIR / "workload_long_manifest.yaml"
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "工作记录与进度笔记本" / "runtime_trace_smokes"

ENVELOPE_CASES = [
    {"case_id": "P002_cap4096_gen32", "prompt_id": "P002", "cap_tokens": 4096, "max_new_tokens": 32},
    {"case_id": "P003_cap8192_gen32", "prompt_id": "P003", "cap_tokens": 8192, "max_new_tokens": 32},
    {"case_id": "P005_cap8192_gen128", "prompt_id": "P005", "cap_tokens": 8192, "max_new_tokens": 128},
    {"case_id": "P006_cap12288_gen32", "prompt_id": "P006", "cap_tokens": 12288, "max_new_tokens": 32},
    {"case_id": "P007_cap4096_gen32", "prompt_id": "P007", "cap_tokens": 4096, "max_new_tokens": 32},
    {"case_id": "P008_cap4096_gen32", "prompt_id": "P008", "cap_tokens": 4096, "max_new_tokens": 32},
    {"case_id": "P010_cap16384_gen32", "prompt_id": "P010", "cap_tokens": 16384, "max_new_tokens": 32},
    {"case_id": "P012_cap8192_gen128", "prompt_id": "P012", "cap_tokens": 8192, "max_new_tokens": 128},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded long-prompt input/output envelope matrix on the Ascend server."
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
    parser.add_argument("--device", default=os.environ.get("AK_SMALL_MODEL_DEVICE", "npu:6"))
    parser.add_argument("--contract-dir", type=Path, default=DEFAULT_CONTRACT_DIR)
    parser.add_argument("--long-manifest", type=Path, default=DEFAULT_LONG_MANIFEST)
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
        f"DEVICE={args.device}",
        f"CONTRACT_DIR={args.contract_dir}",
        f"LONG_MANIFEST={args.long_manifest}",
        "task_policy=existing_transformers_torch_npu_no_vllm_no_package_install",
        "matrix_policy=long_prompt_input_output_envelope_decode_depth",
        "profiler_policy=disabled_not_part_of_this_task",
        "performance_policy=trace_matrix_only_no_perf_or_bottleneck_conclusion",
        "selected_cases="
        + ",".join(
            f"{case['prompt_id']}@{case['cap_tokens']}+{case['max_new_tokens']}"
            for case in selected_cases
        ),
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


def run_envelope(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir or (DEFAULT_ARTIFACT_ROOT / args.run_id)
    generated_dir = artifact_dir / "generated_texts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)

    write_run_context(artifact_dir / "run_context.txt", args, ENVELOPE_CASES)
    write_package_inventory(artifact_dir / "package_inventory.tsv")
    write_model_path_precheck(artifact_dir / "model_path_precheck.txt", args.model_path)

    trace_path = artifact_dir / "long_prompt_envelope_decode_trace.jsonl"
    summary_path = artifact_dir / "long_prompt_envelope_decode_summary.tsv"
    result_path = artifact_dir / "long_prompt_envelope_decode_result.json"
    conclusion_path = artifact_dir / "long_prompt_envelope_decode_conclusion.txt"
    validation_path = artifact_dir / "long_prompt_envelope_decode_validation.txt"

    rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    fatal_error = ""
    tokenizer_class = ""
    model_class = ""

    try:
        import torch
        import torch_npu  # noqa: F401
        from transformers import AutoModelForCausalLM, AutoTokenizer

        prompt_index = load_prompt_index(args.contract_dir, args.long_manifest)
        tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(args.model_path, trust_remote_code=True)
        model.eval()
        model.to(args.device)
        tokenizer_class = tokenizer.__class__.__name__
        model_class = model.__class__.__name__

        for request_index, case in enumerate(ENVELOPE_CASES, start=1):
            rows.append(
                run_case(
                    torch=torch,
                    tokenizer=tokenizer,
                    model=model,
                    prompt_index=prompt_index,
                    case=case,
                    request_index=request_index,
                    device=args.device,
                    trace_path=trace_path,
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
    status = "success" if not fatal_error and failed_count == 0 and not validation_errors else "failed"

    _write_summary(summary_path, rows)
    result = {
        "run_id": args.run_id,
        "status": status,
        "matrix_status": status,
        "phase": "complete" if not fatal_error else "fatal",
        "model_path": args.model_path,
        "device": args.device,
        "tokenizer_class": tokenizer_class,
        "model_class": model_class,
        "attempted_case_count": len(rows),
        "success_case_count": success_count,
        "failed_case_count": failed_count,
        "input_count_mismatch_count": input_count_mismatch_count,
        "trace_event_count": len(events),
        "trace_validation_errors": len(validation_errors),
        "trace_validation_error_messages": validation_errors,
        "fatal_error": fatal_error,
        "policy": "existing_transformers_torch_npu_no_vllm_no_package_install",
        "matrix_policy": "long_prompt_input_output_envelope_decode_depth",
        "profiler_policy": "disabled_not_part_of_this_task",
        "performance_policy": "trace_matrix_only_no_perf_or_bottleneck_conclusion",
        "rows": rows,
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_conclusion(conclusion_path, result)
    return 0 if status == "success" else 1


def run_case(
    *,
    torch: Any,
    tokenizer: Any,
    model: Any,
    prompt_index: dict[str, dict[str, Any]],
    case: dict[str, Any],
    request_index: int,
    device: str,
    trace_path: Path,
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
        "generated_token_count": 0,
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
        row["full_token_count"] = len(token_ids)
        row["expected_input_token_count"] = min(len(token_ids), cap_tokens)
        row["input_token_count"] = len(selected_token_ids)

        request_id = f"req_p1_long_prompt_envelope_{request_index:04d}_{case_id}"
        stream_id = f"{device}:default_stream"
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
            )
        )

        input_ids = torch.tensor([selected_token_ids], dtype=torch.long, device=device)
        prefill_start = time.monotonic_ns()
        with torch.inference_mode():
            output_ids = model.generate(
                input_ids=input_ids,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                use_cache=True,
                pad_token_id=tokenizer.eos_token_id,
            )
        end_ts = time.monotonic_ns()
        generated_ids = output_ids[0, input_ids.shape[1] :].detach().cpu().tolist()
        generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
        (generated_dir / f"{case_id}.txt").write_text(generated_text, encoding="utf-8")
        (generated_dir / f"{case_id}_token_ids.json").write_text(
            json.dumps(generated_ids, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        row["generated_token_count"] = len(generated_ids)
        row["status"] = "success" if generated_ids else "failed"
        if not generated_ids:
            row["error_type"] = "empty_generation"
            row["error"] = "model.generate returned no new tokens"

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
                    prefill_start,
                    layer_id=0,
                    op_name="model.generate_prefill_candidate",
                    stream_id=stream_id,
                    device_id=device,
                ),
                _event(
                    case_id,
                    request_id,
                    request_index,
                    "prefill",
                    "lifecycle",
                    "state_object_profile",
                    prefill_start,
                    layer_id=0,
                    stream_id=stream_id,
                    device_id=device,
                    object_type="kv",
                    object_id=kv_object_id,
                    target_tier="npu_hbm",
                    bytes_write=len(selected_token_ids) * 2,
                    policy_decision="bounded_long_prompt_envelope",
                ),
                _event(
                    case_id,
                    request_id,
                    request_index,
                    "prefill",
                    "metric_sample",
                    "transfer_overlap_profile",
                    prefill_start,
                    layer_id=0,
                    stream_id=stream_id,
                    device_id=device,
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
                    op_name="model.generate_prefill_candidate",
                    stream_id=stream_id,
                    device_id=device,
                    latency_us=max(0, (end_ts - prefill_start) // 1000),
                ),
                _event(
                    case_id,
                    request_id,
                    request_index,
                    "decode",
                    "metric_sample",
                    "request_runtime_profile",
                    end_ts,
                    latency_us=max(0, (end_ts - prefill_start) // 1000),
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
        "trace_id": "trace_p1_long_prompt_envelope_decode_0001",
        "request_id": request_id,
        "session_id": "session_p1_long_prompt_envelope_decode",
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
        "evidence_source": "runtime_queue_trace",
        "artifact_path": "long_prompt_envelope_decode_trace.jsonl",
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
        "generated_token_count",
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
        "device",
        "tokenizer_class",
        "model_class",
        "attempted_case_count",
        "success_case_count",
        "failed_case_count",
        "input_count_mismatch_count",
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
    return run_envelope(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
