# Developer to Server

## 当前任务：P1.30 Qwen3.5-4B vLLM prefix-cache phase memory readout

- 状态 ID：`runtime_vllm_api_memory_phase_readout_2026_0708_p1_030`
- 上一轮依据：P1.29 `runtime_vllm_api_streaming_perf_denominator_2026_0708_p1_029`
- 本轮目的：补齐 P1.29 未覆盖的 `prefix_cache_on/off x prefill/decode` 显存/内存占用矩阵。
- 任务性质：小文件采集与摘要；不做瓶颈归因，不做优化结论。

## 背景

P1.29 已经产出 Qwen3.5-4B / vLLM OpenAI streaming client 的 TTFT、TPOT、E2EL、ITL、AISBench-style Performance Parameters / Common Metrics 和 MatMulV2/MatMulV3 shape-derived denominator。

但 P1.29 没有证明以下内容：

- prefix_cache_on/off 在 prefill 阶段的 NPU HBM used/free。
- prefix_cache_on/off 在 decode 阶段的 NPU HBM used/free。
- prefix_cache_on/off 在 prefill/decode 阶段的 host process RSS/PSS/VmRSS/VmHWM。
- KV/prefix object footprint、lookup、restore、eviction、bytes。

P1.29 只有 `server_stats_max_kv_cache_usage_pct`：

- prefix_cache_on: `8.2%`
- prefix_cache_off: `16.1%`

这只能作为 overall vLLM KV cache usage proxy，不能冒充显存占用、host 内存占用或 phase-split memory readout。

## 固定条件

沿用 P1.29 条件，不降级：

- 模型：`/data/node0_disk1/Public/Qwen3.5-4B`
- workload：`continuous32_mixed`
- `--max-model-len 9216`
- `--min-tokens 64`
- `--ignore-eos`
- prefix cache A/B：on/off 各一轮
- device 默认：`ASCEND_RT_VISIBLE_DEVICES=6`
- `VLLM_PLUGINS=ascend`
- `VLLM_USE_V1=1`
- output：on/off 均应为 32/32 success、fixed 64 tokens、mismatch=0

## 采集要求

请在 vLLM server 启动后、请求执行期间，用不高于 0.5s 的周期采样以下信息，并用 request timing 将样本归到 `prefill` 和 `decode` 窗口：

- NPU/device 侧：
  - HBM used/free MB。
  - 如果工具能给出，记录 HBM utilization 或 memory utilization。
  - 原始 `npu-smi` 命令、输出样例和解析策略必须保留。
- Host/process 侧：
  - vLLM API server 主进程和子进程 PID。
  - process group RSS MB。
  - 如果 `/proc/*/smaps_rollup` 可读，记录 PSS MB。
  - 至少保留 VmRSS/VmHWM。
- Request timing：
  - request_start_ns。
  - first_token_ns 或 TTFT 对应时间点。
  - response_end_ns。
  - phase policy：`prefill=request_start..first_token`，`decode=first_token..response_end`。

如果多请求并发导致同一采样点同时覆盖多个 request/phase，请不要取巧丢弃样本；按 benchmark-window phase overlap 汇总，并在 policy 中说明。

## 必须输出的小文件

请在 artifact_dir 下输出：

```text
summary.txt
p1_030_result.json
memory_phase_summary.tsv
memory_phase_samples_head.tsv
memory_phase_sampling_policy.txt
mail_attachment_candidates.tsv
```

建议 `memory_phase_summary.tsv` 字段：

```text
mode
phase
sample_count
overlapped_request_count
host_process_rss_mb_avg
host_process_rss_mb_max
host_process_pss_mb_avg
host_process_pss_mb_max
npu_hbm_used_mb_avg
npu_hbm_used_mb_max
npu_hbm_free_mb_avg
npu_hbm_free_mb_min
npu_hbm_usage_pct_avg
npu_hbm_usage_pct_max
kv_cache_usage_pct_max
policy
```

期望 mode/phase 至少有 4 行：

```text
prefix_cache_on   prefill
prefix_cache_on   decode
prefix_cache_off  prefill
prefix_cache_off  decode
```

## 必须回传邮件正文

邮件正文控制在 70KB 内，必须包含：

- `run_id`
- `source_run_id=P1.29`
- `commit`
- `git_pull_exit_code`
- `pytest_exit_code`
- `memory_probe_on_exit_code`
- `memory_probe_off_exit_code`
- `summary_exit_code`
- on/off request_count、success、failed、generated mismatch
- on/off 的 max KV cache usage pct
- 4 行 mode/phase memory summary 摘要
- NPU HBM 采样命令和解析可信度
- host RSS/PSS 采样方法和解析可信度
- artifact_dir
- mail_attachment_candidates

## 边界

- 不启动 P5。
- 不启动 DeepSeek-V4-Flash。
- 不重复 P0/P3 hardware ceiling sweep。
- 不重复 P1.29 的 AISBench-style 性能表和 denominator 任务，除非为了对齐 request timing 必须重跑同一 workload。
- 不安装、升级、卸载或修复任何包。
- 不修改、提交或 push 服务器仓库代码。
- 不降低 `max_model_len`、不删减 case、不降低输入 cap、不缩短 output token。
- 不把 KV cache usage pct 当作 HBM used/free。
- 不把 device-level HBM used/free 当作某个单 request 的精确显存。
- 不输出 memory-bound、scheduler-bound、prefix-cache memory benefit、HBM bottleneck 等归因结论。
- 不回传大日志、大 zip、raw profiler、完整 generated text 或超过 70KB 的附件。

## 完成后

请发送任务完成邮件，标题建议：

```text
[AK服务器] 任务完成：P1.30 Qwen3.5-4B vLLM prefix-cache phase memory readout
```

如果无法解析 NPU HBM 或 host process memory，不要用别的指标冒充；请回传失败原因、原始小样例、可用字段和下一步建议。
