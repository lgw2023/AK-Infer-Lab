# Developer to Server

## 当前任务：P1.31 Qwen3.5-4B vLLM 长上下文 Prefix-Cache 交叉实验

任务 ID：

```text
runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031
```

目标：复盘 P1.29/P1.30 后，现有 `continuous32_mixed` 的 input/output token 仍偏短。本轮要用 Qwen3.5-4B / vLLM OpenAI API streaming client 执行长上下文 prefix-cache 交叉实验：`input_cap_tokens=8K/16K/32K/64K/128K`，`target_shared_prefix_ratio=30%/60%/90%`，prefix-cache on/off 成对运行，输出固定 `1024 tokens`，并输出 AISBench-style 性能表、common metrics、on/off delta、observed prefix hit rate 与 phase memory 小表。

本轮不是 P5，不启动 DeepSeek-V4-Flash，不运行全量 msprof denominator。

## 必须回答

1. 使用服务器本地 `git pull-remote` / `server_local/git_pull_remote_wins.sh` 同步后 commit 是什么？
2. `tests/inference_contracts` 是否通过？
3. prefix-cache on/off 两个 mode 是否都覆盖 15 个 cell？
4. 每个成功 cell 是否 `measured_request_count=3`、`measured_success_count=3`？
5. 每个成功 cell 是否固定输出 `1024 tokens`，`generated_token_count_mismatch_count=0`？
6. 是否生成 `prefix_ratio_matrix_aisbench_parameters.tsv`，并包含 `E2EL/TTFT/TPOT/ITL/InputTokens/OutputTokens/OutputTokenThroughput/PrefillTokenThroughput`？
7. 是否生成 `prefix_ratio_matrix_common_metrics.tsv`，并包含 `Benchmark Duration/Concurrency/Max Concurrency/Request Throughput/Input Token Throughput/Output Token Throughput/Total Token Throughput`？
8. 是否生成 `prefix_ratio_matrix_delta_summary.tsv`，并分开记录 target shared-prefix ratio 与 observed prefix cache hit rate？
9. prefix-cache off 的 observed hit rate 是否为 `0.0` 或接近 `0`？如果不是，请报告原始 stats 行。
10. 64K/128K 若失败，失败原因是什么？是否保留 server command、日志摘要和 artifact path？
11. phase memory 是否生成 `phase_memory_summary.tsv`？其口径是否仍为 process-group RSS/PSS 与 whole-device HBM occupancy？
12. 是否遵守邮件正文和每个附件均不超过 70KB？

## 执行边界

允许：

- 使用服务器本地 `server_local/git_pull_remote_wins.sh`（或 alias `git pull-remote`）同步到 `origin/main`；若 helper 不存在且工作区干净，才 fallback 到 `git pull --ff-only`。
- `python -m pytest tests/inference_contracts -q`。
- 使用服务器当前 conda 环境。
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`。
- source `/usr/local/Ascend/nnal/atb/set_env.sh`。
- 使用当前环境已有 `vllm`、`vllm_ascend`、`transformers`、`npu-smi`。
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`。
- 启动本地回环 vLLM OpenAI API server。
- 对 `prefix_cache_on` 与 `prefix_cache_off` 各跑一遍 15-cell 长上下文矩阵。
- 每个 cell 单独启动 server，防止跨 cell warm cache 污染。
- 每个 cell 使用 1 个 warmup 请求和 3 个 measured 请求。
- 采集 host process-group RSS/PSS 与 NPU whole-device HBM occupancy。
- 输出 70KB 内的小摘要、TSV/JSON、文件清单和必要日志摘录。

禁止：

- 不安装、升级、卸载或修复任何包。
- 不创建新 conda 环境。
- 不改 driver、CANN、apt、dpkg、NPU runtime、vLLM 或 vLLM-Ascend 源码。
- 不缩短 `8K/16K/32K/64K/128K` 输入 cap。
- 不把 `1024` output tokens 降回 `64`。
- 不跳过失败 cell，不把失败 cell 计为成功。
- 不把 target shared-prefix ratio 当成 observed prefix cache hit rate。
- 不运行全量 msprof denominator。
- 不启动 P5，不启动 DeepSeek-V4-Flash。
- 不安装或调用 MindIE-Motor/AISBench；本轮只对齐其性能指标表口径。
- 不在服务器上修改、提交或 push 项目代码。
- 不回传 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。
- 不回传 raw server log、完整 generated text、raw memory samples、大 zip、大 TSV/JSON 或完整实验目录。
- 不输出 compute-bound、memory-bound、HBM bottleneck、scheduler-bound 或 prefix-cache benefit 归因。

## 建议执行命令

在服务器上执行：

```bash
set -u

cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
ON_DIR="${ARTIFACT_DIR}/prefix_cache_on"
OFF_DIR="${ARTIFACT_DIR}/prefix_cache_off"
SUMMARY_DIR="${ARTIFACT_DIR}/matrix_summary"
PYTHON_BIN="${PYTHON_BIN:-/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab/bin/python}"
MODEL_PATH="${MODEL_PATH:-/data/node0_disk1/Public/Qwen3.5-4B}"

mkdir -p "${ARTIFACT_DIR}" "${ON_DIR}" "${OFF_DIR}" "${SUMMARY_DIR}"

if [ -x server_local/git_pull_remote_wins.sh ]; then
  server_local/git_pull_remote_wins.sh > "${ARTIFACT_DIR}/git_pull.log" 2>&1
else
  git pull --ff-only > "${ARTIFACT_DIR}/git_pull.log" 2>&1
fi
git_pull_exit_code=$?
echo "${git_pull_exit_code}" > "${ARTIFACT_DIR}/git_pull_exit_code.txt"

{
  echo "run_id=${RUN_ID}"
  echo "commit=$(git rev-parse HEAD)"
  echo "timestamp=$(date -Is)"
  echo "PYTHON_BIN=${PYTHON_BIN}"
  echo "MODEL_PATH=${MODEL_PATH}"
  echo "ARTIFACT_DIR=${ARTIFACT_DIR}"
  echo "ON_DIR=${ON_DIR}"
  echo "OFF_DIR=${OFF_DIR}"
  echo "SUMMARY_DIR=${SUMMARY_DIR}"
  echo "input_caps=8192,16384,32768,65536,131072"
  echo "prefix_ratios=0.30,0.60,0.90"
  echo "output_tokens=1024"
  echo "warmup_requests_per_cell=1"
  echo "measured_requests_per_cell=3"
  echo "mode_count=2"
  echo "cell_count_per_mode=15"
  echo "git_pull_exit_code=${git_pull_exit_code}"
  echo "policy=long_context_prefix_ratio_matrix_no_bottleneck_claim"
} > "${ARTIFACT_DIR}/run_context.txt"

set +e
source /usr/local/Ascend/cann-9.0.0/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u

export ASCEND_RT_VISIBLE_DEVICES="${ASCEND_RT_VISIBLE_DEVICES:-6}"
export AK_VLLM_DEVICE_LABEL="${AK_VLLM_DEVICE_LABEL:-npu:${ASCEND_RT_VISIBLE_DEVICES}}"
export VLLM_USE_V1="${VLLM_USE_V1:-1}"
export VLLM_PLUGINS=ascend
export VLLM_WORKER_MULTIPROC_METHOD="${VLLM_WORKER_MULTIPROC_METHOD:-spawn}"

"${PYTHON_BIN}" -m pytest tests/inference_contracts -q \
  > "${ARTIFACT_DIR}/pytest.log" 2>&1
pytest_exit_code=$?
echo "${pytest_exit_code}" > "${ARTIFACT_DIR}/pytest_exit_code.txt"

run_mode() {
  local mode="$1"
  local mode_dir="$2"

  "${PYTHON_BIN}" tools/inference_contracts/run_vllm_api_prefix_ratio_matrix.py \
    --run-id "${RUN_ID}_${mode}" \
    --artifact-dir "${mode_dir}" \
    --model-path "${MODEL_PATH}" \
    --mode "${mode}" \
    --input-caps 8192,16384,32768,65536,131072 \
    --prefix-ratios 0.30,0.60,0.90 \
    --output-tokens 1024 \
    --warmup-requests-per-cell 1 \
    --measured-requests-per-cell 3 \
    --sample-memory \
    > "${mode_dir}/prefix_ratio_matrix.log" 2>&1

  local exit_code=$?
  echo "${exit_code}" > "${mode_dir}/prefix_ratio_matrix_exit_code.txt"
}

set +e
run_mode "prefix_cache_on" "${ON_DIR}"
run_mode "prefix_cache_off" "${OFF_DIR}"

"${PYTHON_BIN}" tools/inference_contracts/summarize_vllm_api_prefix_ratio_matrix.py \
  --run-id "${RUN_ID}_summary" \
  --prefix-cache-on-dir "${ON_DIR}" \
  --prefix-cache-off-dir "${OFF_DIR}" \
  --artifact-dir "${SUMMARY_DIR}" \
  > "${ARTIFACT_DIR}/matrix_summary.log" 2>&1
summary_exit_code=$?
echo "${summary_exit_code}" > "${ARTIFACT_DIR}/summary_exit_code.txt"
set -u

"${PYTHON_BIN}" - <<'PY' "${ARTIFACT_DIR}" "${ON_DIR}" "${OFF_DIR}" "${SUMMARY_DIR}"
import json
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
on_dir = Path(sys.argv[2])
off_dir = Path(sys.argv[3])
summary_dir = Path(sys.argv[4])

def read_text(path):
    return path.read_text(encoding="utf-8", errors="replace").strip() if path.exists() else "missing"

def load_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

on_result = load_json(on_dir / "result.json")
off_result = load_json(off_dir / "result.json")
summary_result = load_json(summary_dir / "prefix_ratio_matrix_summary_result.json")

result = {
    "run_id": artifact_dir.name,
    "commit": read_text(artifact_dir / "run_context.txt").split("commit=")[-1].splitlines()[0] if "commit=" in read_text(artifact_dir / "run_context.txt") else "",
    "git_pull_exit_code": read_text(artifact_dir / "git_pull_exit_code.txt"),
    "pytest_exit_code": read_text(artifact_dir / "pytest_exit_code.txt"),
    "prefix_cache_on_exit_code": read_text(on_dir / "prefix_ratio_matrix_exit_code.txt"),
    "prefix_cache_off_exit_code": read_text(off_dir / "prefix_ratio_matrix_exit_code.txt"),
    "summary_exit_code": read_text(artifact_dir / "summary_exit_code.txt"),
    "on_status": on_result.get("status", "missing"),
    "off_status": off_result.get("status", "missing"),
    "summary_status": summary_result.get("overall_status", "missing"),
    "on_cell_count": on_result.get("cell_count", 0),
    "off_cell_count": off_result.get("cell_count", 0),
    "expected_cell_count_per_mode": summary_result.get("expected_cell_count_per_mode", 15),
    "output_tokens": 1024,
    "policy": "long_context_prefix_ratio_matrix_no_bottleneck_claim",
}
(artifact_dir / "p1_031_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

candidate_relpaths = [
    "run_context.txt",
    "p1_031_result.json",
    "prefix_cache_on/summary.txt",
    "prefix_cache_on/cell_summary.tsv",
    "prefix_cache_on/phase_memory_summary.tsv",
    "prefix_cache_on/mail_attachment_candidates.tsv",
    "prefix_cache_off/summary.txt",
    "prefix_cache_off/cell_summary.tsv",
    "prefix_cache_off/phase_memory_summary.tsv",
    "prefix_cache_off/mail_attachment_candidates.tsv",
    "matrix_summary/summary.txt",
    "matrix_summary/prefix_ratio_matrix_summary_result.json",
    "matrix_summary/prefix_ratio_matrix_completeness.tsv",
    "matrix_summary/prefix_ratio_matrix_aisbench_parameters.tsv",
    "matrix_summary/prefix_ratio_matrix_common_metrics.tsv",
    "matrix_summary/prefix_ratio_matrix_delta_summary.tsv",
    "matrix_summary/mail_attachment_candidates.tsv",
]
lines = ["path\tsize_bytes\tmail_ok"]
for relpath in candidate_relpaths:
    path = artifact_dir / relpath
    if not path.exists():
        continue
    size = path.stat().st_size
    lines.append(f"{path}\t{size}\t{str(size <= 70 * 1024).lower()}")
(artifact_dir / "mail_attachment_candidates.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")

summary_lines = [
    "## run_context",
    read_text(artifact_dir / "run_context.txt"),
    "",
    "## exit_codes_and_status",
    json.dumps(result, ensure_ascii=False, indent=2),
    "",
    "## prefix_cache_on_summary",
    read_text(on_dir / "summary.txt"),
    "",
    "## prefix_cache_off_summary",
    read_text(off_dir / "summary.txt"),
    "",
    "## matrix_summary",
    read_text(summary_dir / "summary.txt"),
    "",
    "## mail_attachment_candidates",
    read_text(artifact_dir / "mail_attachment_candidates.tsv"),
]
(artifact_dir / "summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
PY

echo "DONE"
cat "${ARTIFACT_DIR}/summary.txt"
```

## 成功口径

强成功必须全部满足：

- `git_pull_exit_code=0`
- `pytest_exit_code=0`
- `prefix_cache_on_exit_code=0`
- `prefix_cache_off_exit_code=0`
- `summary_exit_code=0`
- on/off 两个 mode 均 `cell_count=15`
- on/off 两个 mode 的 15 个 cell 均 `cell_status=success`
- 每个成功 cell 均 `measured_request_count=3`、`measured_success_count=3`
- 每个成功 cell 均 `generated_token_count_mismatch_count=0`
- 每个成功 measured request 均 `generated_token_count=1024`
- `prefix_ratio_matrix_aisbench_parameters.tsv`、`prefix_ratio_matrix_common_metrics.tsv`、`prefix_ratio_matrix_delta_summary.tsv`、`prefix_ratio_matrix_completeness.tsv` 均存在
- target shared-prefix ratio 与 observed prefix cache hit rate 分字段记录
- `phase_memory_summary.tsv` 存在；若无 memory sample，必须说明 `sample_count=0` 的原因

如果 64K/128K 等 cell 失败：

- 不要缩短输入 cap。
- 不要把 output tokens 降到 64 或其他更小值。
- 不要删除失败 cell。
- 不要把失败轮次当成功。
- 保留失败日志在服务器本地，只回传 70KB 内摘要和小文件。

## 回传要求

邮件正文控制在 70KB 内，必须包含：

```text
run_id
commit
git_pull_exit_code
pytest_exit_code
prefix_cache_on_exit_code
prefix_cache_off_exit_code
summary_exit_code
on/off status
on/off cell_count and success_cell_count
failed cells if any:
  mode input_cap_tokens target_prefix_ratio_pct error summary artifact path
per-cell summary:
  mode input_cap_tokens target_prefix_ratio_pct measured_success_count/3 generated_mismatch
  TTFT median, TPOT median, E2E/client_wall median, output_tokens_per_s median
  server_stats_max_kv_cache_usage_pct
  server_stats_max_prefix_cache_hit_rate_pct
  target_vs_observed_prefix_hit_rate_delta_pct
matrix summary:
  AISBench-style parameters table exists
  common metrics table exists
  delta summary exists
boundary:
  target shared-prefix ratio != observed prefix cache hit rate
  vLLM OpenAI streaming client metrics != MindIE native timing
  ITL is host streaming inter-chunk latency
  phase memory is process-group RSS/PSS + whole-device HBM occupancy
  no compute-bound / memory-bound / HBM bottleneck / scheduler-bound / prefix-cache benefit claim
artifact_dir
mail_attachment_candidates
```

建议附件：

- `summary.txt`
- `p1_031_result.json`
- `matrix_summary/summary.txt`
- `matrix_summary/prefix_ratio_matrix_summary_result.json`
- `matrix_summary/prefix_ratio_matrix_completeness.tsv`
- `matrix_summary/prefix_ratio_matrix_aisbench_parameters.tsv`
- `matrix_summary/prefix_ratio_matrix_common_metrics.tsv`
- `matrix_summary/prefix_ratio_matrix_delta_summary.tsv`
- `prefix_cache_on/cell_summary.tsv`
- `prefix_cache_on/phase_memory_summary.tsv`
- `prefix_cache_off/cell_summary.tsv`
- `prefix_cache_off/phase_memory_summary.tsv`
- `mail_attachment_candidates.tsv`

不要附件：

- raw server log
- generated text
- complete `request_summary.tsv` if over 70KB
- `memory_samples.jsonl`
- raw profiler output
- large zip or full artifact directory
