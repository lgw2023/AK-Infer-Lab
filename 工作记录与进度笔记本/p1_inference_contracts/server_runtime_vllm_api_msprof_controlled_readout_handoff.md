# P1.27 vLLM API msprof Controlled Readout Handoff

任务 ID：`runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027`

目标：P1.26 已经完成同一 `continuous16_mixed` workload 的 prefix-cache on/off 受控复现，并确认两轮 16 个请求均固定生成 64 tokens。本轮不重新跑模型、不重新采集 msprof，只在服务器本地读取 P1.26 `final_analysis` 中的大 TSV，把 request-device raw counter、prefix-pair 候选、top op type 和 AI Core metric 汇总成 70KB 内可回传的小读数文件。

本轮回答的问题：

1. P1.26 的 `generated_token_count_mismatch_count` 是否确认为 0？
2. P1.26 的 on/off raw counter delta 在 request、prompt、prefix group 维度是否方向一致？
3. 哪些 op type 的 raw duration delta 最大？
4. 哪些 AI Core metric 的 raw delta 最大？
5. 下一轮是否可以进入更大 workload 的受控复现，还是需要先补事件模型/字段映射？

## 输入依据

- 源任务：`runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026`
- 源目录：`工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026`
- 源分析目录：`工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026/final_analysis`
- 本轮工具：`tools/inference_contracts/summarize_msprof_controlled_replay.py`

P1.26 已回传的关键摘要：

- `pytest_exit_code=0`
- `msprof_prefix_cache_on_exit_code=0`
- `msprof_prefix_cache_off_exit_code=0`
- `request_device_aggregate_fast_exit_code=0`
- on/off 两轮均 `request_count=16`、`success_case_count=16`
- on/off 两轮均 `generated_token_count_mismatch_count=0`
- on/off 两轮均 `min_generated_token_count=64`、`max_generated_token_count=64`
- `final_analysis` 聚合状态为 `overall_status=success`
- 聚合策略为 `bulk_temp_window_join_parallel_modes`

## 通信前置要求

- 昇腾服务器每次邮件正文和每个附件都按不超过 70KB 处理。
- 不要通过邮件发送 raw profiler、完整日志、大 zip、模型输出、实验目录或其他大文件。
- raw msprof、完整 `request_top_op_type_duration.tsv`、完整 `request_ai_core_metric_summary.tsv` 等大文件留在昇腾服务器本地。
- 邮件只回传任务状态、精简摘要、小 TSV/JSON、70KB 内附件和服务器侧路径。

## 建议执行命令

在服务器执行：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab || exit 1

RUN_ID="runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027"
SOURCE_RUN_ID="runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026"
SOURCE_ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${SOURCE_RUN_ID}"
ANALYSIS_DIR="${SOURCE_ARTIFACT_DIR}/final_analysis"
GENERATED_TOKEN_SUMMARY="${SOURCE_ARTIFACT_DIR}/generated_token_length_summary.tsv"
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
PYTHON_BIN="/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab/bin/python"

mkdir -p "${ARTIFACT_DIR}"

{
  echo "run_id=${RUN_ID}"
  echo "source_run_id=${SOURCE_RUN_ID}"
  echo "timestamp=$(date -Is)"
  echo "PYTHON_BIN=${PYTHON_BIN}"
  echo "SOURCE_ARTIFACT_DIR=${SOURCE_ARTIFACT_DIR}"
  echo "ANALYSIS_DIR=${ANALYSIS_DIR}"
  echo "GENERATED_TOKEN_SUMMARY=${GENERATED_TOKEN_SUMMARY}"
  echo "ARTIFACT_DIR=${ARTIFACT_DIR}"
} > "${ARTIFACT_DIR}/run_context.txt"

git pull --ff-only > "${ARTIFACT_DIR}/git_pull.log" 2>&1
GIT_PULL_EXIT_CODE=$?
echo "git_pull_exit_code=${GIT_PULL_EXIT_CODE}" >> "${ARTIFACT_DIR}/run_context.txt"

"${PYTHON_BIN}" -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest_inference_contracts.log" 2>&1
PYTEST_EXIT_CODE=$?
echo "pytest_exit_code=${PYTEST_EXIT_CODE}" >> "${ARTIFACT_DIR}/run_context.txt"

"${PYTHON_BIN}" tools/inference_contracts/summarize_msprof_controlled_replay.py \
  --run-id "${RUN_ID}" \
  --source-run-id "${SOURCE_RUN_ID}" \
  --source-artifact-dir "${SOURCE_ARTIFACT_DIR}" \
  --analysis-dir "${ANALYSIS_DIR}" \
  --generated-token-summary "${GENERATED_TOKEN_SUMMARY}" \
  --artifact-dir "${ARTIFACT_DIR}" \
  --top-op-limit 40 \
  --metric-limit 60 \
  > "${ARTIFACT_DIR}/controlled_readout.log" 2>&1
CONTROLLED_READOUT_EXIT_CODE=$?
echo "controlled_readout_exit_code=${CONTROLLED_READOUT_EXIT_CODE}" >> "${ARTIFACT_DIR}/run_context.txt"

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt"
  echo
  echo "## controlled_readout_summary"
  if [ -f "${ARTIFACT_DIR}/summary.txt" ]; then
    cat "${ARTIFACT_DIR}/summary.txt"
  else
    echo "summary_missing=1"
  fi
  echo
  echo "## output_files"
  find "${ARTIFACT_DIR}" -maxdepth 1 -type f -printf "%f\t%s bytes\n" | sort
} > "${ARTIFACT_DIR}/mail_summary.txt"
```

## 预期产物

产物目录：

```text
工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027
```

核心小文件：

- `summary.txt`
- `run_context.txt`
- `controlled_replay_readout_result.json`
- `controlled_replay_mode_delta_summary.tsv`
- `controlled_replay_pair_delta_summary.tsv`
- `controlled_replay_top_op_delta.tsv`
- `controlled_replay_ai_core_metric_delta.tsv`
- `mail_attachment_candidates.tsv`
- `mail_summary.txt`

## 成功口径

强成功：

- `git_pull_exit_code=0`
- `pytest_exit_code=0`
- `controlled_readout_exit_code=0`
- `controlled_replay_readout_result.json` 中 `overall_status=success`
- `generated_length_status.status=fixed_64`
- `missing_files=[]`
- 产出 mode delta、pair delta、top-op delta、AI Core metric delta 四类小摘要

最低完成：

- 即使 `controlled_readout_exit_code != 0`，也必须回传 `run_context.txt`、`mail_summary.txt`、`controlled_readout.log` 的尾部错误摘要，以及缺失文件列表。
- 不要为补齐缺失文件而重新跑模型或重新采集 msprof；只报告 P1.26 服务器侧路径状态。

## 执行边界

允许：

- `git pull --ff-only`。
- 使用当前 conda 环境运行本地 Python 脚本和 `pytest tests/inference_contracts -q`。
- 只读访问 P1.26 `final_analysis`、P1.26 `generated_token_length_summary.tsv` 和 P1.26 raw artifact 路径。
- 输出 70KB 内的小摘要 TSV/JSON/txt。

禁止：

- 不启动 vLLM API server。
- 不运行新的模型推理请求。
- 不重新运行 msprof。
- 不安装、升级、卸载或修复任何包。
- 不创建新 conda 环境。
- 不改 driver、CANN、apt、dpkg、NPU runtime、vLLM 或 vLLM-Ascend 源码。
- 不运行 full 16K/32K 或 full `P010=43216` tokens。
- 不运行多 worker 压测、benchmark、长时间服务或吞吐压测。
- 不切换 Docker 推理栈。
- 不在服务器上修改、提交或 push 项目代码。
- 不回传 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。
- 不回传超过 70KB 的邮件正文或附件；raw profiler、完整日志、大 zip、完整大 TSV 和实验目录必须留在服务器本地。
- 不输出性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因或优化建议。

## 回传要求

邮件正文请包含：

```text
P1.27 vLLM API msprof controlled readout 已完成/失败。

run_id: runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027
source_run_id: runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026
commit: <git rev-parse HEAD>
artifact_dir: 工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027
git_pull_exit_code: <...>
pytest_exit_code: <...>
controlled_readout_exit_code: <...>
overall_status: <...>
generated_length_status: <fixed_64/not_fixed_64>
missing_files: <[] 或列表>

all_request_raw_delta:
- request_count=<...>
- delta_task_row_count_sum_on_minus_off=<...>
- delta_total_duration_time_sum_on_minus_off=<...>
- negative_duration_delta_request_count=<...>
- positive_duration_delta_request_count=<...>

output_rows:
- mode_delta_group_count=<...>
- pair_delta_row_count=<...>
- top_op_delta_row_count=<...>
- metric_delta_row_count=<...>

边界：本轮只做 P1.26 final_analysis 离线读数；未启动 vLLM server，未运行新请求，未重新采集 msprof，未安装或修复包，未输出 benchmark/吞吐/调度效率/prefix cache 命中率/瓶颈/优化结论。
```

附件只允许包含 `mail_attachment_candidates.tsv` 中 `mail_ok=true` 且不超过 70KB 的小文件。优先回传：

- `mail_summary.txt`
- `summary.txt`
- `run_context.txt`
- `controlled_replay_readout_result.json`
- `controlled_replay_mode_delta_summary.tsv`
- `controlled_replay_pair_delta_summary.tsv`
- `controlled_replay_top_op_delta.tsv`
- `controlled_replay_ai_core_metric_delta.tsv`
- `mail_attachment_candidates.tsv`

如果任何 TSV、JSON 或 log 超过 70KB，不要压缩或拆分回传；正文只写服务器路径、文件大小和关键行数。
