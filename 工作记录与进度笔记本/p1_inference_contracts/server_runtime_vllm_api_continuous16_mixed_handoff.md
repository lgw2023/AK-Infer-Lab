# P1.20 vLLM API Continuous16 Mixed Smoke Server Handoff

任务 ID：`runtime_vllm_api_continuous16_mixed_2026_0706_p1_020`

目标：在 P1.19 已证明 vLLM OpenAI API server 能处理 8 个错开 100ms 的 4K burst / queue 请求后，推进到更接近 `W7_continuous_batching` 的受控混合负载。本轮一次覆盖 16 个本机回环 `/v1/completions` 请求，混合 4K/8K 输入、64-token decode、repeated-prefix、burst queue、continuous arrival、long-system 和 mixed-reasoning prompt。它仍不是 benchmark、压测或性能归因任务。

## 背景

P1.19 `runtime_vllm_api_burst_queue_smoke_2026_0706_p1_019` 已成功：

- 服务器执行 commit：`de6208d5f7691c501ddd55cf701c7d73570c0b8f`
- `pytest_exit_code=0`
- `vllm_api_burst_queue_exit_code=0`
- `status=success`
- `case_plan=burst8`
- `server_ready=1`
- `request_count=8`
- `success_case_count=8`
- `failed_case_count=0`
- `client_overlap_candidate_count=28`
- `prefix_cache_requested=1`
- `input_count_mismatch_count=0`
- `submitted_count_mismatch_count=0`
- `trace_event_count=57`
- `trace_validation_errors=0`
- 8 个 `/v1/completions` 请求均返回 HTTP 200 并生成 32 tokens。

P1.19 的 vLLM server log 已出现 `Running: 8 reqs`、`GPU KV cache usage` 和 `Prefix cache hit rate` 等自带统计。本轮允许抽取这些日志统计作为候选观测数据，但不能把它写成吞吐 benchmark、调度效率结论、prefix cache 命中结论或瓶颈归因。

## 本轮 case 策略

本轮使用脚本参数：

```bash
--case-plan continuous16_mixed
```

| case_id | prompt_id | cap_tokens | max_new_tokens | delay | 目的 |
| --- | --- | ---: | ---: | ---: | --- |
| `P007_api_continuous16_prefix_first_cap8192_gen64` | `P007` | 8192 | 64 | 0ms | repeated-prefix pair 第一条，完整约 6K 输入 |
| `P008_api_continuous16_prefix_second_cap8192_gen64` | `P008` | 8192 | 64 | 100ms | repeated-prefix pair 第二条，完整约 6K 输入 |
| `P011_api_continuous16_burst_001_cap4096_gen64` | `P011` | 4096 | 64 | 200ms | burst queue 候选 |
| `P011_api_continuous16_burst_002_cap4096_gen64` | `P011` | 4096 | 64 | 300ms | burst queue 候选 |
| `P011_api_continuous16_burst_003_cap4096_gen64` | `P011` | 4096 | 64 | 400ms | burst queue 候选 |
| `P011_api_continuous16_burst_004_cap4096_gen64` | `P011` | 4096 | 64 | 500ms | burst queue 候选 |
| `P012_api_continuous16_001_cap8192_gen64` | `P012` | 8192 | 64 | 600ms | continuous-arrival 候选 |
| `P012_api_continuous16_002_cap8192_gen64` | `P012` | 8192 | 64 | 800ms | continuous-arrival 候选 |
| `P012_api_continuous16_003_cap8192_gen64` | `P012` | 8192 | 64 | 1000ms | continuous-arrival 候选 |
| `P012_api_continuous16_004_cap8192_gen64` | `P012` | 8192 | 64 | 1200ms | continuous-arrival 候选 |
| `P012_api_continuous16_005_cap8192_gen64` | `P012` | 8192 | 64 | 1400ms | continuous-arrival 候选 |
| `P012_api_continuous16_006_cap8192_gen64` | `P012` | 8192 | 64 | 1600ms | continuous-arrival 候选 |
| `P003_api_continuous16_system_001_cap8192_gen64` | `P003` | 8192 | 64 | 1800ms | long-system 8K 候选 |
| `P003_api_continuous16_system_002_cap8192_gen64` | `P003` | 8192 | 64 | 2000ms | long-system 8K 候选 |
| `P009_api_continuous16_moe_001_cap8192_gen64` | `P009` | 8192 | 64 | 2200ms | mixed reasoning 8K 候选 |
| `P009_api_continuous16_moe_002_cap8192_gen64` | `P009` | 8192 | 64 | 2400ms | mixed reasoning 8K 候选 |

本轮建议 `AK_VLLM_MAX_MODEL_LEN=9216`，这是 P1.16 已成功使用过的 vLLM 8K 上下文配置，足以覆盖 8192 输入 + 64 decode。

## 本轮必须回答

1. 当前环境中 `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 是否可 import？
2. 使用 `VLLM_PLUGINS=ascend` 和 CANN/ATB 环境后，vLLM OpenAI API server 是否能启动并通过 `/health`？
3. `/v1/completions` 是否能接受 16 个错开请求？
4. 16 个 case 是否全部返回 HTTP 200？
5. 16 个 case 是否全部返回非空输出或正的 `generated_token_count`？
6. 每个 case 的 `submitted_input_token_count` 是否等于 `input_token_count`？
7. 客户端侧请求时间窗是否出现 overlap candidate？
8. 是否能生成合法的 `vllm_api_concurrency_trace.jsonl` 并通过 P1 validator？
9. 是否能生成 `vllm_api_server_stats_summary.tsv`，并从 server log 中抽取 Running/Waiting/KV/prefix-cache 自带统计？
10. 如果失败，失败点是 import、api_server_start、health_probe、CLI 参数、tokenizer、input_count_mismatch、HTTP request、输出为空、NPU/OOM、trace 校验，还是 server log stats 缺失？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`
- source `/usr/local/Ascend/nnal/atb/set_env.sh`
- 使用当前环境已有 `vllm` 和 `vllm_ascend`
- 设置本进程环境变量 `ASCEND_RT_VISIBLE_DEVICES`、`VLLM_USE_V1`、`VLLM_PLUGINS=ascend`、`VLLM_WORKER_MULTIPROC_METHOD`
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 在 `127.0.0.1` 启动一个临时 vLLM OpenAI API server
- 只向本机回环 `/v1/completions` 发送本 handoff 列出的 16 个请求
- 导出 server log、server log stats summary、trace、summary、generated texts、失败日志和邮件附件

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不运行 benchmark、吞吐测试、压测或长时间服务
- 不运行多 worker 压测客户端
- 不运行 full 16K/32K 或 full `P010=43216` tokens
- 不切换到 Docker 推理栈；Docker 内 vLLM/torch_npu 另起任务
- 不复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不启用 profiler 导出；profiler/CANN pairing 另起任务处理
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息
- 不输出性能 benchmark、吞吐结论、调度效率结论、瓶颈归因、优化建议或 CANN device timeline pairing 结论
- 不把 `Prefix cache hit rate` 日志字段单独解释成严格 prefix cache 命中验收

## 成功口径

最低完成：

- pytest 执行并回传日志。
- `vllm_import_probe.tsv` 明确记录 import 成败。
- `vllm_api_server.log` 明确记录 API server 启动或失败信息。
- `vllm_api_concurrency_result.json` 明确给出 `status`、失败阶段和错误堆栈。
- `vllm_api_server_stats_summary.tsv` 存在，即使无样本也要保留表头。

强成功：

- `pytest_exit_code=0`
- `vllm_api_continuous16_mixed_exit_code=0`
- `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 均 import 成功
- vLLM OpenAI API server `/health` ready
- `/v1/completions` 16 个请求均返回 2xx
- 16 个 case 均有非空 generated token 或文本
- 每个 case 的 `submitted_input_token_count == input_token_count`
- `client_overlap_candidate_count > 0`
- `vllm_api_concurrency_trace.jsonl` 校验 `errors=0`
- `server_stats_sample_count > 0`

无论成功或失败，本轮都不能声称 vLLM continuous batching、prefix cache hit rate、吞吐性能、调度瓶颈或 CANN device timeline pairing 已经完成验收。

## 执行入口

当前服务器执行命令写在：

```text
通信模块/docs/developer-to-server.md
```

核心运行脚本：

```text
tools/inference_contracts/run_vllm_api_concurrency_smoke.py
```
