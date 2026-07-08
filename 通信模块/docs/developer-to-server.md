# Developer to Server

## 当前任务：P1.27 vLLM API msprof controlled readout

- 任务 ID：`runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027`
- 上一轮依据：`runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_vllm_api_msprof_controlled_readout_handoff.md`
- 请按详细 handoff 中 `建议执行命令` 的完整 bash 代码块执行。

## 为什么进入 P1.27

P1.26 已经把 P1.25b 暴露的生成长度混杂消掉：

- commit：`e2fa57cc759ca8317a8109e0617f6d4fffa36a05`
- `pytest_exit_code=0`
- `msprof_prefix_cache_on_exit_code=0`
- `msprof_prefix_cache_off_exit_code=0`
- `request_device_aggregate_fast_exit_code=0`
- `msprof_prefix_cache_on`: `request_count=16`、`success_case_count=16`、`generated_token_count_mismatch_count=0`、`min=max=64`
- `msprof_prefix_cache_off`: `request_count=16`、`success_case_count=16`、`generated_token_count_mismatch_count=0`、`min=max=64`
- `final_analysis` 为 `overall_status=success`
- on/off 两个 mode 均输出 request summary、top-op summary、AI Core metric summary 和 prefix delta 表。

这说明当前问题已经从“能否受控采集/聚合”转为“如何读 P1.26 的受控证据”。P1.27 不重新跑模型，只在服务器本地读取 P1.26 `final_analysis` 大表，生成可邮件回传的小读数摘要。

## 通信前置要求

- 昇腾服务器每次邮件正文和每个附件都按不超过 70KB 处理。
- 不要通过邮件发送 raw profiler、完整日志、大 zip、模型输出、实验目录或其他大文件。
- raw msprof、完整 `request_top_op_type_duration.tsv`、完整 `request_ai_core_metric_summary.tsv` 等大文件留在昇腾服务器本地。
- 邮件只回传任务状态、精简摘要、小 TSV/JSON、70KB 内附件和服务器侧路径。

## 服务器需要做什么

1. 在 `/data/node0_disk1/liguowei/AK-Infer-Lab` 执行详细 handoff 的完整 bash 块。
2. 执行 `git pull --ff-only`。
3. 运行本地测试：`python -m pytest tests/inference_contracts -q`。
4. 运行：
   - `tools/inference_contracts/summarize_msprof_controlled_replay.py`
5. 只读输入：
   - `工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026/generated_token_length_summary.tsv`
   - `工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026/final_analysis/`
6. 输出：
   - `controlled_replay_mode_delta_summary.tsv`
   - `controlled_replay_pair_delta_summary.tsv`
   - `controlled_replay_top_op_delta.tsv`
   - `controlled_replay_ai_core_metric_delta.tsv`
   - `controlled_replay_readout_result.json`
   - `summary.txt`
   - `mail_attachment_candidates.tsv`

## 成功口径

强成功：

- `git_pull_exit_code=0`
- `pytest_exit_code=0`
- `controlled_readout_exit_code=0`
- `controlled_replay_readout_result.json` 中 `overall_status=success`
- `generated_length_status.status=fixed_64`
- `missing_files=[]`
- 产出 mode delta、pair delta、top-op delta、AI Core metric delta 四类小摘要。

最低完成：

- 即使 `controlled_readout_exit_code != 0`，也必须回传 `run_context.txt`、`mail_summary.txt`、`controlled_readout.log` 的尾部错误摘要，以及缺失文件列表。
- 不要为补齐缺失文件而重新跑模型或重新采集 msprof；只报告 P1.26 服务器侧路径状态。

## 执行边界

允许：

- `git pull --ff-only`。
- 使用当前 conda 环境运行本地 Python 脚本和 `pytest tests/inference_contracts -q`。
- 只读访问 P1.26 `final_analysis`、P1.26 `generated_token_length_summary.tsv` 和 P1.26 raw artifact 路径。
- 输出 70KB 内的小摘要 TSV/JSON/txt。

禁止：

- 不启动 vLLM API server。
- 不运行新的模型推理请求。
- 不重新运行 msprof。
- 不安装、升级、卸载或修复任何包。
- 不创建新 conda 环境。
- 不改 driver、CANN、apt、dpkg、NPU runtime、vLLM 或 vLLM-Ascend 源码。
- 不运行 full 16K/32K 或 full `P010=43216` tokens。
- 不运行多 worker 压测、benchmark、长时间服务或吞吐压测。
- 不切换 Docker 推理栈。
- 不在服务器上修改、提交或 push 项目代码。
- 不回传 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息。
- 不回传超过 70KB 的邮件正文或附件；raw profiler、完整日志、大 zip、完整大 TSV 和实验目录必须留在服务器本地。
- 不输出性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因或优化建议。

## 回传要求

邮件正文请包含：

```text
P1.27 vLLM API msprof controlled readout 已完成/失败。

run_id: runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027
source_run_id: runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026
commit: <git rev-parse HEAD>
artifact_dir: 工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027
git_pull_exit_code: <...>
pytest_exit_code: <...>
controlled_readout_exit_code: <...>
overall_status: <...>
generated_length_status: <fixed_64/not_fixed_64>
missing_files: <[] 或列表>

all_request_raw_delta:
- request_count=<...>
- delta_task_row_count_sum_on_minus_off=<...>
- delta_total_duration_time_sum_on_minus_off=<...>
- negative_duration_delta_request_count=<...>
- positive_duration_delta_request_count=<...>

output_rows:
- mode_delta_group_count=<...>
- pair_delta_row_count=<...>
- top_op_delta_row_count=<...>
- metric_delta_row_count=<...>

边界：本轮只做 P1.26 final_analysis 离线读数；未启动 vLLM server，未运行新请求，未重新采集 msprof，未安装或修复包，未输出 benchmark/吞吐/调度效率/prefix cache 命中率/瓶颈/优化结论。
```

附件只允许包含 `mail_attachment_candidates.tsv` 中 `mail_ok=true` 且不超过 70KB 的小文件。优先回传：

- `mail_summary.txt`
- `summary.txt`
- `run_context.txt`
- `controlled_replay_readout_result.json`
- `controlled_replay_mode_delta_summary.tsv`
- `controlled_replay_pair_delta_summary.tsv`
- `controlled_replay_top_op_delta.tsv`
- `controlled_replay_ai_core_metric_delta.tsv`
- `mail_attachment_candidates.tsv`

如果任何 TSV、JSON 或 log 超过 70KB，不要压缩或拆分回传；正文只写服务器路径、文件大小和关键行数。
