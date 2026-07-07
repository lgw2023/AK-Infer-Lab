# Developer to Server

## 当前任务：P1.25 vLLM API msprof request-device aggregate

- 任务 ID：`runtime_vllm_api_msprof_request_device_aggregate_2026_0707_p1_025`
- 目标：复用 P1.23/P1.24 已确认存在并可直接对齐的 raw msprof SQLite，在服务器本地只读生成 request 级 device task、op type、AI Core metric 聚合摘要。
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_vllm_api_msprof_request_device_aggregate_handoff.md`
- 请先 `git pull --ff-only`，再按详细 handoff 中 `建议执行命令` 的完整 bash 代码块执行。

## 通信前置要求

- 昇腾服务器每次邮件正文和每个附件都按不超过 70KB 处理。
- 不要通过邮件发送 raw profiler、完整日志、大 zip、模型输出、实验目录或其他大文件。
- 本轮产生的大规模数据保留在昇腾服务器本地；如需进一步分析，由外部开发者（本机）在下一轮 `developer-to-server.md` 中下达服务器本地分析任务。
- 邮件只回传任务状态、精简摘要、小清单、少量样例、70KB 以内的小附件和服务器侧路径。

## 已有依据

P1.24 `runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024` 已完成：

- `commit=b51e779aa5d78ab164b70b308f5204b5390129de`
- `pytest_exit_code=0`
- `reuse_analysis_exit_code=0`
- `rerun_required=0`
- `msprof_prefix_cache_on`: `request_count=16`、`successful_request_count=16`、`sqlite_db_count=17`、`sqlite_table_count=39`、`time_candidate_count=6`、`direct_overlap_candidate_count=3`、`time_alignment_status=direct_request_window_overlap`
- `msprof_prefix_cache_off`: `request_count=16`、`successful_request_count=16`、`sqlite_db_count=17`、`sqlite_table_count=39`、`time_candidate_count=6`、`direct_overlap_candidate_count=3`、`time_alignment_status=direct_request_window_overlap`

P1.24 说明 P1.23 raw profiler 仍可复用，且 device 侧 `task_time`、`AscendTask`、`rts_task` 三类表与 vLLM API request windows 有直接 overlap。本轮不重启 vLLM API server，不运行新的模型请求，直接做更深的 SQLite request 级聚合。

## 服务器需要做什么

1. 在 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行 `git pull --ff-only`。
2. 执行详细 handoff 的 `建议执行命令` bash 块。
3. 该命令会运行本地测试：
   - `python -m pytest tests/inference_contracts -q`
4. 该命令会运行分析工具：
   - `tools/inference_contracts/analyze_msprof_request_device_aggregate.py`
5. 该命令只读复用 P1.23 raw msprof：
   - `/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_on_msprof`
   - `/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_off_msprof`
6. 如果 raw profiler 目录已经被清理，本轮不要偷偷重跑 vLLM；直接回传 `missing_raw=1` 和缺失路径。
7. 最终产物写入：
   - `工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_request_device_aggregate_2026_0707_p1_025`

## 必须生成的 final analysis 文件

- `final_analysis/request_device_task_summary.tsv`
- `final_analysis/request_device_task_type_summary.tsv`
- `final_analysis/request_top_op_type_duration.tsv`
- `final_analysis/request_ai_core_metric_summary.tsv`
- `final_analysis/prefix_cache_mode_request_delta.tsv`
- `final_analysis/prefix_pair_candidate_delta.tsv`
- `final_analysis/msprof_request_device_aggregate_result.json`

`msprof_request_device_aggregate_result.json` 必须给出每个 mode 的 `aggregate_status`：

- `request_device_aggregate_available`
- `missing_direct_overlap_device_tables`
- `missing_raw_msprof`

## 执行边界

允许：

- 使用当前 conda 环境
- 使用当前环境已有 Python 和 SQLite
- 只读解析 raw profiler SQLite
- 输出聚合 TSV/JSON 和小摘要

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
- 不把 raw counter delta 解释为性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因或优化建议

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
