# Developer to Server

## 当前任务：P1.29 Qwen3.5-4B vLLM API streaming perf + denominator

- 状态 ID：`runtime_vllm_api_streaming_perf_denominator_2026_0708_p1_029`
- Handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_vllm_api_streaming_perf_denominator_handoff.md`
- 上一轮依据：P1.28 `runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028`
- 本轮目的：补齐 Qwen3.5-4B / vLLM API 的 TTFT、TPOT、E2E latency、output tokens/s、server stats A/B、AISBench/MindIE-Motor 风格性能参数表、common metric 表、单位映射、MatMul FLOPs denominator 和 input/output tensor footprint bytes。

## 执行要求

请严格执行 handoff 文件中的命令和边界。

本轮分两段：

1. `perf_unprofiled`：不启用 msprof，运行 streaming `/v1/completions`，采集用户可见性能指标，并输出 AISBench-style `Performance Parameters` / `Common Metric` 小表。
2. `msprof_denominator`：启用 msprof 跑同一 `continuous32_mixed` streaming workload，只用于 shape/unit/denominator 读数。

关键固定条件：

- 模型：`/data/node0_disk1/Public/Qwen3.5-4B`
- workload：`continuous32_mixed`
- `--max-model-len 9216`
- `--min-tokens 64`
- `--ignore-eos`
- prefix cache A/B：on/off 各一轮
- device 默认：`ASCEND_RT_VISIBLE_DEVICES=6`
- `VLLM_PLUGINS=ascend`
- `VLLM_USE_V1=1`

## 必须回传

邮件正文控制在 70KB 内，必须包含：

- `run_id`
- `commit`
- `git_pull_exit_code`
- `pytest_exit_code`
- `perf_on_exit_code`
- `perf_off_exit_code`
- `perf_pair_exit_code`
- `msprof_on_exit_code`
- `msprof_off_exit_code`
- `shape_denominator_exit_code`
- unprofiled on/off 的 request_count、success、failed、generated mismatch
- unprofiled on/off 的 TTFT median/p95、TPOT median/p95、E2E median/p95、aggregate output tokens/s
- unprofiled on/off 的 AISBench-style 指标：`E2EL`、`TTFT`、`TPOT`、`ITL`、`InputTokens`、`OutputTokens`、`OutputTokenThroughput`、`PrefillTokenThroughput`
- unprofiled on/off 的 common metrics：`Benchmark Duration`、`Concurrency`、`Max Concurrency`、`Request Throughput`、`Input Token Throughput`、`Output Token Throughput`、`Total Token Throughput`
- on/off 的 max running、max waiting、max KV cache usage、max prefix cache hit rate
- denominator 的 `shape_row_count`、`op_type_row_count`
- MatMulV2/MatMulV3 的 denominator 状态
- unit mapping confidence
- artifact_dir
- mail_attachment_candidates

建议附件：

- `summary.txt`
- `p1_029_result.json`
- `perf_pair_readout/vllm_api_streaming_perf_mode_summary.tsv`
- `perf_pair_readout/vllm_api_streaming_perf_delta_summary.tsv`
- `perf_pair_readout/vllm_api_streaming_perf_parameters.tsv`
- `perf_pair_readout/vllm_api_streaming_perf_common_metrics.tsv`
- `perf_pair_readout/vllm_api_streaming_perf_pair_result.json`
- `msprof_denominator_readout/msprof_shape_denominator_result.json`
- `msprof_denominator_readout/msprof_shape_denominator_by_op_type.tsv`
- `msprof_denominator_readout/msprof_unit_mapping.tsv`
- `msprof_denominator_readout/hardware_denominator_mapping.tsv`
- `mail_attachment_candidates.tsv`

## 边界

- 不启动 P5。
- 不启动 DeepSeek-V4-Flash。
- 不重复 P1.28 原任务。
- 不重复 P0/P3 hardware ceiling sweep。
- 不安装、升级、卸载或修复任何包。
- 不修改、提交或 push 服务器仓库代码。
- 不静默降低 `max_model_len`、不删减 case、不降低输入 cap、不缩短 output token。
- 不把 profiler 下的 TTFT/TPOT 当作 unprofiled 性能结论。
- 不把 vLLM OpenAI streaming client 的 AISBench-style 指标当作 MindIE native `prefill_time/decode_time`。
- `ITL` 是 host streaming inter-chunk latency，不是 runtime native decode event。
- 不把 shape-derived tensor bytes 当作 HBM traffic。
- 不输出 compute-bound、memory-bound、scheduler-bound、prefix-cache benefit 或其他瓶颈归因结论。
- 不回传 raw msprof、大日志、大 zip、完整 generated text 或超过 70KB 的附件。

## 完成后

请发送任务完成邮件，标题建议：

```text
[AK服务器] 任务完成：P1.29 Qwen3.5-4B vLLM API streaming perf denominator
```

如果任何一步失败，不要取巧缩小任务；保留失败产物在服务器本地，回传 70KB 内摘要、退出码和小文件清单。
