任务：P1.31 Qwen3.5-4B vLLM 长上下文 Prefix-Cache 交叉实验
run_id=runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031
主机：DevServer-BMS-3d97cc99-0
IP：7.150.8.22
时间：2026-07-09 15:05:08
ASCEND_RT_VISIBLE_DEVICES=7
artifact_dir（服务器）：/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031

结果摘要：
\- 全部 exit code=0：git_pull、pytest、prefix_cache_on、prefix_cache_off、summary
\- on_status/off_status/summary_status=success
\- 无 compute/memory/HBM/scheduler/prefix-cache benefit 归因（no bottleneck claims）
\- token_count_acceptance_policy=accept_1023_of_1024_as_success_for_matrix_statistics_no_bottleneck_claim
\- accepted_cells：cap8192_prefix60（measured_02 generated_token_count=1023）

developer-to-server.md 必须回答：

1. git pull --ff-only 后 commit=7e84c7e5a6141fc1a00bb4f57cbf98ac6b32ae66
2. tests/inference_contracts：pytest_exit_code=0，53 passed in 0.53s
3. prefix_cache_on/off 均覆盖 15 个 cell，on_cell_count=15，off_cell_count=15
4. 每个成功 cell：measured_request_count=3、measured_success_count=3（见 completeness.tsv 附件系列邮件）
5. 输出固定 1024 tokens；acp8192_prefix60 的 measured_02 为 1023/1024，按 token_count_acceptance_policy 计入矩阵统计成功；其余 cell generated_token_count_mismatch_count=0
6. prefix_ratio_matrix_aisbench_parameters.tsv 已生成；performance_parameter 含：E2EL, TTFT, TPOT, ITL, InputTokens, OutputTokens, OutputTokenThroughput, PrefillTokenThroughput；文件头列=['mode', 'input_cap_tokens', 'target_prefix_ratio_pct', 'performance_parameter', 'stage']...
7. prefix_ratio_matrix_common_metrics.tsv 已生成；common_metric 含：Benchmark Duration, Concurrency, Max Concurrency, Request Throughput, Input Token Throughput, Output Token Throughput, Total Token Throughput
8. prefix_ratio_matrix_delta_summary.tsv 已生成；分开记录 target shared-prefix ratio 与 observed prefix cache hit rate
9. prefix_cache_off 全部 15 cell 的 observed prefix cache hit rate=0.0（见 server_stats/delta 附件邮件）
10. 64K(cap65536)/128K(cap131072) 全部成功，无失败 cell；未单独保留失败日志
11. phase_memory_summary.tsv 已生成（on/off 各一封附件邮件）；口径仍为 process-group RSS/PSS 与 whole-device HBM occupancy
12. 本批邮件脚本发送前校验：正文 UTF-8 与每个附件均 <= 71680 bytes


大文件留存路径：见末封邮件 artifact index；raw server log / 完整 generated text 留在服务器本地。

附件：/Users/liguowei/Downloads/akp1_31prefixcachedevelopertoser