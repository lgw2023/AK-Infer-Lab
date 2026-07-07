# P1.25b vLLM API msprof Request Device Aggregate Fast Handoff

任务 ID：`runtime_vllm_api_msprof_request_device_aggregate_fast_2026_0707_p1_025b`

目标：P1.25 原离线 SQLite 聚合已运行超过 3 小时，说明第一版逐 request 重复扫描和 join 的 SQL 路径过慢。本轮停止仍在运行的旧 P1.25 离线聚合进程，拉取加速版聚合器，只读复用 P1.23 raw msprof SQLite，在服务器本地重新生成 request 级 device task、op type、AI Core metric 聚合摘要。

本轮仍是离线证据抽取和聚合，不是 benchmark、压测、吞吐比较、调度效率结论、prefix cache 命中率验收、瓶颈归因或优化建议。

## 加速策略

- `tools/inference_contracts/analyze_msprof_request_device_aggregate.py` 已改为 `bulk_temp_window_join_parallel_modes`。
- 每个 mode 先建立 `request_windows` 临时表。
- 每个 mode 只把 request-window overlap 的 `task_time` / `AscendTask` 行 materialize 到临时表一次，再从临时表生成 summary、task type、top op type 和 metric 聚合。
- `ge_summary` 与 `ai_core_metrics` 会复制为临时 join 表并建立临时索引；不修改 raw msprof SQLite。
- prefix-cache on/off 两个 mode 使用 `--workers 2` 并行聚合。
- 如果 full 聚合仍在 45 分钟内无法完成，本轮自动切到 `--skip-heavy-joins` 兜底模式：跳过 `ge_summary` top-op 和 `ai_core_metrics` metric join，优先返回 request-level task summary 与 task type 分布，避免再次空等。

## 必须回答

1. 是否发现仍在运行的旧 P1.25 聚合进程？
2. 如果发现，是否已记录旧进程 `ps` 状态和旧 log tail，并仅终止旧的离线聚合进程？
3. `git pull --ff-only` 后的 commit 是什么？
4. 加速版本地测试是否通过？
5. P1.23 raw msprof on/off 目录是否仍存在？
6. 加速版 full 聚合是否在 45 分钟 timeout 内完成？
7. 如果 full 聚合失败或 timeout，`--skip-heavy-joins` 兜底聚合是否完成？
8. on/off 两个 mode 的 `aggregate_status`、`elapsed_sec`、`request_device_summary_rows`、`top_op_summary_rows`、`metric_summary_rows`、`heavy_joins_skipped` 分别是多少？
9. 是否遵守 70KB 通信上限？

## 执行边界

允许：

- 记录旧 P1.25 离线聚合进程状态。
- 如果旧 P1.25 `analyze_msprof_request_device_aggregate.py` 仍在运行，终止该旧离线分析进程。
- `git pull --ff-only`。
- `python -m pytest tests/inference_contracts -q`。
- 使用当前 conda 环境、Python 和 SQLite。
- 只读解析 P1.23 raw profiler SQLite。
- 创建 SQLite 临时表和临时索引。
- 如果 full 聚合 timeout，运行 `--skip-heavy-joins` 基础聚合兜底。
- 输出聚合 TSV/JSON、小摘要和小日志。

禁止：

- 不安装、升级、卸载或修复任何包。
- 不创建新 conda 环境。
- 不改 driver、CANN、apt、dpkg、NPU runtime、vLLM 或 vLLM-Ascend 源码。
- 不重启 vLLM API server。
- 不运行新的模型推理请求。
- 不运行 full 16K/32K 或 full `P010=43216` tokens。
- 不运行多 worker 压测、benchmark、长时间服务或吞吐压测。
- 不切换 Docker 推理栈。
- 不在服务器上修改、提交或 push 项目代码。
- 不终止非 P1.25 离线聚合进程。
- 不回传 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。
- 不回传超过 70KB 的邮件正文或附件；大规模实验数据、raw profiler、完整日志和大 zip 必须留在服务器本地。
- 不把 raw counter delta 解释为性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因或优化建议。

## 建议执行命令

在服务器上执行：

```bash
set -u

cd /data/node0_disk1/liguowei/AK-Infer-Lab

RUN_ID=runtime_vllm_api_msprof_request_device_aggregate_fast_2026_0707_p1_025b
PREV_RUN_ID=runtime_vllm_api_msprof_request_device_aggregate_2026_0707_p1_025
SOURCE_RUN_ID=runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023
WINDOW_RUN_ID=runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024
SOURCE_ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${SOURCE_RUN_ID}"
WINDOW_ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${WINDOW_RUN_ID}"
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
OLD_ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${PREV_RUN_ID}"
FINAL_ANALYSIS_DIR="${ARTIFACT_DIR}/final_analysis"
PYTHON_BIN="${PYTHON_BIN:-/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab/bin/python}"
MSPROF_ROOT_ON="/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_on_msprof"
MSPROF_ROOT_OFF="/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_off_msprof"

mkdir -p "${ARTIFACT_DIR}" "${FINAL_ANALYSIS_DIR}"

OLD_STATUS_LOG="${ARTIFACT_DIR}/old_p1_25_process_status.txt"
{
  echo "timestamp_before_stop=$(date -Is)"
  echo "old_run_id=${PREV_RUN_ID}"
  echo "old_artifact_dir=${OLD_ARTIFACT_DIR}"
  echo ""
  echo "## matching analyzer processes before stop"
} > "${OLD_STATUS_LOG}"

pgrep -af "analyze_msprof_request_device_aggregate.py" \
  | awk '/runtime_vllm_api_msprof_request_device_aggregate_2026_0707_p1_025/ && !/p1_025b/ {print $1}' \
  > "${ARTIFACT_DIR}/old_p1_25_pids.txt" || true
OLD_PIDS="$(tr '\n' ' ' < "${ARTIFACT_DIR}/old_p1_25_pids.txt")"
OLD_PROCESS_FOUND=0

if [ -n "${OLD_PIDS}" ]; then
  OLD_PROCESS_FOUND=1
  ps -fp ${OLD_PIDS} >> "${OLD_STATUS_LOG}" 2>&1 || true
  if [ -f "${OLD_ARTIFACT_DIR}/request_device_aggregate.log" ]; then
    {
      echo ""
      echo "## old request_device_aggregate.log tail"
      tail -200 "${OLD_ARTIFACT_DIR}/request_device_aggregate.log"
    } >> "${OLD_STATUS_LOG}" 2>&1 || true
  fi
  kill -TERM ${OLD_PIDS} >> "${OLD_STATUS_LOG}" 2>&1 || true
  sleep 10
  for pid in ${OLD_PIDS}; do
    if kill -0 "${pid}" 2>/dev/null; then
      echo "pid ${pid} still alive after TERM; sending KILL" >> "${OLD_STATUS_LOG}"
      kill -KILL "${pid}" >> "${OLD_STATUS_LOG}" 2>&1 || true
    fi
  done
else
  echo "no old P1.25 analyzer process found" >> "${OLD_STATUS_LOG}"
fi

git pull --ff-only

{
  echo "run_id=${RUN_ID}"
  echo "previous_run_id=${PREV_RUN_ID}"
  echo "source_run_id=${SOURCE_RUN_ID}"
  echo "window_run_id=${WINDOW_RUN_ID}"
  echo "commit=$(git rev-parse HEAD)"
  echo "timestamp=$(date -Is)"
  echo "PYTHON_BIN=${PYTHON_BIN}"
  echo "SOURCE_ARTIFACT_DIR=${SOURCE_ARTIFACT_DIR}"
  echo "WINDOW_ARTIFACT_DIR=${WINDOW_ARTIFACT_DIR}"
  echo "MSPROF_ROOT_ON=${MSPROF_ROOT_ON}"
  echo "MSPROF_ROOT_OFF=${MSPROF_ROOT_OFF}"
  echo "old_p1_25_process_found=${OLD_PROCESS_FOUND}"
  echo "workers=2"
  echo "full_timeout_minutes=45"
  echo "fallback_timeout_minutes=15"
} > "${ARTIFACT_DIR}/run_context.txt"

"${PYTHON_BIN}" -m pytest tests/inference_contracts -q \
  > "${ARTIFACT_DIR}/pytest.log" 2>&1
pytest_exit_code=$?
echo "${pytest_exit_code}" > "${ARTIFACT_DIR}/pytest_exit_code.txt"

missing_raw=0
if [ ! -d "${MSPROF_ROOT_ON}" ]; then
  echo "missing_raw_msprof=${MSPROF_ROOT_ON}" >> "${ARTIFACT_DIR}/run_context.txt"
  missing_raw=1
fi
if [ ! -d "${MSPROF_ROOT_OFF}" ]; then
  echo "missing_raw_msprof=${MSPROF_ROOT_OFF}" >> "${ARTIFACT_DIR}/run_context.txt"
  missing_raw=1
fi

analysis_exit_code=99
analysis_mode="not_started"
full_analysis_exit_code=99
fallback_analysis_exit_code=99
if [ "${missing_raw}" -eq 0 ]; then
  analysis_mode="full"
  if command -v timeout >/dev/null 2>&1; then
    timeout 45m "${PYTHON_BIN}" tools/inference_contracts/analyze_msprof_request_device_aggregate.py \
      --run-id "${RUN_ID}" \
      --source-artifact-dir "${SOURCE_ARTIFACT_DIR}" \
      --artifact-dir "${FINAL_ANALYSIS_DIR}" \
      --msprof-root-on "${MSPROF_ROOT_ON}" \
      --msprof-root-off "${MSPROF_ROOT_OFF}" \
      --workers 2 \
      > "${ARTIFACT_DIR}/request_device_aggregate_fast.log" 2>&1
    full_analysis_exit_code=$?
  else
    "${PYTHON_BIN}" tools/inference_contracts/analyze_msprof_request_device_aggregate.py \
      --run-id "${RUN_ID}" \
      --source-artifact-dir "${SOURCE_ARTIFACT_DIR}" \
      --artifact-dir "${FINAL_ANALYSIS_DIR}" \
      --msprof-root-on "${MSPROF_ROOT_ON}" \
      --msprof-root-off "${MSPROF_ROOT_OFF}" \
      --workers 2 \
      > "${ARTIFACT_DIR}/request_device_aggregate_fast.log" 2>&1
    full_analysis_exit_code=$?
  fi
  analysis_exit_code="${full_analysis_exit_code}"

  if [ "${full_analysis_exit_code}" -ne 0 ]; then
    {
      echo "full_analysis_exit_code=${full_analysis_exit_code}"
      echo "fallback_reason=full_aggregate_failed_or_timed_out"
    } >> "${ARTIFACT_DIR}/run_context.txt"
    rm -rf "${FINAL_ANALYSIS_DIR}"
    mkdir -p "${FINAL_ANALYSIS_DIR}"
    analysis_mode="skip_heavy_joins_fallback"
    if command -v timeout >/dev/null 2>&1; then
      timeout 15m "${PYTHON_BIN}" tools/inference_contracts/analyze_msprof_request_device_aggregate.py \
        --run-id "${RUN_ID}" \
        --source-artifact-dir "${SOURCE_ARTIFACT_DIR}" \
        --artifact-dir "${FINAL_ANALYSIS_DIR}" \
        --msprof-root-on "${MSPROF_ROOT_ON}" \
        --msprof-root-off "${MSPROF_ROOT_OFF}" \
        --workers 2 \
        --skip-heavy-joins \
        > "${ARTIFACT_DIR}/request_device_aggregate_fast_fallback.log" 2>&1
      fallback_analysis_exit_code=$?
    else
      "${PYTHON_BIN}" tools/inference_contracts/analyze_msprof_request_device_aggregate.py \
        --run-id "${RUN_ID}" \
        --source-artifact-dir "${SOURCE_ARTIFACT_DIR}" \
        --artifact-dir "${FINAL_ANALYSIS_DIR}" \
        --msprof-root-on "${MSPROF_ROOT_ON}" \
        --msprof-root-off "${MSPROF_ROOT_OFF}" \
        --workers 2 \
        --skip-heavy-joins \
        > "${ARTIFACT_DIR}/request_device_aggregate_fast_fallback.log" 2>&1
      fallback_analysis_exit_code=$?
    fi
    analysis_exit_code="${fallback_analysis_exit_code}"
  fi
else
  {
    echo "## run_context"
    echo "run_id=${RUN_ID}"
    echo "overall_status=failed"
    echo "aggregation_strategy=bulk_temp_window_join_parallel_modes"
    echo ""
    echo "## mode_summaries"
    echo "missing_raw_msprof"
  } > "${FINAL_ANALYSIS_DIR}/summary.txt"
  cat > "${FINAL_ANALYSIS_DIR}/msprof_request_device_aggregate_result.json" <<'JSON'
{
  "overall_status": "failed",
  "aggregation_strategy": "bulk_temp_window_join_parallel_modes",
  "policy": "evidence_extraction_only_no_benchmark_or_bottleneck_claim",
  "mode_summaries": [
    {"aggregate_status": "missing_raw_msprof"}
  ]
}
JSON
fi

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt"
  echo "pytest_exit_code=${pytest_exit_code}"
  echo "missing_raw=${missing_raw}"
  echo "analysis_mode=${analysis_mode}"
  echo "full_analysis_exit_code=${full_analysis_exit_code}"
  echo "fallback_analysis_exit_code=${fallback_analysis_exit_code}"
  echo "request_device_aggregate_fast_exit_code=${analysis_exit_code}"
  echo ""
  echo "## old_p1_25_process_status"
  sed -n '1,120p' "${OLD_STATUS_LOG}" || true
  echo ""
  echo "## final_analysis_summary"
  if [ -f "${FINAL_ANALYSIS_DIR}/summary.txt" ]; then
    cat "${FINAL_ANALYSIS_DIR}/summary.txt"
  else
    echo "missing final_analysis/summary.txt"
  fi
} > "${ARTIFACT_DIR}/summary.txt"

"${PYTHON_BIN}" - <<'PY' "${ARTIFACT_DIR}"
from pathlib import Path
import sys

artifact_dir = Path(sys.argv[1])
candidate_relpaths = [
    "summary.txt",
    "run_context.txt",
    "old_p1_25_process_status.txt",
    "pytest.log",
    "request_device_aggregate_fast.log",
    "request_device_aggregate_fast_fallback.log",
    "final_analysis/summary.txt",
    "final_analysis/request_device_task_summary.tsv",
    "final_analysis/request_device_task_type_summary.tsv",
    "final_analysis/request_top_op_type_duration.tsv",
    "final_analysis/request_ai_core_metric_summary.tsv",
    "final_analysis/prefix_cache_mode_request_delta.tsv",
    "final_analysis/prefix_pair_candidate_delta.tsv",
    "final_analysis/msprof_request_device_aggregate_result.json",
]
lines = ["path\tsize_bytes\tmail_ok"]
for relpath in candidate_relpaths:
    path = artifact_dir / relpath
    if not path.exists():
        continue
    size = path.stat().st_size
    lines.append(f"{path}\t{size}\t{str(size <= 70 * 1024).lower()}")
(artifact_dir / "mail_attachment_candidates.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

echo "artifact_dir=${ARTIFACT_DIR}"
echo "old_p1_25_process_found=${OLD_PROCESS_FOUND}"
echo "pytest_exit_code=${pytest_exit_code}"
echo "missing_raw=${missing_raw}"
echo "analysis_mode=${analysis_mode}"
echo "full_analysis_exit_code=${full_analysis_exit_code}"
echo "fallback_analysis_exit_code=${fallback_analysis_exit_code}"
echo "request_device_aggregate_fast_exit_code=${analysis_exit_code}"
echo "mail_attachment_candidates=${ARTIFACT_DIR}/mail_attachment_candidates.tsv"

if [ "${pytest_exit_code}" -ne 0 ]; then
  exit "${pytest_exit_code}"
fi
if [ "${analysis_exit_code}" -ne 0 ]; then
  exit "${analysis_exit_code}"
fi
```

## 回传要求

邮件正文请包含：

```text
P1.25b vLLM API msprof request-device aggregate fast 已完成/失败。

run_id: runtime_vllm_api_msprof_request_device_aggregate_fast_2026_0707_p1_025b
previous_run_id: runtime_vllm_api_msprof_request_device_aggregate_2026_0707_p1_025
commit: <git rev-parse HEAD>
artifact_dir: 工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_request_device_aggregate_fast_2026_0707_p1_025b
old_p1_25_process_found: <0 或 1>
pytest_exit_code: <...>
missing_raw: <0 或 1>
request_device_aggregate_fast_exit_code: <...>
aggregation_strategy: bulk_temp_window_join_parallel_modes
workers: 2
analysis_mode: <full 或 skip_heavy_joins_fallback>
full_analysis_exit_code: <...>
fallback_analysis_exit_code: <...>

mode_summaries:
- msprof_prefix_cache_on: aggregate_status=<...>, elapsed_sec=<...>, request_device_summary_rows=<...>, top_op_summary_rows=<...>, metric_summary_rows=<...>, heavy_joins_skipped=<0 或 1>
- msprof_prefix_cache_off: aggregate_status=<...>, elapsed_sec=<...>, request_device_summary_rows=<...>, top_op_summary_rows=<...>, metric_summary_rows=<...>, heavy_joins_skipped=<0 或 1>

边界：未重启 vLLM API server，未运行新模型请求，未安装或修复包，未修改 raw msprof SQLite，未输出 benchmark/吞吐/命中率/瓶颈结论。
```

附件只允许包含 `mail_attachment_candidates.tsv` 中 `mail_ok=true` 且不超过 70KB 的小文件。优先考虑：

- `${RUN_ID}/summary.txt`
- `${RUN_ID}/run_context.txt`
- `${RUN_ID}/old_p1_25_process_status.txt`
- `${RUN_ID}/pytest.log`
- `${RUN_ID}/final_analysis/summary.txt`
- `${RUN_ID}/final_analysis/msprof_request_device_aggregate_result.json`
- `${RUN_ID}/mail_attachment_candidates.tsv`

如果任何 TSV 或 log 超过 70KB，不要压缩或拆分回传；正文只写服务器路径、文件大小和关键行数。

## 判读边界

- `total_duration_time`、`total_wait_time`、metric sum/avg 和 delta 都只是 raw profiler counter 聚合，不是吞吐 benchmark。
- on/off delta 只说明两次 profiled run 的 request-window counter 差异，不单独证明 prefix cache hit 或优化收益。
- repeated-prefix pair delta 只说明同一 mode 内第一个/第二个请求的 counter 差异，不单独证明缓存命中。
- 如果 P1.25b 成功，下一轮再决定是把聚合器接入统一事件模型，还是进入更长 decode / 更大 workload 的 profiled run。
