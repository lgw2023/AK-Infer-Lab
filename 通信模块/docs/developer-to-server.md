# 开发机 -> 服务器消息

> 本文件每次只保留当前待执行任务；旧历史信息已清空。

## 当前任务：P1.7 small model readiness 只读盘点

- 任务 ID：`runtime_small_model_readiness_2026_0706_p1_006`
- 证据基线：`obs_2026_0705_atlas800t_a2_006`
- P1.2 预检：`runtime_trace_smoke_2026_0705_p1_001`
- P1.3 hook 侦查：`runtime_hook_discovery_2026_0705_p1_002`
- P1.4 hook 原型：`runtime_hook_proto_2026_0705_p1_003`
- P1.5 marker pairing：`runtime_marker_pairing_2026_0705_p1_004`
- P1.6 profiler bridge：`runtime_profiler_bridge_2026_0706_p1_005`
- 当前契约入口：`工作记录与进度笔记本/p1_inference_contracts/`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_small_model_readiness_handoff.md`

P1.6 最新反馈邮件时间为 2026-07-06 00:35:35 CST，服务器执行 commit 为 `e7dc6ae`，`tests/inference_contracts` 为 `11 passed in 0.19s`，`runtime_profiler_bridge_trace.jsonl` 校验 `errors=0`、`events=4`。`torch.profiler.ProfilerActivity` 不包含 `NPU`，本轮实际只启用 `activities=CPU`；但导出的 `torch_profiler_trace.json` 中同时出现 3 个自定义 `record_function` marker 和 7 个 NPU 相关 op 候选，且两类事件均带 Chrome trace `ts` / `dur`。

P1.6 的关键结论是：`torch_profiler_trace` 可作为后续小模型阶段的候选 marker/op bridge，但它仍不是 `msprof` / CANN 独立 device timeline pairing 证据。进入小模型 trace smoke 前，需要先单独确认服务器 `models/` 目录里有哪些候选模型、metadata 是否完整、当前环境是否已有可用加载入口。

本轮目标不是小模型加载，不运行推理，不安装或修复任何包。本轮只做只读 readiness 盘点，输出是否可以另起独立小模型加载 smoke 的结论。

## 服务器执行边界

请执行：

- 在服务器项目根目录 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行本文件命令。
- 通过 `git pull --ff-only` 获取开发机已提交的最新项目状态。
- 使用服务器当前 conda 环境；不创建新环境。
- 默认扫描项目根目录下 `models/`；如模型目录实际不同，可通过 `AK_MODELS_DIR=/path/to/models` 覆盖，并在邮件中说明。
- 产出并邮件回传 `runtime_small_model_readiness_2026_0706_p1_006.zip`。

请不要执行：

- 不要加载模型权重，不要实例化模型，不要实例化 tokenizer。
- 不要运行真实模型推理、小模型 smoke、vLLM engine serve/generate 或 P000-P012 workload。
- 不要读取权重文件内容，不要复制、移动、删除或改名 `models/` 下任何文件。
- 不要安装、升级、卸载或修复 `transformers`、`vllm`、`vllm_ascend`、`mindie`、`mindspore` 或其他推理框架包。
- 不要修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码。
- 不要自动修复或重装 `ascend910b-driver`。
- 不要在服务器上修改、提交或 push 项目代码。
- 不要发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。

## 本轮必须回答的问题

- 服务器项目根目录下 `models/` 是否存在，是否有可读候选模型？
- 候选目录是否包含 `config.json`、`tokenizer_config.json`、`generation_config.json`、`*.safetensors.index.json` 等 metadata？
- 根据目录名和 metadata，是否存在适合 P4 小模型 smoke 的小尺寸候选？
- 当前 conda 环境中 `torch`、`torch_npu`、`transformers`、`tokenizers`、`sentencepiece`、`accelerate`、`safetensors`、`vllm`、`vllm_ascend`、`mindie`、`mindspore` 是否可见？
- 是否可以不修环境、不装包、不搬模型，另起独立小模型加载 smoke？
- 如果不能，阻塞原因是缺模型、缺 tokenizer、缺框架、环境需修复，还是需要人工选择模型？

## 执行命令

在昇腾服务器项目根目录执行：

```bash
set -u

git pull --ff-only
PULL_STATUS=$?
if [ "${PULL_STATUS}" -ne 0 ]; then
  exit "${PULL_STATUS}"
fi

RUN_ID=runtime_small_model_readiness_2026_0706_p1_006
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
MODELS_DIR="${AK_MODELS_DIR:-models}"
export RUN_ID ARTIFACT_DIR MODELS_DIR

rm -rf "${ARTIFACT_DIR}"
mkdir -p "${ARTIFACT_DIR}"

{
  echo "run_id=${RUN_ID}"
  echo "commit=$(git rev-parse --short HEAD)"
  echo "timestamp=$(date -Is)"
  echo "hostname=$(hostname)"
  echo "python=$(command -v python || true)"
  echo "cwd=$(pwd)"
  echo "MODELS_DIR=${MODELS_DIR}"
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
    ("numpy", "numpy", ("numpy",)),
    ("pydantic", "pydantic", ("pydantic",)),
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

python - <<'PY' > "${ARTIFACT_DIR}/model_inventory.log" 2>&1
import json
import os
import re
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
models_dir = Path(os.environ["MODELS_DIR"]).expanduser()
if not models_dir.is_absolute():
    models_dir = (Path.cwd() / models_dir).resolve()

max_depth = 5
max_json_bytes = 2_000_000
metadata_names = {
    "config.json",
    "tokenizer_config.json",
    "generation_config.json",
    "preprocessor_config.json",
    "processor_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
}
weight_suffixes = {".safetensors", ".bin", ".pt", ".pth", ".gguf"}

summary = {
    "models_dir": str(models_dir),
    "models_dir_exists": models_dir.exists(),
    "models_dir_is_dir": models_dir.is_dir(),
    "max_depth": max_depth,
    "note": "metadata-only scan; no model/tokenizer load and no weight content read",
}

file_rows = ["kind\trel_path\tbytes\tmetadata_kind"]
metadata_rows = []
listing_lines = []
candidates = {}

def rel_text(path):
    try:
        return str(path.relative_to(models_dir))
    except ValueError:
        return str(path)

def safe_stat(path):
    try:
        return path.stat()
    except OSError:
        return None

def json_load_small(path):
    stat = safe_stat(path)
    if stat is None or stat.st_size > max_json_bytes:
        return None, "too_large_or_unreadable"
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace")), ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"

def candidate_for(root):
    root = Path(root)
    rec = candidates.setdefault(str(root), {
        "path": str(root),
        "rel_path": rel_text(root),
        "has_config": False,
        "has_tokenizer_metadata": False,
        "has_generation_config": False,
        "has_safetensors_index": False,
        "metadata_files": [],
        "weight_file_count": 0,
        "weight_bytes_stat_only": 0,
        "model_type": "",
        "architectures": [],
        "torch_dtype": "",
        "max_position_embeddings": "",
        "num_hidden_layers": "",
        "hidden_size": "",
        "num_attention_heads": "",
        "num_key_value_heads": "",
        "num_experts": "",
        "tokenizer_class": "",
        "model_max_length": "",
    })
    return rec

def record_metadata(path, kind, data, error):
    rel = rel_text(path)
    rec = candidate_for(path.parent)
    rec["metadata_files"].append(rel)
    if kind == "config":
        rec["has_config"] = True
    if kind == "tokenizer":
        rec["has_tokenizer_metadata"] = True
    if kind == "generation":
        rec["has_generation_config"] = True
    if kind == "safetensors_index":
        rec["has_safetensors_index"] = True

    selected = {}
    if isinstance(data, dict):
        selected = {
            key: data.get(key)
            for key in [
                "model_type",
                "architectures",
                "torch_dtype",
                "vocab_size",
                "max_position_embeddings",
                "rope_scaling",
                "num_hidden_layers",
                "num_attention_heads",
                "num_key_value_heads",
                "hidden_size",
                "intermediate_size",
                "num_experts",
                "moe_intermediate_size",
                "tokenizer_class",
                "model_max_length",
                "total_size",
            ]
            if key in data
        }
        if kind == "config":
            rec["model_type"] = str(data.get("model_type", ""))
            rec["architectures"] = data.get("architectures", []) or []
            rec["torch_dtype"] = str(data.get("torch_dtype", ""))
            rec["max_position_embeddings"] = str(data.get("max_position_embeddings", ""))
            rec["num_hidden_layers"] = str(data.get("num_hidden_layers", ""))
            rec["hidden_size"] = str(data.get("hidden_size", ""))
            rec["num_attention_heads"] = str(data.get("num_attention_heads", ""))
            rec["num_key_value_heads"] = str(data.get("num_key_value_heads", ""))
            rec["num_experts"] = str(data.get("num_experts", ""))
        if kind == "tokenizer":
            rec["tokenizer_class"] = str(data.get("tokenizer_class", ""))
            rec["model_max_length"] = str(data.get("model_max_length", ""))

    metadata_rows.append(json.dumps({
        "path": rel,
        "kind": kind,
        "bytes": safe_stat(path).st_size if safe_stat(path) else None,
        "parse_error": error,
        "selected": selected,
    }, ensure_ascii=False, sort_keys=True))

def metadata_kind_for(name):
    lower = name.lower()
    if lower == "config.json":
        return "config"
    if lower in {"tokenizer_config.json", "tokenizer.json", "special_tokens_map.json", "processor_config.json", "preprocessor_config.json"}:
        return "tokenizer"
    if lower == "generation_config.json":
        return "generation"
    if lower.endswith(".safetensors.index.json"):
        return "safetensors_index"
    return ""

def score_candidate(rec):
    text = " ".join([
        rec["rel_path"].lower(),
        rec.get("model_type", "").lower(),
        " ".join(str(x).lower() for x in rec.get("architectures", [])),
    ])
    score = 0
    reasons = []
    if rec["has_config"]:
        score += 4
        reasons.append("has_config")
    if rec["has_tokenizer_metadata"]:
        score += 3
        reasons.append("has_tokenizer_metadata")
    if rec["has_safetensors_index"] or rec["weight_file_count"] > 0:
        score += 2
        reasons.append("has_weight_manifest_or_files")
    if any(token in text for token in ["causallm", "forcausallm", "qwen", "llama", "chatglm", "baichuan", "internlm", "deepseek"]):
        score += 2
        reasons.append("likely_llm")
    if re.search(r"(^|[^0-9])(0\.5b|1\.5b|1b|2b|3b|tiny|small)([^0-9]|$)", text):
        score += 3
        reasons.append("small_name_hint")
    if re.search(r"(^|[^0-9])(30b|32b|70b|72b|110b)([^0-9]|$)", text):
        score -= 4
        reasons.append("large_name_hint")
    return score, ",".join(reasons)

if not models_dir.exists() or not models_dir.is_dir():
    summary.update({
        "top_level_entry_count": 0,
        "metadata_file_count": 0,
        "model_candidate_count": 0,
        "top_candidate": "",
    })
else:
    try:
        top_entries = sorted(models_dir.iterdir(), key=lambda p: p.name)
    except OSError:
        top_entries = []
    listing_lines.append(f"# models_dir={models_dir}")
    listing_lines.append("# Top-level entries")
    for entry in top_entries[:200]:
        stat = safe_stat(entry)
        size = stat.st_size if stat else ""
        kind = "dir" if entry.is_dir() else "file"
        listing_lines.append(f"{kind}\t{entry.name}\t{size}")

    for root, dirs, files in os.walk(models_dir):
        root_path = Path(root)
        try:
            depth = len(root_path.relative_to(models_dir).parts)
        except ValueError:
            depth = 0
        dirs[:] = sorted([name for name in dirs if not name.startswith(".")])
        files = sorted(files)
        if depth >= max_depth:
            dirs[:] = []
        for name in files:
            path = root_path / name
            rel = rel_text(path)
            stat = safe_stat(path)
            size = stat.st_size if stat else 0
            lower = name.lower()
            kind = metadata_kind_for(name)
            suffix = path.suffix.lower()
            if len(file_rows) <= 10000:
                file_rows.append("\t".join([
                    "file",
                    rel,
                    str(size),
                    kind,
                ]))
            if kind:
                data, error = json_load_small(path)
                record_metadata(path, kind, data, error)
            if suffix in weight_suffixes:
                rec = candidate_for(path.parent)
                rec["weight_file_count"] += 1
                rec["weight_bytes_stat_only"] += size

rank_rows = ["rank\tscore\treasons\trel_path\tmodel_type\tarchitectures\ttorch_dtype\tmax_position_embeddings\tnum_hidden_layers\thidden_size\tnum_attention_heads\tnum_key_value_heads\tnum_experts\ttokenizer_class\tmodel_max_length\tweight_file_count\tweight_bytes_stat_only\tmetadata_files"]
ranked = []
for rec in candidates.values():
    score, reasons = score_candidate(rec)
    ranked.append((score, reasons, rec))
ranked.sort(key=lambda item: (-item[0], item[2]["rel_path"]))
for index, (score, reasons, rec) in enumerate(ranked[:200], start=1):
    rank_rows.append("\t".join([
        str(index),
        str(score),
        reasons,
        rec["rel_path"],
        rec["model_type"],
        ",".join(str(x) for x in rec["architectures"]),
        rec["torch_dtype"],
        rec["max_position_embeddings"],
        rec["num_hidden_layers"],
        rec["hidden_size"],
        rec["num_attention_heads"],
        rec["num_key_value_heads"],
        rec["num_experts"],
        rec["tokenizer_class"],
        rec["model_max_length"],
        str(rec["weight_file_count"]),
        str(rec["weight_bytes_stat_only"]),
        ",".join(rec["metadata_files"][:20]),
    ]))

summary.update({
    "top_level_entry_count": len(list(top_entries)) if models_dir.exists() and models_dir.is_dir() else 0,
    "metadata_file_count": len(metadata_rows),
    "model_candidate_count": len(candidates),
    "top_candidate": ranked[0][2]["rel_path"] if ranked else "",
    "top_candidate_score": ranked[0][0] if ranked else 0,
    "top_candidate_reasons": ranked[0][1] if ranked else "",
})

(artifact_dir / "models_dir_listing.txt").write_text("\n".join(listing_lines) + "\n", encoding="utf-8")
(artifact_dir / "model_file_inventory.tsv").write_text("\n".join(file_rows) + "\n", encoding="utf-8")
(artifact_dir / "model_metadata_inventory.jsonl").write_text("\n".join(metadata_rows) + ("\n" if metadata_rows else ""), encoding="utf-8")
(artifact_dir / "model_candidate_ranking.tsv").write_text("\n".join(rank_rows) + "\n", encoding="utf-8")
(artifact_dir / "model_inventory_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
PY
MODEL_STATUS=$?
cat "${ARTIFACT_DIR}/model_inventory.log"
echo "model_inventory_exit_code=${MODEL_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

python - <<'PY' > "${ARTIFACT_DIR}/readiness_conclusion.txt"
import json
import os
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
summary_path = artifact_dir / "model_inventory_summary.json"
package_path = artifact_dir / "package_inventory.tsv"

summary = {}
if summary_path.is_file():
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

packages = {}
if package_path.is_file():
    lines = package_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) >= 4:
            packages[parts[0]] = {
                "module": parts[1],
                "version": parts[2],
                "spec_found": parts[3] == "1",
            }

def found(name):
    return packages.get(name, {}).get("spec_found", False)

models_exists = bool(summary.get("models_dir_exists") and summary.get("models_dir_is_dir"))
candidate_count = int(summary.get("model_candidate_count") or 0)
metadata_count = int(summary.get("metadata_file_count") or 0)
top_candidate = str(summary.get("top_candidate") or "")

has_torch_npu = found("torch") and found("torch_npu")
has_transformers_entry = found("transformers") and found("safetensors")
has_vllm_entry = found("vllm") or found("vllm_ascend")

if not models_exists:
    readiness = "blocked_models_dir_missing"
elif candidate_count <= 0 or metadata_count <= 0:
    readiness = "blocked_no_readable_model_metadata"
elif not has_torch_npu:
    readiness = "blocked_torch_npu_not_visible"
elif not (has_transformers_entry or has_vllm_entry):
    readiness = "blocked_no_loading_framework_entry_visible"
else:
    readiness = "ready_for_separate_small_model_load_smoke_candidate_only"

print(f"models_dir={summary.get('models_dir', '')}")
print(f"models_dir_exists={1 if models_exists else 0}")
print(f"model_candidate_count={candidate_count}")
print(f"metadata_file_count={metadata_count}")
print(f"top_candidate={top_candidate}")
print(f"top_candidate_score={summary.get('top_candidate_score', '')}")
print(f"top_candidate_reasons={summary.get('top_candidate_reasons', '')}")
print(f"torch_npu_visible={1 if has_torch_npu else 0}")
print(f"transformers_entry_visible={1 if has_transformers_entry else 0}")
print(f"vllm_entry_visible={1 if has_vllm_entry else 0}")
print(f"readiness_status={readiness}")
print("next_step_policy=do_not_load_model_in_this_task; design a separate load smoke only if readiness_status is ready")
print("trace_pairing_policy=torch_profiler_trace_candidate_only; do not claim CANN device timeline pairing")
PY
CONCLUSION_STATUS=$?
cat "${ARTIFACT_DIR}/readiness_conclusion.txt"
echo "readiness_conclusion_exit_code=${CONCLUSION_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

python - <<'PY' > "${ARTIFACT_DIR}/summary.txt"
import os
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
run_context = (artifact_dir / "run_context.txt").read_text(encoding="utf-8", errors="replace")
conclusion = (artifact_dir / "readiness_conclusion.txt").read_text(encoding="utf-8", errors="replace")
packages = (artifact_dir / "package_inventory.tsv").read_text(encoding="utf-8", errors="replace")
ranking = (artifact_dir / "model_candidate_ranking.tsv").read_text(encoding="utf-8", errors="replace")

print("## run_context")
print(run_context.strip())
print()
print("## readiness_conclusion")
print(conclusion.strip())
print()
print("## package_inventory")
print(packages.strip())
print()
print("## top_model_candidates")
print("\n".join(ranking.splitlines()[:21]))
PY

python - <<'PY' > "${ARTIFACT_DIR}/mail_body.txt"
import os
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
run_id = os.environ["RUN_ID"]
summary = (artifact_dir / "summary.txt").read_text(encoding="utf-8", errors="replace")

print(f"P1.7 small model readiness 只读盘点已完成。")
print()
print(f"任务 ID: {run_id}")
print(f"附件: 工作记录与进度笔记本/runtime_trace_smokes/{run_id}.zip")
print()
print(summary)
print()
print("执行边界：")
print("- 未加载模型权重")
print("- 未实例化 tokenizer")
print("- 未运行 generate/serve/小模型 smoke/P000-P012 workload")
print("- 未安装、升级、卸载或修复任何推理框架包")
print("- 未修改 models/、CANN/driver/runtime/vLLM 源码")
PY

(
  cd 工作记录与进度笔记本/runtime_trace_smokes
  rm -f "${RUN_ID}.zip"
  zip -qr "${RUN_ID}.zip" "${RUN_ID}"
  unzip -t "${RUN_ID}.zip"
)

python 通信模块/send_notify.py \
  -s "[AK服务器] 任务完成：small model readiness ${RUN_ID}" \
  --body-file "${ARTIFACT_DIR}/mail_body.txt" \
  --attach "工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}.zip"
```

## 需要回传的附件

请邮件附加：

- `工作记录与进度笔记本/runtime_trace_smokes/runtime_small_model_readiness_2026_0706_p1_006.zip`

zip 内至少包含：

- `run_context.txt`
- `pytest_inference_contracts.log`
- `package_inventory.tsv`
- `models_dir_listing.txt`
- `model_file_inventory.tsv`
- `model_metadata_inventory.jsonl`
- `model_candidate_ranking.tsv`
- `model_inventory_summary.json`
- `model_inventory.log`
- `readiness_conclusion.txt`
- `summary.txt`

邮件主题请使用：

```text
[AK服务器] 任务完成：small model readiness runtime_small_model_readiness_2026_0706_p1_006
```

默认收件人继续使用：

```text
gwlee1995@gmail.com,yilili1023@gmail.com
```

## 验收标准

本轮算完成：

- `git pull --ff-only` 成功。
- `tests/inference_contracts` 执行并回传日志。
- `models/` 存在性、候选数量、metadata 文件数量、top candidate 和包可见性均写入 artifact。
- `readiness_conclusion.txt` 明确给出 `readiness_status`。
- 邮件正文明确说明本轮没有加载模型、没有运行推理、没有装包或修环境。

本轮不要求：

- 不要求模型能生成文本。
- 不要求 vLLM 或 Transformers 成功加载模型。
- 不要求修复缺失包。
- 不要求确认 CANN device timeline pairing。
