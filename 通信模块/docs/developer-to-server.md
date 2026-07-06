# 开发机 -> 服务器消息

> 本文件每次只保留当前待执行任务；旧历史信息已清空。

## 当前任务：P1.8 model symlink readiness 只读复核

- 任务 ID：`runtime_model_symlink_readiness_2026_0706_p1_007`
- 证据基线：`obs_2026_0705_atlas800t_a2_006`
- P1.6 profiler bridge：`runtime_profiler_bridge_2026_0706_p1_005`
- P1.7 small model readiness：`runtime_small_model_readiness_2026_0706_p1_006`
- 当前契约入口：`工作记录与进度笔记本/p1_inference_contracts/`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_model_symlink_readiness_handoff.md`

P1.7 最新反馈邮件时间为 2026-07-06 00:54:20 CST，服务器执行 commit 为 `7c2e3ff`，`tests/inference_contracts` 为 `11 passed in 0.20s`。当前 conda 环境中 `torch_npu`、`transformers`、`safetensors`、`vllm`、`vllm_ascend` 均可见；`mindie`、`mindspore` 不可见。

P1.7 的正式扫描结果为：

- `models_dir=/data/node0_disk1/liguowei/AK-Infer-Lab/models`
- `models_dir_exists=1`
- `top_level_entry_count=10`
- `model_candidate_count=0`
- `metadata_file_count=0`
- `readiness_status=blocked_no_readable_model_metadata`

邮件补充观察说明：`models/` 下 9 个模型目录入口是 symlink，指向 `../../../Public/<name>`；P1.7 脚本使用 `os.walk` 时没有 follow symlinks，因此只扫描到 `README.md`。服务器人工 `ls` 已确认 `/data/node0_disk1/Public/Qwen3.5-4B` 含 `config.json`、`tokenizer_config.json`、`model.safetensors.index.json` 等 metadata。

本轮目标不是模型加载，不运行推理，不安装或修复任何包。本轮只做 symlink-aware metadata 复核：跟随 `models/` 顶层 symlink 到 `/data/node0_disk1/Public/...`，只读解析小型 metadata，区分生成式 causal LM、embedding、reranker、keyword/NER 等候选类型，并给出是否可以另起独立小模型加载 smoke 的候选路径。

## 服务器执行边界

请执行：

- 在服务器项目根目录 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行本文件命令。
- 通过 `git pull --ff-only` 获取开发机已提交的最新项目状态。
- 使用服务器当前 conda 环境；不创建新环境。
- 默认扫描项目根目录下 `models/`，并跟随顶层 symlink 的真实目标。
- 默认 Public 目录为 `/data/node0_disk1/Public`；如实际不同，可通过 `AK_PUBLIC_MODELS_DIR=/path/to/Public` 覆盖，并在邮件中说明。
- 产出并邮件回传 `runtime_model_symlink_readiness_2026_0706_p1_007.zip`。

请不要执行：

- 不要加载模型权重，不要实例化模型，不要实例化 tokenizer。
- 不要运行真实模型推理、小模型 smoke、vLLM engine serve/generate 或 P000-P012 workload。
- 不要读取权重文件内容，只允许对权重文件做 `stat`。
- 不要复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件。
- 不要安装、升级、卸载或修复 `transformers`、`vllm`、`vllm_ascend`、`mindie`、`mindspore` 或其他推理框架包。
- 不要修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码。
- 不要自动修复或重装 `ascend910b-driver`。
- 不要在服务器上修改、提交或 push 项目代码。
- 不要发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。

## 本轮必须回答的问题

- `models/` 顶层目录项哪些是 symlink，分别解析到哪个真实路径？
- symlink 目标是否存在、是否可读、是否位于 `/data/node0_disk1/Public/`？
- 跟随 symlink 后能否读取 `config.json`、`tokenizer_config.json`、`generation_config.json`、`*.safetensors.index.json` 等 metadata？
- 哪些候选是生成式 causal LM，哪些只是 embedding、reranker 或 keyword/NER 模型？
- 是否存在一个最适合下一轮独立小模型加载 smoke 的候选路径？
- 如果仍不能进入加载 smoke，阻塞原因是 symlink 目标不可读、metadata 缺失、候选不是生成模型，还是需要人工选择模型？

## 执行命令

在昇腾服务器项目根目录执行：

```bash
set -u

git pull --ff-only
PULL_STATUS=$?
if [ "${PULL_STATUS}" -ne 0 ]; then
  exit "${PULL_STATUS}"
fi

RUN_ID=runtime_model_symlink_readiness_2026_0706_p1_007
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
MODELS_DIR="${AK_MODELS_DIR:-models}"
PUBLIC_MODELS_DIR="${AK_PUBLIC_MODELS_DIR:-/data/node0_disk1/Public}"
export RUN_ID ARTIFACT_DIR MODELS_DIR PUBLIC_MODELS_DIR

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
  echo "PUBLIC_MODELS_DIR=${PUBLIC_MODELS_DIR}"
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

python - <<'PY' > "${ARTIFACT_DIR}/model_symlink_inventory.log" 2>&1
import json
import os
import re
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
models_dir = Path(os.environ["MODELS_DIR"]).expanduser()
public_dir = Path(os.environ["PUBLIC_MODELS_DIR"]).expanduser()
if not models_dir.is_absolute():
    models_dir = (Path.cwd() / models_dir).resolve()
if not public_dir.is_absolute():
    public_dir = (Path.cwd() / public_dir).resolve()

max_depth = 5
max_json_bytes = 10_000_000
metadata_filenames = {
    "config.json",
    "tokenizer_config.json",
    "generation_config.json",
    "preprocessor_config.json",
    "processor_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
}
weight_suffixes = {".safetensors", ".bin", ".pt", ".pth", ".gguf"}

def safe_stat(path, follow_symlinks=True):
    try:
        return path.stat() if follow_symlinks else path.lstat()
    except OSError:
        return None

def clean(value):
    text = "" if value is None else str(value)
    return text.replace("\n", "\\n").replace("\t", " ")

def json_load_small(path):
    stat = safe_stat(path)
    if stat is None:
        return None, "stat_failed"
    if stat.st_size > max_json_bytes:
        return None, f"too_large:{stat.st_size}"
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace")), ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"

def metadata_kind(name):
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

def under(path, parent):
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False

def relative_to_root(path, root):
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)

summary = {
    "models_dir": str(models_dir),
    "models_dir_exists": models_dir.exists(),
    "models_dir_is_dir": models_dir.is_dir(),
    "public_models_dir": str(public_dir),
    "public_models_dir_exists": public_dir.exists(),
    "public_models_dir_is_dir": public_dir.is_dir(),
    "note": "symlink-aware metadata-only scan; no model/tokenizer load and no weight content read",
}

symlink_rows = ["entry\tentry_path\tkind\traw_link_target\tresolved_path\tresolved_exists\tresolved_is_dir\tunder_public\tbytes_lstat"]
file_rows = ["model_name\trel_path\tmetadata_kind\tbytes\tparse_error"]
metadata_rows = []
candidates = {}
scan_roots = []

if models_dir.exists() and models_dir.is_dir():
    entries = sorted(models_dir.iterdir(), key=lambda path: path.name)
else:
    entries = []

for entry in entries:
    lstat = safe_stat(entry, follow_symlinks=False)
    raw_target = ""
    try:
        raw_target = os.readlink(entry) if entry.is_symlink() else ""
    except OSError as exc:
        raw_target = f"readlink_error:{type(exc).__name__}:{exc}"
    resolved = entry.resolve(strict=False)
    resolved_exists = resolved.exists()
    resolved_is_dir = resolved.is_dir()
    if entry.is_symlink():
        kind = "symlink_dir" if resolved_is_dir else "symlink_other"
    elif entry.is_dir():
        kind = "dir"
    elif entry.is_file():
        kind = "file"
    else:
        kind = "other"
    symlink_rows.append("\t".join([
        clean(entry.name),
        clean(str(entry)),
        kind,
        clean(raw_target),
        clean(str(resolved)),
        "1" if resolved_exists else "0",
        "1" if resolved_is_dir else "0",
        "1" if under(resolved, public_dir) else "0",
        str(lstat.st_size if lstat else ""),
    ]))
    if resolved_exists and resolved_is_dir and kind in {"symlink_dir", "dir"}:
        scan_roots.append((entry.name, resolved))

def candidate_for(model_name, root):
    key = str(root)
    rec = candidates.setdefault(key, {
        "model_name": model_name,
        "resolved_path": str(root),
        "under_public": under(root, public_dir),
        "has_config": False,
        "has_tokenizer_metadata": False,
        "has_generation_config": False,
        "has_safetensors_index": False,
        "metadata_files": [],
        "metadata_parse_errors": [],
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
        "vocab_size": "",
        "tokenizer_class": "",
        "model_max_length": "",
    })
    return rec

def record_metadata(model_name, root, path, kind):
    rec = candidate_for(model_name, root)
    rel = relative_to_root(path, root)
    data, error = json_load_small(path)
    stat = safe_stat(path)
    rec["metadata_files"].append(rel)
    if error:
        rec["metadata_parse_errors"].append(f"{rel}:{error}")
    if kind == "config":
        rec["has_config"] = True
    elif kind == "tokenizer":
        rec["has_tokenizer_metadata"] = True
    elif kind == "generation":
        rec["has_generation_config"] = True
    elif kind == "safetensors_index":
        rec["has_safetensors_index"] = True

    selected = {}
    if isinstance(data, dict):
        for key in [
            "model_type",
            "architectures",
            "torch_dtype",
            "vocab_size",
            "max_position_embeddings",
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
        ]:
            if key in data:
                selected[key] = data.get(key)
        if kind == "config":
            rec["model_type"] = clean(data.get("model_type", ""))
            rec["architectures"] = data.get("architectures", []) or []
            rec["torch_dtype"] = clean(data.get("torch_dtype", ""))
            rec["max_position_embeddings"] = clean(data.get("max_position_embeddings", ""))
            rec["num_hidden_layers"] = clean(data.get("num_hidden_layers", ""))
            rec["hidden_size"] = clean(data.get("hidden_size", ""))
            rec["num_attention_heads"] = clean(data.get("num_attention_heads", ""))
            rec["num_key_value_heads"] = clean(data.get("num_key_value_heads", ""))
            rec["num_experts"] = clean(data.get("num_experts", ""))
            rec["vocab_size"] = clean(data.get("vocab_size", ""))
        if kind == "tokenizer":
            if not rec["tokenizer_class"]:
                rec["tokenizer_class"] = clean(data.get("tokenizer_class", ""))
            if not rec["model_max_length"]:
                rec["model_max_length"] = clean(data.get("model_max_length", ""))

    metadata_rows.append(json.dumps({
        "model_name": model_name,
        "root": str(root),
        "path": rel,
        "kind": kind,
        "bytes": stat.st_size if stat else None,
        "parse_error": error,
        "selected": selected,
    }, ensure_ascii=False, sort_keys=True))
    file_rows.append("\t".join([
        clean(model_name),
        clean(rel),
        clean(kind),
        str(stat.st_size if stat else ""),
        clean(error),
    ]))

for model_name, root in scan_roots:
    candidate_for(model_name, root)
    seen_dirs = set()
    for current, dirs, files in os.walk(root, followlinks=True):
        current_path = Path(current)
        try:
            depth = len(current_path.relative_to(root).parts)
        except ValueError:
            depth = 0
        stat = safe_stat(current_path)
        inode_key = None
        if stat is not None:
            inode_key = (stat.st_dev, stat.st_ino)
            if inode_key in seen_dirs:
                dirs[:] = []
                continue
            seen_dirs.add(inode_key)
        dirs[:] = sorted([name for name in dirs if not name.startswith(".")])
        files = sorted(files)
        if depth >= max_depth:
            dirs[:] = []
        for name in files:
            path = current_path / name
            kind = metadata_kind(name)
            suffix = path.suffix.lower()
            if kind:
                record_metadata(model_name, root, path, kind)
            if suffix in weight_suffixes:
                rec = candidate_for(model_name, root)
                stat = safe_stat(path)
                rec["weight_file_count"] += 1
                rec["weight_bytes_stat_only"] += stat.st_size if stat else 0

def classify_and_score(rec):
    text = " ".join([
        rec["model_name"],
        rec["model_type"],
        " ".join(str(x) for x in rec["architectures"]),
        rec["resolved_path"],
    ]).lower()
    score = 0
    reasons = []
    kind = "unknown"
    if rec["has_config"]:
        score += 4
        reasons.append("has_config")
    if rec["has_tokenizer_metadata"]:
        score += 3
        reasons.append("has_tokenizer_metadata")
    if rec["has_safetensors_index"] or rec["weight_file_count"] > 0:
        score += 2
        reasons.append("has_weight_manifest_or_files")
    if "forcausallm" in text or "causal_lm" in text or "causallm" in text:
        score += 5
        reasons.append("causal_lm_architecture")
        kind = "causal_lm"
    elif any(token in text for token in ["embedding", "reranker", "bge", "gliner", "tokenclassification", "sequenceclassification"]):
        score -= 5
        reasons.append("non_generate_model_hint")
        kind = "non_generate"
    elif any(token in text for token in ["qwen", "llama", "baichuan", "internlm", "deepseek"]):
        score += 2
        reasons.append("llm_name_hint")
        kind = "possible_lm"
    if re.search(r"(^|[^0-9])(0\.5b|1\.5b|1b|2b|3b|4b|tiny|small)([^0-9]|$)", text):
        score += 2
        reasons.append("small_or_mid_name_hint")
    if re.search(r"(^|[^0-9])(27b|30b|32b|70b|72b|110b)([^0-9]|$)", text):
        score -= 4
        reasons.append("large_name_hint")
    if not rec["under_public"]:
        score -= 1
        reasons.append("outside_public_dir")
    if rec["metadata_parse_errors"]:
        score -= 1
        reasons.append("metadata_parse_errors")
    return kind, score, ",".join(reasons)

ranking_rows = ["rank\tscore\tcandidate_kind\treasons\tmodel_name\tresolved_path\tunder_public\tmodel_type\tarchitectures\ttorch_dtype\tmax_position_embeddings\tnum_hidden_layers\thidden_size\tnum_attention_heads\tnum_key_value_heads\tnum_experts\tvocab_size\ttokenizer_class\tmodel_max_length\tweight_file_count\tweight_bytes_stat_only\tmetadata_files\tmetadata_parse_errors"]
ranked = []
for rec in candidates.values():
    kind, score, reasons = classify_and_score(rec)
    rec["candidate_kind"] = kind
    rec["score"] = score
    rec["reasons"] = reasons
    ranked.append(rec)
ranked.sort(key=lambda rec: (-rec["score"], rec["model_name"], rec["resolved_path"]))
for index, rec in enumerate(ranked, start=1):
    ranking_rows.append("\t".join([
        str(index),
        str(rec["score"]),
        rec["candidate_kind"],
        clean(rec["reasons"]),
        clean(rec["model_name"]),
        clean(rec["resolved_path"]),
        "1" if rec["under_public"] else "0",
        clean(rec["model_type"]),
        clean(",".join(str(x) for x in rec["architectures"])),
        clean(rec["torch_dtype"]),
        clean(rec["max_position_embeddings"]),
        clean(rec["num_hidden_layers"]),
        clean(rec["hidden_size"]),
        clean(rec["num_attention_heads"]),
        clean(rec["num_key_value_heads"]),
        clean(rec["num_experts"]),
        clean(rec["vocab_size"]),
        clean(rec["tokenizer_class"]),
        clean(rec["model_max_length"]),
        str(rec["weight_file_count"]),
        str(rec["weight_bytes_stat_only"]),
        clean(",".join(rec["metadata_files"][:30])),
        clean(",".join(rec["metadata_parse_errors"][:10])),
    ]))

causal_candidates = [rec for rec in ranked if rec["candidate_kind"] == "causal_lm" and rec["has_config"] and rec["has_tokenizer_metadata"]]
top_candidate = causal_candidates[0] if causal_candidates else (ranked[0] if ranked else None)
summary.update({
    "top_level_entry_count": len(entries),
    "scan_root_count": len(scan_roots),
    "metadata_file_count": len(metadata_rows),
    "model_candidate_count": len(candidates),
    "causal_lm_candidate_count": len(causal_candidates),
    "top_candidate_model_name": top_candidate["model_name"] if top_candidate else "",
    "top_candidate_resolved_path": top_candidate["resolved_path"] if top_candidate else "",
    "top_candidate_kind": top_candidate["candidate_kind"] if top_candidate else "",
    "top_candidate_score": top_candidate["score"] if top_candidate else 0,
    "top_candidate_reasons": top_candidate["reasons"] if top_candidate else "",
})

(artifact_dir / "models_symlink_map.tsv").write_text("\n".join(symlink_rows) + "\n", encoding="utf-8")
(artifact_dir / "model_metadata_files.tsv").write_text("\n".join(file_rows) + "\n", encoding="utf-8")
(artifact_dir / "model_metadata_inventory.jsonl").write_text("\n".join(metadata_rows) + ("\n" if metadata_rows else ""), encoding="utf-8")
(artifact_dir / "model_candidate_ranking.tsv").write_text("\n".join(ranking_rows) + "\n", encoding="utf-8")
(artifact_dir / "model_symlink_inventory_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
PY
MODEL_STATUS=$?
cat "${ARTIFACT_DIR}/model_symlink_inventory.log"
echo "model_symlink_inventory_exit_code=${MODEL_STATUS}" >> "${ARTIFACT_DIR}/run_context.txt"

python - <<'PY' > "${ARTIFACT_DIR}/readiness_conclusion.txt"
import json
import os
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
summary = json.loads((artifact_dir / "model_symlink_inventory_summary.json").read_text(encoding="utf-8"))

packages = {}
lines = (artifact_dir / "package_inventory.tsv").read_text(encoding="utf-8", errors="replace").splitlines()
for line in lines[1:]:
    parts = line.split("\t")
    if len(parts) >= 4:
        packages[parts[0]] = {"version": parts[2], "found": parts[3] == "1"}

def found(name):
    return packages.get(name, {}).get("found", False)

models_exists = bool(summary.get("models_dir_exists") and summary.get("models_dir_is_dir"))
scan_root_count = int(summary.get("scan_root_count") or 0)
metadata_count = int(summary.get("metadata_file_count") or 0)
candidate_count = int(summary.get("model_candidate_count") or 0)
causal_count = int(summary.get("causal_lm_candidate_count") or 0)
top_path = str(summary.get("top_candidate_resolved_path") or "")
top_kind = str(summary.get("top_candidate_kind") or "")
has_torch_npu = found("torch") and found("torch_npu")
has_transformers_entry = found("transformers") and found("safetensors")
has_vllm_entry = found("vllm") or found("vllm_ascend")

if not models_exists:
    status = "blocked_models_dir_missing"
elif scan_root_count <= 0:
    status = "blocked_no_readable_symlink_targets"
elif metadata_count <= 0 or candidate_count <= 0:
    status = "blocked_no_metadata_after_following_symlinks"
elif causal_count <= 0:
    status = "blocked_no_causal_lm_candidate"
elif not has_torch_npu:
    status = "blocked_torch_npu_not_visible"
elif not (has_transformers_entry or has_vllm_entry):
    status = "blocked_no_loading_framework_entry_visible"
else:
    status = "ready_for_separate_small_model_load_smoke_candidate_only"

print(f"models_dir={summary.get('models_dir', '')}")
print(f"public_models_dir={summary.get('public_models_dir', '')}")
print(f"models_dir_exists={1 if models_exists else 0}")
print(f"scan_root_count={scan_root_count}")
print(f"model_candidate_count={candidate_count}")
print(f"metadata_file_count={metadata_count}")
print(f"causal_lm_candidate_count={causal_count}")
print(f"top_candidate_model_name={summary.get('top_candidate_model_name', '')}")
print(f"top_candidate_resolved_path={top_path}")
print(f"top_candidate_kind={top_kind}")
print(f"top_candidate_score={summary.get('top_candidate_score', '')}")
print(f"top_candidate_reasons={summary.get('top_candidate_reasons', '')}")
print(f"torch_npu_visible={1 if has_torch_npu else 0}")
print(f"transformers_entry_visible={1 if has_transformers_entry else 0}")
print(f"vllm_entry_visible={1 if has_vllm_entry else 0}")
print(f"readiness_status={status}")
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
for title, filename, limit in [
    ("run_context", "run_context.txt", 80),
    ("readiness_conclusion", "readiness_conclusion.txt", 80),
    ("package_inventory", "package_inventory.tsv", 40),
    ("models_symlink_map", "models_symlink_map.tsv", 80),
    ("top_model_candidates", "model_candidate_ranking.tsv", 30),
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

print("P1.8 model symlink readiness 只读复核已完成。")
print()
print(f"任务 ID: {run_id}")
print(f"附件: 工作记录与进度笔记本/runtime_trace_smokes/{run_id}.zip")
print()
print(summary)
print("执行边界：")
print("- 未加载模型权重")
print("- 未实例化模型或 tokenizer")
print("- 未运行 generate/serve/小模型 smoke/P000-P012 workload")
print("- 未安装、升级、卸载或修复任何推理框架包")
print("- 未修改 models/、Public/、CANN/driver/runtime/vLLM 源码")
PY

(
  cd 工作记录与进度笔记本/runtime_trace_smokes
  rm -f "${RUN_ID}.zip"
  zip -qr "${RUN_ID}.zip" "${RUN_ID}"
  unzip -t "${RUN_ID}.zip"
)

python 通信模块/send_notify.py \
  -s "[AK服务器] 任务完成：model symlink readiness ${RUN_ID}" \
  --body-file "${ARTIFACT_DIR}/mail_body.txt" \
  --attach "工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}.zip"
```

## 需要回传的附件

请邮件附加：

- `工作记录与进度笔记本/runtime_trace_smokes/runtime_model_symlink_readiness_2026_0706_p1_007.zip`

zip 内至少包含：

- `run_context.txt`
- `pytest_inference_contracts.log`
- `package_inventory.tsv`
- `models_symlink_map.tsv`
- `model_metadata_files.tsv`
- `model_metadata_inventory.jsonl`
- `model_candidate_ranking.tsv`
- `model_symlink_inventory_summary.json`
- `model_symlink_inventory.log`
- `readiness_conclusion.txt`
- `summary.txt`

邮件主题请使用：

```text
[AK服务器] 任务完成：model symlink readiness runtime_model_symlink_readiness_2026_0706_p1_007
```

默认收件人继续使用：

```text
gwlee1995@gmail.com,yilili1023@gmail.com
```

## 验收标准

本轮算完成：

- `git pull --ff-only` 成功。
- `tests/inference_contracts` 执行并回传日志。
- `models_symlink_map.tsv` 明确记录每个顶层入口的 symlink 目标与真实路径。
- `model_candidate_ranking.tsv` 明确区分 causal LM 与非生成模型。
- `readiness_conclusion.txt` 明确给出 `readiness_status` 和推荐候选路径。
- 邮件正文明确说明本轮没有加载模型、没有运行推理、没有装包或修环境。

本轮不要求：

- 不要求模型能生成文本。
- 不要求 vLLM 或 Transformers 成功加载模型。
- 不要求修复缺失包。
- 不要求确认 CANN device timeline pairing。
