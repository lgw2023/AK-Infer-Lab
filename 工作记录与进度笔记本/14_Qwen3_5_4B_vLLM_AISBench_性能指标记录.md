# Qwen3.5-4B / vLLM AISBench 风格性能指标记录

日期：2026-07-09

本页专门记录 P1.28、P1.29、P1.30、P1.31 四轮服务器回传结果中与 Qwen3.5-4B / vLLM 推理性能指标最相关的证据；当前也作为展示页第 5 节与审计正文的细节账本。

## 结论摘要

P1.29 是当前阶段最有价值的一轮 Qwen3.5-4B / vLLM OpenAI streaming client 性能事实表。它在同一 `continuous32_mixed` workload、固定 64 输出 token、prefix-cache on/off A/B 条件下，补齐了 AISBench/MindIE-Motor 风格的 parameter 表和 common metric 表：

- TTFT median：prefix-cache on `8.277s`，off `12.917s`。
- TPOT median：on `137.4ms`，off `270.7ms`。
- E2EL / client wall median：on `16.405s`，off `30.025s`。
- Benchmark Duration：on `20.701s`，off `37.693s`。
- Request Throughput：on `1.546 req/s`，off `0.849 req/s`。
- Output Token Throughput：on `98.93 token/s`，off `54.33 token/s`。
- Total Token Throughput：on `10750.54 token/s`，off `5904.32 token/s`。

P1.30 则补齐 P1.29 之后仍缺的 phase memory matrix：`prefix_cache_on/off x prefill/decode` 的 host RSS/PSS 与 NPU HBM used/free。P1.30 显示，在本轮采样口径下，四个 phase row 的 whole-device HBM 汇总均为 `55050.24 MB used / 10485.76 MB free / 84.0% max usage`；host process-group RSS/PSS 在 on/off 之间只有十几 MB 到几 MB 级差异；vLLM server log proxy 的 `kv_cache_usage_pct_max` 在附件表中为 on `9.4`、off `16.1`。

P1.31 把输入 cap 扩展到 `8K/16K/32K/64K/128K`，把 target shared-prefix ratio 扩展到 `30%/60%/90%`，固定输出目标为 `1024 tokens`，并对 prefix-cache on/off 做 15 cell 成对矩阵。它证明当前 Qwen3.5-4B / vLLM OpenAI streaming client 能完成长上下文矩阵：on/off 均 15/15 cell success，64K/128K 全部成功；off 侧 observed hit rate 全为 `0.0`，on 侧 observed hit rate 为 `22.5%` 到 `84.8%`。一个 `cap8192_prefix60` measured request 生成 `1023/1024` tokens，按用户确认和服务器 acceptance policy 作为成功样本处理。

这些结果可以作为“scoped performance facts”入账，但仍不能发布为 MindIE native AISBench 结果、compute-bound/memory-bound 结论、HBM bottleneck 结论、scheduler-bound 结论或 prefix-cache benefit 归因。

## 证据与归档

P1.28：

```text
run_id=runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028
归档=工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028/server_feedback/
附件来源=/Users/liguowei/Downloads/akp1_28vllmapimsproflargercontrolledreplay
```

P1.29：

```text
run_id=runtime_vllm_api_streaming_perf_denominator_2026_0708_p1_029
归档=工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_streaming_perf_denominator_2026_0708_p1_029/server_feedback/
附件来源=/Users/liguowei/Downloads/akp1_29qwen3_54bvllmapistreamingperfdenomi
```

P1.30：

```text
run_id=runtime_vllm_api_memory_phase_readout_2026_0708_p1_030
source_run_id=runtime_vllm_api_streaming_perf_denominator_2026_0708_p1_029
归档=工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_memory_phase_readout_2026_0708_p1_030/server_feedback/
附件来源=/Users/liguowei/Downloads/akp1_30qwen3_54bvllmprefixcachephasememory
```

P1.31：

```text
run_id=runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031
归档=工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031/server_feedback/
附件来源=/Users/liguowei/Downloads/ 下 20 封 P1.31 邮件和小附件
服务器完整目录=/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031
```

P1.31 本地归档需要保留一个下载细节：第一次手动下载时，部分 on/off 同名附件被覆盖，包括 `request_summary.tsv`、`server_stats_summary.tsv`、`phase_memory_summary.tsv`、`result.json`；用户随后补充了带邮件名和附件名的唯一命名附件，本地归档已补齐 on/off 双侧表。prefix-cache on 的 `server_stats_summary.tsv` 附件中 mode/cell 标签列为空，但 stats 数值保留；本页引用分 cell hit rate 与 KV cache proxy 时优先采用 `matrix_summary/prefix_ratio_matrix_delta_summary.tsv`。完整 raw artifact 仍以服务器本地 artifact index 为准。

P1.30 邮件正文与本地附件存在一个小差异，需要保留：

- 邮件正文写的是 prefix-cache on `max_kv_cache_usage_pct=10.1`、off `16.0`。
- 本地附件 `summary.txt`、`p1_030_result.json` 和 `memory_phase_summary.tsv` 写的是 on `9.4`、off `16.1`。
- 本页采用已归档附件表格作为可复查 artifact 主证据，同时保留邮件正文差异，避免后续引用时混淆。

另一个格式细节：P1.30 附件文件名为 `memory_phase_summary.tsv`，但当前落盘内容实际使用逗号分隔。

## P1.28：受控 replay 扩大到 32 请求

P1.28 的核心价值不是用户侧性能表，而是把 P1.26/P1.27 的固定输出受控复现扩大到 `continuous32_mixed`：

- `case_plan=continuous32_mixed`。
- `max_model_len=9216`。
- `request_min_tokens=64`。
- `request_ignore_eos=1`。
- prefix-cache on/off 两轮均 `request_count=32`、`success_case_count=32`、`failed_case_count=0`。
- 两轮均 `generated_token_count_mismatch_count=0`，`min_generated_token_count=max_generated_token_count=64`。
- request-device full 聚合成功：on `32` 行 request summary、`640` 行 top-op、`32` 行 AI Core metric；off 同样 `32/640/32`。
- readout `overall_status=success`、`missing_files=[]`。
- readout 小摘要包含 `mode_delta_group_count=12`、`pair_delta_row_count=8`、`top_op_delta_row_count=23`、`metric_delta_row_count=21`。
- all-request raw delta 中 `negative_duration_delta_request_count=32`、`positive_duration_delta_request_count=0`。

边界：

- P1.28 是 raw counter readout，不是 benchmark。
- P1.28 不输出吞吐、latency、scheduler 效率、prefix-cache 命中率验收或瓶颈归因。
- P1.28 的价值是支撑 P1.29 能在更大、更受控的 32 请求 workload 上继续补用户侧 streaming 指标。

## P1.29：AISBench 风格 parameter 表

P1.29 条件：

- 模型：`Qwen3.5-4B`。
- 路径：vLLM OpenAI streaming client。
- workload：`continuous32_mixed`。
- `max_model_len=9216`。
- `min_tokens=64`。
- `ignore_eos=1`。
- prefix-cache on/off A/B。
- on/off 均 `32/32` 成功、失败 `0`、生成长度 mismatch `0`。
- on/off 总输入 token 均为 `220502`。
- on/off 总输出 token 均为 `2048`。
- 每请求输出 token 固定为 `64`。

Parameter 表来自 `vllm_api_streaming_perf_parameters.tsv`：

| Metric | Mode | Average | Min | Max | Median | P75 | P90 | P99 | N | Unit |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| E2EL | on | 16359.330 | 15442.011 | 17143.512 | 16404.872 | 16724.225 | 16828.388 | 17111.817 | 32 | ms |
| E2EL | off | 27852.395 | 18534.275 | 32682.666 | 30024.809 | 31286.328 | 32201.320 | 32659.332 | 32 | ms |
| TTFT | on | 6803.979 | 1549.062 | 9695.890 | 8276.868 | 9029.211 | 9475.670 | 9677.677 | 32 | ms |
| TTFT | off | 12732.687 | 1332.521 | 26508.421 | 12916.854 | 18841.982 | 23591.355 | 26263.085 | 32 | ms |
| TPOT | on | 151.672 | 96.094 | 220.522 | 137.365 | 185.352 | 207.006 | 218.432 | 32 | ms |
| TPOT | off | 239.995 | 98.003 | 304.487 | 270.671 | 287.973 | 301.638 | 304.074 | 32 | ms |
| ITL | on | 143.694 | 96.489 | 228.659 | 97.861 | 228.303 | 228.517 | 228.657 | 32 | ms |
| ITL | off | 243.828 | 99.382 | 308.139 | 295.179 | 304.177 | 307.457 | 308.042 | 32 | ms |
| OutputTokenThroughput | on | 3.915 | 3.733 | 4.145 | 3.901 | 4.005 | 4.027 | 4.124 | 32 | token/s |
| OutputTokenThroughput | off | 2.370 | 1.958 | 3.453 | 2.132 | 2.623 | 3.122 | 3.406 | 32 | token/s |
| PrefillTokenThroughput | on | 1219.219 | 469.543 | 3855.236 | 947.940 | 1532.822 | 1731.848 | 3477.648 | 32 | token/s |
| PrefillTokenThroughput | off | 945.208 | 250.154 | 4481.730 | 555.822 | 1239.987 | 1771.481 | 4054.405 | 32 | token/s |

Input/output token rows：

- `InputTokens` on/off 平均均为 `6890.6875`，min `4096`，max `8192`，median/P75/P90/P99 均为 `8192`。
- `OutputTokens` on/off 的 Average/Min/Max/Median/P75/P90/P99 均为 `64`。

关键 ratio：

- E2EL median on/off ratio `0.546`。
- E2EL P99 on/off ratio `0.524`。
- TTFT median on/off ratio `0.641`。
- TTFT P99 on/off ratio `0.368`。
- TPOT median on/off ratio `0.507`。
- TPOT P99 on/off ratio `0.718`。
- per-request OutputTokenThroughput median on/off ratio `1.830`。
- per-request PrefillTokenThroughput median on/off ratio `1.705`。

口径说明：

- `E2EL` 是 client wall time，来自 streaming client。
- `TTFT` 是 host client first non-empty text chunk。
- `TPOT` 是 `(response_end - first_token) / (generated_tokens - 1)`。
- `ITL` 是 host streaming inter-chunk median per request，不是 runtime native decode event。
- `OutputTokenThroughput` 是 per-request `generated_tokens / client_wall_time` 后再做统计。
- `PrefillTokenThroughput` 是 `input_tokens / TTFT` 的 host-client approximation，不是 MindIE native `prefill_time`。

## P1.29：AISBench 风格 common metrics

Common metrics 来自 `vllm_api_streaming_perf_common_metrics.tsv`：

| Metric | prefix-cache on | prefix-cache off | Unit |
| --- | ---: | ---: | --- |
| Benchmark Duration | 20701.285 | 37692.712 | ms |
| Total Requests | 32 | 32 | request |
| Failed Requests | 0 | 0 | request |
| Success Requests | 32 | 32 | request |
| Concurrency | 25.288 | 23.646 | request |
| Max Concurrency | 32 | 32 | request |
| Request Throughput | 1.545798 | 0.848970 | req/s |
| Total Input Tokens | 220502 | 220502 | token |
| Prefill Token Throughput | 10651.609 | 5849.990 | token/s |
| Total generated tokens | 2048 | 2048 | token |
| Input Token Throughput | 10651.609 | 5849.990 | token/s |
| Output Token Throughput | 98.931 | 54.334 | token/s |
| Total Token Throughput | 10750.540 | 5904.324 | token/s |

这里的 throughput 使用 benchmark-window denominator，和 parameter 表中的 per-request throughput 不是同一个分母。

## P1.29：server stats 与 denominator

vLLM server stats：

| Field | prefix-cache on | prefix-cache off | Notes |
| --- | ---: | ---: | --- |
| `server_stats_sample_count` | 2 | 3 | 样本数很少，不能当完整时间序列 |
| `server_stats_max_running_reqs` | 15 | 21 | server log proxy |
| `server_stats_max_waiting_reqs` | 17 | 21 | server log proxy |
| `server_stats_max_kv_cache_usage_pct` | 8.2 | 16.1 | overall KV cache usage proxy，不是 HBM |
| `server_stats_max_prefix_cache_hit_rate_pct` | 63.3 | 0.0 | 证明 on/off 开关路径和 stats 信号有效 |

msprof shape denominator：

- `overall_status=success`。
- `shape_row_count=160`。
- `op_type_row_count=33`。
- on/off 两侧各 `request_count=32`、`shape_row_count=80`。
- MatMulV2 / MatMulV3 有 shape-derived FLOPs denominator。
- input/output tensor footprint bytes 可用，但不是 HBM traffic。

重点 op type denominator：

| Mode | Op type | Occurrences | Duration raw sum | Estimated FLOPs | Estimated tensor bytes | FLOPs status | Bytes status |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| off | MatMulV2 | 181461 | 99472622052 | 28739558912819200 | 27162134446080 | available | available |
| on | MatMulV2 | 49429 | 15620311150 | 3615226331136000 | 5764497295360 | available | available |
| off | MatMulV3 | 181476 | 45610170949 | 12665955192668160 | 13035100962816 | available | available |
| on | MatMulV3 | 39236 | 7188172893 | 1472363568824320 | 2205121421312 | available | available |
| off | FusedInferAttentionScore | 38244 | 44967616785 | 0 | 210614526904160 | missing | available |
| on | FusedInferAttentionScore | 24254 | 13263269641 | 0 | 132955602107360 | missing | available |

单位与可比性：

- client timing 字段 confidence 为 HIGH，可作为用户可见 host wall-clock 指标。
- msprof `task_time.duration_time` confidence 为 MEDIUM，只作为 raw profiler field，不发布为用户侧 latency。
- AI Core raw metric confidence 为 LOW，没有 denominator 时不做 utilization/bottleneck claim。
- MatMul shape-derived FLOPs 与 P0/P3 FP16 square matmul ceiling `290.448949 TFLOPS` 只部分可比。
- tensor footprint bytes 与 HBM bandwidth ceiling 不可直接比较；缺 HBM read/write bytes、cache reuse、MTE traffic、bandwidth counter 和 utilization denominator。

## P1.30：phase memory matrix

P1.30 条件：

- source run：P1.29 `runtime_vllm_api_streaming_perf_denominator_2026_0708_p1_029`。
- commit：附件为 `a0ec67868697ebdab1368fc7c1a06c738a5168bb`。
- `git_pull_exit_code=0`。
- `pytest_exit_code=0`。
- `memory_probe_on_exit_code=0`。
- `memory_probe_off_exit_code=0`。
- `summary_exit_code=0`。
- prefix-cache on/off 均 `request_count=32`、`success=32`、`failed=0`、`generated_token_count_mismatch_count=0`。
- on `memory_sample_count=9`，off `memory_sample_count=15`。

Phase memory summary 来自 `memory_phase_summary.tsv`：

| Mode | Phase | Samples | Overlapped requests | RSS avg MB | RSS max MB | PSS avg MB | PSS max MB | HBM used avg MB | HBM free min MB | HBM usage max % | KV cache usage max % |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| prefix_cache_on | prefill | 5 | 26 | 5109.184 | 5111.360 | 4377.083 | 4379.112 | 55050.240 | 10485.760 | 84.0 | 9.4 |
| prefix_cache_on | decode | 8 | 31 | 5110.943 | 5114.344 | 4378.816 | 4382.152 | 55050.240 | 10485.760 | 84.0 | 9.4 |
| prefix_cache_off | prefill | 12 | 25 | 5090.707 | 5091.871 | 4376.619 | 4377.767 | 55050.240 | 10485.760 | 84.0 | 16.1 |
| prefix_cache_off | decode | 14 | 19 | 5090.991 | 5092.816 | 4376.917 | 4378.814 | 55050.240 | 10485.760 | 84.0 | 16.1 |

Delta 读法：

- prefill RSS avg：on 比 off 高 `18.477 MB`。
- decode RSS avg：on 比 off 高 `19.952 MB`。
- prefill PSS avg：on 比 off 高 `0.464 MB`。
- decode PSS avg：on 比 off 高 `1.899 MB`。
- NPU whole-device HBM used/free 在四行中相同：`55050.24 MB used`、`10485.76 MB free`、`84.0% max usage`。
- 附件表中的 `kv_cache_usage_pct_max`：on `9.4`，off `16.1`，on/off ratio 约 `0.584`。

采样策略：

- sample interval：`0.4s`。
- prefill phase：`request_start -> first_token`。
- decode phase：`first_token -> response_end`。
- phase overlap 不丢弃：`overlap_not_discarded`。
- host process scope：vLLM API server root pid 和所有 descendant pids。
- RSS：汇总 `/proc/<pid>/status VmRSS`。
- PSS：可读时汇总 `/proc/<pid>/smaps_rollup Pss`。
- NPU HBM primary command：`npu-smi info -t usages -i 6`。
- NPU HBM 字段：`HBM Capacity(MB)`、`HBM Usage Rate(%)`，派生 used/free MB。
- table crosscheck：`npu-smi info HBM-Usage(MB)` used/total row。

P1.30 可信边界：

- NPU HBM 是 device-level whole-NPU occupancy，不是 per-request exact allocation。
- host RSS/PSS 是 server process group footprint，不是 KV object bytes。
- `kv_cache_usage_pct_max` 是 vLLM server log proxy，不是 HBM used/free。
- phase rows 的 sample_count 会因为 overlap policy 而不能简单相加为 overall sample count。
- P1.30 证明 memory matrix 已补采，但不证明 memory-bound、HBM bottleneck、scheduler-bound 或 prefix-cache memory benefit。

## P1.31：长上下文 prefix ratio matrix

P1.31 条件：

- 模型：`Qwen3.5-4B`。
- 路径：vLLM OpenAI streaming client。
- 服务器 device：`ASCEND_RT_VISIBLE_DEVICES=7`。
- commit：`7e84c7e5a6141fc1a00bb4f57cbf98ac6b32ae66`。
- 输入 cap：`8192`、`16384`、`32768`、`65536`、`131072`。
- target shared-prefix ratio：`30%`、`60%`、`90%`。
- prefix-cache on/off 成对运行。
- 每个 cell 1 个 warmup request，3 个 measured request。
- 目标输出：`1024 tokens`。
- `git_pull_exit_code=0`、`pytest_exit_code=0`、`prefix_cache_on_exit_code=0`、`prefix_cache_off_exit_code=0`、`summary_exit_code=0`。
- `tests/inference_contracts`：`53 passed in 0.53s`。

完成度：

- on/off 均 `cell_count=15`。
- 30 个 mode-cell 全部 `cell_status=success`。
- 每个 cell 均 `measured_success_count=3`、`measured_request_count=3`。
- 64K/128K 全部成功，无失败 cell。
- `cap8192_prefix60` 中一个 measured request 为 `1023/1024`，按用户确认和服务器 `accept_1023_of_1024_as_success_for_matrix_statistics_no_bottleneck_claim` 策略计入成功样本。

Observed prefix hit rate：

| Input cap | target 30% on | target 60% on | target 90% on | off |
| ---: | ---: | ---: | ---: | ---: |
| 8192 | 22.5% | 43.8% | 68.8% | 0.0% |
| 16384 | 23.4% | 50.5% | 72.9% | 0.0% |
| 32768 | 26.9% | 55.7% | 76.6% | 0.0% |
| 65536 | 29.0% | 57.4% | 81.4% | 0.0% |
| 131072 | 29.4% | 58.3% | 84.8% | 0.0% |

TTFT median on/off ratio：

| Input cap | target 30% | target 60% | target 90% |
| ---: | ---: | ---: | ---: |
| 8192 | 0.921 | 0.640 | 0.360 |
| 16384 | 0.964 | 0.656 | 0.212 |
| 32768 | 1.035 | 0.627 | 0.199 |
| 65536 | 0.954 | 0.597 | 0.206 |
| 131072 | 0.959 | 0.590 | 0.189 |

TPOT median on/off ratio：

| Input cap | target 30% | target 60% | target 90% |
| ---: | ---: | ---: | ---: |
| 8192 | 1.044 | 1.008 | 0.951 |
| 16384 | 1.029 | 0.993 | 1.008 |
| 32768 | 1.030 | 1.061 | 0.959 |
| 65536 | 0.983 | 0.972 | 0.963 |
| 131072 | 1.012 | 0.959 | 0.881 |

Client wall median on/off ratio：

| Input cap | target 30% | target 60% | target 90% |
| ---: | ---: | ---: | ---: |
| 8192 | 1.041 | 0.999 | 0.937 |
| 16384 | 1.026 | 0.979 | 0.973 |
| 32768 | 1.030 | 1.027 | 0.899 |
| 65536 | 0.978 | 0.915 | 0.849 |
| 131072 | 0.997 | 0.853 | 0.688 |

Memory and server stats facts:

- vLLM server stats `server_stats_max_kv_cache_usage_pct` stays lower on prefix-cache on than off in every delta row.
- 128K target 30%: on `22.9%` vs off `28.3%`.
- 128K target 60%: on `17.4%` vs off `28.3%`.
- 128K target 90%: on `12.0%` vs off `28.3%`.
- delta summary 中 on/off 的 `hbm_used_max_mb` 均为 `57671.68 MB`；这是 whole-device occupancy，不是 per-request KV object bytes。

AISBench-style 表结构补充：

| asset | count/range | scope | notes |
| --- | --- | --- | --- |
| Performance Parameters rows | 240 | 30 mode-cells x 8 parameters | E2EL/TTFT/TPOT/ITL/InputTokens/OutputTokens/PrefillTokenThroughput/OutputTokenThroughput |
| Common Metric rows | 390 | 30 mode-cells x 13 metrics | Benchmark Duration through Total Token Throughput |
| Request rows | 120 total / 90 measured | on 60, off 60; measured 45+45 | 每个 cell 1 warmup + 3 measured |
| Phase memory rows | 60 | on/off x 15 cells x prefill/decode | process-group RSS/PSS + whole-device HBM |

Performance median 范围：

| metric | prefix-cache on | prefix-cache off | notes |
| --- | --- | --- | --- |
| TTFT median | 0.783-40.301 s | 2.174-42.404 s | from aisbench parameters / delta summary |
| TPOT median | 88.089-107.259 ms | 87.976-105.975 ms | decode wall after first token / generated tokens minus one |
| E2EL/client wall median | 90.835-150.028 s | 92.173-150.452 s | client wall us / 1000 |
| OutputTokenThroughput median | 6.825-11.273 token/s | 6.806-11.110 token/s | per-cell median |
| PrefillTokenThroughput median | 1,888.9-24,890.1 token/s | 3,484.3-30,631.8 token/s | input tokens divided by host-client TTFT approximation |

硬件/process 范围：

| metric | prefix-cache on | prefix-cache off | notes |
| --- | --- | --- | --- |
| HBM used max | 57671.68 MB | 57671.68 MB | whole-device occupancy in every delta row |
| HBM free min / usage max | 7864.32 MB / 88.0% | 7864.32 MB / 88.0% | phase memory probe; not bandwidth |
| RSS max range | 5091.84-5431.83 MB | 5083.84-5365.70 MB | vLLM process group |
| PSS max range | 4235.60-4696.33 MB | 4347.94-4662.93 MB | shared pages proportionally charged |
| KV usage proxy range | 1.7%-22.9% | 2.6%-28.3% | vLLM server stats; not KV object bytes |
| server stats samples | 289 total | 299 total | cell_summary sums |

这些表参考 MindIE-Motor quick_start 的 `Performance Parameters` / `Common Metric` 双表风格组织展示，但 P1.31 的数值来源仍是本地归档的 vLLM OpenAI streaming client server-feedback artifact。

P1.31 可入账事实：

- 当前 Qwen3.5-4B / vLLM path 可以完成 8K 到 128K、30% 到 90% target shared-prefix ratio、1024 输出目标的 on/off 长上下文矩阵。
- target shared-prefix ratio 与 observed prefix hit rate 已分字段记录。
- off 侧 observed hit rate 全为 `0.0`，可作为 prefix-cache off 开关路径的 sanity check。
- P1.31 的 AISBench-style parameter/common metric 表可作为后续 DeepSeek-V4-Flash 表格 schema 参考。

P1.31 不能入账：

- 不能把 target shared-prefix ratio 写成 observed hit rate。
- 不能把 P1.31 称为 MindIE native AISBench/MindIE-Motor 结果。
- 不能把 TPOT ratio 或 client wall ratio 直接写成 prefix-cache 收益归因。
- 不能把 `server_stats_max_kv_cache_usage_pct` 称为 HBM used/free 或 KV object bytes。
- 不能把 Qwen3.5-4B 单卡长上下文事实外推为 DeepSeek-V4-Flash 八卡 benchmark。

## 可入账的结论和仍缺证据

可以入账：

- P1.28 证明 32 请求 fixed-output msprof controlled replay 与 request-device readout 能跑通。
- P1.29 证明 Qwen3.5-4B / vLLM OpenAI streaming client 在 `continuous32_mixed` 上可以产出 AISBench-style parameter/common metric 表。
- P1.29 的 fixed-output A/B 条件成立：on/off 输入 token 总量一致，输出 token 总量一致，每请求输出 token 固定为 64。
- P1.29 可以作为后续 DeepSeek-V4-Flash 性能表 schema 的模板。
- P1.30 补齐了 `prefix_cache_on/off x prefill/decode` 的 host RSS/PSS 与 NPU whole-device HBM readout。
- P1.31 补齐了 Qwen3.5-4B / vLLM 长上下文 prefix ratio matrix，覆盖 8K 到 128K、30%/60%/90% target shared-prefix ratio 和 1024 输出目标。

不能入账：

- 不能把 P1.29 称为 MindIE-Motor 或 AISBench native run。
- 不能把 `ITL` 称为 runtime native decode event。
- 不能把 `PrefillTokenThroughput` 称为 MindIE native `prefill_time` 派生值。
- 不能把 `server_stats_max_kv_cache_usage_pct` 称为 HBM used/free。
- 不能把 tensor footprint bytes 称为 HBM traffic。
- 不能发布 compute-bound、memory-bound、scheduler-bound、HBM bottleneck 或 prefix-cache memory benefit 归因。
- 不能把 Qwen3.5-4B 单卡 vLLM scoped facts 外推为 DeepSeek-V4-Flash 八卡正式 benchmark。

仍缺证据：

- HBM read/write bytes。
- HBM bandwidth counter 和 utilization denominator。
- MTE traffic / cache reuse。
- KV object 生命周期、block allocation/eviction、prefix cache object 级命中链路。
- scheduler wait breakdown。
- slow-token attribution。
- MindIE native AISBench/MindIE-Motor 对照结果。
- DeepSeek-V4-Flash 八卡官方 baseline 与单/双卡极限边界。
