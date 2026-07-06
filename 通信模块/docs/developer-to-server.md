# 开发机 -> 服务器消息

> 本文件每次只保留当前待执行任务；旧历史信息已清空。

## 当前任务：P1.9 small model load smoke 独立验证

- 任务 ID：`runtime_small_model_load_smoke_2026_0706_p1_008`
- 证据基线：`obs_2026_0705_atlas800t_a2_006`
- P1.6 profiler bridge：`runtime_profiler_bridge_2026_0706_p1_005`
- P1.8 model symlink readiness：`runtime_model_symlink_readiness_2026_0706_p1_007`
- 当前契约入口：`工作记录与进度笔记本/p1_inference_contracts/`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_small_model_load_smoke_handoff.md`

P1.8 最新反馈邮件时间为 2026-07-06 09:39:20 CST，服务器执行 commit 为 `b5cad00`。9 个 `models/` 顶层模型入口均为 symlink，并全部解析到 `/data/node0_disk1/Public/<name>`；跟随 symlink 后读取到 50 个 metadata 文件。`Qwen3.5-4B` 排名第一，真实路径为 `/data/node0_disk1/Public/Qwen3.5-4B`，具备 `config.json`、`tokenizer_config.json`、`model.safetensors.index.json` 和约 9.32 GB 权重文件 stat。

P1.8 自动结论为 `readiness_status=blocked_no_causal_lm_candidate`，原因是分类脚本只把 `ForCausalLM` 字符串视为 causal LM，而 `Qwen3.5-4B` 的 metadata 为 `architectures=Qwen3_5ForConditionalGeneration`。这属于分类规则偏窄，不是模型路径、metadata 或包可见性的 blocker。因此本轮作为独立任务，允许实际加载 `Qwen3.5-4B` 并执行最短 tokenizer / prefill / decode smoke。

本轮和 P1.8 边界不同：本轮允许加载模型权重、实例化 tokenizer、执行极短推理；但仍不安装包、不修环境、不运行 vLLM 服务、不跑完整 P000-P012 workload、不输出性能或瓶颈归因结论。

## 服务器执行边界

请执行：

- 在服务器项目根目录 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行本文件命令。
- 通过 `git pull --ff-only` 获取开发机已提交的最新项目状态。
- 使用服务器当前 conda 环境；不创建新环境。
- 默认模型路径为 `/data/node0_disk1/Public/Qwen3.5-4B`，可用 `AK_SMALL_MODEL_PATH=/path/to/model` 覆盖。
- 默认 NPU 设备为 `npu:6`，可用 `AK_OBS_NPU_DEVICE=npu:<id>` 覆盖。
- 默认只截断 `P000` 到 256 tokens，并最多生成 4 个 token。
- 产出并邮件回传 `runtime_small_model_load_smoke_2026_0706_p1_008.zip`。

请不要执行：

- 不要安装、升级、卸载或修复 `transformers`、`vllm`、`vllm_ascend`、`mindie`、`mindspore` 或其他包。
- 不要创建新 conda 环境。
- 不要运行 vLLM engine、serve、benchmark 或完整 P000-P012 workload。
- 不要复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件。
- 不要修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码。
- 不要自动修复或重装 `ascend910b-driver`。
- 不要在服务器上修改、提交或 push 项目代码。
- 不要发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。

## 本轮必须回答的问题

- 当前服务器 conda 环境能否从本地路径加载 `Qwen3.5-4B` 的 config 与 tokenizer？
- `AutoModelForCausalLM.from_pretrained(..., local_files_only=True, trust_remote_code=True)` 能否加载该模型权重？
- 模型能否移动到指定 NPU 设备并完成一次极短 prefill 与 decode？
- 最短推理能否产生非空 token / 文本输出？
- 能否导出同一份 `torch_profiler_trace.json`，其中包含 `ak_p1_small_model_*` marker 与 NPU/op 事件候选？
- 能否生成并通过校验 `small_model_trace.jsonl`，至少覆盖 request runtime、operator timeline、state object、transfer overlap 四类 resource scope？
- 如果失败，失败点是 tokenizer/config、模型架构支持、权重加载、NPU 可用性、OOM、推理执行、profiler 导出，还是 trace 校验？

## 执行命令

在昇腾服务器项目根目录执行：

```bash
set -u

git pull --ff-only
PULL_STATUS=$?
if [ "${PULL_STATUS}" -ne 0 ]; then
  exit "${PULL_STATUS}"
fi

RUN_ID=runtime_small_model_load_smoke_2026_0706_p1_008
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
MODEL_PATH="${AK_SMALL_MODEL_PATH:-/data/node0_disk1/Public/Qwen3.5-4B}"
PROMPT_PATH="${AK_SMALL_MODEL_PROMPT_PATH:-工作记录与进度笔记本/p1_inference_contracts/prompts/P000.md}"
AK_OBS_NPU_DEVICE="${AK_OBS_NPU_DEVICE:-npu:6}"
AK_SMALL_MODEL_MAX_INPUT_TOKENS="${AK_SMALL_MODEL_MAX_INPUT_TOKENS:-256}"
AK_SMALL_MODEL_MAX_NEW_TOKENS="${AK_SMALL_MODEL_MAX_NEW_TOKENS:-4}"
AK_SMALL_MODEL_TIMEOUT="${AK_SMALL_MODEL_TIMEOUT:-45m}"
export RUN_ID ARTIFACT_DIR MODEL_PATH PROMPT_PATH AK_OBS_NPU_DEVICE AK_SMALL_MODEL_MAX_INPUT_TOKENS AK_SMALL_MODEL_MAX_NEW_TOKENS

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
  echo "PROMPT_PATH=${PROMPT_PATH}"
  echo "AK_OBS_NPU_DEVICE=${AK_OBS_NPU_DEVICE}"
  echo "AK_SMALL_MODEL_MAX_INPUT_TOKENS=${AK_SMALL_MODEL_MAX_INPUT_TOKENS}"
  echo "AK_SMALL_MODEL_MAX_NEW_TOKENS=${AK_SMALL_MODEL_MAX_NEW_TOKENS}"
  echo "AK_SMALL_MODEL_TIMEOUT=${AK_SMALL_MODEL_TIMEOUT}"
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

run_smoke() {
python - <<'PY'
import json
import os
import time
import traceback
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
model_path = Path(os.environ["MODEL_PATH"]).expanduser()
prompt_path = Path(os.environ["PROMPT_PATH"])
device = os.environ.get("AK_OBS_NPU_DEVICE", "npu:6")
max_input_tokens = int(os.environ.get("AK_SMALL_MODEL_MAX_INPUT_TOKENS", "256"))
max_new_tokens = max(2, int(os.environ.get("AK_SMALL_MODEL_MAX_NEW_TOKENS", "4")))

result_path = artifact_dir / "small_model_smoke_result.json"
error_path = artifact_dir / "small_model_smoke_error.txt"
conclusion_path = artifact_dir / "small_model_load_conclusion.txt"
trace_path = artifact_dir / "small_model_trace.jsonl"
trace_validation_path = artifact_dir / "small_model_trace_validation.txt"
profiler_path = artifact_dir / "torch_profiler_trace.json"
profiler_summary_path = artifact_dir / "torch_profiler_summary.json"
generated_text_path = artifact_dir / "generated_text.txt"
generated_ids_path = artifact_dir / "generated_token_ids.json"

result = {
    "run_id": os.environ["RUN_ID"],
    "status": "started",
    "phase": "init",
    "model_path": str(model_path),
    "prompt_path": str(prompt_path),
    "device": device,
    "max_input_tokens": max_input_tokens,
    "max_new_tokens": max_new_tokens,
}

def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

def update(**kwargs):
    result.update(kwargs)
    write_json(result_path, result)

def write_conclusion():
    lines = [
        f"small_model_smoke_status={result.get('status', '')}",
        f"failure_phase={result.get('failure_phase', '')}",
        f"model_path={result.get('model_path', '')}",
        f"device={result.get('device', '')}",
        f"config_class={result.get('config_class', '')}",
        f"tokenizer_class={result.get('tokenizer_class', '')}",
        f"model_class={result.get('model_class', '')}",
        f"input_token_count={result.get('input_token_count', '')}",
        f"generated_token_count={result.get('generated_token_count', '')}",
        f"generated_text_nonempty={1 if result.get('generated_text_nonempty') else 0}",
        f"prefill_latency_us={result.get('prefill_latency_us', '')}",
        f"decode_step_count={result.get('decode_step_count', '')}",
        f"first_decode_latency_us={result.get('first_decode_latency_us', '')}",
        f"torch_profiler_trace_exists={1 if result.get('torch_profiler_trace_exists') else 0}",
        f"torch_profiler_marker_event_count={result.get('torch_profiler_marker_event_count', '')}",
        f"torch_profiler_npu_event_candidate_count={result.get('torch_profiler_npu_event_candidate_count', '')}",
        f"small_model_trace_validation_errors={result.get('small_model_trace_validation_errors', '')}",
        f"error_type={result.get('error_type', '')}",
        f"error={result.get('error', '')}",
        "trace_pairing_policy=torch_profiler_trace_candidate_only; do not claim CANN device timeline pairing",
        "performance_policy=smoke_only_no_perf_or_bottleneck_conclusion",
        "environment_policy=no_package_install_no_environment_repair",
    ]
    conclusion_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def fail(status, exc):
    update(
        status=status,
        failure_phase=result.get("phase", ""),
        error_type=type(exc).__name__,
        error=str(exc),
    )
    error_path.write_text(traceback.format_exc(), encoding="utf-8")
    write_conclusion()

def make_event(**overrides):
    event = {
        "schema_version": "0.1.0",
        "event_id": "",
        "timestamp_ns": time.monotonic_ns(),
        "time_base": "host_monotonic_ns",
        "trace_id": "trace_p1_small_model_0001",
        "request_id": "req_small_model_0001",
        "session_id": "session_p1_small_model",
        "phase": "prefill",
        "event_type": "point",
        "resource_scope": "request_runtime_profile",
        "layer_id": None,
        "op_name": None,
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
        "policy_decision": "small_model_smoke",
        "hit_or_miss": "not_applicable",
        "stall_reason": "unknown",
        "evidence_source": "runtime_queue_trace",
        "artifact_path": "small_model_trace.jsonl",
    }
    event.update(overrides)
    return event

try:
    update(phase="import_runtime")
    import torch
    import torch_npu  # noqa: F401
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
    from tools.inference_contracts.validation import validate_trace_fixture

    if not model_path.is_dir():
        raise RuntimeError(f"model path is not a directory: {model_path}")
    if not hasattr(torch, "npu") or not torch.npu.is_available():
        raise RuntimeError("torch.npu is not available")

    update(
        phase="set_device",
        torch_version=getattr(torch, "__version__", ""),
        npu_device_count=int(torch.npu.device_count()),
    )
    torch.npu.set_device(device)

    update(phase="load_config")
    config = AutoConfig.from_pretrained(
        str(model_path),
        trust_remote_code=True,
        local_files_only=True,
    )
    update(
        config_class=type(config).__name__,
        config_model_type=getattr(config, "model_type", ""),
        config_architectures=getattr(config, "architectures", None),
    )

    update(phase="load_tokenizer")
    tokenizer = AutoTokenizer.from_pretrained(
        str(model_path),
        trust_remote_code=True,
        local_files_only=True,
    )
    update(
        tokenizer_class=type(tokenizer).__name__,
        tokenizer_model_max_length=getattr(tokenizer, "model_max_length", None),
    )

    update(phase="load_model")
    base_load_kwargs = {
        "trust_remote_code": True,
        "local_files_only": True,
    }

    model = None
    type_errors = []
    for extra_kwargs in [
        {"torch_dtype": "auto", "low_cpu_mem_usage": True},
        {"dtype": "auto", "low_cpu_mem_usage": True},
        {"torch_dtype": "auto"},
        {"dtype": "auto"},
        {},
    ]:
        try:
            model = AutoModelForCausalLM.from_pretrained(
                str(model_path),
                **base_load_kwargs,
                **extra_kwargs,
            )
            update(model_load_kwargs=extra_kwargs)
            break
        except TypeError as exc:
            type_errors.append(f"{extra_kwargs}: {exc}")
            continue
    if model is None:
        raise RuntimeError("AutoModelForCausalLM load failed with TypeError attempts: " + " | ".join(type_errors))

    update(phase="move_model_to_device", model_class=type(model).__name__)
    model.eval()
    model.to(device)
    torch.npu.synchronize()

    update(phase="tokenize_prompt")
    prompt_text = prompt_path.read_text(encoding="utf-8", errors="replace")
    tokenize_start = time.monotonic_ns()
    encoded_cpu = tokenizer(
        prompt_text,
        return_tensors="pt",
        truncation=True,
        max_length=max_input_tokens,
    )
    tokenize_end = time.monotonic_ns()
    input_token_count = int(encoded_cpu["input_ids"].shape[-1])
    input_bytes = int(sum(t.numel() * t.element_size() for t in encoded_cpu.values() if hasattr(t, "numel")))
    update(
        input_token_count=input_token_count,
        tokenizer_latency_us=(tokenize_end - tokenize_start) // 1000,
        input_tensor_bytes=input_bytes,
    )

    update(phase="copy_inputs_to_device")
    h2d_start = time.monotonic_ns()
    inputs_npu = {
        name: tensor.to(device) if hasattr(tensor, "to") else tensor
        for name, tensor in encoded_cpu.items()
    }
    torch.npu.synchronize()
    h2d_end = time.monotonic_ns()
    h2d_latency_us = (h2d_end - h2d_start) // 1000
    update(input_h2d_latency_us=h2d_latency_us)

    activities = [torch.profiler.ProfilerActivity.CPU]
    generated_ids = []
    decode_latencies_us = []
    prefill_start = prefill_end = 0

    update(phase="prefill_decode_smoke")
    with torch.inference_mode():
        with torch.profiler.profile(
            activities=activities,
            record_shapes=False,
            profile_memory=False,
            with_stack=False,
        ) as prof:
            with torch.profiler.record_function("ak_p1_small_model_prefill"):
                prefill_start = time.monotonic_ns()
                outputs = model(**inputs_npu, use_cache=True)
                torch.npu.synchronize()
                prefill_end = time.monotonic_ns()

            next_token = torch.argmax(outputs.logits[:, -1, :], dim=-1, keepdim=True)
            generated_ids.append(int(next_token.detach().cpu().item()))
            past_key_values = getattr(outputs, "past_key_values", None)
            attention_mask = inputs_npu.get("attention_mask")

            for step in range(1, max_new_tokens):
                if attention_mask is not None:
                    one_token_mask = torch.ones(
                        (attention_mask.shape[0], 1),
                        dtype=attention_mask.dtype,
                        device=device,
                    )
                    attention_mask = torch.cat([attention_mask, one_token_mask], dim=-1)
                decode_kwargs = {"input_ids": next_token, "use_cache": True}
                if past_key_values is not None:
                    decode_kwargs["past_key_values"] = past_key_values
                if attention_mask is not None:
                    decode_kwargs["attention_mask"] = attention_mask
                with torch.profiler.record_function(f"ak_p1_small_model_decode_{step}"):
                    decode_start = time.monotonic_ns()
                    decode_outputs = model(**decode_kwargs)
                    torch.npu.synchronize()
                    decode_end = time.monotonic_ns()
                decode_latencies_us.append((decode_end - decode_start) // 1000)
                next_token = torch.argmax(decode_outputs.logits[:, -1, :], dim=-1, keepdim=True)
                generated_ids.append(int(next_token.detach().cpu().item()))
                past_key_values = getattr(decode_outputs, "past_key_values", past_key_values)

        profiler_export_error = ""
        try:
            prof.export_chrome_trace(str(profiler_path))
        except Exception as exc:
            profiler_export_error = f"{type(exc).__name__}: {exc}"

    generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
    generated_text_path.write_text(generated_text, encoding="utf-8")
    write_json(generated_ids_path, {"generated_token_ids": generated_ids})

    prefill_latency_us = (prefill_end - prefill_start) // 1000
    update(
        phase="write_trace",
        generated_token_count=len(generated_ids),
        generated_text_nonempty=bool(generated_text.strip()),
        prefill_latency_us=prefill_latency_us,
        decode_step_count=len(decode_latencies_us),
        first_decode_latency_us=decode_latencies_us[0] if decode_latencies_us else "",
        decode_total_latency_us=sum(decode_latencies_us),
        torch_profiler_export_error=profiler_export_error,
        torch_profiler_trace_exists=profiler_path.is_file(),
    )

    input_object_id = "activation:req_small_model_0001:input_ids"
    events = [
        make_event(
            event_id="evt_small_model_tokenize_done",
            timestamp_ns=tokenize_end,
            phase="tokenize",
            event_type="point",
            resource_scope="request_runtime_profile",
            op_name="tokenizer_encode",
            stream_id="host:tokenizer",
            device_id="host:cpu",
            latency_us=(tokenize_end - tokenize_start) // 1000,
            policy_decision="truncate_to_smoke_max_input_tokens",
            evidence_source="runtime_queue_trace",
        ),
        make_event(
            event_id="evt_small_model_input_activation_ready",
            timestamp_ns=h2d_end,
            phase="prefill",
            event_type="lifecycle",
            resource_scope="state_object_profile",
            layer_id=0,
            op_name="input_activation_h2d_ready",
            stream_id=f"{device}:copy:unknown",
            device_id=device,
            object_type="activation",
            object_id=input_object_id,
            source_tier="dram",
            target_tier="hbm",
            bytes_read=input_bytes,
            bytes_write=input_bytes,
            latency_us=h2d_latency_us,
            policy_decision="copy_prompt_inputs_to_npu",
            evidence_source="state_object_trace",
        ),
        make_event(
            event_id="evt_small_model_input_h2d_done",
            timestamp_ns=h2d_end,
            phase="prefill",
            event_type="span_end",
            resource_scope="transfer_overlap_profile",
            layer_id=0,
            op_name="input_ids_h2d_copy",
            kernel_name="torch_tensor_to_npu",
            stream_id=f"{device}:copy:unknown",
            device_id=device,
            object_type="activation",
            object_id=input_object_id,
            source_tier="dram",
            target_tier="hbm",
            bytes_read=input_bytes,
            bytes_write=input_bytes,
            latency_us=h2d_latency_us,
            overlap_ratio=None,
            policy_decision="sync_copy_before_prefill",
            evidence_source="copy_overlap_trace",
        ),
        make_event(
            event_id="evt_small_model_prefill_done",
            timestamp_ns=prefill_end,
            phase="prefill",
            event_type="span_end",
            resource_scope="operator_timeline_profile",
            layer_id=0,
            op_name="model_prefill_forward",
            kernel_name="torch_profiler_candidate",
            stream_id=f"{device}:compute:unknown",
            device_id=device,
            bytes_read=None,
            bytes_write=None,
            latency_us=prefill_latency_us,
            policy_decision="manual_prefill_forward",
            evidence_source="operator_timeline",
        ),
        make_event(
            event_id="evt_small_model_decode_done",
            timestamp_ns=time.monotonic_ns(),
            phase="decode",
            event_type="span_end",
            resource_scope="request_runtime_profile",
            op_name="manual_greedy_decode",
            stream_id="host:runtime",
            device_id="host:cpu",
            latency_us=sum(decode_latencies_us),
            policy_decision="manual_decode_smoke",
            evidence_source="runtime_queue_trace",
        ),
        make_event(
            event_id="evt_small_model_decode_op_done",
            timestamp_ns=time.monotonic_ns(),
            phase="decode",
            event_type="span_end",
            resource_scope="operator_timeline_profile",
            layer_id=0,
            op_name="model_decode_forward",
            kernel_name="torch_profiler_candidate",
            stream_id=f"{device}:compute:unknown",
            device_id=device,
            bytes_read=None,
            bytes_write=None,
            latency_us=decode_latencies_us[0] if decode_latencies_us else 0,
            policy_decision="manual_decode_forward",
            evidence_source="operator_timeline",
        ),
    ]
    trace_path.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )

    validation_report = validate_trace_fixture(trace_path)
    trace_validation_path.write_text(
        "\n".join([
            f"errors={len(validation_report.errors)}",
            f"events={len(validation_report.metadata.get('events', []))}",
            "error_list=" + json.dumps(validation_report.errors, ensure_ascii=False),
        ]) + "\n",
        encoding="utf-8",
    )

    marker_count = ""
    npu_candidate_count = ""
    profiler_summary = {
        "trace_exists": profiler_path.is_file(),
        "export_error": profiler_export_error,
        "marker_event_count": 0,
        "npu_event_candidate_count": 0,
        "trace_event_count": 0,
    }
    if profiler_path.is_file():
        try:
            profiler_data = json.loads(profiler_path.read_text(encoding="utf-8", errors="replace"))
            trace_events = profiler_data.get("traceEvents", [])
            profiler_summary["trace_event_count"] = len(trace_events)
            marker_names = []
            npu_names = []
            for event in trace_events:
                name = str(event.get("name", ""))
                lower = name.lower()
                if "ak_p1_small_model" in lower:
                    marker_names.append(name)
                if any(token in lower for token in ["npu", "acl", "aclnn", "matmul", "attention", "aten::"]):
                    npu_names.append(name)
            profiler_summary["marker_event_count"] = len(marker_names)
            profiler_summary["npu_event_candidate_count"] = len(npu_names)
            profiler_summary["marker_names_sample"] = marker_names[:20]
            profiler_summary["npu_event_names_sample"] = npu_names[:40]
        except Exception as exc:
            profiler_summary["analysis_error"] = f"{type(exc).__name__}: {exc}"

    write_json(profiler_summary_path, profiler_summary)
    marker_count = profiler_summary.get("marker_event_count", "")
    npu_candidate_count = profiler_summary.get("npu_event_candidate_count", "")

    final_status = "success"
    if validation_report.errors:
        final_status = "partial_trace_validation_failed"
    elif not profiler_path.is_file() or profiler_export_error:
        final_status = "partial_profiler_trace_missing"
    elif not generated_ids:
        final_status = "partial_no_generated_tokens"

    update(
        status=final_status,
        phase="complete",
        small_model_trace_validation_errors=len(validation_report.errors),
        torch_profiler_marker_event_count=marker_count,
        torch_profiler_npu_event_candidate_count=npu_candidate_count,
    )
    write_conclusion()

    try:
        del model
        torch.npu.empty_cache()
    except Exception:
        pass

except Exception as exc:
    fail("blocked_" + result.get("phase", "unknown"), exc)
PY
}

if command -v timeout >/dev/null 2>&1; then
  timeout "${AK_SMALL_MODEL_TIMEOUT}" bash -c "$(declare -f run_smoke); run_smoke" > "${ARTIFACT_DIR}/small_model_load_smoke.log" 2>&1
  SMOKE_STATUS=$?
else
  run_smoke > "${ARTIFACT_DIR}/small_model_load_smoke.log" 2>&1
  SMOKE_STATUS=$?
fi
cat "${ARTIFACT_DIR}/small_model_load_smoke.log"
echo "small_model_load_smoke_exit_code=${SMOKE_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

if [ ! -f "${ARTIFACT_DIR}/small_model_load_conclusion.txt" ]; then
  {
    echo "small_model_smoke_status=blocked_process_exit_${SMOKE_STATUS}"
    echo "failure_phase=process_or_timeout"
    echo "model_path=${MODEL_PATH}"
    echo "device=${AK_OBS_NPU_DEVICE}"
    echo "error=small model smoke process did not produce a conclusion; inspect small_model_load_smoke.log"
    echo "trace_pairing_policy=torch_profiler_trace_candidate_only; do not claim CANN device timeline pairing"
    echo "performance_policy=smoke_only_no_perf_or_bottleneck_conclusion"
    echo "environment_policy=no_package_install_no_environment_repair"
  } > "${ARTIFACT_DIR}/small_model_load_conclusion.txt"
fi

python - <<'PY' > "${ARTIFACT_DIR}/summary.txt"
import os
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
for title, filename, limit in [
    ("run_context", "run_context.txt", 80),
    ("small_model_load_conclusion", "small_model_load_conclusion.txt", 80),
    ("model_path_precheck", "model_path_precheck.txt", 80),
    ("package_inventory", "package_inventory.tsv", 40),
    ("small_model_trace_validation", "small_model_trace_validation.txt", 30),
    ("generated_text", "generated_text.txt", 20),
    ("small_model_smoke_error", "small_model_smoke_error.txt", 80),
]:
    print(f"## {title}")
    path = artifact_dir / filename
    if path.is_file():
        print("\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[:limit]))
    else:
        print(f"missing={filename}")
    print()
PY

python - <<'PY' > "${ARTIFACT_DIR}/mail_body.txt"
import os
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
run_id = os.environ["RUN_ID"]
summary = (artifact_dir / "summary.txt").read_text(encoding="utf-8", errors="replace")

print("P1.9 small model load smoke 独立验证已完成。")
print()
print(f"任务 ID: {run_id}")
print(f"附件: 工作记录与进度笔记本/runtime_trace_smokes/{run_id}.zip")
print()
print(summary)
print("执行边界：")
print("- 本轮允许加载 Qwen3.5-4B、实例化 tokenizer、执行极短 prefill/decode smoke")
print("- 未安装、升级、卸载或修复任何推理框架包")
print("- 未运行 vLLM serve/benchmark 或完整 P000-P012 workload")
print("- 未修改 models/、Public/、CANN/driver/runtime/vLLM 源码")
print("- torch_profiler_trace 仍只作为 candidate bridge，不声称 CANN device timeline pairing")
print("- 本轮 smoke 不输出性能或瓶颈归因结论")
PY

(
  cd 工作记录与进度笔记本/runtime_trace_smokes
  rm -f "${RUN_ID}.zip"
  zip -qr "${RUN_ID}.zip" "${RUN_ID}"
  unzip -t "${RUN_ID}.zip"
)

python 通信模块/send_notify.py \
  -s "[AK服务器] 任务完成：small model load smoke ${RUN_ID}" \
  --body-file "${ARTIFACT_DIR}/mail_body.txt" \
  --attach "工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}.zip"
```

## 需要回传的附件

请邮件附加：

- `工作记录与进度笔记本/runtime_trace_smokes/runtime_small_model_load_smoke_2026_0706_p1_008.zip`

zip 内至少包含：

- `run_context.txt`
- `pytest_inference_contracts.log`
- `package_inventory.tsv`
- `model_path_precheck.txt`
- `small_model_load_smoke.log`
- `small_model_smoke_result.json`
- `small_model_load_conclusion.txt`
- `small_model_smoke_error.txt`，如果发生异常
- `generated_token_ids.json`，如果推理执行成功
- `generated_text.txt`，如果推理执行成功
- `small_model_trace.jsonl`，如果 trace 生成成功
- `small_model_trace_validation.txt`，如果 trace 生成成功
- `torch_profiler_trace.json`，如果 profiler 导出成功
- `torch_profiler_summary.json`，如果 profiler 分析成功
- `summary.txt`

邮件主题请使用：

```text
[AK服务器] 任务完成：small model load smoke runtime_small_model_load_smoke_2026_0706_p1_008
```

默认收件人继续使用：

```text
gwlee1995@gmail.com,yilili1023@gmail.com
```

## 验收标准

本轮算完成：

- `git pull --ff-only` 成功。
- `tests/inference_contracts` 执行并回传日志。
- `small_model_load_conclusion.txt` 明确给出 `small_model_smoke_status`。
- 成功时必须回传最短生成结果、P1 trace 校验结果和 profiler 摘要。
- 失败时必须回传失败阶段、错误类型和 traceback。
- 邮件正文明确说明本轮没有安装包、没有修环境、没有运行 vLLM 服务、没有做性能或瓶颈归因。

本轮不要求：

- 不要求 vLLM engine 成功启动。
- 不要求跑 P000-P012 全量 workload。
- 不要求采集完整 CANN device timeline。
- 不要求输出 TTFT/TPOT benchmark 或优化建议。
