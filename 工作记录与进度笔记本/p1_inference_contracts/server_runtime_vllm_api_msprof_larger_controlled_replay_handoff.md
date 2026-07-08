# P1.28 vLLM API msprof Larger Controlled Replay Handoff

任务 ID：`runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028`

上一轮依据：`runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027`

目标：P1.26/P1.27 已证明 16 请求 `continuous16_mixed` 可以完成固定 64-token on/off msprof 受控复现、request-device full 聚合和离线 readout。本轮把 workload 扩大到 `continuous32_mixed`，仍保持 4K/8K 输入 cap、`--max-model-len 9216`、`--min-tokens 64 --ignore-eos`，并在同一轮完成 on/off msprof、request-device 聚合和 readout 小摘要。

本轮仍是 raw counter 证据扩展，不是 benchmark、吞吐比较、调度效率结论、prefix cache 命中率验收、瓶颈归因或优化建议。

## 必须回答

1. `git pull --ff-only` 后的 commit 是什么？
2. `tests/inference_contracts` 是否通过？
3. `continuous32_mixed` 是否实际发送 32 个请求，on/off 两轮是否都 32/32 成功？
4. 两个 mode 是否都固定生成 64 tokens，`generated_token_count_mismatch_count=0`？
5. on/off 两轮的 msprof raw 目录是否生成，并各自包含 device sqlite？
6. request-device full 聚合是否完成，`request_device_aggregate_fast_exit_code` 是多少？
7. readout 是否完成，`controlled_readout_exit_code` 是多少？
8. 是否生成 `controlled_replay_readout_result.json`、mode delta、pair delta、top-op delta 和 AI Core metric delta 小摘要？
9. 是否遵守 70KB 邮件正文和附件上限？

## 执行边界

允许：

- `git pull --ff-only`。
- `python -m pytest tests/inference_contracts -q`。
- 使用服务器当前 conda 环境。
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`。
- source `/usr/local/Ascend/nnal/atb/set_env.sh`。
- 使用当前环境已有 `vllm`、`vllm_ascend`、`msprof`。
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`。
- 对 `msprof_prefix_cache_on` 与 `msprof_prefix_cache_off` 各运行一次 profiled `continuous32_mixed` 负载。
- 在 `/v1/completions` 请求中使用 vLLM SamplingParams：`min_tokens=64`、`ignore_eos=true`。
- 只读解析本轮 raw profiler SQLite。
- 运行 `bulk_temp_window_join_parallel_modes` 聚合器。
- 运行 `tools/inference_contracts/summarize_msprof_controlled_replay.py` 生成小 readout。
- 输出 70KB 内的小摘要、TSV/JSON、文件清单和小日志。

禁止：

- 不安装、升级、卸载或修复任何包。
- 不创建新 conda 环境。
- 不改 driver、CANN、apt、dpkg、NPU runtime、vLLM 或 vLLM-Ascend 源码。
- 不静默降低 `max_model_len`、不删减 case、不降低输入 cap、不缩短 output token。
- 不运行 full 16K/32K 或 full `P010=43216` tokens。
- 不运行多 worker 压测、benchmark、长时间服务或吞吐压测。
- 不切换 Docker 推理栈。
- 不在服务器上修改、提交或 push 项目代码。
- 不回传 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。
- 不回传超过 70KB 的邮件正文或附件；raw profiler、完整日志、大 zip、完整大 TSV 和实验目录必须留在服务器本地。
- 不输出性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因或优化建议。

## 建议执行命令

在服务器上执行：

```bash
set -u

cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028
PREV_RUN_ID=runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027
CASE_PLAN=continuous32_mixed
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
SOURCE_ARTIFACT_DIR="${ARTIFACT_DIR}/source"
FINAL_ANALYSIS_DIR="${ARTIFACT_DIR}/final_analysis"
READOUT_DIR="${ARTIFACT_DIR}/readout"
PYTHON_BIN="${PYTHON_BIN:-/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab/bin/python}"
MODEL_PATH="${MODEL_PATH:-/data/node0_disk1/Public/Qwen3.5-4B}"
MSPROF_ROOT_ON="/tmp/${RUN_ID}_msprof_prefix_cache_on_msprof"
MSPROF_ROOT_OFF="/tmp/${RUN_ID}_msprof_prefix_cache_off_msprof"

mkdir -p "${ARTIFACT_DIR}" "${SOURCE_ARTIFACT_DIR}" "${FINAL_ANALYSIS_DIR}" "${READOUT_DIR}"

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
  echo "SOURCE_ARTIFACT_DIR=${SOURCE_ARTIFACT_DIR}"
  echo "FINAL_ANALYSIS_DIR=${FINAL_ANALYSIS_DIR}"
  echo "READOUT_DIR=${READOUT_DIR}"
  echo "MSPROF_ROOT_ON=${MSPROF_ROOT_ON}"
  echo "MSPROF_ROOT_OFF=${MSPROF_ROOT_OFF}"
  echo "case_plan=${CASE_PLAN}"
  echo "max_model_len=9216"
  echo "request_min_tokens=64"
  echo "request_ignore_eos=1"
  echo "workers=2"
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

run_profiled_mode() {
  local mode="$1"
  local prefix_arg="$2"
  local mode_dir="${SOURCE_ARTIFACT_DIR}/${mode}"
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
  } > "${mode_dir}/run_context.txt"

  msprof \
    --output "${msprof_out}" \
    --msproftx=on \
    --storage-limit=8192 \
    "${PYTHON_BIN}" tools/inference_contracts/run_vllm_api_concurrency_smoke.py \
      --run-id "${RUN_ID}_${mode}" \
      --artifact-dir "${mode_dir}/vllm" \
      --model-path "${MODEL_PATH}" \
      --case-plan "${CASE_PLAN}" \
      --max-model-len 9216 \
      --min-tokens 64 \
      --ignore-eos \
      "${prefix_arg}" \
      > "${mode_dir}/msprof_vllm_api.log" 2>&1

  local exit_code=$?
  echo "${exit_code}" > "${mode_dir}/msprof_exit_code.txt"
  find "${msprof_out}" -type f -print 2>/dev/null | sort > "${mode_dir}/msprof_output_files.txt" || true
  du -ah "${msprof_out}" 2>/dev/null | sort -h > "${mode_dir}/msprof_du.txt" || true
}

run_profiled_mode "msprof_prefix_cache_on" "--enable-prefix-caching"
run_profiled_mode "msprof_prefix_cache_off" "--no-enable-prefix-caching"

"${PYTHON_BIN}" - <<'PY' "${SOURCE_ARTIFACT_DIR}" "${ARTIFACT_DIR}/generated_token_length_summary.tsv"
import json
import sys
from pathlib import Path

source_dir = Path(sys.argv[1])
out_path = Path(sys.argv[2])
lines = [
    "mode\tstatus\trequest_count\tsuccess_case_count\tfailed_case_count\tgenerated_token_count_mismatch_count\tmin_generated_token_count\tmax_generated_token_count"
]
for mode in ("msprof_prefix_cache_on", "msprof_prefix_cache_off"):
    result_path = source_dir / mode / "vllm" / "vllm_api_concurrency_result.json"
    if not result_path.exists():
        lines.append(f"{mode}\tmissing_result\t0\t0\t0\t0\t0\t0")
        continue
    data = json.loads(result_path.read_text(encoding="utf-8"))
    rows = data.get("rows") or []
    generated = [int(row.get("generated_token_count") or 0) for row in rows]
    mismatch = sum(
        1
        for row in rows
        if int(row.get("generated_token_count") or 0) != int(row.get("max_new_tokens") or 0)
    )
    lines.append(
        f"{mode}\t{data.get('status', '')}\t{data.get('request_count', len(rows))}\t"
        f"{data.get('success_case_count', 0)}\t{data.get('failed_case_count', 0)}\t"
        f"{mismatch}\t{min(generated) if generated else 0}\t{max(generated) if generated else 0}"
    )
out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

set +e
if command -v timeout >/dev/null 2>&1; then
  timeout 60m "${PYTHON_BIN}" tools/inference_contracts/analyze_msprof_request_device_aggregate.py \
    --run-id "${RUN_ID}" \
    --source-artifact-dir "${SOURCE_ARTIFACT_DIR}" \
    --artifact-dir "${FINAL_ANALYSIS_DIR}" \
    --msprof-root-on "${MSPROF_ROOT_ON}" \
    --msprof-root-off "${MSPROF_ROOT_OFF}" \
    --workers 2 \
    > "${ARTIFACT_DIR}/request_device_aggregate_fast.log" 2>&1
  aggregate_exit_code=$?
else
  "${PYTHON_BIN}" tools/inference_contracts/analyze_msprof_request_device_aggregate.py \
    --run-id "${RUN_ID}" \
    --source-artifact-dir "${SOURCE_ARTIFACT_DIR}" \
    --artifact-dir "${FINAL_ANALYSIS_DIR}" \
    --msprof-root-on "${MSPROF_ROOT_ON}" \
    --msprof-root-off "${MSPROF_ROOT_OFF}" \
    --workers 2 \
    > "${ARTIFACT_DIR}/request_device_aggregate_fast.log" 2>&1
  aggregate_exit_code=$?
fi
echo "${aggregate_exit_code}" > "${ARTIFACT_DIR}/request_device_aggregate_fast_exit_code.txt"

"${PYTHON_BIN}" tools/inference_contracts/summarize_msprof_controlled_replay.py \
  --run-id "${RUN_ID}_readout" \
  --source-run-id "${RUN_ID}" \
  --source-artifact-dir "${ARTIFACT_DIR}" \
  --analysis-dir "${FINAL_ANALYSIS_DIR}" \
  --generated-token-summary "${ARTIFACT_DIR}/generated_token_length_summary.tsv" \
  --artifact-dir "${READOUT_DIR}" \
  --top-op-limit 40 \
  --metric-limit 60 \
  > "${ARTIFACT_DIR}/controlled_readout.log" 2>&1
controlled_readout_exit_code=$?
echo "${controlled_readout_exit_code}" > "${ARTIFACT_DIR}/controlled_readout_exit_code.txt"

"${PYTHON_BIN}" - <<'PY' "${ARTIFACT_DIR}" "${FINAL_ANALYSIS_DIR}" "${READOUT_DIR}"
import json
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
analysis_dir = Path(sys.argv[2])
readout_dir = Path(sys.argv[3])

summary = {
    "run_id": artifact_dir.name,
    "analysis_result_exists": int((analysis_dir / "msprof_request_device_aggregate_result.json").exists()),
    "readout_result_exists": int((readout_dir / "controlled_replay_readout_result.json").exists()),
    "generated_token_length_summary": (artifact_dir / "generated_token_length_summary.tsv").read_text(encoding="utf-8")
    if (artifact_dir / "generated_token_length_summary.tsv").exists()
    else "",
    "aggregate_exit_code": (artifact_dir / "request_device_aggregate_fast_exit_code.txt").read_text(encoding="utf-8").strip()
    if (artifact_dir / "request_device_aggregate_fast_exit_code.txt").exists()
    else "",
    "controlled_readout_exit_code": (artifact_dir / "controlled_readout_exit_code.txt").read_text(encoding="utf-8").strip()
    if (artifact_dir / "controlled_readout_exit_code.txt").exists()
    else "",
}
(artifact_dir / "controlled_replay_result.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

on_exit_code="$(cat "${SOURCE_ARTIFACT_DIR}/msprof_prefix_cache_on/msprof_exit_code.txt" 2>/dev/null || echo missing)"
off_exit_code="$(cat "${SOURCE_ARTIFACT_DIR}/msprof_prefix_cache_off/msprof_exit_code.txt" 2>/dev/null || echo missing)"

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt"
  echo "git_pull_exit_code=${git_pull_exit_code}"
  echo "pytest_exit_code=${pytest_exit_code}"
  echo "msprof_prefix_cache_on_exit_code=${on_exit_code}"
  echo "msprof_prefix_cache_off_exit_code=${off_exit_code}"
  echo "request_device_aggregate_fast_exit_code=${aggregate_exit_code}"
  echo "controlled_readout_exit_code=${controlled_readout_exit_code}"
  echo ""
  echo "## generated_token_length_summary"
  cat "${ARTIFACT_DIR}/generated_token_length_summary.tsv" 2>/dev/null || true
  echo ""
  echo "## final_analysis_summary"
  cat "${FINAL_ANALYSIS_DIR}/summary.txt" 2>/dev/null || echo "missing final_analysis/summary.txt"
  echo ""
  echo "## readout_summary"
  cat "${READOUT_DIR}/summary.txt" 2>/dev/null || echo "missing readout/summary.txt"
} > "${ARTIFACT_DIR}/summary.txt"

cp "${ARTIFACT_DIR}/summary.txt" "${ARTIFACT_DIR}/mail_summary.txt"

"${PYTHON_BIN}" - <<'PY' "${ARTIFACT_DIR}" "${FINAL_ANALYSIS_DIR}" "${READOUT_DIR}"
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
analysis_dir = Path(sys.argv[2])
readout_dir = Path(sys.argv[3])
candidate_paths = [
    artifact_dir / "summary.txt",
    artifact_dir / "run_context.txt",
    artifact_dir / "generated_token_length_summary.tsv",
    artifact_dir / "controlled_replay_result.json",
    artifact_dir / "mail_summary.txt",
    analysis_dir / "summary.txt",
    analysis_dir / "msprof_request_device_aggregate_result.json",
    analysis_dir / "prefix_cache_mode_request_delta.tsv",
    analysis_dir / "prefix_pair_candidate_delta.tsv",
    readout_dir / "summary.txt",
    readout_dir / "controlled_replay_readout_result.json",
    readout_dir / "controlled_replay_mode_delta_summary.tsv",
    readout_dir / "controlled_replay_pair_delta_summary.tsv",
    readout_dir / "controlled_replay_top_op_delta.tsv",
    readout_dir / "controlled_replay_ai_core_metric_delta.tsv",
]
lines = ["path\tsize_bytes\tmail_ok"]
for path in candidate_paths:
    if not path.exists():
        continue
    size = path.stat().st_size
    lines.append(f"{path}\t{size}\t{str(size <= 70 * 1024).lower()}")
(artifact_dir / "mail_attachment_candidates.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

{
  echo ""
  echo "## mail_attachment_candidates"
  cat "${ARTIFACT_DIR}/mail_attachment_candidates.tsv" 2>/dev/null || true
} >> "${ARTIFACT_DIR}/mail_summary.txt"

echo "DONE"
echo "artifact_dir=${ARTIFACT_DIR}"
cat "${ARTIFACT_DIR}/mail_summary.txt"
```

## 成功口径

强成功：

- `git_pull_exit_code=0`
- `pytest_exit_code=0`
- `msprof_prefix_cache_on_exit_code=0`
- `msprof_prefix_cache_off_exit_code=0`
- on/off 两轮均 `request_count=32`、`success_case_count=32`、`failed_case_count=0`
- on/off 两轮均 `generated_token_count_mismatch_count=0`、`min_generated_token_count=64`、`max_generated_token_count=64`
- `request_device_aggregate_fast_exit_code=0`
- `controlled_readout_exit_code=0`
- `readout/controlled_replay_readout_result.json` 中 `overall_status=success`
- 产出 mode delta、pair delta、top-op delta、AI Core metric delta 四类小摘要

最低完成：

- 即使任一步失败，也必须回传 `run_context.txt`、`mail_summary.txt`、失败日志尾部摘要、已生成的小文件清单和服务器侧路径。
- 如果 32 请求 workload 失败，不要自动降回 16 请求；报告失败原因、失败 case、server log 尾部和可见 NPU/runtime 状态。

## 回传要求

邮件正文请包含：

```text
P1.28 vLLM API msprof larger controlled replay 已完成/失败。

run_id: runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028
previous_run_id: runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027
commit: <git rev-parse HEAD>
artifact_dir: 工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028
case_plan: continuous32_mixed
git_pull_exit_code: <...>
pytest_exit_code: <...>
msprof_prefix_cache_on_exit_code: <...>
msprof_prefix_cache_off_exit_code: <...>
request_device_aggregate_fast_exit_code: <...>
controlled_readout_exit_code: <...>

generated_token_length_summary:
- msprof_prefix_cache_on: request_count=<...>, success_case_count=<...>, failed_case_count=<...>, generated_token_count_mismatch_count=<...>, min_generated_token_count=<...>, max_generated_token_count=<...>
- msprof_prefix_cache_off: request_count=<...>, success_case_count=<...>, failed_case_count=<...>, generated_token_count_mismatch_count=<...>, min_generated_token_count=<...>, max_generated_token_count=<...>

readout:
- overall_status=<...>
- missing_files=<...>
- mode_delta_group_count=<...>
- pair_delta_row_count=<...>
- top_op_delta_row_count=<...>
- metric_delta_row_count=<...>
- all_request_delta_total_duration_time_sum_on_minus_off=<...>
- negative_duration_delta_request_count=<...>
- positive_duration_delta_request_count=<...>

边界：使用 --case-plan continuous32_mixed、--max-model-len 9216、--min-tokens 64 --ignore-eos；未安装或修复包，未切换 Docker，未运行 full 16K/32K 或 P010=43216，未输出 benchmark/吞吐/调度效率/prefix cache 命中率/瓶颈/优化结论。
```

附件只允许包含 `mail_attachment_candidates.tsv` 中 `mail_ok=true` 且不超过 70KB 的小文件。优先回传：

- `${RUN_ID}/mail_summary.txt`
- `${RUN_ID}/summary.txt`
- `${RUN_ID}/run_context.txt`
- `${RUN_ID}/generated_token_length_summary.tsv`
- `${RUN_ID}/controlled_replay_result.json`
- `${RUN_ID}/final_analysis/summary.txt`
- `${RUN_ID}/final_analysis/msprof_request_device_aggregate_result.json`
- `${RUN_ID}/final_analysis/prefix_cache_mode_request_delta.tsv`
- `${RUN_ID}/final_analysis/prefix_pair_candidate_delta.tsv`
- `${RUN_ID}/readout/summary.txt`
- `${RUN_ID}/readout/controlled_replay_readout_result.json`
- `${RUN_ID}/readout/controlled_replay_mode_delta_summary.tsv`
- `${RUN_ID}/readout/controlled_replay_pair_delta_summary.tsv`
- `${RUN_ID}/readout/controlled_replay_top_op_delta.tsv`
- `${RUN_ID}/readout/controlled_replay_ai_core_metric_delta.tsv`
- `${RUN_ID}/mail_attachment_candidates.tsv`

如果任何 TSV、JSON 或 log 超过 70KB，不要压缩或拆分回传；正文只写服务器路径、文件大小和关键行数。
