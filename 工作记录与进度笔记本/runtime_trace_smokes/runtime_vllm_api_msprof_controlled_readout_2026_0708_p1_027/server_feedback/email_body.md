# P1.27 Server Feedback Email Body

来源：Gmail message `19f3f82873895b4f`，标题 `[AK服务器] 任务完成：P1.27 vLLM API msprof controlled readout`。

本地状态：用户更正后的附件目录 `/Users/liguowei/Downloads/akp1_27vllmapimsprofcontrolledreadout` 已存在，附件小文件已同步到本目录。本文件保留邮件正文作为旁证，后续判读以同目录内附件文件为准。

```text
P1.27 vLLM API msprof controlled readout 已完成。

run_id: runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027
source_run_id: runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026
commit: c65d9d63c9ec2a0f2ac87ca1d79cb732a2b905eb
artifact_dir: 工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027
git_pull_exit_code: 0
pytest_exit_code: 0
controlled_readout_exit_code: 0
overall_status: success
generated_length_status: fixed_64
missing_files: []

all_request_raw_delta:
- request_count=16
- delta_task_row_count_sum_on_minus_off=-166800
- delta_total_duration_time_sum_on_minus_off=-88984462248
- negative_duration_delta_request_count=16
- positive_duration_delta_request_count=0

output_rows:
- mode_delta_group_count=12
- pair_delta_row_count=8
- top_op_delta_row_count=22
- metric_delta_row_count=21

generated_length_detail:
- mode_count=2, request_count=32, success_case_count=32, failed_case_count=0
- generated_token_count_mismatch_count=0, min_generated_token_count=64, max_generated_token_count=64

服务器执行备注：
- 本轮仅离线读取 P1.26 final_analysis 大表，未启动 vLLM server，未运行新请求，未重新采集 msprof。
- git pull 使用 HTTP 代理；pytest 40 passed。

边界：本轮只做 P1.26 final_analysis 离线读数；未启动 vLLM server，未运行新请求，未重新采集 msprof，未安装或修复包，未输出 benchmark/吞吐/调度效率/prefix cache 命中率/瓶颈/优化结论。
```
