# P1.22 vLLM API Prefix Cache A/B Stats Smoke

任务 ID：`runtime_vllm_api_prefix_cache_ab_2026_0707_p1_022`

目标：在 P1.21 已证明 `Qwen3.5-4B + vLLM OpenAI API server + continuous16_mixed + --max-model-len 9216` 可完整跑通后，使用同一 16 请求负载连续执行两轮受控对照：`prefix_cache_on` 启用 `--enable-prefix-caching`，`prefix_cache_off` 显式关闭 prefix cache。只收集 vLLM 自带 server log stats、server command、client overlap 和 P1 trace 校验结果，判断 prefix-cache 开关路径和日志观测字段是否可稳定对照。

本轮不是 benchmark、压测、吞吐比较、调度效率结论、prefix cache 命中验收、瓶颈归因或 CANN device timeline pairing。

通信前置要求：服务器 pull 后请确认项目根目录本地 `.env` 中 `AK_COMM_MAIL_TO=yilili1023@gmail.com`，本轮邮件不再发送到 `gwlee1995@gmail.com`。不要回传 `.env`、SMTP 授权码或代理凭据。

## 已有依据

P1.21 `runtime_vllm_api_continuous16_mixed_retry_2026_0707_p1_021` 已成功：

- `pytest_exit_code=0`
- `vllm_api_continuous16_mixed_retry_exit_code=0`
- `case_plan=continuous16_mixed`
- `max_model_len=9216`
- `request_count=16`
- `success_case_count=16`
- `failed_case_count=0`
- `client_overlap_candidate_count=120`
- `trace_validation_errors=0`
- `server_stats_sample_count=2`
- `server_stats_max_running_reqs=16`
- `server_stats_max_waiting_reqs=1`
- `server_stats_max_kv_cache_usage_pct=8.6`
- `server_stats_max_prefix_cache_hit_rate_pct=52.1`

因此下一轮不再重复单次 smoke，而是做同负载 prefix-cache 开关 A/B 证据采集。

## 本轮必须回答

1. 当前环境中 `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 是否可 import？
2. `prefix_cache_on/vllm_api_server_command.json` 是否包含 `--enable-prefix-caching`？
3. `prefix_cache_off/vllm_api_server_command.json` 是否不包含 `--enable-prefix-caching`？
4. 两轮 `run_context.txt` 是否都记录 `max_model_len=9216`？
5. 两轮是否都使用 `--case-plan continuous16_mixed`，且都发送同一 16 个 case？
6. 两轮 vLLM OpenAI API server 是否都能 ready？
7. 两轮 16 个 case 是否都返回 HTTP 200 并生成非空输出或正的 `generated_token_count`？
8. 两轮是否都满足 `submitted_input_token_count == input_token_count`？
9. 两轮客户端侧请求时间窗是否都有 overlap candidate？
10. 两轮 `vllm_api_concurrency_trace.jsonl` 是否都通过 P1 validator？
11. 两轮是否都导出 `vllm_api_server_stats_summary.tsv`；如果关闭 prefix cache 后日志不再输出 `Prefix cache hit rate` 字段，请原样记录为缺失，不要当场修改脚本或环境。
12. 汇总 `prefix_cache_ab_summary.tsv` 是否列出两轮的 prefix 开关、请求成功数、overlap、Running/Waiting/KV/prefix-cache 自带统计字段？

## 本轮 case

两轮都使用：

```bash
--case-plan continuous16_mixed
--max-model-len 9216
```

保持 P1.21 相同 16 个 case，不删减、不降 cap、不缩短 decode：

| case_id | prompt_id | cap_tokens | max_new_tokens | delay |
| --- | --- | ---: | ---: | ---: |
| `P007_api_continuous16_prefix_first_cap8192_gen64` | `P007` | 8192 | 64 | 0ms |
| `P008_api_continuous16_prefix_second_cap8192_gen64` | `P008` | 8192 | 64 | 100ms |
| `P011_api_continuous16_burst_001_cap4096_gen64` | `P011` | 4096 | 64 | 200ms |
| `P011_api_continuous16_burst_002_cap4096_gen64` | `P011` | 4096 | 64 | 300ms |
| `P011_api_continuous16_burst_003_cap4096_gen64` | `P011` | 4096 | 64 | 400ms |
| `P011_api_continuous16_burst_004_cap4096_gen64` | `P011` | 4096 | 64 | 500ms |
| `P012_api_continuous16_001_cap8192_gen64` | `P012` | 8192 | 64 | 600ms |
| `P012_api_continuous16_002_cap8192_gen64` | `P012` | 8192 | 64 | 800ms |
| `P012_api_continuous16_003_cap8192_gen64` | `P012` | 8192 | 64 | 1000ms |
| `P012_api_continuous16_004_cap8192_gen64` | `P012` | 8192 | 64 | 1200ms |
| `P012_api_continuous16_005_cap8192_gen64` | `P012` | 8192 | 64 | 1400ms |
| `P012_api_continuous16_006_cap8192_gen64` | `P012` | 8192 | 64 | 1600ms |
| `P003_api_continuous16_system_001_cap8192_gen64` | `P003` | 8192 | 64 | 1800ms |
| `P003_api_continuous16_system_002_cap8192_gen64` | `P003` | 8192 | 64 | 2000ms |
| `P009_api_continuous16_moe_001_cap8192_gen64` | `P009` | 8192 | 64 | 2200ms |
| `P009_api_continuous16_moe_002_cap8192_gen64` | `P009` | 8192 | 64 | 2400ms |

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 仅在服务器本地 `.env` 中确认或更新 `AK_COMM_MAIL_TO=yilili1023@gmail.com`
- 使用服务器当前 conda 环境
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`
- source `/usr/local/Ascend/nnal/atb/set_env.sh`
- 使用当前环境已有 `vllm` 和 `vllm_ascend`
- 设置 `ASCEND_RT_VISIBLE_DEVICES`、`VLLM_USE_V1`、`VLLM_PLUGINS=ascend`、`VLLM_WORKER_MULTIPROC_METHOD`
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 在 `127.0.0.1` 先后启动两个临时 vLLM OpenAI API server
- 分别运行 `prefix_cache_on` 和 `prefix_cache_off` 两个同负载子任务
- 导出每轮 server command、run context、server log、server log stats summary、trace、summary、result、generated texts、失败日志和总 summary

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不静默降低 `max_model_len`、不删减 case、不降低输入 cap、不缩短 output token
- 不运行 benchmark、吞吐测试、压测或长时间服务
- 不运行多 worker 压测客户端
- 不运行 full 16K/32K 或 full `P010=43216` tokens
- 不切换到 Docker 推理栈；Docker 内 vLLM/torch_npu 另起任务
- 不复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不启用 profiler 导出；profiler/CANN pairing 另起任务处理
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息
- 不输出性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因、优化建议或 CANN device timeline pairing 结论

## 成功口径

强成功：

- `pytest_exit_code=0`
- `prefix_cache_on_exit_code=0`
- `prefix_cache_off_exit_code=0`
- `prefix_cache_ab_validation_exit_code=0`
- 两轮 `request_count=16`
- 两轮 `success_case_count=16`
- 两轮 `failed_case_count=0`
- 两轮 `client_overlap_candidate_count > 0`
- 两轮 `trace_validation_errors=0`
- 两轮 `max_model_len=9216`
- `prefix_cache_on` 命令包含 `--enable-prefix-caching`
- `prefix_cache_off` 命令不包含 `--enable-prefix-caching`
- `prefix_cache_ab_summary.tsv` 已生成并记录两轮 vLLM 自带 stats 字段

无论成功或失败，本轮都不能把 A/B 结果解释成吞吐优劣、调度效率、prefix cache 命中验收、瓶颈归因或优化建议。

## 执行入口

当前服务器执行命令写在：

```text
通信模块/docs/developer-to-server.md
```

核心运行脚本：

```text
tools/inference_contracts/run_vllm_api_concurrency_smoke.py
```
