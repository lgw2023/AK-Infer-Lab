# 开发机 -> 服务器消息

> 本文件每次只保留当前待执行任务；旧历史信息已清空。

## 当前任务：P1.11 remaining prompt trace matrix 受限验证

- 任务 ID：`runtime_small_model_remaining_prompt_trace_2026_0706_p1_010`
- 证据基线：`obs_2026_0705_atlas800t_a2_006`
- P1.6 profiler bridge：`runtime_profiler_bridge_2026_0706_p1_005`
- P1.9 small model load smoke：`runtime_small_model_load_smoke_2026_0706_p1_008`
- P1.10 small model trace matrix：`runtime_small_model_trace_matrix_2026_0706_p1_009`
- 当前契约入口：`工作记录与进度笔记本/p1_inference_contracts/`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_small_model_remaining_prompt_trace_handoff.md`

P1.10 最新反馈邮件时间为 2026-07-06 10:50:21 CST，服务器执行 commit 为 `42fa210`。`Qwen3.5-4B` 已在同一模型加载会话中完成 `P000,P001,P002` 顺序单请求 trace；`small_model_trace_matrix.jsonl` 校验 `errors=0`、`events=18`，`torch_profiler_trace.json` 含 24 个 `ak_p1_trace_matrix_*` marker 和 407700 个 NPU/op 候选事件。P1.10 还完成 `P000-P012` tokenizer 校准，当前 prompt 文件实测只有 51-185 tokens，说明它们目前是 shape fixture，不是真正的 4K/8K/16K/32K 长上下文负载。

本轮不是重复 P1.10 的前三条 prompt。P1.11 只补齐当前短形态样例中的 `P003-P012` 顺序单请求 trace；和 P1.10 合并后，可形成当前 `P000-P012` shape fixture 的完整小模型 trace 覆盖。本轮仍使用现有 `Qwen3.5-4B + transformers + torch_npu` 手动路径，不安装包、不修环境、不运行 vLLM 服务、不跑长上下文/并发/burst/continuous batching workload、不输出性能 benchmark 或瓶颈归因结论。

## 服务器执行边界

请执行：

- 在服务器项目根目录 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行本文件命令。
- 通过 `git pull --ff-only` 获取开发机已提交的最新项目状态。
- 使用服务器当前 conda 环境；不创建新环境。
- 默认模型路径为 `/data/node0_disk1/Public/Qwen3.5-4B`，可用 `AK_SMALL_MODEL_PATH=/path/to/model` 覆盖。
- 默认 NPU 设备为 `npu:6`，可用 `AK_OBS_NPU_DEVICE=npu:<id>` 覆盖。
- 默认复核 `P000-P012` 的 tokenizer token 数。
- 默认只对 `P003-P012` 执行顺序单请求 trace。
- 默认每条请求最多截断到 4096 tokens，最多生成 4 个 token。
- 产出并邮件回传 `runtime_small_model_remaining_prompt_trace_2026_0706_p1_010.zip`。

请不要执行：

- 不要安装、升级、卸载或修复 `transformers`、`vllm`、`vllm_ascend`、`mindie`、`mindspore` 或其他包。
- 不要创建新 conda 环境。
- 不要运行 vLLM engine、serve、benchmark、长上下文 workload 或并发 P000-P012 workload。
- 不要运行并发、burst、continuous batching 或 prefix cache 结论型测试。
- 不要复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件。
- 不要修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码。
- 不要自动修复或重装 `ascend910b-driver`。
- 不要在服务器上修改、提交或 push 项目代码。
- 不要发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。

## 本轮必须回答的问题

- 复核 `Qwen3.5-4B` tokenizer 对 `P000-P012` 的真实 token 数是否与 P1.10 一致。
- 默认 `P003-P012` 十个 prompt 是否都能在同一个模型加载会话中完成顺序单请求 prefill/decode？
- 每个 `P003-P012` 请求是否都能产生非空 token 或文本输出？
- 能否生成并通过校验 `small_model_trace_matrix.jsonl`？
- 能否导出同一份 `torch_profiler_trace.json`，其中包含 `ak_p1_trace_matrix_P003` 到 `P012` 的 marker 与 NPU/op 事件候选？
- 如果失败，失败点是 prompt/tokenizer、模型推理、NPU/OOM、profiler 导出，还是 trace 校验？

## 执行命令

在昇腾服务器项目根目录执行：

```bash
set -u

git pull --ff-only
PULL_STATUS=$?
if [ "${PULL_STATUS}" -ne 0 ]; then
  exit "${PULL_STATUS}"
fi

RUN_ID=runtime_small_model_remaining_prompt_trace_2026_0706_p1_010
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
MODEL_PATH="${AK_SMALL_MODEL_PATH:-/data/node0_disk1/Public/Qwen3.5-4B}"
PROMPT_ROOT="${AK_SMALL_MODEL_PROMPT_ROOT:-工作记录与进度笔记本/p1_inference_contracts/prompts}"
AK_OBS_NPU_DEVICE="${AK_OBS_NPU_DEVICE:-npu:6}"
AK_TOKEN_CALIBRATION_PROMPTS="${AK_TOKEN_CALIBRATION_PROMPTS:-P000,P001,P002,P003,P004,P005,P006,P007,P008,P009,P010,P011,P012}"
AK_TRACE_MATRIX_PROMPTS="${AK_TRACE_MATRIX_PROMPTS:-P003,P004,P005,P006,P007,P008,P009,P010,P011,P012}"
AK_TRACE_MATRIX_MAX_INPUT_TOKENS="${AK_TRACE_MATRIX_MAX_INPUT_TOKENS:-4096}"
AK_TRACE_MATRIX_MAX_NEW_TOKENS="${AK_TRACE_MATRIX_MAX_NEW_TOKENS:-4}"
AK_TRACE_MATRIX_TIMEOUT="${AK_TRACE_MATRIX_TIMEOUT:-90m}"
export RUN_ID ARTIFACT_DIR MODEL_PATH PROMPT_ROOT AK_OBS_NPU_DEVICE
export AK_TOKEN_CALIBRATION_PROMPTS AK_TRACE_MATRIX_PROMPTS
export AK_TRACE_MATRIX_MAX_INPUT_TOKENS AK_TRACE_MATRIX_MAX_NEW_TOKENS

rm -rf "${ARTIFACT_DIR}"
mkdir -p "${ARTIFACT_DIR}"

{
  echo "run_id=${RUN_ID}"
  echo "commit=$(git rev-parse --short HEAD)"
  echo "timestamp=$(date -Is)"
  echo "hostname=$(hostname)"
  echo "python=$(command -v python || true)"
  echo "cwd=$(pwd)"
  echo "MODEL_PATH=${MODEL_PATH}"
  echo "PROMPT_ROOT=${PROMPT_ROOT}"
  echo "AK_OBS_NPU_DEVICE=${AK_OBS_NPU_DEVICE}"
  echo "AK_TOKEN_CALIBRATION_PROMPTS=${AK_TOKEN_CALIBRATION_PROMPTS}"
  echo "AK_TRACE_MATRIX_PROMPTS=${AK_TRACE_MATRIX_PROMPTS}"
  echo "AK_TRACE_MATRIX_MAX_INPUT_TOKENS=${AK_TRACE_MATRIX_MAX_INPUT_TOKENS}"
  echo "AK_TRACE_MATRIX_MAX_NEW_TOKENS=${AK_TRACE_MATRIX_MAX_NEW_TOKENS}"
  echo "AK_TRACE_MATRIX_TIMEOUT=${AK_TRACE_MATRIX_TIMEOUT}"
} | tee "${ARTIFACT_DIR}/run_context.txt"

python -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest_inference_contracts.log" 2>&1
PYTEST_STATUS=$?
cat "${ARTIFACT_DIR}/pytest_inference_contracts.log"
echo "pytest_exit_code=${PYTEST_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

python - <<'PY' > "${ARTIFACT_DIR}/package_inventory.tsv" 2>&1
import importlib.metadata as metadata
import importlib.util

probes = [
    ("torch", "torch", ("torch",)),
    ("torch_npu", "torch_npu", ("torch-npu", "torch_npu")),
    ("transformers", "transformers", ("transformers",)),
    ("tokenizers", "tokenizers", ("tokenizers",)),
    ("sentencepiece", "sentencepiece", ("sentencepiece",)),
    ("accelerate", "accelerate", ("accelerate",)),
    ("safetensors", "safetensors", ("safetensors",)),
    ("vllm", "vllm", ("vllm",)),
    ("vllm_ascend", "vllm_ascend", ("vllm-ascend", "vllm_ascend")),
    ("mindie", "mindie", ("mindie",)),
    ("mindspore", "mindspore", ("mindspore",)),
]

def version_for(distribution_names):
    for name in distribution_names:
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return ""

print("package\tmodule\tdistribution_version\tspec_found\torigin")
for package, module_name, distributions in probes:
    spec = importlib.util.find_spec(module_name)
    origin = getattr(spec, "origin", "") if spec is not None else ""
    print("\t".join([
        package,
        module_name,
        version_for(distributions),
        "1" if spec is not None else "0",
        origin or "",
    ]))
PY
PACKAGE_STATUS=$?
cat "${ARTIFACT_DIR}/package_inventory.tsv"
echo "package_inventory_exit_code=${PACKAGE_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

python - <<'PY' > "${ARTIFACT_DIR}/model_path_precheck.txt" 2>&1
import json
import os
from pathlib import Path

model_path = Path(os.environ["MODEL_PATH"]).expanduser()
print(f"model_path={model_path}")
print(f"exists={1 if model_path.exists() else 0}")
print(f"is_dir={1 if model_path.is_dir() else 0}")
for name in ["config.json", "tokenizer_config.json", "generation_config.json", "model.safetensors.index.json"]:
    path = model_path / name
    try:
        stat = path.stat()
        print(f"{name}\texists=1\tbytes={stat.st_size}")
        if name.endswith(".json") and stat.st_size <= 200000:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            if name == "config.json":
                print(f"config_model_type={data.get('model_type', '')}")
                print(f"config_architectures={data.get('architectures', '')}")
            if name == "tokenizer_config.json":
                print(f"tokenizer_class={data.get('tokenizer_class', '')}")
                print(f"model_max_length={data.get('model_max_length', '')}")
    except FileNotFoundError:
        print(f"{name}\texists=0\tbytes=")
    except Exception as exc:
        print(f"{name}\terror={type(exc).__name__}: {exc}")
PY
PRECHECK_STATUS=$?
cat "${ARTIFACT_DIR}/model_path_precheck.txt"
echo "model_path_precheck_exit_code=${PRECHECK_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

run_matrix() {
python - <<'PY'
import json
import os
import sys
import time
import traceback
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
model_path = Path(os.environ["MODEL_PATH"]).expanduser()
prompt_root = Path(os.environ["PROMPT_ROOT"])
device = os.environ.get("AK_OBS_NPU_DEVICE", "npu:6")
calibration_ids = [item.strip() for item in os.environ["AK_TOKEN_CALIBRATION_PROMPTS"].split(",") if item.strip()]
matrix_ids = [item.strip() for item in os.environ["AK_TRACE_MATRIX_PROMPTS"].split(",") if item.strip()]
max_input_tokens = int(os.environ.get("AK_TRACE_MATRIX_MAX_INPUT_TOKENS", "4096"))
max_new_tokens = max(2, int(os.environ.get("AK_TRACE_MATRIX_MAX_NEW_TOKENS", "8")))

result_path = artifact_dir / "small_model_trace_matrix_result.json"
conclusion_path = artifact_dir / "small_model_trace_matrix_conclusion.txt"
error_path = artifact_dir / "small_model_trace_matrix_error.txt"
trace_path = artifact_dir / "small_model_trace_matrix.jsonl"
trace_validation_path = artifact_dir / "small_model_trace_matrix_validation.txt"
token_calibration_path = artifact_dir / "token_calibration.tsv"
matrix_summary_path = artifact_dir / "small_model_trace_matrix_summary.tsv"
profiler_path = artifact_dir / "torch_profiler_trace.json"
profiler_summary_path = artifact_dir / "torch_profiler_summary.json"
generated_dir = artifact_dir / "generated_texts"
generated_dir.mkdir(exist_ok=True)

result = {
    "run_id": os.environ["RUN_ID"],
    "status": "started",
    "phase": "init",
    "model_path": str(model_path),
    "prompt_root": str(prompt_root),
    "device": device,
    "calibration_prompt_ids": calibration_ids,
    "matrix_prompt_ids": matrix_ids,
    "max_input_tokens": max_input_tokens,
    "max_new_tokens": max_new_tokens,
}
calibration_rows = []
matrix_rows = []
events = []

def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

def update(**kwargs):
    result.update(kwargs)
    write_json(result_path, result)

def write_conclusion():
    lines = [
        f"matrix_status={result.get('status', '')}",
        f"failure_phase={result.get('failure_phase', '')}",
        f"model_path={result.get('model_path', '')}",
        f"device={result.get('device', '')}",
        f"config_class={result.get('config_class', '')}",
        f"tokenizer_class={result.get('tokenizer_class', '')}",
        f"model_class={result.get('model_class', '')}",
        f"token_calibration_prompt_count={len(calibration_rows)}",
        f"matrix_prompt_ids={','.join(matrix_ids)}",
        f"matrix_success_prompt_count={sum(1 for row in matrix_rows if row.get('status') == 'success')}",
        f"trace_event_count={result.get('trace_event_count', '')}",
        f"trace_validation_errors={result.get('trace_validation_errors', '')}",
        f"torch_profiler_trace_exists={1 if result.get('torch_profiler_trace_exists') else 0}",
        f"torch_profiler_marker_event_count={result.get('torch_profiler_marker_event_count', '')}",
        f"torch_profiler_npu_event_candidate_count={result.get('torch_profiler_npu_event_candidate_count', '')}",
        f"error_type={result.get('error_type', '')}",
        f"error={result.get('error', '')}",
        "trace_pairing_policy=torch_profiler_trace_candidate_only; do not claim CANN device timeline pairing",
        "performance_policy=trace_matrix_smoke_only_no_perf_or_bottleneck_conclusion",
        "environment_policy=no_package_install_no_environment_repair",
    ]
    conclusion_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def fail(exc):
    update(
        status="failed",
        failure_phase=result.get("phase", ""),
        error_type=type(exc).__name__,
        error=str(exc),
    )
    error_path.write_text(traceback.format_exc(), encoding="utf-8")
    write_conclusion()

def make_event(prompt_id, request_id, **overrides):
    event = {
        "schema_version": "0.1.0",
        "event_id": "",
        "timestamp_ns": time.monotonic_ns(),
        "time_base": "host_monotonic_ns",
        "trace_id": "trace_p1_small_model_matrix_0001",
        "request_id": request_id,
        "session_id": "session_p1_small_model_matrix",
        "phase": "prefill",
        "event_type": "point",
        "resource_scope": "request_runtime_profile",
        "layer_id": None,
        "op_name": "",
        "kernel_name": None,
        "stream_id": "host:runtime",
        "device_id": "host:cpu",
        "object_type": None,
        "object_id": None,
        "source_tier": "none",
        "target_tier": "none",
        "bytes_read": 0,
        "bytes_write": 0,
        "latency_us": 0,
        "queue_wait_us": 0,
        "overlap_ratio": None,
        "policy_decision": "matrix_smoke",
        "hit_or_miss": "not_applicable",
        "stall_reason": "unknown",
        "evidence_source": "runtime_queue_trace",
        "artifact_path": "small_model_trace_matrix.jsonl",
        "prompt_id": prompt_id,
    }
    event.update(overrides)
    return event

try:
    update(phase="import")
    import torch
    import torch_npu  # noqa: F401
    from torch.profiler import ProfilerActivity, profile, record_function
    from transformers import AutoModelForCausalLM, AutoTokenizer

    update(
        phase="tokenizer_load",
        torch_version=getattr(torch, "__version__", ""),
    )
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=True,
    )
    update(
        tokenizer_class=tokenizer.__class__.__name__,
        tokenizer_model_max_length=getattr(tokenizer, "model_max_length", None),
    )

    token_calibration_path.write_text(
        "prompt_id\tprompt_path\tfull_token_count\ttruncated_token_count\tmax_input_tokens\tstatus\n",
        encoding="utf-8",
    )
    for prompt_id in calibration_ids:
        path = prompt_root / f"{prompt_id}.md"
        row = {
            "prompt_id": prompt_id,
            "prompt_path": str(path),
            "full_token_count": "",
            "truncated_token_count": "",
            "max_input_tokens": max_input_tokens,
            "status": "started",
        }
        try:
            text = path.read_text(encoding="utf-8")
            encoded = tokenizer(text, add_special_tokens=True, return_attention_mask=False)
            input_ids = encoded["input_ids"]
            full_count = len(input_ids)
            row.update(
                full_token_count=full_count,
                truncated_token_count=min(full_count, max_input_tokens),
                status="success",
            )
        except Exception as exc:
            row.update(status=f"failed:{type(exc).__name__}:{exc}")
        calibration_rows.append(row)
        with token_calibration_path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"{row['prompt_id']}\t{row['prompt_path']}\t{row['full_token_count']}\t"
                f"{row['truncated_token_count']}\t{row['max_input_tokens']}\t{row['status']}\n"
            )

    update(phase="model_load")
    if hasattr(torch, "npu"):
        torch.npu.set_device(device)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=True,
        torch_dtype="auto",
        low_cpu_mem_usage=True,
    )
    model.eval()
    model.to(device)
    if hasattr(torch, "npu"):
        torch.npu.synchronize()
    update(
        config_class=model.config.__class__.__name__,
        config_model_type=getattr(model.config, "model_type", ""),
        config_architectures=getattr(model.config, "architectures", []),
        model_class=model.__class__.__name__,
        npu_device_count=torch.npu.device_count() if hasattr(torch, "npu") else "",
    )

    update(phase="matrix_inference")
    matrix_summary_path.write_text(
        "prompt_id\tstatus\tinput_token_count\tgenerated_token_count\tgenerated_text_nonempty\t"
        "input_h2d_latency_us\tprefill_latency_us\tdecode_step_count\tdecode_total_latency_us\tfirst_decode_latency_us\n",
        encoding="utf-8",
    )
    profiler_export_error = ""
    with profile(activities=[ProfilerActivity.CPU], record_shapes=False, profile_memory=False) as prof:
        for index, prompt_id in enumerate(matrix_ids, start=1):
            request_id = f"req_trace_matrix_{index:04d}_{prompt_id}"
            prompt_path = prompt_root / f"{prompt_id}.md"
            row = {"prompt_id": prompt_id, "status": "started"}
            prompt_text = prompt_path.read_text(encoding="utf-8")

            t0 = time.perf_counter_ns()
            encoded = tokenizer(
                prompt_text,
                return_tensors="pt",
                truncation=True,
                max_length=max_input_tokens,
            )
            tokenizer_latency_us = (time.perf_counter_ns() - t0) // 1000
            input_ids_cpu = encoded["input_ids"]
            input_token_count = int(input_ids_cpu.shape[-1])
            input_tensor_bytes = int(input_ids_cpu.numel() * input_ids_cpu.element_size())

            h2d_start = time.perf_counter_ns()
            input_ids = input_ids_cpu.to(device)
            if hasattr(torch, "npu"):
                torch.npu.synchronize()
            h2d_latency_us = (time.perf_counter_ns() - h2d_start) // 1000

            events.append(make_event(
                prompt_id,
                request_id,
                event_id=f"evt_{prompt_id}_tokenize_done",
                phase="tokenize",
                op_name="tokenizer_encode",
                stream_id="host:tokenizer",
                latency_us=tokenizer_latency_us,
                policy_decision="truncate_to_trace_matrix_max_input_tokens",
            ))
            activation_id = f"activation:{request_id}:input_ids"
            events.append(make_event(
                prompt_id,
                request_id,
                event_id=f"evt_{prompt_id}_input_activation_ready",
                phase="prefill",
                event_type="lifecycle",
                resource_scope="state_object_profile",
                layer_id=0,
                op_name="input_activation_h2d_ready",
                stream_id=f"{device}:copy:unknown",
                device_id=device,
                object_type="activation",
                object_id=activation_id,
                source_tier="dram",
                target_tier="hbm",
                bytes_read=input_tensor_bytes,
                bytes_write=input_tensor_bytes,
                latency_us=h2d_latency_us,
                policy_decision="copy_prompt_inputs_to_npu",
                evidence_source="state_object_trace",
            ))
            events.append(make_event(
                prompt_id,
                request_id,
                event_id=f"evt_{prompt_id}_input_h2d_done",
                phase="prefill",
                event_type="span_end",
                resource_scope="transfer_overlap_profile",
                layer_id=0,
                op_name="input_ids_h2d_copy",
                kernel_name="torch_tensor_to_npu",
                stream_id=f"{device}:copy:unknown",
                device_id=device,
                object_type="activation",
                object_id=activation_id,
                source_tier="dram",
                target_tier="hbm",
                bytes_read=input_tensor_bytes,
                bytes_write=input_tensor_bytes,
                latency_us=h2d_latency_us,
                policy_decision="sync_copy_before_prefill",
                evidence_source="copy_overlap_trace",
            ))

            generated_ids = []
            decode_latencies = []
            with torch.inference_mode():
                prefill_start = time.perf_counter_ns()
                with record_function(f"ak_p1_trace_matrix_{prompt_id}_prefill"):
                    outputs = model(input_ids=input_ids, use_cache=True)
                    if hasattr(torch, "npu"):
                        torch.npu.synchronize()
                prefill_latency_us = (time.perf_counter_ns() - prefill_start) // 1000
                past_key_values = outputs.past_key_values
                next_token = outputs.logits[:, -1, :].argmax(dim=-1, keepdim=True)
                generated_ids.append(int(next_token.item()))

                for step in range(1, max_new_tokens):
                    decode_start = time.perf_counter_ns()
                    with record_function(f"ak_p1_trace_matrix_{prompt_id}_decode_{step}"):
                        outputs = model(
                            input_ids=next_token,
                            past_key_values=past_key_values,
                            use_cache=True,
                        )
                        if hasattr(torch, "npu"):
                            torch.npu.synchronize()
                    decode_latency_us = (time.perf_counter_ns() - decode_start) // 1000
                    decode_latencies.append(decode_latency_us)
                    past_key_values = outputs.past_key_values
                    next_token = outputs.logits[:, -1, :].argmax(dim=-1, keepdim=True)
                    generated_ids.append(int(next_token.item()))

            generated_text = tokenizer.decode(generated_ids, skip_special_tokens=False)
            (generated_dir / f"{prompt_id}.txt").write_text(generated_text, encoding="utf-8")
            (generated_dir / f"{prompt_id}_token_ids.json").write_text(
                json.dumps(generated_ids, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            decode_total_latency_us = sum(decode_latencies)
            first_decode_latency_us = decode_latencies[0] if decode_latencies else 0
            events.append(make_event(
                prompt_id,
                request_id,
                event_id=f"evt_{prompt_id}_prefill_done",
                phase="prefill",
                event_type="span_end",
                resource_scope="operator_timeline_profile",
                layer_id=0,
                op_name="model_prefill_forward",
                kernel_name="torch_profiler_candidate",
                stream_id=f"{device}:compute:unknown",
                device_id=device,
                latency_us=prefill_latency_us,
                policy_decision="manual_prefill_forward",
                evidence_source="operator_timeline",
            ))
            events.append(make_event(
                prompt_id,
                request_id,
                event_id=f"evt_{prompt_id}_decode_done",
                phase="decode",
                event_type="span_end",
                op_name="manual_greedy_decode",
                stream_id="host:runtime",
                latency_us=decode_total_latency_us,
                policy_decision="manual_decode_trace_matrix",
            ))
            events.append(make_event(
                prompt_id,
                request_id,
                event_id=f"evt_{prompt_id}_decode_op_done",
                phase="decode",
                event_type="span_end",
                resource_scope="operator_timeline_profile",
                layer_id=0,
                op_name="model_decode_forward",
                kernel_name="torch_profiler_candidate",
                stream_id=f"{device}:compute:unknown",
                device_id=device,
                latency_us=first_decode_latency_us,
                policy_decision="manual_decode_forward",
                evidence_source="operator_timeline",
            ))

            row.update(
                status="success",
                input_token_count=input_token_count,
                generated_token_count=len(generated_ids),
                generated_text_nonempty=bool(generated_text.strip()) or bool(generated_ids),
                input_h2d_latency_us=h2d_latency_us,
                prefill_latency_us=prefill_latency_us,
                decode_step_count=len(decode_latencies),
                decode_total_latency_us=decode_total_latency_us,
                first_decode_latency_us=first_decode_latency_us,
            )
            matrix_rows.append(row)
            with matrix_summary_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    f"{row['prompt_id']}\t{row['status']}\t{row['input_token_count']}\t"
                    f"{row['generated_token_count']}\t{1 if row['generated_text_nonempty'] else 0}\t"
                    f"{row['input_h2d_latency_us']}\t{row['prefill_latency_us']}\t"
                    f"{row['decode_step_count']}\t{row['decode_total_latency_us']}\t"
                    f"{row['first_decode_latency_us']}\n"
                )
            if hasattr(prof, "step"):
                prof.step()

            del outputs, past_key_values, next_token, input_ids, input_ids_cpu
            if hasattr(torch, "npu"):
                torch.npu.empty_cache()

    try:
        prof.export_chrome_trace(str(profiler_path))
    except Exception as exc:
        profiler_export_error = f"{type(exc).__name__}: {exc}"

    with trace_path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    update(phase="trace_validation")
    from tools.inference_contracts.validation import validate_trace_fixture
    validation_report = validate_trace_fixture(trace_path)
    trace_errors = list(validation_report.errors)
    trace_event_count = len(validation_report.metadata.get("events", []))
    trace_validation_path.write_text(
        "\n".join([
            f"errors={len(trace_errors)}",
            f"events={trace_event_count}",
            f"error_list={trace_errors}",
        ]) + "\n",
        encoding="utf-8",
    )

    profiler_summary = {
        "trace_exists": profiler_path.is_file(),
        "export_error": profiler_export_error,
        "trace_event_count": 0,
        "marker_event_count": 0,
        "marker_names_sample": [],
        "npu_event_candidate_count": 0,
        "npu_event_names_sample": [],
    }
    if profiler_path.is_file():
        try:
            trace_data = json.loads(profiler_path.read_text(encoding="utf-8", errors="replace"))
            trace_events = trace_data.get("traceEvents", [])
            profiler_summary["trace_event_count"] = len(trace_events)
            marker_names = [
                str(event.get("name", ""))
                for event in trace_events
                if "ak_p1_trace_matrix" in str(event.get("name", ""))
            ]
            npu_names = [
                str(event.get("name", ""))
                for event in trace_events
                if any(token in str(event.get("name", "")).lower() for token in ["npu", "acl", "aten::"])
            ]
            profiler_summary["marker_event_count"] = len(marker_names)
            profiler_summary["marker_names_sample"] = marker_names[:40]
            profiler_summary["npu_event_candidate_count"] = len(npu_names)
            profiler_summary["npu_event_names_sample"] = npu_names[:40]
        except Exception as exc:
            profiler_summary["parse_error"] = f"{type(exc).__name__}: {exc}"
    write_json(profiler_summary_path, profiler_summary)

    status = "success"
    if trace_errors:
        status = "failed_trace_validation"
    elif profiler_export_error or not profiler_summary["trace_exists"]:
        status = "partial_profiler_export_failed"
    elif profiler_summary["marker_event_count"] == 0:
        status = "partial_profiler_marker_missing"

    update(
        status=status,
        phase="complete",
        token_calibration_prompt_count=len(calibration_rows),
        matrix_success_prompt_count=sum(1 for row in matrix_rows if row.get("status") == "success"),
        trace_event_count=trace_event_count,
        trace_validation_errors=len(trace_errors),
        torch_profiler_trace_exists=profiler_summary["trace_exists"],
        torch_profiler_export_error=profiler_export_error,
        torch_profiler_marker_event_count=profiler_summary["marker_event_count"],
        torch_profiler_npu_event_candidate_count=profiler_summary["npu_event_candidate_count"],
    )
    result["token_calibration"] = calibration_rows
    result["matrix_summary"] = matrix_rows
    write_json(result_path, result)
    write_conclusion()
    if status != "success":
        sys.exit(1)
except Exception as exc:
    fail(exc)
    sys.exit(1)
PY
}

if command -v timeout >/dev/null 2>&1; then
  timeout "${AK_TRACE_MATRIX_TIMEOUT}" bash -c "$(declare -f run_matrix); run_matrix" > "${ARTIFACT_DIR}/small_model_trace_matrix.log" 2>&1
  MATRIX_STATUS=$?
else
  run_matrix > "${ARTIFACT_DIR}/small_model_trace_matrix.log" 2>&1
  MATRIX_STATUS=$?
fi
cat "${ARTIFACT_DIR}/small_model_trace_matrix.log"
echo "small_model_trace_matrix_exit_code=${MATRIX_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"
if [ "${MATRIX_STATUS}" -ne 0 ] && [ ! -f "${ARTIFACT_DIR}/small_model_trace_matrix_conclusion.txt" ]; then
  {
    echo "matrix_status=failed"
    echo "failure_phase=process_or_timeout"
    echo "error_type=process_exit"
    echo "error=small_model_trace_matrix exited ${MATRIX_STATUS}; inspect small_model_trace_matrix.log"
    echo "trace_pairing_policy=torch_profiler_trace_candidate_only; do not claim CANN device timeline pairing"
    echo "performance_policy=trace_matrix_smoke_only_no_perf_or_bottleneck_conclusion"
    echo "environment_policy=no_package_install_no_environment_repair"
  } > "${ARTIFACT_DIR}/small_model_trace_matrix_conclusion.txt"
fi

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt"
  echo
  echo "## small_model_trace_matrix_conclusion"
  cat "${ARTIFACT_DIR}/small_model_trace_matrix_conclusion.txt"
  echo
  echo "## token_calibration"
  if [ -f "${ARTIFACT_DIR}/token_calibration.tsv" ]; then
    sed -n '1,20p' "${ARTIFACT_DIR}/token_calibration.tsv"
  else
    echo "missing=token_calibration.tsv"
  fi
  echo
  echo "## small_model_trace_matrix_summary"
  if [ -f "${ARTIFACT_DIR}/small_model_trace_matrix_summary.tsv" ]; then
    cat "${ARTIFACT_DIR}/small_model_trace_matrix_summary.tsv"
  else
    echo "missing=small_model_trace_matrix_summary.tsv"
  fi
  echo
  echo "## trace_validation"
  if [ -f "${ARTIFACT_DIR}/small_model_trace_matrix_validation.txt" ]; then
    cat "${ARTIFACT_DIR}/small_model_trace_matrix_validation.txt"
  else
    echo "missing=small_model_trace_matrix_validation.txt"
  fi
  echo
  echo "## torch_profiler_summary"
  if [ -f "${ARTIFACT_DIR}/torch_profiler_summary.json" ]; then
    python -m json.tool "${ARTIFACT_DIR}/torch_profiler_summary.json" || cat "${ARTIFACT_DIR}/torch_profiler_summary.json"
  else
    echo "missing=torch_profiler_summary.json"
  fi
} | tee "${ARTIFACT_DIR}/summary.txt"

python - <<'PY' > "${ARTIFACT_DIR}/mail_body.txt"
import os
from pathlib import Path

run_id = os.environ["RUN_ID"]
artifact_dir = Path(os.environ["ARTIFACT_DIR"])
summary_path = artifact_dir / "summary.txt"
summary = summary_path.read_text(encoding="utf-8", errors="replace") if summary_path.exists() else ""

print("P1.11 remaining prompt trace matrix 受限验证已完成。")
print()
print(f"任务 ID: {run_id}")
print(f"附件: 工作记录与进度笔记本/runtime_trace_smokes/{run_id}.zip")
print()
print(summary)
print("执行边界：")
print("- 本轮使用现有 Qwen3.5-4B、transformers、torch_npu 路径")
print("- 默认只对 P003-P012 执行顺序单请求 trace")
print("- 对 P000-P012 复核 tokenizer token 数")
print("- 未安装、升级、卸载或修复任何推理框架包")
print("- 未运行 vLLM serve/benchmark、长上下文 workload、并发、burst 或 continuous batching")
print("- 未修改 models/、Public/、CANN/driver/runtime/vLLM 源码")
print("- torch_profiler_trace 仍只作为 candidate bridge，不声称 CANN device timeline pairing")
print("- 本轮不输出性能或瓶颈归因结论")
PY

(
  cd 工作记录与进度笔记本/runtime_trace_smokes
  rm -f "${RUN_ID}.zip"
  zip -qr "${RUN_ID}.zip" "${RUN_ID}"
  unzip -t "${RUN_ID}.zip"
)

python 通信模块/send_notify.py \
  -s "[AK服务器] 任务完成：small model remaining prompt trace ${RUN_ID}" \
  --body-file "${ARTIFACT_DIR}/mail_body.txt" \
  --attach "工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}.zip"
```

## 需要回传的附件

请邮件附加：

- `工作记录与进度笔记本/runtime_trace_smokes/runtime_small_model_remaining_prompt_trace_2026_0706_p1_010.zip`

zip 内至少包含：

- `run_context.txt`
- `pytest_inference_contracts.log`
- `package_inventory.tsv`
- `model_path_precheck.txt`
- `small_model_trace_matrix.log`
- `small_model_trace_matrix_result.json`
- `small_model_trace_matrix_conclusion.txt`
- `small_model_trace_matrix_error.txt`，如果发生异常
- `token_calibration.tsv`
- `small_model_trace_matrix_summary.tsv`
- `generated_texts/`
- `small_model_trace_matrix.jsonl`，如果 trace 生成成功
- `small_model_trace_matrix_validation.txt`，如果 trace 生成成功
- `torch_profiler_trace.json`，如果 profiler 导出成功
- `torch_profiler_summary.json`，如果 profiler 分析成功
- `summary.txt`

邮件主题请使用：

```text
[AK服务器] 任务完成：small model remaining prompt trace runtime_small_model_remaining_prompt_trace_2026_0706_p1_010
```

默认收件人继续使用：

```text
gwlee1995@gmail.com,yilili1023@gmail.com
```

## 验收标准

本轮算完成：

- `git pull --ff-only` 成功。
- `tests/inference_contracts` 执行并回传日志。
- `token_calibration.tsv` 明确给出 `P000-P012` 的 tokenizer token 数或失败状态。
- `small_model_trace_matrix_conclusion.txt` 明确给出 `matrix_status`。
- 成功时必须回传 `P003-P012` 的 matrix summary、P1 trace 校验结果和 profiler 摘要。
- 失败时必须回传失败阶段、错误类型和 traceback。
- 邮件正文明确说明本轮没有安装包、没有修环境、没有运行 vLLM 服务、没有做性能或瓶颈归因。

本轮不要求：

- 不要求 vLLM engine 成功启动。
- 不要求跑真实长上下文、并发、burst 或 continuous batching workload。
- 不要求并发、burst、continuous batching 或 prefix cache 实测。
- 不要求采集完整 CANN device timeline。
- 不要求输出 TTFT/TPOT benchmark 或优化建议。
