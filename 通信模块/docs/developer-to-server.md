# Developer to Server

## 当前任务：P1.26 vLLM API msprof controlled replay

- 任务 ID：`runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026`
- 上一轮依据：`runtime_vllm_api_msprof_request_device_aggregate_fast_2026_0707_p1_025b`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_vllm_api_msprof_controlled_replay_handoff.md`
- 请按详细 handoff 中 `建议执行命令` 的完整 bash 代码块执行。

## 为什么进入 P1.26

P1.25b 已证明离线 request-device 聚合链路可用：

- 旧 P1.25 第一版离线聚合在服务器运行 8.6 小时后被中止。
- P1.25b 使用 `bulk_temp_window_join_parallel_modes`、SQLite 临时表/临时索引和 `--workers 2` 后，on/off 两个 mode 各约 54-56 秒完成 full 聚合。
- 两个 mode 均 `request_count=16`、`successful_request_count=16`，并生成 request summary、task type、top op、AI Core metric 和 prefix delta 表。

但 P1.25b 复用的是 P1.23 raw workload。该 workload 中 off 侧有部分请求提前 EOS，`generated_token_count` 只有 1、2、4、6 等值，导致 on/off raw counter delta 不能直接作为受控比较证据。因此 P1.26 要重新运行同一 16 请求 workload，并显式传入：

- `--min-tokens 64`
- `--ignore-eos`
- `--case-plan continuous16_mixed`
- `--max-model-len 9216`

本轮目标不是做性能结论，而是消除输出长度混杂，拿到更干净的 msprof raw + request-device aggregate 证据。

## 通信前置要求

- 昇腾服务器每次邮件正文和每个附件都按不超过 70KB 处理。
- 不要通过邮件发送 raw profiler、完整日志、大 zip、模型输出、实验目录或其他大文件。
- raw msprof 与大规模实验数据留在昇腾服务器本地。
- 邮件只回传任务状态、精简摘要、小清单、少量样例、70KB 以内的小附件和服务器侧路径。

## 服务器需要做什么

1. 在 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行详细 handoff 的完整 bash 块。
2. 执行 `git pull --ff-only`。
3. 运行本地测试：`python -m pytest tests/inference_contracts -q`。
4. 使用当前环境已有 vLLM/vLLM-Ascend 和 msprof，不安装或修复包。
5. 对 `msprof_prefix_cache_on` 运行一次 profiled `continuous16_mixed`：
   - `/v1/completions`
   - `--max-model-len 9216`
   - `--min-tokens 64`
   - `--ignore-eos`
   - `--enable-prefix-caching`
6. 对 `msprof_prefix_cache_off` 运行一次 profiled `continuous16_mixed`：
   - 同上，但使用 `--no-enable-prefix-caching`
7. 生成 `generated_token_length_summary.tsv`，重点确认两个 mode 的 `generated_token_count_mismatch_count`。
8. 立即运行 P1.25b 加速聚合器：
   - `tools/inference_contracts/analyze_msprof_request_device_aggregate.py --workers 2`
9. 最终产物写入：
   - `工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026`

## 成功口径

强成功：

- `pytest_exit_code=0`
- `msprof_prefix_cache_on_exit_code=0`
- `msprof_prefix_cache_off_exit_code=0`
- on/off 两个 mode 均 `success_case_count=16`
- on/off 两个 mode 均 `generated_token_count_mismatch_count=0`
- on/off 两个 raw msprof 目录均存在并包含 device sqlite
- `request_device_aggregate_fast_exit_code=0`
- `final_analysis/msprof_request_device_aggregate_result.json` 为 `overall_status=success`

最低完成：

- 即使某个 mode 失败，也必须回传 pytest、该 mode 的 vLLM result、msprof exit code、生成长度摘要、raw msprof 路径状态和失败阶段。

## 执行边界

允许：

- `git pull --ff-only`。
- 使用当前 conda 环境、CANN/ATB 环境、vLLM/vLLM-Ascend 和 msprof。
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`。
- 用 ASCII `/tmp/<run_id>_<mode>_msprof` 作为 msprof 输出目录。
- 运行同一 `continuous16_mixed` 16 请求 workload 的 prefix-cache on/off 两轮。
- 在请求中使用 vLLM SamplingParams：`min_tokens=64`、`ignore_eos=true`。
- 只读解析本轮 raw profiler SQLite。
- 输出 TSV/JSON/summary 小文件。

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
- 不回传超过 70KB 的邮件正文或附件；raw profiler、完整日志、大 zip 和实验目录必须留在服务器本地。
- 不输出性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因或优化建议。

## 回传要求

邮件正文请包含：

```text
P1.26 vLLM API msprof controlled replay 已完成/失败。

run_id: runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026
previous_run_id: runtime_vllm_api_msprof_request_device_aggregate_fast_2026_0707_p1_025b
commit: <git rev-parse HEAD>
artifact_dir: 工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026
git_pull_exit_code: <...>
pytest_exit_code: <...>
msprof_prefix_cache_on_exit_code: <...>
msprof_prefix_cache_off_exit_code: <...>
request_device_aggregate_fast_exit_code: <...>

generated_token_length_summary:
- msprof_prefix_cache_on: request_count=<...>, success_case_count=<...>, failed_case_count=<...>, generated_token_count_mismatch_count=<...>, min_generated_token_count=<...>, max_generated_token_count=<...>
- msprof_prefix_cache_off: request_count=<...>, success_case_count=<...>, failed_case_count=<...>, generated_token_count_mismatch_count=<...>, min_generated_token_count=<...>, max_generated_token_count=<...>

mode_summaries:
- msprof_prefix_cache_on: aggregate_status=<...>, elapsed_sec=<...>, request_device_summary_rows=<...>, top_op_summary_rows=<...>, metric_summary_rows=<...>
- msprof_prefix_cache_off: aggregate_status=<...>, elapsed_sec=<...>, request_device_summary_rows=<...>, top_op_summary_rows=<...>, metric_summary_rows=<...>

边界：使用 --min-tokens 64 --ignore-eos 控制生成长度；未安装或修复包，未切换 Docker，未运行 full 16K/32K 或 P010=43216，未输出 benchmark/吞吐/调度效率/prefix cache 命中率/瓶颈/优化结论。
```

附件只允许包含 `mail_attachment_candidates.tsv` 中 `mail_ok=true` 且不超过 70KB 的小文件。优先回传：

- `${RUN_ID}/summary.txt`
- `${RUN_ID}/run_context.txt`
- `${RUN_ID}/generated_token_length_summary.tsv`
- `${RUN_ID}/controlled_replay_result.json`
- `${RUN_ID}/final_analysis/summary.txt`
- `${RUN_ID}/final_analysis/msprof_request_device_aggregate_result.json`
- `${RUN_ID}/final_analysis/prefix_cache_mode_request_delta.tsv`
- `${RUN_ID}/final_analysis/prefix_pair_candidate_delta.tsv`
- `${RUN_ID}/mail_attachment_candidates.tsv`

如果任何 TSV、JSON 或 log 超过 70KB，不要压缩或拆分回传；正文只写服务器路径、文件大小和关键行数。
