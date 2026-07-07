# P1.25 vLLM API msprof Request Device Aggregate Handoff

任务 ID：`runtime_vllm_api_msprof_request_device_aggregate_2026_0707_p1_025`

目标：P1.24 已证明 P1.23 raw msprof SQLite 仍在服务器 `/tmp` 下，并且 `msprof_prefix_cache_on` / `msprof_prefix_cache_off` 两侧都有 `direct_request_window_overlap`。本轮不再重复证明 SQLite 存在，也不重启 vLLM API server；直接在服务器本地只读解析 P1.23 raw profiler，把每个 vLLM API 请求窗口内的 device task、GE op type、AI Core metric 字段聚合到 request 级摘要，并输出 prefix-cache on/off 与 repeated-prefix pair 的候选差异表。

本轮是证据抽取和聚合，不是 benchmark、压测、吞吐比较、调度效率结论、prefix cache 命中率验收、瓶颈归因或优化建议。

## 通信前置要求

- 昇腾服务器每次邮件正文和每个附件都按不超过 70KB 处理。
- 不要通过邮件发送 raw profiler、完整日志、大 zip、模型输出、实验目录或其他大文件。
- 本轮产生的大规模数据保留在昇腾服务器本地；如需进一步分析，由外部开发者（本机）在下一轮 `通信模块/docs/developer-to-server.md` 中下达服务器本地分析任务。
- 邮件只回传任务状态、精简摘要、小清单、少量样例、70KB 以内的小附件和服务器侧路径。

## P1.24 已有依据

P1.24 `runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024` 已完成：

- `commit=b51e779aa5d78ab164b70b308f5204b5390129de`
- `pytest_exit_code=0`
- `reuse_analysis_exit_code=0`
- `rerun_required=0`
- `msprof_prefix_cache_on`: `request_count=16`、`successful_request_count=16`、`sqlite_db_count=17`、`sqlite_table_count=39`、`time_candidate_count=6`、`direct_overlap_candidate_count=3`、`time_alignment_status=direct_request_window_overlap`
- `msprof_prefix_cache_off`: `request_count=16`、`successful_request_count=16`、`sqlite_db_count=17`、`sqlite_table_count=39`、`time_candidate_count=6`、`direct_overlap_candidate_count=3`、`time_alignment_status=direct_request_window_overlap`
- 可直接重叠的 device 时间字段候选包括 `device_6/sqlite/ai_core_op_summary.db::task_time(start_time + duration_time)`、`device_6/sqlite/ascend_task.db::AscendTask(start_time + duration)`、`device_6/sqlite/op_counter.db::rts_task(start_time + duration)`。
- host `ApiData` 和合并库 `CANN_API/TASK(startNs/endNs)` 与 request monotonic ns 不在同一直接时间域；本轮不强行做 host/device 全时间基换算。

## 本轮必须回答

1. P1.23 raw msprof 目录是否仍在服务器 `/tmp` 下？
2. `tools/inference_contracts/analyze_msprof_request_device_aggregate.py` 能否读取 P1.23 vLLM API result JSON 与 raw SQLite？
3. `request_device_task_summary.tsv` 是否为 on/off 各 16 个成功请求输出 request 级 task row count、窗口内 start/end、`total_duration_time`、`total_wait_time`、stream/task 去重计数？
4. `request_device_task_type_summary.tsv` 是否输出 `task_time.task_type` 与 `AscendTask.device_task_type/host_task_type` 的 request 级分布？
5. `request_top_op_type_duration.tsv` 是否输出每个请求窗口内按 `total_duration_time` 排序的 top op type 候选？
6. `request_ai_core_metric_summary.tsv` 是否输出每个请求窗口内 `ai_core_metrics` 的 raw sum/avg 字段？
7. `prefix_cache_mode_request_delta.tsv` 是否按相同 `case_id` 输出 prefix-cache on/off 的 raw counter delta？
8. `prefix_pair_candidate_delta.tsv` 是否按 repeated-prefix group 输出第二个请求相对第一个请求的 raw counter delta？
9. `msprof_request_device_aggregate_result.json` 是否明确每个 mode 的 `aggregate_status`？
10. 是否遵守 70KB 通信上限，只回传摘要、小清单、服务器路径和 70KB 以内的小附件？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 优先复用 P1.23 raw msprof
- 只读解析 P1.23 raw msprof：
  - `/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_on_msprof`
  - `/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_off_msprof`
- 读取 P1.23 selected artifact：
  - `工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023`
- 读取 P1.24 selected artifact：
  - `工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024`
- 只输出聚合 TSV/JSON 和小摘要

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不改 driver、CANN、apt、dpkg、NPU runtime、vLLM 或 vLLM-Ascend 源码
- 不重启 vLLM API server
- 不运行新的模型推理请求
- 不运行 full 16K/32K 或 full `P010=43216` tokens
- 不运行多 worker 压测、benchmark、长时间服务或吞吐压测
- 不切换 Docker 推理栈
- 不在服务器上修改、提交或 push 项目代码
- 不回传 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息
- 不回传超过 70KB 的邮件正文或附件；大规模实验数据、raw profiler、完整日志和大 zip 必须留在服务器本地
- 不输出性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因或优化建议
- 不把 raw counter delta 解释为性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因或优化建议

如果 P1.23 raw profiler 目录已经被清理，本轮不要偷偷重跑 vLLM；直接把 `aggregate_status=missing_raw_msprof` 和缺失路径回传。

## 建议执行命令

在服务器上执行：

```bash
set -u

cd /data/node0_disk1/liguowei/AK-Infer-Lab
git pull --ff-only

RUN_ID=runtime_vllm_api_msprof_request_device_aggregate_2026_0707_p1_025
SOURCE_RUN_ID=runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023
WINDOW_RUN_ID=runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024
SOURCE_ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${SOURCE_RUN_ID}"
WINDOW_ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${WINDOW_RUN_ID}"
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
FINAL_ANALYSIS_DIR="${ARTIFACT_DIR}/final_analysis"
PYTHON_BIN="${PYTHON_BIN:-/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab/bin/python}"
MSPROF_ROOT_ON="/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_on_msprof"
MSPROF_ROOT_OFF="/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_off_msprof"

mkdir -p "${ARTIFACT_DIR}" "${FINAL_ANALYSIS_DIR}"

{
  echo "run_id=${RUN_ID}"
  echo "source_run_id=${SOURCE_RUN_ID}"
  echo "window_run_id=${WINDOW_RUN_ID}"
  echo "commit=$(git rev-parse HEAD)"
  echo "timestamp=$(date -Is)"
  echo "PYTHON_BIN=${PYTHON_BIN}"
  echo "SOURCE_ARTIFACT_DIR=${SOURCE_ARTIFACT_DIR}"
  echo "WINDOW_ARTIFACT_DIR=${WINDOW_ARTIFACT_DIR}"
  echo "MSPROF_ROOT_ON=${MSPROF_ROOT_ON}"
  echo "MSPROF_ROOT_OFF=${MSPROF_ROOT_OFF}"
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
if [ "${missing_raw}" -eq 0 ]; then
  "${PYTHON_BIN}" tools/inference_contracts/analyze_msprof_request_device_aggregate.py \
    --run-id "${RUN_ID}" \
    --source-artifact-dir "${SOURCE_ARTIFACT_DIR}" \
    --artifact-dir "${FINAL_ANALYSIS_DIR}" \
    --msprof-root-on "${MSPROF_ROOT_ON}" \
    --msprof-root-off "${MSPROF_ROOT_OFF}" \
    > "${ARTIFACT_DIR}/request_device_aggregate.log" 2>&1
  analysis_exit_code=$?
else
  {
    echo "## run_context"
    echo "run_id=${RUN_ID}"
    echo "overall_status=failed"
    echo ""
    echo "## mode_summaries"
    echo "missing_raw_msprof"
  } > "${FINAL_ANALYSIS_DIR}/summary.txt"
  cat > "${FINAL_ANALYSIS_DIR}/msprof_request_device_aggregate_result.json" <<'JSON'
{
  "overall_status": "failed",
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
  echo "request_device_aggregate_exit_code=${analysis_exit_code}"
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
    "pytest.log",
    "request_device_aggregate.log",
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
echo "pytest_exit_code=${pytest_exit_code}"
echo "missing_raw=${missing_raw}"
echo "request_device_aggregate_exit_code=${analysis_exit_code}"
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
P1.25 vLLM API msprof request-device aggregate 已完成/失败。

run_id: runtime_vllm_api_msprof_request_device_aggregate_2026_0707_p1_025
commit: <git rev-parse HEAD>
artifact_dir: 工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_request_device_aggregate_2026_0707_p1_025
pytest_exit_code: <...>
missing_raw: <0 或 1>
request_device_aggregate_exit_code: <...>

mode_summaries:
- msprof_prefix_cache_on: aggregate_status=<...>, request_device_summary_rows=<...>, top_op_summary_rows=<...>, metric_summary_rows=<...>
- msprof_prefix_cache_off: aggregate_status=<...>, request_device_summary_rows=<...>, top_op_summary_rows=<...>, metric_summary_rows=<...>

请见正文摘要；只附 70KB 以内的小文件。大规模数据、raw profiler、完整日志和大 zip 已留在服务器。
```

附件只允许包含 `mail_attachment_candidates.tsv` 中 `mail_ok=true` 且不超过 70KB 的小文件。优先考虑：

- `${RUN_ID}/summary.txt`
- `${RUN_ID}/run_context.txt`
- `${RUN_ID}/pytest.log`
- `${RUN_ID}/final_analysis/summary.txt`
- `${RUN_ID}/final_analysis/request_device_task_summary.tsv`
- `${RUN_ID}/final_analysis/request_device_task_type_summary.tsv`
- `${RUN_ID}/final_analysis/request_top_op_type_duration.tsv`
- `${RUN_ID}/final_analysis/request_ai_core_metric_summary.tsv`
- `${RUN_ID}/final_analysis/prefix_cache_mode_request_delta.tsv`
- `${RUN_ID}/final_analysis/prefix_pair_candidate_delta.tsv`
- `${RUN_ID}/final_analysis/msprof_request_device_aggregate_result.json`
- `${RUN_ID}/mail_attachment_candidates.tsv`

如果任何文件超过 70KB，不要强行压缩、拆分或通过多封邮件发送；只在正文说明服务器路径、文件大小和建议的后续服务器本地分析任务。

## 判读边界

- `total_duration_time`、`total_wait_time`、metric sum/avg 和 delta 都只是 raw profiler counter 聚合，不是吞吐 benchmark。
- on/off delta 只说明两次 profiled run 的 request-window counter 差异，不单独证明 prefix cache hit 或优化收益。
- repeated-prefix pair delta 只说明同一 mode 内第一个/第二个请求的 counter 差异，不单独证明缓存命中。
- 如果两个 mode 都输出 `aggregate_status=request_device_aggregate_available`，下一轮可以进入 P1.26：更长 decode 或更大 continuous workload 的 profiled run，并把 P1.25 聚合器作为固定后处理。
