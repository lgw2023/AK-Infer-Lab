# 开发机 -> 服务器消息

> 本文件每次只保留当前待执行任务；旧历史信息已清空。

## 当前任务：P1.12 long prompt tokenizer calibration

- 任务 ID：`runtime_long_prompt_calibration_2026_0706_p1_012`
- 证据基线：`obs_2026_0705_atlas800t_a2_006`
- 已完成短形态 trace：P1.10 `runtime_small_model_trace_matrix_2026_0706_p1_009`，P1.11 `runtime_small_model_remaining_prompt_trace_2026_0706_p1_010`
- 当前契约入口：`工作记录与进度笔记本/p1_inference_contracts/`
- 长 prompt manifest：`工作记录与进度笔记本/p1_inference_contracts/workload_long_manifest.yaml`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_long_prompt_calibration_handoff.md`

P1.10 + P1.11 已证明当前短形态 `P000-P012` 可以完成小模型顺序单请求 trace，但服务器 tokenizer 校准显示这些文件只有 51-185 tokens，不能代表 4K/8K/16K/32K 长上下文压力。本轮新增 `prompts_long/P000-P012.md` 和 `workload_long_manifest.yaml`，服务器只需要用现有 `Qwen3.5-4B` tokenizer 做真实 token 校准。

本轮不加载模型权重、不使用 NPU、不运行推理、不运行 vLLM、不安装包。bucket 是否偏离只记录，不在服务器上自动改 prompt。

## 服务器执行边界

请执行：

- 在服务器项目根目录 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行本文件命令。
- 通过 `git pull --ff-only` 获取开发机已提交的最新项目状态。
- 使用服务器当前 conda 环境；不创建新环境。
- 默认 tokenizer/model 目录为 `/data/node0_disk1/Public/Qwen3.5-4B`，可用 `AK_SMALL_MODEL_PATH=/path/to/model` 覆盖。
- 只读取 `workload_long_manifest.yaml` 和 `prompts_long/P000-P012.md`。
- 产出并邮件回传 `runtime_long_prompt_calibration_2026_0706_p1_012.zip`。

请不要执行：

- 不要加载 `AutoModelForCausalLM` 或任何模型权重。
- 不要使用 NPU，不要占用 `npu:6` 或其他 NPU。
- 不要运行 prefill、decode、generate、serve、benchmark、burst、continuous batching 或 prefix cache 测试。
- 不要安装、升级、卸载或修复 `transformers`、`vllm`、`vllm_ascend`、`mindie`、`mindspore` 或其他包。
- 不要创建新 conda 环境。
- 不要复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件。
- 不要修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码。
- 不要自动修复或重装 `ascend910b-driver`。
- 不要在服务器上修改、提交或 push 项目代码。
- 不要发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。

## 本轮必须回答的问题

- `prompts_long/P000-P012.md` 是否都能被服务器现有 tokenizer 成功编码？
- 每条 prompt 的真实 `Qwen3.5-4B` token 数是多少？
- 每条 prompt 相对目标 bucket 是 `within_range`、`below_range` 还是 `above_range`？
- 哪些 prompt 超过 4096 / 8192 / 16384 / 32768 token 截断阈值？
- 如果失败，失败点是 `git pull`、pytest、manifest、prompt 文件、tokenizer 加载，还是 tokenizer 编码？

## 执行命令

在昇腾服务器项目根目录执行：

```bash
set -u

git pull --ff-only
PULL_STATUS=$?
if [ "${PULL_STATUS}" -ne 0 ]; then
  exit "${PULL_STATUS}"
fi

RUN_ID=runtime_long_prompt_calibration_2026_0706_p1_012
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
MODEL_PATH="${AK_SMALL_MODEL_PATH:-/data/node0_disk1/Public/Qwen3.5-4B}"
CONTRACT_DIR="工作记录与进度笔记本/p1_inference_contracts"
LONG_MANIFEST="${CONTRACT_DIR}/workload_long_manifest.yaml"
export RUN_ID ARTIFACT_DIR MODEL_PATH CONTRACT_DIR LONG_MANIFEST

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
  echo "CONTRACT_DIR=${CONTRACT_DIR}"
  echo "LONG_MANIFEST=${LONG_MANIFEST}"
  echo "task_policy=tokenizer_only_no_model_weights_no_npu_no_vllm_no_package_install"
} | tee "${ARTIFACT_DIR}/run_context.txt"

python -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest_inference_contracts.log" 2>&1
PYTEST_STATUS=$?
cat "${ARTIFACT_DIR}/pytest_inference_contracts.log"
echo "pytest_exit_code=${PYTEST_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

python - <<'PY' > "${ARTIFACT_DIR}/package_inventory.tsv" 2>&1
import importlib.metadata as metadata
import importlib.util

probes = [
    ("transformers", "transformers", ("transformers",)),
    ("tokenizers", "tokenizers", ("tokenizers",)),
    ("sentencepiece", "sentencepiece", ("sentencepiece",)),
    ("safetensors", "safetensors", ("safetensors",)),
    ("torch", "torch", ("torch",)),
    ("torch_npu", "torch_npu", ("torch-npu", "torch_npu")),
    ("vllm", "vllm", ("vllm",)),
    ("vllm_ascend", "vllm_ascend", ("vllm-ascend", "vllm_ascend")),
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
for name in ["config.json", "tokenizer_config.json", "tokenizer.json", "generation_config.json"]:
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

cp "${LONG_MANIFEST}" "${ARTIFACT_DIR}/workload_long_manifest.snapshot.yaml"

python - <<'PY' > "${ARTIFACT_DIR}/long_prompt_token_calibration.log" 2>&1
import json
import os
import sys
import traceback
from pathlib import Path

import yaml
from transformers import AutoTokenizer

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
model_path = Path(os.environ["MODEL_PATH"]).expanduser()
contract_dir = Path(os.environ["CONTRACT_DIR"])
manifest_path = Path(os.environ["LONG_MANIFEST"])

tsv_path = artifact_dir / "long_prompt_token_calibration.tsv"
result_path = artifact_dir / "long_prompt_token_calibration_result.json"
conclusion_path = artifact_dir / "long_prompt_calibration_conclusion.txt"
error_path = artifact_dir / "long_prompt_token_calibration_error.txt"

bucket_ranges = {
    "512": (256, 900),
    "1K": (700, 1500),
    "4K": (2800, 5200),
    "8K": (6000, 10000),
    "16K": (12000, 20000),
    "32K": (24000, 40000),
}
truncate_limits = [4096, 8192, 16384, 32768]

def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def bucket_status(bucket, token_count):
    low, high = bucket_ranges.get(str(bucket), (0, 10**18))
    if token_count < low:
        return "below_range"
    if token_count > high:
        return "above_range"
    return "within_range"

result = {
    "run_id": os.environ["RUN_ID"],
    "model_path": str(model_path),
    "manifest_path": str(manifest_path),
    "phase": "start",
    "status": "started",
    "policy": "tokenizer_only_no_model_weights_no_npu_no_vllm_no_package_install",
}

try:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    prompts = manifest.get("prompts", []) if isinstance(manifest, dict) else []
    if not isinstance(prompts, list) or not prompts:
        raise ValueError("workload_long_manifest.yaml prompts must be a non-empty list")

    result["phase"] = "tokenizer_load"
    write_json(result_path, result)
    tokenizer = AutoTokenizer.from_pretrained(
        str(model_path),
        trust_remote_code=True,
        local_files_only=True,
    )
    tokenizer_class = type(tokenizer).__name__
    tokenizer_model_max_length = getattr(tokenizer, "model_max_length", None)

    rows = []
    failures = []
    tsv_header = [
        "prompt_id",
        "context_len_bucket",
        "estimated_prompt_tokens",
        "materialized_char_count_manifest",
        "char_count",
        "byte_count",
        "full_token_count",
        "bucket_status",
        "truncated_4096",
        "truncated_8192",
        "truncated_16384",
        "truncated_32768",
        "status",
        "error_type",
        "error",
    ]
    tsv_path.write_text("\t".join(tsv_header) + "\n", encoding="utf-8")

    for prompt in prompts:
        prompt_id = str(prompt.get("prompt_id", ""))
        prompt_path = contract_dir / str(prompt.get("prompt_path", ""))
        row = {
            "prompt_id": prompt_id,
            "context_len_bucket": str(prompt.get("context_len_bucket", "")),
            "estimated_prompt_tokens": int(prompt.get("estimated_prompt_tokens", 0)),
            "materialized_char_count_manifest": int(prompt.get("materialized_char_count", 0)),
            "char_count": 0,
            "byte_count": 0,
            "full_token_count": 0,
            "bucket_status": "not_measured",
            "status": "started",
            "error_type": "",
            "error": "",
        }
        try:
            text = prompt_path.read_text(encoding="utf-8")
            row["char_count"] = len(text)
            row["byte_count"] = len(text.encode("utf-8"))
            token_ids = tokenizer.encode(text, add_special_tokens=False)
            token_count = len(token_ids)
            row["full_token_count"] = token_count
            row["bucket_status"] = bucket_status(row["context_len_bucket"], token_count)
            for limit in truncate_limits:
                row[f"truncated_{limit}"] = min(token_count, limit)
            row["status"] = "success"
        except Exception as exc:
            row["status"] = "failed"
            row["error_type"] = type(exc).__name__
            row["error"] = str(exc)
            failures.append(row)
        rows.append(row)
        with tsv_path.open("a", encoding="utf-8") as handle:
            handle.write("\t".join(str(row.get(name, "")) for name in tsv_header) + "\n")

    bucket_miss_count = sum(1 for row in rows if row["status"] == "success" and row["bucket_status"] != "within_range")
    status = "success" if not failures else "failed"
    full_token_counts = [row["full_token_count"] for row in rows if row["status"] == "success"]
    result.update(
        phase="complete",
        status=status,
        tokenizer_class=tokenizer_class,
        tokenizer_model_max_length=tokenizer_model_max_length,
        prompt_count=len(rows),
        success_prompt_count=sum(1 for row in rows if row["status"] == "success"),
        failed_prompt_count=len(failures),
        bucket_miss_count=bucket_miss_count,
        max_full_token_count=max(full_token_counts) if full_token_counts else 0,
        over_4096_count=sum(1 for row in rows if row["full_token_count"] > 4096),
        over_8192_count=sum(1 for row in rows if row["full_token_count"] > 8192),
        over_16384_count=sum(1 for row in rows if row["full_token_count"] > 16384),
        over_32768_count=sum(1 for row in rows if row["full_token_count"] > 32768),
        rows=rows,
    )
    write_json(result_path, result)
    conclusion_lines = [
        f"calibration_status={status}",
        f"failure_phase=",
        f"model_path={model_path}",
        f"tokenizer_class={tokenizer_class}",
        f"prompt_count={len(rows)}",
        f"success_prompt_count={result['success_prompt_count']}",
        f"failed_prompt_count={result['failed_prompt_count']}",
        f"bucket_miss_count={bucket_miss_count}",
        f"max_full_token_count={result['max_full_token_count']}",
        f"over_4096_count={result['over_4096_count']}",
        f"over_8192_count={result['over_8192_count']}",
        f"over_16384_count={result['over_16384_count']}",
        f"over_32768_count={result['over_32768_count']}",
        "execution_policy=tokenizer_only_no_model_weights_no_npu_no_vllm_no_package_install",
        "performance_policy=token_calibration_only_no_perf_or_bottleneck_conclusion",
    ]
    conclusion_path.write_text("\n".join(conclusion_lines) + "\n", encoding="utf-8")
    print("\n".join(conclusion_lines))
    if failures:
        sys.exit(1)
except Exception as exc:
    result.update(
        phase=result.get("phase", "unknown"),
        status="failed",
        error_type=type(exc).__name__,
        error=str(exc),
    )
    write_json(result_path, result)
    error_path.write_text(traceback.format_exc(), encoding="utf-8")
    conclusion_path.write_text(
        "\n".join([
            "calibration_status=failed",
            f"failure_phase={result.get('phase', 'unknown')}",
            f"model_path={model_path}",
            f"error_type={type(exc).__name__}",
            f"error={exc}",
            "execution_policy=tokenizer_only_no_model_weights_no_npu_no_vllm_no_package_install",
            "performance_policy=token_calibration_only_no_perf_or_bottleneck_conclusion",
        ]) + "\n",
        encoding="utf-8",
    )
    print(traceback.format_exc())
    sys.exit(1)
PY
CALIBRATION_STATUS=$?
cat "${ARTIFACT_DIR}/long_prompt_token_calibration.log"
echo "long_prompt_token_calibration_exit_code=${CALIBRATION_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt"
  echo
  echo "## long_prompt_calibration_conclusion"
  if [ -f "${ARTIFACT_DIR}/long_prompt_calibration_conclusion.txt" ]; then
    cat "${ARTIFACT_DIR}/long_prompt_calibration_conclusion.txt"
  else
    echo "missing=long_prompt_calibration_conclusion.txt"
  fi
  echo
  echo "## long_prompt_token_calibration"
  if [ -f "${ARTIFACT_DIR}/long_prompt_token_calibration.tsv" ]; then
    cat "${ARTIFACT_DIR}/long_prompt_token_calibration.tsv"
  else
    echo "missing=long_prompt_token_calibration.tsv"
  fi
  echo
  echo "## package_inventory"
  cat "${ARTIFACT_DIR}/package_inventory.tsv"
  echo
  echo "## model_path_precheck"
  cat "${ARTIFACT_DIR}/model_path_precheck.txt"
} | tee "${ARTIFACT_DIR}/summary.txt"

python - <<'PY' > "${ARTIFACT_DIR}/mail_body.txt"
import os
from pathlib import Path

run_id = os.environ["RUN_ID"]
artifact_dir = Path(os.environ["ARTIFACT_DIR"])
summary = (artifact_dir / "summary.txt").read_text(encoding="utf-8", errors="replace")

print("P1.12 long prompt tokenizer calibration 已完成。")
print()
print(f"任务 ID: {run_id}")
print(f"附件: 工作记录与进度笔记本/runtime_trace_smokes/{run_id}.zip")
print()
print(summary)
print("执行边界：")
print("- 本轮只加载 Qwen3.5-4B tokenizer")
print("- 未加载 AutoModelForCausalLM 或任何模型权重")
print("- 未使用 NPU，未运行 prefill/decode/generate")
print("- 未运行 vLLM serve/benchmark、并发、burst、continuous batching 或 prefix cache 测试")
print("- 未安装、升级、卸载或修复任何包")
print("- 未修改 models/、Public/、CANN/driver/runtime/vLLM 源码")
print("- 本轮不输出性能或瓶颈归因结论")
PY

(
  cd 工作记录与进度笔记本/runtime_trace_smokes
  rm -f "${RUN_ID}.zip"
  zip -qr "${RUN_ID}.zip" "${RUN_ID}"
  unzip -t "${RUN_ID}.zip"
)

python 通信模块/send_notify.py \
  -s "[AK服务器] 任务完成：long prompt calibration ${RUN_ID}" \
  --body-file "${ARTIFACT_DIR}/mail_body.txt" \
  --attach "工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}.zip"
```

## 需要回传的附件

请邮件附加：

- `工作记录与进度笔记本/runtime_trace_smokes/runtime_long_prompt_calibration_2026_0706_p1_012.zip`

zip 内至少包含：

- `run_context.txt`
- `pytest_inference_contracts.log`
- `package_inventory.tsv`
- `model_path_precheck.txt`
- `workload_long_manifest.snapshot.yaml`
- `long_prompt_token_calibration.log`
- `long_prompt_token_calibration.tsv`
- `long_prompt_token_calibration_result.json`
- `long_prompt_calibration_conclusion.txt`
- `long_prompt_token_calibration_error.txt`，如果发生异常
- `summary.txt`
- `mail_body.txt`

邮件主题请使用：

```text
[AK服务器] 任务完成：long prompt calibration runtime_long_prompt_calibration_2026_0706_p1_012
```

默认收件人继续使用：

```text
gwlee1995@gmail.com,yilili1023@gmail.com
```

## 验收标准

本轮算完成：

- `git pull --ff-only` 成功。
- `tests/inference_contracts` 执行并回传日志。
- `long_prompt_token_calibration.tsv` 明确给出 `P000-P012` 的 tokenizer token 数或失败状态。
- `long_prompt_calibration_conclusion.txt` 明确给出 `calibration_status`、成功 prompt 数、bucket miss 数和截断阈值统计。
- 邮件正文明确说明本轮没有加载模型权重、没有使用 NPU、没有安装包、没有运行 vLLM、没有做性能或瓶颈归因。

本轮不要求：

- 不要求模型推理成功。
- 不要求 4K/8K/16K/32K 长 prompt smoke。
- 不要求并发、burst、continuous batching 或 prefix cache 实测。
- 不要求采集 profiler trace。
- 不要求输出 TTFT/TPOT benchmark 或优化建议。
