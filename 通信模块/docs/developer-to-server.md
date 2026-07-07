# Developer to Server

## 当前任务：P1.24 vLLM API msprof SQLite window analysis

- 任务 ID：`runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024`
- 目标：把 P1.23 的 profiler coverage 证据推进到 SQLite/request-window 可解释摘要。
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_vllm_api_msprof_sqlite_window_analysis_handoff.md`
- 请先 `git pull --ff-only`，再按详细 handoff 中 `建议执行命令` 的完整 bash 代码块执行。

## 通信前置要求

- 昇腾服务器每次邮件正文和每个附件都按不超过 70KB 处理。
- 不要通过邮件发送 raw profiler、完整日志、大 zip、模型输出、实验目录或其他大文件。
- 本轮产生的大规模数据保留在昇腾服务器本地；如需进一步分析，由外部开发者（本机）在下一轮 `developer-to-server.md` 中下达服务器本地分析任务。
- 邮件只回传任务状态、精简摘要、小清单、少量样例、70KB 以内的小附件和服务器侧路径。

## 已有依据

P1.23 `runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023` 已完成：

- `commit=6f2e3eb0d5cda17fa1558629bc847ab084531f18`
- `pytest_exit_code=0`
- `msprof_prefix_cache_on_exit_code=0`
- `msprof_prefix_cache_off_exit_code=0`
- 两轮均为 `continuous16_mixed`、`max_model_len=9216`
- 两轮均 `request_count=16`、`success_case_count=16`、`failed_case_count=0`
- 两轮均 `client_overlap_candidate_count=120`、`trace_validation_errors=0`
- on 侧 `server_stats_max_prefix_cache_hit_rate_pct=51.4`，off 侧为 `0.0`
- on 侧 `msprof_file_count=582`，off 侧 `msprof_file_count=808`
- 两侧均 `msprof_sqlite_count=17`、`msprof_host_dir_count=1`、`msprof_device_dir_count=1`、`msprof_timebase_candidate_count=56`

P1.23 附件只回传了 selected artifacts，没有完整 raw SQLite DB。本轮请优先复用服务器 `/tmp` 下的 P1.23 raw msprof 目录；如果 raw 不存在，则按 handoff 自动重跑同一 on/off profiled workload，并立即运行分析工具。

## 服务器需要做什么

1. 在 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行 `git pull --ff-only`。
2. 执行详细 handoff 的 `建议执行命令` bash 块。
3. 该命令会运行本地测试：
   - `python -m pytest tests/inference_contracts -q`
4. 该命令会运行分析工具：
   - `tools/inference_contracts/analyze_msprof_sqlite_windows.py`
5. 如果 P1.23 raw profiler 目录仍存在，直接分析：
   - `/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_on_msprof`
   - `/tmp/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023_msprof_prefix_cache_off_msprof`
6. 如果 raw profiler 目录不存在，自动重跑同一负载：
   - `case_plan=continuous16_mixed`
   - `max_model_len=9216`
   - `msprof_prefix_cache_on --enable-prefix-caching`
   - `msprof_prefix_cache_off --no-enable-prefix-caching`
7. 最终产物写入：
   - `工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024`

## 必须生成的 final analysis 文件

- `final_analysis/request_window_summary.tsv`
- `final_analysis/profiler_sqlite_table_inventory.tsv`
- `final_analysis/profiler_time_range_summary.tsv`
- `final_analysis/request_profiler_overlap_summary.tsv`
- `final_analysis/profiler_group_count_summary.tsv`
- `final_analysis/msprof_sqlite_window_analysis_result.json`

`msprof_sqlite_window_analysis_result.json` 必须给出每个 mode 的 `time_alignment_status`：

- `direct_request_window_overlap`
- `profiler_tables_available_but_no_direct_window_overlap`
- `missing_msprof_sqlite`

如果没有请求窗口直接重叠，不能强行声称 CANN timeline pairing 已完成。

## 执行边界

允许：

- 使用当前 conda 环境
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`
- source `/usr/local/Ascend/nnal/atb/set_env.sh`
- 使用当前环境已有 `vllm`、`vllm_ascend`、`msprof`
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 只读解析 raw profiler SQLite，输出聚合 TSV/JSON

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

## 回传要求

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
- `${RUN_ID}/mail_attachment_candidates.tsv`

如果任何文件超过 70KB，不要强行压缩、拆分或通过多封邮件发送；只在正文说明服务器路径、文件大小和建议的后续分析任务。raw profiler 目录仍在服务器 `/tmp/<run_id>_<mode>_msprof`，项目内 artifact 仍在 `工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024`。
