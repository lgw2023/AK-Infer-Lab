# Developer to Server

## 当前任务：P1.25b vLLM API msprof request-device aggregate fast

- 任务 ID：`runtime_vllm_api_msprof_request_device_aggregate_fast_2026_0707_p1_025b`
- 旧任务 ID：`runtime_vllm_api_msprof_request_device_aggregate_2026_0707_p1_025`
- 目标：旧 P1.25 离线 SQLite 聚合已运行超过 3 小时。本轮记录旧进程状态并终止仍在运行的旧离线聚合进程，拉取加速版聚合器，只读复用 P1.23 raw msprof SQLite，重新生成 request 级 device task、op type、AI Core metric 聚合摘要。
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_vllm_api_msprof_request_device_aggregate_fast_handoff.md`
- 请按详细 handoff 中 `建议执行命令` 的完整 bash 代码块执行。

## 为什么改为 P1.25b

P1.25 第一版聚合器按 request 逐个查询 SQLite，容易对 `task_time`、`ge_summary`、`ai_core_metrics` 做重复扫描和 join。P1.25b 已改为：

- 每个 mode 建 `request_windows` 临时表。
- 每个 mode 只 materialize 一次 request-window overlap task 临时表。
- `ge_summary` / `ai_core_metrics` 复制为临时 join 表并建临时索引。
- prefix-cache on/off 两个 mode 用 `--workers 2` 并行跑。
- 如果 full 聚合仍在 45 分钟内失败或 timeout，自动切到 `--skip-heavy-joins` 兜底模式，跳过 top-op/AI Core metric heavy joins，优先回传 request/task-type 基础聚合。
- 不修改 raw msprof SQLite。

## 通信前置要求

- 昇腾服务器每次邮件正文和每个附件都按不超过 70KB 处理。
- 不要通过邮件发送 raw profiler、完整日志、大 zip、模型输出、实验目录或其他大文件。
- 本轮产生的大规模数据保留在昇腾服务器本地；如需进一步分析，由外部开发者在下一轮 `developer-to-server.md` 中下达服务器本地分析任务。
- 邮件只回传任务状态、精简摘要、小清单、少量样例、70KB 以内的小附件和服务器侧路径。

## 服务器需要做什么

1. 在 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行详细 handoff 的完整 bash 块。
2. 该命令会先查找旧 P1.25 `analyze_msprof_request_device_aggregate.py` 进程。
3. 如果旧进程仍在运行，只记录该旧离线聚合进程状态和旧 log tail，然后终止该旧进程。
4. 执行 `git pull --ff-only`。
5. 运行本地测试：`python -m pytest tests/inference_contracts -q`。
6. 只读复用 P1.23 raw msprof：
   - `/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_on_msprof`
   - `/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_off_msprof`
7. 运行加速聚合：
   - `tools/inference_contracts/analyze_msprof_request_device_aggregate.py --workers 2`
8. 如果 full 聚合失败或 timeout，自动运行兜底聚合：
   - `tools/inference_contracts/analyze_msprof_request_device_aggregate.py --workers 2 --skip-heavy-joins`
9. 最终产物写入：
   - `工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_request_device_aggregate_fast_2026_0707_p1_025b`

## 必须生成的 final analysis 文件

- `final_analysis/request_device_task_summary.tsv`
- `final_analysis/request_device_task_type_summary.tsv`
- `final_analysis/request_top_op_type_duration.tsv`
- `final_analysis/request_ai_core_metric_summary.tsv`
- `final_analysis/prefix_cache_mode_request_delta.tsv`
- `final_analysis/prefix_pair_candidate_delta.tsv`
- `final_analysis/msprof_request_device_aggregate_result.json`

`msprof_request_device_aggregate_result.json` 必须给出：

- `aggregation_strategy=bulk_temp_window_join_parallel_modes`
- `workers=2`
- `heavy_joins_skipped`
- 每个 mode 的 `aggregate_status`
- 每个 mode 的 `elapsed_sec`

## 执行边界

允许：

- 记录并终止仍在运行的旧 P1.25 离线聚合进程。
- 使用当前 conda 环境、Python 和 SQLite。
- 创建 SQLite 临时表和临时索引。
- 如果 full 聚合 timeout，运行 `--skip-heavy-joins` 基础聚合兜底。
- 只读解析 raw profiler SQLite。
- 输出聚合 TSV/JSON 和小摘要。

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
