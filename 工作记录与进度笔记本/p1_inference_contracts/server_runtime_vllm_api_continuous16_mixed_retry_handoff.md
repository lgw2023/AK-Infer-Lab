# P1.21 vLLM API Continuous16 Mixed Retry Server Handoff

任务 ID：`runtime_vllm_api_continuous16_mixed_retry_2026_0707_p1_021`

目标：复跑 P1.20 的同一 `continuous16_mixed` 16 请求混合负载，但强制确认 vLLM API server 以 `--max-model-len 9216` 启动。P1.20 的部分失败已明确来自 `--max-model-len 6144`，10 个 8K cap case 被 vLLM 输入长度校验拒绝，不是 API server 启动失败、并发客户端崩溃、trace schema 失败或包环境问题。

本轮仍是 smoke / 入口验证，不是 benchmark、压测、性能归因、prefix cache 命中验收或 CANN device timeline pairing。

## P1.20 回传结论

P1.20 `runtime_vllm_api_continuous16_mixed_2026_0706_p1_020` 已完成但部分失败：

- 服务器执行 commit：`2b7b92905cfa106765eb20196d0c132dbd403ed0`
- `pytest_exit_code=0`
- `vllm_api_continuous16_mixed_exit_code=1`
- `server_ready=1`
- `request_count=16`
- `success_case_count=6`
- `failed_case_count=10`
- `client_overlap_candidate_count=75`
- `trace_validation_errors=0`
- `server_stats_sample_count=1`
- `server_stats_max_running_reqs=6`
- `server_stats_max_waiting_reqs=0`
- `server_stats_max_kv_cache_usage_pct=3.1`
- `server_stats_max_prefix_cache_hit_rate_pct=35.5`

失败点：

- 实际启动命令使用 `--max-model-len 6144`。
- 6 个 4K 或约 6K 内请求成功：`P007`、`P008`、`P011 x4`。
- 10 个 8K cap case 被 HTTP 400 拒绝：`P012 x6`、`P003 x2`、`P009 x2`。
- vLLM 错误为：`This model's maximum context length is 6144 tokens... prompt contains at least 6081 input tokens + 64 output = 6145 tokens`。

## 本轮必须改正的点

本轮不能再以 `6144` 启动 server。必须同时在以下文件中看到 `9216`：

- `vllm_api_server_command.json` 中的 `--max-model-len` 后一个参数。
- `run_context.txt` 中的 `max_model_len=9216`。
- `summary.txt` 的 run context 段。

本地脚本已经将 `continuous16_mixed` 的默认 `max_model_len` 调整为 `9216`，但服务器执行命令仍必须显式传入：

```bash
--max-model-len "${AK_VLLM_MAX_MODEL_LEN}"
```

并设置：

```bash
export AK_VLLM_MAX_MODEL_LEN="${AK_VLLM_MAX_MODEL_LEN:-9216}"
```

如果 `9216` 下失败，不要静默降低为 `8192`、`6144` 或减少 case；请原样回传失败 artifact。

## 本轮 case 策略

仍使用脚本参数：

```bash
--case-plan continuous16_mixed
```

保持 P1.20 相同 16 个 case，不删减：

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

## 本轮必须回答

1. 当前环境中 `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 是否可 import？
2. `vllm_api_server_command.json` 是否明确记录 `--max-model-len 9216`？
3. `run_context.txt` 是否明确记录 `max_model_len=9216`？
4. 使用 `VLLM_PLUGINS=ascend` 和 CANN/ATB 环境后，vLLM OpenAI API server 是否能启动并通过 `/health`？
5. `/v1/completions` 是否能接受 16 个错开请求？
6. 16 个 case 是否全部返回 HTTP 200？
7. 16 个 case 是否全部返回非空输出或正的 `generated_token_count`？
8. 每个 case 的 `submitted_input_token_count` 是否等于 `input_token_count`？
9. 客户端侧请求时间窗是否出现 overlap candidate？
10. 是否能生成合法的 `vllm_api_concurrency_trace.jsonl` 并通过 P1 validator？
11. 是否能生成 `vllm_api_server_stats_summary.tsv` 并抽取 Running/Waiting/KV/prefix-cache 自带统计？
12. 如果失败，失败点是 max-model-len 未生效、API server start、health probe、HTTP 400、NPU/OOM、输出为空、input count mismatch、trace 校验，还是 server log stats 缺失？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`
- source `/usr/local/Ascend/nnal/atb/set_env.sh`
- 使用当前环境已有 `vllm` 和 `vllm_ascend`
- 设置本进程环境变量 `ASCEND_RT_VISIBLE_DEVICES`、`VLLM_USE_V1`、`VLLM_PLUGINS=ascend`、`VLLM_WORKER_MULTIPROC_METHOD`
- 设置 `AK_VLLM_MAX_MODEL_LEN=9216`
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 在 `127.0.0.1` 启动一个临时 vLLM OpenAI API server
- 只向本机回环 `/v1/completions` 发送本 handoff 列出的 16 个请求
- 导出 server command、server log、server log stats summary、trace、summary、generated texts、失败日志和邮件附件

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不静默降低 `max_model_len`、不删减 case、不缩短 output token
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

强成功：

- `pytest_exit_code=0`
- `vllm_api_continuous16_mixed_retry_exit_code=0`
- `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 均 import 成功
- `vllm_api_server_command.json` 明确记录 `--max-model-len 9216`
- `run_context.txt` 明确记录 `max_model_len=9216`
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
