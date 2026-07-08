# P1.29 Qwen3.5-4B vLLM API Streaming Perf + Denominator Handoff

任务 ID：`runtime_vllm_api_streaming_perf_denominator_2026_0708_p1_029`

上一轮依据：

- P1.28 `runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028`
- P0/P3 `hardware_ceiling_sweep_2026_0708_p0_007`

目标：补齐 Qwen3.5-4B / vLLM API 在 `continuous32_mixed` 小 prompt workload 下的模型推理性能指标。P1.28 已有 fixed 64-token raw counter readout，但缺 TTFT/TPOT、E2E latency、输出吞吐、server stats A/B、单位映射，以及 MatMul/shape 的 FLOPs 和 tensor bytes denominator。本轮显式补这些指标，并额外输出 AISBench/MindIE-Motor 风格的性能参数表和 common metric 表，作为后续 DeepSeek Flash 复用的推理性能指标模板。

本轮分两段：

1. `perf_unprofiled`：不启用 msprof，使用 streaming `/v1/completions` 客户端采集用户可见 TTFT、TPOT、E2E latency、output tokens/s、server stats、prefix on/off A/B，并汇总 `E2EL/TTFT/TPOT/ITL/InputTokens/OutputTokens/OutputTokenThroughput/PrefillTokenThroughput` 与 `Benchmark Duration/Request Throughput/Token Throughput` 等 AISBench-style 小表。
2. `msprof_denominator`：启用 msprof 跑同一 `continuous32_mixed` streaming workload，离线读取 `ge_summary/task_time`，输出 input/output shapes、dtype、MatMul FLOPs denominator、input/output tensor footprint bytes、unit mapping 和 hardware-ceiling 可映射性。

边界：本轮可以输出 Qwen3.5-4B/vLLM 的模型推理性能指标和 denominator evidence；仍不得直接输出 compute-bound、memory-bound、HBM-bound、scheduler-bound、prefix-cache benefit 定论或 DeepSeek 迁移结论。prefix on/off delta 只按本轮条件报告，不外推。

## 必须回答

1. `git pull --ff-only` 后 commit 是什么？
2. `tests/inference_contracts` 是否通过？
3. `perf_unprofiled` on/off 两轮是否都完成 32/32 streaming 请求？
4. on/off 两轮是否都固定生成 64 tokens，`generated_token_count_mismatch_count=0`？
5. on/off 两轮的 TTFT median/p95、TPOT median/p95、E2E median/p95、aggregate output tokens/s 分别是多少？
6. on/off 两轮 vLLM server stats 的 max running、max waiting、max KV cache usage、max prefix cache hit rate 分别是多少？
7. `vllm_api_streaming_perf_pair_result.json`、mode summary、delta summary 是否生成？
8. `vllm_api_streaming_perf_parameters.tsv` 是否生成并包含 `E2EL`、`TTFT`、`TPOT`、`ITL`、`InputTokens`、`OutputTokens`、`OutputTokenThroughput`、`PrefillTokenThroughput`？
9. `vllm_api_streaming_perf_common_metrics.tsv` 是否生成并包含 `Benchmark Duration`、`Concurrency`、`Max Concurrency`、`Request Throughput`、`Input Token Throughput`、`Output Token Throughput`、`Total Token Throughput`？
10. `msprof_denominator` on/off 两轮是否生成 msprof raw 目录和 `ai_core_op_summary.db`？
11. `msprof_shape_denominator_result.json`、shape denominator、by-op summary、unit mapping、hardware denominator mapping 是否生成？
12. MatMulV2/MatMulV3 是否出现 shape-derived FLOPs denominator？如果没有，缺失原因是什么？
13. tensor bytes 是 input/output tensor footprint，不是 HBM traffic。请确认报告中是否保留这个边界。
14. AISBench-style 表是 vLLM OpenAI streaming client 口径；`ITL` 是 host streaming inter-chunk latency，不是 MindIE native runtime decode event。请确认报告中是否保留这个边界。
15. 是否遵守 70KB 邮件正文和附件上限？

## 执行边界

允许：

- `git pull --ff-only`。
- `python -m pytest tests/inference_contracts -q`。
- 使用服务器当前 conda 环境。
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`。
- source `/usr/local/Ascend/nnal/atb/set_env.sh`。
- 使用当前环境已有 `vllm`、`vllm_ascend`、`msprof`。
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`。
- 启动本地回环 vLLM OpenAI API server。
- 对 `prefix_cache_on` 与 `prefix_cache_off` 各运行一次 unprofiled streaming `continuous32_mixed`。
- 对 `msprof_prefix_cache_on` 与 `msprof_prefix_cache_off` 各运行一次 profiled streaming `continuous32_mixed`，只用于 denominator 和单位映射。
- 固定 CLI 语义等价于 `--case-plan continuous32_mixed`。
- 在 `/v1/completions` 请求中使用 `stream=true`、`min_tokens=64`、`ignore_eos=true`。
- 只读解析本轮 raw profiler SQLite。
- 输出 70KB 内的小摘要、TSV/JSON、文件清单和小日志。

禁止：

- 不安装、升级、卸载或修复任何包。
- 不创建新 conda 环境。
- 不改 driver、CANN、apt、dpkg、NPU runtime、vLLM 或 vLLM-Ascend 源码。
- 不静默降低 `max_model_len`、不删减 case、不降低输入 cap、不缩短 output token。
- 不运行 full 16K/32K 或 full `P010=43216` tokens。
- 不运行多 worker 压测、生产 benchmark、长时间服务或额外模型。
- 不启动 P5，不启动 DeepSeek-V4-Flash。
- 不切换 Docker 推理栈。
- 不安装或调用 MindIE-Motor/AISBench；本轮只对齐其性能指标表口径。
- 不在服务器上修改、提交或 push 项目代码。
- 不回传 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。
- 不回传超过 70KB 的邮件正文或附件；raw profiler、完整日志、大 zip、完整大 TSV 和实验目录必须留在服务器本地。
- 不把 profiler 下的 TTFT/TPOT 当作无 profiler 性能结论。
- 不把 vLLM OpenAI streaming client 口径的 `ITL`、`PrefillTokenThroughput` 当作 MindIE native `prefill_time/decode_time`。
- 不把 shape-derived tensor bytes 当作 HBM bandwidth 或实际 memory traffic。
- 不输出瓶颈归因或优化建议。

## 建议执行命令

在服务器上执行：

```bash
set -u

cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=runtime_vllm_api_streaming_perf_denominator_2026_0708_p1_029
PREV_RUN_ID=runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028
CASE_PLAN=continuous32_mixed
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
PERF_DIR="${ARTIFACT_DIR}/perf_unprofiled"
PAIR_DIR="${ARTIFACT_DIR}/perf_pair_readout"
MSPROF_SOURCE_DIR="${ARTIFACT_DIR}/msprof_source"
DENOM_DIR="${ARTIFACT_DIR}/msprof_denominator_readout"
PYTHON_BIN="${PYTHON_BIN:-/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab/bin/python}"
MODEL_PATH="${MODEL_PATH:-/data/node0_disk1/Public/Qwen3.5-4B}"
MSPROF_ROOT_ON="/tmp/${RUN_ID}_msprof_prefix_cache_on_msprof"
MSPROF_ROOT_OFF="/tmp/${RUN_ID}_msprof_prefix_cache_off_msprof"

mkdir -p "${ARTIFACT_DIR}" "${PERF_DIR}" "${PAIR_DIR}" "${MSPROF_SOURCE_DIR}" "${DENOM_DIR}"

git pull --ff-only > "${ARTIFACT_DIR}/git_pull.log" 2>&1
git_pull_exit_code=$?
echo "${git_pull_exit_code}" > "${ARTIFACT_DIR}/git_pull_exit_code.txt"

{
  echo "run_id=${RUN_ID}"
  echo "previous_run_id=${PREV_RUN_ID}"
  echo "commit=$(git rev-parse HEAD)"
  echo "timestamp=$(date -Is)"
  echo "PYTHON_BIN=${PYTHON_BIN}"
  echo "MODEL_PATH=${MODEL_PATH}"
  echo "ARTIFACT_DIR=${ARTIFACT_DIR}"
  echo "PERF_DIR=${PERF_DIR}"
  echo "PAIR_DIR=${PAIR_DIR}"
  echo "MSPROF_SOURCE_DIR=${MSPROF_SOURCE_DIR}"
  echo "DENOM_DIR=${DENOM_DIR}"
  echo "MSPROF_ROOT_ON=${MSPROF_ROOT_ON}"
  echo "MSPROF_ROOT_OFF=${MSPROF_ROOT_OFF}"
  echo "case_plan=${CASE_PLAN}"
  echo "max_model_len=9216"
  echo "request_min_tokens=64"
  echo "request_ignore_eos=1"
  echo "streaming=1"
  echo "git_pull_exit_code=${git_pull_exit_code}"
} > "${ARTIFACT_DIR}/run_context.txt"

set +e
source /usr/local/Ascend/cann-9.0.0/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u

export ASCEND_RT_VISIBLE_DEVICES="${ASCEND_RT_VISIBLE_DEVICES:-6}"
export VLLM_USE_V1="${VLLM_USE_V1:-1}"
export VLLM_PLUGINS=ascend
export VLLM_WORKER_MULTIPROC_METHOD="${VLLM_WORKER_MULTIPROC_METHOD:-spawn}"

"${PYTHON_BIN}" -m pytest tests/inference_contracts -q \
  > "${ARTIFACT_DIR}/pytest.log" 2>&1
pytest_exit_code=$?
echo "${pytest_exit_code}" > "${ARTIFACT_DIR}/pytest_exit_code.txt"

run_streaming_perf_mode() {
  local mode="$1"
  local prefix_arg="$2"
  local mode_dir="${PERF_DIR}/${mode}"
  rm -rf "${mode_dir}"
  mkdir -p "${mode_dir}"

  "${PYTHON_BIN}" tools/inference_contracts/run_vllm_api_streaming_perf.py \
    --run-id "${RUN_ID}_${mode}_perf" \
    --artifact-dir "${mode_dir}" \
    --model-path "${MODEL_PATH}" \
    --case-plan "${CASE_PLAN}" \
    --max-model-len 9216 \
    --min-tokens 64 \
    --ignore-eos \
    "${prefix_arg}" \
    > "${mode_dir}/streaming_perf.log" 2>&1

  local exit_code=$?
  echo "${exit_code}" > "${mode_dir}/streaming_perf_exit_code.txt"
}

run_streaming_perf_mode "prefix_cache_on" "--enable-prefix-caching"
run_streaming_perf_mode "prefix_cache_off" "--no-enable-prefix-caching"

"${PYTHON_BIN}" tools/inference_contracts/summarize_vllm_api_streaming_perf_pair.py \
  --run-id "${RUN_ID}_perf_pair" \
  --prefix-cache-on-dir "${PERF_DIR}/prefix_cache_on" \
  --prefix-cache-off-dir "${PERF_DIR}/prefix_cache_off" \
  --artifact-dir "${PAIR_DIR}" \
  > "${ARTIFACT_DIR}/perf_pair_readout.log" 2>&1
perf_pair_exit_code=$?
echo "${perf_pair_exit_code}" > "${ARTIFACT_DIR}/perf_pair_exit_code.txt"

run_profiled_denominator_mode() {
  local mode="$1"
  local prefix_arg="$2"
  local mode_dir="${MSPROF_SOURCE_DIR}/${mode}"
  local msprof_out="/tmp/${RUN_ID}_${mode}_msprof"
  rm -rf "${mode_dir}" "${msprof_out}"
  mkdir -p "${mode_dir}" "${msprof_out}"

  {
    echo "mode=${mode}"
    echo "prefix_arg=${prefix_arg}"
    echo "msprof_out=${msprof_out}"
    echo "case_plan=${CASE_PLAN}"
    echo "max_model_len=9216"
    echo "request_min_tokens=64"
    echo "request_ignore_eos=1"
    echo "purpose=msprof_shape_denominator_not_unprofiled_perf"
  } > "${mode_dir}/run_context.txt"

  msprof \
    --output "${msprof_out}" \
    --msproftx=on \
    --storage-limit=8192 \
    "${PYTHON_BIN}" tools/inference_contracts/run_vllm_api_streaming_perf.py \
      --run-id "${RUN_ID}_${mode}_msprof" \
      --artifact-dir "${mode_dir}/vllm" \
      --model-path "${MODEL_PATH}" \
      --case-plan "${CASE_PLAN}" \
      --max-model-len 9216 \
      --min-tokens 64 \
      --ignore-eos \
      "${prefix_arg}" \
      > "${mode_dir}/msprof_streaming_perf.log" 2>&1

  local exit_code=$?
  echo "${exit_code}" > "${mode_dir}/msprof_exit_code.txt"
  find "${msprof_out}" -type f -print 2>/dev/null | sort > "${mode_dir}/msprof_output_files.txt" || true
  du -ah "${msprof_out}" 2>/dev/null | sort -h > "${mode_dir}/msprof_du.txt" || true
}

run_profiled_denominator_mode "msprof_prefix_cache_on" "--enable-prefix-caching"
run_profiled_denominator_mode "msprof_prefix_cache_off" "--no-enable-prefix-caching"

"${PYTHON_BIN}" tools/inference_contracts/summarize_msprof_shape_denominators.py \
  --run-id "${RUN_ID}_shape_denominators" \
  --source-artifact-dir "${MSPROF_SOURCE_DIR}" \
  --artifact-dir "${DENOM_DIR}" \
  --msprof-root-on "${MSPROF_ROOT_ON}" \
  --msprof-root-off "${MSPROF_ROOT_OFF}" \
  --top-limit 80 \
  > "${ARTIFACT_DIR}/msprof_shape_denominator.log" 2>&1
shape_denominator_exit_code=$?
echo "${shape_denominator_exit_code}" > "${ARTIFACT_DIR}/shape_denominator_exit_code.txt"

"${PYTHON_BIN}" - <<'PY' "${ARTIFACT_DIR}" "${PERF_DIR}" "${PAIR_DIR}" "${MSPROF_SOURCE_DIR}" "${DENOM_DIR}"
import json
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
perf_dir = Path(sys.argv[2])
pair_dir = Path(sys.argv[3])
msprof_source_dir = Path(sys.argv[4])
denom_dir = Path(sys.argv[5])

def read_text(path):
    return path.read_text(encoding="utf-8", errors="replace").strip() if path.exists() else "missing"

summary = {
    "run_id": artifact_dir.name,
    "commit": read_text(artifact_dir / "run_context.txt").split("commit=")[-1].splitlines()[0] if (artifact_dir / "run_context.txt").exists() and "commit=" in read_text(artifact_dir / "run_context.txt") else "",
    "git_pull_exit_code": read_text(artifact_dir / "git_pull_exit_code.txt"),
    "pytest_exit_code": read_text(artifact_dir / "pytest_exit_code.txt"),
    "perf_on_exit_code": read_text(perf_dir / "prefix_cache_on" / "streaming_perf_exit_code.txt"),
    "perf_off_exit_code": read_text(perf_dir / "prefix_cache_off" / "streaming_perf_exit_code.txt"),
    "perf_pair_exit_code": read_text(artifact_dir / "perf_pair_exit_code.txt"),
    "msprof_on_exit_code": read_text(msprof_source_dir / "msprof_prefix_cache_on" / "msprof_exit_code.txt"),
    "msprof_off_exit_code": read_text(msprof_source_dir / "msprof_prefix_cache_off" / "msprof_exit_code.txt"),
    "shape_denominator_exit_code": read_text(artifact_dir / "shape_denominator_exit_code.txt"),
    "perf_pair_result_exists": int((pair_dir / "vllm_api_streaming_perf_pair_result.json").exists()),
    "shape_denominator_result_exists": int((denom_dir / "msprof_shape_denominator_result.json").exists()),
    "policy": "qwen_vllm_streaming_perf_and_shape_denominator_no_bottleneck_claim",
}
(artifact_dir / "p1_029_result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

candidate_relpaths = [
    "run_context.txt",
    "p1_029_result.json",
    "perf_pair_readout/summary.txt",
    "perf_pair_readout/vllm_api_streaming_perf_mode_summary.tsv",
    "perf_pair_readout/vllm_api_streaming_perf_delta_summary.tsv",
    "perf_pair_readout/vllm_api_streaming_perf_parameters.tsv",
    "perf_pair_readout/vllm_api_streaming_perf_common_metrics.tsv",
    "perf_pair_readout/vllm_api_streaming_perf_pair_result.json",
    "msprof_denominator_readout/summary.txt",
    "msprof_denominator_readout/msprof_shape_denominator_result.json",
    "msprof_denominator_readout/msprof_shape_denominator_summary.tsv",
    "msprof_denominator_readout/msprof_shape_denominator_by_op_type.tsv",
    "msprof_denominator_readout/msprof_unit_mapping.tsv",
    "msprof_denominator_readout/hardware_denominator_mapping.tsv",
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
    "## exit_codes",
    json.dumps(summary, ensure_ascii=False, indent=2),
    "",
    "## perf_pair_summary",
    read_text(pair_dir / "summary.txt"),
    "",
    "## denominator_summary",
    read_text(denom_dir / "summary.txt"),
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

必须全部满足：

- `git_pull_exit_code=0`
- `pytest_exit_code=0`
- `perf_on_exit_code=0`
- `perf_off_exit_code=0`
- `perf_pair_exit_code=0`
- `msprof_on_exit_code=0`
- `msprof_off_exit_code=0`
- `shape_denominator_exit_code=0`
- unprofiled on/off 均 `request_count=32`、`success_case_count=32`、`failed_case_count=0`
- unprofiled on/off 均 `generated_token_count_mismatch_count=0`
- pair readout 中存在 TTFT/TPOT/E2E/output tokens/s 的 mode summary 和 on-minus-off delta summary
- pair readout 中存在 `vllm_api_streaming_perf_parameters.tsv`，且 `E2EL/TTFT/TPOT/ITL/InputTokens/OutputTokens/OutputTokenThroughput/PrefillTokenThroughput` 字段非空。
- pair readout 中存在 `vllm_api_streaming_perf_common_metrics.tsv`，且 `Benchmark Duration/Concurrency/Max Concurrency/Request Throughput/Input Token Throughput/Output Token Throughput/Total Token Throughput` 字段非空。
- AISBench-style 表明确写出 `vllm_openai_streaming_client_metrics_not_mindie_native_timing` 或等价边界，不声称 MindIE native `prefill_time/decode_time`。
- denominator readout 中存在 `msprof_unit_mapping.tsv`、`hardware_denominator_mapping.tsv`
- denominator readout 至少对 MatMulV2 或 MatMulV3 输出 shape-derived FLOPs denominator，若无则必须写出 `shape_or_dtype_unavailable` 等明确缺失原因

如果有失败：

- 不要缩短任务取巧通过。
- 不要删减 32 case。
- 不要把失败轮次当成功。
- 保留失败日志在服务器本地，只回传 70KB 内摘要和小文件。

## 回传要求

邮件正文控制在 70KB 内，必须包含：

```text
run_id
commit
git_pull_exit_code
pytest_exit_code
perf_on_exit_code
perf_off_exit_code
perf_pair_exit_code
msprof_on_exit_code
msprof_off_exit_code
shape_denominator_exit_code
perf_unprofiled summary:
  on/off request_count success failed generated_mismatch
  on/off TTFT median/p95
  on/off TPOT median/p95
  on/off E2E median/p95
  on/off aggregate output tokens/s
  on/off AISBench-style E2EL/TTFT/TPOT/ITL/InputTokens/OutputTokens/OutputTokenThroughput/PrefillTokenThroughput Average/Median/P90/P99/N
  on/off Benchmark Duration/Concurrency/Max Concurrency/Request Throughput/Input Token Throughput/Output Token Throughput/Total Token Throughput
  on/off max running/waiting/KV/prefix-hit stats
denominator summary:
  shape_row_count
  op_type_row_count
  MatMulV2/MatMulV3 denominator status
  unit mapping confidence
boundary:
  unprofiled perf != profiled denominator
  vLLM OpenAI streaming client metrics != MindIE native prefill/decode timing
  ITL is host streaming inter-chunk latency
  tensor footprint bytes != HBM traffic
  no bottleneck claim
artifact_dir
mail_attachment_candidates
```

建议附件：

- `summary.txt`
- `p1_029_result.json`
- `perf_pair_readout/vllm_api_streaming_perf_mode_summary.tsv`
- `perf_pair_readout/vllm_api_streaming_perf_delta_summary.tsv`
- `perf_pair_readout/vllm_api_streaming_perf_parameters.tsv`
- `perf_pair_readout/vllm_api_streaming_perf_common_metrics.tsv`
- `perf_pair_readout/vllm_api_streaming_perf_pair_result.json`
- `msprof_denominator_readout/msprof_shape_denominator_result.json`
- `msprof_denominator_readout/msprof_shape_denominator_by_op_type.tsv`
- `msprof_denominator_readout/msprof_unit_mapping.tsv`
- `msprof_denominator_readout/hardware_denominator_mapping.tsv`
- `mail_attachment_candidates.tsv`

不要附件：

- raw msprof 目录
- 完整 server log
- 完整 generated text
- 大 zip
- 大 TSV/JSON
