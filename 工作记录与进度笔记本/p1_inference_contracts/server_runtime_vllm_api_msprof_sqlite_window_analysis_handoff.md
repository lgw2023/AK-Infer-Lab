# P1.24 vLLM API msprof SQLite Window Analysis Handoff

任务 ID：`runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024`

目标：P1.23 已证明 vLLM API `continuous16_mixed` on/off 两轮可以在 `msprof --msproftx=on` 下完成，并且 raw profiler 中有 host、device、sqlite 和 timebase 候选。本轮不再做更小 smoke，而是把 P1.23 的 profiler coverage 证据推进到可解释的 SQLite/request-window 摘要：读取每个请求的 `request_start_ns` / `response_end_ns`，枚举 msprof SQLite 表和时间字段，输出请求窗口与 profiler 时间字段的直接重叠候选、表级 row count、op/task 类型分布和 mode 级对齐状态。

本轮仍是证据抽取，不是 benchmark、压测、吞吐比较、调度效率结论、prefix cache 命中率验收、瓶颈归因或优化建议。

## 通信前置要求

- 昇腾服务器每次邮件正文和每个附件都按不超过 70KB 处理。
- 不要通过邮件发送 raw profiler、完整日志、大 zip、模型输出、实验目录或其他大文件。
- 本轮产生的大规模数据保留在昇腾服务器本地；如需进一步分析，由外部开发者（本机）在下一轮 `通信模块/docs/developer-to-server.md` 中下达服务器本地分析任务。
- 邮件只回传任务状态、精简摘要、小清单、少量样例、70KB 以内的小附件和服务器侧路径。

## P1.23 已有依据

P1.23 `runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023` 已完成：

- `commit=6f2e3eb0d5cda17fa1558629bc847ab084531f18`
- `pytest_exit_code=0`
- `msprof_prefix_cache_on_exit_code=0`
- `msprof_prefix_cache_off_exit_code=0`
- 两轮均为 `case_plan=continuous16_mixed`、`max_model_len=9216`
- 两轮均 `request_count=16`、`success_case_count=16`、`failed_case_count=0`
- 两轮均 `client_overlap_candidate_count=120`
- 两轮均 `trace_validation_errors=0`
- `msprof_prefix_cache_on`: `server_stats_sample_count=1`、`max_running=13`、`max_waiting=3`、`max_kv_cache_usage_pct=7.0`、`max_prefix_cache_hit_rate_pct=51.4`、`msprof_file_count=582`、`msprof_sqlite_count=17`、`msprof_host_dir_count=1`、`msprof_device_dir_count=1`、`msprof_timebase_candidate_count=56`
- `msprof_prefix_cache_off`: `server_stats_sample_count=2`、`max_running=10`、`max_waiting=4`、`max_kv_cache_usage_pct=7.1`、`max_prefix_cache_hit_rate_pct=0.0`、`msprof_file_count=808`、`msprof_sqlite_count=17`、`msprof_host_dir_count=1`、`msprof_device_dir_count=1`、`msprof_timebase_candidate_count=56`

P1.23 附件只回传了 schema/timebase/file-list 等 selected artifacts，没有回传完整 raw SQLite DB。本轮优先复用 P1.23 raw msprof 服务器路径；如果 raw profiler 目录不存在，就用同一负载重跑并立即分析。

## 本轮必须回答

1. P1.23 raw msprof 目录是否还在服务器 `/tmp` 下？
2. 如果 raw 存在，`tools/inference_contracts/analyze_msprof_sqlite_windows.py` 能否直接读取 P1.23 artifact 和 raw SQLite 并生成分析摘要？
3. 如果 raw 不存在，是否能重跑同一 `continuous16_mixed` on/off profiled workload 并在同一轮生成分析摘要？
4. `request_window_summary.tsv` 是否列出 16 个请求窗口、请求 token 数、prefix group 和 client wall time？
5. `profiler_sqlite_table_inventory.tsv` 是否列出每个 mode 的 SQLite DB、table、row count 和字段清单？
6. `profiler_time_range_summary.tsv` 是否列出可用时间字段候选、min/max、与请求窗口重叠的请求数和 row 数？
7. `request_profiler_overlap_summary.tsv` 是否给出每个请求窗口与每个时间候选表的重叠 row count？
8. `profiler_group_count_summary.tsv` 是否给出 op/task 类型分布候选？
9. `msprof_sqlite_window_analysis_result.json` 是否给出每个 mode 的 `time_alignment_status`，并明确是 `direct_request_window_overlap`、`profiler_tables_available_but_no_direct_window_overlap` 还是 `missing_msprof_sqlite`？
10. 是否遵守 70KB 通信上限，只回传摘要、小清单、服务器路径和 70KB 以内的小附件？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`
- source `/usr/local/Ascend/nnal/atb/set_env.sh`
- 使用当前环境已有 `vllm`、`vllm_ascend`、`msprof`
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 优先复用 P1.23 raw msprof：`/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_on_msprof` 与 `/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_off_msprof`
- 如果 raw profiler 目录不存在，则重跑同一 `continuous16_mixed` on/off profiled workload
- 只读解析 raw profiler SQLite，输出聚合 TSV/JSON；不要回传完整 raw profiler DB
- 仅回传 70KB 以内的小文件，其他 artifact 留在服务器本地并在邮件正文列路径

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不改 driver、CANN、apt、dpkg、NPU runtime、vLLM 或 vLLM-Ascend 源码
- 不静默降低 `max_model_len`、不删减 case、不降低输入 cap、不缩短 output token
- 不运行 full 16K/32K 或 full `P010=43216` tokens
- 不运行多 worker 压测、benchmark、长时间服务或吞吐压测
- 不切换 Docker 推理栈
- 不在服务器上修改、提交或 push 项目代码
- 不回传 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息
- 不回传超过 70KB 的邮件正文或附件；大规模实验数据、raw profiler、完整日志和大 zip 必须留在服务器本地
- 不输出性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因或优化建议

## 建议执行命令

在服务器上执行：

```bash
set -u

cd /data/node0_disk1/liguowei/AK-Infer-Lab
git pull --ff-only

RUN_ID=runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024
SOURCE_RUN_ID=runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023
SOURCE_ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${SOURCE_RUN_ID}"
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
MODEL_PATH=/data/node0_disk1/Public/Qwen3.5-4B
PYTHON_BIN="${PYTHON_BIN:-/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab/bin/python}"
DEVICE_ID="${ASCEND_RT_VISIBLE_DEVICES:-6}"

mkdir -p "${ARTIFACT_DIR}"

{
  echo "run_id=${RUN_ID}"
  echo "source_run_id=${SOURCE_RUN_ID}"
  echo "commit=$(git rev-parse HEAD)"
  echo "timestamp=$(date -Is)"
  echo "MODEL_PATH=${MODEL_PATH}"
  echo "PYTHON_BIN=${PYTHON_BIN}"
  echo "ASCEND_RT_VISIBLE_DEVICES=${DEVICE_ID}"
} > "${ARTIFACT_DIR}/run_context.txt"

if [ -f /usr/local/Ascend/cann-9.0.0/set_env.sh ]; then
  # shellcheck disable=SC1091
  source /usr/local/Ascend/cann-9.0.0/set_env.sh
fi
if [ -f /usr/local/Ascend/nnal/atb/set_env.sh ]; then
  # shellcheck disable=SC1091
  source /usr/local/Ascend/nnal/atb/set_env.sh
fi

export ASCEND_RT_VISIBLE_DEVICES="${DEVICE_ID}"
export VLLM_PLUGINS=ascend
export VLLM_USE_V1="${VLLM_USE_V1:-0}"
export VLLM_WORKER_MULTIPROC_METHOD="${VLLM_WORKER_MULTIPROC_METHOD:-spawn}"
export AK_VLLM_MAX_MODEL_LEN=9216
export AK_VLLM_API_CASE_PLAN=continuous16_mixed

"${PYTHON_BIN}" -m pytest tests/inference_contracts -q \
  > "${ARTIFACT_DIR}/pytest.log" 2>&1
pytest_exit_code=$?
echo "${pytest_exit_code}" > "${ARTIFACT_DIR}/pytest_exit_code.txt"

analysis_success() {
  local result_path="$1"
  "${PYTHON_BIN}" - "${result_path}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(1)
data = json.loads(path.read_text(encoding="utf-8"))
if data.get("overall_status") != "success":
    raise SystemExit(1)
for row in data.get("mode_summaries", []):
    if int(row.get("sqlite_db_count") or 0) <= 0:
        raise SystemExit(1)
raise SystemExit(0)
PY
}

REUSE_ANALYSIS_DIR="${ARTIFACT_DIR}/reuse_p1_023_analysis"
mkdir -p "${REUSE_ANALYSIS_DIR}"

"${PYTHON_BIN}" tools/inference_contracts/analyze_msprof_sqlite_windows.py \
  --run-id "${RUN_ID}_reuse_p1_023" \
  --source-artifact-dir "${SOURCE_ARTIFACT_DIR}" \
  --artifact-dir "${REUSE_ANALYSIS_DIR}" \
  > "${ARTIFACT_DIR}/reuse_analysis.log" 2>&1
reuse_analysis_exit_code=$?
echo "${reuse_analysis_exit_code}" > "${ARTIFACT_DIR}/reuse_analysis_exit_code.txt"

final_analysis_dir="${REUSE_ANALYSIS_DIR}"
rerun_required=0
if ! analysis_success "${REUSE_ANALYSIS_DIR}/msprof_sqlite_window_analysis_result.json"; then
  rerun_required=1
fi
echo "${rerun_required}" > "${ARTIFACT_DIR}/rerun_required.txt"

run_profiled_mode() {
  local mode="$1"
  local prefix_arg="$2"
  local mode_dir="${ARTIFACT_DIR}/rerun_source/${mode}"
  local msprof_out="/tmp/${RUN_ID}_${mode}_msprof"
  rm -rf "${msprof_out}"
  mkdir -p "${mode_dir}" "${msprof_out}"

  {
    echo "mode=${mode}"
    echo "prefix_arg=${prefix_arg}"
    echo "msprof_out=${msprof_out}"
    echo "case_plan=continuous16_mixed"
    echo "max_model_len=9216"
  } > "${mode_dir}/run_context.txt"

  msprof \
    --output "${msprof_out}" \
    --msproftx=on \
    --storage-limit=4096 \
    "${PYTHON_BIN}" tools/inference_contracts/run_vllm_api_concurrency_smoke.py \
      --run-id "${RUN_ID}_${mode}" \
      --artifact-dir "${mode_dir}/vllm" \
      --model-path "${MODEL_PATH}" \
      --case-plan continuous16_mixed \
      --max-model-len 9216 \
      "${prefix_arg}" \
      > "${mode_dir}/msprof_vllm_api.log" 2>&1

  local exit_code=$?
  echo "${exit_code}" > "${mode_dir}/msprof_exit_code.txt"
  find "${msprof_out}" -type f -print 2>/dev/null | sort > "${mode_dir}/msprof_output_files.txt" || true
  du -ah "${msprof_out}" 2>/dev/null | sort -h > "${mode_dir}/msprof_du.txt" || true
}

if [ "${rerun_required}" = "1" ]; then
  run_profiled_mode "msprof_prefix_cache_on" "--enable-prefix-caching"
  run_profiled_mode "msprof_prefix_cache_off" "--no-enable-prefix-caching"

  RERUN_ANALYSIS_DIR="${ARTIFACT_DIR}/rerun_analysis"
  mkdir -p "${RERUN_ANALYSIS_DIR}"
  "${PYTHON_BIN}" tools/inference_contracts/analyze_msprof_sqlite_windows.py \
    --run-id "${RUN_ID}_rerun" \
    --source-artifact-dir "${ARTIFACT_DIR}/rerun_source" \
    --artifact-dir "${RERUN_ANALYSIS_DIR}" \
    > "${ARTIFACT_DIR}/rerun_analysis.log" 2>&1
  rerun_analysis_exit_code=$?
  echo "${rerun_analysis_exit_code}" > "${ARTIFACT_DIR}/rerun_analysis_exit_code.txt"
  final_analysis_dir="${RERUN_ANALYSIS_DIR}"
fi

mkdir -p "${ARTIFACT_DIR}/final_analysis"
cp -p "${final_analysis_dir}"/* "${ARTIFACT_DIR}/final_analysis/" 2>/dev/null || true

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt"
  echo "pytest_exit_code=${pytest_exit_code}"
  echo "reuse_analysis_exit_code=${reuse_analysis_exit_code}"
  echo "rerun_required=${rerun_required}"
  if [ -f "${ARTIFACT_DIR}/rerun_analysis_exit_code.txt" ]; then
    echo "rerun_analysis_exit_code=$(cat "${ARTIFACT_DIR}/rerun_analysis_exit_code.txt")"
  fi
  echo ""
  echo "## final_analysis_summary"
  if [ -f "${ARTIFACT_DIR}/final_analysis/summary.txt" ]; then
    cat "${ARTIFACT_DIR}/final_analysis/summary.txt"
  fi
} > "${ARTIFACT_DIR}/summary.txt"

python - "${ARTIFACT_DIR}" <<'PY'
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
limit_bytes = 70 * 1024
preferred = [
    artifact_dir / "summary.txt",
    artifact_dir / "run_context.txt",
    artifact_dir / "pytest.log",
    artifact_dir / "reuse_analysis.log",
    artifact_dir / "rerun_analysis.log",
    artifact_dir / "final_analysis" / "request_window_summary.tsv",
    artifact_dir / "final_analysis" / "profiler_sqlite_table_inventory.tsv",
    artifact_dir / "final_analysis" / "profiler_time_range_summary.tsv",
    artifact_dir / "final_analysis" / "request_profiler_overlap_summary.tsv",
    artifact_dir / "final_analysis" / "profiler_group_count_summary.tsv",
    artifact_dir / "final_analysis" / "msprof_sqlite_window_analysis_result.json",
]
for path in sorted((artifact_dir / "rerun_source").rglob("*")) if (artifact_dir / "rerun_source").exists() else []:
    if path.is_file() and path.name in {
        "msprof_vllm_api.log",
        "msprof_output_files.txt",
        "msprof_du.txt",
        "vllm_api_concurrency_result.json",
        "vllm_api_server_stats_summary.tsv",
    }:
        preferred.append(path)

rows = ["path\tsize_bytes\tmail_ok"]
seen = set()
for path in preferred:
    if path in seen or not path.is_file():
        continue
    seen.add(path)
    size = path.stat().st_size
    rows.append(f"{path}\t{size}\t{str(size <= limit_bytes).lower()}")
(artifact_dir / "mail_attachment_candidates.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
PY

echo "ARTIFACT_DIR=${ARTIFACT_DIR}"
echo "MAIL_ATTACHMENT_CANDIDATES=${ARTIFACT_DIR}/mail_attachment_candidates.tsv"
cat "${ARTIFACT_DIR}/summary.txt"
```

## 需要回传

邮件正文请包含：

```text
P1.24 vLLM API msprof SQLite window analysis 已完成/失败。

run_id: runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024
commit: <git rev-parse HEAD>
artifact_dir: 工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024
pytest_exit_code: <...>
reuse_analysis_exit_code: <...>
rerun_required: <0 或 1>
rerun_analysis_exit_code: <如有>

请见正文摘要；只附 70KB 以内的小文件。大规模数据、raw profiler、完整日志和大 zip 已留在服务器。
```

附件只允许包含 `mail_attachment_candidates.tsv` 中 `mail_ok=true` 且不超过 70KB 的小文件。优先考虑：

- `${RUN_ID}/summary.txt`
- `${RUN_ID}/run_context.txt`
- `${RUN_ID}/pytest.log`
- `${RUN_ID}/final_analysis/request_window_summary.tsv`
- `${RUN_ID}/final_analysis/profiler_sqlite_table_inventory.tsv`
- `${RUN_ID}/final_analysis/profiler_time_range_summary.tsv`
- `${RUN_ID}/final_analysis/request_profiler_overlap_summary.tsv`
- `${RUN_ID}/final_analysis/profiler_group_count_summary.tsv`
- `${RUN_ID}/final_analysis/msprof_sqlite_window_analysis_result.json`
- 如果发生 rerun：两个 mode 的 `msprof_vllm_api.log`、`msprof_output_files.txt`、`msprof_du.txt`、`vllm/vllm_api_concurrency_result.json`、`vllm/vllm_api_server_stats_summary.tsv`
- `${RUN_ID}/mail_attachment_candidates.tsv`

如果任何文件超过 70KB，不要强行压缩、拆分或通过多封邮件发送；只在正文说明服务器路径、文件大小和建议的后续分析任务。raw profiler 目录仍在服务器 `/tmp/<run_id>_<mode>_msprof`，项目内 artifact 仍在 `工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}`。

## 成功口径

强成功：

- `pytest_exit_code=0`
- final analysis `overall_status=success`
- 两个 mode 均 `sqlite_db_count > 0`
- 两个 mode 均 `time_candidate_count > 0`
- `request_window_summary.tsv`、`profiler_sqlite_table_inventory.tsv`、`profiler_time_range_summary.tsv`、`request_profiler_overlap_summary.tsv`、`profiler_group_count_summary.tsv`、`msprof_sqlite_window_analysis_result.json` 均生成
- 每个 mode 的 `time_alignment_status` 明确，不允许空缺

最低完成：

- 如果 raw 缺失且 rerun 也失败，必须回传复用尝试结果、rerun 日志、失败码和失败阶段。
- 如果 SQLite 可读但没有请求窗口直接重叠，必须回传 `profiler_tables_available_but_no_direct_window_overlap`，不能强行声称已经完成 CANN timeline pairing。

无论成功或失败，本轮只判断 SQLite 表、时间字段和请求窗口对齐证据是否可用，不做性能或瓶颈结论。
