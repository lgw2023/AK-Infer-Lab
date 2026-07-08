# Developer to Server

## 当前任务：P1.28 vLLM API msprof larger controlled replay

- 任务 ID：`runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028`
- 上一轮依据：`runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_vllm_api_msprof_larger_controlled_replay_handoff.md`
- 请先 `git pull --ff-only`，然后按详细 handoff 中 `建议执行命令` 的完整 bash 代码块执行。

## 为什么进入 P1.28

P1.26/P1.27 附件已确认 16 请求闭环成立：

- P1.26 附件目录：`/Users/liguowei/Downloads/akp1_26vllmapimsprofcontrolledreplay-2`
- P1.27 附件目录：`/Users/liguowei/Downloads/akp1_27vllmapimsprofcontrolledreadout`
- P1.26 `overall_status=success`，on/off 两轮均 `request_count=16`、`success_case_count=16`、`generated_token_count_mismatch_count=0`、`min=max=64`。
- P1.26 request-device full 聚合成功：on/off 两轮各 16 行 request summary、320 行 top-op、16 行 AI Core metric。
- P1.27 `overall_status=success`、`missing_files=[]`、`generated_length_status=fixed_64`。
- P1.27 all-request raw delta：`request_count=16`、`delta_task_row_count_sum_on_minus_off=-166800`、`delta_total_duration_time_sum_on_minus_off=-88984462248`、`negative_duration_delta_request_count=16`、`positive_duration_delta_request_count=0`。
- P1.27 输出 12 行 mode/group、8 行 prefix-pair、22 行 top-op、21 行 AI Core metric 小摘要。

这说明当前可以从 16 请求受控闭环扩大到 32 请求受控 workload。P1.28 不再拆成“先 replay、再 readout”两封任务，而是在同一轮完成 on/off msprof、request-device 聚合和 readout 小摘要。

## 通信前置要求

- 昇腾服务器每次邮件正文和每个附件都按不超过 70KB 处理。
- 不要通过邮件发送 raw profiler、完整日志、大 zip、模型输出、实验目录或其他大文件。
- raw msprof、完整 `request_top_op_type_duration.tsv`、完整 `request_ai_core_metric_summary.tsv` 等大文件留在昇腾服务器本地。
- 邮件只回传任务状态、精简摘要、小 TSV/JSON、70KB 内附件和服务器侧路径。

## 服务器需要做什么

1. 在 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行详细 handoff 的完整 bash 块。
2. 执行 `git pull --ff-only`。
3. 运行本地测试：`python -m pytest tests/inference_contracts -q`。
4. 使用 `tools/inference_contracts/run_vllm_api_concurrency_smoke.py` 的 `--case-plan continuous32_mixed`。
5. 对 `msprof_prefix_cache_on` 与 `msprof_prefix_cache_off` 各运行一次 profiled workload。
6. 两轮均使用：
   - `--max-model-len 9216`
   - `--min-tokens 64`
   - `--ignore-eos`
   - `--storage-limit=8192`
7. 运行 `tools/inference_contracts/analyze_msprof_request_device_aggregate.py --workers 2` 生成 `final_analysis/`。
8. 运行 `tools/inference_contracts/summarize_msprof_controlled_replay.py` 生成 `readout/` 小摘要。

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

## 执行边界

允许：

- `git pull --ff-only`。
- 使用当前 conda 环境运行本地 Python 脚本和 `pytest tests/inference_contracts -q`。
- source CANN/ATB 环境。
- 使用当前已有 `vllm`、`vllm_ascend`、`msprof` 和 `/data/node0_disk1/Public/Qwen3.5-4B`。
- 输出 70KB 内的小摘要 TSV/JSON/txt。

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
- 不回传超过 70KB 的邮件正文或附件。
- 不输出性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因或优化建议。

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

- `mail_summary.txt`
- `summary.txt`
- `run_context.txt`
- `generated_token_length_summary.tsv`
- `controlled_replay_result.json`
- `final_analysis/summary.txt`
- `final_analysis/msprof_request_device_aggregate_result.json`
- `final_analysis/prefix_cache_mode_request_delta.tsv`
- `final_analysis/prefix_pair_candidate_delta.tsv`
- `readout/summary.txt`
- `readout/controlled_replay_readout_result.json`
- `readout/controlled_replay_mode_delta_summary.tsv`
- `readout/controlled_replay_pair_delta_summary.tsv`
- `readout/controlled_replay_top_op_delta.tsv`
- `readout/controlled_replay_ai_core_metric_delta.tsv`
- `mail_attachment_candidates.tsv`

如果任何 TSV、JSON 或 log 超过 70KB，不要压缩或拆分回传；正文只写服务器路径、文件大小和关键行数。
