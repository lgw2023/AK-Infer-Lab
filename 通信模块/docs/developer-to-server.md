# 开发机给服务器的任务说明

## 当前任务：P1.14 long prompt trace matrix

- 任务 ID：`runtime_long_prompt_trace_matrix_2026_0706_p1_014`
- 当前开发机分支：`main`
- 服务器同步方式：只执行 `git pull --ff-only`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_long_prompt_matrix_handoff.md`

P1.13 `runtime_long_prompt_trace_smoke_2026_0706_p1_013` 已完成，服务器现有 `Qwen3.5-4B + transformers + torch_npu` 路径可以在 `npu:6` 上完成 4 个 4K/8K 截断长 prompt 的顺序单请求 trace，`long_prompt_trace_matrix.jsonl` 校验 `errors=0`。P1.13 同时暴露 `torch_profiler_trace` 未成功导出，错误为 `AttributeError: 'NoneType' object has no attribute 'save'`，因此 P1.14 不把 profiler 导出作为主成功条件。

本轮只扩大长 prompt 覆盖面：顺序执行 `P000-P012` 的 13 个单请求，最大输入 cap 为 8192 tokens。仍不运行 vLLM、不安装包、不修环境、不跑 16K/32K full prompt、不跑并发、不输出性能或瓶颈归因结论。

## 本轮问题

请服务器回答：

1. `Qwen3.5-4B + transformers + torch_npu` 是否能在 `npu:6` 上完成全部 13 条长 prompt 的 4K/8K cap 顺序单请求 prefill/decode？
2. 每个 case 是否有非空 generated token 或文本？
3. 每个 case 的 `input_token_count` 是否等于 `min(full_token_count, cap_tokens)`？
4. 是否能生成合法的 `long_prompt_trace_matrix_full.jsonl` 并通过 P1 validator？
5. 如果失败，失败点是模型加载、tokenizer、NPU/OOM、具体 prompt 推理、trace 校验，还是可选 profiler 导出？

## 严格边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 使用现有 `transformers + torch_npu`
- 默认使用 `npu:6`，可由 `AK_SMALL_MODEL_DEVICE` 覆盖
- 顺序执行 `P000-P012` 的 13 个单请求 trace
- 默认跳过 profiler 导出；如显式设置 `AK_LONG_PROMPT_MATRIX_ENABLE_PROFILER=1`，只记录 profiler 成功或失败，不把它作为主成功条件
- 导出 trace、summary、generated texts、失败日志和邮件附件

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不运行 vLLM engine、serve、benchmark 或 vLLM-Ascend 任务
- 不运行 16K/32K full prompt，不运行 full P010 43216 tokens
- 不运行并发、burst、continuous batching 或 prefix cache 结论型测试
- 不复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息
- 不输出性能 benchmark、瓶颈归因、优化建议或 CANN device timeline pairing 结论

## 建议执行命令

请在服务器项目根目录执行：

```bash
set -euo pipefail

cd /data/node0_disk1/liguowei/AK-Infer-Lab
git pull --ff-only

RUN_ID=runtime_long_prompt_trace_matrix_2026_0706_p1_014
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
MODEL_PATH="${AK_SMALL_MODEL_PATH:-/data/node0_disk1/Public/Qwen3.5-4B}"
DEVICE="${AK_SMALL_MODEL_DEVICE:-npu:6}"
MAX_NEW_TOKENS="${AK_LONG_PROMPT_MATRIX_MAX_NEW_TOKENS:-4}"
ENABLE_PROFILER="${AK_LONG_PROMPT_MATRIX_ENABLE_PROFILER:-0}"
CONTRACT_DIR="工作记录与进度笔记本/p1_inference_contracts"
LONG_MANIFEST="${CONTRACT_DIR}/workload_long_manifest.yaml"

export RUN_ID ARTIFACT_DIR MODEL_PATH DEVICE MAX_NEW_TOKENS ENABLE_PROFILER CONTRACT_DIR LONG_MANIFEST
export PYTHONUNBUFFERED=1

mkdir -p "${ARTIFACT_DIR}/generated_texts"

{
  echo "run_id=${RUN_ID}"
  echo "commit=$(git rev-parse HEAD)"
  echo "timestamp=$(date -Is)"
  echo "hostname=$(hostname)"
  echo "python=$(command -v python)"
  echo "cwd=$(pwd)"
  echo "MODEL_PATH=${MODEL_PATH}"
  echo "DEVICE=${DEVICE}"
  echo "MAX_NEW_TOKENS=${MAX_NEW_TOKENS}"
  echo "ENABLE_PROFILER=${ENABLE_PROFILER}"
  echo "CONTRACT_DIR=${CONTRACT_DIR}"
  echo "LONG_MANIFEST=${LONG_MANIFEST}"
  echo "task_policy=existing_transformers_torch_npu_no_vllm_no_package_install"
  echo "selected_cases=P000@4096,P001@4096,P002@4096,P003@8192,P004@8192,P005@8192,P006@8192,P007@4096,P008@4096,P009@8192,P010@8192,P011@4096,P012@8192"
  echo "profiler_policy=candidate_only_optional_disabled_by_default"
} | tee "${ARTIFACT_DIR}/run_context.txt"

set +e
python -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest_inference_contracts.log" 2>&1
pytest_exit_code=$?
set -e
echo "pytest_exit_code=${pytest_exit_code}" | tee -a "${ARTIFACT_DIR}/run_context.txt"

python - <<'PY' > "${ARTIFACT_DIR}/package_inventory.tsv"
import importlib.metadata as metadata
import importlib.util

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

print("package\tmodule\tdistribution_version\tspec_found\torigin")
for dist_name, module_name in packages:
    try:
        version = metadata.version(dist_name)
    except metadata.PackageNotFoundError:
        version = ""
    spec = importlib.util.find_spec(module_name)
    print(
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
PY

python - <<'PY' > "${ARTIFACT_DIR}/model_path_precheck.txt"
import json
import os
from pathlib import Path

model_path = Path(os.environ["MODEL_PATH"])
print(f"model_path={model_path}")
print(f"exists={int(model_path.exists())}")
print(f"is_dir={int(model_path.is_dir())}")
for name in ["config.json", "tokenizer_config.json", "tokenizer.json", "generation_config.json"]:
    path = model_path / name
    print(f"{name}\texists={int(path.is_file())}\tbytes={path.stat().st_size if path.is_file() else ''}")
    if path.is_file() and name in {"config.json", "tokenizer_config.json"}:
        data = json.loads(path.read_text(encoding="utf-8"))
        if name == "config.json":
            print(f"config_model_type={data.get('model_type', '')}")
            print(f"config_architectures={data.get('architectures', '')}")
        if name == "tokenizer_config.json":
            print(f"tokenizer_class={data.get('tokenizer_class', '')}")
            print(f"model_max_length={data.get('model_max_length', '')}")
PY

set +e
python - <<'PY' > "${ARTIFACT_DIR}/long_prompt_trace_matrix_full.log" 2>&1
from __future__ import annotations

import json
import os
import time
import traceback
from contextlib import nullcontext
from pathlib import Path

import torch
import yaml
from transformers import AutoModelForCausalLM, AutoTokenizer

import torch_npu  # noqa: F401
from tools.inference_contracts.validation import validate_trace_fixture


RUN_ID = os.environ["RUN_ID"]
ARTIFACT_DIR = Path(os.environ["ARTIFACT_DIR"])
MODEL_PATH = os.environ["MODEL_PATH"]
DEVICE = os.environ["DEVICE"]
MAX_NEW_TOKENS = int(os.environ["MAX_NEW_TOKENS"])
ENABLE_PROFILER = os.environ.get("ENABLE_PROFILER", "0") == "1"
CONTRACT_DIR = Path(os.environ["CONTRACT_DIR"])
LONG_MANIFEST = Path(os.environ["LONG_MANIFEST"])
TRACE_PATH = ARTIFACT_DIR / "long_prompt_trace_matrix_full.jsonl"
SUMMARY_TSV = ARTIFACT_DIR / "long_prompt_trace_matrix_full_summary.tsv"
RESULT_JSON = ARTIFACT_DIR / "long_prompt_trace_matrix_full_result.json"
CONCLUSION_TXT = ARTIFACT_DIR / "long_prompt_trace_matrix_full_conclusion.txt"
PROFILER_SUMMARY = ARTIFACT_DIR / "torch_profiler_summary.json"
PROFILER_TRACE = ARTIFACT_DIR / "torch_profiler_trace.json"
PROFILER_OMITTED = ARTIFACT_DIR / "torch_profiler_trace.omitted.txt"
GENERATED_DIR = ARTIFACT_DIR / "generated_texts"

SELECTED_CASES = [
    {"case_id": "P000_cap4096", "prompt_id": "P000", "cap_tokens": 4096},
    {"case_id": "P001_cap4096", "prompt_id": "P001", "cap_tokens": 4096},
    {"case_id": "P002_cap4096", "prompt_id": "P002", "cap_tokens": 4096},
    {"case_id": "P003_cap8192", "prompt_id": "P003", "cap_tokens": 8192},
    {"case_id": "P004_cap8192", "prompt_id": "P004", "cap_tokens": 8192},
    {"case_id": "P005_cap8192", "prompt_id": "P005", "cap_tokens": 8192},
    {"case_id": "P006_cap8192", "prompt_id": "P006", "cap_tokens": 8192},
    {"case_id": "P007_cap4096", "prompt_id": "P007", "cap_tokens": 4096},
    {"case_id": "P008_cap4096", "prompt_id": "P008", "cap_tokens": 4096},
    {"case_id": "P009_cap8192", "prompt_id": "P009", "cap_tokens": 8192},
    {"case_id": "P010_cap8192", "prompt_id": "P010", "cap_tokens": 8192},
    {"case_id": "P011_cap4096", "prompt_id": "P011", "cap_tokens": 4096},
    {"case_id": "P012_cap8192", "prompt_id": "P012", "cap_tokens": 8192},
]


def now_ns() -> int:
    return time.monotonic_ns()


def truncate_head(token_ids: list[int], cap_tokens: int) -> tuple[list[int], str]:
    if len(token_ids) <= cap_tokens:
        return token_ids, "no_truncation"
    return token_ids[:cap_tokens], f"head_truncate_to_{cap_tokens}_tokens"


def make_event(
    *,
    case_id: str,
    prompt_id: str,
    request_index: int,
    phase: str,
    event_type: str,
    resource_scope: str,
    timestamp_ns: int,
    layer_id=None,
    op_name=None,
    kernel_name=None,
    stream_id=None,
    device_id=None,
    object_type=None,
    object_id=None,
    bytes_read=0,
    bytes_write=0,
    latency_us=0,
    queue_wait_us=0,
    overlap_ratio=None,
    policy_decision="none",
    hit_or_miss="not_applicable",
    stall_reason="unknown",
    evidence_source="runtime_queue_trace",
    artifact_path="long_prompt_trace_matrix_full.jsonl",
) -> dict:
    request_id = f"req_p1_long_prompt_full_{request_index:04d}_{case_id}"
    return {
        "schema_version": "0.1.0",
        "event_id": f"evt_{case_id}_{resource_scope}_{phase}_{event_type}_{request_index:04d}",
        "timestamp_ns": timestamp_ns,
        "time_base": "host_monotonic_ns",
        "trace_id": "trace_p1_long_prompt_matrix_full_0001",
        "request_id": request_id,
        "session_id": "session_p1_long_prompt_matrix_full",
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
        "source_tier": "none",
        "target_tier": "none",
        "bytes_read": bytes_read,
        "bytes_write": bytes_write,
        "latency_us": latency_us,
        "queue_wait_us": queue_wait_us,
        "overlap_ratio": overlap_ratio,
        "policy_decision": policy_decision,
        "hit_or_miss": hit_or_miss,
        "stall_reason": stall_reason,
        "evidence_source": evidence_source,
        "artifact_path": artifact_path,
        "prompt_id": prompt_id,
        "case_id": case_id,
    }


def count_profiler_candidates(path: Path) -> dict:
    if not path.is_file():
        return {
            "torch_profiler_trace_exists": 0,
            "torch_profiler_trace_bytes": 0,
            "torch_profiler_marker_event_count": 0,
            "torch_profiler_npu_event_candidate_count": 0,
        }
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {
        "torch_profiler_trace_exists": 1,
        "torch_profiler_trace_bytes": path.stat().st_size,
        "torch_profiler_marker_event_count": text.count("ak_p1_long_prompt_full"),
        "torch_profiler_npu_event_candidate_count": (
            text.count("npu") + text.count("NPU") + text.count("aclnn") + text.count("acl")
        ),
    }


def write_summary(rows: list[dict]) -> None:
    columns = [
        "case_id",
        "prompt_id",
        "cap_tokens",
        "full_token_count",
        "expected_input_token_count",
        "input_token_count",
        "generated_token_count",
        "status",
        "error_type",
        "error",
    ]
    with SUMMARY_TSV.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(columns) + "\n")
        for row in rows:
            handle.write("\t".join(str(row.get(column, "")) for column in columns) + "\n")


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    manifest = yaml.safe_load(LONG_MANIFEST.read_text(encoding="utf-8"))
    prompts = {entry["prompt_id"]: entry for entry in manifest["prompts"]}

    result = {
        "run_id": RUN_ID,
        "phase": "start",
        "status": "failed",
        "policy": "existing_transformers_torch_npu_no_vllm_no_package_install",
        "profiler_policy": "candidate_only_optional_disabled_by_default",
        "model_path": MODEL_PATH,
        "device": DEVICE,
        "max_new_tokens": MAX_NEW_TOKENS,
        "selected_cases": SELECTED_CASES,
        "rows": [],
        "trace_validation_errors": None,
        "trace_event_count": 0,
    }
    events = []
    profiler = None
    record_function = None

    try:
        result["phase"] = "tokenizer_load"
        tokenizer = AutoTokenizer.from_pretrained(
            MODEL_PATH,
            trust_remote_code=True,
            local_files_only=True,
        )
        if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
            tokenizer.pad_token = tokenizer.eos_token
        result["tokenizer_class"] = type(tokenizer).__name__
        result["tokenizer_model_max_length"] = getattr(tokenizer, "model_max_length", None)

        result["phase"] = "model_load"
        if hasattr(torch, "npu"):
            torch.npu.set_device(DEVICE)
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_PATH,
            trust_remote_code=True,
            local_files_only=True,
            torch_dtype="auto",
        )
        model.eval()
        model.to(DEVICE)
        result["model_class"] = type(model).__name__

        profiler_context = nullcontext(None)
        if ENABLE_PROFILER:
            try:
                from torch.profiler import ProfilerActivity, profile, record_function as rf

                record_function = rf
                profiler_context = profile(
                    activities=[ProfilerActivity.CPU],
                    record_shapes=False,
                    with_stack=False,
                )
                result["profiler_policy"] = "candidate_only_optional_enabled"
            except Exception as exc:
                result["profiler_setup_error"] = f"{type(exc).__name__}: {exc}"

        with profiler_context as profiler:
            for request_index, case in enumerate(SELECTED_CASES, start=1):
                case_id = case["case_id"]
                prompt_id = case["prompt_id"]
                cap_tokens = int(case["cap_tokens"])
                prompt = prompts[prompt_id]
                prompt_path = CONTRACT_DIR / prompt["prompt_path"]
                row = {
                    "case_id": case_id,
                    "prompt_id": prompt_id,
                    "cap_tokens": cap_tokens,
                    "full_token_count": prompt["measured_prompt_tokens_qwen3_5_4b"],
                    "expected_input_token_count": min(
                        prompt["measured_prompt_tokens_qwen3_5_4b"], cap_tokens
                    ),
                    "input_token_count": "",
                    "generated_token_count": "",
                    "status": "failed",
                    "error_type": "",
                    "error": "",
                }
                result["phase"] = f"case_{case_id}"

                try:
                    events.append(
                        make_event(
                            case_id=case_id,
                            prompt_id=prompt_id,
                            request_index=request_index,
                            phase="enqueue",
                            event_type="point",
                            resource_scope="request_runtime_profile",
                            timestamp_ns=now_ns(),
                            stream_id="host:python",
                            device_id="host:cpu",
                        )
                    )

                    text = prompt_path.read_text(encoding="utf-8")
                    tokenize_start = now_ns()
                    full_ids = tokenizer.encode(text, add_special_tokens=False)
                    input_ids, truncation_policy = truncate_head(full_ids, cap_tokens)
                    tokenize_end = now_ns()
                    row["full_token_count"] = len(full_ids)
                    row["expected_input_token_count"] = min(len(full_ids), cap_tokens)
                    row["input_token_count"] = len(input_ids)
                    if row["input_token_count"] != row["expected_input_token_count"]:
                        row["error_type"] = "input_count_mismatch"
                        row["error"] = "input_token_count != min(full_token_count, cap_tokens)"
                        result["rows"].append(row)
                        break
                    events.append(
                        make_event(
                            case_id=case_id,
                            prompt_id=prompt_id,
                            request_index=request_index,
                            phase="tokenize",
                            event_type="point",
                            resource_scope="request_runtime_profile",
                            timestamp_ns=tokenize_end,
                            op_name="tokenizer_encode",
                            stream_id="host:tokenizer",
                            device_id="host:cpu",
                            latency_us=(tokenize_end - tokenize_start) // 1000,
                            policy_decision=truncation_policy,
                        )
                    )

                    input_tensor = torch.tensor([input_ids], dtype=torch.long).to(DEVICE)
                    attention_mask = torch.ones_like(input_tensor)
                    kv_object_id = f"kv:{case_id}:L00"
                    events.append(
                        make_event(
                            case_id=case_id,
                            prompt_id=prompt_id,
                            request_index=request_index,
                            phase="prefill",
                            event_type="lifecycle",
                            resource_scope="state_object_profile",
                            timestamp_ns=now_ns(),
                            layer_id=0,
                            op_name="kv_cache_materialize",
                            stream_id=f"{DEVICE}:default",
                            device_id=DEVICE,
                            object_type="kv",
                            object_id=kv_object_id,
                            policy_decision=truncation_policy,
                        )
                    )
                    events.append(
                        make_event(
                            case_id=case_id,
                            prompt_id=prompt_id,
                            request_index=request_index,
                            phase="prefill",
                            event_type="span_end",
                            resource_scope="transfer_overlap_profile",
                            timestamp_ns=now_ns(),
                            layer_id=0,
                            op_name="host_to_device_input_ids",
                            stream_id=f"{DEVICE}:default",
                            device_id=DEVICE,
                            object_type="kv",
                            object_id=kv_object_id,
                            bytes_read=len(input_ids) * 8,
                            bytes_write=len(input_ids) * 8,
                            overlap_ratio=0.0,
                            evidence_source="runtime_trace_smoke",
                        )
                    )

                    marker = f"ak_p1_long_prompt_full_{case_id}"
                    marker_context = record_function(marker) if record_function else nullcontext()
                    prefill_start = now_ns()
                    events.append(
                        make_event(
                            case_id=case_id,
                            prompt_id=prompt_id,
                            request_index=request_index,
                            phase="prefill",
                            event_type="span_start",
                            resource_scope="operator_timeline_profile",
                            timestamp_ns=prefill_start,
                            layer_id=0,
                            op_name="model_generate_prefill_decode",
                            kernel_name="unknown",
                            stream_id=f"{DEVICE}:default",
                            device_id=DEVICE,
                            object_type="kv",
                            object_id=kv_object_id,
                            policy_decision=truncation_policy,
                            evidence_source="torch_profiler_record_function",
                        )
                    )
                    with torch.inference_mode(), marker_context:
                        output = model.generate(
                            input_ids=input_tensor,
                            attention_mask=attention_mask,
                            max_new_tokens=MAX_NEW_TOKENS,
                            do_sample=False,
                            use_cache=True,
                            pad_token_id=tokenizer.pad_token_id,
                            eos_token_id=tokenizer.eos_token_id,
                        )
                    if hasattr(torch, "npu"):
                        torch.npu.synchronize()
                    prefill_end = now_ns()
                    events.append(
                        make_event(
                            case_id=case_id,
                            prompt_id=prompt_id,
                            request_index=request_index,
                            phase="prefill",
                            event_type="span_end",
                            resource_scope="operator_timeline_profile",
                            timestamp_ns=prefill_end,
                            layer_id=0,
                            op_name="model_generate_prefill_decode",
                            kernel_name="unknown",
                            stream_id=f"{DEVICE}:default",
                            device_id=DEVICE,
                            object_type="kv",
                            object_id=kv_object_id,
                            latency_us=(prefill_end - prefill_start) // 1000,
                            policy_decision=truncation_policy,
                            evidence_source="torch_profiler_record_function",
                        )
                    )

                    generated_ids = output[0, input_tensor.shape[1] :].detach().cpu().tolist()
                    generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
                    row["generated_token_count"] = len(generated_ids)
                    row["status"] = "success" if generated_ids else "failed"
                    if not generated_ids:
                        row["error_type"] = "empty_generation"
                        row["error"] = "model.generate returned zero new tokens"
                    (GENERATED_DIR / f"{case_id}.txt").write_text(generated_text, encoding="utf-8")
                    (GENERATED_DIR / f"{case_id}_token_ids.json").write_text(
                        json.dumps(generated_ids, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    events.append(
                        make_event(
                            case_id=case_id,
                            prompt_id=prompt_id,
                            request_index=request_index,
                            phase="decode",
                            event_type="point",
                            resource_scope="request_runtime_profile",
                            timestamp_ns=now_ns(),
                            op_name="model_generate_decode",
                            stream_id=f"{DEVICE}:default",
                            device_id=DEVICE,
                            latency_us=(prefill_end - prefill_start) // 1000,
                            policy_decision=truncation_policy,
                        )
                    )
                except Exception as exc:
                    row["status"] = "failed"
                    row["error_type"] = type(exc).__name__
                    row["error"] = str(exc).replace("\n", " ")[:1000]
                    result["error_traceback"] = traceback.format_exc()
                    result["rows"].append(row)
                    break

                result["rows"].append(row)
                if row["status"] != "success":
                    break

            if ENABLE_PROFILER and profiler is not None:
                try:
                    profiler.export_chrome_trace(str(PROFILER_TRACE))
                except Exception as exc:
                    result["profiler_export_error"] = f"{type(exc).__name__}: {exc}"

        if hasattr(torch, "npu"):
            torch.npu.empty_cache()

    except Exception as exc:
        result["status"] = "failed"
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
        result["error_traceback"] = traceback.format_exc()

    with TRACE_PATH.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    result["trace_event_count"] = len(events)

    if events:
        validation = validate_trace_fixture(TRACE_PATH)
        result["trace_validation_errors"] = len(validation.errors)
        result["trace_validation_error_messages"] = validation.errors
        (ARTIFACT_DIR / "long_prompt_trace_matrix_full_validation.txt").write_text(
            "\n".join(validation.errors) if validation.errors else "errors=0\n",
            encoding="utf-8",
        )
    else:
        result["trace_validation_errors"] = None
        (ARTIFACT_DIR / "long_prompt_trace_matrix_full_validation.txt").write_text(
            "errors=trace_not_generated\n",
            encoding="utf-8",
        )

    profiler_counts = count_profiler_candidates(PROFILER_TRACE)
    result.update(profiler_counts)
    if PROFILER_TRACE.is_file() and PROFILER_TRACE.stat().st_size > 25_000_000:
        PROFILER_OMITTED.write_text(
            f"torch_profiler_trace.json omitted from zip because bytes={PROFILER_TRACE.stat().st_size}\n",
            encoding="utf-8",
        )
        PROFILER_TRACE.unlink()
        result["torch_profiler_trace_omitted_from_zip"] = 1
    else:
        result["torch_profiler_trace_omitted_from_zip"] = 0

    write_summary(result["rows"])
    attempted = len(result["rows"])
    success_count = sum(1 for row in result["rows"] if row.get("status") == "success")
    input_count_mismatch_count = sum(
        1
        for row in result["rows"]
        if row.get("input_token_count") != row.get("expected_input_token_count")
    )
    result["attempted_case_count"] = attempted
    result["success_case_count"] = success_count
    result["failed_case_count"] = attempted - success_count
    result["input_count_mismatch_count"] = input_count_mismatch_count
    result["matrix_status"] = (
        "success"
        if success_count == len(SELECTED_CASES)
        and result.get("trace_validation_errors") == 0
        and input_count_mismatch_count == 0
        else "failed"
    )
    result["status"] = result["matrix_status"]
    result["phase"] = "complete"

    RESULT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    PROFILER_SUMMARY.write_text(
        json.dumps(
            {
                key: result.get(key)
                for key in [
                    "profiler_policy",
                    "profiler_setup_error",
                    "profiler_export_error",
                    "torch_profiler_trace_exists",
                    "torch_profiler_trace_bytes",
                    "torch_profiler_marker_event_count",
                    "torch_profiler_npu_event_candidate_count",
                    "torch_profiler_trace_omitted_from_zip",
                ]
                if key in result
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    CONCLUSION_TXT.write_text(
        "\n".join(
            [
                f"status={result['status']}",
                f"matrix_status={result['matrix_status']}",
                f"phase={result['phase']}",
                f"model_path={MODEL_PATH}",
                f"device={DEVICE}",
                f"tokenizer_class={result.get('tokenizer_class', '')}",
                f"model_class={result.get('model_class', '')}",
                f"attempted_case_count={attempted}",
                f"success_case_count={success_count}",
                f"failed_case_count={result['failed_case_count']}",
                f"input_count_mismatch_count={input_count_mismatch_count}",
                f"trace_event_count={result['trace_event_count']}",
                f"trace_validation_errors={result.get('trace_validation_errors')}",
                f"torch_profiler_trace_exists={result.get('torch_profiler_trace_exists')}",
                f"torch_profiler_marker_event_count={result.get('torch_profiler_marker_event_count')}",
                f"torch_profiler_npu_event_candidate_count={result.get('torch_profiler_npu_event_candidate_count')}",
                "selected_cases=P000@4096,P001@4096,P002@4096,P003@8192,P004@8192,P005@8192,P006@8192,P007@4096,P008@4096,P009@8192,P010@8192,P011@4096,P012@8192",
                "execution_policy=existing_transformers_torch_npu_no_vllm_no_package_install",
                "performance_policy=trace_matrix_only_no_perf_or_bottleneck_conclusion",
                "profiler_policy=candidate_only_optional_disabled_by_default",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["matrix_status"] == "success" else 1


raise SystemExit(main())
PY
matrix_exit_code=$?
set -e
echo "long_prompt_trace_matrix_full_exit_code=${matrix_exit_code}" | tee -a "${ARTIFACT_DIR}/run_context.txt"
cat "${ARTIFACT_DIR}/long_prompt_trace_matrix_full.log"

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt"
  echo
  echo "## long_prompt_trace_matrix_full_conclusion"
  cat "${ARTIFACT_DIR}/long_prompt_trace_matrix_full_conclusion.txt"
  echo
  echo "## long_prompt_trace_matrix_full_summary"
  cat "${ARTIFACT_DIR}/long_prompt_trace_matrix_full_summary.tsv"
  echo
  echo "## validation"
  cat "${ARTIFACT_DIR}/long_prompt_trace_matrix_full_validation.txt"
  echo
  echo "## profiler_summary"
  cat "${ARTIFACT_DIR}/torch_profiler_summary.json"
  echo
  echo "## package_inventory"
  cat "${ARTIFACT_DIR}/package_inventory.tsv"
  echo
  echo "## model_path_precheck"
  cat "${ARTIFACT_DIR}/model_path_precheck.txt"
} > "${ARTIFACT_DIR}/summary.txt"

(
  cd 工作记录与进度笔记本/runtime_trace_smokes
  zip -r -X "${RUN_ID}.zip" "${RUN_ID}"
)

ZIP_PATH="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}.zip"

{
  echo "P1.14 long prompt trace matrix 已完成。"
  echo
  echo "任务 ID: ${RUN_ID}"
  echo "附件: ${ZIP_PATH}"
  echo
  cat "${ARTIFACT_DIR}/summary.txt"
  echo
  echo "执行边界："
  echo "- 本轮使用 Qwen3.5-4B + transformers + torch_npu"
  echo "- 本轮会加载模型权重并使用 NPU"
  echo "- 本轮只执行 P000-P012 的 4K/8K cap 顺序单请求 trace matrix"
  echo "- 默认不启用 profiler 导出；如启用失败也只记录为 candidate_only_optional"
  echo "- 未运行 vLLM serve/benchmark、并发、burst、continuous batching 或 prefix cache 结论型测试"
  echo "- 未安装、升级、卸载或修复任何包"
  echo "- 未修改 models/、Public/、CANN/driver/runtime/vLLM 源码"
  echo "- 本轮不输出性能或瓶颈归因结论"
} > "${ARTIFACT_DIR}/mail_body.txt"

python 通信模块/send_notify.py \
  -s "[AK服务器] 任务完成：long prompt trace matrix ${RUN_ID}" \
  -b "$(cat "${ARTIFACT_DIR}/mail_body.txt")" \
  -a "${ZIP_PATH}"

exit "${matrix_exit_code}"
```

## 回传要求

请邮件回传 zip 附件，并在正文保留：

- `run_context.txt`
- `long_prompt_trace_matrix_full_conclusion.txt`
- `long_prompt_trace_matrix_full_summary.tsv`
- `long_prompt_trace_matrix_full_validation.txt`
- `torch_profiler_summary.json`
- `package_inventory.tsv`
- `model_path_precheck.txt`
- 如果失败，保留 `long_prompt_trace_matrix_full.log` 中的 traceback

成功口径：

- `pytest_exit_code=0`
- `long_prompt_trace_matrix_full_exit_code=0`
- `matrix_status=success`
- `attempted_case_count=13`
- `success_case_count=13`
- `input_count_mismatch_count=0`
- `trace_validation_errors=0`

失败也请回传完整附件，不要在服务器上现场修包、换框架、改模型路径或重试 vLLM。
